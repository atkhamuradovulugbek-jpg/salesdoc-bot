"""
aksiya_jadval.py — SalesDoc Monitor: kunlik AKSIYA umumiy jadvali (rasm).

2026-10-08 (Asia/Tashkent) dan boshlab 20:00 guruh hisobotida eski umumiy
BALL jadvali O'RNIGA yuboriladi (bot.py → send_agent_cards_to_group).
Individual agent kartochkalari o'zgarmaydi. Nazorat botiga aloqasi yo'q.

Qoida (egasi 2026-10-07 da tasdiqlagan):
  - bitta DO'KONning bitta KUNidagi yaroqli buyurtmalari (status 1,2,3 —
    NEW, SHIPPED/OTGRUZHEN, DELIVERED), har biri bir marta, qaytim
    ayirilgandan keyin AVVAL yig'iladi;
  - aksiya = floor(max(sof_jami, 0) / 300 000) — faqat to'liq bloklar;
  - turli do'kon / turli kun birlashmaydi, qoldiq ertaga o'tmaydi;
  - qaytim asl buyurtmadan, asl savdo kunidan ayiriladi (`orders` da
    total_returns asl buyurtma qatorida, asl `date` bilan turadi);
  - agent aksiyasi = uning do'kon-kun bloklari yig'indisi.

Mukofot — aniq kasr bilan ko'paytiriladi, faqat OXIRIDA bir marta so'mga
yaxlitlanadi:
  shahar:  n<10 → 0 · 10–14 → n×5 000 · 15+ → n×100 000/15
  viloyat: n<10 → 0 · 10–14 → n×4 000 · 15+ → n×80 000/15

Dizayn: faqat sarlavha/sana + jadval (O'rin · Agent va hudud · Bugungi
savdo · Aksiya (dona) · Mukofot (so'm)). Qator rangi — eski savdo/kunlik
reja qoidasi (`_ball_for_pct`), mukofotga qarab EMAS. Ball/Rang ustuni,
JAMI, footer, formula yo'q.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from fractions import Fraction
from io import BytesIO
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

from db import get_conn
from image_reports import (
    BG_CREAM,
    GREEN_HEADER,
    TEXT_DARK,
    WHITE,
    _ball_for_pct,
    _draw_cell,
    _fmt_int,
    _font,
)
from reports import DEFAULT_CITY_DAILY_PLAN, DEFAULT_REGION_DAILY_PLAN, classify_agent

TZ = ZoneInfo("Asia/Tashkent")

# Shu Toshkent sanasidan boshlab Ball jadvali o'rniga Aksiya jadvali
START_DATE = date(2026, 10, 8)

BLOCK_SUM = 300_000
VALID_STATUSES = (1, 2, 3)  # NEW · SHIPPED/OTGRUZHEN · DELIVERED; 4 = to'liq vazvrat

# (min_n, bitta aksiya stavkasi) — eng yuqori mos pog'ona ishlaydi; 10 dan past → 0
REWARD_TIERS = {
    "city": [(10, Fraction(5_000)), (15, Fraction(100_000, 15))],
    "region": [(10, Fraction(4_000)), (15, Fraction(80_000, 15))],
}

LABELS = {"city": "SHAHAR", "region": "VILOYAT"}
DAILY_PLAN = {"city": DEFAULT_CITY_DAILY_PLAN, "region": DEFAULT_REGION_DAILY_PLAN}


# ------------------------------------------------------------------
# Sana / faollashish
# ------------------------------------------------------------------

def tashkent_today(now: Optional[datetime] = None) -> date:
    """Toshkent bo'yicha bugungi sana (server soat mintaqasidan qat'i nazar)."""
    return (now or datetime.now(TZ)).astimezone(TZ).date()


def is_active(day: date) -> bool:
    return day >= START_DATE


# ------------------------------------------------------------------
# Hisob
# ------------------------------------------------------------------

def units_for_shop_day(net_total: float) -> int:
    """Do'konning bir kunlik JAMI sof summasidan to'liq 300 000 bloklar soni."""
    net = round(net_total, 2)  # float yig'indi shovqini (299999.9999…) uchun
    if net <= 0:
        return 0
    return int(net // BLOCK_SUM)


def agent_units(orders: Iterable[dict]) -> dict[str, int]:
    """Buyurtmalardan agent → aksiya soni.

    Har buyurtma: {"id", "agent", "shop", "day", "status", "total", "returns"}.
    Bir xil `id` ikki marta kelsa — bir marta (oxirgisi) sanaladi."""
    by_id: dict = {}
    for i, o in enumerate(orders):
        by_id[o.get("id", ("_", i))] = o

    blocks: dict[tuple, float] = defaultdict(float)
    for oid, o in by_id.items():
        if o.get("status") not in VALID_STATUSES:
            continue
        # Do'koni noma'lum buyurtma boshqalar bilan birlashmaydi
        shop = o.get("shop") or ("_order", oid)
        net = float(o.get("total") or 0) - float(o.get("returns") or 0)
        blocks[(o.get("agent"), shop, o.get("day"))] += net

    units: dict[str, int] = defaultdict(int)
    for (agent, _shop, _day), net in blocks.items():
        units[agent] += units_for_shop_day(net)
    return dict(units)


def reward(units: int, category: str) -> int:
    """Kunlik mukofot (so'm). Aniq kasr, yaxlitlash faqat oxirida, bir marta."""
    rate: Optional[Fraction] = None
    for min_n, r in REWARD_TIERS[category]:
        if units >= min_n:
            rate = r
    if rate is None:
        return 0
    total = rate * units
    return int(total + Fraction(1, 2))  # eng yaqin so'm (0.5 yuqoriga)


def compute_items(category: str, day: date) -> list[dict] | None:
    """Faol (`active='Y'`) agentlar, liga bo'yicha, savdo kamayish tartibida."""
    with get_conn() as conn:
        agents = conn.execute(
            "SELECT sd_id, name FROM agents WHERE active='Y'"
        ).fetchall()
        rows = conn.execute(
            """
            SELECT sd_id, agent_sd_id, client_sd_id, date, status,
                   total_after_discount, total_returns
            FROM orders
            WHERE date = ? AND status IN (1,2,3)
            """,
            (day.isoformat(),),
        ).fetchall()

    orders = [
        {
            "id": r["sd_id"],
            "agent": r["agent_sd_id"],
            "shop": r["client_sd_id"],
            "day": r["date"],
            "status": r["status"],
            "total": float(r["total_after_discount"] or 0),
            "returns": float(r["total_returns"] or 0),
        }
        for r in rows
    ]
    units = agent_units(orders)
    sales: dict[str, float] = defaultdict(float)
    for o in orders:
        sales[o["agent"]] += o["total"] - o["returns"]

    plan = DAILY_PLAN[category]
    items: list[dict] = []
    for a in agents:
        if classify_agent(a["name"]) != category:
            continue
        s = sales.get(a["sd_id"], 0.0)
        n = units.get(a["sd_id"], 0)
        _, _, bg = _ball_for_pct((s / plan * 100) if plan > 0 else 0)
        items.append({
            "name": a["name"],
            "sales": s,
            "units": n,
            "bonus": reward(n, category),
            "bg": bg,
        })

    if not items:
        return None
    items.sort(key=lambda x: (-x["sales"], x["name"]))
    return items


# ------------------------------------------------------------------
# Rasm
# ------------------------------------------------------------------

W = 1760
COLS = [110, 740, 330, 250, 330]
H_TITLE, H_HEAD, H_ROW = 110, 104, 96
NAME_SIZE, NAME_MIN_SIZE, NAME_PAD = 26, 16, 14


def _center(d, text, x, y, w, h, f, fill):
    bb = f.getbbox(text)
    d.text((x + (w - (bb[2] - bb[0])) // 2 - bb[0],
            y + (h - (bb[3] - bb[1])) // 2 - bb[1]), text, font=f, fill=fill)


def _head(d, x, y, w, h, lines, f):
    _draw_cell(d, x, y, w, h, bg=GREEN_HEADER)
    lh = f.getbbox("Ag")[3] - f.getbbox("Ag")[1]
    yy = y + (h - (lh * len(lines) + 6 * (len(lines) - 1))) // 2
    for ln in lines:
        bb = f.getbbox(ln)
        d.text((x + (w - (bb[2] - bb[0])) // 2 - bb[0], yy - bb[1]), ln, font=f, fill=WHITE)
        yy += lh + 6


def _wrap(text, f, max_w) -> list[str]:
    """So'z bo'yicha bo'lish. Hech bir so'z TASHLANMAYDI."""
    if f.getbbox(text)[2] <= max_w:
        return [text]
    out, cur = [], ""
    for word in text.split():
        cand = (cur + " " + word).strip()
        if f.getbbox(cand)[2] <= max_w or not cur:
            cur = cand
        else:
            out.append(cur)
            cur = word
    if cur:
        out.append(cur)
    return out


def _fit_name(text: str, max_w: int, max_lines: int = 2):
    """To'liq ism va hudud: ko'pi 2 qator; sig'masa shrift kichrayadi, kesilmaydi."""
    size = NAME_SIZE
    while True:
        f = _font(size, bold=True)
        lines = _wrap(text, f, max_w)
        fits = len(lines) <= max_lines and all(f.getbbox(ln)[2] <= max_w for ln in lines)
        if fits or size <= NAME_MIN_SIZE:
            return f, lines
        size -= 1


def render_items(items: list[dict], category: str, day: date) -> bytes:
    H = H_TITLE + H_HEAD + H_ROW * len(items)  # JAMI/footer yo'q
    img = Image.new("RGB", (W, H), BG_CREAM)
    d = ImageDraw.Draw(img)
    f_title, f_head, f_row = _font(36, bold=True), _font(25, bold=True), _font(28, bold=True)

    _draw_cell(d, 0, 0, W, H_TITLE, bg=GREEN_HEADER)
    _center(d, f"AKSIYA JADVALI — {LABELS[category]}  ·  {day.strftime('%d.%m.%Y')}",
            0, 0, W, H_TITLE, f_title, WHITE)

    y, x = H_TITLE, 0
    for lines, w in zip([["O'rin"], ["Agent va hudud"], ["Bugungi savdo"],
                         ["Aksiya", "(dona)"], ["Mukofot", "(so'm)"]], COLS):
        _head(d, x, y, w, H_HEAD, lines, f_head)
        x += w
    y += H_HEAD

    for i, it in enumerate(items, 1):
        bg = it["bg"]
        cells = [str(i), None, _fmt_int(it["sales"]), str(it["units"]),
                 f"{_fmt_int(it['bonus'])} so'm"]
        x = 0
        for val, w in zip(cells, COLS):
            _draw_cell(d, x, y, w, H_ROW, bg=bg)
            if val is None:
                f_nm, lines = _fit_name(it["name"], w - 2 * NAME_PAD)
                lh = f_nm.getbbox("Ag")[3] - f_nm.getbbox("Ag")[1]
                yy = y + (H_ROW - (lh * len(lines) + 4 * (len(lines) - 1))) // 2
                for ln in lines:
                    bb = f_nm.getbbox(ln)
                    d.text((x + NAME_PAD, yy - bb[1]), ln, font=f_nm, fill=TEXT_DARK)
                    yy += lh + 4
            else:
                _center(d, val, x, y, w, H_ROW, f_row, TEXT_DARK)
            x += w
        y += H_ROW

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_aksiya_table(category: str, day: date) -> Optional[bytes]:
    items = compute_items(category, day)
    if not items:
        return None
    return render_items(items, category, day)
