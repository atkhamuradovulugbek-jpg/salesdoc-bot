"""
scheduler.py — Avtomatik vaqtlar:
  03:00 — TO'LIQ sync + admin xabari
  12:00 — TEZ sync + admin xabari
  15:00 — TO'LIQ sync + admin xabari
  20:00 — TEZ sync + admin xabari + guruh kartochkalari + kunlik xulosa
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram.ext import Application

from config import TIMEZONE
from sync import run_sync

logger = logging.getLogger(__name__)


async def _scheduled_full(app: Application, time_label: str) -> None:
    """To'liq sync + admin xabari."""
    logger.info("%s — TO'LIQ sync boshlandi", time_label)
    result = await run_sync("scheduled", mode="full")
    from bot import notify_admins
    if result == "ok":
        await notify_admins(app, f"🔵 <b>{time_label}</b>\n✅ Ma'lumotlar <b>to'liq</b> yangilandi")
    elif result == "busy":
        logger.info("%s — boshqa sync ishlamoqda, o'tkazib yuborildi", time_label)
    else:
        await notify_admins(app, f"⚠️ <b>{time_label} sync xatosi:</b>\n<code>{result[:300]}</code>")


async def _scheduled_fast(app: Application, time_label: str) -> None:
    """Tez sync + admin xabari."""
    logger.info("%s — TEZ sync boshlandi", time_label)
    result = await run_sync("scheduled", mode="fast")
    from bot import notify_admins
    if result == "ok":
        await notify_admins(app, f"🟢 <b>{time_label}</b>\n✅ Tez yangilash tugadi")
    elif result == "busy":
        logger.info("%s — boshqa sync ishlamoqda, o'tkazib yuborildi", time_label)
    else:
        await notify_admins(app, f"⚠️ <b>{time_label} sync xatosi:</b>\n<code>{result[:300]}</code>")


async def _evening(app: Application) -> None:
    """20:00 — TEZ sync + admin xabari + guruh kartochkalari + kunlik xulosa."""
    logger.info("20:00 — kechki ish boshlandi")
    result = await run_sync("scheduled", mode="fast")
    from bot import notify_admins
    if result == "busy":
        logger.info("20:00 — boshqa sync ishlamoqda, o'tkazib yuborildi")
        return
    if result != "ok":
        await notify_admins(app, f"⚠️ <b>20:00 sync xatosi:</b>\n<code>{result[:300]}</code>")
        return

    await notify_admins(app, "🟢 <b>20:00</b>\n✅ Tez yangilash + Kunlik xulosa")

    # Kunlik xulosani adminga yuborish
    from bot import send_daily_digest, send_agent_cards_to_group
    await send_daily_digest(app)

    # Guruhga har agent uchun kartochka
    try:
        sent = await send_agent_cards_to_group(app)
        if sent > 0:
            logger.info("✅ Guruhga %d kartochka yuborildi", sent)
    except Exception as exc:
        logger.exception("Guruh kartochkalari xatosi: %s", exc)


def setup_scheduler(app: Application) -> None:
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    # 03:00 — TO'LIQ
    scheduler.add_job(
        _scheduled_full,
        CronTrigger(hour=3, minute=0, timezone=TIMEZONE),
        args=[app, "03:00"],
        id="full_3am",
        replace_existing=True,
        misfire_grace_time=1800,
    )

    # 12:00 — TEZ
    scheduler.add_job(
        _scheduled_fast,
        CronTrigger(hour=12, minute=0, timezone=TIMEZONE),
        args=[app, "12:00"],
        id="fast_noon",
        replace_existing=True,
        misfire_grace_time=1800,
    )

    # 15:00 — TO'LIQ
    scheduler.add_job(
        _scheduled_full,
        CronTrigger(hour=15, minute=0, timezone=TIMEZONE),
        args=[app, "15:00"],
        id="full_3pm",
        replace_existing=True,
        misfire_grace_time=1800,
    )

    # 20:00 — TEZ + guruh + digest
    scheduler.add_job(
        _evening,
        CronTrigger(hour=20, minute=0, timezone=TIMEZONE),
        args=[app],
        id="evening",
        replace_existing=True,
        misfire_grace_time=1800,
    )

    scheduler.start()
    logger.info("Scheduler ishga tushdi: 03:00 (TO'LIQ), 12:00 (TEZ), 15:00 (TO'LIQ), 20:00 (TEZ+guruh) — %s", TIMEZONE)
