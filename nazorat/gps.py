"""
gps.py — GPS vizit nazorati: kunlik xulosa uchun ma'lumot yig'ish.

Sales Doctor'dan bugungi vizitlarni olib, har agent bo'yicha hisoblaydi:
  1-vizit (birinchi do'konga kirgan soat), oxirgi vizit, jami vizit,
  soxta vizit (gps_visit=0 — GPS tasdiqlamagan), tez vizit (<60 soniya).

Karta 20:10 da render bo'ladi (nazorat.jobs → cards.render_gps_summary).
Kelajakda (2-bosqich) kunduzgi tezkor trevogalar ham shu ma'lumotdan foydalanadi.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from . import storage

TZ = ZoneInfo("Asia/Tashkent")

FAST_SECONDS = 60          # shundan qisqa vizit = TEZ (eski bot bilan bir xil)

# Qator/katak ranglari chegaralari (jami vizitga nisbatan ulush)
FAKE_RED, FAKE_AMBER = 0.60, 0.35
FAST_RED, FAST_AMBER = 0.50, 0.25
LATE_START_RED, LATE_START_AMBER = 11 * 60, 10 * 60        # 1-vizit shu daqiqadan kech
EARLY_END_RED, EARLY_END_AMBER = 13 * 60 + 30, 15 * 60 + 30  # oxirgi vizit shu daqiqadan erta
LOW_TOTAL = 8              # shundan kam vizit = e'tibor


def _parse(s) -> datetime | None:
    if not s:
        return None
    s = str(s).strip()[:19]
    for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, f)
        except ValueError:
            continue
    return None


async def fetch_today_visits() -> list[dict]:
    """Bugungi vizitlar (Sales Doctor API, jonli)."""
    from salesdoc_api import get_api
    today = datetime.now(TZ).date().isoformat()
    api = get_api()
    await api.login()
    return await api.get_visits(today, today)


def analyze_visits(visits: list[dict], agents) -> dict[str, dict]:
    """API vizitlaridan sd_id bo'yicha statistika (faqat visited=1)."""
    stats = {a.sd_id: {"first": None, "last": None, "total": 0, "fake": 0, "fast": 0}
             for a in agents}
    for v in visits:
        if str(v.get("visited")) not in ("1", "True", "true"):
            continue
        aid = str(v.get("agent_id") or "")
        if aid not in stats:
            continue
        s = stats[aid]
        st, en = _parse(v.get("start_date")), _parse(v.get("end_date"))
        s["total"] += 1
        t = en or st
        if st and (s["first"] is None or st < s["first"]):
            s["first"] = st
        if t and (s["last"] is None or t > s["last"]):
            s["last"] = t
        if st and en and 0 <= (en - st).total_seconds() < FAST_SECONDS:
            s["fast"] += 1
        if str(v.get("gps_visit")) in ("0", "False", "false", "", "None"):
            s["fake"] += 1
    return stats


def _mins(dt: datetime | None) -> int | None:
    return dt.hour * 60 + dt.minute if dt else None


def severity(s: dict) -> str:
    """Qator rangi: red (jiddiy) / amber (e'tibor) / ok."""
    t = s["total"]
    if t == 0:
        return "red"
    fake_r, fast_r = s["fake"] / t, s["fast"] / t
    lm = _mins(s["last"])
    if (lm is not None and lm < EARLY_END_RED) or fast_r >= FAST_RED or fake_r >= FAKE_RED:
        return "red"
    fm = _mins(s["first"])
    if ((fm is not None and fm > LATE_START_AMBER) or
            (lm is not None and lm < EARLY_END_AMBER) or
            fake_r >= FAKE_AMBER or fast_r >= FAST_AMBER or t < LOW_TOTAL):
        return "amber"
    return "ok"


def _cell(v: float, red: float, amber: float, invert: bool = False) -> str:
    """Katak rangi: qiymat chegaradan oshsa bad/warn ('invert' — kichik bo'lsa yomon)."""
    if invert:
        return "bad" if v < red else ("warn" if v < amber else "ok")
    return "bad" if v >= red else ("warn" if v >= amber else "ok")


def build_league_card(league: str, visits: list[dict], today: date) -> dict:
    """render_gps_summary uchun tayyor dict (muammolilar tepada)."""
    from db import get_conn
    from .data import MONTHS_UZ
    from . import roster
    with get_conn() as conn:                 # ro'yxat manbasi — roster.py (yagona joy)
        agents = roster.active_agents(conn, league=league)
    stats = analyze_visits(visits, agents)
    rows = []
    for a in agents:
        s = stats[a.sd_id]
        t = s["total"]
        fake_r = s["fake"] / t if t else 0.0
        fast_r = s["fast"] / t if t else 0.0
        fm, lm = _mins(s["first"]), _mins(s["last"])
        rows.append({
            "name": a.short, "terr": a.area, "sev": severity(s),
            "first": s["first"].strftime("%H:%M") if s["first"] else "—",
            "last": s["last"].strftime("%H:%M") if s["last"] else "—",
            "total": t, "fake": s["fake"], "fast": s["fast"],
            "first_col": "ok" if fm is None else _cell(fm, LATE_START_RED, LATE_START_AMBER),
            "last_col": "ok" if lm is None else
                        ("bad" if lm < EARLY_END_RED else ("warn" if lm < EARLY_END_AMBER else "ok")),
            "total_col": "bad" if t == 0 else ("warn" if t < LOW_TOTAL else "ok"),
            "fake_col": _cell(fake_r, FAKE_RED, FAKE_AMBER) if t else "ok",
            "fast_col": _cell(fast_r, FAST_RED, FAST_AMBER) if t else "ok",
            "_susp": (s["fake"] + s["fast"]) / t if t else 9.0,
        })
    order = {"red": 0, "amber": 1, "ok": 2}
    rows.sort(key=lambda r: (order[r["sev"]], -r["_susp"], r["total"]))
    title = "Shahar ligasi" if league == "city" else "Viloyat ligasi"
    return {
        "title": title,
        "date_label": f"{today.day}-{MONTHS_UZ[today.month].upper()}",
        "rows": rows,
    }
