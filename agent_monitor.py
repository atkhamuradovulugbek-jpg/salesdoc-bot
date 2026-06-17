"""
agent_monitor.py — Agentlar intizomini real vaqtda nazorat qiladi.

Sales Doctor API'dan bugungi vizitlarni olib, quyidagilarni topadi:
  1. 😴 Yo'qolgan agent — ish vaqtida uzoq (ABSENCE_ALERT_MIN daqiqa) vizit qilmagan
  2. ⚡ Juda tez vizit — do'konda FAST_VISIT_SECONDS soniyadan kam bo'lgan
  3. 🏃 Ketma-ket shubhali tez vizitlar — 1 daqiqada bir nechta do'kon
  4. 🚫 GPS'siz vizit — gps_visit=0 (agent jismonan bormagan bo'lishi mumkin)

Takror ogohlantirmaslik uchun holatni `settings` jadvalida (JSON) saqlaydi.
"""

import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from config import (
    ABSENCE_ALERT_MIN,
    FAST_VISIT_SECONDS,
    RAPID_VISIT_SECONDS,
    TIMEZONE,
    WORK_END_HOUR,
    WORK_START_HOUR,
)
from db import get_conn
from salesdoc_api import get_api

logger = logging.getLogger(__name__)

TZ = ZoneInfo(TIMEZONE)
_STATE_KEY = "agent_monitor_state"


def _parse_dt(s: str):
    """'2026-06-17 09:07:29' -> naive datetime. Xato bo'lsa None."""
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
    return None


def _hhmm(dt: datetime) -> str:
    return dt.strftime("%H:%M") if dt else "—"


def _load_state(today: str) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key=?", (_STATE_KEY,)
        ).fetchone()
    state = {}
    if row and row["value"]:
        try:
            state = json.loads(row["value"])
        except Exception:
            state = {}
    # Yangi kun — holatni tozalaymiz
    if state.get("date") != today:
        state = {"date": today, "absence": {}, "fast": [], "nogps": []}
    state.setdefault("absence", {})
    state.setdefault("fast", [])
    state.setdefault("nogps", [])
    return state


def _save_state(state: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (_STATE_KEY, json.dumps(state, ensure_ascii=False)),
        )


def _sig(v: dict) -> str:
    """Vizit uchun takrorlanmas belgi (API'da vizit id yo'q)."""
    return f"{v.get('agent_id')}|{v.get('client_id')}|{v.get('start_date')}"


def analyze(visits: list[dict], now: datetime) -> dict:
    """Vizitlarni tahlil qilib, topilmalarni qaytaradi (holatdan mustaqil)."""
    in_work_hours = WORK_START_HOUR <= now.hour < WORK_END_HOUR

    # Agent bo'yicha guruhlash
    by_agent: dict[str, dict] = {}
    fast_visits: list[dict] = []
    nogps_visits: list[dict] = []

    for v in visits:
        # Faqat haqiqatan bo'lib o'tgan vizitlar (visited=1)
        if str(v.get("visited")) not in ("1", "True", "true"):
            continue
        start = _parse_dt(v.get("start_date"))
        end = _parse_dt(v.get("end_date"))
        agent_id = str(v.get("agent_id") or "")
        if not agent_id:
            continue

        ag = by_agent.setdefault(agent_id, {
            "name": v.get("agent_name") or agent_id,
            "starts": [],          # (start_dt, visit)
            "last_activity": None,  # eng oxirgi end yoki start
        })
        if start:
            ag["starts"].append((start, v))
        last = end or start
        if last and (ag["last_activity"] is None or last > ag["last_activity"]):
            ag["last_activity"] = last

        # 1 daqiqadan qisqa vizit
        if start and end:
            dur = (end - start).total_seconds()
            if 0 <= dur < FAST_VISIT_SECONDS:
                fast_visits.append({
                    "agent": ag["name"], "client": v.get("client_name") or "",
                    "start": start, "dur_sec": int(dur), "sig": _sig(v),
                })

        # GPS'siz vizit
        if str(v.get("gps_visit")) in ("0", "False", "false", "", "None"):
            nogps_visits.append({
                "agent": ag["name"], "client": v.get("client_name") or "",
                "start": start, "sig": _sig(v),
            })

    # 😴 Yo'qolgan agentlar (faqat ish vaqtida)
    absent: list[dict] = []
    if in_work_hours:
        for agent_id, ag in by_agent.items():
            last = ag["last_activity"]
            if not last:
                continue
            mins = (now - last).total_seconds() / 60.0
            if mins >= ABSENCE_ALERT_MIN:
                absent.append({
                    "agent_id": agent_id, "name": ag["name"],
                    "last": last, "mins": int(mins),
                })

    # 🏃 Ketma-ket shubhali tez vizitlar (start'lar orasi juda yaqin)
    rapid: list[dict] = []
    for agent_id, ag in by_agent.items():
        starts = sorted(ag["starts"], key=lambda x: x[0])
        for i in range(1, len(starts)):
            gap = (starts[i][0] - starts[i - 1][0]).total_seconds()
            if 0 <= gap < RAPID_VISIT_SECONDS:
                v = starts[i][1]
                prev = starts[i - 1][1]
                rapid.append({
                    "agent": ag["name"],
                    "client": v.get("client_name") or "",
                    "prev_client": prev.get("client_name") or "",
                    "gap_sec": int(gap),
                    "start": starts[i][0],
                    "sig": _sig(v),
                })

    return {
        "in_work_hours": in_work_hours,
        "absent": absent,
        "fast": fast_visits,
        "rapid": rapid,
        "nogps": nogps_visits,
        "agent_count": len(by_agent),
    }


def _build_message(findings: dict, now: datetime, only_new: bool, state: dict) -> str | None:
    """Topilmalardan HTML xabar yasaydi. only_new=True bo'lsa faqat yangi (avval
    ogohlantirilmagan) holatlarni qo'shadi va state'ni yangilaydi."""
    lines: list[str] = []

    # 😴 Yo'qolganlar
    absent_new = []
    for a in findings["absent"]:
        if only_new:
            # Shu absence epizodi uchun avval ogohlantirilganmi?
            sig = a["last"].isoformat()
            if state["absence"].get(a["agent_id"]) == sig:
                continue
            state["absence"][a["agent_id"]] = sig
        absent_new.append(a)
    if absent_new:
        lines.append("😴 <b>ISH JOYIDA EMAS (uzoq vaqt vizit yo'q):</b>")
        for a in sorted(absent_new, key=lambda x: -x["mins"]):
            lines.append(f"   • {a['name']} — oxirgi vizit {_hhmm(a['last'])} ({a['mins']} daq oldin)")
        lines.append("")

    # ⚡ Tez vizitlar
    fast_new = []
    for f in findings["fast"]:
        if only_new:
            if f["sig"] in state["fast"]:
                continue
            state["fast"].append(f["sig"])
        fast_new.append(f)
    if fast_new:
        lines.append(f"⚡ <b>JUDA TEZ VIZIT (1 daqiqadan kam):</b>")
        for f in fast_new[:20]:
            lines.append(f"   • {f['agent']} → {f['client']} ({f['dur_sec']} sek, {_hhmm(f['start'])})")
        if len(fast_new) > 20:
            lines.append(f"   <i>...va yana {len(fast_new) - 20} ta</i>")
        lines.append("")

    # 🏃 Ketma-ket tez
    rapid_new = []
    for r in findings["rapid"]:
        if only_new:
            if r["sig"] in state["fast"]:  # bir xil ro'yxatdan foydalanamiz
                continue
            state["fast"].append(r["sig"])
        rapid_new.append(r)
    if rapid_new:
        lines.append("🏃 <b>SHUBHALI TEZ KETMA-KET (1 daqiqada bir nechta do'kon):</b>")
        for r in rapid_new[:20]:
            lines.append(f"   • {r['agent']}: {r['prev_client']} → {r['client']} ({r['gap_sec']} sek farq)")
        if len(rapid_new) > 20:
            lines.append(f"   <i>...va yana {len(rapid_new) - 20} ta</i>")
        lines.append("")

    # 🚫 GPS'siz
    nogps_new = []
    for n in findings["nogps"]:
        if only_new:
            if n["sig"] in state["nogps"]:
                continue
            state["nogps"].append(n["sig"])
        nogps_new.append(n)
    if nogps_new:
        lines.append("🚫 <b>GPS'SIZ VIZIT (jismonan bormagan bo'lishi mumkin):</b>")
        for n in nogps_new[:20]:
            lines.append(f"   • {n['agent']} → {n['client']} ({_hhmm(n['start'])})")
        if len(nogps_new) > 20:
            lines.append(f"   <i>...va yana {len(nogps_new) - 20} ta</i>")
        lines.append("")

    if not lines:
        return None

    header = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🕵️ <b>AGENT NAZORATI</b> — {_hhmm(now)}\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    msg = header + "\n".join(lines).strip()
    # Telegram xabar chegarasi 4096 — xavfsiz tomonda cheklaymiz
    if len(msg) > 3900:
        msg = msg[:3900] + "\n\n<i>...ro'yxat uzun, qisqartirildi.</i>"
    return msg


async def _fetch_today_visits() -> list[dict]:
    today = datetime.now(TZ).date().isoformat()
    api = get_api()
    await api.login()
    return await api.get_visits(today, today)


async def run_check(only_new: bool = True) -> str | None:
    """Avtomatik tekshiruv (scheduler chaqiradi). Faqat YANGI muammolarni
    qaytaradi (takror emas). Muammo yo'q bo'lsa None."""
    now = datetime.now(TZ).replace(tzinfo=None)
    today = now.date().isoformat()

    if not (WORK_START_HOUR <= now.hour < WORK_END_HOUR):
        logger.info("Agent nazorati: ish vaqtidan tashqari (%s), o'tkazib yuborildi", _hhmm(now))
        return None

    visits = await _fetch_today_visits()
    findings = analyze(visits, now)
    state = _load_state(today)
    msg = _build_message(findings, now, only_new=True, state=state)
    _save_state(state)
    logger.info(
        "Agent nazorati: agentlar=%d, yo'q=%d, tez=%d, ketma-ket=%d, gps-siz=%d, xabar=%s",
        findings["agent_count"], len(findings["absent"]), len(findings["fast"]),
        len(findings["rapid"]), len(findings["nogps"]), "bor" if msg else "yo'q",
    )
    return msg


async def run_snapshot() -> str:
    """Qo'lda tugma uchun: hozirgi to'liq holat (takror filtri yo'q)."""
    now = datetime.now(TZ).replace(tzinfo=None)
    visits = await _fetch_today_visits()
    findings = analyze(visits, now)
    # only_new=False — hammasini ko'rsatamiz, state'ga tegmaymiz
    msg = _build_message(findings, now, only_new=False, state={"absence": {}, "fast": [], "nogps": []})
    if msg is None:
        return (
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🕵️ <b>AGENT NAZORATI</b> — {_hhmm(now)}\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ Muammo topilmadi.\n"
            f"👥 Bugun faol agentlar: {findings['agent_count']} ta"
        )
    return msg
