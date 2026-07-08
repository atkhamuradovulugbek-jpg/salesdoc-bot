"""
send_now.py — QO'LDA bir martalik test: hozirgi ma'lumot bilan namuna
hisobotni adminga yuboradi (DRY_RUN ko'rinishi). Deploy'dan oldin ko'rish uchun.

Ishlatish:  python -m nazorat.send_now
"""

import asyncio
import logging
from datetime import date

from telegram import Bot

from db import get_conn
from .build import DayContext
from .cards import (render_admin_summary, render_evening_card, render_group_daily,
                    render_morning_card, render_plan_card, render_toy_card)
from .nz_config import ADMIN_IDS, NAZORAT_BOT_TOKEN
from .storage import init_nz_tables

logging.basicConfig(level=logging.INFO)


async def main():
    with get_conn() as conn:
        init_nz_tables(conn)
        last = conn.execute("SELECT MAX(date) d FROM orders").fetchone()["d"]

    dc = DayContext(date.fromisoformat(last))
    bot = Bot(NAZORAT_BOT_TOKEN)
    sample = dc.agents[0]  # Bahodir

    async with bot:
        for aid in ADMIN_IDS:
            await bot.send_message(aid,
                "🧪 <b>SINOV — namuna hisobot</b>\n"
                f"Ma'lumot sanasi: {last}\n"
                "Quyida bitta agent (Bahodir) kechqurun oladigan 3 karta, "
                "so'ng guruh reytingi va sizga keladigan svodka.",
                parse_mode="HTML")

            ev = dc.evening_cards(sample.sd_id)
            await bot.send_photo(aid, render_evening_card(ev[0]), caption="1) Kunlik natija")
            await bot.send_photo(aid, render_plan_card(ev[1]), caption="2) Oylik plan")
            await bot.send_photo(aid, render_toy_card(ev[2]), caption="3) Happy Toy")
            await bot.send_photo(aid, render_morning_card(dc.morning_card(sample.sd_id)),
                                 caption="Ertalabki qarz/vazvrat (10:00)")
            await bot.send_photo(aid, render_group_daily(dc.group_daily("city")),
                                 caption="Guruhga — kunlik ballar (shahar)")
            await bot.send_photo(aid, render_admin_summary(dc.admin_evening("city")),
                                 caption="Sizga — admin svodka (shahar)")
            await bot.send_message(aid, "✅ Namuna tugadi. Ma'qul bo'lsa jonli DRY_RUN'ga o'tamiz.")


if __name__ == "__main__":
    asyncio.run(main())
