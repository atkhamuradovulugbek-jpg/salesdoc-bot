"""
binding.py — ULANISH mantiqining YAGONA joyi (3-bosqich, 2026-07-30).

Avval "tasdiqlash/uzish" faqat Telegram tugmalari ichida yozilgan edi (bot.py), va
kutilayotgan so'rov HECH QAYERDA saqlanmasdi — u faqat Telegram xabarining tugmasida
yashardi. Web ekranida "kutilyapti" ro'yxatini ko'rsatish uchun bazaga yozamiz
(`nz_bind_request`), va tasdiqlash/uzishni SHU MODUL bajaradi. Telegram tugmasi ham,
web ham aynan shu funksiyalarni chaqiradi — ikki xil mantiq bo'lmaydi.

Xavfsizlik: kod O'ZI ulamaydi — admin tasdiqlashi shart (avvalgidek). Qo'shimcha:
so'rov MUDDATLI (24 soat) va tasdiqlangach so'rov yopiladi (bir martalik).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from db import get_conn

from . import storage
from .core.rules import load_agents
from .nz_config import TIMEZONE

logger = logging.getLogger("nazorat.binding")
TZ = ZoneInfo(TIMEZONE)

REQUEST_TTL_HOURS = 24          # so'rov shundan keyin eskiradi


def _now() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def resolve_code(code: str) -> tuple[str, str | None, str] | None:
    """Kod kimga tegishli: ('agent'|'supervisor'|'debt', sd_id|None, ism).
    Topilmasa None. YAML har chaqiruvda o'qiladi — yangi kod qo'shilsa qayta
    ishga tushirish shart emas."""
    code = (code or "").strip().upper()
    if not code:
        return None
    cfg = load_agents()
    for a in cfg.agents:
        if a.code.upper() == code:
            return "agent", a.sd_id, a.name
    for s in cfg.supervisors:
        if s.code.upper() == code:
            return "supervisor", None, s.name
    for d in cfg.debt_controllers:                      # qarz nazoratchisi (2026-08-13)
        if d.code.upper() == code:
            return "debt", None, d.name
    return None


def display_name(code: str) -> str:
    """Qisqa ism (xabarlar uchun)."""
    code = (code or "").strip().upper()
    cfg = load_agents()
    for a in cfg.agents:
        if a.code.upper() == code:
            return a.short
    for s in cfg.supervisors:
        if s.code.upper() == code:
            return s.name
    for d in cfg.debt_controllers:
        if d.code.upper() == code:
            return d.name
    return code


# ------------------------------------------------------------------
# Kutilayotgan so'rovlar
# ------------------------------------------------------------------

def create_request(conn, code: str, chat_id: int, who: str) -> int:
    """Agent kod yozdi — so'rovni bazaga yozadi (web ekranida ko'rinadi).
    Shu chat/kod uchun ochiq so'rov bo'lsa — yangilaydi (dublikat yaratmaydi)."""
    code = code.strip().upper()
    r = resolve_code(code)
    role, sd_id = (r[0], r[1]) if r else (None, None)
    now = datetime.now(TZ)
    exp = (now + timedelta(hours=REQUEST_TTL_HOURS)).isoformat(timespec="seconds")
    row = conn.execute(
        "SELECT id FROM nz_bind_request WHERE code=? AND chat_id=? AND status='pending'",
        (code, chat_id)).fetchone()
    if row:
        conn.execute("UPDATE nz_bind_request SET who=?, requested_at=?, expires_at=? WHERE id=?",
                     (who, now.isoformat(timespec="seconds"), exp, row["id"]))
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO nz_bind_request (code, chat_id, who, role, sd_id, requested_at, "
        "expires_at, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')",
        (code, chat_id, who, role, sd_id, now.isoformat(timespec="seconds"), exp))
    return int(cur.lastrowid)


def expire_old(conn) -> int:
    """Muddati o'tgan so'rovlarni yopadi. Qaytadi: nechtasi."""
    cur = conn.execute(
        "UPDATE nz_bind_request SET status='expired' WHERE status='pending' AND expires_at < ?",
        (_now(),))
    return cur.rowcount


def pending_requests(conn) -> list[dict]:
    """Web ekrani uchun kutilayotgan so'rovlar (eskilari avtomatik yopiladi)."""
    expire_old(conn)
    rows = conn.execute(
        "SELECT id, code, chat_id, who, role, sd_id, requested_at FROM nz_bind_request "
        "WHERE status='pending' ORDER BY id DESC").fetchall()
    out = []
    for r in rows:
        out.append({"id": r["id"], "code": r["code"], "chat_id": r["chat_id"],
                    "who": r["who"] or str(r["chat_id"]), "role": r["role"],
                    "sd_id": r["sd_id"], "name": display_name(r["code"]),
                    "requested_at": r["requested_at"]})
    return out


def _close_request(conn, code: str, chat_id: int, status: str, decided_by: str,
                   close_siblings: bool = False) -> None:
    """So'rovni yopadi. close_siblings=True bo'lsa — SHU KODNING boshqa chatlardan
    kelgan so'rovlari ham yopiladi (kod ulangach eskisi tasdiqlanmasin;
    2026-07-30 review topdi)."""
    code = code.strip().upper()
    conn.execute(
        "UPDATE nz_bind_request SET status=?, decided_at=?, decided_by=? "
        "WHERE code=? AND chat_id=? AND status='pending'",
        (status, _now(), decided_by, code, chat_id))
    if close_siblings:
        conn.execute(
            "UPDATE nz_bind_request SET status='expired', decided_at=?, decided_by=? "
            "WHERE code=? AND chat_id<>? AND status='pending'",
            (_now(), decided_by, code, chat_id))


# ------------------------------------------------------------------
# Tasdiqlash / rad etish / uzish — YAGONA amalga oshirish
# ------------------------------------------------------------------

async def approve(app, code: str, chat_id: int, decided_by: str = "telegram") -> str:
    """Ulanishni tasdiqlaydi: bazaga yozadi + agentga xabar beradi.
    Qaytadi: qisqa natija matni. Kod topilmasa ValueError."""
    from .bot import DEBT_KB, REVEAL_STR, SUPERVISOR_KB, agent_kb

    code = code.strip().upper()
    r = resolve_code(code)
    if not r:
        raise ValueError(f"kod topilmadi: {code}")
    role, sd_id, name = r

    with get_conn() as conn:
        old_chat = storage.bind_code(conn, code, chat_id, role, sd_id, _now())
        _close_request(conn, code, chat_id, "approved", decided_by, close_siblings=True)

    try:
        if role == "agent":
            await app.bot.send_message(
                chat_id, f"✅ Ulandingiz!\n👤 {name}\n"
                         f"Har kuni 10:00 (qarz/vazvrat) va {REVEAL_STR} (natija) da hisobot keladi.\n"
                         f"Quyidagi tugmalardan foydalaning 👇", reply_markup=agent_kb())
        elif role == "supervisor":
            await app.bot.send_message(
                chat_id, f"✅ Ulandingiz!\n👤 {name} (supervayzer)\n"
                         f"Ligangiz jadvallari har kuni keladi. Tugmalardan foydalaning 👇",
                reply_markup=SUPERVISOR_KB)
        elif role == "debt":
            await app.bot.send_message(
                chat_id, f"✅ Ulandingiz!\n👤 {name}\n\n"
                         f"Har kuni <b>22:00</b> da ertangi kunga qaror rasmi keladi "
                         f"(shahar va viloyat alohida).\n"
                         f"Agent limitdan oshsa — darhol xabar beraman.\n\n"
                         f"Tugmalardan foydalaning 👇",
                parse_mode="HTML", reply_markup=DEBT_KB)
        else:
            await app.bot.send_message(chat_id, f"✅ Ulandingiz!\n👤 {name}")
    except Exception as e:  # noqa: BLE001 — xabar yuborish ixtiyoriy
        logger.warning("ulanish xabari yuborilmadi (%s): %s", chat_id, e)

    if old_chat and old_chat != chat_id:
        try:
            await app.bot.send_message(
                old_chat, "⚠️ Kodingiz boshqa qurilmaga ulandi (admin tasdig'i bilan).")
        except Exception:  # noqa: BLE001
            pass
    logger.info("Ulandi: %s (%s) → chat %s [%s]", name, code, chat_id, decided_by)
    return f"{name} ({code}) ulandi"


async def reject(app, code: str, chat_id: int, decided_by: str = "telegram") -> str:
    code = code.strip().upper()
    with get_conn() as conn:
        _close_request(conn, code, chat_id, "rejected", decided_by)
    try:
        await app.bot.send_message(
            chat_id, "❌ Ulanish so'rovingiz rad etildi. Administrator bilan bog'laning.")
    except Exception:  # noqa: BLE001
        pass
    return f"{display_name(code)} ({code}) rad etildi"


async def disconnect(app, code: str, decided_by: str = "telegram") -> str:
    """Ulanishni uzadi + o'sha chatga xabar beradi."""
    code = code.strip()
    with get_conn() as conn:
        old_chat = storage.unbind(conn, code)
    name = display_name(code)
    if old_chat:
        try:
            await app.bot.send_message(
                old_chat, "🔌 Siz botdan uzildingiz. Qayta ulanish uchun kodingizni yuboring.")
        except Exception:  # noqa: BLE001
            pass
    logger.info("Uzildi: %s (%s) [%s]", name, code, decided_by)
    return f"{name} ({code}) uzildi"


# ------------------------------------------------------------------
# Web ekrani uchun: hamma agent+supervayzer, ulangan/ulanmagan holati
# ------------------------------------------------------------------

def connection_list(conn) -> list[dict]:
    """🟢 ulangan / 🔴 ulanmagan ro'yxati. Ro'yxat manbasi — roster (faol agentlar)."""
    from . import roster

    cfg = load_agents()
    bound = {r["code"].upper(): r for r in storage.list_bindings(conn)}
    active_ids = {a.sd_id for a in roster.active_agents(conn, cfg)}

    out: list[dict] = []
    for a in cfg.agents:
        if a.sd_id not in active_ids:
            continue                      # ishdan ketgan — ro'yxatda ko'rsatilmaydi
        b = bound.get(a.code.upper())
        out.append({
            "code": a.code, "name": a.short, "full_name": a.name, "sd_id": a.sd_id,
            "role": "agent", "league": a.league,
            "league_label": "Shahar" if a.league == "city" else "Viloyat",
            "area": a.area, "observe": bool(a.observe_only),
            "seat_changed": bool(a.seat_changed), "seat_prev": a.seat_prev_name,
            "seat_since": a.start_date,
            "connected": b is not None,
            "chat_id": b["chat_id"] if b else None,
            "bound_at": b["bound_at"] if b else None,
        })
    for s in cfg.supervisors:
        b = bound.get(s.code.upper())
        out.append({
            "code": s.code, "name": s.name, "full_name": s.name, "sd_id": None,
            "role": "supervisor", "league": s.league,
            "league_label": "Shahar" if s.league == "city" else "Viloyat",
            "area": "", "observe": False,
            "seat_changed": False, "seat_prev": "", "seat_since": None,
            "connected": b is not None,
            "chat_id": b["chat_id"] if b else None,
            "bound_at": b["bound_at"] if b else None,
        })
    # Ulanmaganlar tepada (e'tibor kerak), keyin rol/liga bo'yicha
    out.sort(key=lambda x: (x["connected"], x["role"] != "supervisor", x["league"], x["name"]))
    return out
