"""
cards.py — Siribom Nazorat botining rasm-kartalari (Pillow, PNG bytes).

Dizayn: premium tungi karta. Siribom logosi brend langari,
pushti — asosiy urg'u (bitta muhim raqam), lime — ijobiy/pul,
har metrik qatordan keyin nozik ajratgich chiziq (toza jadval ko'rinishi).

Barcha render_* funksiyalari SOF: tayyor dict oladi, PNG bytes qaytaradi.
Ma'lumot yig'ish data.py/build.py'da — bu yerda faqat chizish.
"""

from __future__ import annotations

import os
from functools import lru_cache
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

# ------------------------------------------------------------------
# Palitra (professional tungi — Luxe Dark)
# ------------------------------------------------------------------

BG = (13, 18, 26)            # karta foni (chuqur ko'mir-ko'k)
BG2 = (17, 23, 33)           # ichki panel (bir pog'ona ochiqroq)
EDGE = (32, 43, 58)          # tashqi chegara
HAIR = (26, 34, 47)          # qatorlar orasidagi nozik chiziq
TRACK = (30, 41, 56)         # progress yo'lak
TEXT = (236, 242, 249)       # asosiy matn
SUB = (144, 164, 186)        # ikkinchi darajali
MUTED = (98, 116, 138)       # xira (izoh/footer)
PINK = (255, 78, 151)        # Siribom pushti (asosiy urg'u)
PINK_LT = (255, 125, 176)
LIME = (200, 240, 60)        # Siribom lime
OK = (70, 224, 138)
WARN = (255, 196, 77)
BAD = (255, 107, 107)
GOLD = (255, 214, 90)


def _mix(a, b, t):
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))


PILL_OK = _mix(BG, OK, 0.18)
PILL_WARN = _mix(BG, WARN, 0.18)
PILL_BAD = _mix(BG, BAD, 0.18)
PILL_LIME = _mix(BG, LIME, 0.18)
PILL_PINK = _mix(BG, PINK, 0.20)
HL_LIME = (_mix(BG, LIME, 0.11), _mix(BG, LIME, 0.34), _mix(LIME, (255, 255, 255), 0.30))
HL_OK = (_mix(BG, OK, 0.11), _mix(BG, OK, 0.32), _mix(OK, (255, 255, 255), 0.35))
HL_WARN = (_mix(BG, WARN, 0.10), _mix(BG, WARN, 0.32), _mix(WARN, (255, 255, 255), 0.25))
HL_PINK = (_mix(BG, PINK, 0.12), _mix(BG, PINK, 0.34), PINK_LT)
ME_ROW = _mix(BG, PINK, 0.10)

W = 1080
PAD = 60

_ASSETS = os.path.join(os.path.dirname(__file__), "assets")


@lru_cache(maxsize=4)
def _logo(height: int) -> Image.Image | None:
    p = os.path.join(_ASSETS, "logo.png")
    if not os.path.exists(p):
        return None
    im = Image.open(p).convert("RGBA")
    s = height / im.height
    return im.resize((int(im.width * s), height), Image.LANCZOS)


# ------------------------------------------------------------------
# Shriftlar
# ------------------------------------------------------------------

_FONT_REG = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:/Windows/Fonts/arial.ttf",
]
_FONT_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:/Windows/Fonts/arialbd.ttf",
]


@lru_cache(maxsize=64)
def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
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


def _sanitize(s: str) -> str:
    for a, b in (("→", "»"), ("✅", ""), ("⚠️", ""), ("🔴", ""), ("🟡", ""),
                 ("✓", ""), ("↩️", ""), ("🏆", ""), ("🔥", ""), ("🎯", "")):
        s = s.replace(a, b)
    return s.strip()


# ==================================================================
# Karta chizish asosi
# ==================================================================

class Card:
    def __init__(self, height_guess: int = 2600):
        self.img = Image.new("RGB", (W, height_guess), BG)
        self.d = ImageDraw.Draw(self.img)
        self.y = PAD

    # --- header: logo + kicker + sana + sarlavha ---

    def header(self, kicker: str, date_label: str, title: str, subtitle: str = "",
               accent=PINK_LT):
        logo = _logo(64)
        lx = PAD
        if logo is not None:
            self.img.paste(logo, (PAD, self.y), logo)
            lx = PAD + logo.width + 22
        # kicker (logo yonida, yuqorida)
        fk = _font(23, bold=True)
        self.d.text((lx, self.y + 6), kicker.upper(), font=fk, fill=accent)
        # sana (o'ng yuqori)
        fd = _font(25, bold=True)
        dw = self.d.textlength(date_label, font=fd)
        self.d.text((W - PAD - dw, self.y + 8), date_label, font=fd, fill=SUB)
        # kicker ostida ingichka izoh chizig'i uchun joy
        self.d.text((lx, self.y + 36), "AGENTLAR NAZORATI", font=_font(16, bold=True),
                    fill=MUTED)
        self.y += 84

        # sarlavha (katta ism)
        self.d.text((PAD, self.y), title, font=_font(48, bold=True), fill=(255, 255, 255))
        self.y += 62
        if subtitle:
            self.d.text((PAD, self.y), subtitle, font=_font(26), fill=SUB)
            self.y += 40
        self._section_line()

    def _section_line(self):
        self.gap(10)
        self.d.line([(PAD, self.y), (W - PAD, self.y)], fill=EDGE, width=2)
        self.gap(18)

    def gap(self, h=16):
        self.y += h

    def _hair(self):
        self.d.line([(PAD, self.y), (W - PAD, self.y)], fill=HAIR, width=1)

    # --- katta hero raqam ---

    def hero(self, value: str, suffix: str, color=PINK_LT):
        f = _font(88, bold=True)
        self.d.text((PAD, self.y), value, font=f, fill=color)
        wv = self.d.textlength(value, font=f)
        self.d.text((PAD + wv + 22, self.y + 46), suffix, font=_font(27), fill=SUB)
        self.y += 112
        self._hair()
        self.gap(16)

    # --- oddiy label/value qator + ajratgich ---

    def row(self, label: str, value: str, value_color=TEXT, label_color=SUB,
            divider=True, value_pill=None):
        f_l, f_v = _font(29), _font(30, bold=True)
        self.d.text((PAD, self.y), label, font=f_l, fill=label_color)
        if value_pill:
            bg, fg = value_pill
            pw = int(self.d.textlength(value, font=_font(28, bold=True)) + 34)
            self.d.rounded_rectangle([W - PAD - pw, self.y - 5, W - PAD, self.y + 39],
                                     11, fill=bg)
            self.d.text((W - PAD - pw + 17, self.y + 1), value,
                        font=_font(28, bold=True), fill=fg)
        else:
            wv = self.d.textlength(value, font=f_v)
            self.d.text((W - PAD - wv, self.y - 1), value, font=f_v, fill=value_color)
        self.y += 44
        if divider:
            self.gap(10)
            self._hair()
            self.gap(11)
        else:
            self.gap(8)

    def bar_row(self, label: str, frac: float, right: str, fill=PINK, divider=True):
        f_l = _font(27)
        label_w, right_w = 210, 200
        self.d.text((PAD, self.y + 2), label, font=f_l, fill=SUB)
        bx = PAD + label_w
        bw = W - PAD - right_w - bx
        by = self.y + 14
        self.d.rounded_rectangle([bx, by, bx + bw, by + 15], 8, fill=TRACK)
        fw = max(int(bw * min(max(frac, 0), 1)), 10 if frac > 0 else 0)
        if fw:
            self.d.rounded_rectangle([bx, by, bx + fw, by + 15], 8, fill=fill)
        fv = _font(28, bold=True)
        wv = self.d.textlength(right, font=fv)
        self.d.text((W - PAD - wv, self.y), right, font=fv, fill=TEXT)
        self.y += 46
        if divider:
            self.gap(10)
            self._hair()
            self.gap(11)
        else:
            self.gap(8)

    def section(self, label: str):
        """Bo'lim sarlavhasi (kichik uppercase)."""
        self.gap(6)
        self.d.text((PAD, self.y), label.upper(), font=_font(19, bold=True), fill=MUTED)
        self.y += 34

    def pill(self, x, text, bg, fg, y=None):
        yy = self.y if y is None else y
        f = _font(26, bold=True)
        w = int(self.d.textlength(text, font=f) + 36)
        self.d.rounded_rectangle([x, yy, x + w, yy + 44], 12, fill=bg)
        self.d.text((x + 18, yy + 7), text, font=f, fill=fg)
        return w

    def list_row(self, left, right, right_color=TEXT, sub="", sub_color=MUTED):
        f_l, f_v, f_s = _font(28), _font(29, bold=True), _font(22)
        self.d.text((PAD, self.y), left, font=f_l, fill=(206, 217, 230))
        lw = self.d.textlength(left, font=f_l)
        if sub:
            self.d.text((PAD + lw + 12, self.y + 5), sub, font=f_s, fill=sub_color)
        wv = self.d.textlength(right, font=f_v)
        self.d.text((W - PAD - wv, self.y - 1), right, font=f_v, fill=right_color)
        self.y += 42
        self.gap(8)
        self._hair()
        self.gap(9)

    def rank_row(self, pos, name, pill_text, pill_bg, pill_fg, tail="", highlight=False):
        rh = 62
        if highlight:
            self.d.rounded_rectangle([PAD - 18, self.y - 8, W - PAD + 18, self.y + rh - 14],
                                     12, fill=ME_ROW)
        self.d.text((PAD + 2, self.y + 9), pos, font=_font(27, bold=True), fill=SUB)
        self.d.text((PAD + 62, self.y + 5), name, font=_font(31, bold=True),
                    fill=(255, 210, 228) if highlight else (224, 233, 243))
        # Summa — o'ng chetga tekislangan (qat'iy ustun)
        ft = _font(24)
        if tail:
            tw = self.d.textlength(tail, font=ft)
            self.d.text((W - PAD - tw, self.y + 10), tail, font=ft, fill=SUB)
        # Ball plashkasi — qat'iy ustunda (o'ng chekka W-PAD-200), tekislangan
        fp = _font(26, bold=True)
        pw = int(self.d.textlength(pill_text, font=fp) + 34)
        pill_right = W - PAD - 210
        px = pill_right - pw
        self.d.rounded_rectangle([px, self.y + 2, pill_right, self.y + 44], 11, fill=pill_bg)
        self.d.text((px + 17, self.y + 8), pill_text, font=fp, fill=pill_fg)
        self.y += rh
        self._hair()

    def _wrap(self, text, font, max_w):
        out, cur = [], ""
        for w_ in text.split():
            t = (cur + " " + w_).strip()
            if self.d.textlength(t, font=font) <= max_w:
                cur = t
            else:
                if cur:
                    out.append(cur)
                cur = w_
        if cur:
            out.append(cur)
        return out

    def callout(self, text, scheme="lime", label="ENG FOYDALI HARAKAT"):
        bg, edge, fg = {"lime": HL_LIME, "ok": HL_OK, "warn": HL_WARN, "pink": HL_PINK}[scheme]
        f = _font(28)
        lines = self._wrap(_sanitize(text), f, W - 2 * PAD - 56)
        head_h = 32 if label else 6
        h = head_h + len(lines) * 40 + 26
        self.gap(14)
        self.d.rounded_rectangle([PAD, self.y, W - PAD, self.y + h], 16,
                                 fill=bg, outline=edge, width=2)
        ty = self.y + 18
        if label:
            self.d.text((PAD + 28, ty), label, font=_font(18, bold=True), fill=edge)
            ty += 32
        for ln in lines:
            self.d.text((PAD + 28, ty), ln, font=f, fill=fg)
            ty += 40
        self.y += h + 12

    def footer(self, text):
        self.gap(6)
        f = _font(22)
        for ln in self._wrap(_sanitize(text), f, W - 2 * PAD):
            self.d.text((PAD, self.y), ln, font=f, fill=MUTED)
            self.y += 31

    def png(self) -> bytes:
        h = self.y + PAD - 4
        img = self.img.crop((0, 0, W, h))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([1, 1, W - 2, h - 2], 26, outline=EDGE, width=2)
        buf = BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()


def ball_pill(ball: int):
    if ball >= 4:
        return PILL_OK, OK
    if ball == 3:
        return PILL_LIME, LIME
    if ball >= 1:
        return PILL_WARN, WARN
    return PILL_BAD, BAD


def _pct_pill(pct: float):
    if pct >= 100:
        return PILL_OK, OK
    if pct >= 80:
        return PILL_LIME, LIME
    if pct >= 50:
        return PILL_WARN, WARN
    return PILL_BAD, BAD


# ==================================================================
# 1. KECHKI ASOSIY KARTA
# ==================================================================

def render_evening_card(x: dict) -> bytes:
    c = Card()
    sub = (x["league_label"] + (" · kuzatuv rejimi" if x.get("observe_only")
           else f" · plan {x['ball_plan']} ball"))
    c.header("kechki hisobot", x["date_label"], x["name"], sub)

    c.hero(f"+{x['ball_today']} ball",
           f"bugun {fmt(x['today_sales'])} · reja {x['today_pct']:.0f}%")

    plan = max(x["ball_plan"], 1)
    c.bar_row("Oy balli", x["month_ball"] / plan,
              f"{x['month_ball']} / {x['ball_plan']}" if x["ball_plan"] else f"{x['month_ball']}",
              fill=PINK)

    if not x.get("observe_only") and x["ball_plan"]:
        gap = x["prognoz_ball"] - x["ball_plan"]
        c.row(f"Prognoz  ~{x['prognoz_ball']:.0f} ball",
              f"plandan {abs(gap):.0f} kam" if gap < 0 else f"plandan +{gap:.0f}",
              value_color=(WARN if gap < 0 else OK),
              divider=(gap >= 0 or x["per_day_needed"] <= 0))
        if gap < 0 and x["per_day_needed"] > 0:
            c.row("Plandan oshish uchun", f"kuniga {x['per_day_needed']:.1f} ball")

    c.section("Pul tizimlari")
    if x.get("growth_pct") is not None:
        g = x["growth_pct"]
        c.row("O'sish (o'tgan oyga)",
              f"{g:+.0f}%" + ("  ·  sovrin yo'lida" if g >= 10 else ""),
              value_color=(OK if g >= 10 else (WARN if g >= 0 else BAD)))
    c.bar_row("KPI plan", x["kpi_pct"] / 100, f"{x['kpi_pct']:.0f}%", fill=LIME)
    if x.get("kpi_gap"):
        need, bonus = x["kpi_gap"]
        c.row("Keyingi pog'onaga", f"{fmt(need)}  = +{fmt(bonus)}", value_color=LIME)

    rp = x["returns_month_pct"]
    c.row("Vazvrat", f"bugun {fmt(x['returns_today'])} · oyda {rp:.1f}%",
          value_color=(OK if rp < 3 else (WARN if rp < 6 else BAD)))
    debt_ok = x["debt"] <= x["debt_limit"]
    c.row("Qarz", f"{fmt(x['debt'])} / {fmt(x['debt_limit'])}",
          value_color=(OK if debt_ok else BAD), divider=False)

    if x.get("action"):
        c.callout(x["action"], "lime")
    if x.get("observe_only"):
        c.footer("Kuzatuv rejimi: birinchi to'liq oy — ball hisoblanadi, plan va sovrinlar keyingi oydan.")
    return c.png()


# ==================================================================
# 2. OYLIK PLAN KARTASI
# ==================================================================

def render_plan_card(x: dict) -> bytes:
    c = Card()
    c.header("oylik plan", x["date_label"], x["name"],
             f"{x['month_label']} · ish kuni {x['wd_total']} · ishlandi {x['wd_passed']} · qoldi {x['wd_remaining']}",
             accent=LIME)

    c.row("Oylik plan", fmt(x["sales_plan"]))
    c.row("Bajarildi", f"{fmt(x['sales_done'])} · {x['plan_pct']:.0f}%",
          value_pill=_pct_pill(x["plan_pct"]))
    c.row("Qoldiq (bajarish kerak)", fmt(x["plan_remaining"]))
    c.row("Prognoz", f"{fmt(x['prognoz'])} · {x['prognoz_pct']:.0f}%",
          value_pill=_pct_pill(x["prognoz_pct"]))
    c.row("Kunlik bajarish kerak", fmt(x["daily_required"]))
    c.row("Bugun bajarildi", f"{fmt(x['today_sales'])} · {x['today_pct']:.0f}%",
          value_pill=_pct_pill(x["today_pct"]), divider=False)

    c.section("Vizitlar")
    c.row("Vizit plani " + str(x["visit_plan"]),
          f"bajarildi {x['visits_done']} · qoldi {x['visit_remaining']}")
    vok = x["today_visits"] >= x["visit_daily_required"]
    c.row(f"Kunlik kerak {x['visit_daily_required']:.0f}",
          f"bugun {x['today_visits']}", value_color=(OK if vok else WARN), divider=False)

    c.callout(x["status_text"], x.get("status_scheme", "ok"), label="")
    return c.png()


# ==================================================================
# 3. HAPPY TOY
# ==================================================================

def render_toy_card(x: dict) -> bytes:
    c = Card()
    c.header("happy toy", x["date_label"], x["name"],
             "Sotilgan, qaytmagan bloklar · 1 blok = 24 dona", accent=LIME)

    c.hero(f"{x['blocks']:.0f} blok", "shu oyda · qaytmagan", color=LIME)

    first = x["tiers"][0][0] if x["tiers"] else 105
    c.bar_row("1-daraja", x["blocks"] / first, f"{x['blocks']:.0f} / {first:.0f}",
              fill=LIME, divider=False)
    c.section("Bonus darajalari")

    for i, (blocks, bonus) in enumerate(x["tiers"]):
        reached = x["blocks"] >= blocks
        is_next = (x.get("next_blocks") == blocks)
        ring = OK if reached else (PINK if is_next else TRACK)
        c.d.ellipse([PAD, c.y, PAD + 56, c.y + 56], outline=ring, width=4)
        bt = f"{blocks:.0f}"
        bw = c.d.textlength(bt, font=_font(24, bold=True))
        c.d.text((PAD + 28 - bw / 2, c.y + 14), bt, font=_font(24, bold=True),
                 fill=(OK if reached else (PINK_LT if is_next else SUB)))
        c.d.text((PAD + 82, c.y - 2), f"{fmt(bonus)} bonus", font=_font(31, bold=True),
                 fill=(255, 255, 255) if (reached or is_next) else SUB)
        s = ("olindi" if reached else
             (f"{x['to_next']:.0f} blok qoldi · kuniga {x['per_day_needed']:.1f}"
              if is_next else "keyingi daraja"))
        c.d.text((PAD + 82, c.y + 34), s, font=_font(24),
                 fill=(OK if reached else (LIME if is_next else MUTED)))
        c.y += 86
        if i < len(x["tiers"]) - 1:
            c._hair()
            c.gap(8)

    if x.get("reached_bonus"):
        c.callout(f"Hozirgacha kafolatlangan bonus: {fmt(x['reached_bonus'])} so'm. "
                  f"Keyingi darajagacha to'xtama!", "ok", label="")
    c.footer("Bonus faqat yetkazilgan va qaytmagan mahsulotga to'lanadi.")
    return c.png()


# ==================================================================
# 4. ERTALABKI QARZ/VAZVRAT
# ==================================================================

def render_morning_card(x: dict) -> bytes:
    c = Card()
    c.header("ertalabki hisobot", x["date_label"], x["name"], x["league_label"])

    c.section("Kecha kelgan vazvratlar")
    if x["returns"]:
        for shop, summa in x["returns"][:6]:
            c.list_row(shop, fmt(summa), right_color=BAD)
        c.row("Jami vazvrat", f"−{fmt(x['returns_total'])}", value_color=BAD, divider=False)
    else:
        c.row("Vazvrat", "yo'q", value_color=OK, divider=False)
    if x.get("ball_note"):
        c.callout(x["ball_note"], "warn", label="BALL O'ZGARDI")

    c.section("Qarz qoldig'i")
    for shop, summa, age in x["debts"][:7]:
        age_txt = f"· {age} kun" if age else ""
        c.list_row(shop, fmt(summa), sub=age_txt,
                   sub_color=(BAD if (age or 0) >= 10 else MUTED))
    if x.get("debt_more"):
        c.row(f"yana {x['debt_more']} ta do'kon", "", divider=False)
    frac = x["debt_total"] / x["debt_limit"] if x["debt_limit"] else 0
    col = OK if frac <= 0.8 else (WARN if frac <= 1 else BAD)
    c.bar_row(f"Limit {fmt(x['debt_limit'])}", frac, f"{frac*100:.0f}%", fill=col, divider=False)
    c.footer("Eng eski qarz qizil bilan. To'liq ro'yxat — «Qarz» tugmasida.")
    return c.png()


# ==================================================================
# 5. GURUH — KUNLIK BALLAR REYTINGI
# ==================================================================

def render_group_daily(x: dict) -> bytes:
    c = Card()
    c.header("kunlik ballar", x["date_label"], x["league_label"],
             "Bugungi natijalar · ball teng bo'lsa summa hal qiladi")
    for i, (name, ball, sales) in enumerate(x["rows"], 1):
        bg, fg = ball_pill(ball)
        c.rank_row(str(i), name, f"{ball} ball", bg, fg, tail=fmt(sales))
    c.gap(6)
    if x.get("streak_note"):
        c.callout(x["streak_note"], "lime", label="SERIYA")
    c.footer("Oylik yig'indi maxfiy — g'oliblar oy yakunida e'lon qilinadi.")
    return c.png()


# ==================================================================
# 6. ADMIN SVODKA
# ==================================================================

def render_admin_summary(x: dict) -> bytes:
    c = Card()
    logo = _logo(56)
    if logo is not None:
        c.img.paste(logo, (PAD, c.y), logo)
    fk = _font(23, bold=True)
    c.d.text((PAD + (logo.width + 20 if logo else 0), c.y + 4),
             x["title"].upper(), font=fk, fill=PINK_LT)
    dw = c.d.textlength(x["date_label"], font=fk)
    c.d.text((W - PAD - dw, c.y + 6), x["date_label"], font=fk, fill=SUB)
    c.y += 76
    c.d.line([(PAD, c.y), (W - PAD, c.y)], fill=EDGE, width=2)
    c.gap(16)

    cols = [(PAD, "Agent"), (452, "Savdo"), (642, "Ball"), (742, "Plan"),
            (858, "Toy"), (958, "Qarz")]
    for cx, label in cols:
        c.d.text((cx, c.y), label.upper(), font=_font(20, bold=True), fill=MUTED)
    c.y += 36
    c._hair()
    c.gap(8)

    fn, fv = _font(27, bold=True), _font(26)
    for name, sales, ball, plan_pct, toy, debt_mln, frac in x["rows"]:
        c.d.text((PAD, c.y), name[:20], font=fn, fill=(237, 243, 250))
        c.d.text((452, c.y + 1), fmt(sales), font=fv, fill=(BAD if sales == 0 else (214, 224, 236)))
        c.d.text((642, c.y + 1), str(ball), font=fv, fill=(214, 224, 236))
        pcol = OK if plan_pct >= 80 else (WARN if plan_pct >= 50 else BAD)
        c.d.text((742, c.y + 1), f"{plan_pct:.0f}%", font=fv, fill=pcol)
        c.d.text((858, c.y + 1), f"{toy:.0f}", font=fv, fill=(214, 224, 236))
        dcol = BAD if frac > 1 else (WARN if frac >= 0.9 else (214, 224, 236))
        c.d.text((958, c.y + 1), f"{debt_mln:.1f}", font=fv, fill=dcol)
        c.y += 48
        c._hair()
    c.gap(12)

    for level, text in x.get("signals", []):
        c.callout(text, "warn" if level != "info" else "ok", label="")
    c.footer("Qarz — mln so'mda (90%+ sariq, oshgan qizil).")
    return c.png()


# ==================================================================
# 7. OY YAKUNI — REVEAL
# ==================================================================

def render_month_final(x: dict) -> bytes:
    c = Card()
    c.header(f"{x['month_label']} yakuni", "G'OLIBLAR", x["league_label"],
             "Oy bo'yi maxfiy saqlangan yig'indi — mana natija!", accent=GOLD)

    medals = {1: GOLD, 2: (200, 208, 220), 3: (222, 156, 96)}
    for place, name, total_ball, over, prize in x["podium"]:
        col = medals.get(place, SUB)
        c.d.text((PAD, c.y), f"{place}-o'rin", font=_font(35, bold=True), fill=col)
        c.d.text((PAD + 196, c.y), name, font=_font(35, bold=True),
                 fill=(255, 255, 255) if place == 1 else (226, 234, 243))
        tail = f"{total_ball} ball (+{over})  ·  {fmt(prize)}"
        ft = _font(27, bold=True)
        tw = c.d.textlength(tail, font=ft)
        c.d.text((W - PAD - tw, c.y + 5), tail, font=ft,
                 fill=LIME if place == 1 else (202, 214, 227))
        c.y += 64
        c._hair()
        c.gap(6)
    if not x["podium"]:
        c.row("Podium", "bu oy plandan oshgan agent yo'q", value_color=WARN, divider=False)

    c.section("Qo'shimcha sovrinlar")
    if x.get("growth"):
        gn, gp, gpr = x["growth"]
        c.row("Eng zo'r o'sish", f"{gn} · +{gp:.0f}% · {fmt(gpr)}", value_color=OK)
    for name, blocks, bonus in x.get("toy_winners", []):
        c.row(f"Happy Toy · {name}", f"{blocks:.0f} blok · {fmt(bonus)}",
              value_color=LIME, divider=False)

    c.callout(x.get("note", "Yangi oy — yangi o'yin: hamma noldan boshlaydi!"), "pink", label="")
    c.footer("Vazvratlar hisobga olingan yakuniy natija. 1-o'rin ketma-ket 2 oy berilmaydi.")
    return c.png()
