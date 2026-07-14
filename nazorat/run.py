"""
run.py — nazorat botini ishga tushiradi.
- DB va nz_ jadvallarni tayyorlaydi
- Telegram handlerlarni ro'yxatga oladi
- APScheduler: 09:50/19:50 sync, 10:00 ertalabki, 20:00 kechki, oy 3-kuni yakuni
- polling

Asosiy salesdoc-bot bilan bir xil bot.db, lekin ALOHIDA jarayon va bot token.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          MessageHandler, ContextTypes, filters)

from db import get_conn, init_db

from . import bot as nzbot
from . import jobs
from . import month_end
from .nz_config import (DRY_RUN, EVENING_HOUR, EVENING_MINUTE, MORNING_HOUR,
                        MORNING_MINUTE, NAZORAT_BOT_TOKEN, SYNC_BEFORE_MIN, TIMEZONE)
from .storage import init_nz_tables

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("nazorat.run")
TZ = ZoneInfo(TIMEZONE)


async def _sync_then(app, job_coro):
    """Hisobotdan oldin fresh sync (fast). Xato bo'lsa — adminga xabar, agentlarga emas."""
    from sync import run_sync
    try:
        res = await run_sync("nazorat", mode="fast")
        if res != "ok":
            logger.error("Sync xato: %s", res)
            await jobs._admins(app, text=f"⚠️ Sync xatosi — hisobot yuborilmadi.\n{res}")
            return
    except Exception as e:
        logger.exception("Sync exception")
        await jobs._admins(app, text=f"⚠️ Sync xatoligi: {e}")
        return
    await job_coro(app)


def _minus(hour: int, minute: int, mins: int) -> tuple[int, int]:
    t = datetime(2000, 1, 1, hour, minute) - timedelta(minutes=mins)
    return t.hour, t.minute


def setup_scheduler(app: Application) -> AsyncIOScheduler:
    sched = AsyncIOScheduler(timezone=TZ)

    async def morning():
        await _sync_then(app, jobs.morning_job)

    async def evening():
        await _sync_then(app, jobs.evening_job)

    async def month_final():
        # Har oyning 3-kuni: o'tgan oy yakunini adminga
        await month_end.send_month_final_to_admin(app)

    sched.add_job(morning, CronTrigger(hour=MORNING_HOUR, minute=MORNING_MINUTE, timezone=TZ),
                  id="morning", misfire_grace_time=3600)
    sched.add_job(evening, CronTrigger(hour=EVENING_HOUR, minute=EVENING_MINUTE, timezone=TZ),
                  id="evening", misfire_grace_time=3600)
    sched.add_job(month_final, CronTrigger(day=3, hour=11, minute=0, timezone=TZ),
                  id="month_final", misfire_grace_time=7200)
    return sched


def build_app() -> Application:
    app = Application.builder().token(NAZORAT_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", nzbot.cmd_start))
    app.add_handler(CommandHandler("bugun", nzbot.cmd_bugun))
    app.add_handler(CommandHandler("oy", nzbot.cmd_oy))
    app.add_handler(CommandHandler("toy", nzbot.cmd_toy))
    app.add_handler(CommandHandler("qarz", nzbot.cmd_qarz))
    app.add_handler(CommandHandler("vazvrat", nzbot.cmd_vazvrat))
    app.add_handler(CommandHandler("yordam", nzbot.cmd_yordam))
    app.add_handler(CommandHandler("tasdiqla", nzbot.cmd_tasdiqla))
    app.add_handler(CallbackQueryHandler(nzbot.on_bind_decision, pattern=r"^nzbind:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, nzbot.on_text))
    return app


async def _post_init(app: Application):
    sched = setup_scheduler(app)
    sched.start()
    app.bot_data["scheduler"] = sched
    logger.info("✅ Nazorat bot ishga tushdi. DRY_RUN=%s", DRY_RUN)
    for aid in nzbot.ADMIN_IDS:
        try:
            await app.bot.send_message(
                aid, f"🤖 Nazorat bot ishga tushdi.\nDRY_RUN={DRY_RUN} "
                     f"(hozircha hamma hisobot faqat sizga keladi).")
        except Exception:
            pass


def main():
    with get_conn() as conn:
        init_nz_tables(conn)
    init_db()
    app = build_app()
    app.post_init = _post_init
    logger.info("Polling boshlandi...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
