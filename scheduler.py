"""
scheduler.py — Har kuni 12:00 va 20:00 (Toshkent vaqti) ma'lumot tortadi.
20:00 dan keyin kunlik xulosa adminlarga yuboriladi.
"""

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram.ext import Application

from config import TIMEZONE
from sync import run_sync

logger = logging.getLogger(__name__)


async def _noon_sync(app: Application) -> None:
    logger.info("12:00 — sinxronizatsiya boshlandi")
    result = await run_sync("scheduled")
    if result != "ok":
        from bot import notify_admins
        await notify_admins(app, f"⚠️ <b>Sales Doctor xatosi (12:00):</b>\n<code>{result[:300]}</code>")


async def _evening_sync(app: Application) -> None:
    logger.info("20:00 — sinxronizatsiya boshlandi")
    result = await run_sync("scheduled")
    if result != "ok":
        from bot import notify_admins
        await notify_admins(app, f"⚠️ <b>Sales Doctor xatosi (20:00):</b>\n<code>{result[:300]}</code>")
    else:
        from bot import send_daily_digest, send_agent_cards_to_group
        await send_daily_digest(app)
        # Har agent uchun guruhga hisobot kartochkasi
        await send_agent_cards_to_group(app)


def setup_scheduler(app: Application) -> None:
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    # Async funksiyalarni to'g'ridan-to'g'ri uzatish (lambda noto'g'ri ishlaydi)
    scheduler.add_job(
        _noon_sync,
        CronTrigger(hour=12, minute=0, timezone=TIMEZONE),
        args=[app],
        id="noon_sync",
        replace_existing=True,
        misfire_grace_time=1800,
    )
    scheduler.add_job(
        _evening_sync,
        CronTrigger(hour=20, minute=0, timezone=TIMEZONE),
        args=[app],
        id="evening_sync",
        replace_existing=True,
        misfire_grace_time=1800,
    )

    scheduler.start()
    logger.info("Scheduler ishga tushdi (12:00 va 20:00, %s)", TIMEZONE)
