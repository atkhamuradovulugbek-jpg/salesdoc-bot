"""
aksiya_cards.py — agent uchun AKSIYA kartalari (egasi tasdiqlagan, 2026-10-07).

2026-10-08 20:10 (Asia/Tashkent) dan agentga kechki to'plam:
  1) BUGUNGI NATIJA — sof savdo, liga faol agentlari ichida SAVDO bo'yicha o'rin,
     oldingi ish kuni bilan taqqos, kunlik aksiya soni va aksiya mukofoti (ball YO'Q)
  2) OYLIK SAVDO REJA — o'zgarmagan (cards.render_plan_card)
  3) OYLIK AKSIYA DAFTARI — oy kunlari bo'yicha aksiya (dona) / mukofot (so'm) + JAMI
Happy Toy kartasi agentga BORMAYDI (supervayzer/admin/web o'zgarmaydi).

Hisob — Monitordagi `aksiya_jadval` (aynan o'sha funksiyalar, qayta yozilmagan):
bitta do'kon + bitta kun sof savdosi (status 1,2,3, qaytim asl buyurtma/kundan ayirilgan)
→ floor(max(net,0)/300 000); agent kuni = do'kon bloklari yig'indisi; kunlik mukofot
bir marta yaxlitlanadi; OYLIK mukofot = kunlik yaxlitlangan mukofotlar yig'indisi.

Ikki sana ARALASHMASIN:
  BUSINESS_START — aksiya hisobi shu kundan (undan oldingi kunlar daftarda «—»)
  ACTIVATION     — yangi kartalar agentga shu paytdan yuboriladi
"""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import aksiya_jadval as aj
from db import get_conn

from . import icons
from .cards import (EDGE, GREEN, MUTED, PAD, PINK, PINK_SOFT, SUB, TILE, TILE2, WHITE, W,
                    ME_ROW, Card, _font, fmt, render_plan_card)
from .data import MONTHS_UZ

TZ = ZoneInfo("Asia/Tashkent")
BUSINESS_START = date(2026, 10, 5)
START_LABEL = "5-oktabr 2026"                      # egasi tasdiqlagan yozuv
ACTIVATION = datetime(2026, 10, 8, 20, 10, tzinfo=TZ)

WEEKDAYS = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]
WD_SHORT = ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"]
ZEBRA = (15, 21, 30)


def active(now: datetime | None = None) -> bool:
    """Yangi agent kartalari yoqilganmi (Toshkent vaqti bilan)."""
    return (now or datetime.now(TZ)) >= ACTIVATION


# ------------------------------------------------------------------
# Ma'lumot
# ------------------------------------------------------------------

def _agent_start(ag) -> date:
    return date.fromisoformat(ag.start_date) if getattr(ag, "start_date", None) else date.min


def eligible_from(ag) -> date:
    """Aksiya hisobi shu agent uchun qaysi kundan (biznes start yoki o'rindiq sanasi)."""
    return max(BUSINESS_START, _agent_start(ag))


def full_name(conn, ag) -> tuple[str, str]:
    """Sales Doctor'dagi JORIY to'liq ism + hudud ("Ism Familiya (Hudud)").
    O'rindiq almashganda YAML ismi eski bo'ladi — shuning uchun bazadan olinadi."""
    row = conn.execute("SELECT name FROM agents WHERE sd_id=?", (ag.sd_id,)).fetchone()
    raw = " ".join(((row[0] if row else "") or "").split())
    m = re.match(r"^(.*?)\s*\((.*?)\)\s*$", raw)
    if m and m.group(1).strip():
        return m.group(1).strip(), " ".join(m.group(2).split()) or ag.area
    return (raw or ag.name), ag.area


def _orders(conn, sd_id: str, dfrom: date, dto: date) -> list[dict]:
    rows = conn.execute(
        """SELECT sd_id, agent_sd_id, client_sd_id, date, status,
                  total_after_discount, total_returns
           FROM orders WHERE agent_sd_id=? AND date>=? AND date<=?""",
        (sd_id, dfrom.isoformat(), dto.isoformat())).fetchall()
    return [{"id": r[0], "agent": r[1], "shop": r[2], "day": r[3], "status": r[4],
             "total": float(r[5] or 0), "returns": float(r[6] or 0)} for r in rows]


def day_result(conn, sd_id: str, day: date, league: str) -> tuple[int, int]:
    """(aksiya soni, mukofot so'm) — bitta agent, bitta kun."""
    n = aj.agent_units(_orders(conn, sd_id, day, day)).get(sd_id, 0)
    return n, aj.reward(n, league)


def league_day_net(conn, sd_ids: list[str], day: date) -> dict[str, float]:
    """Liga agentlarining shu kungi SOF savdosi (status 1,2,3, qaytim ayirilgan)."""
    net = {s: 0.0 for s in sd_ids}
    if not sd_ids:
        return net
    ph = ",".join("?" * len(sd_ids))
    st = ",".join(str(s) for s in aj.VALID_STATUSES)
    for sd, v in conn.execute(
            f"""SELECT agent_sd_id, COALESCE(SUM(total_after_discount - total_returns), 0)
                FROM orders WHERE date=? AND status IN ({st}) AND agent_sd_id IN ({ph})
                GROUP BY agent_sd_id""", (day.isoformat(), *sd_ids)):
        net[sd] = float(v or 0)
    return net


def _rank(net: dict[str, float], sd_id: str) -> int | None:
    """O'rin = 1 + o'zidan KO'P sotganlar soni. Hech kim sotmagan kun — o'rin yo'q."""
    if not any(v > 0 for v in net.values()):
        return None
    me = net.get(sd_id, 0.0)
    return 1 + sum(1 for v in net.values() if v > me)


def prev_workday(day: date, sunday_off: bool = True) -> date:
    d = day - timedelta(days=1)
    while sunday_off and d.weekday() == 6:
        d -= timedelta(days=1)
    return d


def _data_time(conn) -> datetime:
    """Buyurtmalar oxirgi marta qachon yangilangan (qarz sync'lari hisobga olinmaydi)."""
    row = conn.execute("""SELECT run_at FROM sync_log WHERE status='ok' AND type NOT LIKE '%debt%'
                          ORDER BY id DESC LIMIT 1""").fetchone()
    try:
        return datetime.fromisoformat(row[0]).astimezone(TZ)
    except (TypeError, ValueError):
        return datetime.now(TZ)


def _league_label(league: str) -> str:
    return "Shahar ligasi" if league == "city" else "Viloyat ligasi"


def daily_dict(dc, sd_id: str, word: str = "bugun") -> dict:
    """BUGUNGI (word='bugun') yoki KECHAGI (word='kecha') NATIJA — dc.today kuni uchun."""
    day = dc.today
    s = dc.snap[sd_id]
    ag, league = s.agent, s.league
    peers = [p.agent.sd_id for p in dc.by_league[league] if not p.agent.observe_only]
    prev = prev_workday(day, getattr(dc.rules, "sunday_off", True))
    with get_conn() as conn:
        name, area = full_name(conn, ag)
        net = league_day_net(conn, peers, day)
        pnet = league_day_net(conn, peers, prev)
        counted = day >= eligible_from(ag)
        n, x = day_result(conn, sd_id, day, league) if counted else (None, None)
    rank = _rank(net, sd_id)
    prank = _rank(pnet, sd_id) if (rank and prev >= _agent_start(ag)) else None
    if word == "bugun" and prev == day - timedelta(days=1):
        prev_label = "Kecha"
    else:
        prev_label = f"{WEEKDAYS[prev.weekday()]} kuni"
    return {
        "word": word, "name": name, "area": area, "league_label": _league_label(league),
        "date_label": f"{day.day}-{MONTHS_UZ[day.month].upper()} {day.year}",
        "sales": net.get(sd_id, 0.0), "rank": rank, "prev_rank": prank,
        "prev_label": prev_label, "league_size": len(peers), "units": n, "reward": x,
    }


def ledger_dict(dc, sd_id: str, now: datetime | None = None) -> dict:
    """OYLIK AKSIYA DAFTARI — dc.today oyi, dc.today gacha haqiqiy hisob."""
    day = dc.today
    now = now or datetime.now(TZ)
    s = dc.snap[sd_id]
    ag, league = s.agent, s.league
    first = day.replace(day=1)
    last = calendar.monthrange(day.year, day.month)[1]
    elig = eligible_from(ag)
    with get_conn() as conn:
        name, area = full_name(conn, ag)
        orders = _orders(conn, sd_id, max(first, elig), day) if elig <= day else []
        data_time = _data_time(conn)
    by_day: dict[str, list[dict]] = {}
    for o in orders:
        by_day.setdefault(o["day"], []).append(o)
    rows = []
    for d in range(1, last + 1):
        dd = date(day.year, day.month, d)
        if dd < elig or dd > day:
            rows.append((dd, None, None))
            continue
        n = aj.agent_units(by_day.get(dd.isoformat(), [])).get(sd_id, 0)
        rows.append((dd, n, aj.reward(n, league)))
    counted = [r for r in rows if r[1] is not None]
    month = MONTHS_UZ[day.month].lower()
    notes = []
    if elig.year == day.year and elig.month == day.month and elig.day > 1:
        why = "aksiya boshlanishidan oldin" if elig == BUSINESS_START else "hisobingiz boshlanishidan oldin"
        notes.append(f"1–{elig.day - 1} {month}: {why}.")
    if counted:
        a, b = counted[0][0].day, counted[-1][0].day
        span = f"{a}–{b}" if a != b else f"{a}"
        if day == now.astimezone(TZ).date():
            when = f"{day:%d.%m} ma'lumoti {data_time:%H:%M} holatiga, kun yakuni emas"
        else:
            when = f"ma'lumot {data_time:%d.%m %H:%M} holatiga"
        notes.append(f"{span} {month}: haqiqiy buyurtmalar ({when}).")
    if day.day < last:
        notes.append(f"{day.day + 1}–{last}: hali kelmagan kunlar.")
    return {
        "name": name, "area": area, "league_label": _league_label(league),
        "month_label": f"{MONTHS_UZ[day.month].upper()} {day.year}",
        "start_note": (f"Aksiya boshlangan sana: {START_LABEL}"
                       if (BUSINESS_START.year, BUSINESS_START.month) == (day.year, day.month) else ""),
        "today": day, "rows": rows,
        "total_units": sum(r[1] for r in counted), "total_reward": sum(r[2] for r in counted),
        "footer": " ".join(notes),
    }


# ------------------------------------------------------------------
# Rasm (tasdiqlangan namunalar uslubi: Siribom, qora fon, pushti urg'u)
# ------------------------------------------------------------------

def rank_message(tr: int | None, pr: int | None, prev_label: str, word: str):
    """O'rin o'zgarishi matni: (matn, rang, sarlavha, ikonka) yoki None.
    1-o'rin saqlansa — «yuqoriga chiqing» DEYILMAYDI."""
    if not tr or not pr:
        return None
    if tr == 1 and pr == 1:
        return ("Birinchi o'rinni saqladingiz. Barakalla, shu natijani davom ettiring!",
                "green", "O'RINNI SAQLADINGIZ", "check")
    if tr < pr:
        return (f"{prev_label} {pr}-o'rinda edingiz, {word} {tr}-o'ringa ko'tarildingiz. Barakalla!",
                "green", "O'RIN KO'TARILDI", "sales")
    if tr > pr:
        return (f"{prev_label} {pr}-o'rinda edingiz, {word} {tr}-o'rindasiz. "
                f"Ertaga o'rningizni qaytarishga harakat qiling!",
                "red", "O'RIN TUSHDI", "sales_down")
    return (f"{prev_label} ham {pr}-o'rinda edingiz. Bir pog'ona yuqoriga ko'tarilishga harakat qiling!",
            "pink", "O'RIN O'ZGARMADI", "target")


def _fit(c: Card, text: str, size: int, min_size: int, max_w: float, bold: bool = True):
    while size > min_size and c.d.textlength(text, font=_font(size, bold=bold)) > max_w:
        size -= 1
    return _font(size, bold=bold)


def _header(c: Card, kicker: str, date_label: str, title: str, subtitle: str):
    """cards.Card.header bilan bir xil, faqat uzun ism/hudud kesilmasin."""
    from .cards import _logo
    logo = _logo(58)
    lx = PAD
    if logo is not None:
        c.img.paste(logo, (PAD, c.y + 2), logo)
        lx = PAD + logo.width + 20
    c.d.text((lx, c.y + 14), kicker.upper(), font=_font(24, bold=True), fill=PINK_SOFT)
    fd = _font(24, bold=True)
    c.d.text((W - PAD - c.d.textlength(date_label, font=fd), c.y + 16), date_label, font=fd, fill=SUB)
    c.y += 78
    c.d.rounded_rectangle([PAD, c.y + 4, PAD + 8, c.y + 58], 4, fill=PINK)
    c.d.text((PAD + 26, c.y), title, font=_fit(c, title, 46, 28, W - 2 * PAD - 26), fill=WHITE)
    c.y += 58
    if subtitle:
        fs = _fit(c, subtitle, 26, 18, W - 2 * PAD - 26, bold=False)
        c.d.text((PAD + 26, c.y), subtitle, font=fs, fill=SUB)
        c.y += 40
    c.gap(20)


def render_daily(x: dict) -> bytes:
    bugun = x["word"] == "bugun"
    adj = "BUGUNGI" if bugun else "KECHAGI"
    c = Card()
    _header(c, f"{adj.lower()} natija", x["date_label"], x["name"],
            f"{x['area']} · {x['league_label']}" if x["area"] else x["league_label"])

    # SAVDO
    h = 140
    c.d.rounded_rectangle([PAD, c.y, W - PAD, c.y + h], 18, fill=TILE2)
    c.d.text((PAD + 34, c.y + 28), f"{adj} SAVDO", font=_font(21, bold=True), fill=MUTED)
    c.d.text((PAD + 34, c.y + 62), f"{fmt(x['sales'])} so'm", font=_font(48, bold=True), fill=WHITE)
    c.y += h + 16

    # O'RIN (savdo bo'yicha)
    if x["rank"]:
        h_r = 92
        c.d.rounded_rectangle([PAD, c.y, W - PAD, c.y + h_r], 16, fill=TILE)
        icons.draw(c.d, "trophy", PAD + 34, c.y + h_r // 2, 16, PINK_SOFT, 3)
        c.d.text((PAD + 72, c.y + 24), f"{adj} SAVDO BO'YICHA O'RNINGIZ",
                 font=_font(19, bold=True), fill=MUTED)
        c.d.text((PAD + 72, c.y + 48), f"{x['league_label']} faol agentlari orasida",
                 font=_font(22), fill=SUB)
        fr = _font(52, bold=True)
        rt = f"{x['rank']}"
        c.d.text((W - PAD - 34 - c.d.textlength(rt, font=fr) - 130, c.y + 18), rt, font=fr, fill=PINK)
        c.d.text((W - PAD - 34 - 118, c.y + 26), "-o'rin", font=_font(30, bold=True), fill=PINK_SOFT)
        c.d.text((W - PAD - 34 - 118, c.y + 62), f"/ {x['league_size']} agent", font=_font(20), fill=MUTED)
        c.y += h_r + 12

        msg = rank_message(x["rank"], x["prev_rank"], x["prev_label"], x["word"])
        if msg:
            text, scheme, label, icon = msg
            c.callout(text, scheme, label=label, icon=icon)

    # AKSIYA
    c.gap(4)
    h_a = 196
    c.d.rounded_rectangle([PAD, c.y, W - PAD, c.y + h_a], 18, fill=TILE2)
    icons.draw(c.d, "kpi", PAD + 34, c.y + 44, 16, PINK_SOFT, 3)
    c.d.text((PAD + 72, c.y + 30), f"{adj} AKSIYA", font=_font(21, bold=True), fill=MUTED)
    x0 = PAD + 34
    if x["units"] is None:
        c.d.text((x0, c.y + 96), "Bu kun aksiya hisobiga kirmaydi", font=_font(30), fill=SUB)
    else:
        f1, f1b = _font(34), _font(34, bold=True)
        for txt, f, col in ((f"Siz {x['word']} ", f1, WHITE), (f"{x['units']} ta", f1b, PINK),
                            (" aksiya sotdingiz", f1, WHITE)):
            c.d.text((x0, c.y + 70), txt, font=f, fill=col)
            x0 += c.d.textlength(txt, font=f)
        lab = f"{adj.capitalize()} aksiya mukofotingiz: "
        f2, f2b = _font(30), _font(34, bold=True)
        c.d.text((PAD + 34, c.y + 129), lab, font=f2, fill=SUB)
        c.d.text((PAD + 34 + c.d.textlength(lab, font=f2), c.y + 126), f"{fmt(x['reward'])} so'm",
                 font=f2b, fill=GREEN)
    c.y += h_a + 6
    return c.png()


def render_ledger(x: dict) -> bytes:
    c = Card()
    _header(c, "oylik aksiya daftari", x["month_label"], x["name"],
            f"{x['area']} · {x['league_label']}" if x["area"] else x["league_label"])
    if x["start_note"]:
        c.d.text((PAD, c.y - 10), x["start_note"], font=_font(21), fill=MUTED)
        c.y += 26

    X_DATE, X_N, X_R = PAD + 24, PAD + 470, W - PAD - 24
    hh = 52
    c.d.rounded_rectangle([PAD, c.y, W - PAD, c.y + hh], 12, fill=TILE2)
    fh = _font(21, bold=True)
    c.d.text((X_DATE, c.y + 15), "SANA", font=fh, fill=MUTED)
    lab = "AKSIYA (DONA)"
    c.d.text((X_N - c.d.textlength(lab, font=fh) / 2, c.y + 15), lab, font=fh, fill=MUTED)
    lab = "MUKOFOT (SO'M)"
    c.d.text((X_R - c.d.textlength(lab, font=fh), c.y + 15), lab, font=fh, fill=MUTED)
    c.y += hh + 6

    RH = 40
    fd, fdb, fv, fvb = _font(25), _font(25, bold=True), _font(26), _font(26, bold=True)
    for i, (dd, n, r) in enumerate(x["rows"]):
        is_today, empty, sunday = dd == x["today"], n is None, dd.weekday() == 6
        if is_today:
            c.d.rounded_rectangle([PAD, c.y - 2, W - PAD, c.y + RH - 2], 10, fill=ME_ROW)
        elif i % 2 == 1:
            c.d.rectangle([PAD, c.y - 2, W - PAD, c.y + RH - 2], fill=ZEBRA)
        dcol = PINK_SOFT if is_today else (MUTED if (empty or sunday) else SUB)
        c.d.text((X_DATE, c.y + 5), f"{dd.day:02d}.{dd.month:02d}  {WD_SHORT[dd.weekday()]}",
                 font=fdb if is_today else fd, fill=dcol)
        if empty:
            nt, rt, ncol, rcol, f_n, f_r = "—", "—", MUTED, MUTED, fv, fv
        else:
            nt, rt = str(n), fmt(r)
            ncol, f_n = (WHITE, fvb) if n > 0 else (MUTED, fv)
            rcol, f_r = (GREEN, fvb) if r > 0 else (MUTED, fv)
        c.d.text((X_N - c.d.textlength(nt, font=f_n) / 2, c.y + 4), nt, font=f_n, fill=ncol)
        c.d.text((X_R - c.d.textlength(rt, font=f_r), c.y + 4), rt, font=f_r, fill=rcol)
        c.y += RH

    c.y += 8
    c.d.line([(PAD, c.y), (W - PAD, c.y)], fill=EDGE, width=2)
    c.y += 10
    jh = 68
    c.d.rounded_rectangle([PAD, c.y, W - PAD, c.y + jh], 14, fill=TILE2)
    fj, fjv = _font(28, bold=True), _font(34, bold=True)
    c.d.text((X_DATE, c.y + 19), "JAMI", font=fj, fill=WHITE)
    t = str(x["total_units"])
    c.d.text((X_N - c.d.textlength(t, font=fjv) / 2, c.y + 14), t, font=fjv, fill=PINK)
    t = f"{fmt(x['total_reward'])} so'm"
    c.d.text((X_R - c.d.textlength(t, font=fjv), c.y + 14), t, font=fjv, fill=GREEN)
    c.y += jh + 14
    if x["footer"]:
        c.footer(x["footer"])
    return c.png()


# ------------------------------------------------------------------
# Agentga yuboriladigan to'plam
# ------------------------------------------------------------------

def agent_cards(dc, sd_id: str, word: str = "bugun") -> list[bytes]:
    """[natija, oylik savdo reja, oylik aksiya daftari] — Happy Toy YO'Q."""
    return [render_daily(daily_dict(dc, sd_id, word)),
            render_plan_card(dc.snap[sd_id].plan_dict()),
            render_ledger(ledger_dict(dc, sd_id))]


# ------------------------------------------------------------------
# Agent «Yordam» — FAQAT o'z ligasi tarifi (egasi qarori 2026-10-07)
# ------------------------------------------------------------------

_LEAGUE_HELP = {"city": ("shahar", "5 000", "100 000÷15"),
                "region": ("viloyat", "4 000", "80 000÷15")}


def help_text(league: str | None, reveal: str) -> str:
    """Agentga shaxsiy qoidalar. Liga noma'lum bo'lsa — tarif ko'rsatilmaydi (ikkalasi ham emas)."""
    head = ("<b>Siribom Nazorat — qoidalar</b>\n\n"
            f"📊 <b>Har kuni {reveal} da:</b> bugungi natija, oylik savdo reja va oylik aksiya daftari.\n"
            f"🎁 <b>Aksiya ({START_LABEL} dan):</b> bitta do'konning bir kunlik sof savdosi — yaroqli "
            "buyurtmalar, qaytim asl savdo kunidan ayiriladi. Har to'liq 300 000 so'm = 1 aksiya. "
            "Turli do'kon va turli kunlar qo'shilmaydi, qoldiq ertaga o'tmaydi, bekor qilingan "
            "buyurtma hisoblanmaydi.\n")
    if league in _LEAGUE_HELP:
        name, r1, r2 = _LEAGUE_HELP[league]
        mid = (f"💰 <b>Kunlik aksiya mukofoti ({name} ligasi):</b>\n"
               "• 10 tadan kam — 0 so'm\n"
               f"• 10–14 ta — har biriga {r1} so'm (masalan, 10 ta = {fmt(aj.reward(10, league))} so'm)\n"
               f"• 15 ta va ko'proq — har biriga {r2} so'm "
               f"(masalan, 15 ta = {fmt(aj.reward(15, league))} so'm)\n"
               "Kunlik mukofot kun yakunida bir marta so'mga yaxlitlanadi.\n")
    else:
        mid = ("💰 <b>Kunlik aksiya mukofoti</b> ligangizga bog'liq — ligangiz aniqlanmadi. "
               "Rahbaringizga murojaat qiling.\n")
    tail = ("📒 <b>Oylik daftar:</b> kunlik aksiya va mukofotlar; oylik jami — kunlik mukofotlar "
            "yig'indisi.\n"
            "💵 <b>KPI:</b> oylik plan bajarilishiga qarab komissiya + bonus.\n"
            "💳 <b>Qarz:</b> limitdan oshmasin.\n\n"
            "Pastdagi tugmalardan foydalaning 👇")
    return head + mid + tail


def ledger_caption(dc) -> str:
    return f"📒 Oylik aksiya daftari · {MONTHS_UZ[dc.today.month]} {dc.today.year}"
