"""
cards.py — nazorat botining rasm-kartalari (Pillow, PNG bytes).
Dizayn: tasdiqlangan maket — qora fon, Siribom pushti + lime aksentlar.

Barcha render_* funksiyalari SOF: tayyor dict oladi, PNG bytes qaytaradi.
Ma'lumot yig'ish data.py'da — bu yerda faqat chizish.
"""

from __future__ import annotations

import os
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

# ------------------------------------------------------------------
# Palitra (maketdan)
# ------------------------------------------------------------------

BG = (10, 15, 22)            # karta foni
EDGE = (29, 40, 54)          # chegara
TRACK = (27, 38, 52)         # progress yo'lak / chiziqlar
TEXT = (233, 240, 248)       # asosiy matn
SUB = (143, 163, 183)        # ikkinchi darajali matn
MUTED = (95, 113, 136)       # xira matn (footer)
PINK = (255, 92, 157)        # Siribom pushti
PINK_LIGHT = (255, 107, 168)
LIME = (198, 241, 53)        # Siribom lime
OK = (74, 222, 128)          # yashil
WARN = (255, 201, 77)        # sariq
BAD = (255, 122, 122)        # qizil


def _mix(a, b, t: float):
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))


# Yarim shaffof fonlar (oldindan aralashtirilgan)
PILL_OK_BG = _mix(BG, OK, 0.16)
PILL_WARN_BG = _mix(BG, WARN, 0.16)
PILL_BAD_BG = _mix(BG, BAD, 0.16)
PILL_LIME_BG = _mix(BG, LIME, 0.16)
HL_LIME_BG = _mix(BG, LIME, 0.10)
HL_LIME_EDGE = _mix(BG, LIME, 0.32)
HL_OK_BG = _mix(BG, OK, 0.10)
HL_OK_EDGE = _mix(BG, OK, 0.30)
HL_WARN_BG = _mix(BG, WARN, 0.09)
HL_WARN_EDGE = _mix(BG, WARN, 0.30)
ME_ROW_BG = _mix(BG, PINK, 0.09)

W = 1080                     # karta kengligi (2x — Telegram'da tiniq)
PAD = 56


# ------------------------------------------------------------------
# Shriftlar (Railway Linux + macOS + Windows)
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


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for p in (_FONT_BOLD if bold else _FONT_REG):
        if os.path.exists(p):
            try:
                # Helvetica.ttc: index 1 = Bold
                if p.endswith(".ttc") and bold:
                    return ImageFont.truetype(p, size, index=1)
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def fmt(n: float) -> str:
    """1234567 → '1 234 567'"""
    try:
        return f"{int(round(n)):,}".replace(",", " ")
    except (ValueError, TypeError):
        return "0"


def _sanitize(s: str) -> str:
    """Shriftda yo'q belgilarni almashtiradi (→, emoji kvadrat bo'lib chiqmasin)."""
    return (s.replace("→", "»").replace("✅", "").replace("⚠️", "")
             .replace("🔴", "").replace("🟡", "").strip())


# ------------------------------------------------------------------
# Karta chizish asosi
# ------------------------------------------------------------------

class Card:
    """Yuqoridan pastga qator-qator chiziladigan karta. Oxirida kesib olinadi."""

    def __init__(self, height_guess: int = 2400):
        self.img = Image.new("RGB", (W, height_guess), BG)
        self.d = ImageDraw.Draw(self.img)
        self.y = PAD

    # --- primitivlar ---

    def gap(self, h: int = 16):
        self.y += h

    def kicker(self, left: str, right: str = ""):
        """Yuqori satr: chapda 'SIRIBOM · ...' (pushti nuqta), o'ngda sana."""
        f = _font(26, bold=True)
        self.d.text((PAD, self.y), "SIRIBOM", font=f, fill=PINK_LIGHT)
        w1 = self.d.textlength("SIRIBOM", font=f)
        self.d.text((PAD + w1, self.y), f" · {left}", font=f, fill=SUB)
        if right:
            wr = self.d.textlength(right, font=f)
            self.d.text((W - PAD - wr, self.y), right, font=f, fill=SUB)
        self.y += 40

    def title(self, name: str, sub: str = ""):
        self.d.text((PAD, self.y), name, font=_font(46, bold=True), fill=(255, 255, 255))
        self.y += 62
        if sub:
            self.d.text((PAD, self.y), sub, font=_font(27), fill=SUB)
            self.y += 42

    def divider(self):
        self.gap(14)
        self.d.line([(PAD, self.y), (W - PAD, self.y)], fill=TRACK, width=2)
        self.gap(18)

    def big(self, value: str, suffix: str, color=PINK_LIGHT):
        """Katta raqam: '+3 ball' + yonida izoh."""
        f = _font(84, bold=True)
        self.d.text((PAD, self.y), value, font=f, fill=color)
        wv = self.d.textlength(value, font=f)
        self.d.text((PAD + wv + 20, self.y + 42), suffix, font=_font(28), fill=SUB)
        self.y += 104

    def row(self, label: str, value: str, value_color=TEXT, label_color=SUB):
        f_l, f_v = _font(29), _font(30, bold=True)
        self.d.text((PAD, self.y), label, font=f_l, fill=label_color)
        wv = self.d.textlength(value, font=f_v)
        self.d.text((W - PAD - wv, self.y - 2), value, font=f_v, fill=value_color)
        self.y += 46

    def bar_row(self, label: str, frac: float, right: str, fill=PINK):
        """Chapda label, o'rtada progress, o'ngda qiymat."""
        f_l, f_v = _font(27), _font(28, bold=True)
        label_w = 210
        right_w = 190
        self.d.text((PAD, self.y), label, font=f_l, fill=SUB)
        bar_x = PAD + label_w
        bar_w = W - PAD - right_w - bar_x - 20
        bar_y = self.y + 12
        self.d.rounded_rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + 14], 7, fill=TRACK)
        fw = max(int(bar_w * min(max(frac, 0), 1)), 8 if frac > 0 else 0)
        if fw:
            self.d.rounded_rectangle([bar_x, bar_y, bar_x + fw, bar_y + 14], 7, fill=fill)
        wv = self.d.textlength(right, font=f_v)
        self.d.text((W - PAD - wv, self.y), right, font=f_v, fill=TEXT)
        self.y += 50

    def pill(self, x: int, text: str, bg, fg) -> int:
        """Kichik rangli plashka. Qaytaradi: kengligi."""
        f = _font(26, bold=True)
        tw = self.d.textlength(text, font=f)
        w = int(tw + 36)
        self.d.rounded_rectangle([x, self.y, x + w, self.y + 44], 12, fill=bg)
        self.d.text((x + 18, self.y + 7), text, font=f, fill=fg)
        return w

    def pills(self, items: list[tuple[str, tuple, tuple]]):
        """Bir qatorda bir nechta plashka: [(matn, bg, fg)]"""
        x = PAD
        for text, bg, fg in items:
            x += self.pill(x, text, bg, fg) + 14
        self.y += 58

    def list_row(self, left: str, right: str, right_color=TEXT, left_sub: str = "",
                 left_sub_color=MUTED, dashed: bool = True):
        """Do'kon — summa qatori (nuqtali ajratgich bilan)."""
        f_l, f_v, f_s = _font(28), _font(29, bold=True), _font(23)
        self.d.text((PAD, self.y), left, font=f_l, fill=(199, 211, 225))
        lw = self.d.textlength(left, font=f_l)
        if left_sub:
            self.d.text((PAD + lw + 12, self.y + 4), left_sub, font=f_s, fill=left_sub_color)
        wv = self.d.textlength(right, font=f_v)
        self.d.text((W - PAD - wv, self.y - 1), right, font=f_v, fill=right_color)
        self.y += 44
        if dashed:
            for x in range(PAD, W - PAD, 14):
                self.d.line([(x, self.y), (x + 6, self.y)], fill=TRACK, width=1)
            self.y += 12

    def rank_row(self, pos: str, name: str, pill_text: str, pill_bg, pill_fg,
                 tail: str = "", highlight: bool = False):
        """Reyting qatori: o'rin, ism, ball plashkasi, (summa)."""
        row_h = 58
        if highlight:
            self.d.rounded_rectangle(
                [PAD - 16, self.y - 8, W - PAD + 16, self.y + row_h - 12], 10, fill=ME_ROW_BG)
        f_p, f_n = _font(26), _font(30, bold=True)
        self.d.text((PAD, self.y + 8), pos, font=f_p, fill=SUB)
        self.d.text((PAD + 56, self.y + 4), name, font=f_n,
                    fill=(255, 214, 231) if highlight else (221, 230, 240))
        # o'ng tomonda: [pill] tail
        f_t = _font(24)
        tail_w = self.d.textlength(tail, font=f_t) if tail else 0
        f_pl = _font(26, bold=True)
        pw = int(self.d.textlength(pill_text, font=f_pl) + 36)
        px = W - PAD - int(tail_w) - (18 if tail else 0) - pw
        self.d.rounded_rectangle([px, self.y, px + pw, self.y + 42], 11, fill=pill_bg)
        self.d.text((px + 18, self.y + 6), pill_text, font=f_pl, fill=pill_fg)
        if tail:
            self.d.text((W - PAD - tail_w, self.y + 9), tail, font=f_t, fill=SUB)
        self.y += row_h

    def _wrap(self, text: str, font, max_w: int) -> list[str]:
        words = text.split()
        lines, cur = [], ""
        for w_ in words:
            trial = (cur + " " + w_).strip()
            if self.d.textlength(trial, font=font) <= max_w:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = w_
        if cur:
            lines.append(cur)
        return lines

    def highlight(self, text: str, scheme: str = "lime"):
        """Rangli ramkali blok (Eng foydali harakat / izoh)."""
        bg, edge, fg = {
            "lime": (HL_LIME_BG, HL_LIME_EDGE, _mix(LIME, (255, 255, 255), 0.25)),
            "ok": (HL_OK_BG, HL_OK_EDGE, _mix(OK, (255, 255, 255), 0.3)),
            "warn": (HL_WARN_BG, HL_WARN_EDGE, _mix(WARN, (255, 255, 255), 0.2)),
        }[scheme]
        f = _font(28)
        lines = self._wrap(_sanitize(text), f, W - 2 * PAD - 56)
        h = 30 + len(lines) * 40 + 8
        self.gap(10)
        self.d.rounded_rectangle([PAD, self.y, W - PAD, self.y + h], 14,
                                 fill=bg, outline=edge, width=2)
        ty = self.y + 20
        for ln in lines:
            self.d.text((PAD + 28, ty), ln, font=f, fill=fg)
            ty += 40
        self.y += h + 12

    def footer(self, text: str):
        f = _font(23)
        for ln in self._wrap(text, f, W - 2 * PAD):
            self.d.text((PAD, self.y), ln, font=f, fill=MUTED)
            self.y += 32

    # --- yakun ---

    def png(self) -> bytes:
        h = self.y + PAD
        img = self.img.crop((0, 0, W, h))
        # tashqi chegara
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([1, 1, W - 2, h - 2], 24, outline=EDGE, width=2)
        buf = BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()


def ball_pill_colors(ball: int) -> tuple[tuple, tuple]:
    """Ball → (fon, matn) ranglari."""
    if ball >= 4:
        return PILL_OK_BG, OK
    if ball == 3:
        return PILL_LIME_BG, LIME
    if ball >= 1:
        return PILL_WARN_BG, WARN
    return PILL_BAD_BG, BAD


# ==================================================================
# 1. KECHKI ASOSIY KARTA (20:00, shaxsiy)
# ==================================================================

def render_evening_card(x: dict) -> bytes:
    """
    x: name, league_label, date_label, ball_today, today_sales, today_pct,
       month_ball, ball_plan, prognoz_ball, per_day_needed,
       growth_pct (None bo'lishi mumkin), kpi_pct, kpi_gap ( (summa,bonus) | None ),
       returns_today, returns_month_pct, debt, debt_limit, action (str | None),
       observe_only (bool)
    """
    c = Card()
    c.kicker("kechki hisobot", x["date_label"])
    c.title(x["name"], x["league_label"] +
            (" · kuzatuv rejimi" if x.get("observe_only") else f" · plan {x['ball_plan']} ball"))

    c.big(f"+{x['ball_today']} ball",
          f"bugun: {fmt(x['today_sales'])} · reja {x['today_pct']:.0f}%")

    plan = max(x["ball_plan"], 1)
    c.bar_row("Oy balli", x["month_ball"] / plan,
              f"{x['month_ball']} / {x['ball_plan']}" if x["ball_plan"] else f"{x['month_ball']}",
              fill=PINK)

    if not x.get("observe_only") and x["ball_plan"]:
        gap = x["prognoz_ball"] - x["ball_plan"]
        gap_txt = (f"plandan {abs(gap):.0f} kam" if gap < 0
                   else f"plandan +{gap:.0f}")
        c.row(f"Prognoz: ~{x['prognoz_ball']:.0f} ball",
              gap_txt, value_color=(WARN if gap < 0 else OK))
        if gap < 0 and x["per_day_needed"] > 0:
            c.row("Plandan oshish uchun",
                  f"kuniga {x['per_day_needed']:.1f} ball kerak")

    c.divider()

    if x.get("growth_pct") is not None:
        g = x["growth_pct"]
        c.row("O'sish (o'tgan oyga)",
              f"{g:+.0f}%" + ("  ·  sovrin yo'lida" if g >= 10 else ""),
              value_color=(OK if g >= 10 else (WARN if g >= 0 else BAD)))

    c.bar_row("KPI plan", x["kpi_pct"] / 100, f"{x['kpi_pct']:.0f}%", fill=LIME)
    if x.get("kpi_gap"):
        need, bonus = x["kpi_gap"]
        c.row("Keyingi pog'onaga", f"{fmt(need)} qoldi  = +{fmt(bonus)}",
              value_color=LIME)

    ret_col = OK if x["returns_month_pct"] < 3 else (WARN if x["returns_month_pct"] < 6 else BAD)
    c.row("Vazvrat", f"bugun {fmt(x['returns_today'])} · oyda {x['returns_month_pct']:.1f}%",
          value_color=ret_col)

    debt_ok = x["debt"] <= x["debt_limit"]
    c.row("Qarz", f"{fmt(x['debt'])} / {fmt(x['debt_limit'])}",
          value_color=(OK if debt_ok else BAD))

    if x.get("action"):
        c.highlight("Eng foydali harakat: " + x["action"], "lime")

    if x.get("observe_only"):
        c.footer("Kuzatuv rejimi: birinchi to'liq oy — ball hisoblanadi, plan va sovrinlar keyingi oydan.")
    return c.png()


# ==================================================================
# 2. OYLIK PLAN KARTASI (20:00, shaxsiy — eski suratning yangi ko'rinishi)
# ==================================================================

def render_plan_card(x: dict) -> bytes:
    """
    x: name, date_label, month_label, wd_total, wd_passed, wd_remaining,
       sales_plan, sales_done, plan_pct, plan_remaining, prognoz, prognoz_pct,
       daily_required, today_sales, today_pct,
       visit_plan, visits_done, visit_remaining, visit_daily_required, today_visits,
       status_text, status_scheme ('ok'/'warn'/'lime')
    """
    c = Card()
    c.kicker("oylik plan", x["date_label"])
    c.title(x["name"],
            f"{x['month_label']} · ish kuni {x['wd_total']} · ishlandi {x['wd_passed']} · qoldi {x['wd_remaining']}")

    c.row("Oylik plan", fmt(x["sales_plan"]))
    pct = x["plan_pct"]
    pill_bg, pill_fg = (PILL_OK_BG, OK) if pct >= 100 else \
        (PILL_LIME_BG, LIME) if pct >= 80 else \
        (PILL_WARN_BG, WARN) if pct >= 50 else (PILL_BAD_BG, BAD)
    f_l = _font(29)
    c.d.text((PAD, c.y), "Bajarildi", font=f_l, fill=SUB)
    txt = f"{fmt(x['sales_done'])} · {pct:.0f}%"
    f_v = _font(28, bold=True)
    pw = int(c.d.textlength(txt, font=f_v) + 36)
    c.d.rounded_rectangle([W - PAD - pw, c.y - 6, W - PAD, c.y + 38], 12, fill=pill_bg)
    c.d.text((W - PAD - pw + 18, c.y), txt, font=f_v, fill=pill_fg)
    c.y += 52

    c.row("Qoldiq (bajarish kerak)", fmt(x["plan_remaining"]))

    ppct = x["prognoz_pct"]
    prog_col = OK if ppct >= 100 else (WARN if ppct >= 80 else BAD)
    c.row("Prognoz", f"{fmt(x['prognoz'])} · {ppct:.0f}%", value_color=prog_col)
    c.row("Kunlik bajarish kerak", fmt(x["daily_required"]))
    tcol = OK if x["today_pct"] >= 100 else (WARN if x["today_pct"] >= 50 else BAD)
    c.row("Bugun bajarildi", f"{fmt(x['today_sales'])} · {x['today_pct']:.0f}%", value_color=tcol)

    c.divider()

    c.row(f"Vizit plani: {x['visit_plan']}",
          f"bajarildi {x['visits_done']} · qoldi {x['visit_remaining']}")
    vcol = OK if x["today_visits"] >= x["visit_daily_required"] else WARN
    c.row(f"Vizit kunlik kerak: {x['visit_daily_required']:.0f}",
          f"bugun {x['today_visits']}", value_color=vcol)

    c.highlight(x["status_text"], x.get("status_scheme", "ok"))
    return c.png()


# ==================================================================
# 3. HAPPY TOY KARTASI (20:00, shaxsiy)
# ==================================================================

def render_toy_card(x: dict) -> bytes:
    """
    x: name, date_label, blocks, tiers [(blocks,bonus)...] o'sish tartibida,
       reached_bonus, next_blocks, next_bonus, to_next, per_day_needed
    """
    c = Card()
    c.kicker("happy toy", x["date_label"])
    c.title(x["name"], "Sotilgan, qaytmagan bloklar sanaladi · 1 blok = 24 dona")

    c.big(f"{x['blocks']:.0f} blok", "shu oyda sotilgan · qaytmagan", color=LIME)

    first_tier = x["tiers"][0][0] if x["tiers"] else 105
    c.bar_row("1-daraja", x["blocks"] / first_tier,
              f"{x['blocks']:.0f} / {first_tier:.0f}", fill=LIME)
    c.divider()

    for blocks, bonus in x["tiers"]:
        reached = x["blocks"] >= blocks
        is_next = (x.get("next_blocks") == blocks)
        f_n = _font(30, bold=True)
        # doira raqami
        ring = OK if reached else (PINK if is_next else TRACK)
        c.d.ellipse([PAD, c.y, PAD + 54, c.y + 54], outline=ring, width=4)
        bt = f"{blocks:.0f}"
        bw = c.d.textlength(bt, font=_font(24, bold=True))
        c.d.text((PAD + 27 - bw / 2, c.y + 13), bt, font=_font(24, bold=True),
                 fill=(OK if reached else (PINK_LIGHT if is_next else SUB)))
        # nomi
        c.d.text((PAD + 78, c.y - 2), f"{fmt(bonus)} bonus", font=f_n,
                 fill=(255, 255, 255) if (reached or is_next) else SUB)
        sub = ("olindi ✓" if reached else
               (f"{x['to_next']:.0f} blok qoldi — kuniga {x['per_day_needed']:.1f}"
                if is_next else "keyingi daraja"))
        c.d.text((PAD + 78, c.y + 34), sub, font=_font(24),
                 fill=(OK if reached else (LIME if is_next else MUTED)))
        c.y += 84

    if x.get("reached_bonus"):
        c.highlight(f"Hozirgacha kafolatlangan bonus: {fmt(x['reached_bonus'])} so'm. "
                    f"Keyingi darajagacha to'xtama!", "ok")
    c.footer("Bonus faqat yetkazilgan va qaytmagan mahsulotga to'lanadi.")
    return c.png()


# ==================================================================
# 4. ERTALABKI QARZ/VAZVRAT KARTASI (10:00, shaxsiy)
# ==================================================================

def render_morning_card(x: dict) -> bytes:
    """
    x: name, league_label, date_label,
       returns [(shop, summa)], returns_total,
       ball_note (str|None),
       debts [(shop, summa, age_days|None)], debt_total, debt_limit, debt_more (int)
    """
    c = Card()
    c.kicker("ertalabki hisobot", x["date_label"])
    c.title(x["name"], x["league_label"])

    c.row("Kecha kelgan vazvratlar",
          f"−{fmt(x['returns_total'])}" if x["returns_total"] else "yo'q",
          value_color=(BAD if x["returns_total"] else OK), label_color=(185, 198, 214))
    for shop, summa in x["returns"][:6]:
        c.list_row(shop, fmt(summa), right_color=BAD)

    if x.get("ball_note"):
        c.highlight(x["ball_note"], "warn")

    c.divider()

    c.row("Qarz qoldig'i", fmt(x["debt_total"]), label_color=(185, 198, 214))
    for shop, summa, age in x["debts"][:7]:
        age_txt = f"· {age} kun" if age else ""
        age_col = BAD if (age or 0) >= 10 else MUTED
        c.list_row(shop, fmt(summa), left_sub=age_txt, left_sub_color=age_col)
    if x.get("debt_more"):
        c.list_row(f"yana {x['debt_more']} ta do'kon", "", dashed=False)

    frac = x["debt_total"] / x["debt_limit"] if x["debt_limit"] else 0
    col = OK if frac <= 0.8 else (WARN if frac <= 1 else BAD)
    c.bar_row(f"Limit {fmt(x['debt_limit'])}", frac, f"{frac * 100:.0f}%", fill=col)
    c.footer("Eng eski qarz qizil bilan belgilanadi. To'liq ro'yxat — «Qarz» tugmasida.")
    return c.png()


# ==================================================================
# 5. GURUH — KUNLIK BALLAR REYTINGI (20:00)
# ==================================================================

def render_group_daily(x: dict) -> bytes:
    """
    x: league_label, date_label, rows [(name, ball, sales)], streak_note (str|None)
    Oylik yig'indi KO'RSATILMAYDI (maxfiy).
    """
    c = Card()
    c.kicker("kunlik ballar", x["date_label"])
    c.title(x["league_label"], "Bugungi natijalar · ball teng bo'lsa summa hal qiladi")
    c.divider()

    for i, (name, ball, sales) in enumerate(x["rows"], 1):
        bg, fg = ball_pill_colors(ball)
        c.rank_row(str(i), name, f"{ball} ball", bg, fg, tail=fmt(sales))

    if x.get("streak_note"):
        c.highlight(x["streak_note"], "lime")
    c.footer("Oylik yig'indi maxfiy — g'oliblar oy yakunida e'lon qilinadi.")
    return c.png()


# ==================================================================
# 6. ADMIN SVODKA (10:00 va 20:00)
# ==================================================================

def render_admin_summary(x: dict) -> bytes:
    """
    x: title ('kechki svodka · shahar'), date_label,
       rows [(name, sales, ball, plan_pct, toy, debt_mln, debt_frac)],
       debt_frac — qarz/limit nisbati (rang uchun),
       signals [('bad'|'warn'|'info', text)]
    """
    c = Card()
    c.kicker(x["title"], x["date_label"])
    c.gap(8)

    # jadval sarlavhasi
    cols = [(PAD, "Agent"), (470, "Savdo"), (640, "Ball"), (740, "Plan"),
            (850, "Toy"), (950, "Qarz")]
    f_h = _font(22, bold=True)
    for cx, label in cols:
        c.d.text((cx, c.y), label.upper(), font=f_h, fill=MUTED)
    c.y += 38
    c.d.line([(PAD, c.y), (W - PAD, c.y)], fill=TRACK, width=2)
    c.y += 14

    f_n, f_v = _font(27, bold=True), _font(26)
    for name, sales, ball, plan_pct, toy, debt_mln, debt_frac in x["rows"]:
        c.d.text((PAD, c.y), name[:22], font=f_n, fill=(237, 243, 250))
        scol = BAD if sales == 0 else (214, 224, 236)
        c.d.text((470, c.y + 1), fmt(sales), font=f_v, fill=scol)
        c.d.text((640, c.y + 1), str(ball), font=f_v, fill=(214, 224, 236))
        pcol = OK if plan_pct >= 80 else (WARN if plan_pct >= 50 else BAD)
        c.d.text((740, c.y + 1), f"{plan_pct:.0f}%", font=f_v, fill=pcol)
        c.d.text((850, c.y + 1), f"{toy:.0f}", font=f_v, fill=(214, 224, 236))
        dcol = BAD if debt_frac > 1 else (WARN if debt_frac >= 0.9 else (214, 224, 236))
        c.d.text((950, c.y + 1), f"{debt_mln:.1f}", font=f_v, fill=dcol)
        c.y += 46
        c.d.line([(PAD, c.y - 6), (W - PAD, c.y - 6)], fill=_mix(BG, TRACK, 0.5), width=1)

    if x.get("signals"):
        c.gap(14)
        for level, text in x["signals"]:
            scheme = {"bad": "warn", "warn": "warn", "info": "ok"}[level]
            c.highlight(text, scheme)

    c.footer("Qarz — mln so'mda (90%+ limit sariq, oshgan qizil).")
    return c.png()


# ==================================================================
# 7. OY YAKUNI — KATTA REVEAL (guruhga, tasdiqdan keyin)
# ==================================================================

def render_month_final(x: dict) -> bytes:
    """
    x: league_label, month_label,
       podium [(place, name, total_ball, over, prize)],
       growth (name, pct, prize) | None,
       toy_winners [(name, blocks, bonus)],
       note (str)
    """
    c = Card()
    c.kicker(f"{x['month_label']} yakuni", "G'OLIBLAR")
    c.title(x["league_label"], "Oy bo'yi maxfiy saqlangan yig'indi — mana natija!")
    c.divider()

    medal_colors = {1: (255, 214, 90), 2: (200, 208, 220), 3: (222, 156, 96)}
    for place, name, total_ball, over, prize in x["podium"]:
        col = medal_colors.get(place, SUB)
        f_m = _font(34, bold=True)
        c.d.text((PAD, c.y), f"{place}-o'rin", font=f_m, fill=col)
        c.d.text((PAD + 190, c.y), name, font=_font(34, bold=True),
                 fill=(255, 255, 255) if place == 1 else (225, 233, 242))
        tail = f"{total_ball} ball (+{over}) · {fmt(prize)}"
        f_t = _font(27, bold=True)
        tw = c.d.textlength(tail, font=f_t)
        c.d.text((W - PAD - tw, c.y + 5), tail, font=f_t,
                 fill=LIME if place == 1 else (200, 212, 225))
        c.y += 62

    if not x["podium"]:
        c.row("Podium", "bu oy plandan oshgan agent yo'q", value_color=WARN)

    c.divider()
    if x.get("growth"):
        gname, gpct, gprize = x["growth"]
        c.row("Eng zo'r o'sish", f"{gname} · +{gpct:.0f}% · {fmt(gprize)}", value_color=OK)
    for name, blocks, bonus in x.get("toy_winners", []):
        c.row("Happy Toy", f"{name} · {blocks:.0f} blok · {fmt(bonus)}", value_color=LIME)

    c.highlight(x.get("note", "Yangi oy — yangi o'yin: hamma noldan boshlaydi!"), "lime")
    c.footer("Vazvratlar hisobga olingan yakuniy natija. 1-o'rin qoidasi: "
             "bitta agent ketma-ket 2 oy yutolmaydi.")
    return c.png()
