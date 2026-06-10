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


async def _test_send_to_group(app: Application) -> None:
    """BIR MARTALIK TEST: bot avtomatik xabar yuborayotganini ko'rsatish uchun."""
    from db import get_conn
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key='report_chat_id'").fetchone()
    if not row or not row["value"]:
        logger.warning("Test: guruh sozlanmagan")
        return
    chat_id = int(row["value"])
    from telegram.constants import ParseMode
    text = (
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🧪 <b>AVTOMATIK TEST XABAR</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "✅ Bu xabar bot tomonidan <b>avtomatik</b> yuborildi.\n"
        "🖥 Source: Railway server (24/7 ishlaydi)\n"
        "👤 Foydalanuvchi ishtirokisiz.\n\n"
        "🎯 Demak ertaga 03:00, 12:00, 15:00 va 20:00 da xabarlar ham <b>avtomatik</b> keladi."
    )
    try:
        await app.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
        logger.info("✅ TEST xabar guruhga yuborildi")
    except Exception as exc:
        logger.exception("TEST xabar xatosi: %s", exc)


async def _test_send_agent_cards(app: Application) -> None:
    """BIR MARTALIK TEST: agent kartochkalarini avtomatik guruhga yuborish."""
    from bot import send_agent_cards_to_group, notify_admins
    logger.info("🧪 AGENT KARTOCHKALARI TEST boshlandi")
    try:
        sent = await send_agent_cards_to_group(app)
        logger.info("🧪 TEST yakuni: %d ta agent kartochkasi yuborildi", sent)
        if sent == 0:
            await notify_admins(app, "⚠️ Test: 0 ta kartochka. Bazada agent ma'lumotlari yo'q bo'lishi mumkin.")
    except Exception as exc:
        logger.exception("Agent kartochkalari test xatosi: %s", exc)
        from bot import notify_admins
        await notify_admins(app, f"⚠️ Test xatosi:\n<code>{str(exc)[:200]}</code>")


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

    # 🧪 BIR MARTALIK TEST — 23:45 da agent kartochkalari guruhga yuboriladi
    scheduler.add_job(
        _test_send_agent_cards,
        CronTrigger(hour=23, minute=45, timezone=TIMEZONE),
        args=[app],
        id="onetime_test_cards_23_45",
        replace_existing=True,
        misfire_grace_time=600,
    )

    scheduler.start()
    logger.info("Scheduler ishga tushdi: 03:00 (TO'LIQ), 12:00 (TEZ), 15:00 (TO'LIQ), 20:00 (TEZ+guruh), 23:45 (KARTOCHKA TEST) — %s", TIMEZONE)
