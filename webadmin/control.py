"""
control.py — web dasturning BOSHQARUV qatlami (2-4 bosqich).

MUHIM QOIDA (llm-council): web dastur og'ir ishni O'ZI BAJARMAYDI. U faqat:
  • o'qiydi (ulanish ro'yxati, sync holati);
  • `nz_jobs` ga kichik "vazifa" qatorini yozadi — uni nazorat boti bajaradi.
Shu bilan web jarayoni muzlamaydi va ikki jarayon bir vaqtda sync qilmaydi.

`reportdata.py` faqat-o'qish qatlami bo'lib qoladi; yozish SHU faylda.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from db import get_conn
from nazorat import binding, period, roster, taskq
from nazorat.nz_config import TIMEZONE


def _today():
    return datetime.now(ZoneInfo(TIMEZONE)).date()


def _now() -> str:
    return datetime.now(ZoneInfo(TIMEZONE)).isoformat(timespec="seconds")


# ------------------------------------------------------------------
# O'QISH
# ------------------------------------------------------------------

def connections() -> dict:
    """Ulanish ekrani: hamma agent/supervayzer + kutilayotgan so'rovlar + sync holati."""
    with get_conn() as conn:
        rows = binding.connection_list(conn)
        pending = binding.pending_requests(conn)
        sync = taskq.last_sync(conn)
        jobs = [dict(r) for r in taskq.recent(conn, limit=8)]
        queued = taskq.pending_count(conn)
    connected = sum(1 for r in rows if r["connected"])
    return {
        "rows": rows,
        "pending": pending,
        "total": len(rows),
        "connected": connected,
        "not_connected": len(rows) - connected,
        "sync": sync,
        "jobs": [{"kind": j["kind"], "label": taskq.KIND_LABELS.get(j["kind"], j["kind"]),
                  "status": j["status"], "created_at": j["created_at"],
                  "finished_at": j["finished_at"], "result": j["result"]} for j in jobs],
        "queued": queued,
        "blackout": taskq.blackout_note(),
        "blackout_window": list(taskq.blackout_window()),
    }


# ------------------------------------------------------------------
# YOZISH — faqat navbatga qo'yish
# ------------------------------------------------------------------

def request_quick() -> dict:
    """⟳ tugmasi: BUGUNGI ma'lumotni Sales Doctor'dan tortishni so'raydi (~5 soniya).

    Web O'ZI tortmaydi — botga vazifa beradi (yagona yozuvchi qoidasi). Bot uni
    ~15 soniya ichida oladi. Kutish (90s) ichida bo'lsa bot qayta tortmaydi."""
    from nazorat import quick
    with get_conn() as conn:
        left = quick.cooldown_left(conn)
        age = quick.seconds_since(quick.last_any_sync(conn))
        if left:
            return {"ok": False, "queued": False,
                    "note": f"{quick.age_text(age)} yangilangan"}
        job_id, note = taskq.enqueue(conn, "sync_today", {}, "web", dedupe_minutes=1)
    return {"ok": job_id is not None, "queued": job_id is not None, "note": note}


def data_age() -> dict:
    """Ma'lumot qanchalik eski (ekranda ko'rsatish uchun)."""
    from nazorat import quick
    with get_conn() as conn:
        at = quick.last_any_sync(conn)
        return {"age_sec": quick.seconds_since(at),
                "age_text": quick.age_text(quick.seconds_since(at)),
                "at": at.isoformat(timespec="seconds") if at else None}


def request_sync(mode: str = "fast") -> dict:
    """Yangilash vazifasini navbatga qo'yadi (bot bajaradi)."""
    kind = "sync_full" if mode == "full" else "sync_fast"
    with get_conn() as conn:
        job_id, note = taskq.enqueue(conn, kind, requested_by="web", dedupe_minutes=5)
    return {"ok": job_id is not None, "note": note, "job_id": job_id,
            "blackout": taskq.blackout_note()}


def _enqueue_once(kind: str, payload: dict) -> dict:
    """Ulanish amallari: ikki marta bosilsa ikkinchisi qo'shilmaydi (agentga ikkita
    bir xil xabar ketmasin — 2026-07-30 review topdi). Kalit payload'ni ham hisobga oladi."""
    with get_conn() as conn:
        # Shu kod uchun ayni turdagi bajarilmagan vazifa bormi?
        row = conn.execute(
            "SELECT id FROM nz_jobs WHERE kind=? AND status IN ('pending','running') "
            "AND payload LIKE ? ORDER BY id DESC LIMIT 1",
            (kind, f'%"{payload.get("code", "")}"%')).fetchone()
        if row:
            return {"ok": False, "note": "allaqachon navbatda"}
        job_id, note = taskq.enqueue(conn, kind, payload, "web")
    return {"ok": job_id is not None, "note": note}


def approve_binding(code: str, chat_id: int) -> dict:
    return _enqueue_once("bind_approve", {"code": code, "chat_id": chat_id})


def reject_binding(code: str, chat_id: int) -> dict:
    return _enqueue_once("bind_reject", {"code": code, "chat_id": chat_id})


def disconnect_binding(code: str) -> dict:
    return _enqueue_once("unbind", {"code": code})


# ------------------------------------------------------------------
# «OY VARAQASI» — ball plan (5-bosqich)
# ------------------------------------------------------------------
# Qoralama saqlash — kichik yozuv, WEB O'ZI qiladi (nz_period/nz_agent_plan
# faqat web'niki, sync ularga TEGMAYDI). Namuna va e'lon esa botga beriladi:
# ular Telegram va rasm chizishni talab qiladi.

def period_overview() -> dict:
    """Ball plan ekranining boshlang'ich holati: varaqalar + ochiladigan oy."""
    today = _today()
    cur = period.period_of(today)
    nxt = period.next_period(cur)
    with get_conn() as conn:
        sheets = period.list_sheets(conn)
        active = period.resolve(conn, today)
        # Ochiladigan oy: tahrirlanadigan eng yangisi, bo'lmasa KEYINGI oy
        editable = [s for s in sheets if s["status"] != period.PUBLISHED]
        default_ym = editable[0]["period_ym"] if editable else nxt
    return {
        "today_period": cur, "today_label": period.month_label(cur),
        "next_period": nxt, "next_label": period.month_label(nxt),
        "default_ym": default_ym,
        "active": ({"period_ym": active.period_ym, "label": period.month_label(active.period_ym),
                    "checksum": active.checksum, "prizes_enabled": active.prizes_enabled,
                    "growth_enabled": active.growth_enabled}
                   if active else None),
        "sheets": sheets,
    }


def period_sheet(ym: str) -> dict:
    """Bitta oy varaqasi (agentlar + ball planlar + farqlar)."""
    today = _today()
    with get_conn() as conn:
        agents = roster.active_agents(conn, day=today)
        view = period.sheet_view(conn, ym, agents, today)
        view["pending"] = _pending_period_job(conn, ym)
        return view


def _pending_period_job(conn, ym: str) -> str | None:
    """Shu oy uchun bot hali bajarmagan vazifa (namuna/e'lon) — ekranda kutish
    holati ko'rsatiladi. Aks holda tugma bosilgach hech narsa o'zgarmagandek
    tuyulib, egasi ikkinchi marta bosardi."""
    row = conn.execute(
        "SELECT kind FROM nz_jobs WHERE status IN ('pending','running') "
        "AND kind IN ('period_preview','period_publish') AND payload LIKE ? "
        "ORDER BY id DESC LIMIT 1", (f'%"{ym}"%',)).fetchone()
    return row["kind"] if row else None


def period_save(ym: str, plans: dict[str, int], prizes: bool,
                growth: bool = True) -> dict:
    """Qoralamani saqlaydi (agentlar HALI ko'rmaydi)."""
    with get_conn() as conn:
        period.save_draft(conn, ym, plans, prizes, "web", _now(), growth=growth)
    return {"ok": True, "note": "Qoralama saqlandi — agentlar hali ko'rmaydi."}


def period_preview(ym: str) -> dict:
    """Haqiqiy kartani Telegramga yuborishni so'raydi (bot chizadi)."""
    return _enqueue_period("period_preview", ym)


def period_publish(ym: str) -> dict:
    """Varaqani muzlatishni so'raydi (bot bajaradi + tasdiq yuboradi)."""
    return _enqueue_period("period_publish", ym)


def period_reopen(ym: str) -> dict:
    """TUZATISH — e'lon qilingan varaqani qoralamaga qaytaradi (oy tugamagan bo'lsa).
    Avvalgi nusxa tarixga yoziladi."""
    with get_conn() as conn:
        ver = period.reopen(conn, ym, _today(), _now())
        # Tuzatish boshlanganini ADMINGA bildiramiz — e'lon qilingan raqam
        # o'zgarayotgani jimgina o'tmasin.
        taskq.enqueue(conn, "period_reopened", {"period_ym": ym, "version": ver}, "web")
    return {"ok": True, "version": ver,
            "note": f"{period.month_label(ym)} tuzatishga ochildi. "
                    f"O'zgartirib, qayta E'LON QILING."}


def _enqueue_period(kind: str, ym: str) -> dict:
    period.parse_period(ym)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM nz_jobs WHERE kind=? AND status IN ('pending','running') "
            "AND payload LIKE ? ORDER BY id DESC LIMIT 1",
            (kind, f'%"{ym}"%')).fetchone()
        if row:
            return {"ok": False, "note": "allaqachon navbatda"}
        job_id, note = taskq.enqueue(conn, kind, {"period_ym": ym, "by": "web"}, "web")
    return {"ok": job_id is not None, "note": note}
