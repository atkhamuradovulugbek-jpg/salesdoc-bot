"""
sup_plan.py — SUPERVAYZER «Plan jadvali» (egasi 2026-10-15 da tasdiqlagan 4-namuna).

Yo'nalish (shahar / viloyat) bo'yicha OYLIK plan (supervisor_plan.yaml, har biri 1 mlrd):
  tepa  — ish kunlari · plan · bajarildi % · qolgan · prognoz · «oy oxirida N mln yetmaydi» ·
          kunlik o'rtacha · BUGUN (sotildi / kerak edi / %) · ERTADAN kunlik kerak
  past  — agentlar (oy savdosi bo'yicha): oy savdosi · bugun (ulushga nisbatan yashil/qizil) ·
          «Ertaga e'tibor» — bugun ulushidan eng ko'p ortda qolgan 3 agent.

Hisob:
  • ish kunlari — mavjud kalendar (yakshanba dam);
  • bugun kerak edi = (plan − kechagacha savdo) ÷ (bugun + qolgan ish kunlari);
  • ertadan kunlik kerak = (plan − bugungacha savdo) ÷ qolgan ish kunlari;
  • agent ulushi = bugun kerak edi ÷ yo'nalishdagi faol agentlar soni (teng);
  • prognoz = kunlik o'rtacha (bugungacha ÷ o'tgan ish kunlari) × oydagi ish kunlari.
Agentlarning 50/60 mln shaxsiy planlari bu kartada ISHLATILMAYDI.
"""

from __future__ import annotations

from functools import lru_cache

import yaml

from db import get_conn

from . import icons, sup_cards
from .cards import (BG, GREEN, HAIR, MUTED, PAD, PINK, PINK_SOFT, RED, SUB, TILE, TILE2, W,
                    Card, _big_tile, _font, _mix, _plan_tile, fmt, status_color)
from .core.rules import CONFIG_DIR
from .core.workdays import month_workdays
from .data import MONTHS_UZ

LEAGUE_TITLE = {"city": "Toshkent shahar", "region": "Toshkent viloyati"}
VAL = (214, 224, 236)


@lru_cache(maxsize=1)
def monthly_plan() -> dict[str, float]:
    with open(CONFIG_DIR / "supervisor_plan.yaml", encoding="utf-8") as f:
        return {k: float(v) for k, v in yaml.safe_load(f)["monthly_plan"].items()}


def mln(n: float) -> str:
    return f"{n / 1_000_000:.1f}".replace(".", ",") + " mln"


def plan_dict(dc, league: str) -> dict:
    t = dc.today
    plan = monthly_plan()[league]
    wds = month_workdays(t.year, t.month, getattr(dc.rules, "sunday_off", True))
    wd_total = len(wds)
    wd_passed = len([d for d in wds if d <= t])
    wd_rem = wd_total - wd_passed                       # ertadan
    snaps = dc.by_league[league]
    n_ag = len(snaps)

    done = sum(s.month_sales for s in snaps)
    today = sum(s.today_sales for s in snaps)
    need_today = max(plan - (done - today), 0) / (wd_rem + 1) if t in wds else 0
    share = need_today / n_ag if n_ag else 0
    avg = done / wd_passed if wd_passed else 0
    prognoz = avg * wd_total

    rows = []
    with get_conn() as conn:
        for s in snaps:
            name, area = sup_cards._name(s, conn)
            days_sold = len([d for d, v in s.day_sales.items() if v > 0 and d in wds])
            rows.append({"name": name, "area": area, "month": s.month_sales,
                         "today": s.today_sales,
                         "pct": s.today_sales / share * 100 if share else 0,
                         "behind": share - s.today_sales,
                         # oyda ish kunlarining yarmidan kam kunida savdo — yangi/ta'tilda?
                         "low_days": days_sold < wd_passed / 2})
    rows.sort(key=lambda r: -r["month"])
    focus = sorted([r for r in rows if r["behind"] > 0], key=lambda r: -r["behind"])[:3]
    return {"title": LEAGUE_TITLE[league],
            "date_label": f"{t.day}-{MONTHS_UZ[t.month].upper()}",
            "day_word": f"{t.day}-{MONTHS_UZ[t.month].lower()}", "month_label": MONTHS_UZ[t.month],
            "wd_total": wd_total, "wd_passed": wd_passed, "wd_rem": wd_rem,
            "plan": plan, "done": done, "pct": done / plan * 100 if plan else 0,
            "remaining": max(plan - done, 0), "today": today, "need_today": need_today,
            "today_pct": today / need_today * 100 if need_today else 0, "share": share,
            "need_next": max(plan - done, 0) / wd_rem if wd_rem else 0, "avg": avg,
            "prognoz": prognoz, "prognoz_pct": prognoz / plan * 100 if plan else 0,
            "gap": plan - prognoz, "rows": rows, "focus": focus}


def _dot(c, x, y, ok, r=9):
    c.d.ellipse([x - r, y - r, x + r, y + r], fill=GREEN if ok else RED)


def render(x: dict) -> bytes:
    c = Card()
    c.header("supervayzer · plan jadvali", x["date_label"], x["title"], x["month_label"] + " oyi")
    c.gap(2)
    seg_w = (W - 2 * PAD - 24) / 3
    for i, (lab, val, col) in enumerate([("ISH KUNI", x["wd_total"], SUB),
                                          ("ISHLAB BO'LINDI", x["wd_passed"], PINK_SOFT),
                                          ("QOLDI", x["wd_rem"], GREEN)]):
        sx = PAD + i * (seg_w + 12)
        c.d.rounded_rectangle([sx, c.y, sx + seg_w, c.y + 66], 12, fill=TILE)
        c.d.text((sx + 20, c.y + 12), lab, font=_font(16, bold=True), fill=MUTED)
        c.d.text((sx + 20, c.y + 32), f"{val} kun", font=_font(26, bold=True), fill=col)
    c.y += 66 + 18
    _plan_tile(c, "Oylik plan", f"{fmt(x['plan'])} so'm", SUB)
    _plan_tile(c, "Bajarildi", f"{fmt(x['done'])} so'm", PINK,
               sub=f"{x['pct']:.0f}%", frac=x["pct"] / 100)
    _plan_tile(c, "Yana bajarish kerak", f"{fmt(x['remaining'])} so'm", GREEN)
    _big_tile(c, "Oylik prognoz (shu ketishda)", f"{fmt(x['prognoz'])} so'm",
              status_color(x["prognoz_pct"]), sub=f"{x['prognoz_pct']:.0f}%", icon_name="growth")

    # pulda orqada qolish / ortig'i
    g = x["gap"]
    if g > 0:
        txt, gc = f"Shu tezlikda oy oxirida {mln(g)} yetmaydi", RED
    else:
        txt, gc = f"Shu tezlikda plan {mln(-g)} ortig'i bilan bajariladi", GREEN
    c.d.rounded_rectangle([PAD, c.y, W - PAD, c.y + 54], 12, fill=TILE)
    c.d.rounded_rectangle([PAD, c.y + 10, PAD + 6, c.y + 44], 3, fill=gc)
    c.d.text((PAD + 24, c.y + 12), txt, font=_font(26, bold=True), fill=gc)
    c.y += 54 + 14
    c.row("Hozirgi kunlik o'rtacha", f"{fmt(x['avg'])} so'm", divider=False)
    c.gap(4)

    # BUGUN
    ok = x["today_pct"] >= 100
    col = GREEN if ok else RED
    h = 170
    c.d.rounded_rectangle([PAD, c.y, W - PAD, c.y + h], 18, fill=TILE2)
    lx = PAD + 32
    c.d.text((lx, c.y + 22), f"BUGUN · {x['day_word'].upper()}", font=_font(21, bold=True), fill=MUTED)
    big = _font(58, bold=True)
    c.d.text((lx, c.y + 52), fmt(x["today"]), font=big, fill=col)
    vw = c.d.textlength(fmt(x["today"]), font=big)
    c.d.text((lx + vw + 12, c.y + 80), "so'm sotildi", font=_font(26), fill=SUB)
    c.d.text((lx, c.y + 126), f"Kerak edi: {fmt(x['need_today'])} so'm", font=_font(26, bold=True),
             fill=VAL)
    pt = f"{x['today_pct']:.0f}%"
    pf = _font(54, bold=True)
    c.d.text((W - PAD - 32 - c.d.textlength(pt, font=pf), c.y + 40), pt, font=pf, fill=col)
    lab = "BAJARILDI" if ok else "BAJARILMADI"
    lw = c.d.textlength(lab, font=_font(20, bold=True))
    _dot(c, W - PAD - 32 - lw - 22, c.y + 124, ok)
    c.d.text((W - PAD - 32 - lw, c.y + 112), lab, font=_font(20, bold=True), fill=col)
    c.y += h + 12

    # ERTADAN KUNLIK KERAK
    h = 118
    c.d.rounded_rectangle([PAD, c.y, W - PAD, c.y + h], 18, fill=TILE2)
    icons.draw(c.d, "target", PAD + 42, c.y + h // 2, 20, PINK, 3)
    c.d.text((PAD + 86, c.y + 20), "ERTADAN PLANGA YETISH UCHUN KUNIGA", font=_font(20, bold=True),
             fill=MUTED)
    c.d.text((PAD + 86, c.y + 50), f"{fmt(x['need_next'])} so'm", font=_font(46, bold=True), fill=PINK)
    sub = f"{x['wd_rem']} kun qoldi"
    sw = c.d.textlength(sub, font=_font(26, bold=True))
    c.d.text((W - PAD - 32 - sw, c.y + 62), sub, font=_font(26, bold=True), fill=PINK_SOFT)
    c.y += h + 6

    # AGENTLAR
    c.section(f"Agentlar · bugungi ulush {mln(x['share'])} dan", icon="growth")
    X = [PAD, PAD + 50, 640, 850]
    hf = _font(16, bold=True)
    for cx, lab in ((X[1], "AGENT"), (X[2], "OY SAVDOSI"), (X[3], "BUGUN")):
        c.d.text((cx, c.y), lab, font=hf, fill=MUTED)
    c.y += 32
    for i, r in enumerate(x["rows"], 1):
        nm = r["name"] + (" *" if r["low_days"] else "")
        c.d.text((PAD, c.y + 6), f"{i}.", font=_font(24, bold=True), fill=MUTED)
        c.d.text((X[1], c.y), nm, font=sup_cards._fit(c, nm, 24, 15, 520, True), fill=(237, 243, 250))
        c.d.text((X[1], c.y + 28), r["area"], font=sup_cards._fit(c, r["area"], 18, 12, 520, False),
                 fill=MUTED)
        c.d.text((X[2], c.y + 10), mln(r["month"]), font=_font(25), fill=VAL)
        okr = r["pct"] >= 100
        _dot(c, X[3] + 9, c.y + 25, okr)
        c.d.text((X[3] + 28, c.y + 9), mln(r["today"]), font=_font(25, bold=True),
                 fill=GREEN if okr else RED)
        c.y += 56
        c.d.line([(PAD, c.y - 6), (W - PAD, c.y - 6)], fill=HAIR, width=1)

    if x["focus"]:
        c.gap(4)
        h = 58
        c.d.rounded_rectangle([PAD, c.y, W - PAD, c.y + h], 14, fill=_mix(BG, RED, 0.16),
                              outline=RED, width=2)
        lab = "ERTAGA E'TIBOR:"
        lf = _font(22, bold=True)
        c.d.text((PAD + 22, c.y + 16), lab, font=lf, fill=RED)
        lx = PAD + 22 + c.d.textlength(lab, font=lf) + 14
        names = ", ".join(r["name"] + ("*" if r["low_days"] else "") for r in x["focus"])
        c.d.text((lx, c.y + 14), names,
                 font=sup_cards._fit(c, names, 25, 16, W - PAD - 22 - lx, True), fill=(255, 225, 225))
        c.y += h + 12
    c.footer("Yashil — agent bugun ulushini bajardi, qizil — bajarmadi."
             + ("  * oyda kam kun ishlagan — aniqlang." if any(r["low_days"] for r in x["rows"])
                else ""))
    return c.png()


def plan_png(dc, league: str) -> bytes:
    return render(plan_dict(dc, league))
