"""
sup_cards.py — SUPERVAYZER oylik/kunlik jadvallari (Ball/Toy o'rniga AKSIYA).
Egasi 2026-10-08 da tasdiqlagan namunalar (suppreview/namuna-sup-aksiya-*.png).

OYLIK:  Agent | STRIKE | OY SAVDO | SAVDO PROGNOZI | OYLIK AKSIYA | AKSIYA PROGNOZI
        strike, oy savdo va savdo prognozi — avvalgi mantiq (o'zgarmagan);
        oylik aksiya — aksiya boshlanishidan hisobot kunigacha kunlik aksiyalar yig'indisi;
        aksiya prognozi — yig'indi ÷ o'tgan aksiya-ish-kunlari × oydagi jami aksiya-ish-kunlari
        (ish kunlari — mavjud kalendar, yakshanba dam), eng yaqin butun son.
KUNLIK: Agent | BUGUN SAVDO | BUGUN AKSIYA | MUKOFOT (SO'M) | KIRDI/SOTDI
        bugun savdo — SOF (qaytim ayirilgan, status 1,2,3) — Monitor va agent kartasi bilan bir xil.
Aksiya hisobi — aksiya_cards / Monitor `aksiya_jadval` (qayta yozilmagan).
"""

from __future__ import annotations

from fractions import Fraction

from db import get_conn

from . import aksiya_cards as ac
from .cards import (GREEN, HAIR, MUTED, PAD, PINK, PINK_SOFT, RED, W, Card, _big_tile, _font,
                    _strike_color, _sup_header, fmt, fmt_mln)
from .core.workdays import month_workdays
from .data import MONTHS_UZ, agent_strike

NAME_W = 290
VAL = (214, 224, 236)
NAME_COL = (237, 243, 250)
ROW_H = 64


def _league_word(league: str) -> str:
    return "shahar" if league == "city" else "viloyat"


def _name(s, conn) -> tuple[str, str]:
    name, area = ac.full_name(conn, s.agent)
    return name + (" (yangi)" if s.agent.observe_only else ""), area


def aksiya_forecast(units: int, agent, asof, sunday_off: bool = True):
    """(prognoz | None, o'tgan aksiya-ish-kunlari, oydagi jami aksiya-ish-kunlari).
    O'tgan ish kuni 0 bo'lsa (aksiya/agent hali boshlanmagan) — prognoz yo'q."""
    elig = ac.eligible_from(agent)
    days = [d for d in month_workdays(asof.year, asof.month, sunday_off) if d >= elig]
    passed = [d for d in days if d <= asof]
    if not passed:
        return None, 0, len(days)
    return int(Fraction(units * len(days), len(passed)) + Fraction(1, 2)), len(passed), len(days)


def monthly_dict(dc, league: str) -> dict:
    asof = dc.today
    dfrom, dto = asof.replace(day=1).isoformat(), asof.isoformat()
    wd_p, wd_t = dc.wd_passed_val(), dc.wd_total_val()
    sunday_off = getattr(dc.rules, "sunday_off", True)
    rows, league_sales, league_prognoz = [], 0.0, 0.0
    with get_conn() as conn:
        for s in dc.by_league[league]:
            name, area = _name(s, conn)
            _, _, strike = agent_strike(conn, s.agent.sd_id, dfrom, dto)
            prognoz = (s.month_sales / wd_p * wd_t) if wd_p else 0      # avvalgi savdo prognozi
            league_sales += s.month_sales
            league_prognoz += prognoz
            units = ac.ledger_dict(dc, s.agent.sd_id)["total_units"]
            fc, _, _ = aksiya_forecast(units, s.agent, asof, sunday_off)
            rows.append({"sd_id": s.agent.sd_id, "name": name, "area": area, "strike": strike,
                         "month_sales": s.month_sales, "prognoz": prognoz,
                         "aksiya": units, "aksiya_fc": fc})
    rows.sort(key=lambda r: r["strike"])
    focus = [f"{r['name']} (strike {r['strike']:.0f}%)" for r in rows[:3] if r["strike"] < 45]
    return {"title": f"supervayzer · oylik · {_league_word(league)}",
            "date_label": f"{asof.day}-{MONTHS_UZ[asof.month].upper()}",
            "rows": rows, "league_sales": league_sales, "league_prognoz": league_prognoz,
            "focus": focus, "month_label": MONTHS_UZ[asof.month]}


def daily_dict(dc, league: str) -> dict:
    day = dc.today
    peers = [s.agent.sd_id for s in dc.by_league[league]]
    rows, league_today = [], 0.0
    with get_conn() as conn:
        net = ac.league_day_net(conn, peers, day)
        for s in dc.by_league[league]:
            name, area = _name(s, conn)
            kirdi, sotdi, _ = agent_strike(conn, s.agent.sd_id, day.isoformat(), day.isoformat())
            n, x = ac.day_result(conn, s.agent.sd_id, day, league)
            sales = net.get(s.agent.sd_id, 0.0)
            league_today += sales
            rows.append({"sd_id": s.agent.sd_id, "name": name, "area": area, "sales": sales,
                         "units": n, "reward": x, "kirdi": kirdi, "sotdi": sotdi})
    rows.sort(key=lambda r: -r["sales"])                 # bugun eng ko'p sotgan yuqorida
    return {"title": f"supervayzer · kunlik · {_league_word(league)}",
            "date_label": f"{day.day}-{MONTHS_UZ[day.month].upper()}",
            "rows": rows, "league_today": league_today}


# ------------------------------------------------------------------
# Rasm (tasdiqlangan namuna uslubi)
# ------------------------------------------------------------------

def _fit(c, text, size, min_size, max_w, bold):
    while size > min_size and c.d.textlength(text, font=_font(size, bold=bold)) > max_w:
        size -= 1
    return _font(size, bold=bold)


def _name_cell(c, name, area):
    c.d.text((PAD, c.y), name, font=_fit(c, name, 23, 15, NAME_W, True), fill=NAME_COL)
    c.d.text((PAD, c.y + 29), area, font=_fit(c, area, 18, 12, NAME_W, False), fill=MUTED)


def _heads(c, cols):
    f = _font(16, bold=True)
    for x, lines in cols:
        for i, ln in enumerate(lines):
            c.d.text((x, c.y + i * 20), ln, font=f, fill=MUTED)
    c.y += 46
    c.d.line([(PAD, c.y), (W - PAD, c.y)], fill=HAIR, width=1)
    c.gap(10)


def _row_end(c):
    c.y += ROW_H
    c.d.line([(PAD, c.y - 6), (W - PAD, c.y - 6)], fill=HAIR, width=1)


def render_monthly(x: dict) -> bytes:
    c = Card()
    _sup_header(c, x["title"], x["date_label"],
                "STRIKE = kirgan do'konning nechtasi oldi · eng yomondan saralab")
    X = [PAD, 356, 462, 594, 750, 884]
    _heads(c, [(X[0], ["AGENT"]), (X[1], ["STRIKE"]), (X[2], ["OY", "SAVDO"]),
               (X[3], ["SAVDO", "PROGNOZI"]), (X[4], ["OYLIK", "AKSIYA"]), (X[5], ["AKSIYA", "PROGNOZI"])])
    fv = _font(24)
    for r in x["rows"]:
        _name_cell(c, r["name"], r["area"])
        y = c.y + 12
        c.d.text((X[1], y - 1), f"{r['strike']:.0f}%", font=_font(26, bold=True), fill=_strike_color(r["strike"]))
        c.d.text((X[2], y + 1), fmt_mln(r["month_sales"]), font=fv, fill=VAL)
        c.d.text((X[3], y + 1), fmt_mln(r["prognoz"]), font=fv, fill=(160, 210, 180))
        c.d.text((X[4], y), str(r["aksiya"]), font=_font(25, bold=True),
                 fill=PINK if r["aksiya"] else MUTED)
        fc = "—" if r["aksiya_fc"] is None else f"~{r['aksiya_fc']}"
        c.d.text((X[5], y + 1), fc, font=fv, fill=PINK_SOFT)
        _row_end(c)
    c.gap(10)
    _big_tile(c, f"{x['month_label']} — liga jami (shu ketishda oy oxiriga)",
              f"{fmt(x['league_prognoz'])} so'm", GREEN,
              sub=f"hozir {fmt(x['league_sales'])}", icon_name="growth")
    if x["focus"]:
        c.callout("Bugun shu agentlar bilan gaplashing: " + ", ".join(x["focus"]) +
                  ". Strike past — oson do'konga sotib, qolganini tashlab ketyapti.",
                  "red", label="BUGUN E'TIBOR BERING", icon="flag")
    c.footer("Strike: <45% qizil, 45-59% sariq, 60%+ yashil. Savdo — mln so'mda. Oylik aksiya — "
             "5-oktabrdan. Aksiya prognozi — shu sur'atda oy oxiriga (ish kunlari, yakshanbasiz).")
    return c.png()


def render_daily(x: dict) -> bytes:
    c = Card()
    _sup_header(c, x["title"], x["date_label"],
                "Bugungi natijalar · kirdi/sotdi = nechta do'konga kirdi va nechtasi oldi")
    X = [PAD, 356, 556, 690, 880]
    _heads(c, [(X[0], ["AGENT"]), (X[1], ["BUGUN", "SAVDO"]), (X[2], ["BUGUN", "AKSIYA"]),
               (X[3], ["MUKOFOT", "(SO'M)"]), (X[4], ["KIRDI/", "SOTDI"])])
    fv = _font(24)
    for r in x["rows"]:
        _name_cell(c, r["name"], r["area"])
        y = c.y + 12
        c.d.text((X[1], y + 1), fmt(r["sales"]), font=fv, fill=RED if r["sales"] <= 0 else VAL)
        c.d.text((X[2], y), str(r["units"]), font=_font(25, bold=True), fill=PINK if r["units"] else MUTED)
        c.d.text((X[3], y + 1), fmt(r["reward"]), font=_font(24, bold=bool(r["reward"])),
                 fill=GREEN if r["reward"] else MUTED)
        c.d.text((X[4], y + 1), f"{r['kirdi']}/{r['sotdi']}", font=fv, fill=VAL)
        _row_end(c)
    c.gap(10)
    _big_tile(c, "Bugun liga jami savdo", f"{fmt(x['league_today'])} so'm", PINK, icon_name="sales")
    c.footer("Kirdi/Sotdi — masalan 12/5: 12 do'konga kirdi, 5 tasi zakaz berdi. "
             "Mukofot — bugungi aksiya mukofoti (so'm).")
    return c.png()


def monthly_png(dc, league: str) -> bytes:
    return render_monthly(monthly_dict(dc, league))


def daily_png(dc, league: str) -> bytes:
    return render_daily(daily_dict(dc, league))


# ------------------------------------------------------------------
# Supervayzer «Yordam» — faqat O'Z ligasi
# ------------------------------------------------------------------

def help_text(league: str | None, reveal: str, gps_alerts: bool, gps_summary: bool) -> str:
    lines = ["<b>Siribom Nazorat — supervayzer</b>\n"]
    if league in ("city", "region"):
        lines.append(f"Ligangiz: <b>{_league_word(league)}</b>\n")
    lines += [
        "📊 <b>Oylik jadval:</b> strike (kirgan do'konning nechtasi oldi), oy savdo, savdo prognozi, "
        f"oylik aksiya ({ac.START_LABEL} dan) va aksiya prognozi (ish kunlari sur'atida, yakshanbasiz).",
        "📋 <b>Kunlik jadval:</b> bugungi sof savdo (qaytim ayirilgan), bugungi aksiya, mukofot (so'm), "
        "kirdi/sotdi.",
        "⚡ <b>Hozirgi holat:</b> bugungi ma'lumotni yangilab, kunlik jadvalni beradi.",
        "💳 <b>Qarz-vazvrat:</b> agentlar qarzi va oylik qaytgan tovar.",
        f"🕘 <b>Avtomatik:</b> 10:00 da qarz-vazvrat, {reveal} da oylik va kunlik jadval"
        + (" hamda GPS xulosa" if gps_summary else "") + "."
        + (" Ish vaqtida GPS ogohlantirishlari keladi." if gps_alerts else ""),
    ]
    if league in ("city", "region"):
        word = _league_word(league)
        r1, r2 = ac._LEAGUE_HELP[league][1:]
        lines.append(
            f"💰 <b>Kunlik aksiya mukofoti ({word} ligasi):</b> 10 tadan kam — 0; 10–14 ta — har biriga "
            f"{r1} so'm; 15 ta va ko'proq — har biriga {r2} so'm. Bitta do'konning bir kunlik sof savdosi — "
            "har to'liq 300 000 so'm = 1 aksiya.")
    else:
        lines.append("💰 Ligangiz aniqlanmadi — tarif ko'rsatilmaydi. Administratorga murojaat qiling.")
    lines.append("\nPastdagi tugmalardan foydalaning 👇")
    return "\n".join(lines)
