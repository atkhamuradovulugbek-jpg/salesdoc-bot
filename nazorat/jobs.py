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

from . import storage
from .build import DayContext
from .cards import (render_admin_summary, render_ball_card, render_debt_card,
                    render_group_daily, render_plan_card, render_returns_card,
                    render_toy_card)
from .core.balls import zero_streak
from .nz_config import ADMIN_IDS, DRY_RUN, GROUP_CITY_CHAT_ID, GROUP_REGION_CHAT_ID

logger = logging.getLogger("nazorat.jobs")


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


async def _send_agent(app, sd_id: str, photos: list[bytes], day: str, kind: str):
    """Agent shaxsiy chatiga (DRY_RUN bo'lsa adminga). Idempotent."""
    with get_conn() as conn:
        chat = storage.chat_for_sd_id(conn, sd_id)
        target = "admin" if DRY_RUN else (str(chat) if chat else None)
        if target is None:
            return  # agent hali ulanmagan
        if storage.already_sent(conn, day, kind, target):
            return

    dest_ids = list(ADMIN_IDS) if DRY_RUN else [chat]
    ok = False
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
    if ok:
        with get_conn() as conn:
            storage.mark_sent(conn, day, kind, target, _now())


# ==================================================================
# 10:00 — ertalabki qarz/vazvrat
# ==================================================================

async def morning_job(app: Application):
    logger.info("Ertalabki job boshlandi (DRY_RUN=%s)", DRY_RUN)
    today = date.today()
    day = today.isoformat()

    # Qarz tarixini saqlaymiz (yosh hisobi uchun) — har kuni bir marta
    with get_conn() as conn:
        n = storage.snapshot_balances(conn, day)
    logger.info("Qarz snapshot: %d do'kon", n)

    dc = DayContext(today)
    for ag in dc.agents:
        if ag.observe_only:
            continue
        card = dc.morning_card(ag.sd_id)
        photos = []
        if card["debt_total"] > 0:
            photos.append(render_debt_card(card))       # 1-jadval: qarz
        if card["returns_total"] > 0:
            photos.append(render_returns_card(card))    # 2-jadval: vazvrat
        if not photos:
            continue
        await _send_agent(app, ag.sd_id, photos, day, "morning")

    # Adminga ertalabki svodka (qarz/vazvrat bo'yicha eng muhimlari)
    await _admin_morning(app, dc, day)
    logger.info("Ertalabki job tugadi")


async def _admin_morning(app, dc: DayContext, day: str):
    with get_conn() as conn:
        if storage.already_sent(conn, day, "admin_morning", "admin"):
            return
    for league in ("city", "region"):
        summ = dc.admin_evening(league)   # jadval bir xil, ertalab qarz muhim
        summ["title"] = f"ertalabki svodka · {'shahar' if league=='city' else 'viloyat'}"
        await _admins(app, photo=render_admin_summary(summ))
    with get_conn() as conn:
        storage.mark_sent(conn, day, "admin_morning", "admin", _now())


# ==================================================================
# 20:00 — kechki natija + guruh reyting
# ==================================================================

async def evening_job(app: Application):
    logger.info("Kechki job boshlandi (DRY_RUN=%s)", DRY_RUN)
    today = date.today()
    day = today.isoformat()
    dc = DayContext(today)

    # Shaxsiy: 3 karta har agentga
    for ag in dc.agents:
        cards = dc.evening_cards(ag.sd_id)
        photos = [render_ball_card(cards[0]), render_plan_card(cards[1]),
                  render_toy_card(cards[2])]
        await _send_agent(app, ag.sd_id, photos, day, "evening")

    # Guruh: kunlik ball reytingi (yig'indisiz)
    await _group_daily(app, dc, day)

    # Admin: kechki svodka (shahar + viloyat)
    await _admin_evening(app, dc, day)

    # Ogohlantirishlar (2 kun 0 ball)
    await _alerts(app, dc, day)
    logger.info("Kechki job tugadi")


async def _group_daily(app, dc: DayContext, day: str):
    targets = {"city": GROUP_CITY_CHAT_ID, "region": GROUP_REGION_CHAT_ID}
    for league, gid in targets.items():
        png = render_group_daily(dc.group_daily(league))
        target = "admin" if (DRY_RUN or not gid) else str(gid)
        with get_conn() as conn:
            if storage.already_sent(conn, day, f"group_{league}", target):
                continue
        try:
            if DRY_RUN or not gid:
                await _admins(app, photo=png,
                              text=f"[DRY_RUN] guruh reyting → {league}")
            else:
                await app.bot.send_photo(gid, png)
            with get_conn() as conn:
                storage.mark_sent(conn, day, f"group_{league}", target, _now())
        except TelegramError as e:
            logger.warning("guruh %s yuborilmadi: %s", league, e)


async def _admin_evening(app, dc: DayContext, day: str):
    with get_conn() as conn:
        if storage.already_sent(conn, day, "admin_evening", "admin"):
            return
    for league in ("city", "region"):
        await _admins(app, photo=render_admin_summary(dc.admin_evening(league)))
    with get_conn() as conn:
        storage.mark_sent(conn, day, "admin_evening", "admin", _now())


async def _alerts(app, dc: DayContext, day: str):
    """2 kun ketma-ket 0 ball → agentga alohida ohang + adminga signal."""
    for ag in dc.agents:
        if ag.observe_only:
            continue
        s = dc.snap[ag.sd_id]
        zs = zero_streak(s.balls, dc.today)
        if zs < dc.rules.alerts.dead_days_zero_ball:
            continue
        kind = f"alert_zero_{day}"
        with get_conn() as conn:
            chat = storage.chat_for_sd_id(conn, ag.sd_id)
            target = "admin" if DRY_RUN else (str(chat) if chat else None)
            if target is None or storage.already_sent(conn, day, kind, target):
                continue
        text = (f"{zs} kun natija bo'lmadi. Bugun kichik bo'lsa ham buyurtma kiriting — "
                f"80% reja ham 1 ball beradi. Hali hammasi qo'lingizda!")
        dest = list(ADMIN_IDS) if DRY_RUN else [chat]
        for did in dest:
            try:
                await app.bot.send_message(did, (f"[DRY_RUN {ag.name}] " if DRY_RUN else "") + text)
            except TelegramError:
                pass
        with get_conn() as conn:
            storage.mark_sent(conn, day, kind, target, _now())
