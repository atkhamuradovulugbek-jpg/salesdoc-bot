"""
monitor.py — kunduzgi GPS trevoga (2-bosqich): agent ish vaqtida yo'qolsa
supervayzerga (sinovda — adminga) darhol MATN xabar + tugmalar.

Qoidalar (foydalanuvchi bilan kelishilgan, 2026-07-17):
- Ikkala liga ham 45 daqiqa (sariq), 90 daqiqa = qizil (adminga ham nusxa).
- Ish vaqti 09:00-17:00, yakshanba dam. Tushlik ham tutiladi.
- Bir tekshiruvda bir nechta yo'qolgan bo'lsa — BITTA jamlangan xabar.
- Agent qaytsa — "qaytdi" xabari. "Bu hafta X-marta" hisobchisi.
- Har epizod uchun bir marta ogohlantiriladi (spam yo'q); sariq→qizil o'tishda yana bir marta.
- Supervayzer qizilga 30 daq javob bermasa — adminga signal (faqat jonli rejimda).
- Xabar matnlari foydalanuvchi tasdiqlagan to'liq-gap formatida (2026-07-17).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

from db import get_conn

from . import gps, storage
from .nz_config import (ADMIN_IDS, ALERTS_TO_SUPERVISORS, GPS_ESCALATE_MIN,
                        GPS_MISSING_MIN, GPS_MISSING_RED_MIN, TIMEZONE)

logger = logging.getLogger("nazorat.monitor")
TZ = ZoneInfo(TIMEZONE)

WORK_START, WORK_END = 9, 17
SUPERVISOR_CODES = {"city": "SPV-TSH-01", "region": "SPV-TVL-01"}


def _now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def build_last_map(visits: list[dict], agents) -> dict[str, dict]:
    """Har agent: oxirgi faollik vaqti + oxirgi do'kon + bugungi vizit soni.
    Sof funksiya (testlanadi)."""
    out = {a.sd_id: {"last": None, "shop": "", "total": 0, "first_after": {}} for a in agents}
    for v in visits:
        if str(v.get("visited")) not in ("1", "True", "true"):
            continue
        aid = str(v.get("agent_id") or "")
        if aid not in out:
            continue
        st = gps._parse(v.get("start_date"))
        en = gps._parse(v.get("end_date"))
        t = en or st
        s = out[aid]
        s["total"] += 1
        if t and (s["last"] is None or t > s["last"]):
            s["last"] = t
            s["shop"] = str(v.get("client_name") or "")[:40]
    return out


def find_missing(last_map: dict, now: datetime,
                 yellow_min: int = GPS_MISSING_MIN,
                 red_min: int = GPS_MISSING_RED_MIN) -> list[dict]:
    """Yo'qolganlar ro'yxati (sof funksiya). now — naive Toshkent vaqti."""
    res = []
    for sd_id, s in last_map.items():
        if s["last"] is None:
            continue
        mins = int((now - s["last"]).total_seconds() // 60)
        if mins < yellow_min:
            continue
        res.append({"sd_id": sd_id, "mins": mins,
                    "level": "red" if mins >= red_min else "yellow",
                    "last": s["last"], "shop": s["shop"], "total": s["total"]})
    res.sort(key=lambda r: -r["mins"])
    return res


def _fmt_dur(mins: int) -> str:
    if mins < 60:
        return f"{mins} daqiqa"
    return f"{mins // 60} soat {mins % 60} daqiqa"


def _fmt_sum(v: float) -> str:
    return f"{int(round(v)):,}".replace(",", " ")


def _today_sales(conn, sd_id: str, day: str) -> float:
    row = conn.execute(
        "SELECT COALESCE(SUM(total_after_discount),0) s FROM orders WHERE agent_sd_id=? AND date=?",
        (sd_id, day)).fetchone()
    return float(row["s"] or 0)


def _last_line(f: dict, prefix: str = "") -> str:
    """'Oxirgi marta "X"da bo'lgan, HH:MM da chiqib ketgan.' (do'kon nomi bo'lmasa soddaroq)."""
    hhmm = f["last"].strftime("%H:%M")
    if f["shop"]:
        return f"{prefix}Oxirgi marta \"{f['shop']}\"da bo'lgan, {hhmm} da chiqib ketgan."
    return f"{prefix}Oxirgi vizitini {hhmm} da tugatgan."


async def _send(app, chat_ids, text, kb=None):
    for cid in chat_ids:
        try:
            await app.bot.send_message(cid, text, reply_markup=kb)
        except TelegramError as e:
            logger.warning("GPS trevoga yuborilmadi (%s): %s", cid, e)


def _targets(league: str, red: bool = False) -> list[int]:
    """Kimga boradi: sinovda — faqat admin; jonlida — supervayzer + admin nusxa.
    Foydalanuvchi 'mengaham kelaversin' dedi (2026-07-17) — parallel sinov davrida
    admin HAR trevoga nusxasini oladi (faqat qizil emas)."""
    if not ALERTS_TO_SUPERVISORS:
        return list(ADMIN_IDS)
    with get_conn() as conn:
        chat = storage.chat_for_supervisor(conn, SUPERVISOR_CODES.get(league, ""))
    out = [chat] if chat else []
    out += [a for a in ADMIN_IDS if a not in out]  # admin doim nusxa oladi
    return out


_SEP = "➖➖➖➖➖➖➖➖➖➖➖➖"


def _mark(level: str) -> str:
    """Rangli signal: 🔴 = jiddiy (90+ daq), 🟡 = ogohlantirish (45-90 daq)."""
    return "🔴" if level == "red" else "🟡"


def _single_message(f: dict) -> str:
    """Bitta agent uchun xabar (foydalanuvchi tasdiqlagan matn + belgilar, 2026-07-17)."""
    a = f["agent"]
    lines = []
    if f["level"] == "red":
        lines.append(f"🔴 JIDDIY! {a.short} {_fmt_dur(f['mins'])}dan beri "
                     f"birorta do'konga kirmadi.")
        lines.append("")
        lines.append(f"🔴 {a.short} ({a.area})")
        tail = _last_line(f, prefix="⏰ ")
        if f["upgrade"]:
            tail += f" Bu haqda sizga {GPS_MISSING_MIN} daqiqa oldin xabar berilgan edi."
        lines.append(tail)
        if ALERTS_TO_SUPERVISORS:
            lines.append("")
            lines.append("Bu xabar rahbarga ham yuborildi.")
    else:
        lines.append(f"🚨 DIQQAT! {a.short} do'konlarga kirmay qo'ydi.")
        lines.append("")
        lines.append(f"🟡 {a.short} ({a.area})")
        hhmm = f["last"].strftime("%H:%M")
        if f["shop"]:
            lines.append(f"⏰ Oxirgi marta \"{f['shop']}\" do'konida bo'lgan — "
                         f"u yerdan {hhmm} da chiqib ketgan.")
        else:
            lines.append(f"⏰ Oxirgi vizitini {hhmm} da tugatgan.")
        lines.append(f"🚫 O'shandan beri {_fmt_dur(f['mins'])} o'tdi. "
                     f"Shu vaqt ichida birorta ham do'konga kirmadi.")
        lines.append(f"🏪 Bugun jami: {f['total']} ta do'konga kirgan, "
                     f"{_fmt_sum(f['sales'])} so'm savdo qilgan.")
        if f["week"] >= 2:
            lines.append(f"⚠️ Bunday yo'qolish shu hafta {f['week']}-marta bo'ldi.")
        lines.append("")
        lines.append("📞 Hozir unga qo'ng'iroq qilib, qayerdaligini so'rang.")
    return "\n".join(lines)


def _batch_message(fresh: list[dict], now_tz: datetime) -> str:
    """Jamlangan xabar: rangli signal + ajratgich chiziqlar (tasdiqlangan, 2026-07-17)."""
    lines = [f"🚨🚨🚨 DIQQAT! {len(fresh)} ta agent do'konlarga kirmay qo'ygan.",
             f"Soat {now_tz.strftime('%H:%M')} dagi holat:", "", _SEP]
    for i, f in enumerate(fresh, 1):
        a = f["agent"]
        lines.append(f"{_mark(f['level'])} {i}. {a.short} ({a.area})")
        lines.append(_last_line(f, prefix="⏰ "))
        lines.append(f"🚫 O'shandan beri {_fmt_dur(f['mins'])} — birorta do'konga kirmadi.")
        lines.append(f"🏪 Bugun jami {f['total']} ta do'konga kirgan.")
        if f["week"] >= 2:
            lines.append(f"⚠️ Shu hafta {f['week']}-marta shunday bo'ldi.")
        lines.append(_SEP)
    worst = fresh[0]["agent"].short
    lines.append("")
    lines.append(f"📞 Eng avval {worst}ga qo'ng'iroq qiling — u eng uzoq vaqtdan beri yo'q.")
    return "\n".join(lines)


async def gps_check(app) -> None:
    """Rejalashtirilgan tekshiruv (har GPS_CHECK_MIN daqiqada)."""
    now_tz = datetime.now(TZ)
    if now_tz.weekday() == 6 or not (WORK_START <= now_tz.hour < WORK_END):
        return
    now = now_tz.replace(tzinfo=None)
    day = now_tz.date().isoformat()
    week_ago = (now_tz.date() - timedelta(days=6)).isoformat()

    try:
        visits = await gps.fetch_today_visits()
    except Exception as e:
        logger.warning("GPS trevoga: vizitlar olinmadi: %s", e)
        return

    from . import roster
    with get_conn() as conn:                 # ro'yxat manbasi — roster.py (yagona joy)
        agents = roster.active_agents(conn)
    by_id = {a.sd_id: a for a in agents}
    last_map = build_last_map(visits, agents)
    missing = find_missing(last_map, now)

    # --- qaytganlarni yopish (oxirgi faollik epizod boshlanganidan keyin) ---
    with get_conn() as conn:
        open_eps = storage.gps_open_episodes(conn, day)
    for ep in open_eps:
        s = last_map.get(ep["sd_id"])
        if not s or not s["last"]:
            continue
        if s["last"].isoformat(sep=" ", timespec="seconds") > ep["last_seen"]:
            with get_conn() as conn:
                storage.gps_mark_returned(conn, ep["id"], _now_iso())
            a = by_id.get(ep["sd_id"])
            name = a.short if a else ep["sd_id"]
            gone = int((s["last"] - datetime.fromisoformat(ep["last_seen"])).total_seconds() // 60)
            hhmm = s["last"].strftime("%H:%M")
            if s["shop"]:
                where = f"{hhmm} da \"{s['shop']}\" do'koniga kirdi."
            else:
                where = f"{hhmm} da yana do'konga kirdi."
            await _send(app, _targets(a.league if a else "city", False),
                        f"✅ {name} yana ishga qaytdi.\n\n{where}\n"
                        f"Undan oldin {_fmt_dur(max(gone, 0))} birorta do'konga kirmagan edi.")

    # --- yangi trevogalar (liga bo'yicha jamlab) ---
    for league in ("city", "region"):
        fresh: list[dict] = []
        has_red = False
        for m in missing:
            a = by_id.get(m["sd_id"])
            if not a or a.league != league:
                continue
            last_seen = m["last"].isoformat(sep=" ", timespec="seconds")
            with get_conn() as conn:
                ep = storage.gps_episode_get(conn, m["sd_id"], day, last_seen)
                if ep is None:
                    eid = storage.gps_episode_create(conn, m["sd_id"], day, last_seen,
                                                     m["level"], _now_iso())
                    wk = storage.gps_week_count(conn, m["sd_id"], week_ago)
                    fresh.append({**m, "agent": a, "eid": eid, "week": wk, "upgrade": False})
                    has_red = has_red or m["level"] == "red"
                elif ep["level"] == "yellow" and m["level"] == "red":
                    storage.gps_episode_to_red(conn, ep["id"], _now_iso())
                    wk = storage.gps_week_count(conn, m["sd_id"], week_ago)
                    fresh.append({**m, "agent": a, "eid": ep["id"], "week": wk, "upgrade": True})
                    has_red = True
        if not fresh:
            continue

        with get_conn() as conn:
            for f in fresh:
                f["sales"] = _today_sales(conn, f["agent"].sd_id, day)

        if len(fresh) == 1:
            f = fresh[0]
            text = _single_message(f)
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("📞 Qo'ng'iroq qildim", callback_data=f"nzgps:ack:{f['eid']}"),
                InlineKeyboardButton("ℹ️ Uzrli sababi bor", callback_data=f"nzgps:why:{f['eid']}"),
            ]])
        else:
            text = _batch_message(fresh, now_tz)
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(f"📞 {f['agent'].short} — qo'ng'iroq qildim",
                                     callback_data=f"nzgps:ack:{f['eid']}"),
                InlineKeyboardButton("ℹ️ Sababi bor", callback_data=f"nzgps:why:{f['eid']}"),
            ] for f in fresh])

        if not ALERTS_TO_SUPERVISORS:
            text = "[SINOV — hozircha faqat sizga]\n" + text
        await _send(app, _targets(league, has_red), text, kb)

    # --- eskalatsiya: qizil, javobsiz, 30 daq o'tgan -> adminga (faqat jonli rejimda) ---
    if ALERTS_TO_SUPERVISORS:
        cutoff = (now_tz - timedelta(minutes=GPS_ESCALATE_MIN)).isoformat(timespec="seconds")
        with get_conn() as conn:
            stale = storage.gps_unacked_red(conn, day, cutoff)
        for ep in stale:
            a = by_id.get(ep["sd_id"])
            with get_conn() as conn:
                storage.gps_mark_escalated(conn, ep["id"], _now_iso())
            await _send(app, list(ADMIN_IDS),
                        f"⚠️ Supervayzer {GPS_ESCALATE_MIN} daqiqadan beri javob bermadi: "
                        f"{a.short if a else ep['sd_id']} (qizil trevoga).")
