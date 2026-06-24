"""
image_reports.py — Pillow yordamida agent kartochkasi va ball jadvali rasmlarini yaratadi.
Qaytaradi: PNG bytes (Telegram'ga `send_photo` bilan yuborish uchun).

Ikki funksiya:
  render_agent_card(agent_sd_id)  -> bytes | None    (1-surat ko'rinishi)
  render_ball_table(category)     -> bytes | None    (2-surat ko'rinishi)
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from io import BytesIO
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from db import get_conn
from reports import (
    DEFAULT_CITY_DAILY_PLAN,
    DEFAULT_CITY_SALES_PLAN,
    DEFAULT_REGION_DAILY_PLAN,
    DEFAULT_REGION_SALES_PLAN,
    DEFAULT_VISIT_PLAN,
    STOCK_AVG_DAYS,
    _calc_stock_days,
    classify_agent,
    workdays_in_month,
    workdays_passed,
    workdays_remaining,
)


# ------------------------------------------------------------------
# Ranglar (suratdagi dizaynga mos)
# ------------------------------------------------------------------

BG_CREAM = (250, 246, 224)          # umumiy fon — krem
GREEN_HEADER = (47, 84, 56)         # to'q yashil — sarlavha
GREEN_HEADER_LIGHT = (90, 120, 90)  # yashil tekst ustun bo'limi (Agent, Iyun oyi, %, Izoh)
GREEN_OK_BG = (90, 180, 110)        # yashil — 100%+
RED_BAD_BG = (220, 40, 50)          # qizil — past holat
YELLOW_MID_BG = (240, 195, 75)      # sariq — o'rta holat (vizit jadvalida)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
BORDER_GRAY = (180, 170, 130)       # jadval chiziqlari
TEXT_DARK = (35, 35, 35)
LIGHT_ROW = (252, 250, 232)         # iliq oq qator
GREEN_CELL_TEXT = WHITE


# ------------------------------------------------------------------
# Shrift yuklash (Windows + Linux/Railway fallback)
# ------------------------------------------------------------------

_FONT_CANDIDATES_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/calibri.ttf",
]
_FONT_CANDIDATES_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/calibrib.ttf",
]


import logging as _logging

_logger = _logging.getLogger(__name__)
_FONT_WARNED = False


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    paths = _FONT_CANDIDATES_BOLD if bold else _FONT_CANDIDATES_REGULAR
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    # Hech qaysi TTF topilmadi — bu Railway'da shrift o'rnatilmaganini bildiradi.
    global _FONT_WARNED
    if not _FONT_WARNED:
        _logger.error(
            "TTF SHRIFT TOPILMADI! Rasm matni mitti chiqadi. "
            "Dockerfile'da 'fonts-dejavu-core' o'rnatilganini tekshiring."
        )
        _FONT_WARNED = True
    # O'lchamga bo'ysunadigan zaxira (Pillow 10+ load_default(size) ni qo'llab-quvvatlaydi)
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


# ------------------------------------------------------------------
# Formatlash
# ------------------------------------------------------------------

def _fmt_money(amount: float) -> str:
    try:
        return f"{int(round(amount)):,}".replace(",", " ") + " so'm"
    except Exception:
        return "0 so'm"


def _fmt_int(value: float | int) -> str:
    try:
        return f"{int(round(value)):,}".replace(",", " ")
    except Exception:
        return "0"


MONTH_UZ = ["", "YANVAR", "FEVRAL", "MART", "APREL", "MAY", "IYUN",
            "IYUL", "AVGUST", "SENTYABR", "OKTYABR", "NOYABR", "DEKABR"]


# ------------------------------------------------------------------
# Yordamchi: matnni wraplab chizish
# ------------------------------------------------------------------

def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Matnni `max_width` ga sig'adigan satrlarga bo'lib qaytaradi."""
    words = text.split(" ")
    lines: list[str] = []
    cur = ""
    for w in words:
        candidate = (cur + " " + w).strip()
        bbox = font.getbbox(candidate)
        width = bbox[2] - bbox[0]
        if width <= max_width:
            cur = candidate
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    max_width: int,
    font: ImageFont.FreeTypeFont,
    fill=TEXT_DARK,
    line_spacing: int = 4,
) -> int:
    """Wraplangan matnni chizadi. Yakuniy y-koordinatani qaytaradi."""
    lines = _wrap_text(text, font, max_width)
    ascent, descent = font.getmetrics()
    line_h = ascent + descent + line_spacing
    cur_y = y
    for line in lines:
        draw.text((x, cur_y), line, font=font, fill=fill)
        cur_y += line_h
    return cur_y


def _text_size(text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _draw_centered_text(draw, text, x, y, w, h, font, fill):
    tw, th = _text_size(text, font)
    tx = x + (w - tw) // 2
    ty = y + (h - th) // 2 - 2
    draw.text((tx, ty), text, font=font, fill=fill)


def _draw_centered_fit(draw, text, x, y, w, h, size, fill, bold=True,
                       min_size: int = 16, pad: int = 16):
    """Matnni katakka markazlab chizadi. Agar sig'masa — shriftni
    avtomatik kichraytiradi (hech qachon katak chetidan oshib ketmaydi)."""
    s = size
    font = _font(s, bold=bold)
    tw = font.getbbox(text)[2] - font.getbbox(text)[0]
    while tw > (w - pad) and s > min_size:
        s -= 1
        font = _font(s, bold=bold)
        tw = font.getbbox(text)[2] - font.getbbox(text)[0]
    _draw_centered_text(draw, text, x, y, w, h, font, fill)


def _draw_cell(draw, x, y, w, h, bg=None, border=BORDER_GRAY, border_w: int = 2):
    if bg is not None:
        draw.rectangle([x, y, x + w, y + h], fill=bg)
    if border is not None:
        draw.rectangle([x, y, x + w, y + h], outline=border, width=border_w)


# ------------------------------------------------------------------
# Status matnlari (suratdagi izohlar uchun)
# ------------------------------------------------------------------

def _remaining_suffix(remaining_wd: int) -> str:
    if remaining_wd == 5:
        return "5 ish kuni qoldi. Harakatni kuchaytirish kerak!"
    if remaining_wd == 4:
        return "4 ish kuni qoldi. Sezilarli harakat kerak!"
    if remaining_wd == 3:
        return "3 ish kuni qoldi. Juda qiyin!"
    if remaining_wd == 2:
        return "2 ish kuni qoldi. Katta harakat kerak!"
    if remaining_wd == 1:
        return "1 ish kuni qoldi!"
    if remaining_wd == 0:
        return "Oy tugadi!"
    return "Oylik ish jarayoni davom etmoqda."


def _bajardi_text(pct: float, remaining_wd: int = 15) -> str:
    if pct < 70:
        status = "QIZIL HOLAT — Oylik plan bajarilishi juda past. Savdo faolligini keskin oshirish zarur."
    elif pct < 90:
        status = "SARIQ HOLAT — Plan asta-sekin bajarilmoqda, lekin tempni sezilarli oshirish kerak."
    elif pct < 100:
        status = "YASHIL HOLAT — Plan bajarilish chizig'iga yaqin. Yakuniy harakatlar bilan 100% mumkin."
    elif pct < 110:
        status = "TABRIKLAYMIZ — Oylik plan bajarildi! Shu tempni saqlab yuqori natijaga erishing."
    else:
        status = "SUPER NATIJA — Oylik plan oshirib bajarildi! Bu juda kuchli ko'rsatkich."
    return status + " " + _remaining_suffix(remaining_wd)


def _prognoz_text(pct: float) -> str:
    p = round(pct)
    if pct < 70:
        return (f"PROGNOZ XAVFLI — Hozirgi temp bilan plan atigi {p}% darajada "
                "yopilishi mumkin. Kunlik savdoni tezkor oshirish kerak.")
    if pct < 90:
        return (f"PROGNOZ PAST — Hozirgi temp bilan plan taxminan {p}% darajada "
                "bajarilishi mumkin. Tempni sezilarli oshirish zarur.")
    if pct < 100:
        return (f"PROGNOZ CHEGARADA — Hozirgi temp bilan plan {p}% atrofida "
                "bajarilishi mumkin. Qo'shimcha harakat kerak.")
    if pct < 110:
        return (f"PROGNOZ YAXSHI — Hozirgi temp bilan plan {p}% darajada "
                "bajarilishi mumkin. Tempni saqlab qolish kifoya.")
    return (f"SUPER PROGNOZ — Hozirgi temp bilan oy oxirida plan {p}% darajada "
            "bajarilishi mumkin! Bu juda kuchli ko'rsatkich.")


def _kunlik_text(pct: float, remaining_wd: int = 15) -> str:
    if pct < 70:
        status = "QIZIL HOLAT — Bugungi kunlik plan juda past darajada bajarildi."
    elif pct < 90:
        status = "SARIQ HOLAT — Kunlik plan to'liq bajarilmadi. Faollikni oshirish kerak."
    elif pct < 100:
        status = "YASHIL HOLAT — Kunlik planga yaqin. Biroz qo'shimcha harakat kerak."
    elif pct < 110:
        status = "TABRIKLAYMIZ — Bugungi kunlik plan bajarildi! Shu tempda davom eting."
    else:
        status = "SUPER NATIJA — Kunlik plan oshirib bajarildi! Bu kuchli savdo ko'rsatkichi."
    return status + " " + _remaining_suffix(remaining_wd)


def _bg_for_pct(pct: float, has_target: bool = True) -> tuple[int, int, int]:
    if not has_target:
        return LIGHT_ROW
    if pct >= 100:
        return GREEN_OK_BG
    if pct >= 70:
        return YELLOW_MID_BG
    return RED_BAD_BG


# ------------------------------------------------------------------
# AGENT METRIKLARINI BAZADAN OLISH (reports.py logikasi bilan bir xil)
# ------------------------------------------------------------------

def _compute_metrics(agent_sd_id: str) -> dict | None:
    today = date.today()
    year, month = today.year, today.month
    month_first = f"{year:04d}-{month:02d}-01"
    today_iso = today.isoformat()

    with get_conn() as conn:
        agent = conn.execute(
            "SELECT sd_id, name FROM agents WHERE sd_id=?", (agent_sd_id,)
        ).fetchone()
        if not agent:
            return None

        plan_row = conn.execute(
            "SELECT sales_plan, visit_plan FROM agent_plans WHERE agent_sd_id=?",
            (agent_sd_id,),
        ).fetchone()
        sales_plan = float(plan_row["sales_plan"] or 0) if plan_row else 0
        visit_plan = int(plan_row["visit_plan"] or 0) if plan_row else 0

        sales_row = conn.execute("""
            SELECT COALESCE(SUM(total_after_discount), 0) AS s
            FROM orders WHERE agent_sd_id=? AND date >= ? AND date <= ? AND status IN (1,2,3)
        """, (agent_sd_id, month_first, today_iso)).fetchone()
        sales_done = float(sales_row["s"] or 0)

        today_row = conn.execute("""
            SELECT COALESCE(SUM(total_after_discount), 0) AS s
            FROM orders WHERE agent_sd_id=? AND date=? AND status IN (1,2,3)
        """, (agent_sd_id, today_iso)).fetchone()
        today_sales = float(today_row["s"] or 0)

        visit_row = conn.execute("""
            SELECT COUNT(*) AS c FROM visits
            WHERE agent_sd_id=? AND date >= ? AND date <= ? AND visited=1
        """, (agent_sd_id, month_first, today_iso)).fetchone()
        visits_done = int(visit_row["c"] or 0)

        today_visit_row = conn.execute("""
            SELECT COUNT(*) AS c FROM visits
            WHERE agent_sd_id=? AND date=? AND visited=1
        """, (agent_sd_id, today_iso)).fetchone()
        today_visits = int(today_visit_row["c"] or 0)

    kind = classify_agent(agent["name"])
    if sales_plan <= 0:
        if kind == "city":
            sales_plan = DEFAULT_CITY_SALES_PLAN
        elif kind == "region":
            sales_plan = DEFAULT_REGION_SALES_PLAN
    if visit_plan <= 0:
        visit_plan = DEFAULT_VISIT_PLAN

    total_wd = workdays_in_month(year, month)
    passed_wd = workdays_passed(year, month, today)
    remaining_wd = workdays_remaining(year, month, today)

    plan_pct = (sales_done / sales_plan * 100) if sales_plan > 0 else 0
    plan_remaining = max(sales_plan - sales_done, 0)
    daily_avg = sales_done / passed_wd if passed_wd > 0 else 0
    prognoz = daily_avg * total_wd
    prognoz_pct = (prognoz / sales_plan * 100) if sales_plan > 0 else 0
    daily_required = (plan_remaining / remaining_wd) if remaining_wd > 0 else 0
    daily_pct = (today_sales / daily_required * 100) if daily_required > 0 else 0

    visit_remaining = max(visit_plan - visits_done, 0)
    visit_daily_required = (visit_remaining / remaining_wd) if remaining_wd > 0 else 0

    return {
        "name": agent["name"],
        "today": today,
        "month": month,
        "year": year,
        "sales_plan": sales_plan,
        "sales_done": sales_done,
        "plan_pct": plan_pct,
        "plan_remaining": plan_remaining,
        "prognoz": prognoz,
        "prognoz_pct": prognoz_pct,
        "daily_required": daily_required,
        "today_sales": today_sales,
        "daily_pct": daily_pct,
        "total_wd": total_wd,
        "passed_wd": passed_wd,
        "remaining_wd": remaining_wd,
        "visit_plan": visit_plan,
        "visits_done": visits_done,
        "visit_remaining": visit_remaining,
        "visit_daily_required": visit_daily_required,
        "today_visits": today_visits,
    }


# ------------------------------------------------------------------
# AGENT KARTOCHKASI RASMI (1-surat)
# ------------------------------------------------------------------

def render_agent_card(agent_sd_id: str) -> Optional[bytes]:
    m = _compute_metrics(agent_sd_id)
    if not m:
        return None

    # O'lcham va layout
    # Ustun kengliklari — summa va % bir-biriga qo'shilib ketmasligi uchun
    # kengaytirildi (C2 va C3 ancha keng).
    C1 = 360   # Label
    C2 = 480   # Qiymat (so'm) — keng, summalar sig'sin
    C3 = 180   # foiz — keng, % sig'sin
    C4 = 620   # Izoh
    C5_LBL = 130  # Ish kuni label
    C5_VAL = 80   # Ish kuni qiymat
    W = C1 + C2 + C3 + C4 + C5_LBL + C5_VAL

    # Row balandliklari (katta matn + ko'proq joy)
    H_HEADER = 64
    H_PLAN = 64
    H_BAJARDI = 200
    H_QOLDIQ = 64
    H_PROGNOZ = 200
    H_KUNLIK_KER = 64
    H_KUNLIK_BAJ = 200

    main_height = (H_HEADER + H_PLAN + H_BAJARDI + H_QOLDIQ +
                   H_PROGNOZ + H_KUNLIK_KER + H_KUNLIK_BAJ)

    # Pastida vizit jadvali + sana
    GAP = 36
    H_VISIT_ROW = 58
    visit_rows = 5
    H_VISIT = H_VISIT_ROW * visit_rows
    H_SANA = 44
    H = main_height + GAP + H_VISIT + H_SANA + 24

    img = Image.new("RGB", (W, H), BG_CREAM)
    draw = ImageDraw.Draw(img)

    # ----- Fontlar (hammasi BOLD — jirniy, ~2x katta) -----
    f_h_lbl = _font(30, bold=True)         # Header label (AGENT, IYUN OYI)
    f_h_val = _font(30, bold=True)         # Agent nomi
    f_lbl = _font(28, bold=True)           # row labels (chap ustun)
    f_money = _font(38, bold=True)         # asosiy summalar
    f_money_small = _font(31, bold=True)
    f_pct = _font(46, bold=True)
    f_note = _font(28, bold=True)          # Izoh matni — QALIN
    f_kun_lbl = _font(23, bold=True)
    f_kun_val = _font(34, bold=True)

    # ============================================================
    # ROW 0 — Header (AGENT | nomi | (empty) | IYUN OYI)
    # ============================================================
    y = 0
    x = 0
    # ustun 1: AGENT
    _draw_cell(draw, x, y, C1, H_HEADER, bg=BG_CREAM)
    _draw_centered_text(draw, "AGENT", x, y, C1, H_HEADER, f_h_lbl, GREEN_HEADER_LIGHT)
    x += C1
    # ustun 2 (Agent nomi) — keng (C2 + C3) ni qamrab oladi
    span_w = C2 + C3
    _draw_cell(draw, x, y, span_w, H_HEADER, bg=BG_CREAM)
    _draw_centered_text(draw, m["name"], x, y, span_w, H_HEADER,
                        f_h_val, GREEN_HEADER_LIGHT)
    x += span_w
    # ustun 3 (izoh ustuni boshi — bo'sh)
    _draw_cell(draw, x, y, C4, H_HEADER, bg=BG_CREAM)
    x += C4
    # ustun 4 (IYUN OYI)
    span_w = C5_LBL + C5_VAL
    _draw_cell(draw, x, y, span_w, H_HEADER, bg=BG_CREAM)
    _draw_centered_text(draw, f"{MONTH_UZ[m['month']]} OYI", x, y, span_w, H_HEADER,
                        f_h_lbl, GREEN_HEADER_LIGHT)
    y += H_HEADER

    # ============================================================
    # ROW 1 — OYLIK PLAN: | summa (yashil) | % (yashil) | Izoh (yashil) | ISH KUNI | 26
    # ============================================================
    x = 0
    _draw_cell(draw, x, y, C1, H_PLAN, bg=GREEN_HEADER)
    _draw_centered_text(draw, "OYLIK PLAN:", x, y, C1, H_PLAN, f_lbl, WHITE)
    x += C1
    _draw_cell(draw, x, y, C2, H_PLAN, bg=GREEN_HEADER)
    _draw_centered_fit(draw, _fmt_money(m["sales_plan"]),
                       x, y, C2, H_PLAN, 38, WHITE)
    x += C2
    _draw_cell(draw, x, y, C3, H_PLAN, bg=GREEN_HEADER)
    _draw_centered_text(draw, "%", x, y, C3, H_PLAN, f_lbl, WHITE)
    x += C3
    _draw_cell(draw, x, y, C4, H_PLAN, bg=GREEN_HEADER)
    _draw_centered_text(draw, "Izoh", x, y, C4, H_PLAN, f_lbl, WHITE)
    x += C4
    _draw_cell(draw, x, y, C5_LBL, H_PLAN, bg=GREEN_HEADER)
    _draw_centered_text(draw, "ISH KUNI", x, y, C5_LBL, H_PLAN, f_kun_lbl, WHITE)
    x += C5_LBL
    _draw_cell(draw, x, y, C5_VAL, H_PLAN, bg=GREEN_HEADER)
    _draw_centered_text(draw, str(m["total_wd"]), x, y, C5_VAL, H_PLAN, f_kun_val, WHITE)
    y += H_PLAN

    # ============================================================
    # ROW 2 — PLAN BAJARDI: | summa | % | Izoh-A (PLAN BAJARDI+QOLDIQ) | ISHLAB BO'LINDI | 11
    # ============================================================
    bajardi_bg = _bg_for_pct(m["plan_pct"])
    bajardi_text_color = WHITE
    x = 0
    _draw_cell(draw, x, y, C1, H_BAJARDI, bg=LIGHT_ROW)
    _draw_centered_text(draw, "PLAN BAJARDI:", x, y, C1, H_BAJARDI, f_lbl, TEXT_DARK)
    x += C1
    _draw_cell(draw, x, y, C2, H_BAJARDI, bg=bajardi_bg)
    _draw_centered_fit(draw, _fmt_money(m["sales_done"]),
                       x, y, C2, H_BAJARDI, 38, bajardi_text_color)
    x += C2
    _draw_cell(draw, x, y, C3, H_BAJARDI, bg=bajardi_bg)
    _draw_centered_fit(draw, f"{m['plan_pct']:.0f}%",
                       x, y, C3, H_BAJARDI, 46, bajardi_text_color)
    x += C3
    # Izoh ustuni — PLAN BAJARDI + PLAN QOLDIQ ikkisini qamrab oladi
    note_h = H_BAJARDI + H_QOLDIQ
    _draw_cell(draw, x, y, C4, note_h, bg=LIGHT_ROW)
    _draw_wrapped(draw, _bajardi_text(m["plan_pct"], m["remaining_wd"]),
                  x + 12, y + 10, C4 - 24, f_note, fill=TEXT_DARK, line_spacing=12)
    x += C4
    # ISHLAB BO'LINDI label
    _draw_cell(draw, x, y, C5_LBL, H_BAJARDI, bg=BG_CREAM)
    _draw_centered_text(draw, "ISHLAB", x, y, C5_LBL, H_BAJARDI // 2,
                        f_kun_lbl, TEXT_DARK)
    _draw_centered_text(draw, "BO'LINDI", x, y + H_BAJARDI // 2, C5_LBL, H_BAJARDI // 2,
                        f_kun_lbl, TEXT_DARK)
    x += C5_LBL
    _draw_cell(draw, x, y, C5_VAL, H_BAJARDI, bg=BG_CREAM)
    _draw_centered_text(draw, str(m["passed_wd"]),
                        x, y, C5_VAL, H_BAJARDI, f_kun_val, TEXT_DARK)
    y += H_BAJARDI

    # ============================================================
    # ROW 3 — PLAN QOLDIQ: | summa | (bo'sh) | (note davomi yuqorida) | ISH KUNI QOLDI | 15
    # ============================================================
    x = 0
    _draw_cell(draw, x, y, C1, H_QOLDIQ, bg=LIGHT_ROW)
    _draw_centered_fit(draw, "PLAN QOLDIQ (BAJARISH KERAK):",
                       x, y, C1, H_QOLDIQ, 24, TEXT_DARK)
    x += C1
    _draw_cell(draw, x, y, C2, H_QOLDIQ, bg=LIGHT_ROW)
    _draw_centered_fit(draw, _fmt_money(m["plan_remaining"]),
                       x, y, C2, H_QOLDIQ, 34, TEXT_DARK)
    x += C2
    _draw_cell(draw, x, y, C3, H_QOLDIQ, bg=LIGHT_ROW)
    x += C3
    # Izoh ustuni — yuqorida (merge bilan) chizilgan, lekin pastki chiziq uchun border
    # Pastki chegarani qo'shamiz:
    draw.line([x, y + H_QOLDIQ - 1, x + C4, y + H_QOLDIQ - 1], fill=BORDER_GRAY, width=2)
    x += C4
    _draw_cell(draw, x, y, C5_LBL, H_QOLDIQ, bg=BG_CREAM)
    # 2 satrli: "ISH KUNI" / "QOLDI"
    _draw_centered_text(draw, "ISH KUNI", x, y, C5_LBL, H_QOLDIQ // 2,
                        _font(18, bold=True), TEXT_DARK)
    _draw_centered_text(draw, "QOLDI", x, y + H_QOLDIQ // 2, C5_LBL, H_QOLDIQ // 2,
                        _font(18, bold=True), TEXT_DARK)
    x += C5_LBL
    _draw_cell(draw, x, y, C5_VAL, H_QOLDIQ, bg=BG_CREAM)
    _draw_centered_text(draw, str(m["remaining_wd"]),
                        x, y, C5_VAL, H_QOLDIQ, f_kun_val, TEXT_DARK)
    y += H_QOLDIQ

    # ============================================================
    # ROW 4 — PLAN PROGNOZ: | summa (yashil) | % | Izoh-B (PROGNOZ + KUNLIK_KER)
    # ============================================================
    prognoz_bg = _bg_for_pct(m["prognoz_pct"])
    x = 0
    _draw_cell(draw, x, y, C1, H_PROGNOZ, bg=LIGHT_ROW)
    _draw_centered_text(draw, "PLAN PROGNOZ:", x, y, C1, H_PROGNOZ, f_lbl, TEXT_DARK)
    x += C1
    _draw_cell(draw, x, y, C2, H_PROGNOZ, bg=prognoz_bg)
    _draw_centered_fit(draw, _fmt_money(m["prognoz"]),
                       x, y, C2, H_PROGNOZ, 38, WHITE)
    x += C2
    _draw_cell(draw, x, y, C3, H_PROGNOZ, bg=prognoz_bg)
    _draw_centered_fit(draw, f"{m['prognoz_pct']:.0f}%",
                       x, y, C3, H_PROGNOZ, 46, WHITE)
    x += C3
    # Note B — PROGNOZ + KUNLIK_KER merge
    note_h_b = H_PROGNOZ + H_KUNLIK_KER
    _draw_cell(draw, x, y, C4, note_h_b, bg=LIGHT_ROW)
    _draw_wrapped(draw, _prognoz_text(m["prognoz_pct"]),
                  x + 12, y + 10, C4 - 24, f_note, fill=TEXT_DARK, line_spacing=12)
    x += C4
    # O'ng tomonda (C5) — bo'sh hujayralar qo'shamiz, vertical span
    _draw_cell(draw, x, y, C5_LBL + C5_VAL, note_h_b, bg=BG_CREAM)
    y += H_PROGNOZ

    # ============================================================
    # ROW 5 — KUNLIK BAJARISH KEREAK: | summa | (bo'sh) | (note continues)
    # ============================================================
    x = 0
    _draw_cell(draw, x, y, C1, H_KUNLIK_KER, bg=LIGHT_ROW)
    _draw_centered_fit(draw, "KUNLIK BAJARISH KEREAK:",
                       x, y, C1, H_KUNLIK_KER, 24, TEXT_DARK)
    x += C1
    _draw_cell(draw, x, y, C2, H_KUNLIK_KER, bg=LIGHT_ROW)
    _draw_centered_fit(draw, _fmt_money(m["daily_required"]),
                       x, y, C2, H_KUNLIK_KER, 34, TEXT_DARK)
    x += C2
    _draw_cell(draw, x, y, C3, H_KUNLIK_KER, bg=LIGHT_ROW)
    x += C3
    # Note B davomi — pastki chegara
    draw.line([x, y + H_KUNLIK_KER - 1, x + C4, y + H_KUNLIK_KER - 1],
              fill=BORDER_GRAY, width=2)
    x += C4
    # O'ng tomonda yana
    y += H_KUNLIK_KER

    # ============================================================
    # ROW 6 — KUNLIK BAJARILDI: | summa (yashil) | % | Izoh-C
    # ============================================================
    kunlik_bg = _bg_for_pct(m["daily_pct"], has_target=m["daily_required"] > 0)
    x = 0
    _draw_cell(draw, x, y, C1, H_KUNLIK_BAJ, bg=LIGHT_ROW)
    _draw_centered_text(draw, "KUNLIK BAJARILDI:",
                        x, y, C1, H_KUNLIK_BAJ, f_lbl, TEXT_DARK)
    x += C1
    _draw_cell(draw, x, y, C2, H_KUNLIK_BAJ, bg=kunlik_bg)
    _draw_centered_fit(draw, _fmt_money(m["today_sales"]),
                       x, y, C2, H_KUNLIK_BAJ, 38,
                       WHITE if kunlik_bg != LIGHT_ROW else TEXT_DARK)
    x += C2
    _draw_cell(draw, x, y, C3, H_KUNLIK_BAJ, bg=kunlik_bg)
    pct_txt = f"{m['daily_pct']:.0f}%" if m["daily_required"] > 0 else "—"
    _draw_centered_fit(draw, pct_txt, x, y, C3, H_KUNLIK_BAJ, 46,
                       WHITE if kunlik_bg != LIGHT_ROW else TEXT_DARK)
    x += C3
    _draw_cell(draw, x, y, C4, H_KUNLIK_BAJ, bg=LIGHT_ROW)
    _draw_wrapped(draw, _kunlik_text(m["daily_pct"], m["remaining_wd"]),
                  x + 12, y + 10, C4 - 24, f_note, fill=TEXT_DARK, line_spacing=12)
    x += C4
    _draw_cell(draw, x, y, C5_LBL + C5_VAL, H_KUNLIK_BAJ, bg=BG_CREAM)
    y += H_KUNLIK_BAJ

    # ============================================================
    # VIZIT JADVALI (pastda kichik, chap tomon)
    # ============================================================
    y += GAP
    v_x = 0
    v_w_lbl = 440
    v_w_val = 260
    v_total = v_w_lbl + v_w_val
    f_v_lbl = _font(24, bold=True)
    f_v_val = _font(30, bold=True)

    visit_rows_data = [
        ("VIZIT PLAN:", str(m["visit_plan"]), GREEN_HEADER, WHITE),
        ("VIZIT BAJARILDI:", str(m["visits_done"]), LIGHT_ROW, TEXT_DARK),
        ("VIZIT QOLDI:", str(m["visit_remaining"]), LIGHT_ROW, TEXT_DARK),
        ("KUNLIK BAJARISH KEREAK:", f"{m['visit_daily_required']:.0f}", LIGHT_ROW, TEXT_DARK),
        ("KUNLIK BAJARILDI:", str(m["today_visits"]), LIGHT_ROW, TEXT_DARK),
    ]
    for label, val, bg, color in visit_rows_data:
        _draw_cell(draw, v_x, y, v_w_lbl, H_VISIT_ROW, bg=bg)
        # label chap tomonga
        bbox = f_v_lbl.getbbox(label)
        th = bbox[3] - bbox[1]
        draw.text((v_x + 10, y + (H_VISIT_ROW - th) // 2 - 2),
                  label, font=f_v_lbl, fill=color)
        _draw_cell(draw, v_x + v_w_lbl, y, v_w_val, H_VISIT_ROW, bg=bg)
        _draw_centered_text(draw, val, v_x + v_w_lbl, y, v_w_val, H_VISIT_ROW,
                            f_v_val, color)
        y += H_VISIT_ROW

    # SANA — pastda o'ng tomon
    sana_y = y - H_VISIT_ROW  # pastki vizit qator bilan bir tekisda
    sana_text = f"SANA: {m['today'].strftime('%d.%m.%Y')}"
    f_sana = _font(28, bold=True)
    draw.text((820, sana_y + 12), sana_text, font=f_sana, fill=TEXT_DARK)

    # PNG bytes ga aylantirib qaytarish
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ------------------------------------------------------------------
# BALL JADVALI RASMI (2-surat)
# ------------------------------------------------------------------

def _ball_for_pct(pct: float) -> tuple[str, int, tuple[int, int, int]]:
    """Kunlik savdo plani foiziga qarab: (marker turi, ball, fon rangi).

    Qoidalar:
      >= 150%      -> SUPER KUN     -> 4 ball (alanga)
      100-149%     -> ULTRA YASHIL  -> 3 ball (yashil + ✓)
      90-99%       -> YASHIL        -> 2 ball (yashil aylana)
      80-89%       -> SARIQ         -> 1 ball (sariq aylana)
      0-79%        -> QIZIL         -> 0 ball (qizil aylana)
    """
    if pct >= 150:
        return ("super", 4, (250, 190, 140))   # to'q sariq fon (alanga)
    if pct >= 100:
        return ("ultra", 3, (190, 235, 190))   # yashil fon + ✓
    if pct >= 90:
        return ("green", 2, (215, 245, 210))   # och yashil fon
    if pct >= 80:
        return ("yellow", 1, (255, 245, 190))  # sariq fon
    return ("red", 0, (255, 205, 205))         # qizil fon


def _compute_ball_items(category: str) -> list[dict] | None:
    if category == "city":
        daily_plan = DEFAULT_CITY_DAILY_PLAN
    else:
        daily_plan = DEFAULT_REGION_DAILY_PLAN

    today_iso = date.today().isoformat()

    with get_conn() as conn:
        rows = conn.execute("""
            SELECT a.sd_id, a.name,
                   COALESCE(SUM(o.total_after_discount), 0) AS sales
            FROM agents a
            LEFT JOIN orders o ON o.agent_sd_id = a.sd_id
                AND o.date = ? AND o.status IN (1,2,3)
            WHERE a.active = 'Y'
            GROUP BY a.sd_id
        """, (today_iso,)).fetchall()

    items: list[dict] = []
    for a in rows:
        if classify_agent(a["name"]) != category:
            continue
        sales = float(a["sales"] or 0)
        pct = (sales / daily_plan * 100) if daily_plan > 0 else 0
        color_name, ball, bg = _ball_for_pct(pct)
        items.append({
            "name": a["name"],
            "sales": sales,
            "pct": pct,
            "color": color_name,
            "ball": ball,
            "bg": bg,
        })

    if not items:
        return None
    items.sort(key=lambda x: -x["sales"])
    return items


def render_ball_table(category: str) -> Optional[bytes]:
    items = _compute_ball_items(category)
    if not items:
        return None

    # O'lcham va layout
    W = 1560
    C_ORIN = 120
    C_AGENT = 710
    C_SAVDO = 340
    C_RANG = 170
    C_BALL = 220
    assert C_ORIN + C_AGENT + C_SAVDO + C_RANG + C_BALL == W

    H_HEADER = 92
    H_ROW = 86
    H_TITLE = 110
    H = H_TITLE + H_HEADER + H_ROW * len(items) + 28

    img = Image.new("RGB", (W, H), BG_CREAM)
    draw = ImageDraw.Draw(img)

    f_title = _font(38, bold=True)
    f_h = _font(32, bold=True)
    f_row = _font(32, bold=True)
    f_orin = _font(34, bold=True)
    f_ball = _font(36, bold=True)

    # Sarlavha
    cat_label = "SHAHAR AGENTLARI" if category == "city" else "VILOYAT AGENTLARI"
    today_str = date.today().strftime("%d.%m.%Y")
    title = f"BUGUNGI BALL JADVALI — {cat_label}  ·  {today_str}"
    _draw_cell(draw, 0, 0, W, H_TITLE, bg=GREEN_HEADER)
    _draw_centered_text(draw, title, 0, 0, W, H_TITLE, f_title, WHITE)

    # Header
    y = H_TITLE
    headers = [("O'rin", C_ORIN), ("Agent", C_AGENT), ("Savdo", C_SAVDO),
               ("Rang", C_RANG), ("Ball", C_BALL)]
    x = 0
    for label, w in headers:
        _draw_cell(draw, x, y, w, H_HEADER, bg=GREEN_HEADER)
        _draw_centered_text(draw, label, x, y, w, H_HEADER, f_h, WHITE)
        x += w
    y += H_HEADER

    # Qatorlar
    for i, it in enumerate(items, start=1):
        bg = it["bg"]
        x = 0
        # O'rin
        _draw_cell(draw, x, y, C_ORIN, H_ROW, bg=bg)
        _draw_centered_text(draw, str(i), x, y, C_ORIN, H_ROW, f_orin, TEXT_DARK)
        x += C_ORIN
        # Agent nomi
        _draw_cell(draw, x, y, C_AGENT, H_ROW, bg=bg)
        bbox = f_row.getbbox(it["name"])
        th = bbox[3] - bbox[1]
        draw.text((x + 14, y + (H_ROW - th) // 2 - 2),
                  it["name"], font=f_row, fill=TEXT_DARK)
        x += C_AGENT
        # Savdo
        _draw_cell(draw, x, y, C_SAVDO, H_ROW, bg=bg)
        _draw_centered_text(draw, _fmt_int(it["sales"]),
                            x, y, C_SAVDO, H_ROW, f_row, TEXT_DARK)
        x += C_SAVDO
        # Rang (aylana)
        _draw_cell(draw, x, y, C_RANG, H_ROW, bg=bg)
        _draw_color_circle(draw, x + C_RANG // 2, y + H_ROW // 2, 26, it["color"])
        x += C_RANG
        # Ball
        _draw_cell(draw, x, y, C_BALL, H_ROW, bg=bg)
        _draw_centered_text(draw, str(it["ball"]),
                            x, y, C_BALL, H_ROW, f_ball, TEXT_DARK)
        y += H_ROW

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _draw_flame(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int):
    """SUPER KUN uchun alanga (olov) belgisi — to'q sariq + sariq."""
    outer = [
        (cx, cy - r),
        (cx + int(r * 0.85), cy + int(r * 0.25)),
        (cx + int(r * 0.45), cy + r),
        (cx - int(r * 0.45), cy + r),
        (cx - int(r * 0.85), cy + int(r * 0.25)),
    ]
    draw.polygon(outer, fill=(255, 120, 30), outline=(190, 70, 10))
    inner = [
        (cx, cy - int(r * 0.45)),
        (cx + int(r * 0.45), cy + int(r * 0.30)),
        (cx, cy + int(r * 0.75)),
        (cx - int(r * 0.45), cy + int(r * 0.30)),
    ]
    draw.polygon(inner, fill=(255, 215, 70))


def _draw_color_circle(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, marker: str):
    """Ball markerini chizadi:
    super -> alanga, ultra -> yashil aylana + ✓, green -> yashil aylana,
    yellow -> sariq aylana, red -> qizil aylana."""
    if marker == "super":
        _draw_flame(draw, cx, cy, r)
        return
    colors = {
        "ultra": (40, 170, 70),
        "green": (90, 200, 110),
        "yellow": (240, 200, 60),
        "red": (220, 50, 60),
    }
    c = colors.get(marker, (150, 150, 150))
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c, outline=(60, 60, 60), width=2)
    # ULTRA YASHIL aylana ichida ✓ belgi
    if marker == "ultra":
        draw.line([(cx - 11, cy + 2), (cx - 3, cy + 11)], fill=WHITE, width=5)
        draw.line([(cx - 3, cy + 11), (cx + 12, cy - 9)], fill=WHITE, width=5)


# ------------------------------------------------------------------
# TEZ TUGAYDIGAN MAHSULOTLAR — rasm jadval (3-surat ko'rinishi)
# ------------------------------------------------------------------

LOW_STOCK_MAX_ROWS = 30  # rasmda ko'rsatiladigan eng ko'p qator

# Qator fonlari va holat ranglari (qizil <2 kun, sariq <=5 kun)
LOW_RED_ROW = (255, 214, 214)
LOW_YELLOW_ROW = (255, 246, 210)
LOW_RED_CHIP = (224, 60, 68)
LOW_YELLOW_CHIP = (242, 202, 70)
LOW_RED_KUN = (170, 30, 40)


def _compute_low_stock_items(max_days: int = 5) -> Optional[tuple[list[dict], str]]:
    """≤ max_days kunlik qoldiq qolgan tovarlar (eng kritik birinchi).
    Qaytaradi: (items, last_updated) yoki None (agar yo'q bo'lsa).
    reports.low_stock_report bilan bir xil logika (lekin tuzilgan ma'lumot)."""
    with get_conn() as conn:
        rows = conn.execute(f"""
            SELECT
                s.product_sd_id,
                MAX(s.product_name) AS name,
                SUM(s.quantity) AS stock,
                MAX(s.updated_at) AS upd,
                COALESCE((
                    SELECT SUM(oi.quantity)
                    FROM order_items oi
                    JOIN orders o ON o.sd_id = oi.order_sd_id
                    WHERE oi.product_sd_id = s.product_sd_id
                      AND o.status IN (1, 2, 3)
                      AND o.date >= date('now', '-{STOCK_AVG_DAYS} days')
                ), 0) AS sold
            FROM stock s
            GROUP BY s.product_sd_id
        """).fetchall()

    items = []
    for r in rows:
        stock = float(r["stock"] or 0)
        sold = float(r["sold"] or 0)
        days = _calc_stock_days(stock, sold)
        if days <= max_days:
            items.append({"name": r["name"] or "—", "stock": stock, "days": days})

    if not items:
        return None
    items.sort(key=lambda x: x["days"])
    last_updated = max((r["upd"] or "" for r in rows), default="")[:16]
    return items, last_updated


def _draw_low_stock_image(all_items: list[dict], last_updated: str, max_days: int) -> bytes:
    """Tuzilgan ma'lumotdan PNG jadval chizadi (test qilsa bo'ladigan qism)."""
    total = len(all_items)
    items = all_items[:LOW_STOCK_MAX_ROWS]

    W = 1560
    C_NAME = 780
    C_QOLDIQ = 300
    C_KUN = 230
    C_HOLAT = 250
    assert C_NAME + C_QOLDIQ + C_KUN + C_HOLAT == W

    H_TITLE = 150
    H_HEADER = 92
    H_ROW_MIN = 92
    LINE_H = 46
    PAD_NAME = 18

    f_title = _font(40, bold=True)
    f_sub = _font(25, bold=False)
    f_h = _font(32, bold=True)
    f_name = _font(31, bold=True)
    f_cell = _font(32, bold=True)

    # nomlarni oldindan 2 satrga wraplab, qator balandliklarini hisoblaymiz
    prepared = []
    for it in items:
        full = _wrap_text(it["name"], f_name, C_NAME - 2 * PAD_NAME)
        if len(full) > 2:
            lines = full[:2]
            lines[1] = lines[1].rstrip() + "…"
        else:
            lines = full or [""]
        rh = max(H_ROW_MIN, len(lines) * LINE_H + 36)
        prepared.append((lines, it, rh))

    foot_h = 58 if total > len(items) else 24
    H = H_TITLE + H_HEADER + sum(rh for _, _, rh in prepared) + foot_h

    img = Image.new("RGB", (W, H), BG_CREAM)
    draw = ImageDraw.Draw(img)

    # Sarlavha (2 qator)
    _draw_cell(draw, 0, 0, W, H_TITLE, bg=GREEN_HEADER)
    _draw_centered_text(draw, "TEZ TUGAYDIGAN MAHSULOTLAR", 0, 18, W, 58, f_title, WHITE)
    sub = f"≤ {max_days} kunlik qoldiq   ·   jami {total} ta   ·   yangilangan: {last_updated or '—'}"
    _draw_centered_text(draw, sub, 0, 88, W, 46, f_sub, (212, 226, 212))

    # Header qatori
    y = H_TITLE
    for label, w, x0 in [("Tovar nomi", C_NAME, 0), ("Qoldiq", C_QOLDIQ, C_NAME),
                         ("Necha kun", C_KUN, C_NAME + C_QOLDIQ),
                         ("Holat", C_HOLAT, C_NAME + C_QOLDIQ + C_KUN)]:
        _draw_cell(draw, x0, y, w, H_HEADER, bg=GREEN_HEADER)
        _draw_centered_text(draw, label, x0, y, w, H_HEADER, f_h, WHITE)
    y += H_HEADER

    # Qatorlar
    for lines, it, rh in prepared:
        days = it["days"]
        if days < 2:
            row_bg, chip_bg, chip_tx, chip_lbl, kun_col = LOW_RED_ROW, LOW_RED_CHIP, WHITE, "Qizil", LOW_RED_KUN
        else:
            row_bg, chip_bg, chip_tx, chip_lbl, kun_col = LOW_YELLOW_ROW, LOW_YELLOW_CHIP, TEXT_DARK, "Sariq", TEXT_DARK

        # Tovar nomi (1-2 satr, vertikal markaz)
        _draw_cell(draw, 0, y, C_NAME, rh, bg=row_bg)
        ty = y + (rh - len(lines) * LINE_H) // 2
        for ln in lines:
            draw.text((PAD_NAME, ty), ln, font=f_name, fill=TEXT_DARK)
            ty += LINE_H
        # Qoldiq
        x = C_NAME
        _draw_cell(draw, x, y, C_QOLDIQ, rh, bg=row_bg)
        _draw_centered_text(draw, f"{_fmt_int(it['stock'])} blok", x, y, C_QOLDIQ, rh, f_cell, TEXT_DARK)
        # Necha kun
        x += C_QOLDIQ
        _draw_cell(draw, x, y, C_KUN, rh, bg=row_bg)
        _draw_centered_text(draw, f"{int(round(days))} kun", x, y, C_KUN, rh, f_cell, kun_col)
        # Holat (rangli chip + yozuv)
        x += C_KUN
        _draw_cell(draw, x, y, C_HOLAT, rh, bg=chip_bg)
        _draw_centered_text(draw, chip_lbl, x, y, C_HOLAT, rh, f_cell, chip_tx)
        y += rh

    # Footer (agar ro'yxat cheklangan bo'lsa)
    if total > len(items):
        note = f"Eng kritik {len(items)} tasi ko'rsatildi (jami {total} ta)."
        draw.text((24, y + 16), note, font=f_sub, fill=(120, 110, 80))

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_low_stock_table(max_days: int = 5) -> Optional[bytes]:
    """«🔴 Tez tugaydiganlar» tugmasi uchun PNG jadval.
    Ma'lumot yo'q bo'lsa None qaytaradi (bot matn/«yo'q» ko'rsatadi)."""
    computed = _compute_low_stock_items(max_days)
    if not computed:
        return None
    items, last_updated = computed
    return _draw_low_stock_image(items, last_updated, max_days)
