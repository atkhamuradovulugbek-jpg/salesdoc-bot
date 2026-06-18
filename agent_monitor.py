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
    MONITOR_RED_MIN,
    RAPID_VISIT_SECONDS,
    SUSPICIOUS_RED,
    SUSPICIOUS_SHOW,
    TIMEZONE,
    WORK_END_HOUR,
    WORK_START_HOUR,
)
import hashlib
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
            "visits": 0, "fast": 0, "nogps": 0, "rapid": 0,
        })
        ag["visits"] += 1
        if start:
            ag["starts"].append((start, v))
        last = end or start
        if last and (ag["last_activity"] is None or last > ag["last_activity"]):
            ag["last_activity"] = last

        # 1 daqiqadan qisqa vizit
        if start and end:
            dur = (end - start).total_seconds()
            if 0 <= dur < FAST_VISIT_SECONDS:
                ag["fast"] += 1
                fast_visits.append({
                    "agent": ag["name"], "client": v.get("client_name") or "",
                    "start": start, "dur_sec": int(dur), "sig": _sig(v),
                })

        # GPS'siz vizit
        if str(v.get("gps_visit")) in ("0", "False", "false", "", "None"):
            ag["nogps"] += 1
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
                ag["rapid"] += 1
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

    # Har agent bo'yicha yig'ma statistika (kompakt hisobot uchun)
    stats: list[dict] = []
    for agent_id, ag in by_agent.items():
        last = ag["last_activity"]
        mins = int((now - last).total_seconds() / 60) if last else 9999
        susp = ag["fast"] + ag["rapid"] + ag["nogps"]
        stats.append({
            "agent_id": agent_id, "name": ag["name"],
            "visits": ag["visits"], "fast": ag["fast"],
            "rapid": ag["rapid"], "nogps": ag["nogps"],
            "susp": susp, "mins": mins, "last": last,
        })

    return {
        "in_work_hours": in_work_hours,
        "absent": absent,
        "fast": fast_visits,
        "rapid": rapid,
        "nogps": nogps_visits,
        "stats": stats,
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


def _short_name(name: str) -> str:
    """Ismni qisqartiradi: 'Rahmonov Burhoniddin (Shayhontohur)' -> familiya + hudud."""
    terr = ""
    if "(" in name and name.endswith(")"):
        terr = name[name.rfind("(") + 1:-1].strip()
        name = name[:name.rfind("(")].strip()
    first = name.split()[0] if name.split() else name
    return f"{first} ({terr})" if terr else first


def _susp_breakdown(s: dict) -> str:
    parts = []
    if s["fast"]:
        parts.append(f"{s['fast']} tez")
    if s["rapid"]:
        parts.append(f"{s['rapid']} ketma-ket")
    if s["nogps"]:
        parts.append(f"{s['nogps']} GPSsiz")
    return ", ".join(parts)


def _classify_stats(stats: list[dict]) -> tuple[list[dict], int]:
    """Agentlarni muammoli (🔴/🟡) va sog'lom (yashirin) ga ajratadi."""
    problems = []
    healthy = 0
    for s in stats:
        is_problem = s["mins"] > ABSENCE_ALERT_MIN or s["susp"] >= SUSPICIOUS_SHOW
        if not is_problem:
            healthy += 1
            continue
        if s["mins"] > MONITOR_RED_MIN or s["susp"] >= SUSPICIOUS_RED:
            status = "🔴"
        else:
            status = "🟡"
        problems.append({**s, "status": status})
    order = {"🔴": 0, "🟡": 1}
    problems.sort(key=lambda p: (order[p["status"]], -p["mins"], -p["susp"]))
    return problems, healthy


_CAT_LABEL = {"city": "🏙️ SHAHAR", "region": "🏘️ VILOYAT"}


def _filter_by_category(stats: list[dict], category: str | None) -> list[dict]:
    """Agentlarni shahar/viloyat bo'yicha ajratadi (reports.classify_agent orqali).
    Hududi tanilmagan ('unknown') agentlar SHAHAR guruhiga qo'shiladi — hech kim
    ikkala xabardан tushib qolmasin."""
    if not category:
        return stats
    from reports import classify_agent
    if category == "city":
        return [s for s in stats if classify_agent(s["name"]) in ("city", "unknown")]
    return [s for s in stats if classify_agent(s["name"]) == category]


def build_compact(findings: dict, now: datetime, category: str | None = None,
                  show_when_clean: bool = True) -> str | None:
    """Kompakt hisobot: muammoli agentlar yuqorida (bittadan), sog'lomlar yig'ilgan.
    category='city'/'region' bo'lsa faqat o'sha guruh. Muammo yo'q va
    show_when_clean=False bo'lsa None qaytaradi."""
    stats = _filter_by_category(findings["stats"], category)
    problems, healthy = _classify_stats(stats)
    reds = sum(1 for p in problems if p["status"] == "🔴")
    yellows = sum(1 for p in problems if p["status"] == "🟡")

    cat_txt = f" · {_CAT_LABEL[category]}" if category in _CAT_LABEL else ""

    if not problems:
        if not show_when_clean:
            return None
        return (
            f"🕵️ <b>AGENT NAZORATI</b>{cat_txt} · {_hhmm(now)}\n"
            f"✅ Hammasi joyida — {healthy} agent normal ishlayapti."
        )

    lines = [
        f"🕵️ <b>AGENT NAZORATI</b>{cat_txt} · {_hhmm(now)}",
        f"🔴 {reds} · 🟡 {yellows} · ✅ {healthy} normal",
        "",
    ]
    for i, p in enumerate(problems, start=1):
        mins_txt = f"{p['mins']}daq yo'q" if p["mins"] > ABSENCE_ALERT_MIN else f"{p['mins']}daq oldin"
        # "Shubhali" yig'indisi olib tashlandi (u har xil narsalarni qo'shib chalkash edi).
        # Faqat vizit soni + turlarga ajratilgan tafsilot: "24 vizit (12 tez, 3 ketma-ket, 16 GPSsiz)"
        bd = _susp_breakdown(p)
        vizit_txt = f"{p['visits']} vizit ({bd})" if bd else f"{p['visits']} vizit"
        lines.append(f"{p['status']} {i}. <b>{_short_name(p['name'])}</b>")
        lines.append(f"    {mins_txt} · {vizit_txt}")
    if healthy:
        lines.append("")
        lines.append(f"✅ Qolgan {healthy} agent normal ishlayapti")

    msg = "\n".join(lines)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n\n<i>...ro'yxat uzun, qisqartirildi.</i>"
    return msg


def _compact_signature(findings: dict, category: str | None = None) -> str:
    """Holat 'belgisi' — daqiqalarsiz (ular har safar o'zgaradi). Faqat qaysi agent,
    qanday status va shubhali soni o'zgarsa — yangi xabar yuboriladi."""
    stats = _filter_by_category(findings["stats"], category)
    problems, _ = _classify_stats(stats)
    parts = [f"{p['agent_id']}:{p['status']}:{p['susp']}:{p['visits']}" for p in problems]
    raw = "|".join(sorted(parts))
    return hashlib.md5(raw.encode()).hexdigest()


async def _fetch_today_visits() -> list[dict]:
    today = datetime.now(TZ).date().isoformat()
    api = get_api()
    await api.login()
    return await api.get_visits(today, today)


async def run_check(only_new: bool = True) -> list[str]:
    """Avtomatik tekshiruv (scheduler chaqiradi). SHAHAR va VILOYAT uchun ALOHIDA
    ikkita kompakt xabar (supervayzerlarga alohida forward qilish uchun).
    Faqat holat o'zgargan kategoriya yuboriladi — takror spam emas.
    O'zgarish bo'lmasa bo'sh ro'yxat."""
    now = datetime.now(TZ).replace(tzinfo=None)
    today = now.date().isoformat()

    if not (WORK_START_HOUR <= now.hour < WORK_END_HOUR):
        logger.info("Agent nazorati: ish vaqtidan tashqari (%s), o'tkazib yuborildi", _hhmm(now))
        return []

    visits = await _fetch_today_visits()
    findings = analyze(visits, now)
    state = _load_state(today)

    messages: list[str] = []
    sent_cats = []
    for cat in ("city", "region"):  # shahar tepada, viloyat keyin
        sig = _compact_signature(findings, cat)
        key = f"last_sig_{cat}"
        if state.get(key) != sig:
            msg = build_compact(findings, now, category=cat, show_when_clean=False)
            if msg:
                messages.append(msg)
                sent_cats.append(cat)
            state[key] = sig
    _save_state(state)

    logger.info(
        "Agent nazorati: agentlar=%d, yuborilgan kategoriyalar=%s",
        findings["agent_count"], sent_cats or "yo'q",
    )
    return messages


async def run_summary() -> str:
    """📍 GPS tugmasi uchun: shahar va viloyat alohida bo'limда (bitta xabarда)."""
    now = datetime.now(TZ).replace(tzinfo=None)
    visits = await _fetch_today_visits()
    findings = analyze(visits, now)
    city = build_compact(findings, now, category="city", show_when_clean=True)
    region = build_compact(findings, now, category="region", show_when_clean=True)
    return f"{city}\n\n{region}"


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
