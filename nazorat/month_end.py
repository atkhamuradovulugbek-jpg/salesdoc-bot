"""
month_end.py — oy yakuni: 2 kun vazvrat kutib, 3-kuni yakuniy hisob.
Adminga tasdiqlash uchun yuboriladi; admin /tasdiqla bosgach agentlarga/guruhga e'lon.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from telegram.error import TelegramError
from telegram.ext import Application

from db import get_conn

from . import storage
from .build import DayContext, prev_month
from .cards import render_month_final
from .core.rules import load_rules
from .nz_config import ADMIN_IDS, DRY_RUN, GROUP_CITY_CHAT_ID, GROUP_REGION_CHAT_ID

logger = logging.getLogger("nazorat.month_end")


def _now() -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Asia/Tashkent")).isoformat(timespec="seconds")


def _month_label(m: int) -> str:
    from .data import MONTHS_UZ
    return MONTHS_UZ[m].upper()


def compute_month_final(year: int, month: int) -> dict[str, dict]:
    """
    O'tgan oy uchun har liga bo'yicha yakuniy natija (podium/o'sish/toy).
    "Ketma-ket 2 oy" qoidalari tarixdan (nz_month_results) tekshiriladi.
    Qaytadi: {league: card_dict}
    """
    # O'tgan oyning oxirgi kuni bilan DayContext (o'sha oy to'liq hisoblanadi)
    last_day = (date(year, month, 1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    dc = DayContext(today=last_day)

    # Bir oldingi oy g'oliblari (ketma-ket taqiq uchun)
    ppy, ppm = prev_month(date(year, month, 1))

    result = {}
    for league in ("city", "region"):
        with get_conn() as conn:
            last_first = storage.last_first_place(conn, ppy, ppm, league)
            last_growth = storage.last_growth_winner(conn, ppy, ppm, league)

        podium = dc.podium_result(league, last_first)
        growth = dc.growth_result(league, last_growth)

        # Toy g'oliblari (darajaga yetganlar)
        toy_winners = []
        for s in dc.by_league[league]:
            if s.toy.reached_bonus > 0:
                toy_winners.append((s.agent.name.split()[0], s.toy.blocks, s.toy.reached_bonus))

        card = {
            "league_label": "Shahar ligasi" if league == "city" else "Viloyat ligasi",
            "month_label": _month_label(month),
            "podium": [(pl, e.name, e.total_ball, e.over, prize)
                       for pl, e, prize in podium.winners],
            "growth": (growth.name, growth.growth_pct, load_rules().growth.prize) if growth else None,
            "toy_winners": toy_winners,
            "note": "Yangi oy — yangi o'yin: hamma noldan boshlaydi!",
        }
        result[league] = card

        # Tarixga saqlaymiz (keyingi oy taqiqlari uchun)
        payload = {
            "podium": [{"place": pl, "sd_id": e.sd_id, "prize": prize}
                       for pl, e, prize in podium.winners],
            "growth": {"sd_id": growth.sd_id, "pct": growth.growth_pct} if growth else None,
        }
        with get_conn() as conn:
            storage.save_month_result(conn, year, month, league, payload, _now())

    return result


async def send_month_final_to_admin(app: Application):
    """3-kuni: o'tgan oy yakunini adminga tasdiqlash uchun yuboradi."""
    today = date.today()
    year, month = prev_month(today)
    cards = compute_month_final(year, month)
    for aid in ADMIN_IDS:
        try:
            await app.bot.send_message(
                aid, f"📊 <b>{_month_label(month)} yakuni tayyor.</b>\n"
                     f"Quyidagi g'oliblarni ko'rib chiqing. To'g'ri bo'lsa "
                     f"<b>/tasdiqla</b> bosing — agentlarga e'lon qilinadi.",
                parse_mode="HTML")
            for league in ("city", "region"):
                await app.bot.send_photo(aid, render_month_final(cards[league]))
        except TelegramError as e:
            logger.warning("admin %s: %s", aid, e)


async def confirm_and_announce(app: Application) -> str:
    """Admin /tasdiqla bosdi — o'tgan oy g'oliblarini guruhga/agentlarga e'lon qiladi."""
    today = date.today()
    year, month = prev_month(today)
    with get_conn() as conn:
        already = storage.get_month_result(conn, year, month, "city")
    if not already:
        return "❌ Avval oy yakuni hisoblanmagan. Keyinroq urinib ko'ring."
    if already.get("confirmed"):
        return "ℹ️ Bu oy allaqachon tasdiqlangan."

    cards = compute_month_final(year, month)
    targets = {"city": GROUP_CITY_CHAT_ID, "region": GROUP_REGION_CHAT_ID}
    sent = 0
    for league, gid in targets.items():
        png = render_month_final(cards[league])
        dest = list(ADMIN_IDS) if (DRY_RUN or not gid) else [gid]
        for did in dest:
            try:
                cap = "[DRY_RUN] oy yakuni e'loni" if (DRY_RUN or not gid) else None
                await app.bot.send_photo(did, png, caption=cap)
                sent += 1
            except TelegramError as e:
                logger.warning("e'lon %s: %s", league, e)

    with get_conn() as conn:
        storage.confirm_month(conn, year, month)
    return f"✅ {_month_label(month)} g'oliblari e'lon qilindi ({sent} ta xabar)."
