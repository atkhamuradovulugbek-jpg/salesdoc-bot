"""
compute.py — bot bazasidan (faqat o'qish) prezentatsiya MODELini hisoblaydi.

Formulalar oktyabr 1–12 shahar taqdimotidan olingan (Cowork sessiyasi, 2026-10-13 — asl skriptlar
README'da sanab o'tilgan). Farqi — manba: o'shanda Sales Doctor'dan qo'lda eksport qilingan Excel,
endi bot bazasi (Sales Doctor bilan avtomatik sinxron). Aksiya va «sof savdo» botning o'z
funksiyalari bilan hisoblanadi (aksiya_jadval: do'kon-kun sof = summa − qaytim, status 1,2,3).

Slaydlar (render.py tartibida): muqova · 1 plan/prognoz · 2 kim qancha sotdi · 3 haftalik reyting ·
4 300 000 aksiya · 5 aksiya kunma-kun · 6 ozgina yetmagan · 7 xulosa · yakun.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import yaml

import aksiya_jadval as aj
from db import get_conn
from nazorat import roster
from nazorat.core.rules import load_agents, load_rules
from nazorat.core.workdays import month_workdays

from .render import cell

HERE = Path(__file__).resolve().parent
OK = (1, 2, 3)                     # yangi · jo'natilgan · yetkazilgan
DELIVERED = 3
MON = ["", "YANVAR", "FEVRAL", "MART", "APREL", "MAY", "IYUN", "IYUL", "AVGUST", "SENTYABR",
       "OKTYABR", "NOYABR", "DEKABR"]
MON3 = ["", "yan", "fev", "mar", "apr", "may", "iyun", "iyul", "avg", "sen", "okt", "noy", "dek"]
LEAGUE = {"shahar": "city", "viloyat": "region"}
LEAGUE_UP = {"city": "SHAHAR", "region": "VILOYAT"}
RATES = {"city": ("5 000", "6 667"), "region": ("4 000", "5 333")}


def load_config(path: Path | None = None) -> dict:
    return yaml.safe_load((path or HERE / "config.yaml").read_text(encoding="utf-8"))


def mon_cap(m: int) -> str:
    return MON[m].capitalize()


def fmt_sp(n) -> str:
    return f"{int(round(n)):,}".replace(",", " ")


def mln1(v: float) -> str:
    return f"{v / 1e6:.1f}"


def _d(x) -> date:
    return x if isinstance(x, date) else date.fromisoformat(str(x))


def _workdays(a: date, b: date) -> list[date]:
    return [a + timedelta(i) for i in range((b - a).days + 1) if (a + timedelta(i)).weekday() != 6]


def _prev_month(d: date) -> tuple[date, date]:
    last = d.replace(day=1) - timedelta(days=1)
    return last.replace(day=1), last


@dataclass
class Agent:
    sd_id: str
    nm: str
    hud: str
    since: date                                     # davr ichida hisob boshlanishi (yangi o'rindiq)
    new: bool = False
    day_sales: dict = field(default_factory=dict)   # date -> summa (status 1,2,3, qaytimsiz — asl slayd kabi)
    visits: int = 0
    orders: int = 0
    vis_day: dict = field(default_factory=dict)     # date -> (tashrif, buyurtma)
    prev_sales: float = 0.0                         # o'tgan oy, yetkazilgan (asl: «Sentyabr yakuni»)
    prev_visits: int = 0
    prev_orders: int = 0
    shopday: dict = field(default_factory=dict)     # (do'kon, kun) -> sof summa (aksiya oynasi)
    seat_later: bool = False                        # o'rindiq davrdan keyin boshqa agentga o'tgan


# ------------------------------------------------------------------
# Ma'lumot
# ------------------------------------------------------------------

def _names(conn, ags, cfg):
    from nazorat import aksiya_cards as ac
    out = {}
    for a in ags:
        if a.sd_id in (cfg.get("names") or {}):
            nm, hud = cfg["names"][a.sd_id]
        else:
            nm, hud = ac.full_name(conn, a)
        out[a.sd_id] = (nm, hud)
    return out


def load_agents_data(start: date, end: date, league: str, cfg: dict, aks_start: date) -> list[Agent]:
    p0, p1 = _prev_month(start)
    with get_conn() as conn:
        ags = [a for a in roster.active_agents(conn, load_agents(), day=end) if a.league == league]
        names = _names(conn, ags, cfg)
        out = []
        for a in ags:
            sd = getattr(a, "start_date", None)
            since = max(start, date.fromisoformat(sd)) if sd else start
            later = since > end            # o'rindiq davrdan KEYIN almashgan — bot tarixni saqlamaydi
            if later:
                since = start
            nm, hud = names[a.sd_id]
            for h in (cfg.get("seat_history") or {}).get(a.sd_id, []):   # qo'lda: o'tgan davr egasi
                f, t = _d(h["from"]), _d(h["to"])
                if f <= end <= t:
                    since, later = max(start, f), False
                    nm, hud = h.get("name", nm), h.get("hud", hud)
            ag = Agent(a.sd_id, nm, hud, since, new=since > start)
            ag.seat_later = later
            for d, s in conn.execute(
                    f"""SELECT date, SUM(total_after_discount) FROM orders WHERE agent_sd_id=? AND date>=? AND date<=?
                        AND status IN {OK} GROUP BY date""", (a.sd_id, since.isoformat(), end.isoformat())):
                ag.day_sales[date.fromisoformat(d)] = float(s or 0)
            for d, v, o in conn.execute(
                    """SELECT date, SUM(visited), SUM(has_order) FROM visits WHERE agent_sd_id=? AND date>=? AND date<=?
                       GROUP BY date""", (a.sd_id, since.isoformat(), end.isoformat())):
                ag.vis_day[date.fromisoformat(d)] = (int(v or 0), int(o or 0))
            ag.visits = sum(v for v, _ in ag.vis_day.values())
            ag.orders = sum(o for _, o in ag.vis_day.values())
            if not ag.new:                      # yangi o'rindiqda o'tgan oy — boshqa odamniki
                r = conn.execute(f"""SELECT COALESCE(SUM(total_after_discount),0) FROM orders WHERE agent_sd_id=?
                                     AND date>=? AND date<=? AND status={DELIVERED}""",
                                 (a.sd_id, p0.isoformat(), p1.isoformat())).fetchone()
                ag.prev_sales = float(r[0] or 0)
                r = conn.execute("""SELECT COALESCE(SUM(visited),0), COALESCE(SUM(has_order),0) FROM visits
                                    WHERE agent_sd_id=? AND date>=? AND date<=?""",
                                 (a.sd_id, p0.isoformat(), p1.isoformat())).fetchone()
                ag.prev_visits, ag.prev_orders = int(r[0]), int(r[1])
            a0 = max(aks_start, since)
            if a0 <= end:
                blocks = defaultdict(float)
                for oid, shop, d, total, ret in conn.execute(
                        f"""SELECT sd_id, client_sd_id, date, total_after_discount, total_returns FROM orders
                            WHERE agent_sd_id=? AND date>=? AND date<=? AND status IN {aj.VALID_STATUSES}""",
                        (a.sd_id, a0.isoformat(), end.isoformat())):
                    blocks[(shop or ("_order", oid), date.fromisoformat(d))] += float(total or 0) - float(ret or 0)
                ag.shopday = dict(blocks)
            out.append(ag)
    return out


# ------------------------------------------------------------------
# Hisob
# ------------------------------------------------------------------

def _first_monday(d: date) -> date:
    """Oyning 1-ish kuni tushgan haftaning dushanbasi (1-hafta shundan sanaladi)."""
    fw = d.replace(day=1)
    if fw.weekday() == 6:
        fw += timedelta(days=1)
    return fw - timedelta(days=fw.weekday())


def weeks_in(start: date, end: date) -> list[tuple[int, list[date]]]:
    """Davr ichidagi TUGAGAN haftalar (du–sh, shanba ≤ end): [(oydagi hafta raqami, ish kunlari)]."""
    out, d = [], start
    first_monday = _first_monday(start)
    while d <= end:
        sat = d + timedelta(days=(5 - d.weekday()) % 7)
        if d.weekday() == 6:
            d += timedelta(days=1)
            continue
        if sat > end:
            break
        num = (d - first_monday).days // 7 + 1
        out.append((num, _workdays(d, sat)))
        d = sat + timedelta(days=2)
    return out


def compute(start: date, end: date, league_name: str, cfg: dict | None = None,
            prognoz_days=None, label: str | None = None, overrides: dict | None = None) -> dict:
    cfg = cfg or load_config()
    league = LEAGUE[league_name]
    rules = load_rules()
    dp = rules.daily_plan[league]
    plan_m = rules.monthly_sales_plan[league] / 1e6
    aks_start = cfg["aksiya_start"] if isinstance(cfg["aksiya_start"], date) else date.fromisoformat(cfg["aksiya_start"])
    agents = load_agents_data(start, end, league, cfg, aks_start)
    agents = [a for a in agents if a.day_sales or a.visits]      # davrda umuman ishlamagan — chiqadi
    n = len(agents)
    mwd = month_workdays(end.year, end.month, True)
    wd_passed = len([d for d in mwd if start <= d <= end])
    pd = prognoz_days if prognoz_days is not None else cfg.get("prognoz_days", "calendar")
    M = len(mwd) if pd in (None, "calendar") else int(pd)
    rem = len([d for d in mwd if d > end])
    p0, _ = _prev_month(start)
    PREV, prev_cap = MON[p0.month], mon_cap(p0.month)
    d_lbl = f"{start.day}–{end.day}"
    mon_s = MON3[end.month]

    # ---------- agent ko'rsatkichlari ----------
    for a in agents:
        a.oct = sum(a.day_sales.values()) / 1e6
        own_wd = len([d for d in mwd if a.since <= d <= end]) or 1
        own_m = len([d for d in mwd if d >= a.since]) if a.new else M
        a.proj = a.oct * own_m / own_wd
        a.sept = a.prev_sales / 1e6
        a.chg = (a.proj / a.sept - 1) * 100 if a.sept else None
    tOct = sum(a.oct for a in agents)
    tProj = sum(a.proj for a in agents)
    tSep = sum(a.sept for a in agents if not a.new)

    # ---------- aksiya ----------
    aks_days_month = [d for d in mwd if d >= aks_start]
    aks_window = [d for d in aks_days_month if max(aks_start, start) <= d <= end]
    AWD = len(aks_window)
    ATOT = len(aks_days_month)
    for a in agents:
        daily = defaultdict(int)
        near = band = 0
        for (shop, d), s in a.shopday.items():
            daily[d] += aj.units_for_shop_day(s)
            if 250_000 <= s < 300_000:
                near += 1
            if any(k * 300_000 <= s < k * 300_000 + 30_000 for k in (1, 2, 3)):
                band += 1
        a.aks_daily = dict(daily)
        a.rew_daily = {d: aj.reward(u, league) for d, u in daily.items()}
        a.aks = sum(daily.values())
        a.rew = sum(a.rew_daily.values())
        a.d10 = sum(1 for u in daily.values() if u >= 10)
        a.d15 = sum(1 for u in daily.values() if u >= 15)
        a.nearday = sum(1 for u in daily.values() if u in (8, 9, 13, 14))
        a.exact = sum(1 for u in daily.values() if u in (10, 15))
        a.near, a.band, a.nshop = near, band, len(a.shopday)
        a.net = sum(a.shopday.values()) / 1e6
        own_aw = len([d for d in aks_window if d >= a.since]) or 1
        own_at = len([d for d in aks_days_month if d >= a.since]) if a.new else ATOT
        a.aks_awd = own_aw
        a.avg = a.aks / own_aw
        a.aks_proj = round(a.aks * own_at / own_aw)
        a.rew_proj = round(a.rew * own_at / own_aw)

    # ---------- haftalik reyting ----------
    rc = cfg["rating"]
    wks = weeks_in(start, end)[-2:]
    if not wks:                                    # davrda to'liq hafta yo'q — davrning o'zi bitta hafta
        wks = [((start - _first_monday(start)).days // 7 + 1, _workdays(start, end))]
    for a in agents:
        a.weeks = []
        for num, days in wks:
            days = [d for d in days if d >= a.since]
            if not days:
                a.weeks.append(None)
                continue
            s = sum(a.day_sales.get(d, 0) for d in days)
            v = sum(a.vis_day.get(d, (0, 0))[0] for d in days)
            o = sum(a.vis_day.get(d, (0, 0))[1] for d in days)
            nol = sum(1 for d in days if a.day_sales.get(d, 0) < dp * rc["nol_threshold"])
            ratio = s / (dp * len(days))
            b10 = o / v * 10 if v else 0
            adays = [d for d in days if d >= aks_start]
            aks = sum(a.aks_daily.get(d, 0) for d in adays) / len(adays) if adays else None
            sc = min(ratio / rc["plan_full"], 1) * 4 + min(b10 / rc["b10_full"], 1) * 2 + max(0, 2 - nol)
            score = round(sc / 8 * 10, 1) if aks is None else round(sc + min(aks / rc["aks_full"], 1) * 2, 1)
            a.weeks.append(dict(num=num, ratio=ratio, b10=b10, nol=nol, aks=aks, score=score))

    # ================== MODEL ==================
    tables = []
    hl = LEAGUE_UP[league]

    # --- 1. plan / prognoz
    RS = sorted(agents, key=lambda a: -a.proj)
    rows, alerts = [], set()
    for i, a in enumerate(RS):
        grow = a.chg is not None and a.chg >= 5
        hit = a.proj >= plan_m
        pp = a.proj / plan_m * 100
        st = ("Tushyapti, plan yo'q" if not grow and not hit else "Plan yopiladi, o'sish yo'q" if not grow
              else "O'syapti, LEKIN planga chiqmaydi" if not hit else "O'syapti, plan yopiladi")
        if a.new:
            st = "Yangi agent — " + ("plan yopiladi" if hit else "planga chiqmaydi")
        if not hit:
            alerts.add(i)
        rows.append([
            cell(f"{a.nm}{' *' if a.new else ''}\n{a.hud}"), cell(f"{a.oct:.1f}"),
            cell(f"~{a.proj:.0f}", "a"), cell(f"{a.sept:.1f}" if not a.new else "—", "m"),
            cell(f"{'+' if (a.chg or 0) > 0 else ''}{a.chg:.0f}%" if a.chg is not None else "—",
                 "g" if grow else ("m" if a.chg is None else "r")),
            cell(f"{plan_m:.0f}", "m"), cell(f"{pp:.0f}%", "g" if hit else "r"),
            cell(st, "g" if grow and hit else ("y" if hit else "r"))])
    tchg = (tProj / tSep - 1) * 100 if tSep else 0
    tables.append(dict(
        sec="1", title="O'SISH BORMI? PLANGA CHIQADIMI?", sub="— OY OXIRI PROGNOZI",
        cols=[21.15, 10.16, 11.39, 10.57, 10.08, 8.28, 8.28, 20.08],
        head=["Agent / hudud", f"{mon_s.capitalize()} {d_lbl}\n(mln)", "Oy oxiri\nprognoz", f"{prev_cap}\nyakuni",
              "O'zgarish", "Oylik\nplan", "Plan\n%", "Holat"],
        rows=rows,
        total=[cell("JAMI"), cell(f"{tOct:.1f}"), cell(f"~{tProj:.0f}"), cell(f"{tSep:.1f}"), cell(f"{tchg:.0f}%"),
               cell(f"{plan_m * n:.0f}"), cell(f"{tProj / (plan_m * n) * 100:.0f}%"), cell("")],
        note=(f"Prognoz = {wd_passed} ish kunlik savdo × {M} ÷ {wd_passed} (yangi+jo'natilgan+yetkazilgan, vazvratsiz). "
              f"Oylik plan: {hl.capitalize()} — {plan_m:.0f} mln. Yashil = o'syapti VA plan yopiladi; qizil = plan "
              f"yopilmaydi (o'ssa ham) yoki tushyapti." + _new_note(agents)),
        namecols={0}, textcols={7}, toprows=3, medalcol=None, heat=False,
        bars={6: (round(max(a.proj / plan_m * 100 for a in agents)) if agents else 100, 100)}, alerts=alerts))

    # --- 2. kim qancha sotdi
    def dlt(o, s, dec):
        d = o - s
        c = "m" if abs(d) < (0.3 if dec else 10) else ("g" if d > 0 else "r")
        return cell(("+" if d > 0 else "") + (f"{d:.1f}" if dec else f"{round(d)}"), c)

    KS = sorted(agents, key=lambda a: -a.oct)
    rows = []
    for a in KS:
        ob10 = a.orders / a.visits * 10 if a.visits else 0
        ochk = a.oct * 1e6 / a.orders / 1000 if a.orders else 0
        sb10 = a.prev_orders / a.prev_visits * 10 if a.prev_visits else 0
        schk = a.prev_sales / a.prev_orders / 1000 if a.prev_orders else 0
        has_prev = not a.new and a.prev_visits
        rows.append([
            cell(f"{a.nm}{' *' if a.new else ''}\n{a.hud}"), cell(f"{a.oct:.1f}"), cell(a.visits), cell(a.orders),
            cell(f"{ob10:.1f}", "g" if ob10 >= 5 else ("r" if ob10 < 4 else "w")),
            cell(f"{sb10:.1f}" if has_prev else "—", "m"), dlt(ob10, sb10, True) if has_prev else cell("", "m"),
            cell(f"{round(ochk)}", "g" if ochk >= 250 else ("r" if ochk < 170 else "w")),
            cell(f"{round(schk)}" if has_prev else "—", "m"), dlt(ochk, schk, False) if has_prev else cell("", "m")])
    TV, TO = sum(a.visits for a in agents), sum(a.orders for a in agents)
    old = [a for a in agents if not a.new]
    SV, SO = sum(a.prev_visits for a in old), sum(a.prev_orders for a in old)
    tables.append(dict(
        sec="2", title="KIM QANCHA SOTDI?", sub=f"— {n} AGENT, {PREV} BILAN SOLISHTIRUV",
        cols=[18.7, 8.29, 8.29, 8.86, 11.65, 8.61, 6.73, 12.31, 8.61, 7.96],
        head=["Agent / hudud", "Savdo\n(mln)", "Tashrif", "Buyurtma", "10 tashrifga\nbuyurtma", prev_cap, "Farq",
              "O'rtacha\nchek (ming)", prev_cap, "Farq"],
        rows=rows,
        total=[cell("JAMI"), cell(f"{tOct:.1f}"), cell(TV), cell(TO), cell(f"{TO / TV * 10:.1f}" if TV else "0.0"),
               cell(f"{SO / SV * 10:.1f}" if SV else "—"), cell(""),
               cell(f"{round(tOct * 1000 / TO)}" if TO else "0"), cell(""), cell("")],
        note=(f"O'rtacha chek = savdo ÷ buyurtma. «{prev_cap}» ustuni — {PREV.lower()}ning to'liq oyi. Farq yashil = "
              f"yaxshilandi, qizil = yomonlashdi. 10 tashrifga buyurtma: yashil ≥5, qizil <4."),
        namecols={0}, textcols=set(), toprows=3, medalcol=None, heat=False, bars={}, alerts=set()))

    # --- 3. haftalik reyting
    def sc_col(v):
        return "g" if v >= 8.5 else ("y" if v >= 6.5 else "r")

    def wlabel(num, days):
        a, b = days[0], days[-1]
        rng = f"{a.day}–{b.day} {MON3[b.month]}" if a != b else f"{a.day} {MON3[b.month]}"
        return f"{num}-hafta\n({rng})"

    def avg_of(a):
        s = [w["score"] for w in a.weeks if w]
        return sum(s) / len(s) if s else 0

    RR = sorted(agents, key=lambda a: -avg_of(a))
    rows, alerts = [], set()
    for i, a in enumerate(RR):
        w = a.weeks + [None] * (2 - len(a.weeks))
        w1, w2 = (w[0], w[1]) if len(wks) == 2 else (None, w[0])
        av = avg_of(a)
        if w1 and w2:
            dd = w2["score"] - w1["score"]
            arrow = "▲" if dd >= rc["arrow_step"] else ("▼" if dd <= -rc["arrow_step"] else "=")
        else:
            arrow, dd = "=", 0
        last = w2 or w1
        note = (f"Reja {round(last['ratio'] * 100)}% • 10 tashrifga {last['b10']:.1f} buyurtma • nol kun {last['nol']}"
                + (f" • kuniga {last['aks']:.1f} aksiya" if last and last["aks"] is not None else "")) if last else ""
        if av < 5:
            alerts.add(i)
        rows.append([cell(i + 1), cell(a.nm + (" *" if a.new else "")),
                     cell(f"{w1['score']:.1f}", sc_col(w1["score"])) if w1 else cell("—", "m"),
                     cell(f"{w2['score']:.1f}", sc_col(w2["score"])) if w2 else cell("—", "m"),
                     cell(f"{av:.1f}"), cell(arrow, "g" if arrow == "▲" else ("r" if arrow == "▼" else "m")),
                     cell(note, "m")])
    heads = [wlabel(num, days) for num, days in wks if days]
    heads = (["—"] * (2 - len(heads)) + heads)[-2:]
    no_aks = any(not any(d >= aks_start for d in days) for _, days in wks)
    tables.append(dict(
        sec="3", title="HAFTALIK REYTING BAHOSI", sub="— FUTBOLDAGIDEK, 10 BALLIK",
        cols=[3.93, 17.21, 10.74, 10.74, 9.18, 8.85, 39.34],
        head=["#", "Agent", *heads[:2], "O'rtacha", "Yo'nalish", f"{wks[-1][0] if wks else ''}-hafta izohi"],
        rows=rows, total=None,
        note=("Baho 4 narsadan: kunlik rejani bajarish — 4 ball • 10 tashrifga buyurtma — 2 • aksiya soni (kuniga "
              f"15 = to'liq) — 2 • nol kunlar (har biri −1) — 2."
              + (" 1-haftada aksiya hali yo'q edi — 8 balldan 10 ga keltirilgan." if no_aks else "")
              + " Har majlisda yangi hafta bahosi qo'shiladi."),
        namecols={1}, textcols={6}, toprows=0, medalcol=0, heat=False, bars={4: (10, None)}, alerts=alerts))

    # --- 4. 300 000 aksiya
    AS = sorted(agents, key=lambda a: (-a.rew, -a.aks))
    rows = []
    for i, a in enumerate(AS):
        rows.append([cell(i + 1), cell(a.nm + (" *" if a.new else "")), cell(f"{a.net:.1f}"), cell(a.aks),
                     cell(fmt_sp(a.rew) if a.rew else "0", "g" if a.rew else "r"), cell(a.d10),
                     cell(a.d15, "g" if a.d15 else "w"),
                     cell(f"{a.avg:.1f}", "g" if a.avg >= 10 else ("y" if a.avg >= 8 else "r")),
                     cell(f"~{a.aks_proj}"), cell(f"~{fmt_sp(a.rew_proj)}" if a.rew_proj else "0",
                                                   "w" if a.rew_proj else "r")])
    ta = sum(a.aks for a in AS)
    r1, r2 = RATES[league]
    tables.append(dict(
        sec="4", title="300 000 AKSIYA", sub="— KIM QANCHA SOTDI, QANCHA TOPDI",
        cols=[3.69, 14.12, 9.52, 8.87, 12.89, 7.96, 7.96, 9.52, 11.33, 14.12],
        head=["#", "Agent", "Sof savdo\n(mln)", "Aksiya\nsoni", "Mukofot\n(so'm)", "10+\nkunlar", "15+\nkunlar",
              "Kuniga\no'rtacha", "Aksiya\nprognoz", "Mukofot\nprognoz"],
        rows=rows,
        total=[cell(""), cell("JAMI"), cell(f"{sum(a.net for a in AS):.1f}"), cell(ta), cell(fmt_sp(sum(a.rew for a in AS))),
               cell(sum(a.d10 for a in AS)), cell(sum(a.d15 for a in AS)),
               cell(f"{ta / max(AWD, 1) / max(n, 1):.1f}"), cell(f"~{sum(a.aks_proj for a in AS)}"),
               cell(f"~{fmt_sp(sum(a.rew_proj for a in AS))}")],
        note=(f"Qoida: do'kon-kun sof summasi ÷ 300 000 (pastga yaxlitlab) = aksiya. Kuniga 10–14 → {r1} so'mdan, "
              f"15+ → {r2} so'mdan. {AWD} ish kuni o'tdi, {ATOT} dan. Prognoz = jami × {ATOT} ÷ {AWD}. "
              f"Sof = summa − qaytim (botdagi hisob bilan bir xil)."),
        namecols={1}, textcols=set(), toprows=0, medalcol=0, heat=False,
        bars={3: (max([a.aks for a in AS] + [1]), None)}, alerts=set()))

    # --- 5. kunma-kun
    show_days = sorted({d for d in aks_window} | {d for a in agents for d, u in a.aks_daily.items() if u})
    rows = []
    for a in AS:
        r = [cell(a.nm + (" *" if a.new else ""))]
        for d in show_days:
            u, rw = a.aks_daily.get(d, 0), a.rew_daily.get(d, 0)
            r.append(cell(f"{u}" + (f" / {round(rw / 1000)}" if rw else ""),
                          "g" if u >= 15 else ("y" if u >= 10 else ("w" if u >= 8 else "m"))))
        r.append(cell(f"{a.aks} / {round(a.rew / 1000)}"))
        rows.append(r)
    sundays = [d for d in _days(max(aks_start, start), end) if d.weekday() == 6 and d not in show_days]
    sun_note = (" " + ", ".join(f"{d.day}-{MON[d.month].lower()}" for d in sundays) + " yakshanba — savdo yo'q."
                if sundays else "")
    nd = len(show_days)
    tables.append(dict(
        sec="5", title="AKSIYA KUNMA-KUN", sub="— aksiya soni / mukofot (ming so'm)",
        cols=[16.58] + [round(83.42 / (nd + 1), 2)] * (nd + 1),
        head=["Agent"] + [f"{d.day:02d}-{MON3[d.month]}" for d in show_days] + ["Jami"],
        rows=rows, total=None,
        note=("Yashil = 15+ (yuqori stavka) • Sariq = 10–14 (mukofotli) • Oq = 8–9 (ozgina yetmadi) • Kulrang = "
              "mukofotsiz." + sun_note),
        namecols={0}, textcols=set(), toprows=0, medalcol=None, heat=True, bars={}, alerts=set()))

    # --- 6. ozgina yetmagan
    rows = []
    for a in sorted(agents, key=lambda a: -a.near):
        sh = a.band / a.nshop * 100 if a.nshop else 0
        rows.append([cell(a.nm + (" *" if a.new else "")), cell(a.near, "y" if a.near >= 5 else "w"),
                     cell(a.nearday, "y" if a.nearday >= 2 else "w"), cell(a.exact, "r" if a.exact >= 2 else "w"),
                     cell(a.band), cell(a.nshop, "m"), cell(f"{sh:.0f}%", "r" if sh >= 8 else "w")])
    tables.append(dict(
        sec="6", title="OZGINA YETMAGAN", sub="va SHUBHALI BELGILAR",
        cols=[16.56, 15.98, 16.56, 14.1, 15.33, 11.64, 9.84],
        head=["Agent", "Do'kon-kun\n250–299 ming", "Kunlar 8–9\nyoki 13–14 aksiya", "Kunlar aynan\n10 yoki 15",
              "Do'kon-kun\n300–330 ming", "Jami\ndo'kon-kun", "300–330\nulushi"],
        rows=rows, total=None,
        note=("Chap tomoni — «ozgina yetmagan»: shu do'konlarga 1 ta qo'shimcha mahsulot = aksiya. O'ng tomoni — "
              "faqat belgi, ayb emas: 300–330 ming oralig'i ko'p bo'lsa, buyurtmalar sun'iy «to'ldirilgan» bo'lishi "
              "mumkin — supervayzer tekshirsin."),
        namecols={0}, textcols=set(), toprows=0, medalcol=None, heat=False,
        bars={1: (max([a.near for a in agents] + [1]), None)}, alerts=set()))

    label = label or ("1-YARIM OY" if end.day <= 15 else "OY YAKUNI" if rem == 0 else f"{d_lbl}-{MON[end.month]}")
    model = dict(
        title=f"{MON[end.month]} — {label} • {hl.capitalize()} ligasi • Siribom",
        cover=dict(topbar=f"{hl} LIGASI  •  {d_lbl} {MON[end.month]} {end.year}", l1=f"{MON[end.month]} —", l2=label,
                   src=["Manba: Sales Doctor.",
                        f"Prognoz = {wd_passed} ish kunlik savdo × {M} ÷ {wd_passed}, «shu sur'at davom etsa» — kafolat emas."],
                   kpis=[(f"Savdo {d_lbl} {mon_s}:", f"{tOct:.0f} mln"), ("Oy oxiri prognozi:", f"~{tProj:.0f} mln"),
                         (f"{prev_cap} yakuni:", f"{tSep:.0f} mln ({'+' if tProj >= tSep else ''}{tchg:.0f}%)")]),
        tables=tables,
        xulosa=dict(sec="7", title="XULOSA", sub=f"— {label}", cards=_xulosa(agents, RR, AS, AWD, tchg, n, avg_of, PREV)),
        final=dict(big=f"{rem} ish kuni qoldi — aksiyada hali hech narsa hal bo'lgani yo'q!",
                   f2=("Kuniga 10 aksiya = mukofot boshlanadi, 15 = ikki barobar." if league == "city"
                       else "Kuniga 10 aksiya = mukofot boshlanadi, 15 = yuqori stavka."),
                   f3=f"Keyingi majlisda: {(wks[-1][0] + 1) if wks else 1}-hafta reyting bahosi + aksiya yangilanadi"),
    )
    return apply_overrides(model, overrides)


def _days(a: date, b: date):
    return [a + timedelta(i) for i in range((b - a).days + 1)]


def _new_note(agents) -> str:
    new = [a for a in agents if a.new]
    later = [a for a in agents if a.seat_later]
    out = ""
    if later:
        out += (" O'rindiq davrdan keyin almashgan: " + ", ".join(a.nm for a in later)
                + " — davr butunicha shu o'rindiq bo'yicha.")
    if not new:
        return out
    return out + " * Yangi agent: " + ", ".join(f"{a.nm} ({a.since.day}-{MON[a.since.month].lower()}dan)" for a in new) + \
        " — prognoz o'z ish kunlari bo'yicha, o'tgan oy bilan solishtirilmaydi."


def _xulosa(agents, RR, AS, AWD, tchg, n, avg_of, PREV):
    """4 karta — oktyabr slaydida qo'lda yozilgan; bu yerda shablon bo'yicha avtomatik.
    Istalgan kartani overrides.yaml orqali qo'lda almashtirish mumkin."""
    old = [a for a in agents if not a.new and a.chg is not None]
    up = [a for a in old if a.chg >= 5]
    top_g = sorted(old, key=lambda a: -a.chg)[:3]
    flat = [a for a in old if a.chg < 5]
    c1 = (("Hamma o'syapti" if len(up) == len(old) else f"{len(up)} agent o'syapti") + f" — liga prognozi {tchg:+.0f}%",
          f"{len(old)} agentdan {len(up)} tasi {PREV.lower()} yakunidan yuqori sur'atda. "
          + ", ".join(f"{a.nm} {a.sept:.0f} → ~{a.proj:.0f} mln ({a.chg:+.0f}%)" for a in top_g) + "."
          + (" Past: " + ", ".join(f"{a.nm} ({a.chg:+.0f}%)" for a in flat) + "." if flat else ""), "bag", "g")
    t = AS[0] if AS else None
    zero = [a.nm for a in AS if not a.rew]
    totr = sum(a.rew for a in AS)
    c2 = (f"Aksiya: {t.nm} {t.aks} ta / {fmt_sp(t.rew)}" if t else "Aksiya",
          (", ".join(f"{a.nm} {fmt_sp(a.rew)}" for a in AS[1:3]) + ". " if len(AS) > 1 else "")
          + f"Liga {AWD} kunda {fmt_sp(totr)} so'm mukofot ishladi; oy oxiriga ~{sum(a.rew_proj for a in AS) / 1e6:.1f} mln."
          + (f" {len(zero)} agent ({', '.join(zero)}) hali 0 — kuniga 10 ga yetmayapti." if zero else ""), "gift", "y")
    top3 = RR[:3]
    low = [a for a in RR[-3:] if avg_of(a) < 7]
    c3 = ("Reyting: " + ", ".join(f"{a.nm} {avg_of(a):.1f}" for a in top3),
          ("Pastda: " + ", ".join(
              f"{a.nm} {avg_of(a):.1f}" + (f" ({a.weeks[0]['score']:.1f} → {a.weeks[-1]['score']:.1f})"
                                          if len(a.weeks) == 2 and all(a.weeks) else "") for a in low)
           + ". Supervayzer bilan birga chiqish." if low else "Pastki chegaradan (7 ball) past agent yo'q."), "star", "r")
    nr = sorted(agents, key=lambda a: -a.near)
    c4 = (f"{nr[0].nm} — {nr[0].near} do'kon-kun 250–299 mingda" if nr else "Ozgina yetmagan",
          (", ".join(f"{a.nm} {a.near}" for a in nr[1:4]) + ". " if len(nr) > 1 else "")
          + "Bu do'konlarga 1 ta mahsulot qo'shilsa — tayyor aksiya. Supervayzer ro'yxatni bersin.", "store", "y")
    return [c1, c2, c3, c4]


def apply_overrides(model: dict, ov: dict | None) -> dict:
    """overrides.yaml: qo'lda kiritiladigan matnlar (xulosa kartalari, yorliq, yakuniy matn)."""
    if not ov:
        return model
    for i, card in enumerate(ov.get("xulosa") or []):
        if card and i < len(model["xulosa"]["cards"]):
            old = model["xulosa"]["cards"][i]
            model["xulosa"]["cards"][i] = (card.get("title", old[0]), card.get("text", old[1]), old[2], old[3])
    for k in ("big", "f2", "f3"):
        if (ov.get("final") or {}).get(k):
            model["final"][k] = ov["final"][k]
    return model
