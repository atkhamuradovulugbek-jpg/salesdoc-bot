"""
jobs.py — rejalashtirilgan vazifalar (10:00 ertalabki, 20:00 kechki, ogohlantirishlar).
DRY_RUN=true bo'lsa hamma narsa FAQAT adminga (agentlarga/guruhga emas).
Idempotent: nz_sent_log orqali qayta yubormaydi.
"""

from __future__ import annotations

import logging
from datetime import date

from telegram.error import TelegramError
from telegram.ext import Application

from db import get_conn

from . import health
from . import storage
from .build import DayContext
from .cards import (render_admin_summary, render_ball_card, render_debt_card,
                    render_group_daily, render_plan_card, render_returns_card,
                    render_supervisor_daily, render_supervisor_debt,
                    render_supervisor_monthly, render_toy_card)
from .core.balls import zero_streak
from .data import MONTHS_UZ
from .nz_config import ADMIN_IDS, DRY_RUN, GROUP_CITY_CHAT_ID, GROUP_REGION_CHAT_ID

logger = logging.getLogger("nazorat.jobs")

# Yangi agent kartalari (BUGUNGI NATIJA + reja + OYLIK AKSIYA DAFTARI, Happy Toy yo'q).
# Yuklanmasa — eski to'plam ishlayveradi (bot yiqilmaydi).
try:
    from . import aksiya_cards
except Exception as _aks_err:                       # noqa: BLE001
    aksiya_cards = None
    logger.error("aksiya_cards yuklanmadi: %s", _aks_err)


# Supervayzer oylik/kunlik jadvali — Ball/Toy o'rniga aksiya (egasi tasdiqlagan, 2026-10-08).
# Yuklanmasa — eski jadval ishlayveradi (bot yiqilmaydi).
try:
    from . import sup_cards
except Exception as _sup_err:                       # noqa: BLE001
    sup_cards = None
    logger.error("sup_cards yuklanmadi: %s", _sup_err)


# Supervayzer «Plan jadvali» — yo'nalish plani 1 mlrd (egasi tasdiqlagan, 2026-10-15).
# Yuklanmasa — qolgan kechki hisobotlar ishlayveradi (bot yiqilmaydi).
try:
    from . import sup_plan
except Exception as _plan_err:                      # noqa: BLE001
    sup_plan = None
    logger.error("sup_plan yuklanmadi: %s", _plan_err)


def sup_monthly_png(dc: DayContext, league: str) -> bytes:
    if sup_cards:
        return sup_cards.monthly_png(dc, league)
    return render_supervisor_monthly(dc.supervisor_monthly(league))


def sup_daily_png(dc: DayContext, league: str) -> bytes:
    if sup_cards:
        return sup_cards.daily_png(dc, league)
    return render_supervisor_daily(dc.supervisor_daily(league))


def _new_agent_cards(report_day: date) -> bool:
    """Yangi to'plam: 2026-10-08 20:10 (Toshkent) dan VA hisobot sanasi 08.10 dan.
    Kechikkan/eski sana uchun yuborish — eski to'plam."""
    return bool(aksiya_cards and aksiya_cards.active()
                and report_day >= aksiya_cards.ACTIVATION.date())


def _now() -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Asia/Tashkent")).isoformat(timespec="seconds")


async def _admins(app, photo=None, text=None):
    for aid in ADMIN_IDS:
        try:
            if photo is not None:
                await app.bot.send_photo(aid, photo, caption=text)
            else:
                await app.bot.send_message(aid, text)
        except TelegramError as e:
            logger.warning("admin %s ga yuborilmadi: %s", aid, e)


async def _guard(rep: health.RunReport, block: str, fn, who: str = ""):
    """Bitta bo'lakni HIMOYALAB bajaradi: xato bo'lsa qolgan bo'laklar baribir ketadi.
    (2026-07-18: bitta ketgan agent butun kechki jobni o'ldirgan edi.)"""
    try:
        res = await fn()
        rep.note(block, res if isinstance(res, str) else health.SENT, who)
    except Exception as e:                       # noqa: BLE001 — ataylab hammasi
        logger.exception("%s / %s xato (%s)", rep.job, block, who or "-")
        rep.note(block, health.FAIL, who, e)


async def _send_agent(app, sd_id: str, photos: list[bytes], day: str, kind: str) -> str:
    """Agent shaxsiy chatiga (DRY_RUN bo'lsa adminga). Idempotent.
    Qaytadi: 'sent' | 'dup' | 'unbound'. To'liq yuborilmasa — XATO ko'taradi."""
    with get_conn() as conn:
        chat = storage.chat_for_sd_id(conn, sd_id)
        target = "admin" if DRY_RUN else (str(chat) if chat else None)
        if target is None:
            return health.UNBOUND          # agent hali ulanmagan (xato emas)
        if storage.already_sent(conn, day, kind, target):
            return health.DUP

    dest_ids = list(ADMIN_IDS) if DRY_RUN else [chat]
    ok = False
    last_err: Exception | None = None
    for did in dest_ids:
        try:
            for i, p in enumerate(photos):
                cap = None
                if DRY_RUN and i == 0:
                    cap = f"[DRY_RUN] {kind} → {sd_id}"
                await app.bot.send_photo(did, p, caption=cap)
            ok = True
        except TelegramError as e:
            logger.warning("agent %s (chat %s) ga yuborilmadi: %s", sd_id, did, e)
            last_err = e
    if not ok:
        raise last_err or RuntimeError("agentga yuborilmadi")
    with get_conn() as conn:
        storage.mark_sent(conn, day, kind, target, _now())
    return health.SENT


# Supervayzer kodlari (liga bo'yicha). Hozircha ulanmagan — v2'da bog'lanadi;
# shu paytgacha (va DRY_RUN'da) jadvallar adminga tushadi.
SUPERVISOR_CODES = {"city": "SPV-TSH-01", "region": "SPV-TVL-01"}


async def _send_supervisor(app, league: str, photo: bytes, day: str, kind: str) -> str:
    """Supervayzer jadvali. DRY_RUN yoki supervayzer ulanmagan bo'lsa — adminga. Idempotent.
    Qaytadi: 'sent' | 'dup'. Yuborilmasa — XATO ko'taradi."""
    with get_conn() as conn:
        chat = storage.chat_for_supervisor(conn, SUPERVISOR_CODES.get(league, ""))
    to_admin = DRY_RUN or not chat
    target = "admin" if to_admin else str(chat)
    key = f"sv_{kind}_{league}"
    with get_conn() as conn:
        if storage.already_sent(conn, day, key, target):
            return health.DUP
    if to_admin:
        await _admins(app, photo=photo,
                      text=f"[DRY_RUN] supervayzer {kind} → {league}")
    else:
        await app.bot.send_photo(chat, photo)     # xato bo'lsa _guard ushlaydi
    with get_conn() as conn:
        storage.mark_sent(conn, day, key, target, _now())
    return health.SENT


# ==================================================================
# 10:00 — ertalabki qarz/vazvrat
# ==================================================================

async def morning_job(app: Application):
    logger.info("Ertalabki job boshlandi (DRY_RUN=%s)", DRY_RUN)
    today = date.today()
    day = today.isoformat()
    rep = health.RunReport("morning", day)
    rep.start(_now())
    _save_run(rep)

    # O'rindiqda yangi agent aniqlash (ism o'zgargani) — dc'dan OLDIN, shu kunги
    # hisobotga tushishi uchun. Adminга bir marta xabar beradi.
    await _guard(rep, "yangi-agent", lambda: _agent_change_alerts(app, day))

    # Yaml ro'yxatida YO'Q, lekin Sales Doctor'da faol va savdo qilayotgan agent (yangi
    # ishga kirgan / yangi o'rindiq) — adminга bir marta xabar (ro'yxatga qo'shish uchun).
    await _guard(rep, "yangi-agent", lambda: _new_agent_alerts(app, day))

    # Qarz tarixini saqlaymiz (yosh hisobi uchun) — har kuni bir marta
    await _guard(rep, "qarz-snapshot", lambda: _snapshot_balances(day))

    dc = await _build_context(app, rep, today)
    if dc is None:
        return

    for ag in dc.agents:
        if ag.observe_only:
            continue
        await _guard(rep, "agent",
                     lambda ag=ag: _agent_morning_one(app, dc, ag, day), ag.short)

    # Admin svodkasi ERTALAB YUBORILMAYDI (foydalanuvchi qarori 2026-07-14):
    # savdo/ball/reja jadvali faqat KECHKI 20:00 svodkada — ertalab savdo hali 0
    # bo'lib chalkash chiqardi. Ertalab faqat qarz/vazvrat materiallari.

    # Supervayzerga: qarz-vazvrat jadvali (liga bo'yicha)
    for league in ("city", "region"):
        await _guard(rep, "super-qarz",
                     lambda lg=league: _send_supervisor(
                         app, lg, render_supervisor_debt(dc.supervisor_debt(lg)),
                         day, "debt"), league)

    rep.finish(_now())
    _save_run(rep)
    logger.info("Ertalabki job tugadi: %s", rep.short())


async def _agent_morning_one(app, dc: DayContext, ag, day: str) -> str:
    """Bitta agentning ertalabki kartalari (qarz + vazvrat)."""
    card = dc.morning_card(ag.sd_id)
    photos = []
    if card["debt_total"] > 0:
        photos.append(render_debt_card(card))        # 1-jadval: qarz
    # Vazvrat kartasi HAR KUNI (foydalanuvchi qarori 2026-07-13): kecha vazvrat
    # bo'lmasa ham "kunlik yo'q" + oylik jami vazvratni ko'rsatib turadi.
    photos.append(render_returns_card(card))         # 2-jadval: vazvrat
    return await _send_agent(app, ag.sd_id, photos, day, "morning")


async def _snapshot_balances(day: str) -> str:
    with get_conn() as conn:
        n = storage.snapshot_balances(conn, day)
    logger.info("Qarz snapshot: %d do'kon", n)
    return health.SENT


def _save_run(rep: health.RunReport) -> None:
    """Job holatini bazaga yozadi (watchdog shundan o'qiydi)."""
    try:
        with get_conn() as conn:
            storage.save_job_run(conn, rep.day, rep.job, rep.started_at,
                                 rep.finished_at, rep.payload())
    except Exception:                                # noqa: BLE001
        logger.exception("nz_job_run yozilmadi")


async def _build_context(app, rep: health.RunReport, today: date) -> DayContext | None:
    """DayContext quradi. Qulasa — adminga darhol xabar (jimgina o'tmaydi)."""
    try:
        return DayContext(today)
    except Exception as e:                           # noqa: BLE001
        logger.exception("DayContext qurilmadi")
        rep.note("dc", health.FAIL, "", e)
        _save_run(rep)
        await _admins(app, text=f"🚨 {health.JOB_LABELS.get(rep.job, rep.job)} hisobot "
                                f"BOSHLANMADI — ma'lumot tayyorlanmadi:\n{e}")
        return None


async def _agent_change_alerts(app, day: str):
    """O'rindiqda yangi agent (Sales Doctor ismi o'zgargan) — aniqlab, adminга xabar."""
    from .core.rules import load_agents
    sd_ids = [a.sd_id for a in load_agents().agents]
    with get_conn() as conn:
        changes = storage.sync_agent_terms(conn, sd_ids, day, _now())
    if not changes:
        return
    for ch in changes:
        text = (f"🆕 Yangi agent aniqlandi (o'rindiq almashdi)!\n"
                f"Eski: {ch['old_name']}\n"
                f"Yangi: {ch['new_name']} → hisobda \"{ch['short_name']}\"\n"
                f"Hisoblanadi: {ch['start_date']} dan\n"
                f"Ball plani va sovrin: DARROV qo'llanadi (kuzatuv rejimi yo'q).\n"
                f"Unga alohida ball plani kerak bo'lsa — dasturda "
                f"⚙️ Boshqaruv → 🎯 Ball plan dan qo'ying.\n"
                f"Ism yoki sana noto'g'ri bo'lsa — menga ayting, to'g'rilayman.")
        await _admins(app, text=text)
    with get_conn() as conn:
        storage.mark_terms_notified(conn, [c["sd_id"] for c in changes], _now())
    logger.info("Agent almashinuvi: %d ta yangi agent aniqlandi", len(changes))


async def _new_agent_alerts(app, day: str):
    """Yaml'da yo'q, lekin Sales Doctor'da faol + savdo qilayotgan agent — adminга
    bir marta (nz_sent_log dedup) xabar. Bot ro'yxatiga qo'shish uchun."""
    from .core.rules import load_agents
    yaml_ids = {a.sd_id for a in load_agents().agents}
    month_start = date.today().replace(day=1).isoformat()
    with get_conn() as conn:
        found = storage.unknown_active_agents(conn, yaml_ids, month_start)
    for a in found:
        key = f"new_agent_{a['sd_id']}"
        with get_conn() as conn:
            if storage.already_sent(conn, day, key, "admin"):
                continue
        text = (f"🆕 Yangi agent topildi (bot ro'yxatida yo'q)!\n"
                f"Sales Doctor: {a['name']} (id {a['sd_id']})\n"
                f"U faol va savdo qilyapti, lekin yangi bot hisobotlariga tushmayapti.\n"
                f"Uni qo'shishimni istasangiz — menga ayting (ball plani bilan).")
        await _admins(app, text=text)
        with get_conn() as conn:
            storage.mark_sent(conn, day, key, "admin", _now())


# ==================================================================
# 20:00 — kechki natija + guruh reyting
# ==================================================================

async def evening_job(app: Application):
    logger.info("Kechki job boshlandi (DRY_RUN=%s)", DRY_RUN)
    today = date.today()
    day = today.isoformat()
    rep = health.RunReport("evening", day)
    rep.start(_now())
    _save_run(rep)

    dc = await _build_context(app, rep, today)
    if dc is None:
        return

    # Shaxsiy: 3 karta har agentga (har biri ALOHIDA himoyalangan)
    for ag in dc.agents:
        await _guard(rep, "agent",
                     lambda ag=ag: _agent_evening_one(app, dc, ag, day), ag.short)

    # Guruh: kunlik ball reytingi (yig'indisiz)
    for league in ("city", "region"):
        await _guard(rep, "guruh", lambda lg=league: _group_daily(app, dc, day, lg), league)

    # Admin: kechki svodka (shahar + viloyat)
    await _guard(rep, "admin", lambda: _admin_evening(app, dc, day))

    # Supervayzerga: oylik (strike markazda) + kunlik jadval (liga bo'yicha)
    for league in ("city", "region"):
        await _guard(rep, "supervayzer", lambda lg=league: _send_supervisor(
            app, lg, sup_monthly_png(dc, lg), day, "monthly"), f"{league}/oylik")
        await _guard(rep, "supervayzer", lambda lg=league: _send_supervisor(
            app, lg, sup_daily_png(dc, lg), day, "daily"), f"{league}/kunlik")
        # Plan jadvali — yakshanba (dam olish kuni) yuborilmaydi
        if sup_plan and today.weekday() != 6:
            await _guard(rep, "supervayzer", lambda lg=league: _send_supervisor(
                app, lg, sup_plan.plan_png(dc, lg), day, "plan"), f"{league}/plan")

    # GPS kunlik xulosa (admin doim; supervayzerlar NZ_GPS_TO_SUPERVISORS=1 bo'lsa).
    # O'zi ichida liga bo'yicha himoyalangan — shuning uchun _guard'siz chaqiriladi.
    await _gps_summary(app, day, today, rep)

    # Ogohlantirishlar (2 kun 0 ball)
    for ag in dc.agents:
        if ag.observe_only:
            continue
        await _guard(rep, "signal",
                     lambda ag=ag: _alert_one(app, dc, ag, day), ag.short)

    rep.finish(_now())
    _save_run(rep)
    logger.info("Kechki job tugadi: %s", rep.short())


async def _agent_evening_one(app, dc: DayContext, ag, day: str) -> str:
    """Bitta agentning kechki 3 kartasi."""
    if _new_agent_cards(dc.today):
        photos = aksiya_cards.agent_cards(dc, ag.sd_id)      # natija + reja + aksiya daftari
    else:
        cards = dc.evening_cards(ag.sd_id)
        photos = [render_ball_card(cards[0]), render_plan_card(cards[1]),
                  render_toy_card(cards[2])]
    return await _send_agent(app, ag.sd_id, photos, day, "evening")


async def _gps_summary(app, day: str, today, rep: health.RunReport):
    """GPS kunlik xulosa: har liga jadvali. Admin DOIM oladi (ikkala liga);
    supervayzerlar — NZ_GPS_TO_SUPERVISORS=1 va DRY_RUN=false bo'lganda.
    Yakshanba (dam kuni) yuborilmaydi. API yotsa — adminга xabar, job davom etadi.
    Liga bo'yicha himoyalangan: biri yiqilsa ikkinchisi baribir ketadi."""
    if today.weekday() == 6:
        return
    from . import gps
    try:
        visits = await gps.fetch_today_visits()
    except Exception as e:                           # noqa: BLE001
        logger.exception("GPS xulosa: vizitlar olinmadi")
        rep.note("gps", health.FAIL, "vizitlar", e)
        await _admins(app, text=f"⚠️ GPS xulosa tayyorlanmadi (Sales Doctor javob bermadi): {e}")
        return
    for league in ("city", "region"):
        await _guard(rep, "gps", lambda lg=league: _gps_one(app, day, today, visits, lg),
                     league)


async def _gps_one(app, day: str, today, visits, league: str) -> str:
    """Bitta liga GPS xulosasi: adminga (doim) + supervayzerga (yoqilgan bo'lsa)."""
    from . import gps
    from .cards import render_gps_summary
    from .nz_config import GPS_TO_SUPERVISORS

    x = gps.build_league_card(league, visits, today)
    png = render_gps_summary(x)
    cap = f"🕵 GPS kunlik xulosa · {x['title']}"
    status = health.DUP

    with get_conn() as conn:
        admin_sent = storage.already_sent(conn, day, f"gps_admin_{league}", "admin")
    if not admin_sent:
        await _admins(app, photo=png, text=cap)
        with get_conn() as conn:
            storage.mark_sent(conn, day, f"gps_admin_{league}", "admin", _now())
        status = health.SENT

    if not GPS_TO_SUPERVISORS or DRY_RUN:
        return status
    with get_conn() as conn:
        chat = storage.chat_for_supervisor(conn, SUPERVISOR_CODES.get(league, ""))
    if not chat:
        return status
    with get_conn() as conn:
        if storage.already_sent(conn, day, f"gps_sv_{league}", str(chat)):
            return status
    await app.bot.send_photo(chat, png, caption=cap)   # xato bo'lsa _guard ushlaydi
    with get_conn() as conn:
        storage.mark_sent(conn, day, f"gps_sv_{league}", str(chat), _now())
    return health.SENT


async def _group_daily(app, dc: DayContext, day: str, league: str) -> str:
    """Bitta liga guruhiga kunlik reyting (guruh ulanmagan bo'lsa — adminga)."""
    gid = GROUP_CITY_CHAT_ID if league == "city" else GROUP_REGION_CHAT_ID
    png = render_group_daily(dc.group_daily(league))
    target = "admin" if (DRY_RUN or not gid) else str(gid)
    with get_conn() as conn:
        if storage.already_sent(conn, day, f"group_{league}", target):
            return health.DUP
    if DRY_RUN or not gid:
        await _admins(app, photo=png, text=f"[DRY_RUN] guruh reyting → {league}")
    else:
        await app.bot.send_photo(gid, png)        # xato bo'lsa _guard ushlaydi
    with get_conn() as conn:
        storage.mark_sent(conn, day, f"group_{league}", target, _now())
    return health.SENT


async def _admin_evening(app, dc: DayContext, day: str):
    with get_conn() as conn:
        if storage.already_sent(conn, day, "admin_evening", "admin"):
            return
    for league in ("city", "region"):
        await _admins(app, photo=render_admin_summary(dc.admin_evening(league)))
    with get_conn() as conn:
        storage.mark_sent(conn, day, "admin_evening", "admin", _now())


# ==================================================================
# WATCHDOG — "baqiradigan" nazorat xabari (kechki 20:40 / ertalabki 10:30)
# ==================================================================

async def watchdog(app: Application, job: str):
    """Job natijasini adminга BITTA xabar qilib yuboradi: nima ketdi, nima ketmadi.
    Job umuman ishlamasa yoki yarmida qulasa — shu xabar buni AYTADI.
    Idempotent: bir kunda bir marta (notified_at)."""
    today = date.today()
    day = today.isoformat()
    with get_conn() as conn:
        row = storage.get_job_run(conn, day, job)
        if row is not None and row["notified_at"]:
            return                                  # bu kun uchun allaqachon xabar berilgan
    data = dict(row) if row is not None else None
    day_label = f"{today.day}-{MONTHS_UZ[today.month]}"

    # Job hali ishlayaptimi? (sync band bo'lib kechikkan bo'lishi mumkin — bu trevoga emas)
    age_min = None
    if data and data.get("started_at") and not data.get("finished_at"):
        try:
            from datetime import datetime as _dt
            from zoneinfo import ZoneInfo
            started = _dt.fromisoformat(data["started_at"])
            age_min = (_dt.now(ZoneInfo("Asia/Tashkent")) - started).total_seconds() / 60
        except (ValueError, TypeError):
            age_min = None

    text = health.build_watchdog_text(job, day_label, data, running_age_min=age_min)
    await _admins(app, text=text)
    # Hali ishlayotgan bo'lsa "xabar berildi" deb belgilamaymiz — tugagach yana tekshiriladi
    if row is not None and not (age_min is not None and age_min < health.RUNNING_OK_MIN):
        with get_conn() as conn:
            storage.mark_job_notified(conn, day, job, _now())
    logger.info("Watchdog (%s) xabari yuborildi", job)


async def _alert_one(app, dc: DayContext, ag, day: str) -> str:
    """Bitta agent: 2 kun ketma-ket 0 ball → alohida ohangda xabar."""
    if _new_agent_cards(dc.today):
        return health.SKIP                   # yangi oqimda ball yo'q — agentga ogohlantirish yo'q
    s = dc.snap[ag.sd_id]
    zs = zero_streak(s.balls, dc.today)
    if zs < dc.rules.alerts.dead_days_zero_ball:
        return health.SKIP                   # signal shart emas (yaxshi holat)
    kind = f"alert_zero_{day}"
    with get_conn() as conn:
        chat = storage.chat_for_sd_id(conn, ag.sd_id)
        target = "admin" if DRY_RUN else (str(chat) if chat else None)
        if target is None:
            return health.UNBOUND
        if storage.already_sent(conn, day, kind, target):
            return health.DUP
    text = (f"{zs} kun natija bo'lmadi. Bugun kichik bo'lsa ham buyurtma kiriting — "
            f"80% reja ham 1 ball beradi. Hali hammasi qo'lingizda!")
    dest = list(ADMIN_IDS) if DRY_RUN else [chat]
    ok = False
    last_err: Exception | None = None
    for did in dest:
        try:
            await app.bot.send_message(did, (f"[DRY_RUN {ag.name}] " if DRY_RUN else "") + text)
            ok = True
        except TelegramError as e:
            last_err = e
    if not ok:
        raise last_err or RuntimeError("signal yuborilmadi")
    with get_conn() as conn:
        storage.mark_sent(conn, day, kind, target, _now())
    return health.SENT
