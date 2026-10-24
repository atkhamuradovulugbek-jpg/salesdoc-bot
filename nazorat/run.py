"""
run.py — nazorat botini ishga tushiradi.
- DB va nz_ jadvallarni tayyorlaydi
- Telegram handlerlarni ro'yxatga oladi
- APScheduler: 09:50/19:50 sync, 10:00 ertalabki, 20:00 kechki, oy 3-kuni yakuni
- polling

Asosiy salesdoc-bot bilan bir xil bot.db, lekin ALOHIDA jarayon va bot token.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          MessageHandler, ContextTypes, filters)

from db import get_conn, init_db

from apscheduler.triggers.interval import IntervalTrigger

from . import bot as nzbot
from . import jobs
from . import debtwatch
from . import month_end
from . import quick
from . import monitor
from . import taskq
from .nz_config import (DRY_RUN, EVENING_HOUR, EVENING_MINUTE, GPS_CHECK_MIN,
                        MORNING_HOUR, MORNING_MINUTE, NAZORAT_BOT_TOKEN,
                        SYNC_BEFORE_MIN, TIMEZONE, WATCHDOG_AFTER_MIN)
from .storage import init_nz_tables

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("nazorat.run")
TZ = ZoneInfo(TIMEZONE)


SYNC_BUSY_TRIES = 6              # "busy" bo'lsa shuncha marta 60 sek kutib qayta uriniladi
DATA_FRESH_MIN = 45             # shu daqiqa ichida muvaffaqiyatli sync bo'lsa — ma'lumot yangi


def _sync_looks_stale(since: str) -> str | None:
    """BIZNING sync "ok" dedi-yu, aslida BO'SH qaytdimi? (2026-07-15 nosozligining ildizi)

    Sales Doctor buzilgan javob bersa `get_orders` bo'sh qaytadi; sync eski ma'lumotni
    saqlaydi (to'g'ri) LEKIN "ok" deb qaytaradi — natijada ESKI raqamlar bilan hisobot
    yuborilardi.

    MUHIM (2026-07-30 review): faqat O'ZIMIZNING (nazorat) va shu yurishdan keyin yozilgan
    qatorni tekshiramiz — asosiy botning qatorini o'qib, to'g'ri hisobotni bekor qilib
    qo'ymaslik uchun. Buyurtma 0, lekin bazada shu oyda savdo bor bo'lsa — STALE."""
    import re
    from datetime import date as _date
    with get_conn() as conn:
        row = conn.execute(
            "SELECT type, status, note FROM sync_log WHERE type LIKE 'nazorat%' AND run_at >= ? "
            "ORDER BY id DESC LIMIT 1", (since,)).fetchone()
        if row is None:
            return None                       # o'z qatorimiz topilmadi — to'sib qo'ymaymiz
        if row["status"] != "ok":
            return f"sync holati: {row['status']} ({row['note']})"
        m = re.search(r"orders=(\d+)", row["note"] or "")
        if not m or int(m.group(1)) > 0:
            return None
        month_start = _date.today().replace(day=1).isoformat()
        cnt = conn.execute("SELECT COUNT(*) c FROM orders WHERE date >= ?",
                           (month_start,)).fetchone()["c"]
    if cnt:
        return (f"Sales Doctor 0 buyurtma qaytardi, lekin bazada shu oyda {cnt} ta bor — "
                f"ma'lumot ESKI. Noto'g'ri raqam yubormaslik uchun to'xtatildi.")
    return None


def _data_age_min() -> float | None:
    """Oxirgi MUVAFFAQIYATLI sync'dan necha daqiqa o'tdi (topilmasa None)."""
    from datetime import datetime as _dt
    with get_conn() as conn:
        row = conn.execute("SELECT run_at FROM sync_log WHERE status='ok' "
                           "ORDER BY id DESC LIMIT 1").fetchone()
    if not row or not row["run_at"]:
        return None
    try:
        t = _dt.fromisoformat(row["run_at"])
    except ValueError:
        return None
    return (datetime.now(TZ) - t).total_seconds() / 60


async def _sync_then(app, job_coro):
    """Hisobotdan oldin fresh sync (fast). Xato/eski ma'lumot bo'lsa — hisobot
    YUBORILMAYDI, faqat adminga xabar (agentlarga noto'g'ri raqam ketmasin)."""
    from sync import run_sync
    since = datetime.now(TZ).isoformat(timespec="seconds")
    res = None
    for attempt in range(1, SYNC_BUSY_TRIES + 1):   # "busy" — boshqa sync ketyapti
        try:
            res = await run_sync("nazorat", mode="fast")
        except Exception as e:                       # noqa: BLE001
            logger.exception("Sync exception")
            await jobs._admins(app, text=f"⚠️ Sync xatoligi: {e}")
            return
        if res != "busy":
            break
        logger.warning("Sync band (%d/%d) — 60 sek kutamiz", attempt, SYNC_BUSY_TRIES)
        await asyncio.sleep(60)

    if res == "busy":
        # Boshqa sync hali ketyapti. U AYNAN shu ma'lumotni yangilaydi — agar ma'lumot
        # yangi bo'lsa, hisobotni bekor qilish shart emas (avval bekor qilinardi).
        age = _data_age_min()
        if age is not None and age <= DATA_FRESH_MIN:
            logger.warning("Sync band, lekin ma'lumot yangi (%.0f daq) — hisobot davom etadi", age)
            await jobs._admins(app, text=f"ℹ️ Sync band edi, lekin ma'lumot yangi "
                                         f"({age:.0f} daqiqa) — hisobot yuborildi.")
            return await job_coro(app)
        await jobs._admins(app, text="⚠️ Sync band va ma'lumot eski — hisobot yuborilmadi.")
        return

    if isinstance(res, str) and res.startswith("partial"):
        # Sales Doctor chala javob berdi (24.10.2026 saboqi) — sync eski (to'liq) ma'lumotni
        # saqlab qoldi. Asosiy botning 20:00 sync'i yangi bo'lsa, hisobot shu bilan ketadi.
        age = _data_age_min()
        if age is not None and age <= DATA_FRESH_MIN:
            logger.warning("Sync chala, lekin ma'lumot yangi (%.0f daq) — hisobot davom etadi", age)
            await jobs._admins(app, text=f"⚠️ Sales Doctor chala javob berdi — eski ma'lumot "
                                         f"saqlandi ({age:.0f} daqiqa oldingi), hisobot shu "
                                         f"ma'lumot bilan yuboriladi.\n{res}")
            return await job_coro(app)
        await jobs._admins(app, text=f"⚠️ Sales Doctor chala javob berdi va ma'lumot eski — "
                                     f"hisobot yuborilmadi.\n{res}")
        return

    if res != "ok":
        logger.error("Sync xato: %s", res)
        await jobs._admins(app, text=f"⚠️ Sync xatosi — hisobot yuborilmadi.\n{res}")
        return

    stale = _sync_looks_stale(since)
    if stale:
        logger.error("Sync STALE: %s", stale)
        await jobs._admins(app, text=f"🚨 Hisobot YUBORILMADI — ma'lumot eski.\n{stale}")
        return

    await job_coro(app)


def _minus(hour: int, minute: int, mins: int) -> tuple[int, int]:
    t = datetime(2000, 1, 1, hour, minute) - timedelta(minutes=mins)
    return t.hour, t.minute


def _plus(hour: int, minute: int, mins: int) -> tuple[int, int]:
    t = datetime(2000, 1, 1, hour, minute) + timedelta(minutes=mins)
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

    # WATCHDOG ("baqiradigan" nazorat, 0-bosqich 2026-07-18): hisobotdan 30 daqiqa keyin
    # adminga bitta xabar — nima ketdi, nima ketmadi, job tugadimi. Jimgina buzilish yo'q.
    async def wd_evening():
        await jobs.watchdog(app, "evening")

    async def wd_morning():
        await jobs.watchdog(app, "morning")

    # KUNLIK BAZA NUSXASI (0.5-bosqich): 03:00 to'liq sync'dan keyin, adminga Telegramda.
    async def db_backup():
        from . import backup
        try:
            await backup.send_db_backup(app, nzbot.ADMIN_IDS, reason="kunlik")
        except Exception as e:                       # noqa: BLE001
            logger.exception("Baza nusxasi yasalmadi")
            await jobs._admins(app, text=f"⚠️ Baza nusxasi yasalmadi: {e}")

    sched.add_job(db_backup, CronTrigger(hour=3, minute=30, timezone=TZ),
                  id="db_backup", misfire_grace_time=7200)

    # VAZIFA NAVBATI (2-bosqich): web'dan kelgan vazifalarni SHU jarayon bajaradi
    # (yagona yozuvchi + o'z sync qulfi). Har 15 sekundda bitta vazifa olinadi.
    async def worker():
        await taskq.run_worker(app)

    sched.add_job(worker, IntervalTrigger(seconds=15, timezone=TZ),
                  id="task_worker", misfire_grace_time=60, max_instances=1,
                  next_run_time=datetime.now(TZ) + timedelta(seconds=20))

    # «HOZIRGI HOLAT» — har 30 daqiqada JIMGINA yengil yangilash (~5 soniya).
    # Egasi talabi (2026-08-11): "malumotlar yangilansin, LEKIN XABAR KELMASIN".
    # Shuning uchun bu yerda hech kimga xabar yuborilmaydi — faqat baza yangilanadi
    # va sync_log'ga qator yoziladi. Supervayzer tugma bosmasa ham ma'lumot
    # eng ko'pi 30 daqiqa eski bo'ladi.
    async def quick_refresh():
        try:
            ok, note = await quick.refresh("auto", force=True)
            logger.info("Yengil yangilash (avto): %s — %s", ok, note)
        except Exception:                                # noqa: BLE001
            logger.exception("Yengil yangilash (avto) xatosi")   # JIM: admin bezovta qilinmaydi

    sched.add_job(quick_refresh, IntervalTrigger(minutes=30, timezone=TZ),
                  id="quick_refresh", misfire_grace_time=600, max_instances=1,
                  next_run_time=datetime.now(TZ) + timedelta(minutes=2))

    # ── QARZ NAZORATI (2026-08-13) ──
    # Dastafshiklar limitni bilmay qarzga berib yuborayotgani uchun alohida rol.
    # Nazoratchi ULANMAGAN bo'lsa ikkalasi ham darhol qaytadi (API'ga borilmaydi).
    async def debt_hourly():
        try:
            r = await debtwatch.hourly_check(app)
            logger.info("Qarz tekshiruvi: %s", r)
        except Exception:                                # noqa: BLE001
            logger.exception("Qarz tekshiruvi xatosi")   # jim: hisobotni buzmasin

    async def debt_evening():
        try:
            r = await debtwatch.evening_report(app)
            logger.info("22:00 qarz hisoboti: %s", r)
        except Exception:                                # noqa: BLE001
            logger.exception("22:00 qarz hisoboti xatosi")
            await jobs._admins(app, text="⚠️ 22:00 qarz hisoboti yuborilmadi.")

    # Ish vaqtida har soat (09:00–19:00) — limitdan oshganini darhol bildirish
    sched.add_job(debt_hourly, CronTrigger(hour="9-19", minute=5, timezone=TZ),
                  id="debt_hourly", misfire_grace_time=600, max_instances=1)
    # 22:00 — ertangi kunga qaror (shahar + viloyat alohida rasm)
    sched.add_job(debt_evening, CronTrigger(hour=22, minute=0, timezone=TZ),
                  id="debt_evening", misfire_grace_time=3600, max_instances=1)

    wd_e_h, wd_e_m = _plus(EVENING_HOUR, EVENING_MINUTE, WATCHDOG_AFTER_MIN)
    wd_m_h, wd_m_m = _plus(MORNING_HOUR, MORNING_MINUTE, WATCHDOG_AFTER_MIN)
    sched.add_job(wd_evening, CronTrigger(hour=wd_e_h, minute=wd_e_m, timezone=TZ),
                  id="watchdog_evening", misfire_grace_time=3600)
    sched.add_job(wd_morning, CronTrigger(hour=wd_m_h, minute=wd_m_m, timezone=TZ),
                  id="watchdog_morning", misfire_grace_time=3600)

    # Kunduzgi GPS trevoga (ish vaqti/yakshanba filtri monitor ichida).
    # next_run_time: qayta deploy'da interval noldan sanalmasligi uchun ~3 daqiqada birinchi tekshiruv.
    async def gps_mon():
        await monitor.gps_check(app)

    sched.add_job(gps_mon, IntervalTrigger(minutes=GPS_CHECK_MIN, timezone=TZ),
                  id="gps_monitor", misfire_grace_time=600,
                  next_run_time=datetime.now(TZ) + timedelta(minutes=3))
    return sched


def build_app() -> Application:
    app = Application.builder().token(NAZORAT_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", nzbot.cmd_start))
    app.add_handler(CommandHandler("bugun", nzbot.cmd_bugun))
    app.add_handler(CommandHandler("kecha", nzbot.cmd_kecha))
    app.add_handler(CommandHandler("oy", nzbot.cmd_oy))
    app.add_handler(CommandHandler("toy", nzbot.cmd_toy))
    app.add_handler(CommandHandler("qarz", nzbot.cmd_qarz))
    app.add_handler(CommandHandler("vazvrat", nzbot.cmd_vazvrat))
    app.add_handler(CommandHandler("yordam", nzbot.cmd_yordam))
    app.add_handler(CommandHandler("tasdiqla", nzbot.cmd_tasdiqla))
    app.add_handler(CallbackQueryHandler(nzbot.on_bind_decision, pattern=r"^nzbind:"))
    app.add_handler(CallbackQueryHandler(nzbot.on_gps_button, pattern=r"^nzgps:"))
    app.add_handler(CallbackQueryHandler(nzbot.on_unbind, pattern=r"^nzunbind:"))
    app.add_handler(CallbackQueryHandler(nzbot.on_send_sample, pattern=r"^nzsample:"))
    app.add_handler(CallbackQueryHandler(nzbot.cb_debt_shops, pattern=r"^qrzshop:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, nzbot.on_text))
    return app


async def _post_init(app: Application):
    sched = setup_scheduler(app)
    sched.start()
    app.bot_data["scheduler"] = sched
    logger.info("✅ Nazorat bot ishga tushdi. DRY_RUN=%s", DRY_RUN)
    if DRY_RUN:
        holat = ("🧪 SINOV rejimi (DRY_RUN=True): hamma AVTOMATIK hisobot faqat sizga "
                 "(adminga) keladi, agentlarga emas.")
    else:
        holat = ("✅ JONLI rejim (DRY_RUN=False): avtomatik hisobot 10:00/20:00 da ulangan "
                 "agentlar va supervayzerlarga boradi.")
    for aid in nzbot.ADMIN_IDS:
        try:
            await app.bot.send_message(aid, f"🤖 Nazorat bot ishga tushdi.\n{holat}")
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
