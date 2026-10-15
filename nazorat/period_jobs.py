"""
period_jobs.py — «oy varaqasi» vazifalari (5-bosqich): NAMUNA va E'LON QILISH.

Web dastur bu ishlarni O'ZI qilmaydi — `nz_jobs` ga vazifa qo'yadi, nazorat boti
bajaradi (yagona yozuvchi qoidasi + Telegram faqat botda bor).

Ikki vazifa:
  • `period_preview` — qoralama ball plani bilan HAQIQIY karta chiziladi va admin
    Telegramiga yuboriladi. llm-council talabi: egasi forma xulosasini emas,
    agent ko'radigan RASMNI ko'rib tasdiqlasin.
  • `period_publish` — varaqa MUZLATILADI (checksum) + adminga tasdiq xabari.
    Sovrin o'chirilgan bo'lsa — BALAND E'LON matni ham beriladi (jimgina
    o'chirish motivatsiyani o'ldiradi).
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from telegram.error import TelegramError

from db import get_conn

from . import period, roster
from .nz_config import ADMIN_IDS, TIMEZONE

logger = logging.getLogger("nazorat.period_jobs")


def _now() -> str:
    return datetime.now(ZoneInfo(TIMEZONE)).isoformat(timespec="seconds")


def _today() -> date:
    return datetime.now(ZoneInfo(TIMEZONE)).date()


async def _to_admins(app, text: str = "", photo: bytes | None = None,
                     caption: str | None = None) -> None:
    for aid in ADMIN_IDS:
        try:
            if photo is not None:
                await app.bot.send_photo(aid, photo, caption=caption, parse_mode="HTML")
            else:
                await app.bot.send_message(aid, text, parse_mode="HTML")
        except TelegramError as e:
            logger.warning("admin %s: %s", aid, e)


# ------------------------------------------------------------------
# NAMUNA
# ------------------------------------------------------------------

async def preview(app, ym: str) -> str:
    """Qoralama bilan haqiqiy kartani chizib adminga yuboradi."""
    from .build import DayContext
    from .cards import render_ball_card

    period.parse_period(ym)
    today = _today()
    with get_conn() as conn:
        row = period.get_row(conn, ym)
        if not row:
            raise LookupError(f"{period.month_label(ym)} varaqasi yo'q.")
        draft = period.plans_of(conn, ym)
        agents = roster.active_agents(conn, day=today)
        view = period.sheet_view(conn, ym, agents, today)

    # Kartani BUGUNGI ma'lumot bilan, LEKIN yangi ball plani bilan chizamiz —
    # agent 1-avgustda aynan shunday ko'radi.
    dc = DayContext(today=today, plan_override=draft)
    changed = [r for r in view["rows"] if r["changed"] and not r["observe"]]
    target = None
    for r in (changed or view["rows"]):
        if r["sd_id"] in dc.snap and not r["observe"]:
            target = r
            break
    if target is None:
        raise LookupError("Namuna uchun mos agent topilmadi.")

    card = dc.evening_cards(target["sd_id"])[0]
    png = render_ball_card(card)

    lines = [f"👀 <b>{period.month_label(ym)} — NAMUNA</b>",
             "",
             f"Mana shu karta <b>{target['name']}</b> ga qanday ko'rinadi:",
             f"• ball plani: <b>{target['was']} → {target['ball_plan']}</b>",
             ""]
    if view["changed_count"]:
        lines.append(f"Jami <b>{view['changed_count']} ta</b> agentda ball plani o'zgardi.")
    else:
        lines.append("Hech qaysi agentda ball plani o'zgarmagan.")
    if not view["prizes_enabled"]:
        lines.append("🚫 <b>Sovrin tizimi O'CHIRILGAN</b> — podium va o'sish sovrini bo'lmaydi.")
    lines += ["", "Agar to'g'ri bo'lsa — dasturda <b>«E'LON QILISH»</b> tugmasini bosing.",
              "E'lon qilingach varaqa muzlaydi va o'zgartirib bo'lmaydi."]

    await _to_admins(app, photo=png,
                     caption=f"👀 {period.month_label(ym)} namunasi · {target['name']}")
    await _to_admins(app, text="\n".join(lines))
    return f"namuna yuborildi ({target['name']})"


# ------------------------------------------------------------------
# E'LON QILISH (muzlatish)
# ------------------------------------------------------------------

async def publish(app, ym: str, by: str = "web") -> str:
    """Varaqani muzlatadi va adminga tasdiq yuboradi."""
    today = _today()
    with get_conn() as conn:
        agents = roster.active_agents(conn, day=today)
        view = period.sheet_view(conn, ym, agents, today)
        chk = period.publish(conn, ym, agents, by, _now())
        prizes = view["prizes_enabled"]

    ver = view.get("version", 1)
    head = (f"✅ <b>{period.month_label(ym)} varaqasi E'LON QILINDI</b>" if ver <= 1
            else f"✏️ <b>{period.month_label(ym)} varaqasi TUZATILDI</b> ({ver}-nusxa)")
    lines = [head,
             "",
             f"• {len(view['rows'])} ta agent · {view['changed_count']} tasida ball plani o'zgardi",
             f"• Kuchga kiradi: <b>{view['starts'][8:10]}.{view['starts'][5:7]}."
             f"{view['starts'][:4]}</b> dan",
             f"• Muhr: <code>{chk}</code>"]
    if not prizes:
        lines += ["", "🚫 <b>Sovrin tizimi o'chirildi.</b> Podium va o'sish sovrini "
                      "bu oydan boshlab e'lon qilinmaydi. Agentlarga buni "
                      "<b>ochiq aytish kerak</b> — jimgina o'chirish ishonchni yo'qotadi."]
    if view.get("can_fix") or not view.get("is_over"):
        lines += ["", "Xato bo'lsa — <b>«✏️ Tuzatish»</b> tugmasi bilan shu oyni "
                      "hali ham to'g'rilashingiz mumkin (oy tugagunicha)."]
    else:
        lines += ["", "Bu oy tugagan — varaqa endi <b>muzlagan</b>."]
    await _to_admins(app, text="\n".join(lines))
    return f"e'lon qilindi v{ver} ({chk})"


# ------------------------------------------------------------------
# TUZATISHGA OCHILDI — adminga bildirish
# ------------------------------------------------------------------

async def reopened(app, ym: str, version: int) -> str:
    """E'lon qilingan varaqa tuzatishga ochilganini adminga bildiradi.

    Nega kerak: agentlar ESKI raqamlarni allaqachon ko'rgan. Tuzatish jimgina
    o'tib ketmasin — egasi qayta e'lon qilishni UNUTMASIN."""
    await _to_admins(app, text=(
        f"✏️ <b>{period.month_label(ym)} varaqasi tuzatishga ochildi</b> "
        f"({version}-nusxa tayyorlanmoqda).\n\n"
        f"⚠️ Hozir bu oy uchun <b>e'lon qilingan reja YO'Q</b> — agentlar avvalgi "
        f"oy rejasini ko'radi.\n"
        f"O'zgartirishni tugatgach <b>«E'LON QILISH»</b> ni bosing."))
    return f"tuzatishga ochildi (v{version})"
