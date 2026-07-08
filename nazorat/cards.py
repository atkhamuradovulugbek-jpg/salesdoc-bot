"""
cards.py — Siribom Nazorat botining rasm-kartalari (Pillow, PNG bytes).

Dizayn tamoyillari (foydalanuvchi talabi):
  • 3 RANG: oq/kulrang (matn), pushti (brend — asosiy ball/KPI), yashil/qizil (holat).
  • Plitka (tile) tuzilmasi — har ko'rsatkich o'z quticha+ikonkada (tushunarli).
  • Formal "SIZ" tilida. Prognoz emas — "shu sur'atda davom etsangiz".
  • Sodda: ortiqcha narsa yo'q, muhimi ko'rinadi.

Barcha render_* funksiyalari SOF: tayyor dict oladi, PNG bytes qaytaradi.
"""

from __future__ import annotations

import os
from functools import lru_cache
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from . import icons

# ------------------------------------------------------------------
# Palitra — 3 rang tamoyili
# ------------------------------------------------------------------

BG = (12, 17, 24)            # karta foni
TILE = (19, 26, 37)          # plitka foni
TILE2 = (24, 32, 45)         # ochiqroq plitka (hero)
EDGE = (34, 45, 61)          # chegara
HAIR = (28, 37, 51)          # nozik chiziq
TRACK = (33, 44, 60)         # progress yo'lak
WHITE = (240, 245, 251)      # asosiy matn
SUB = (150, 168, 189)        # ikkinchi daraja
MUTED = (104, 122, 144)      # xira (label/footer)
PINK = (255, 74, 150)        # BREND — asosiy ball/KPI/urg'u
PINK_SOFT = (255, 120, 174)
GREEN = (60, 214, 130)       # yaxshi holat
AMBER = (255, 196, 77)       # o'rta holat (svetofor: yashil/sariq/qizil)
RED = (255, 99, 99)          # yomon holat
GOLD = (255, 205, 84)        # faqat oy yakuni medallari


def status_color(pct: float) -> tuple:
    """Svetofor (foydalanuvchi qoidasi): >=90 yashil, 70-89 sariq, <70 qizil."""
    return GREEN if pct >= 90 else (AMBER if pct >= 70 else RED)


def _mix(a, b, t):
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))


BADGE_PINK = _mix(BG, PINK, 0.16)
BADGE_GREEN = _mix(BG, GREEN, 0.16)
BADGE_RED = _mix(BG, RED, 0.16)
BADGE_NEUTRAL = _mix(BG, WHITE, 0.06)
PILL_GREEN = _mix(BG, GREEN, 0.18)
PILL_RED = _mix(BG, RED, 0.18)
PILL_PINK = _mix(BG, PINK, 0.20)
HL_PINK = (_mix(BG, PINK, 0.12), _mix(BG, PINK, 0.34), PINK_SOFT)
HL_GREEN = (_mix(BG, GREEN, 0.11), _mix(BG, GREEN, 0.32), _mix(GREEN, WHITE, 0.35))
HL_RED = (_mix(BG, RED, 0.11), _mix(BG, RED, 0.32), _mix(RED, WHITE, 0.3))
ME_ROW = _mix(BG, PINK, 0.10)

W = 1080
PAD = 56
_ASSETS = os.path.join(os.path.dirname(__file__), "assets")


@lru_cache(maxsize=4)
def _logo(height: int):
    p = os.path.join(_ASSETS, "logo.png")
    if not os.path.exists(p):
        return None
    im = Image.open(p).convert("RGBA")
    s = height / im.height
    return im.resize((int(im.width * s), height), Image.LANCZOS)


_FONT_REG = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
             "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
             "/System/Library/Fonts/Helvetica.ttc", "C:/Windows/Fonts/arial.ttf"]
_FONT_BOLD = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
              "/System/Library/Fonts/Helvetica.ttc", "C:/Windows/Fonts/arialbd.ttf"]


@lru_cache(maxsize=64)
def _font(size: int, bold: bool = False):
    for p in (_FONT_BOLD if bold else _FONT_REG):
        if os.path.exists(p):
            try:
                if p.endswith(".ttc") and bold:
                    return ImageFont.truetype(p, size, index=1)
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def fmt(n: float) -> str:
    try:
        return f"{int(round(n)):,}".replace(",", " ")
    except (ValueError, TypeError):
        return "0"


def _san(s: str) -> str:
    for a in ("✅", "⚠️", "🔴", "🟡", "✓", "↩️", "🏆", "🔥", "🎯", "→", "»", "↑", "↓"):
        s = s.replace(a, "")
    return s.strip()


# ==================================================================
# Chizish asosi
# ==================================================================

class Card:
    def __init__(self, height_guess=3000):
        self.img = Image.new("RGB", (W, height_guess), BG)
        self.d = ImageDraw.Draw(self.img)
        self.y = PAD

    def gap(self, h=16):
        self.y += h

    # --- header: logo + kicker + sana + ism ---

    def header(self, kicker, date_label, title, subtitle=""):
        logo = _logo(58)
        lx = PAD
        if logo is not None:
            self.img.paste(logo, (PAD, self.y + 2), logo)
            lx = PAD + logo.width + 20
        self.d.text((lx, self.y + 14), kicker.upper(), font=_font(24, bold=True), fill=PINK_SOFT)
        fd = _font(24, bold=True)
        dw = self.d.textlength(date_label, font=fd)
        self.d.text((W - PAD - dw, self.y + 16), date_label, font=fd, fill=SUB)
        self.y += 78
        # ism — pushti aksent chiziq bilan
        self.d.rounded_rectangle([PAD, self.y + 4, PAD + 8, self.y + 58], 4, fill=PINK)
        self.d.text((PAD + 26, self.y), title, font=_font(46, bold=True), fill=WHITE)
        self.y += 58
        if subtitle:
            self.d.text((PAD + 26, self.y), subtitle, font=_font(26), fill=SUB)
            self.y += 40
        self.gap(20)

    # --- katta hero plitka (bugungi natija) ---

    def hero(self, ball_today, today_sales, today_pct, vs_plan):
        h = 150
        self.d.rounded_rectangle([PAD, self.y, W - PAD, self.y + h], 18, fill=TILE2)
        x = PAD + 34
        self.d.text((x, self.y + 26), "BUGUNGI NATIJA", font=_font(21, bold=True), fill=MUTED)
        self.d.text((x, self.y + 56), f"+{ball_today}", font=_font(72, bold=True), fill=PINK)
        wv = self.d.textlength(f"+{ball_today}", font=_font(72, bold=True))
        self.d.text((x + wv + 14, self.y + 82), "ball", font=_font(38, bold=True), fill=PINK_SOFT)
        self.d.text((x, self.y + 118), f"Bugun: {fmt(today_sales)} so'm",
                    font=_font(24), fill=SUB)
        # o'ng: reja va vs-plan
        rx = W - PAD - 300
        self.d.line([(rx - 20, self.y + 30), (rx - 20, self.y + h - 30)], fill=EDGE, width=2)
        self.d.text((rx, self.y + 34), "KUNLIK REJA", font=_font(20, bold=True), fill=MUTED)
        pcol = GREEN if today_pct >= 100 else (WHITE if today_pct >= 80 else RED)
        self.d.text((rx, self.y + 62), f"{today_pct:.0f}%", font=_font(50, bold=True), fill=pcol)
        vs_col = GREEN if vs_plan >= 0 else RED
        vs_txt = f"Rejadan {'+' if vs_plan >= 0 else ''}{vs_plan} ball"
        self.d.text((rx, self.y + 120), vs_txt, font=_font(23, bold=True), fill=vs_col)
        self.y += h + 18

    # --- oy natijasi + "shu sur'atda" ---

    def month_panel(self, month_ball, ball_plan, pace_ball, observe=False):
        h = 150 if not observe else 110
        self.d.rounded_rectangle([PAD, self.y, W - PAD, self.y + h], 18, fill=TILE)
        x = PAD + 34
        icons.draw(self.d, "calendar", x + 16, self.y + 42, 17, PINK_SOFT, 3)
        self.d.text((x + 48, self.y + 26), "OY NATIJASI", font=_font(21, bold=True), fill=MUTED)
        plan_txt = f" / {ball_plan}" if ball_plan else ""
        self.d.text((x + 48, self.y + 52), f"{month_ball}", font=_font(46, bold=True), fill=PINK)
        mw = self.d.textlength(f"{month_ball}", font=_font(46, bold=True))
        self.d.text((x + 48 + mw + 8, self.y + 68), f"{plan_txt} ball", font=_font(28), fill=SUB)
        # progress bar
        bx, bw = x + 48, W - PAD - 34 - (x + 48)
        by = self.y + 108
        self.d.rounded_rectangle([bx, by, bx + bw, by + 16], 8, fill=TRACK)
        frac = month_ball / ball_plan if ball_plan else 0
        fw = max(int(bw * min(frac, 1)), 10) if frac > 0 else 0
        if fw:
            self.d.rounded_rectangle([bx, by, bx + fw, by + 16], 8, fill=PINK)
        if not observe and ball_plan:
            pct = frac * 100
            self.d.text((W - PAD - 34 - self.d.textlength(f"{pct:.0f}%", font=_font(24, bold=True)),
                         self.y + 60), f"{pct:.0f}%", font=_font(24, bold=True), fill=WHITE)
        self.y += h + 12
        # "shu sur'atda davom etsangiz" — panel ostida alohida qator
        if not observe and ball_plan:
            reach = pace_ball >= ball_plan
            col = GREEN if reach else RED
            if reach:
                txt = f"Shu sur'atda davom etsangiz — {pace_ball:.0f} ball to'playsiz"
            else:
                txt = f"Shu sur'atda — {pace_ball:.0f} ball (rejadan {ball_plan - pace_ball:.0f} kam)"
            icons.draw(self.d, "check" if reach else "debt", PAD + 14, self.y + 14, 13, col, 3)
            self.d.text((PAD + 38, self.y), txt, font=_font(24, bold=True), fill=col)
            self.y += 42

    # --- 2 ustunli stat plitkalar ---

    def stat_tiles(self, tiles: list[dict]):
        """tiles: [{icon, label, value, value_color, sub, badge}] — 2 ustun."""
        col_w = (W - 2 * PAD - 20) / 2
        h = 132
        for i, t in enumerate(tiles):
            col = i % 2
            if col == 0:
                row_y = self.y
            tx = PAD + col * (col_w + 20)
            ty = row_y
            self.d.rounded_rectangle([tx, ty, tx + col_w, ty + h], 16, fill=TILE)
            # ikonka badge
            badge = t.get("badge", BADGE_NEUTRAL)
            self.d.rounded_rectangle([tx + 24, ty + 22, tx + 24 + 52, ty + 22 + 52], 13, fill=badge)
            icons.draw(self.d, t["icon"], tx + 50, ty + 48, 15, t.get("icon_color", PINK_SOFT), 3)
            self.d.text((tx + 92, ty + 26), t["label"].upper(), font=_font(19, bold=True), fill=MUTED)
            self.d.text((tx + 92, ty + 52), t["value"], font=_font(33, bold=True),
                        fill=t.get("value_color", WHITE))
            if t.get("sub"):
                self.d.text((tx + 24, ty + 96), t["sub"], font=_font(21), fill=SUB)
            if col == 1 or i == len(tiles) - 1:
                self.y = row_y + h + 16

    # --- oddiy qator (label · value) + ajratgich ---

    def row(self, label, value, value_color=WHITE, divider=True, value_pill=None):
        self.d.text((PAD, self.y), label, font=_font(28), fill=SUB)
        if value_pill:
            bg, fg = value_pill
            pw = int(self.d.textlength(value, font=_font(27, bold=True)) + 32)
            self.d.rounded_rectangle([W - PAD - pw, self.y - 4, W - PAD, self.y + 38], 11, fill=bg)
            self.d.text((W - PAD - pw + 16, self.y + 1), value, font=_font(27, bold=True), fill=fg)
        else:
            wv = self.d.textlength(value, font=_font(29, bold=True))
            self.d.text((W - PAD - wv, self.y - 1), value, font=_font(29, bold=True), fill=value_color)
        self.y += 42
        if divider:
            self.gap(9)
            self.d.line([(PAD, self.y), (W - PAD, self.y)], fill=HAIR, width=1)
            self.gap(11)
        else:
            self.gap(8)

    def section(self, label, icon=None):
        self.gap(8)
        x = PAD
        if icon:
            icons.draw(self.d, icon, PAD + 10, self.y + 10, 12, MUTED, 2)
            x = PAD + 34
        self.d.text((x, self.y), label.upper(), font=_font(20, bold=True), fill=MUTED)
        self.y += 38

    # --- do'kon-summa raqamli qator ---

    def numbered_row(self, num, shop, amount, amount_color=WHITE, sub=""):
        self.d.text((PAD, self.y + 1), f"{num}.", font=_font(26, bold=True), fill=MUTED)
        self.d.text((PAD + 52, self.y), shop, font=_font(27), fill=(212, 222, 234))
        lw = self.d.textlength(shop, font=_font(27))
        if sub:
            self.d.text((PAD + 52 + lw + 12, self.y + 4), sub, font=_font(21),
                        fill=RED if "kun" in sub and _age_big(sub) else MUTED)
        wv = self.d.textlength(amount, font=_font(28, bold=True))
        self.d.text((W - PAD - wv, self.y), amount, font=_font(28, bold=True), fill=amount_color)
        self.y += 40
        self.gap(7)
        self.d.line([(PAD, self.y), (W - PAD, self.y)], fill=HAIR, width=1)
        self.gap(8)

    def bar(self, label, frac, right, fill=PINK):
        self.d.text((PAD, self.y + 2), label, font=_font(26), fill=SUB)
        bx = PAD + 220
        bw = W - PAD - 190 - bx
        by = self.y + 14
        self.d.rounded_rectangle([bx, by, bx + bw, by + 15], 8, fill=TRACK)
        fw = max(int(bw * min(max(frac, 0), 1)), 10 if frac > 0 else 0)
        if fw:
            self.d.rounded_rectangle([bx, by, bx + fw, by + 15], 8, fill=fill)
        wv = self.d.textlength(right, font=_font(27, bold=True))
        self.d.text((W - PAD - wv, self.y), right, font=_font(27, bold=True), fill=WHITE)
        self.y += 46
        self.gap(6)

    def rank_row(self, pos, name, pill_text, pill_bg, pill_fg, tail="", hl=False):
        rh = 60
        if hl:
            self.d.rounded_rectangle([PAD - 16, self.y - 8, W - PAD + 16, self.y + rh - 14],
                                     12, fill=ME_ROW)
        self.d.text((PAD + 2, self.y + 8), pos, font=_font(26, bold=True), fill=SUB)
        self.d.text((PAD + 58, self.y + 4), name, font=_font(30, bold=True),
                    fill=PINK_SOFT if hl else (222, 231, 241))
        ft = _font(23)
        if tail:
            tw = self.d.textlength(tail, font=ft)
            self.d.text((W - PAD - tw, self.y + 9), tail, font=ft, fill=SUB)
        fp = _font(25, bold=True)
        pw = int(self.d.textlength(pill_text, font=fp) + 32)
        pr = W - PAD - 200
        self.d.rounded_rectangle([pr - pw, self.y + 2, pr, self.y + 42], 11, fill=pill_bg)
        self.d.text((pr - pw + 16, self.y + 8), pill_text, font=fp, fill=pill_fg)
        self.y += rh
        self.d.line([(PAD, self.y - 4), (W - PAD, self.y - 4)], fill=HAIR, width=1)

    def _wrap(self, text, font, mw):
        out, cur = [], ""
        for w_ in text.split():
            t = (cur + " " + w_).strip()
            if self.d.textlength(t, font=font) <= mw:
                cur = t
            else:
                if cur:
                    out.append(cur)
                cur = w_
        if cur:
            out.append(cur)
        return out

    def callout(self, text, scheme="pink", label="ENG FOYDALI HARAKAT", icon="bulb"):
        bg, edge, fg = {"pink": HL_PINK, "ok": HL_GREEN, "green": HL_GREEN, "red": HL_RED,
                        "warn": HL_RED}[scheme]
        f = _font(27)
        ix = PAD + 54 if icon else PAD + 28
        lines = self._wrap(_san(text), f, W - PAD - ix - 28)
        head = 30 if label else 0
        h = 22 + head + len(lines) * 38 + 20
        self.gap(14)
        self.d.rounded_rectangle([PAD, self.y, W - PAD, self.y + h], 16, fill=bg,
                                 outline=edge, width=2)
        if icon:
            icons.draw(self.d, icon, PAD + 28, self.y + h / 2, 15, edge, 3)
        ty = self.y + 20
        if label:
            self.d.text((ix, ty), label, font=_font(18, bold=True), fill=edge)
            ty += 30
        for ln in lines:
            self.d.text((ix, ty), ln, font=f, fill=fg)
            ty += 38
        self.y += h + 12

    def footer(self, text):
        self.gap(6)
        f = _font(21)
        for ln in self._wrap(_san(text), f, W - 2 * PAD):
            self.d.text((PAD, self.y), ln, font=f, fill=MUTED)
            self.y += 30

    def png(self):
        h = self.y + PAD - 6
        img = self.img.crop((0, 0, W, h))
        ImageDraw.Draw(img).rounded_rectangle([1, 1, W - 2, h - 2], 26, outline=EDGE, width=2)
        buf = BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()


def _age_big(sub: str) -> bool:
    import re
    m = re.search(r"(\d+)", sub)
    return bool(m and int(m.group(1)) >= 10)


def ball_pill(ball):
    if ball >= 3:
        return PILL_GREEN, GREEN
    if ball >= 1:
        return PILL_PINK, PINK_SOFT
    return PILL_RED, RED


# ==================================================================
# 1. BALL MUSOBAQASI (kechki, faqat ball o'yiniga bag'ishlangan)
# ==================================================================

def render_ball_card(x: dict) -> bytes:
    c = Card()
    c.header("ball musobaqasi", x["date_label"], x["name"], x["league_label"])

    # BUGUNGI NATIJA: chapda savdo, o'ngda katta +ball
    h = 148
    c.d.rounded_rectangle([PAD, c.y, W - PAD, c.y + h], 18, fill=TILE2)
    x0 = PAD + 34
    c.d.text((x0, c.y + 26), "BUGUNGI NATIJA", font=_font(21, bold=True), fill=MUTED)
    c.d.text((x0, c.y + 60), "Savdo", font=_font(24), fill=SUB)
    c.d.text((x0, c.y + 94), f"{fmt(x['today_sales'])} so'm", font=_font(38, bold=True), fill=WHITE)
    bt = f"+{x['ball_today']}"
    fb = _font(74, bold=True)
    bw = c.d.textlength(bt, font=fb)
    c.d.text((W - PAD - 40 - bw - 90, c.y + 44), bt, font=fb, fill=PINK)
    c.d.text((W - PAD - 40 - 82, c.y + 74), "ball", font=_font(40, bold=True), fill=PINK_SOFT)
    c.y += h + 16

    # Bugungi O'RIN (savdodan) + kechagiga nisbatan o'zgarish
    tr, yr = x.get("today_rank"), x.get("yesterday_rank")
    if tr:
        h_r = 88
        c.d.rounded_rectangle([PAD, c.y, W - PAD, c.y + h_r], 16, fill=TILE)
        icons.draw(c.d, "trophy", PAD + 34, c.y + h_r // 2, 15, PINK_SOFT, 3)
        c.d.text((PAD + 72, c.y + 20), "BUGUNGI SAVDO BO'YICHA O'RNINGIZ", font=_font(18, bold=True), fill=MUTED)
        c.d.text((PAD + 72, c.y + 44), f"{tr}-o'rin", font=_font(34, bold=True), fill=WHITE)
        ow = c.d.textlength(f"{tr}-o'rin", font=_font(34, bold=True))
        c.d.text((PAD + 72 + ow + 14, c.y + 52), f"/ {x.get('league_size','')} agent", font=_font(22), fill=SUB)
        # o'zgarish
        if yr:
            diff = yr - tr   # musbat = ko'tarildi
            if diff > 0:
                txt, col, ic = f"↑ kecha {yr}-o'rin edingiz, {diff} pog'ona ko'tarildingiz!", GREEN, "sales"
            elif diff < 0:
                txt, col, ic = f"↓ kecha {yr}-o'rin edingiz, {abs(diff)} pog'ona tushdingiz", RED, "sales_down"
            else:
                txt, col, ic = f"kecha ham {yr}-o'rin edingiz", SUB, "target"
            tw = c.d.textlength(_san(txt), font=_font(20, bold=True))
            c.d.text((W - PAD - 34 - tw, c.y + 34), _san(txt), font=_font(20, bold=True), fill=col)
        c.y += h_r + 16

    # OY NATIJASI: oylik reja aniq ko'rinadi
    if not x.get("observe_only") and x["ball_plan"]:
        h2 = 156
        c.d.rounded_rectangle([PAD, c.y, W - PAD, c.y + h2], 18, fill=TILE)
        icons.draw(c.d, "calendar", PAD + 30, c.y + 40, 16, PINK_SOFT, 3)
        c.d.text((PAD + 62, c.y + 24), "OY NATIJASI", font=_font(21, bold=True), fill=MUTED)
        c.d.text((PAD + 62, c.y + 52), f"{x['month_ball']}", font=_font(52, bold=True), fill=PINK)
        mw = c.d.textlength(f"{x['month_ball']}", font=_font(52, bold=True))
        c.d.text((PAD + 62 + mw + 12, c.y + 74), f"/ {x['ball_plan']} ball",
                 font=_font(34, bold=True), fill=SUB)
        # o'ngda: oylik reja yorlig'i
        c.d.text((W - PAD - 34 - c.d.textlength("OYLIK REJA", font=_font(19, bold=True)), c.y + 30),
                 "OYLIK REJA", font=_font(19, bold=True), fill=MUTED)
        pr = f"{x['ball_plan']} ball"
        c.d.text((W - PAD - 34 - c.d.textlength(pr, font=_font(30, bold=True)), c.y + 54),
                 pr, font=_font(30, bold=True), fill=WHITE)
        bx, bw2, by = PAD + 62, W - PAD - 34 - (PAD + 62), c.y + 118
        c.d.rounded_rectangle([bx, by, bx + bw2, by + 16], 8, fill=TRACK)
        frac = x["month_ball"] / x["ball_plan"]
        fw = max(int(bw2 * min(frac, 1)), 10) if frac > 0 else 0
        if fw:
            c.d.rounded_rectangle([bx, by, bx + fw, by + 16], 8, fill=PINK)
        c.y += h2 + 14

        # KATTA motivatsion qator — "shu sur'atda X ball"
        reach = x["prognoz_ball"] >= x["ball_plan"]
        col = GREEN if reach else RED
        bg = HL_GREEN[0] if reach else HL_RED[0]
        edge = HL_GREEN[1] if reach else HL_RED[1]
        hh = 92
        c.d.rounded_rectangle([PAD, c.y, W - PAD, c.y + hh], 16, fill=bg, outline=edge, width=2)
        icons.draw(c.d, "check" if reach else "flag", PAD + 34, c.y + hh // 2, 16, col, 4)
        c.d.text((PAD + 72, c.y + 20), "SHU SUR'ATDA DAVOM ETSANGIZ", font=_font(19, bold=True), fill=col)
        c.d.text((PAD + 72, c.y + 44), f"{x['prognoz_ball']:.0f} ball to'playsiz",
                 font=_font(38, bold=True), fill=col)
        c.y += hh + 14
    else:
        c.month_panel(x["month_ball"], x["ball_plan"], x["prognoz_ball"], observe=True)

    c.footer("Zo'r natija sari davom eting! Har bir ball sizni maqsadingizga yaqinlashtiradi.")
    if x.get("observe_only"):
        c.footer("Kuzatuv rejimi: birinchi oy — ball hisoblanadi, reja va sovrinlar keyingi oydan.")
    return c.png()


# ==================================================================
# 2. OYLIK REJA KARTASI (sodda, aniq bo'linган)
# ==================================================================

def _plan_tile(c, label, value, accent, sub="", frac=None):
    """Ajratilgan katak: chap aksent chiziq + label + katta qiymat (+ ixtiyoriy bar)."""
    h = 88 if frac is None else 104
    c.d.rounded_rectangle([PAD, c.y, W - PAD, c.y + h], 15, fill=TILE)
    c.d.rounded_rectangle([PAD, c.y + 14, PAD + 7, c.y + h - 14], 4, fill=accent)
    c.d.text((PAD + 28, c.y + 20), label.upper(), font=_font(19, bold=True), fill=MUTED)
    c.d.text((PAD + 28, c.y + 44), value, font=_font(34, bold=True), fill=WHITE)
    if sub:
        sw = c.d.textlength(sub, font=_font(28, bold=True))
        c.d.text((W - PAD - 30 - sw, c.y + 40), sub, font=_font(28, bold=True), fill=accent)
    if frac is not None:
        bx, bw, by = PAD + 28, W - PAD - 30 - (PAD + 28), c.y + h - 22
        c.d.rounded_rectangle([bx, by, bx + bw, by + 12], 6, fill=TRACK)
        fw = max(int(bw * min(max(frac, 0), 1)), 8) if frac > 0 else 0
        if fw:
            c.d.rounded_rectangle([bx, by, bx + fw, by + 12], 6, fill=accent)
    c.y += h + 12


def _big_tile(c, label, value, accent, sub="", icon_name="target"):
    """Katta urg'uli katak: ikonka + label + KATTA qiymat (+ o'ngda sub)."""
    h = 108
    c.d.rounded_rectangle([PAD, c.y, W - PAD, c.y + h], 16, fill=TILE2)
    icons.draw(c.d, icon_name, PAD + 40, c.y + h // 2, 19, accent, 3)
    c.d.text((PAD + 82, c.y + 24), label.upper(), font=_font(20, bold=True), fill=MUTED)
    c.d.text((PAD + 82, c.y + 52), value, font=_font(40, bold=True), fill=accent)
    if sub:
        sw = c.d.textlength(sub, font=_font(32, bold=True))
        c.d.text((W - PAD - 34 - sw, c.y + 46), sub, font=_font(32, bold=True), fill=accent)
    c.y += h + 12


def render_plan_card(x: dict) -> bytes:
    c = Card()
    c.header("oylik reja", x["date_label"], x["name"], x["month_label"] + " oyi")
    # Ish kunlari — aniq 3 qismli rangli strip
    c.gap(2)
    seg_w = (W - 2 * PAD - 24) / 3
    segs = [("ISH KUNI", x["wd_total"], SUB),
            ("ISHLAB BO'LINDI", x["wd_passed"], PINK_SOFT),
            ("QOLDI", x["wd_remaining"], GREEN)]
    for i, (lab, val, col) in enumerate(segs):
        sx = PAD + i * (seg_w + 12)
        c.d.rounded_rectangle([sx, c.y, sx + seg_w, c.y + 66], 12, fill=TILE)
        c.d.text((sx + 20, c.y + 12), lab, font=_font(16, bold=True), fill=MUTED)
        c.d.text((sx + 20, c.y + 32), f"{val} kun", font=_font(26, bold=True), fill=col)
    c.y += 66 + 18

    # Savdo rejasi — reja / bajardingiz / qoldi
    _plan_tile(c, "Oylik rejangiz", f"{fmt(x['sales_plan'])} so'm", SUB)
    _plan_tile(c, "Bajardingiz", f"{fmt(x['sales_done'])} so'm", PINK,
               sub=f"{x['plan_pct']:.0f}%", frac=x["plan_pct"] / 100)
    _plan_tile(c, "Yana bajarishingiz kerak", f"{fmt(x['plan_remaining'])} so'm", GREEN)

    # OYLIK PROGNOZ — shu ketishda oyni qancha bilan yopadi (alohida, ajralib)
    pcol = status_color(x["prognoz_pct"])
    _big_tile(c, "Oylik prognoz (shu ketishda)", f"{fmt(x['prognoz'])} so'm", pcol,
              sub=f"{x['prognoz_pct']:.0f}%", icon_name="growth")

    # KUNLIK KERAK + BUGUNGI SAVDO — aniq yorliqlar; bugungi savdo svetofor rangida
    _big_tile(c, "Kunlik qilishingiz kerak bo'lgan savdo", f"{fmt(x['daily_required'])} so'm",
              PINK, icon_name="target")
    tp = x["today_pct"]
    tcol = status_color(tp)
    ticon = "sales" if tp >= 100 else "sales_down"
    _big_tile(c, "Bugungi bajargan savdoingiz", f"{fmt(x['today_sales'])} so'm", tcol,
              sub=f"{tp:.0f}%", icon_name=ticon)

    c.section("Vizitlar", icon="calendar")
    c.row("Oylik vizit rejasi", f"{x['visit_plan']} ta")
    c.row("Bordingiz", f"{x['visits_done']} ta · yana {x['visit_remaining']} ta qoldi")
    vok = x["today_visits"] >= x["visit_daily_required"]
    c.row("Kuniga kerak", f"{x['visit_daily_required']:.0f} ta  (bugun {x['today_visits']} ta)",
          value_color=(GREEN if vok else WHITE), divider=False)
    return c.png()


# ==================================================================
# 3. HAPPY TOY — prognoz + qulflangan darajalar
# ==================================================================

def render_toy_card(x: dict) -> bytes:
    c = Card()
    c.header("happy toy", x["date_label"], x["name"], "Sotilgan, qaytmagan bloklar · 1 blok = 24 dona")

    # Hero: hozirgi bloklar
    h = 120
    c.d.rounded_rectangle([PAD, c.y, W - PAD, c.y + h], 18, fill=TILE2)
    c.d.text((PAD + 34, c.y + 24), "SHU OYDA SOTILGAN", font=_font(21, bold=True), fill=MUTED)
    c.d.text((PAD + 34, c.y + 52), f"{x['blocks']:.0f}", font=_font(56, bold=True), fill=PINK)
    bw = c.d.textlength(f"{x['blocks']:.0f}", font=_font(56, bold=True))
    c.d.text((PAD + 34 + bw + 14, c.y + 74), "blok", font=_font(30, bold=True), fill=PINK_SOFT)
    # o'ng: prognoz
    prog = x.get("prognoz_blocks", 0)
    first_tier = x["tiers"][0][0] if x["tiers"] else 105
    rx = W - PAD - 340
    c.d.line([(rx - 20, c.y + 26), (rx - 20, c.y + h - 26)], fill=EDGE, width=2)
    c.d.text((rx, c.y + 28), "SHU SUR'ATDA — OY OXIRIGACHA", font=_font(18, bold=True), fill=MUTED)
    pcol = GREEN if prog >= first_tier else PINK_SOFT
    c.d.text((rx, c.y + 54), f"~{prog:.0f} blok", font=_font(40, bold=True), fill=pcol)
    c.y += h + 16

    # Rangli progress chiziq: hozirgi bloklar → 105 (1-daraja)
    frac = x["blocks"] / first_tier if first_tier else 0
    bar_col = GREEN if prog >= first_tier else (RED if frac < 0.33 else PINK)
    c.d.text((PAD, c.y + 2), f"1-darajaga ({first_tier:.0f})", font=_font(24), fill=SUB)
    bx = PAD + 250
    bw = W - PAD - 130 - bx
    by = c.y + 12
    c.d.rounded_rectangle([bx, by, bx + bw, by + 18], 9, fill=TRACK)
    fw = max(int(bw * min(frac, 1)), 10) if frac > 0 else 0
    if fw:
        c.d.rounded_rectangle([bx, by, bx + fw, by + 18], 9, fill=bar_col)
    rt = f"{x['blocks']:.0f} / {first_tier:.0f}"
    c.d.text((W - PAD - c.d.textlength(rt, font=_font(26, bold=True)), c.y),
             rt, font=_font(26, bold=True), fill=WHITE)
    c.y += 52

    # Xabar: prognoz 105 dan past bo'lsa harakatga chaqirish
    if prog < first_tier:
        msg = (f"Shu sur'atda {first_tier:.0f} blok bonusiga yetmaysiz. "
               f"Ko'proq harakat qiling — kuniga bir-ikki blok qo'shsangiz bonus qo'lda!")
        c.callout(msg, "red", label="", icon="flag")
    else:
        c.callout(f"Zo'r sur'at! Shu zayilda {first_tier:.0f} blok bonusini olasiz. Davom eting!",
                  "ok", label="", icon="check")

    c.section("Bonus darajalari")
    reached_any = False
    next_open_found = False
    for blocks, bonus in x["tiers"]:
        reached = x["blocks"] >= blocks
        is_open = (not reached) and (not next_open_found)
        if is_open:
            next_open_found = True
        locked = (not reached) and (not is_open)

        if reached:
            ring, num_col, name_col = GREEN, GREEN, WHITE
            reached_any = True
        elif is_open:
            ring, num_col, name_col = PINK, PINK_SOFT, WHITE
        else:
            ring, num_col, name_col = TRACK, MUTED, MUTED

        c.d.ellipse([PAD, c.y, PAD + 54, c.y + 54], outline=ring, width=4)
        bt = f"{blocks:.0f}"
        bwid = c.d.textlength(bt, font=_font(23, bold=True))
        c.d.text((PAD + 27 - bwid / 2, c.y + 14), bt, font=_font(23, bold=True), fill=num_col)
        c.d.text((PAD + 80, c.y - 2), f"{fmt(bonus)} so'm bonus", font=_font(30, bold=True), fill=name_col)

        if reached:
            icons.draw(c.d, "check", W - PAD - 40, c.y + 26, 15, GREEN, 4)
            s = "Olindi"
            scol = GREEN
        elif is_open:
            s = f"OCHIQ · {x['to_next']:.0f} blok sotish kerak · kuniga {x['per_day_needed']:.1f} tadan"
            scol = PINK_SOFT
        else:
            icons.draw(c.d, "lock", W - PAD - 38, c.y + 26, 13, MUTED, 3)
            prev_tier = x["tiers"][x["tiers"].index((blocks, bonus)) - 1][0]
            s = f"Qulf · {prev_tier:.0f} blokka chiqqach ochiladi"
            scol = MUTED
        c.d.text((PAD + 80, c.y + 34), s, font=_font(22), fill=scol)
        c.y += 84
        c.d.line([(PAD + 80, c.y - 8), (W - PAD, c.y - 8)], fill=HAIR, width=1)

    c.footer("Bonus faqat yetkazilgan va qaytmagan mahsulotga to'lanadi.")
    return c.png()


# ==================================================================
# 4. QARZ KARTASI (ertalabki) — 50k dan yuqori barcha do'kon raqamli
# ==================================================================

def render_debt_card(x: dict) -> bytes:
    c = Card()
    c.header("qarz hisoboti", x["date_label"], x["name"], x["league_label"])
    c.section("50 000 so'mdan yuqori barcha do'konlar", icon="debt")
    debts = x.get("debts_all", x["debts"])
    if debts:
        for i, (shop, summa, age) in enumerate(debts, 1):
            age_txt = f"{age} kun" if age else ""
            c.numbered_row(i, shop, fmt(summa), sub=age_txt)
    else:
        c.row("Qarz", "yo'q", value_color=GREEN, divider=False)
    frac = x["debt_total"] / x["debt_limit"] if x["debt_limit"] else 0
    col = GREEN if frac <= 0.8 else RED
    c.gap(4)
    c.row("Jami qarz", f"{fmt(x['debt_total'])}  /  limit {fmt(x['debt_limit'])}",
          value_color=col, divider=False)
    c.bar("Limit to'ldi", frac, f"{frac*100:.0f}%", fill=col)
    c.footer("Eng eski qarz (10+ kun) qizil bilan belgilanadi.")
    return c.png()


# ==================================================================
# 5. VAZVRAT KARTASI (ertalabki) — kunlik do'kon-do'kon + oylik jami
# ==================================================================

def render_returns_card(x: dict) -> bytes:
    c = Card()
    c.header("vazvrat hisoboti", x["date_label"], x["name"], x["league_label"])
    rdate = x.get("returns_date", "")
    full = x.get("full_returns", [])
    partial = x.get("partial_returns", [])

    # 1) TO'LIQ vazvrat — do'kon butun buyurtmani rad etgan
    c.section(f"{rdate} · to'liq rad etilgan" if rdate else "To'liq rad etilgan", icon="return")
    if full:
        for i, (shop, summa) in enumerate(full, 1):
            c.numbered_row(i, shop, f"−{fmt(summa)}", amount_color=RED)
    else:
        c.row("To'liq vazvrat", "yo'q", value_color=GREEN, divider=False)

    # 2) QISMAN vazvrat — buyurtmadan ba'zi tovar olinmagan
    c.section("Qisman olinmagan tovarlar", icon="debt")
    if partial:
        for i, (shop, summa) in enumerate(partial, 1):
            c.numbered_row(i, shop, f"−{fmt(summa)}", amount_color=RED)
    else:
        c.row("Qisman vazvrat", "yo'q", value_color=GREEN, divider=False)

    # Kunlik jami — ALOHIDA katak
    if x.get("returns_total", 0) > 0:
        c.gap(4)
        _big_tile(c, f"{rdate} kungi jami vazvrat", f"−{fmt(x['returns_total'])} so'm",
                  RED, icon_name="return")

    # Oy bo'yicha — to'liq va qisman ALOHIDA, so'ng jami
    c.section("Shu oy bo'yicha jami", icon="calendar")
    c.row("To'liq rad etilgan (oylik)", f"{fmt(x.get('returns_month_full', 0))} so'm", value_color=RED)
    c.row("Qisman olinmagan (oylik)", f"{fmt(x.get('returns_month_partial', 0))} so'm", value_color=RED)
    mcol = GREEN if x.get("returns_month_pct", 0) < 3 else RED
    _big_tile(c, "Oylik jami vazvrat", f"{fmt(x.get('returns_month', 0))} so'm",
              mcol, sub=f"{x.get('returns_month_pct', 0):.1f}%", icon_name="return")
    c.footer("To'liq: do'kon butun buyurtmani olmagan. Qisman: buyurtmadan ba'zi tovar olinmagan. "
             "Almashtirish (obmen) va javon vazvrati sanalmaydi.")
    return c.png()


# ==================================================================
# 5. GURUH — KUNLIK BALLAR REYTINGI
# ==================================================================

def render_group_daily(x: dict) -> bytes:
    c = Card()
    c.header("kunlik ballar", x["date_label"], x["league_label"],
             "Bugungi natijalar · ball teng bo'lsa savdo hal qiladi")
    # Ustun sarlavhalari
    c.d.text((PAD + 58, c.y), "AGENT", font=_font(18, bold=True), fill=MUTED)
    kb = "KUNLIK BALL"
    c.d.text((W - PAD - 200 - c.d.textlength(kb, font=_font(18, bold=True)) - 12, c.y),
             kb, font=_font(18, bold=True), fill=MUTED)
    ks = "KUNLIK SAVDO"
    c.d.text((W - PAD - c.d.textlength(ks, font=_font(18, bold=True)), c.y),
             ks, font=_font(18, bold=True), fill=MUTED)
    c.y += 32
    c.d.line([(PAD, c.y), (W - PAD, c.y)], fill=HAIR, width=1)
    c.gap(10)
    for i, (name, ball, sales) in enumerate(x["rows"], 1):
        bg, fg = ball_pill(ball)
        c.rank_row(str(i), name, f"{ball} ball", bg, fg, tail=fmt(sales))
    c.gap(6)
    if x.get("streak_note"):
        c.callout(x["streak_note"], "pink", label="SERIYA", icon="trophy")
    c.footer("Oylik yig'indi maxfiy — g'oliblar oy yakunida e'lon qilinadi.")
    return c.png()


# ==================================================================
# 6. ADMIN SVODKA
# ==================================================================

def render_admin_summary(x: dict) -> bytes:
    c = Card()
    logo = _logo(52)
    if logo is not None:
        c.img.paste(logo, (PAD, c.y), logo)
    c.d.text((PAD + (logo.width + 18 if logo else 0), c.y + 4),
             x["title"].upper(), font=_font(23, bold=True), fill=PINK_SOFT)
    dw = c.d.textlength(x["date_label"], font=_font(23, bold=True))
    c.d.text((W - PAD - dw, c.y + 6), x["date_label"], font=_font(23, bold=True), fill=SUB)
    c.y += 72
    c.d.line([(PAD, c.y), (W - PAD, c.y)], fill=EDGE, width=2)
    c.gap(16)

    cols = [(PAD, "Agent"), (446, "Savdo"), (636, "Ball"), (736, "Reja"),
            (852, "Toy"), (952, "Qarz")]
    for cx, label in cols:
        c.d.text((cx, c.y), label.upper(), font=_font(19, bold=True), fill=MUTED)
    c.y += 34
    c.d.line([(PAD, c.y), (W - PAD, c.y)], fill=HAIR, width=1)
    c.gap(8)
    for name, sales, ball, plan_pct, toy, debt_mln, frac in x["rows"]:
        c.d.text((PAD, c.y), name[:20], font=_font(26, bold=True), fill=(237, 243, 250))
        c.d.text((446, c.y + 1), fmt(sales), font=_font(25), fill=(RED if sales == 0 else (214, 224, 236)))
        c.d.text((636, c.y + 1), str(ball), font=_font(25), fill=(214, 224, 236))
        pcol = GREEN if plan_pct >= 80 else (WHITE if plan_pct >= 50 else RED)
        c.d.text((736, c.y + 1), f"{plan_pct:.0f}%", font=_font(25), fill=pcol)
        c.d.text((852, c.y + 1), f"{toy:.0f}", font=_font(25), fill=(214, 224, 236))
        dcol = RED if frac > 1 else (WHITE if frac < 0.9 else PINK_SOFT)
        c.d.text((952, c.y + 1), f"{debt_mln:.1f}", font=_font(25), fill=dcol)
        c.y += 46
        c.d.line([(PAD, c.y - 4), (W - PAD, c.y - 4)], fill=HAIR, width=1)
    c.gap(12)
    for level, text in x.get("signals", []):
        c.callout(text, "red" if level == "bad" else ("warn" if level == "warn" else "ok"),
                  label="", icon="debt" if level != "info" else "check")
    c.footer("Qarz — mln so'mda (limitga yaqin pushti, oshgan qizil).")
    return c.png()


# ==================================================================
# 7. OY YAKUNI — REVEAL
# ==================================================================

def render_month_final(x: dict) -> bytes:
    c = Card()
    c.header(f"{x['month_label']} yakuni", "G'OLIBLAR", x["league_label"],
             "Oy bo'yi maxfiy saqlangan yig'indi — mana natija!")
    medals = {1: GOLD, 2: (200, 208, 220), 3: (222, 156, 96)}
    for place, name, total_ball, over, prize in x["podium"]:
        col = medals.get(place, SUB)
        icons.draw(c.d, "trophy", PAD + 16, c.y + 22, 16, col, 3)
        c.d.text((PAD + 48, c.y), f"{place}-o'rin", font=_font(32, bold=True), fill=col)
        c.d.text((PAD + 210, c.y), name, font=_font(32, bold=True),
                 fill=WHITE if place == 1 else (226, 234, 243))
        tail = f"{total_ball} ball (+{over})  ·  {fmt(prize)}"
        ft = _font(26, bold=True)
        tw = c.d.textlength(tail, font=ft)
        c.d.text((W - PAD - tw, c.y + 4), tail, font=ft, fill=PINK_SOFT if place == 1 else (202, 214, 227))
        c.y += 60
        c.d.line([(PAD, c.y - 2), (W - PAD, c.y - 2)], fill=HAIR, width=1)
        c.gap(8)
    if not x["podium"]:
        c.row("Podium", "bu oy rejadan oshgan agent yo'q", value_color=RED, divider=False)

    c.section("Qo'shimcha sovrinlar")
    if x.get("growth"):
        gn, gp, gpr = x["growth"]
        c.row("Eng zo'r o'sish", f"{gn} · +{gp:.0f}% · {fmt(gpr)}", value_color=GREEN)
    for name, blocks, bonus in x.get("toy_winners", []):
        c.row(f"Happy Toy · {name}", f"{blocks:.0f} blok · {fmt(bonus)}",
              value_color=PINK_SOFT, divider=False)

    c.callout(x.get("note", "Yangi oy — yangi o'yin: hamma noldan boshlaydi!"), "pink", label="")
    c.footer("Vazvratlar hisobga olingan yakuniy natija. 1-o'rin ketma-ket 2 oy berilmaydi.")
    return c.png()
