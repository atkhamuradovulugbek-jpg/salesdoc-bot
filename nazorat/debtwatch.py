"""
debtwatch.py — QARZ NAZORATI (2026-08-13, egasi so'rovi).

MUAMMO: dastafshiklar agentlarning qarzi va limitini bilmaydi — bilmasdan
mahsulotni qarzga berib yuborishyapti. 2026-08-13 holati: 19 agentdan 9 tasi
limitdan oshgan, biri 448% (13.4 mln / 3 mln).

YECHIM: alohida «qarz nazoratchisi» roli (kod QRZ-01). U:
  1. «💳 Hozirgi qarzlar» tugmasi — ~12 soniyada AYNI PAYTDAGI qarzlar
     (shahar/viloyat alohida rasm), agentga bosib do'kon bo'yicha ko'radi;
  2. agent limitdan oshsa — DARHOL xabar oladi (egasi qarori: faqat
     nazoratchiga, faqat 100% dan oshganda);
  3. har kuni 22:00 da ikkita rasm — ertangi kunga "kimga mumkin / kimga yo'q".

QARZ QAYERDAN: `balances` jadvali (Sales Doctor mijoz qoldiqlari) → agentga
biriktirilgan do'konlarning manfiy qoldiqlari yig'indisi. Ya'ni HISOBOTLARDAGI
bilan bir xil raqam — yangi hisob-kitob o'ylab topilmagan.

LIMIT: `rules.yaml` dagi `debt_limit` (shahar 3 mln, viloyat 4 mln) yoki agentga
alohida berilgan qiymat. Egasi 2026-08-13 da "hozirgi limit qolsin" dedi.

MUHIM: yengil «today» sync BALANSLARNI TORTMAYDI (u eng sekin so'rov, 11s).
Shuning uchun qarz uchun alohida `mode="debt"` bor.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from db import get_conn

from . import roster, storage
from .core.rules import load_rules
from .nz_config import ADMIN_IDS, TIMEZONE

logger = logging.getLogger("nazorat.debtwatch")
TZ = ZoneInfo(TIMEZONE)

NEAR_FRAC = 0.9          # 90% — "ehtiyot bo'ling" chegarasi (faqat ko'rsatish uchun)
LEAGUES = (("city", "SHAHAR"), ("region", "VILOYAT"))


def _now() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def _today() -> date:
    return datetime.now(TZ).date()


# ------------------------------------------------------------------
# Ma'lumot
# ------------------------------------------------------------------

def rows_for(conn, league: str | None = None, today: date | None = None) -> list[dict]:
    """Agentlar qarzi + limiti. Limitdan oshgani YUQORIDA.

    DayContext ISHLATILMAYDI — u butun oy savdosini ham yig'adi. Bu yerda faqat
    qarz kerak, shuning uchun yengil yo'l (tugma tez-tez bosiladi)."""
    today = today or _today()
    rules = load_rules()
    agents = roster.active_agents(conn, league=league, day=today)
    out = []
    for a in agents:
        from .data import agent_debt_total
        debt = agent_debt_total(conn, a.sd_id)
        limit = a.debt_limit or rules.debt_limit[a.league]
        out.append({
            "sd_id": a.sd_id, "name": a.short, "area": a.area, "league": a.league,
            "debt": debt, "limit": limit,
            "pct": (debt / limit * 100) if limit else 0.0,
            "over": debt > limit,
            "near": (not debt > limit) and bool(limit) and debt >= limit * NEAR_FRAC,
        })
    out.sort(key=lambda r: -r["pct"])
    return out


def card_dict(rows: list[dict], league_label: str, mode: str,
              today: date | None = None) -> dict:
    from .data import MONTHS_UZ
    t = today or _today()
    return {"title": league_label, "mode": mode,
            "date_label": f"{t.day}-{MONTHS_UZ[t.month]} {t.year}",
            "rows": rows}


def shops_text(conn, sd_id: str, name: str, today: date | None = None) -> str:
    """Bitta agentning qarzli do'konlari (nazoratchi dastafshikka aytishi uchun)."""
    from .data import agent_debt
    t = (today or _today()).isoformat()
    total, shops = agent_debt(conn, sd_id, t)
    if not shops:
        return f"<b>{name}</b> — qarzli do'kon yo'q ✅"
    lines = [f"🏪 <b>{name}</b> — qarzli do'konlar ({len(shops)})", ""]
    for shop, debt, age in shops:
        age_txt = f" · {age} kun" if age is not None else ""
        lines.append(f"• {shop[:34]} — <b>{int(debt):,}</b>{age_txt}".replace(",", " "))
    lines += ["", f"Jami: <b>{int(total):,}</b> so'm".replace(",", " ")]
    return "\n".join(lines)


# ------------------------------------------------------------------
# Ogohlantirish holati — HAR AGENT UCHUN BIR MARTA
# ------------------------------------------------------------------
# Nega kerak: har soatda tekshirilganda bir xil agent uchun kun bo'yi bir xil
# xabar yog'ilib ketardi. Shuning uchun "oshgan" holati bazada eslab qolinadi:
# xabar faqat NORMAL → OSHGAN o'tishida yuboriladi. Qarz tushib yana oshsa —
# yana bir marta yuboriladi.

def newly_over(conn, rows: list[dict], now: str) -> list[dict]:
    """Yangi oshganlar (xabar yuborilishi kerak bo'lganlar). Holatni YANGILAYDI."""
    fresh = []
    for r in rows:
        prev = conn.execute(
            "SELECT over FROM nz_debt_state WHERE sd_id=?", (r["sd_id"],)).fetchone()
        was_over = bool(prev["over"]) if prev else False
        if r["over"] and not was_over:
            fresh.append(r)
        if (prev is None) or (was_over != r["over"]):
            conn.execute(
                "INSERT INTO nz_debt_state (sd_id, over, debt, changed_at) "
                "VALUES (?, ?, ?, ?) ON CONFLICT(sd_id) DO UPDATE SET "
                "over=excluded.over, debt=excluded.debt, changed_at=excluded.changed_at",
                (r["sd_id"], int(r["over"]), r["debt"], now))
    return fresh


def alert_text(r: dict) -> str:
    return (f"⛔ <b>{r['name']} limitdan oshdi</b>\n"
            f"{r['area']}\n\n"
            f"Qarzi: <b>{int(r['debt']):,}</b> so'm\n".replace(",", " ") +
            f"Limiti: {int(r['limit']):,} so'm  ({r['pct']:.0f}%)\n\n".replace(",", " ") +
            f"Dastafshikni ogohlantiring — mahsulot berilmasin.")


# ------------------------------------------------------------------
# Qarzni yangilash (balanslar) — ~12 soniya
# ------------------------------------------------------------------

async def refresh_debt() -> tuple[bool, str]:
    """Sales Doctor'dan BALANSLARNI tortadi. Xato bo'lsa ko'tarmaydi."""
    from . import quick
    with get_conn() as conn:
        left = quick.cooldown_left(conn, kind="debt")
        if left:
            age = quick.seconds_since(quick.last_refresh(conn, kind="debt"))
            return False, quick.age_text(age)
    try:
        from sync import run_sync
        res = await run_sync("qarz", mode="debt")
    except Exception as e:                                # noqa: BLE001
        logger.exception("Qarz yangilash xatosi")
        return False, f"xato: {type(e).__name__}"
    if res == "busy":
        return False, "boshqa yangilash ketyapti"
    if res != "ok":
        return False, "xato"
    return True, "yangilandi"


# ------------------------------------------------------------------
# AVTOMATIK ISHLAR
# ------------------------------------------------------------------

def _controller_chats(conn) -> list[int]:
    """Ulangan qarz nazoratchilari (kod QRZ-*). Ulanmagan bo'lsa bo'sh ro'yxat."""
    from .core.rules import load_agents
    codes = [d.code.upper() for d in load_agents().debt_controllers]
    if not codes:
        return []
    ph = ",".join("?" * len(codes))
    rows = conn.execute(
        f"SELECT chat_id FROM nz_bindings WHERE role='debt' AND UPPER(code) IN ({ph})",
        codes).fetchall()
    return [int(r["chat_id"]) for r in rows]


def _evening_chats(conn) -> list[int]:
    """22:00 umumiy qarz hisoboti: ulangan qarz nazoratchilari + egasi (admin) chati
    (egasi qarori 2026-10-07). Soatlik ogohlantirish — faqat nazoratchilarga."""
    out: list[int] = []
    for cid in _controller_chats(conn) + sorted(ADMIN_IDS):
        if cid not in out:
            out.append(cid)
    return out


async def _send(app, chats, text=None, photo=None, caption=None):
    from telegram.error import TelegramError
    sent = 0
    for cid in chats:
        try:
            if photo is not None:
                await app.bot.send_photo(cid, photo, caption=caption, parse_mode="HTML")
            else:
                await app.bot.send_message(cid, text, parse_mode="HTML")
            sent += 1
        except TelegramError as e:
            logger.warning("qarz nazoratchisi %s: %s", cid, e)
    return sent


async def hourly_check(app) -> str:
    """Har soat: qarzni yangilab, YANGI oshganlarni nazoratchiga xabar qiladi.

    Nazoratchi ulanmagan bo'lsa — API'ga ham borilmaydi (bekorga yuk bo'lmasin)."""
    with get_conn() as conn:
        chats = _controller_chats(conn)
    if not chats:
        return "nazoratchi ulanmagan"

    await refresh_debt()                       # kutish ichida bo'lsa jimgina o'tadi
    now = _now()
    with get_conn() as conn:
        rows = rows_for(conn)
        fresh = newly_over(conn, rows, now)
    for r in fresh:
        await _send(app, chats, text=alert_text(r))
    logger.info("Qarz tekshiruvi: %d yangi oshgan", len(fresh))
    return f"{len(fresh)} yangi oshgan"


async def evening_report(app) -> str:
    """22:00 — ertangi kunga qaror: shahar va viloyat ALOHIDA rasm."""
    from .cards import render_debt_control

    with get_conn() as conn:
        chats = _evening_chats(conn)
    if not chats:
        logger.info("22:00 qarz hisoboti: qabul qiluvchi yo'q")
        return "qabul qiluvchi yo'q"

    await refresh_debt()
    day = _today().isoformat()
    sent = 0
    with get_conn() as conn:
        data = {lg: rows_for(conn, lg) for lg, _ in LEAGUES}
    for lg, label in LEAGUES:
        rows = data[lg]
        if not rows:
            continue
        # IDEMPOTENT: qayta ishga tushsa dublikat rasm ketmasin
        key = f"debt_evening_{lg}"
        with get_conn() as conn:
            if all(storage.already_sent(conn, day, key, str(c)) for c in chats):
                continue
        png = render_debt_control(card_dict(rows, label, "kechki"))
        blocked = sum(1 for r in rows if r["over"])
        n = await _send(app, chats, photo=png,
                        caption=f"📋 <b>{label}</b> · ertangi kunga\\n"
                                f"⛔ berilmasin: <b>{blocked}</b> ta · "
                                f"✅ mumkin: <b>{len(rows) - blocked}</b> ta")
        sent += n
        with get_conn() as conn:
            for c in chats:
                storage.mark_sent(conn, day, key, str(c), _now())
    logger.info("22:00 qarz hisoboti: %d rasm yuborildi", sent)
    return f"{sent} rasm"
