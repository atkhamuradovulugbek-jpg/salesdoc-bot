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


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    paths = _FONT_CANDIDATES_BOLD if bold else _FONT_CANDIDATES_REGULAR
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
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


def _draw_cell(draw, x, y, w, h, bg=None, border=BORDER_GRAY, border_w: int = 2):
    if bg is not None:
        draw.rectangle([x, y, x + w, y + h], fill=bg)
    if border is not None:
        draw.rectangle([x, y, x + w, y + h], outline=border, width=border_w)


# ------------------------------------------------------------------
# Status matnlari (suratdagi izohlar uchun)
# ------------------------------------------------------------------

def _bajardi_text(pct: float) -> str:
    if pct < 50:
        return ("QIZIL HOLAT — Oylik plan bajarilishi past darajada. Savdo "
                "faolligini oshirish, ko'proq do'konlarga kirish va assortimentni "
                "kengroq taklif qilish zarur. Oylik ish jarayoni davom etmoqda. "
                "Hozirgi tempni nazorat qilib borish muhim.")
    if pct < 80:
        return ("SARIQ HOLAT — Plan asta-sekin bajarilmoqda, lekin tempni oshirish "
                "kerak. Faol agentlik va tezroq sotuvlar talab etiladi.")
    if pct < 100:
        return ("YAXSHI HOLAT — Plan bajarilish chizig'iga juda yaqin. Yakuniy "
                "harakatlar bilan oyni 100% yopish mumkin.")
    return ("SUPER NATIJA — Oylik plan oshirib bajarildi! Bu agent uchun katta "
            "natija. Shu temp saqlansin.")


def _prognoz_text(pct: float) -> str:
    if pct < 70:
        return ("OGOH PROGNOZ — Hozirgi temp bilan oy oxirida plan to'liq "
                "bajarilmasligi mumkin. Kunlik savdoni tezroq oshirish kerak.")
    if pct < 100:
        return ("O'RTACHA PROGNOZ — Hozirgi temp bilan plan to'liq bajarilmasligi "
                "mumkin. Kunlik harakatlarni biroz oshirish lozim.")
    if pct < 110:
        return ("YAXSHI PROGNOZ — Hozirgi temp bilan oy oxirida plan to'liq "
                "bajariladi. Tempni saqlab qolish kifoya.")
    return (f"SUPER PROGNOZ — Hozirgi temp bilan oy oxirida plan {pct:.0f}% "
            "darajada bajarilishi mumkin. Bu juda kuchli ko'rsatkich. Siz yuqori "
            "natija zonasidasiz. Endi shu tempni saqlab qolish va natijani yanada "
            "mustahkamlash kerak!")


def _kunlik_text(pct: float) -> str:
    if pct < 50:
        return ("BUGUN PAST — Bugungi kunlik plan bajarilmadi. Faolligingizni "
                "oshirish kerak.")
    if pct < 100:
        return ("BUGUN O'RTACHA — Kunlik plan to'liq bajarilmadi. Ertaga ko'proq "
                "harakat qiling.")
    if pct < 110:
        return ("BUGUN YAXSHI — Kunlik plan to'liq bajarildi. Shu tempda davom "
                "eting.")
    return ("SUPER NATIJA — Bugungi kunlik plan 110% dan ham yuqori darajada "
            "bajarildi. Bu juda kuchli savdo ko'rsatkichi. Shu ish tempini saqlab "
            "qolish tavsiya etiladi. Oylik ish jarayoni davom etmoqda. Kunlik "
            "natijalarni nazorat qilib borish muhim.")


def _bg_for_pct(pct: float, has_target: bool = True) -> tuple[int, int, int]:
    if not has_target:
        return LIGHT_ROW
    if pct >= 100:
        return GREEN_OK_BG
    if pct >= 80:
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
    W = 1280
    # Ustun kengliklari
    C1 = 280   # Label
    C2 = 310   # Qiymat (so'm)
    C3 = 90    # foiz
    C4 = 440   # Izoh
    C5_LBL = 100  # Ish kuni label
    C5_VAL = 60   # Ish kuni qiymat
    assert C1 + C2 + C3 + C4 + C5_LBL + C5_VAL == W

    # Row balandliklari
    H_HEADER = 46
    H_PLAN = 46
    H_BAJARDI = 110
    H_QOLDIQ = 46
    H_PROGNOZ = 110
    H_KUNLIK_KER = 46
    H_KUNLIK_BAJ = 110

    main_height = (H_HEADER + H_PLAN + H_BAJARDI + H_QOLDIQ +
                   H_PROGNOZ + H_KUNLIK_KER + H_KUNLIK_BAJ)

    # Pastida vizit jadvali + sana
    GAP = 24
    H_VISIT_ROW = 36
    visit_rows = 5
    H_VISIT = H_VISIT_ROW * visit_rows
    H_SANA = 40
    H = main_height + GAP + H_VISIT + H_SANA + 20

    img = Image.new("RGB", (W, H), BG_CREAM)
    draw = ImageDraw.Draw(img)

    # ----- Fontlar -----
    f_h_lbl = _font(20, bold=True)         # Header label (AGENT, IYUN OYI)
    f_h_val = _font(22, bold=True)         # Agent nomi
    f_lbl = _font(18, bold=True)           # row labels (chap ustun)
    f_money = _font(22, bold=True)         # asosiy summalar
    f_money_small = _font(19, bold=True)
    f_pct = _font(26, bold=True)
    f_note = _font(15)                     # Izoh matni
    f_kun_lbl = _font(15, bold=True)
    f_kun_val = _font(20, bold=True)

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
                        _font(20, bold=True), GREEN_HEADER_LIGHT)
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
    _draw_centered_text(draw, _fmt_money(m["sales_plan"]),
                        x, y, C2, H_PLAN, f_money, WHITE)
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
    _draw_centered_text(draw, _fmt_money(m["sales_done"]),
                        x, y, C2, H_BAJARDI, f_money, bajardi_text_color)
    x += C2
    _draw_cell(draw, x, y, C3, H_BAJARDI, bg=bajardi_bg)
    _draw_centered_text(draw, f"{m['plan_pct']:.0f}%",
                        x, y, C3, H_BAJARDI, f_pct, bajardi_text_color)
    x += C3
    # Izoh ustuni — PLAN BAJARDI + PLAN QOLDIQ ikkisini qamrab oladi
    note_h = H_BAJARDI + H_QOLDIQ
    _draw_cell(draw, x, y, C4, note_h, bg=LIGHT_ROW)
    _draw_wrapped(draw, _bajardi_text(m["plan_pct"]),
                  x + 12, y + 10, C4 - 24, f_note, fill=TEXT_DARK, line_spacing=3)
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
    _draw_centered_text(draw, "PLAN QOLDIQ (BAJARISH KERAK):",
                        x, y, C1, H_QOLDIQ, _font(15, bold=True), TEXT_DARK)
    x += C1
    _draw_cell(draw, x, y, C2, H_QOLDIQ, bg=LIGHT_ROW)
    _draw_centered_text(draw, _fmt_money(m["plan_remaining"]),
                        x, y, C2, H_QOLDIQ, f_money_small, TEXT_DARK)
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
                        _font(13, bold=True), TEXT_DARK)
    _draw_centered_text(draw, "QOLDI", x, y + H_QOLDIQ // 2, C5_LBL, H_QOLDIQ // 2,
                        _font(13, bold=True), TEXT_DARK)
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
    _draw_centered_text(draw, _fmt_money(m["prognoz"]),
                        x, y, C2, H_PROGNOZ, f_money, WHITE)
    x += C2
    _draw_cell(draw, x, y, C3, H_PROGNOZ, bg=prognoz_bg)
    _draw_centered_text(draw, f"{m['prognoz_pct']:.0f}%",
                        x, y, C3, H_PROGNOZ, f_pct, WHITE)
    x += C3
    # Note B — PROGNOZ + KUNLIK_KER merge
    note_h_b = H_PROGNOZ + H_KUNLIK_KER
    _draw_cell(draw, x, y, C4, note_h_b, bg=LIGHT_ROW)
    _draw_wrapped(draw, _prognoz_text(m["prognoz_pct"]),
                  x + 12, y + 10, C4 - 24, f_note, fill=TEXT_DARK, line_spacing=3)
    x += C4
    # O'ng tomonda (C5) — bo'sh hujayralar qo'shamiz, vertical span
    _draw_cell(draw, x, y, C5_LBL + C5_VAL, note_h_b, bg=BG_CREAM)
    y += H_PROGNOZ

    # ============================================================
    # ROW 5 — KUNLIK BAJARISH KEREAK: | summa | (bo'sh) | (note continues)
    # ============================================================
    x = 0
    _draw_cell(draw, x, y, C1, H_KUNLIK_KER, bg=LIGHT_ROW)
    _draw_centered_text(draw, "KUNLIK BAJARISH KEREAK:",
                        x, y, C1, H_KUNLIK_KER, _font(15, bold=True), TEXT_DARK)
    x += C1
    _draw_cell(draw, x, y, C2, H_KUNLIK_KER, bg=LIGHT_ROW)
    _draw_centered_text(draw, _fmt_money(m["daily_required"]),
                        x, y, C2, H_KUNLIK_KER, f_money_small, TEXT_DARK)
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
    _draw_centered_text(draw, _fmt_money(m["today_sales"]),
                        x, y, C2, H_KUNLIK_BAJ, f_money,
                        WHITE if kunlik_bg != LIGHT_ROW else TEXT_DARK)
    x += C2
    _draw_cell(draw, x, y, C3, H_KUNLIK_BAJ, bg=kunlik_bg)
    pct_txt = f"{m['daily_pct']:.0f}%" if m["daily_required"] > 0 else "—"
    _draw_centered_text(draw, pct_txt, x, y, C3, H_KUNLIK_BAJ, f_pct,
                        WHITE if kunlik_bg != LIGHT_ROW else TEXT_DARK)
    x += C3
    _draw_cell(draw, x, y, C4, H_KUNLIK_BAJ, bg=LIGHT_ROW)
    _draw_wrapped(draw, _kunlik_text(m["daily_pct"]),
                  x + 12, y + 10, C4 - 24, f_note, fill=TEXT_DARK, line_spacing=3)
    x += C4
    _draw_cell(draw, x, y, C5_LBL + C5_VAL, H_KUNLIK_BAJ, bg=BG_CREAM)
    y += H_KUNLIK_BAJ

    # ============================================================
    # VIZIT JADVALI (pastda kichik, chap tomon)
    # ============================================================
    y += GAP
    v_x = 0
    v_w_lbl = 280
    v_w_val = 220
    v_total = v_w_lbl + v_w_val
    f_v_lbl = _font(15, bold=True)
    f_v_val = _font(16, bold=True)

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
    f_sana = _font(18, bold=True)
    draw.text((700, sana_y + 8), sana_text, font=f_sana, fill=TEXT_DARK)

    # PNG bytes ga aylantirib qaytarish
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ------------------------------------------------------------------
# BALL JADVALI RASMI (2-surat)
# ------------------------------------------------------------------

def _ball_for_pct(pct: float) -> tuple[str, int, tuple[int, int, int]]:
    """Pct ga qarab: (rang nomi, ball, fon rangi)."""
    if pct >= 100:
        return ("green", 3, (200, 240, 200))   # och yashil
    if pct >= 80:
        return ("yellow", 2, (255, 250, 200))  # och sariq
    return ("red", 0, (255, 210, 210))         # och qizil


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
    W = 920
    C_ORIN = 70
    C_AGENT = 420
    C_SAVDO = 200
    C_RANG = 100
    C_BALL = 130
    assert C_ORIN + C_AGENT + C_SAVDO + C_RANG + C_BALL == W

    H_HEADER = 50
    H_ROW = 44
    H_TITLE = 60
    H = H_TITLE + H_HEADER + H_ROW * len(items) + 20

    img = Image.new("RGB", (W, H), BG_CREAM)
    draw = ImageDraw.Draw(img)

    f_title = _font(22, bold=True)
    f_h = _font(18, bold=True)
    f_row = _font(17, bold=True)
    f_orin = _font(18, bold=True)
    f_ball = _font(20, bold=True)

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
        _draw_color_circle(draw, x + C_RANG // 2, y + H_ROW // 2, 14, it["color"])
        x += C_RANG
        # Ball
        _draw_cell(draw, x, y, C_BALL, H_ROW, bg=bg)
        _draw_centered_text(draw, str(it["ball"]),
                            x, y, C_BALL, H_ROW, f_ball, TEXT_DARK)
        y += H_ROW

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _draw_color_circle(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, color: str):
    """Yashil/Sariq/Qizil aylana chizadi."""
    colors = {
        "green": (40, 170, 70),
        "yellow": (240, 200, 60),
        "red": (220, 50, 60),
    }
    c = colors.get(color, (150, 150, 150))
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c, outline=(60, 60, 60), width=2)
    # Yashil aylana ichida ✓ belgi
    if color == "green":
        # Galochka chizamiz
        draw.line([(cx - 6, cy + 1), (cx - 1, cy + 6)], fill=WHITE, width=3)
        draw.line([(cx - 1, cy + 6), (cx + 7, cy - 5)], fill=WHITE, width=3)
