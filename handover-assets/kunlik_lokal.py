"""
VAQTINCHALIK LOKAL SKRIPT — namuna rasm chizadi. Faqat scratchpad'da.

TO'LIQ LOKAL: serverga hech narsa yuborilmaydi. Ma'lumot oldin read-only
o'qib olingan lokal fayllardan (orders-today.psv, agents-today.psv).

YANGI QOIDA (egasi 2026-10-07 da tasdiqladi):
  bitta DO'KONning bitta KUNdagi barcha haqiqiy buyurtmalari qaytgan tovar
  ayirilgandan keyin BIRLASHTIRILADI → keyin har to'liq 300 000 = 1 aksiya.
  Har buyurtmani alohida yaxlitlash YO'Q. Do'konlar/kunlar birlashmaydi.
  Qoldiq ertaga o'tmaydi. Manfiy jami → 0.

Doimiy modul (`nazorat/aksiya.py`) O'ZGARTIRILMAYDI — undan faqat
`daily_bonus` (mukofot stavkalari) olinadi.
"""
import sys
from collections import defaultdict
from io import BytesIO
from pathlib import Path

ROOT = Path("/Users/ulugbek/Desktop/salesdoc-bot")
HERE = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw

import image_reports as _ir

# LOKAL SHRIFT: Mac'da DejaVu yo'q. Faqat SHU SKRIPT ichida Arial'ga
# yo'naltiramiz — image_reports.py fayli O'ZGARTIRILMAYDI (serverda DejaVu bor).
_ir._FONT_CANDIDATES_REGULAR = ["/System/Library/Fonts/Supplemental/Arial.ttf",
                                "/Library/Fonts/Arial Unicode.ttf"]
_ir._FONT_CANDIDATES_BOLD = ["/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                             "/System/Library/Fonts/Supplemental/Arial.ttf"]

from image_reports import (BG_CREAM, GREEN_HEADER, TEXT_DARK, WHITE,
                           DEFAULT_CITY_DAILY_PLAN, DEFAULT_REGION_DAILY_PLAN,
                           _ball_for_pct, _draw_cell, _fmt_int, _font,
                           classify_agent)
from nazorat import aksiya

CFG = aksiya.load_config(ROOT / "nazorat" / "config" / "aksiya.yaml")
STEP = CFG["threshold_sum"]                      # 300 000

# ── VILOYAT STAVKASI — egasi 2026-10-07 da tasdiqladi ───────────
# FAQAT SHU NAMUNA UCHUN, xotirada. `aksiya.yaml` fayli O'ZGARTIRILMAYDI.
#   n < 10        → 0 so'm
#   n 10–14       → n × 4 000
#   n 15+         → n × (80 000 ÷ 15), yaxlitlash FAQAT oxirida
# Shahar qoidasi tegilmaydi.
CFG["leagues"]["viloyat"]["min_units"] = 10
CFG["leagues"]["viloyat"]["tiers"] = [
    {"min_n": 10, "rate": 4000},
    {"min_n": 15, "rate_total": 80000, "rate_units": 15},
]


# ── YANGI QOIDA: do'kon-kun bloki ────────────────────────────────
def units_for_shop_day(net_total: float) -> int:
    """Do'konning bir kunlik JAMI sof summasidan aksiya soni."""
    if net_total <= 0:
        return 0
    return int(net_total // STEP)


def verify():
    """Egasi bergan misollar — hisob to'g'riligini tekshiradi."""
    checks = [
        ("bir do'kon/kun 150k+150k",      [(150_000, 0), (150_000, 0)], 1),
        ("bir do'kon/kun 400k+300k+200k", [(400_000, 0), (300_000, 0), (200_000, 0)], 3),
        ("bir do'kon 900k − 300k qaytim", [(900_000, 300_000)], 2),
        ("bir do'kon/kun 200k",           [(200_000, 0)], 0),
        ("bir do'kon/kun 100k",           [(100_000, 0)], 0),
    ]
    ok = True
    for nom, orders, kutilgan in checks:
        net = sum(max(s - r, 0) for s, r in orders)
        got = units_for_shop_day(net)
        mark = "✅" if got == kutilgan else "❌"
        if got != kutilgan:
            ok = False
        print(f"  {mark} {nom:<34} → {got} (kutilgan {kutilgan})")
    # ikki TURLI do'kon 150k dan → har biri 0
    a = units_for_shop_day(150_000) + units_for_shop_day(150_000)
    print(f"  {'✅' if a == 0 else '❌'} ikki turli do'kon 150k dan      → {a} (kutilgan 0)")
    print("\nVILOYAT MUKOFOTI (yangi stavka):")
    for n, kut in ((5, 0), (9, 0), (10, 40_000), (11, 44_000), (13, 52_000),
                   (14, 56_000), (15, 80_000), (16, 85_333), (30, 160_000)):
        got = aksiya.daily_bonus(n, "viloyat", CFG)
        m = "✅" if got == kut else "❌"
        if got != kut:
            ok = False
        print(f"  {m} n={n:<3} → {got:>7} (kutilgan {kut})")
    print("\nSHAHAR MUKOFOTI (o'zgarmagan):")
    for n, kut in ((9, 0), (10, 50_000), (14, 70_000), (15, 100_000), (25, 166_667)):
        got = aksiya.daily_bonus(n, "shahar", CFG)
        m = "✅" if got == kut else "❌"
        if got != kut:
            ok = False
        print(f"  {m} n={n:<3} → {got:>7} (kutilgan {kut})")
    return ok and a == 0


# ── Ma'lumot (lokal fayllardan) ──────────────────────────────────
def load():
    agents = {}
    day = None
    for ln in (HERE / "agents-today.psv").read_text().splitlines():
        if ln.startswith("20") and "|" not in ln:
            day = ln.strip()
            continue
        sd, _, nm = ln.partition("|")
        if sd and nm:
            agents[sd] = nm
    orders = []
    for ln in (HERE / "orders-today.psv").read_text().splitlines():
        p = ln.split("|")
        if len(p) != 5:
            continue
        orders.append({"client": p[0], "agent_sd": p[1], "status": int(p[2]),
                       "total": float(p[3]), "ret": float(p[4])})
    return agents, orders, day


def compute(agents, orders):
    """Do'kon-kun bloklari → agent bo'yicha aksiya."""
    shop_net = defaultdict(float)                 # (agent, do'kon) → sof jami
    shop_agents = defaultdict(set)                # do'kon → agentlar (noaniqlik tekshiruvi)
    sales = defaultdict(float)                    # agent → bugungi savdo
    for o in orders:
        if o["agent_sd"] not in agents:
            continue
        net = max(o["total"] - o["ret"], 0.0)
        shop_net[(o["agent_sd"], o["client"])] += net
        shop_agents[o["client"]].add(o["agent_sd"])
        sales[o["agent_sd"]] += net

    units = defaultdict(int)
    for (ag, _shop), net in shop_net.items():
        units[ag] += units_for_shop_day(net)

    ambiguous = {s: a for s, a in shop_agents.items() if len(a) > 1}

    rows = {"city": [], "region": []}
    for sd, nm in agents.items():
        cat = classify_agent(nm)
        if cat not in rows:
            continue
        lg = "shahar" if cat == "city" else "viloyat"
        u = units[sd]
        plan = DEFAULT_CITY_DAILY_PLAN if cat == "city" else DEFAULT_REGION_DAILY_PLAN
        pct = (sales[sd] / plan * 100) if plan else 0
        _, _, bg = _ball_for_pct(pct)          # ESKI qoida: savdo/kunlik reja
        rows[cat].append({"name": nm, "sales": sales[sd], "units": u,
                          "bonus": aksiya.daily_bonus(u, lg, CFG), "league": lg,
                          "bg": bg})
    for k in rows:
        rows[k].sort(key=lambda v: -v["sales"])
    return rows, ambiguous


# ── Chizish (mavjud uslub) ───────────────────────────────────────
def _center(d, t, x, y, w, h, f, fill):
    bb = f.getbbox(t)
    d.text((x + (w - (bb[2] - bb[0])) // 2 - bb[0],
            y + (h - (bb[3] - bb[1])) // 2 - bb[1]), t, font=f, fill=fill)


def _hdr(d, x, y, w, h, lines, f):
    _draw_cell(d, x, y, w, h, bg=GREEN_HEADER)
    lh = f.getbbox("Ag")[3] - f.getbbox("Ag")[1]
    yy = y + (h - (lh * len(lines) + 6 * (len(lines) - 1))) // 2
    for ln in lines:
        bb = f.getbbox(ln)
        d.text((x + (w - (bb[2] - bb[0])) // 2 - bb[0], yy - bb[1]), ln, font=f, fill=WHITE)
        yy += lh + 6


def _wrap(t, f, maxw):
    if f.getbbox(t)[2] <= maxw:
        return [t]
    out, cur = [], ""
    for w in t.split():
        c = (cur + " " + w).strip()
        if f.getbbox(c)[2] <= maxw or not cur:
            cur = c
        else:
            out.append(cur); cur = w
    if cur:
        out.append(cur)
    return out[:2]


def render(label, data, day_str, league_key):
    W = 1760
    C = [110, 740, 330, 250, 330]
    assert sum(C) == W
    H_T, H_H, H_R = 110, 104, 96
    H = H_T + H_H + H_R * len(data)        # JAMI/izoh yo'q, bo'sh joy yo'q
    img = Image.new("RGB", (W, H), BG_CREAM)
    d = ImageDraw.Draw(img)
    f_title, f_h = _font(36, bold=True), _font(25, bold=True)
    f_row, f_nm = _font(28, bold=True), _font(26, bold=True)
    f_n, f_nb = _font(21), _font(21, bold=True)

    _draw_cell(d, 0, 0, W, H_T, bg=GREEN_HEADER)
    _center(d, f"AKSIYA JADVALI — {label}  ·  {day_str}", 0, 0, W, H_T, f_title, WHITE)

    y = H_T
    x = 0
    for lines, w in zip([["O'rin"], ["Agent va hudud"], ["Bugungi savdo"],
                         ["Aksiya", "(dona)"], ["Mukofot", "(so'm)"]], C):
        _hdr(d, x, y, w, H_H, lines, f_h)
        x += w
    y += H_H

    for i, it in enumerate(data, 1):
        bg = it["bg"]        # eski rang qoidasi
        cells = [str(i), None, _fmt_int(it["sales"]), str(it["units"]),
                 f"{_fmt_int(it['bonus'])} so'm"]
        x = 0
        for val, w in zip(cells, C):
            _draw_cell(d, x, y, w, H_R, bg=bg)
            if val is None:
                lines = _wrap(it["name"], f_nm, w - 28)
                lh = f_nm.getbbox("Ag")[3] - f_nm.getbbox("Ag")[1]
                yy = y + (H_R - (lh * len(lines) + 4 * (len(lines) - 1))) // 2
                for ln in lines:
                    bb = f_nm.getbbox(ln)
                    d.text((x + 14, yy - bb[1]), ln, font=f_nm, fill=TEXT_DARK)
                    yy += lh + 4
            else:
                _center(d, val, x, y, w, H_R, f_row, TEXT_DARK)
            x += w
        y += H_R

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


print("TEKSHIRUV (egasi bergan misollar):")
if not verify():
    sys.exit("❌ misollar mos kelmadi")
agents, orders, day = load()
import datetime as dt
day_str = dt.date.fromisoformat(day).strftime("%d.%m.%Y")
rows, amb = compute(agents, orders)
print(f"\nSana: {day}  ·  {len(orders)} buyurtma  ·  {len(agents)} faol agent")
if amb:
    print(f"⚠️  Bitta do'konda turli agentlar: {len(amb)} ta → {list(amb)[:5]}")
else:
    print("Do'kon↔agent noaniqligi: yo'q")
for cat, key, label in (("city", "shahar", "SHAHAR"), ("region", "viloyat", "VILOYAT")):
    data = rows[cat]
    out = HERE / f"namuna-aksiya-tasdiqlangan-{key}.png"
    out.write_bytes(render(label, data, day_str, key))
    print(f"{out}  ·  {len(data)} agent  ·  {sum(v['units'] for v in data)} aksiya  "
          f"·  {sum(v['bonus'] for v in data)} so'm")
