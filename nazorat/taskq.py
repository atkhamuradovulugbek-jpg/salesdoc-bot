"""
taskq.py — VAZIFA NAVBATI (2-bosqich, 2026-07-30).

QOIDA: web dastur bazaga OG'IR ish qilmaydi va sync ishlatmaydi — u shu jadvalga
kichik "vazifa" qatorini yozadi. Vazifani **nazorat boti** bajaradi (u yagona
yozuvchi, o'z sync qulfi bilan). Shu bilan:
  • web jarayoni muzlab qolmaydi (sync 2-15 daqiqa davom etadi);
  • ikki jarayon bir vaqtda Sales Doctor'ga urilmaydi (2026-07-15 nosozligi);
  • kechki hisobot vaqtida (BLACKOUT 19:50–20:35) sync boshlanmaydi — navbatda kutadi.

Vazifa turlari: sync_fast, sync_full, bind_approve, bind_reject, unbind.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from db import get_conn

from . import storage
from .nz_config import (EVENING_HOUR, EVENING_MINUTE, MORNING_HOUR, MORNING_MINUTE,
                        TIMEZONE)

logger = logging.getLogger("nazorat.taskq")
TZ = ZoneInfo(TIMEZONE)

# HISOBOT VAQTLARI atrofidagi "tinchlik oynasi": sync BOSHLANMAYDI.
# Sabab: sync 2-15 daqiqa davom etadi va bitta jarayon qulfini egallaydi — hisobot
# o'z sync'ini qila olmay qoladi. Shu sababli HAR IKKI hisobot (10:00 va 20:10)
# himoyalanadi (2026-07-30 review topdi: avval faqat kechki himoyalangan edi).
# To'liq sync 10-15 daqiqa ketadi → unga kengroq zapas kerak.
BLACKOUT_AFTER_MIN = 25       # hisobotdan keyin (hisobot yuborilib bo'lguncha)
BLACKOUT_BEFORE_FAST = 20     # tez sync (2-3 daq) uchun oldindan zapas
BLACKOUT_BEFORE_FULL = 45     # to'liq sync (10-15 daq) uchun oldindan zapas

SYNC_KINDS = ("sync_fast", "sync_full")
# sync_today SYNC_KINDS ga KIRMAYDI: u atigi ~5 soniya — blackout paytida ham
# navbatda kutib qolishi shart emas (quick.refresh o'zi blackout'ni tekshiradi).
KIND_LABELS = {
    "sync_fast": "Tez yangilash",
    "sync_full": "To'liq yangilash",
    "sync_today": "Hozirgi holat",
    "bind_approve": "Ulanishni tasdiqlash",
    "bind_reject": "Ulanishni rad etish",
    "unbind": "Ulanishni uzish",
    "period_preview": "Ball plan namunasi",
    "period_publish": "Ball planni e'lon qilish",
    "period_reopened": "Ball planni tuzatishga ochish",
}


def now_str() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


# ------------------------------------------------------------------
# Blackout (tinchlik oynasi)
# ------------------------------------------------------------------

def _report_times() -> list[tuple[int, str]]:
    """Himoyalanadigan hisobot vaqtlari (daqiqada) + nomi."""
    return [(MORNING_HOUR * 60 + MORNING_MINUTE, "ertalabki"),
            (EVENING_HOUR * 60 + EVENING_MINUTE, "kechki")]


def _mins_to_hhmm(m: int) -> str:
    m %= 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def blackout_window(kind: str = "sync_fast") -> tuple[str, str]:
    """Eng yaqin hisobot uchun tinchlik oynasi ('19:50', '20:35')."""
    before = BLACKOUT_BEFORE_FULL if kind == "sync_full" else BLACKOUT_BEFORE_FAST
    base = _report_times()[-1][0]
    return _mins_to_hhmm(base - before), _mins_to_hhmm(base + BLACKOUT_AFTER_MIN)


def in_blackout(now: datetime | None = None, kind: str = "sync_fast") -> bool:
    """Hozir hisobot vaqtiga yaqinmi (sync boshlash xavfli)?"""
    now = now or datetime.now(TZ)
    mins = now.hour * 60 + now.minute
    before = BLACKOUT_BEFORE_FULL if kind == "sync_full" else BLACKOUT_BEFORE_FAST
    for base, _ in _report_times():
        if (base - before) <= mins <= (base + BLACKOUT_AFTER_MIN):
            return True
    return False


def blackout_note(kind: str = "sync_fast") -> str | None:
    """Web'da ko'rsatiladigan izoh (blackout bo'lmasa None)."""
    now = datetime.now(TZ)
    mins = now.hour * 60 + now.minute
    before = BLACKOUT_BEFORE_FULL if kind == "sync_full" else BLACKOUT_BEFORE_FAST
    for base, label in _report_times():
        if (base - before) <= mins <= (base + BLACKOUT_AFTER_MIN):
            return (f"Hozir {label} hisobot vaqti ({_mins_to_hhmm(base - before)}–"
                    f"{_mins_to_hhmm(base + BLACKOUT_AFTER_MIN)}). Yangilash navbatda turadi "
                    f"va {_mins_to_hhmm(base + BLACKOUT_AFTER_MIN)} dan keyin bajariladi.")
    return None


# ------------------------------------------------------------------
# Navbat: yozish / o'qish
# ------------------------------------------------------------------

def enqueue(conn, kind: str, payload: dict | None = None,
            requested_by: str = "web", dedupe_minutes: int = 0) -> tuple[int | None, str]:
    """Vazifa qo'shadi. Qaytadi: (id, holat izohi).

    dedupe_minutes > 0 bo'lsa: shu turdagi vazifa yaqinda qo'yilgan yoki hali
    bajarilmagan bo'lsa YANGISI QO'SHILMAYDI (takror bosishdan himoya)."""
    if dedupe_minutes:
        # Xato bilan tugagan vazifa QAYTA urinishga to'sqinlik qilmaydi (faqat
        # kutilayotgan/bajarilayotgan yoki yaqinda MUVAFFAQIYATLI bajarilgani to'sadi).
        row = conn.execute(
            "SELECT id, status, created_at FROM nz_jobs WHERE kind=? AND ("
            "  status IN ('pending','running') OR (status='done' AND created_at >= ?)"
            ") ORDER BY id DESC LIMIT 1",
            (kind, (datetime.now(TZ) - timedelta(minutes=dedupe_minutes)).isoformat(timespec="seconds")),
        ).fetchone()
        if row:
            if row["status"] in ("pending", "running"):
                return None, "allaqachon navbatda"
            return None, f"yaqinda bajarildi ({row['created_at'][11:16]})"
    cur = conn.execute(
        "INSERT INTO nz_jobs (kind, payload, status, requested_by, created_at) "
        "VALUES (?, ?, 'pending', ?, ?)",
        (kind, json.dumps(payload or {}, ensure_ascii=False), requested_by, now_str()),
    )
    return cur.lastrowid, "navbatga qo'yildi"


STALE_RUNNING_MIN = 30       # shuncha vaqt 'running' turgan vazifa tashlandiq deb belgilanadi


def reap_stale(conn, minutes: int = STALE_RUNNING_MIN) -> int:
    """Deploy/restart paytida yarim qolgan 'running' vazifalarni yopadi.

    Aks holda dedupe ("allaqachon navbatda") tufayli tugma BUTUNLAY ishlamay qolardi
    (2026-07-30 review topdi)."""
    cutoff = (datetime.now(TZ) - timedelta(minutes=minutes)).isoformat(timespec="seconds")
    cur = conn.execute(
        "UPDATE nz_jobs SET status='error', finished_at=?, "
        "result='to''xtab qoldi (qayta ishga tushish) — qaytadan urinib ko''ring' "
        "WHERE status='running' AND (started_at IS NULL OR started_at < ?)",
        (now_str(), cutoff))
    if cur.rowcount:
        logger.warning("Tashlandiq vazifa yopildi: %d ta", cur.rowcount)
    return cur.rowcount


def next_pending(conn, skip_sync: bool = False):
    """Keyingi bajarilmagan vazifa (eng eskisi). skip_sync=True → blackout paytida
    sync vazifalari o'tkazib yuboriladi (navbatda qoladi)."""
    if skip_sync:
        ph = ",".join("?" * len(SYNC_KINDS))
        return conn.execute(
            f"SELECT * FROM nz_jobs WHERE status='pending' AND kind NOT IN ({ph}) "
            f"ORDER BY id LIMIT 1", SYNC_KINDS).fetchone()
    return conn.execute(
        "SELECT * FROM nz_jobs WHERE status='pending' ORDER BY id LIMIT 1").fetchone()


def mark_running(conn, job_id: int) -> bool:
    """Vazifani 'running' qiladi. False qaytsa — allaqachon olingan (ikki marta bajarilmaydi)."""
    cur = conn.execute(
        "UPDATE nz_jobs SET status='running', started_at=? WHERE id=? AND status='pending'",
        (now_str(), job_id))
    return cur.rowcount > 0


def mark_done(conn, job_id: int, result: str = "ok") -> None:
    conn.execute("UPDATE nz_jobs SET status='done', finished_at=?, result=? WHERE id=?",
                 (now_str(), result[:500], job_id))


def mark_error(conn, job_id: int, error: str) -> None:
    conn.execute("UPDATE nz_jobs SET status='error', finished_at=?, result=? WHERE id=?",
                 (now_str(), error[:500], job_id))


def recent(conn, limit: int = 10) -> list:
    return conn.execute(
        "SELECT id, kind, status, requested_by, created_at, started_at, finished_at, result "
        "FROM nz_jobs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def pending_count(conn, kind: str | None = None) -> int:
    if kind:
        r = conn.execute("SELECT COUNT(*) c FROM nz_jobs WHERE status IN ('pending','running') "
                         "AND kind=?", (kind,)).fetchone()
    else:
        r = conn.execute("SELECT COUNT(*) c FROM nz_jobs "
                         "WHERE status IN ('pending','running')").fetchone()
    return int(r["c"] or 0)


def last_sync(conn) -> dict | None:
    """Oxirgi sync (sync_log'dan) — web'da "yangilangan ..." ko'rsatish uchun."""
    row = conn.execute(
        "SELECT run_at, type, status, note FROM sync_log ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return None
    return {"at": row["run_at"], "type": row["type"], "status": row["status"],
            "note": row["note"]}


# ------------------------------------------------------------------
# Ishchi (worker) — nazorat botida har 15 sekundda ishlaydi
# ------------------------------------------------------------------

async def run_worker(app) -> None:
    """Bitta vazifani oladi va bajaradi (navbat bo'sh bo'lsa darhol qaytadi)."""
    with get_conn() as conn:
        reap_stale(conn)                             # yarim qolganlarni tozalash
        # Tez sync uchun oyna torroq, to'liq sync uchun kengroq — shuning uchun
        # avval sync'siz qaraymiz, keyin turiga qarab tekshiramiz.
        job = next_pending(conn, skip_sync=True)
        if job is None:
            job = next_pending(conn, skip_sync=False)
            if job is not None and job["kind"] in SYNC_KINDS and in_blackout(kind=job["kind"]):
                return                               # hisobot vaqti — navbatda qoladi
        if job is None:
            return
        job = dict(job)
        if not mark_running(conn, job["id"]):
            return                                   # boshqa urinish olib qo'ygan

    kind = job["kind"]
    try:
        payload = json.loads(job["payload"] or "{}")
    except (ValueError, TypeError):
        payload = {}
    logger.info("Vazifa boshlandi: #%s %s %s", job["id"], kind, payload)

    try:
        result = await _dispatch(app, kind, payload)
        with get_conn() as conn:
            mark_done(conn, job["id"], result or "ok")
        logger.info("Vazifa tugadi: #%s %s → %s", job["id"], kind, result)
    except Exception as e:                            # noqa: BLE001
        logger.exception("Vazifa xato: #%s %s", job["id"], kind)
        with get_conn() as conn:
            mark_error(conn, job["id"], f"{type(e).__name__}: {e}")


async def _dispatch(app, kind: str, payload: dict) -> str:
    from . import binding

    if kind == "sync_today":
        from . import quick
        ok, note = await quick.refresh("web", force=payload.get("force", False))
        return note

    if kind in SYNC_KINDS:
        from sync import run_sync
        mode = "full" if kind == "sync_full" else "fast"
        res = await run_sync("web", mode=mode)
        if res != "ok":
            raise RuntimeError(f"sync: {res}")
        return "ok"

    if kind == "bind_approve":
        return await binding.approve(app, payload["code"], int(payload["chat_id"]),
                                     decided_by="web")
    if kind == "bind_reject":
        return await binding.reject(app, payload["code"], int(payload["chat_id"]),
                                    decided_by="web")
    if kind == "unbind":
        return await binding.disconnect(app, payload["code"], decided_by="web")

    if kind in ("period_preview", "period_publish", "period_reopened"):
        from . import period_jobs
        if kind == "period_preview":
            return await period_jobs.preview(app, payload["period_ym"])
        if kind == "period_reopened":
            return await period_jobs.reopened(app, payload["period_ym"],
                                              int(payload.get("version", 2)))
        return await period_jobs.publish(app, payload["period_ym"],
                                         payload.get("by", "web"))

    raise ValueError(f"noma'lum vazifa turi: {kind}")
