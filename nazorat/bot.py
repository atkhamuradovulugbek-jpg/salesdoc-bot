"""
nazorat/bot.py — Siribom Nazorat Bot (agentlarga qaragan motivatsiya boti).
Asosiy salesdoc-bot'dan ALOHIDA Telegram bot, lekin bir xil bot.db.

Xabarlar:
  10:00 — ertalabki qarz/vazvrat (shaxsiy)
  20:00 — kunlik natija + oylik plan + Toy (shaxsiy) + guruh kunlik ball reytingi
  Kritik ogohlantirishlar (qarz limiti / 2 kun 0 ball)
DRY_RUN=true bo'lsa — hammasi FAQAT adminga (sinov davri).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup,
                      ReplyKeyboardMarkup, Update)
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)

from db import get_conn, init_db

from . import binding, debtwatch, quick, storage
from .build import DayContext
from .cards import (render_ball_card, render_debt_card, render_debt_control,
                    render_group_daily,
                    render_plan_card, render_returns_card,
                    render_supervisor_debt, render_toy_card)
from .core.rules import load_agents
from .jobs import sup_daily_png, sup_monthly_png, sup_plan
from .nz_config import (ADMIN_IDS, DRY_RUN, EVENING_HOUR, EVENING_MINUTE,
                        NAZORAT_BOT_TOKEN, TIMEZONE)
from .storage import init_nz_tables

logger = logging.getLogger("nazorat.bot")

# Yangi agent kartalari (2026-10-08 20:10 dan). Yuklanmasa — eski oqim ishlayveradi.
try:
    from . import aksiya_cards
except Exception as _aks_err:                       # noqa: BLE001
    aksiya_cards = None
    logger.error("aksiya_cards yuklanmadi: %s", _aks_err)


def _new_cards() -> bool:
    """True — INTERAKTIV agent oqimi yangi (menyu, tugmalar, /start, yordam, eski tugmalar):
    natija + reja + aksiya daftari, Happy Toy/ball yo'q. Egasi qarori 2026-10-07 — darhol.
    AVTOMATIK 20:10 to'plami alohida gate'da (jobs._new_agent_cards, 2026-10-08 20:10)."""
    return aksiya_cards is not None

AGENTS_CFG = load_agents()
CODE_TO_AGENT = {a.code.upper(): a for a in AGENTS_CFG.agents}
CODE_TO_SUP = {s.code.upper(): s for s in AGENTS_CFG.supervisors}
CODE_TO_DEBT = {d.code.upper(): d for d in AGENTS_CFG.debt_controllers}
SD_TO_AGENT = {a.sd_id: a for a in AGENTS_CFG.agents}

# Agent uchun doimiy tugmalar (matn buyruq o'rniga — foydalanuvchi qarori 2026-07-14)
AGENT_KB = ReplyKeyboardMarkup(
    [["📊 Bugungi natija", "🕐 Kechagi natija"],
     ["📅 Oylik ball", "🎁 Happy Toy"],
     ["💳 Qarzlar", "↩️ Vazvratlar"],
     ["❓ Yordam"]],
    resize_keyboard=True,
)

# 2026-10-08 20:10 dan — Happy Toy va Oylik ball tugmalari agentdan olib tashlangan
# (egasi qarori 2026-10-07)
AGENT_KB_NEW = ReplyKeyboardMarkup(
    [["📊 Bugungi natija", "🕐 Kechagi natija"],
     ["💳 Qarzlar", "↩️ Vazvratlar"],
     ["❓ Yordam"]],
    resize_keyboard=True,
)


def agent_kb() -> ReplyKeyboardMarkup:
    return AGENT_KB_NEW if _new_cards() else AGENT_KB

# Admin uchun tugmalar (ulanganlarni ko'rish/uzish)
ADMIN_KB = ReplyKeyboardMarkup(
    [["👥 Ulanganlar"]],
    resize_keyboard=True,
)

# Supervayzer uchun tugmalar (liga jadvallari)
# QARZ NAZORATCHISI (2026-08-13) — o'z klaviaturasi. Agent/supervayzerникига
# TEGILMAYDI: bu butunlay alohida rol.
DEBT_KB = ReplyKeyboardMarkup(
    [["💳 Hozirgi qarzlar"],
     ["🏪 Qarzli do'konlar"]],
    resize_keyboard=True,
)

SUPERVISOR_KB = ReplyKeyboardMarkup(
    [["📊 Oylik jadval", "📋 Kunlik jadval"],
     ["💳 Qarz-vazvrat", "⚡ Hozirgi holat"],
     ["❓ Yordam"]],
    resize_keyboard=True,
)


def _sup_league(binding) -> str | None:
    sup = CODE_TO_SUP.get((binding["code"] or "").upper())
    return sup.league if sup else None


def _period(dc) -> str:
    """Karta tagidagi izoh uchun davr: '1–14 iyul'."""
    from .data import MONTHS_UZ
    t = dc.today
    return f"1–{t.day} {MONTHS_UZ[t.month].lower()}"


def _now() -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Asia/Tashkent")).isoformat(timespec="seconds")


# Bugungi natija (savdo/ball/toy) FAQAT kechki avtomatik hisobotdan keyin ochiladi.
# Maqsad — "ochilish daqiqasi" qiziqarli bo'lsin; kunduzi agent faqat kechagi natijani
# ko'radi (kunlik savdoni Sales Doctor'da baribir ko'rib turadi). Qarz/vazvrat doim ochiq.
# Ochilish vaqti config'dan (EVENING_HOUR:EVENING_MINUTE) — hozir 20:10.
REVEAL_STR = f"{EVENING_HOUR:02d}:{EVENING_MINUTE:02d}"
LOCKED_MSG = (
    f"🔒 Bugungi natija soat {REVEAL_STR} da ochiladi.\n\n"
    f"Hozircha 🕐 <b>Kechagi natija</b> tugmasi orqali kechagi natijangizni ko'rishingiz mumkin.\n"
    f"Bugungi savdo, ball va o'rin — kechqurun {REVEAL_STR} da e'lon qilinadi. Omad! 🔥"
)
# Yangi oqimda ball yo'q — matn shunga mos (2026-10-08 20:10 dan)
LOCKED_MSG_NEW = LOCKED_MSG.replace("Bugungi savdo, ball va o'rin", "Bugungi savdo, o'rin va aksiya")


def _locked_msg() -> str:
    return LOCKED_MSG_NEW if _new_cards() else LOCKED_MSG


def _today_locked() -> bool:
    """True — hozir kechki hisobot vaqtidan (EVENING_HOUR:EVENING_MINUTE, Asia/Tashkent)
    OLDIN bo'lsa. Shu payt bugungi natija berkitilgan."""
    from datetime import datetime, time
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo(TIMEZONE))
    return now.time() < time(EVENING_HOUR, EVENING_MINUTE)


# ==================================================================
# Kod ulash (/start)
# ==================================================================

WELCOME = (
    "👋 Assalomu alaykum! Siribom Nazorat botiga xush kelibsiz.\n\n"
    "Botga ulanish uchun <b>o'z kodingizni</b> yuboring.\n"
    "Kod — Sales Doctor'dagi agent kodingiz (masalan <code>TSH-YNB-01</code>).\n\n"
    "Kodni bilmasangiz — administratorga murojaat qiling."
)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in ADMIN_IDS:
        await update.message.reply_text(
            "👋 Admin panel. Ulangan agentlarni ko'rish/uzish uchun tugmani bosing 👇",
            reply_markup=ADMIN_KB)
        return
    with get_conn() as conn:
        b = storage.binding_by_chat(conn, chat_id)
    if b and b["role"] == "agent":
        await update.message.reply_text(
            "✅ Siz ulangansiz. Quyidagi tugmalardan foydalaning 👇",
            reply_markup=agent_kb())
        return
    if b and b["role"] == "supervisor":
        await update.message.reply_text(
            "✅ Siz ulangansiz (supervayzer). Quyidagi tugmalardan foydalaning 👇",
            reply_markup=SUPERVISOR_KB)
        return
    await update.message.reply_text(WELCOME, parse_mode=ParseMode.HTML)


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Ulangan bo'lsa — TUGMA bosilganini tekshiradi. Ulanmagan bo'lsa — matn KOD deb
    olinadi va ADMIN TASDIG'IGA yuboriladi (eng xavfsiz — foydalanuvchi qarori 2026-07-14)."""
    chat_id = update.effective_chat.id
    raw = (update.message.text or "").strip()

    # GPS trevoga "ℹ️ Sababi" bosilgan — keyingi matn sabab sifatida yoziladi.
    # Faqat 5 daqiqa amal qiladi — aks holda keyingi har qanday matnni (kod, tugma)
    # "sabab" deb yutib yuborardi (2026-07-30 review topdi). (eid, vaqt) saqlanadi.
    import time as _t
    pending = ctx.application.bot_data.get("nzgps_pending", {})
    entry = pending.get(chat_id)
    if entry and raw:
        eid, ts = (entry if isinstance(entry, tuple) else (entry, _t.time()))
        if _t.time() - ts <= 300:
            pending.pop(chat_id, None)
            with get_conn() as conn:
                storage.gps_set_reason(conn, eid, raw)
            return await update.message.reply_text("✅ Sabab yozib olindi va saqlandi.")
        pending.pop(chat_id, None)          # eskirgan — oddiy matn sifatida davom etadi

    # Admin tugmasi (ulanganlarni ko'rish/uzish)
    if chat_id in ADMIN_IDS and raw == "👥 Ulanganlar":
        return await cmd_admin_connected(update, ctx)

    with get_conn() as conn:
        # DIQQAT: o'zgaruvchi nomi `binding` BO'LMASIN — u `binding` modulini bosib qo'yadi
        # (2026-07-30 review: shu sabab ulanish oqimi butunlay ishlamay qolgan edi).
        bnd = storage.binding_by_chat(conn, chat_id)

    # Allaqachon ulangan — FAQAT tugmalar ishlaydi (matn yozsa — tugmalarni eslatadi)
    if bnd:
        if bnd["role"] == "debt":
            h = DEBT_BUTTON_HANDLERS.get(raw)
            if h:
                return await h(update, ctx)
            await update.message.reply_text(
                "⌨️ Pastdagi tugmalardan foydalaning 👇", reply_markup=DEBT_KB)
            return
        if bnd["role"] == "supervisor":
            h = SUP_BUTTON_HANDLERS.get(raw)
            if h:
                return await h(update, ctx)
            await update.message.reply_text(
                "⌨️ Pastdagi tugmalardan foydalaning 👇", reply_markup=SUPERVISOR_KB)
            return
        handler = BUTTON_HANDLERS.get(raw)
        if handler:
            return await handler(update, ctx)
        await update.message.reply_text(
            "⌨️ Iltimos, pastdagi tugmalardan foydalaning 👇", reply_markup=agent_kb())
        return

    # Ulanmagan — matn kod deb olinadi
    code = raw.upper()
    agent = CODE_TO_AGENT.get(code)
    sup = CODE_TO_SUP.get(code)
    dbt = CODE_TO_DEBT.get(code)
    is_admin = chat_id in ADMIN_IDS

    # Admin o'zi — tasdiq shart emas
    if is_admin and code in ("ADMIN", "/ADMIN"):
        with get_conn() as conn:
            storage.bind_code(conn, code, chat_id, "admin", None, _now())
        return await update.message.reply_text("✅ Admin ulandingiz.")

    if agent:
        name = agent.name
    elif sup:
        name = sup.name
    elif dbt:
        name = dbt.name
    else:
        return await update.message.reply_text(
            "❌ Kod noto'g'ri. Iltimos, kodingizni tekshirib qayta yuboring.")

    # Admin tasdig'i uchun so'rov
    user = update.effective_user
    who = f"@{user.username}" if (user and user.username) else (
        (user.full_name if user else None) or str(chat_id))
    # So'rovni BAZAGA yozamiz — web ekranida "kutilyapti" bo'lib ko'rinadi
    # (avval bu holat faqat Telegram tugmasida yashardi).
    with get_conn() as conn:
        binding.create_request(conn, code, chat_id, who)
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Ha", callback_data=f"nzbind:ok:{chat_id}:{code}"),
        InlineKeyboardButton("❌ Yo'q", callback_data=f"nzbind:no:{chat_id}:{code}"),
    ]])
    await update.message.reply_text(
        "⏳ So'rovingiz administratorga yuborildi. Tasdiqlangach xabar beramiz.")
    for aid in ADMIN_IDS:
        try:
            await ctx.application.bot.send_message(
                aid, f"🔐 Ulanish so'rovi:\n"
                     f"Kim: {who} (chat {chat_id})\n"
                     f"Kod: {code} → {name}\n"
                     f"Tasdiqlaysizmi?",
                reply_markup=kb)
        except TelegramError:
            pass


# ==================================================================
# Buyruqlar
# ==================================================================

async def _get_binding(chat_id: int):
    with get_conn() as conn:
        return storage.binding_by_chat(conn, chat_id)


# Ulangan agent Sales Doctor'da o'chirilgan bo'lsa (ishdan ketgan) — tugmalar KeyError
# bermasin, tushunarli javob bersin (1-bosqich, 2026-07-30).
INACTIVE_MSG = ("⚠️ Hisobingiz hozir faol emas (Sales Doctor'da o'chirilgan).\n"
                "Shu sababli hisobot ko'rsatilmaydi. Rahbaringizga murojaat qiling.")


async def _agent_ctx(update: Update, b, today=None) -> DayContext | None:
    """Agent uchun DayContext + faollik tekshiruvi. None qaytsa — javob allaqachon berilgan."""
    dc = DayContext(today=today) if today is not None else DayContext()
    if b["sd_id"] not in dc.snap:
        await update.message.reply_text(INACTIVE_MSG, reply_markup=agent_kb())
        return None
    return dc


async def cmd_bugun(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    b = await _get_binding(update.effective_chat.id)
    if not b or b["role"] != "agent":
        return await update.message.reply_text("Avval kodingizni yuboring: /start")
    if _today_locked():
        return await update.message.reply_text(
            _locked_msg(), parse_mode=ParseMode.HTML, reply_markup=agent_kb())
    dc = await _agent_ctx(update, b)
    if dc is None:
        return
    p = _period(dc)
    if _new_cards():
        photos = aksiya_cards.agent_cards(dc, b["sd_id"], "bugun")
        caps = [f"📊 Bugungi natija · {p}", f"📅 Oylik savdo reja · {p}",
                aksiya_cards.ledger_caption(dc)]
        for i, (ph, cap) in enumerate(zip(photos, caps)):
            # oxirgi rasm bilan yangi menyu (telefondagi eski klaviatura passiv yangilanadi)
            await update.message.reply_photo(
                ph, caption=cap, reply_markup=agent_kb() if i == len(photos) - 1 else None)
        return
    cards = dc.evening_cards(b["sd_id"])
    await update.message.reply_photo(render_ball_card(cards[0]),
                                     caption=f"📊 Bugungi natija + oylik ball · {p}")
    await update.message.reply_photo(render_plan_card(cards[1]),
                                     caption=f"📅 Oylik savdo reja · {p}")
    await update.message.reply_photo(render_toy_card(cards[2]),
                                     caption=f"🎁 Happy Toy · {p}")


async def cmd_kecha(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Kechagi natija — ball/reja/toy kartalari (kecha holatiga)."""
    b = await _get_binding(update.effective_chat.id)
    if not b or b["role"] != "agent":
        return await update.message.reply_text("Avval kodingizni yuboring: /start")
    y = date.today() - timedelta(days=1)
    dc = await _agent_ctx(update, b, today=y)
    if dc is None:
        return
    p = _period(dc)   # kecha holatiga: masalan "1–13 iyul"
    if _new_cards():
        photos = aksiya_cards.agent_cards(dc, b["sd_id"], "kecha")
        caps = [f"🕐 Kechagi natija · {p}", f"📅 Oylik savdo reja (kecha holatiga) · {p}",
                f"{aksiya_cards.ledger_caption(dc)} (kecha holatiga)"]
        for i, (ph, cap) in enumerate(zip(photos, caps)):
            # oxirgi rasm bilan yangi menyu (telefondagi eski klaviatura passiv yangilanadi)
            await update.message.reply_photo(
                ph, caption=cap, reply_markup=agent_kb() if i == len(photos) - 1 else None)
        return
    cards = dc.evening_cards(b["sd_id"])
    await update.message.reply_photo(render_ball_card(cards[0]),
                                     caption=f"🕐 Kechagi natija + oylik ball · {p}")
    await update.message.reply_photo(render_plan_card(cards[1]),
                                     caption=f"📅 Oylik savdo reja (kecha holatiga) · {p}")
    await update.message.reply_photo(render_toy_card(cards[2]),
                                     caption=f"🎁 Happy Toy · {p}")


async def cmd_toy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    b = await _get_binding(update.effective_chat.id)
    if not b or b["role"] != "agent":
        return await update.message.reply_text("Avval kodingizni yuboring: /start")
    if _new_cards():
        # Happy Toy agentga yuborilmaydi (eski klaviaturadan bosilsa — yangisini beramiz)
        return await update.message.reply_text(
            "⌨️ Iltimos, pastdagi tugmalardan foydalaning 👇", reply_markup=agent_kb())
    if _today_locked():
        return await update.message.reply_text(
            LOCKED_MSG, parse_mode=ParseMode.HTML, reply_markup=agent_kb())
    dc = await _agent_ctx(update, b)
    if dc is None:
        return
    await update.message.reply_photo(render_toy_card(dc.evening_cards(b["sd_id"])[2]),
                                     caption=f"🎁 Happy Toy · {_period(dc)}")


async def cmd_qarz(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    b = await _get_binding(update.effective_chat.id)
    if not b or b["role"] != "agent":
        return await update.message.reply_text("Avval kodingizni yuboring: /start")
    dc = await _agent_ctx(update, b)
    if dc is None:
        return
    await update.message.reply_photo(render_debt_card(dc.morning_card(b["sd_id"])),
                                     caption="💳 Qarzdorliklar · bugungi holat (50 ming so'mdan yuqori do'konlar)",
                                     reply_markup=agent_kb())


async def cmd_vazvrat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    b = await _get_binding(update.effective_chat.id)
    if not b or b["role"] != "agent":
        return await update.message.reply_text("Avval kodingizni yuboring: /start")
    dc = await _agent_ctx(update, b)
    if dc is None:
        return
    await update.message.reply_photo(render_returns_card(dc.morning_card(b["sd_id"])),
                                     caption=f"↩️ Vazvratlar · kunlik (kecha) + oylik jami ({_period(dc)})",
                                     reply_markup=agent_kb())


async def cmd_oy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    b = await _get_binding(update.effective_chat.id)
    if not b or b["role"] != "agent":
        return await update.message.reply_text("Avval kodingizni yuboring: /start")
    if _new_cards():
        # Ball taqvimi agentga ko'rsatilmaydi (eski klaviaturadan bosilsa — yangisini beramiz)
        return await update.message.reply_text(
            "⌨️ Iltimos, pastdagi tugmalardan foydalaning 👇", reply_markup=agent_kb())
    dc = await _agent_ctx(update, b)
    if dc is None:
        return
    s = dc.snap[b["sd_id"]]
    locked = _today_locked()
    # Matnli taqvim (ballar kun bo'yicha). 20:00 gacha bugungi ball yashirin.
    lines = [f"📅 <b>{s.today.strftime('%B')} — ball taqvimi</b>\n"]
    total = 0
    for d in sorted(s.balls.keys()):
        if locked and d >= dc.today:   # bugungi (va keyingi) ball 20:00 da ochiladi
            continue
        bar = "🔥" if s.balls[d] == 4 else "✅" if s.balls[d] == 3 else \
              "🟢" if s.balls[d] == 2 else "🟡" if s.balls[d] == 1 else "⚪️"
        lines.append(f"{d.day:2d}-kun: {bar} {s.balls[d]} ball")
        total += s.balls[d]
    if locked:
        lines.append(f"\n<b>Jami (kechagacha): {total} ball</b>")
        lines.append(f"🔒 Bugungi ball soat {REVEAL_STR} da qo'shiladi.")
    else:
        lines.append(f"\n<b>Jami: {s.month_ball} ball</b>")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


def _agent_league(sd_id: str | None) -> str | None:
    """Ulangan agentning JORIY ligasi (faol ro'yxatdan). Topilmasa — None (tarif ko'rsatilmaydi)."""
    if not sd_id:
        return None
    from . import roster
    with get_conn() as conn:
        for a in roster.active_agents(conn, AGENTS_CFG):
            if a.sd_id == sd_id:
                return a.league if a.league in ("city", "region") else None
    return None


async def cmd_yordam(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    b = await _get_binding(update.effective_chat.id)
    from .jobs import sup_cards
    if b and b["role"] == "supervisor" and sup_cards:
        # Supervayzer — o'z jadvallari va FAQAT bindingidagi o'z ligasi tarifi
        from .nz_config import ALERTS_TO_SUPERVISORS, GPS_TO_SUPERVISORS
        return await update.message.reply_text(
            sup_cards.help_text(_sup_league(b), REVEAL_STR, ALERTS_TO_SUPERVISORS, GPS_TO_SUPERVISORS),
            parse_mode=ParseMode.HTML, reply_markup=SUPERVISOR_KB)
    if _new_cards():
        # Agent — faqat O'Z ligasi tarifi. Boshqa rol/ulanmagan — tarifsiz, o'z menyusi saqlanadi.
        is_agent = bool(b and b["role"] == "agent")
        league = _agent_league(b["sd_id"]) if is_agent else None
        return await update.message.reply_text(
            aksiya_cards.help_text(league, REVEAL_STR), parse_mode=ParseMode.HTML,
            reply_markup=agent_kb() if is_agent else None)
    await update.message.reply_text(
        "<b>Siribom Nazorat — qoidalar</b>\n\n"
        "🎯 <b>Ball:</b> kunlik savdo ÷ reja → 80%=1, 90%=2, 100%=3, 150%+=4 ball. "
        "Oy bo'yi jamlanadi. Tovar qaytsa o'sha kun balli kamayadi.\n"
        "🏆 <b>Podium:</b> oy oxirida plandan eng ko'p oshgan 3 agent sovrin oladi.\n"
        "🧸 <b>Toy:</b> 105 blok=600k, 135=900k, 150=1.2mln (qaytmagan mahsulotga).\n"
        "💵 <b>KPI:</b> oylik plan bajarilishiga qarab komissiya + bonus.\n"
        "💳 <b>Qarz:</b> limitdan oshmasin.\n\n"
        "Pastdagi tugmalardan foydalaning 👇",
        parse_mode=ParseMode.HTML,
        reply_markup=agent_kb(),
    )


# ---- Supervayzer buyruqlari (liga jadvallari) ----

async def cmd_sup_oylik(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    b = await _get_binding(update.effective_chat.id)
    if not b or b["role"] != "supervisor":
        return await update.message.reply_text("Avval kodingizni yuboring: /start")
    league = _sup_league(b)
    if not league:
        return await update.message.reply_text("Liga aniqlanmadi.")
    dc = DayContext()
    await update.message.reply_photo(
        sup_monthly_png(dc, league),
        caption=f"📊 Oylik jadval · strike + oy savdo + aksiya ({_period(dc)})",
        reply_markup=SUPERVISOR_KB)


async def cmd_sup_kunlik(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    b = await _get_binding(update.effective_chat.id)
    if not b or b["role"] != "supervisor":
        return await update.message.reply_text("Avval kodingizni yuboring: /start")
    league = _sup_league(b)
    if not league:
        return await update.message.reply_text("Liga aniqlanmadi.")
    dc = DayContext()
    await update.message.reply_photo(
        sup_daily_png(dc, league),
        caption="📋 Kunlik jadval · bugungi sof savdo/aksiya/vizit",
        reply_markup=SUPERVISOR_KB)


async def cmd_sup_hozir(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """⚡ Hozirgi holat — Sales Doctor'dan BUGUNGI ma'lumotni tortib, keyin jadval.

    Kunlik jadval bilan bir xil rasm, farqi: oldin ~5 soniyada yangi ma'lumot
    olinadi. Kutish (90s) ichida bosilsa qayta tortilmaydi — bordagi ko'rsatiladi."""
    b = await _get_binding(update.effective_chat.id)
    if not b or b["role"] != "supervisor":
        return await update.message.reply_text("Avval kodingizni yuboring: /start")
    league = _sup_league(b)
    if not league:
        return await update.message.reply_text("Liga aniqlanmadi.")

    wait = await update.message.reply_text("⏳ Yangilanmoqda...")
    ok, note = await quick.refresh("supervisor")

    with get_conn() as conn:
        age = quick.seconds_since(quick.last_any_sync(conn))
    stamp = _now()[11:16]
    head = (f"🕐 Hozirgi holat · {stamp}" if ok
            else f"🕐 {quick.age_text(age)} holatiga ({note})")

    dc = DayContext()
    try:
        await wait.delete()
    except Exception:                                     # noqa: BLE001
        pass
    await update.message.reply_photo(
        sup_daily_png(dc, league),
        caption=f"📋 Kunlik jadval · bugungi sof savdo/aksiya/vizit\n{head}\n"
                f"<i>Qarz va ombor raqamlari bunda yangilanmaydi.</i>",
        parse_mode="HTML", reply_markup=SUPERVISOR_KB)


async def cmd_sup_qarz(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    b = await _get_binding(update.effective_chat.id)
    if not b or b["role"] != "supervisor":
        return await update.message.reply_text("Avval kodingizni yuboring: /start")
    league = _sup_league(b)
    if not league:
        return await update.message.reply_text("Liga aniqlanmadi.")
    dc = DayContext()
    await update.message.reply_photo(
        render_supervisor_debt(dc.supervisor_debt(league)),
        caption=f"💳 Qarz-vazvrat · agent bo'yicha ({_period(dc)})",
        reply_markup=SUPERVISOR_KB)


async def _send_self_report(app, chat_id: int, bnd):
    # Parametr nomi `binding` BO'LMASIN — modulni bosib qo'yadi (yuqoridagi diqqatga qara).
    if bnd["role"] == "agent":
        dc = DayContext()
        if bnd["sd_id"] not in dc.snap:              # ketgan/faol emas — xato bermaydi
            return await app.bot.send_message(chat_id, INACTIVE_MSG)
        if _new_cards():
            for ph in aksiya_cards.agent_cards(dc, bnd["sd_id"], "bugun"):
                await app.bot.send_photo(chat_id, ph)
            return
        cards = dc.evening_cards(bnd["sd_id"])
        await app.bot.send_photo(chat_id, render_ball_card(cards[0]))
        await app.bot.send_photo(chat_id, render_plan_card(cards[1]))
        await app.bot.send_photo(chat_id, render_toy_card(cards[2]))
    else:
        await app.bot.send_message(chat_id, "✅ Ulangansiz.")


# ==================================================================
# Admin
# ==================================================================

async def _notify_admins(app, text: str):
    for aid in ADMIN_IDS:
        try:
            await app.bot.send_message(aid, text)
        except TelegramError:
            pass


async def on_bind_decision(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin 'Ha/Yo'q' bosdi — ulanish so'rovini tasdiqlaydi yoki rad etadi."""
    q = update.callback_query
    await q.answer()
    if q.message.chat.id not in ADMIN_IDS:
        return
    parts = q.data.split(":")
    if len(parts) < 4:
        return
    decision, target, code = parts[1], int(parts[2]), parts[3]
    # Mantiq binding.py da (web bilan BIR XIL kod yo'li — ikki xil amalga oshirish yo'q)
    r = binding.resolve_code(code)
    if not r:
        return await q.edit_message_text("❌ Kod topilmadi.")
    name = r[2]

    if decision == "no":
        await binding.reject(ctx.application, code, target, decided_by="telegram")
        return await q.edit_message_text(f"❌ Rad etildi: {name} ({code})")

    await binding.approve(ctx.application, code, target, decided_by="telegram")
    await q.edit_message_text(f"✅ Tasdiqlandi: {name} ({code}) → chat {target}")


async def cmd_admin_connected(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin: ulangan agent va supervayzerlar ro'yxati, har biriga Namuna/Uzish tugmasi."""
    if update.effective_chat.id not in ADMIN_IDS:
        return
    with get_conn() as conn:
        rows = storage.list_bindings(conn)
    agents = [r for r in rows if r["role"] == "agent"]
    sups = [r for r in rows if r["role"] == "supervisor"]
    if not agents and not sups:
        return await update.message.reply_text(
            "Hozircha ulangan agent yoki supervayzer yo'q.", reply_markup=ADMIN_KB)

    def _row_kb(code: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("📤 Namuna yuborish", callback_data=f"nzsample:{code}"),
            InlineKeyboardButton("❌ Uzish", callback_data=f"nzunbind:{code}")]])

    if agents:
        await update.message.reply_text(f"👥 Ulangan agentlar: {len(agents)} ta")
        for r in agents:
            ag = SD_TO_AGENT.get(r["sd_id"])
            name = ag.short if ag else r["code"]
            await update.message.reply_text(f"👤 {name} — {r['code']}", reply_markup=_row_kb(r["code"]))
    if sups:
        await update.message.reply_text(f"👔 Ulangan supervayzerlar: {len(sups)} ta")
        for r in sups:
            sup = CODE_TO_SUP.get((r["code"] or "").upper())
            name = sup.name if sup else r["code"]
            await update.message.reply_text(f"👔 {name} — {r['code']}", reply_markup=_row_kb(r["code"]))


async def on_send_sample(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin 'Namuna' bosdi — ulangan foydalanuvchining O'Z akkauntiga namuna to'plam yuboradi.
    Agent: kechagi to'liq to'plam. Supervayzer: ligangiz 3 jadvali."""
    q = update.callback_query
    if q.message.chat.id not in ADMIN_IDS:
        return await q.answer()
    await q.answer("📤 Yuborilyapti...")
    code = q.data.split(":", 1)[1]
    with get_conn() as conn:
        row = conn.execute(
            "SELECT chat_id, sd_id, role FROM nz_bindings WHERE code=?", (code,)
        ).fetchone()
    if not row:
        return await ctx.application.bot.send_message(
            q.message.chat.id, "❌ Bu foydalanuvchi hali ulanmagan (namuna yuborib bo'lmaydi).")
    chat, sd_id, role = row["chat_id"], row["sd_id"], row["role"]
    app = ctx.application

    # --- Supervayzer: ligangiz 3 jadvali (bugungi holat) ---
    if role == "supervisor":
        sup = CODE_TO_SUP.get(code.upper())
        league = sup.league if sup else None
        if not league:
            return await app.bot.send_message(q.message.chat.id, "❌ Liga aniqlanmadi.")
        dc = DayContext()
        p = _period(dc)
        try:
            await app.bot.send_message(chat, f"🧪 Namuna — ligangiz jadvallari ({p})")
            await app.bot.send_photo(chat, sup_monthly_png(dc, league),
                                     caption=f"📊 Oylik jadval · strike + oy savdo + aksiya ({p})")
            await app.bot.send_photo(chat, sup_daily_png(dc, league),
                                     caption="📋 Kunlik jadval · bugungi sof savdo/aksiya/vizit")
            if sup_plan:
                await app.bot.send_photo(chat, sup_plan.plan_png(dc, league),
                                         caption=f"🎯 Plan jadvali · yo'nalish plani ({p})")
            await app.bot.send_photo(chat, render_supervisor_debt(dc.supervisor_debt(league)),
                                     caption=f"💳 Qarz-vazvrat · agent bo'yicha ({p})")
            await app.bot.send_message(q.message.chat.id,
                                       f"✅ Namuna yuborildi: {sup.name}")
        except TelegramError as e:
            await app.bot.send_message(q.message.chat.id, f"❌ Yuborilmadi: {e}")
        return

    # --- Agent: kechagi to'liq to'plam ---
    y = date.today() - timedelta(days=1)
    dc = DayContext(today=y)
    if sd_id not in dc.snap:                         # ketgan/faol emas — adminга tushuntirish
        return await app.bot.send_message(
            q.message.chat.id,
            f"⚠️ {code}: bu agent Sales Doctor'da faol emas — namuna tayyorlanmadi.")
    p = _period(dc)
    mc = dc.morning_card(sd_id)
    ev = dc.evening_cards(sd_id)
    try:
        await app.bot.send_message(chat, f"🧪 Namuna — kechagi to'liq to'plam ({p})")
        await app.bot.send_photo(chat, render_debt_card(mc),
                                 caption="💳 Qarzdorliklar · bugungi holat")
        await app.bot.send_photo(chat, render_returns_card(mc),
                                 caption=f"↩️ Vazvratlar · kunlik + oylik ({p})")
        if _new_cards():
            caps = [f"🕐 Kechagi natija · {p}", f"📅 Oylik savdo reja · {p}",
                    aksiya_cards.ledger_caption(dc)]
            for ph, cap in zip(aksiya_cards.agent_cards(dc, sd_id, "kecha"), caps):
                await app.bot.send_photo(chat, ph, caption=cap)
            ag = SD_TO_AGENT.get(sd_id)
            return await app.bot.send_message(q.message.chat.id,
                                              f"✅ Namuna yuborildi: {ag.short if ag else code}")
        await app.bot.send_photo(chat, render_ball_card(ev[0]),
                                 caption=f"📊 Kechagi natija + oylik ball · {p}")
        await app.bot.send_photo(chat, render_plan_card(ev[1]),
                                 caption=f"📅 Oylik savdo reja · {p}")
        await app.bot.send_photo(chat, render_toy_card(ev[2]),
                                 caption=f"🎁 Happy Toy · {p}")
        ag = SD_TO_AGENT.get(sd_id)
        await app.bot.send_message(q.message.chat.id,
                                   f"✅ Namuna yuborildi: {ag.short if ag else code}")
    except TelegramError as e:
        await app.bot.send_message(q.message.chat.id, f"❌ Yuborilmadi: {e}")


async def on_unbind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin 'Uzish' bosdi — agent ulanishini o'chiradi."""
    q = update.callback_query
    await q.answer()
    if q.message.chat.id not in ADMIN_IDS:
        return
    code = q.data.split(":", 1)[1]
    # Mantiq binding.py da (web bilan bir xil yo'l)
    await binding.disconnect(ctx.application, code, decided_by="telegram")
    await q.edit_message_text(f"🔌 Uzildi: {binding.display_name(code)} ({code})")


async def on_gps_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """GPS trevoga tugmalari: 📞 Aloqaga chiqdim (ack) / ℹ️ Sababi (why)."""
    q = update.callback_query
    parts = q.data.split(":")
    if len(parts) < 3:
        return await q.answer()
    action, eid_s = parts[1], parts[2]
    try:
        eid = int(eid_s)
    except ValueError:
        return await q.answer()
    if eid == 0:  # namuna (demo) tugma
        return await q.answer("Bu namuna tugma ✅ (jonli trevogada ishlaydi)", show_alert=False)

    if action == "ack":
        with get_conn() as conn:
            storage.gps_ack(conn, eid, q.message.chat.id, _now())
        await q.answer("Belgilandi: aloqaga chiqdingiz ✅")
        # bosilgan epizod tugmalarini xabardan olib tashlaymiz
        try:
            kb = q.message.reply_markup.inline_keyboard if q.message.reply_markup else []
            rows = [r for r in kb
                    if not any((b.callback_data or "").endswith(f":{eid}") for b in r)]
            await q.edit_message_reply_markup(InlineKeyboardMarkup(rows) if rows else None)
        except TelegramError:
            pass
    elif action == "why":
        import time as _t
        ctx.application.bot_data.setdefault("nzgps_pending", {})[q.message.chat.id] = (eid, _t.time())
        await q.answer()
        try:
            await ctx.application.bot.send_message(
                q.message.chat.id,
                "ℹ️ Agent nima sababdan yo'q bo'lganini pastga yozib yuboring 👇\n\n"
                "Masalan: \"Kasal bo'lib, uyiga ketgan\".\n\n"
                "Bitta xabar yozsangiz yetarli — men uni saqlab qo'yaman.")
        except TelegramError:
            pass
    else:
        await q.answer()


async def cmd_tasdiqla(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Oy yakuni g'oliblarini tasdiqlab, agentlarga/guruhga e'lon qiladi."""
    if update.effective_chat.id not in ADMIN_IDS:
        return
    from .month_end import confirm_and_announce
    msg = await confirm_and_announce(ctx.application)
    await update.message.reply_text(msg)


# Tugma matni → buyruq funksiyasi (on_text shu orqali yo'naltiradi)
BUTTON_HANDLERS = {
    "📊 Bugungi natija": cmd_bugun,
    "🕐 Kechagi natija": cmd_kecha,
    "📅 Oylik ball": cmd_oy,
    "🎁 Happy Toy": cmd_toy,
    "💳 Qarzlar": cmd_qarz,
    "↩️ Vazvratlar": cmd_vazvrat,
    "❓ Yordam": cmd_yordam,
}

# Supervayzer tugmalari → funksiya
# ---- QARZ NAZORATCHISI (2026-08-13) ----

async def _debt_guard(update):
    b = await _get_binding(update.effective_chat.id)
    if not b or b["role"] != "debt":
        await update.message.reply_text("Avval kodingizni yuboring: /start")
        return None
    return b


async def cmd_debt_now(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """💳 Hozirgi qarzlar — balanslarni yangilab, shahar/viloyat rasmini beradi."""
    if not await _debt_guard(update):
        return
    wait = await update.message.reply_text("⏳ Qarzlar yangilanmoqda...")
    ok, note = await debtwatch.refresh_debt()

    with get_conn() as conn:
        by_league = {lg: debtwatch.rows_for(conn, lg) for lg, _ in debtwatch.LEAGUES}
        age = quick.seconds_since(quick.last_refresh(conn, kind="debt"))
    try:
        await wait.delete()
    except Exception:                                    # noqa: BLE001
        pass

    head = "🕐 Hozirgi holat" if ok else f"🕐 {quick.age_text(age)} holatiga ({note})"
    for lg, label in debtwatch.LEAGUES:
        rows = by_league[lg]
        if not rows:
            continue
        png = render_debt_control(debtwatch.card_dict(rows, label, "tugma"))
        over = sum(1 for r in rows if r["over"])
        await update.message.reply_photo(
            png, caption=f"💳 {label} · limitdan oshgan: <b>{over}</b> ta\n{head}",
            parse_mode="HTML")


async def cmd_debt_shops(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """🏪 Qarzli do'konlar — agent tanlash (eng qarzdorlari tepada)."""
    if not await _debt_guard(update):
        return
    with get_conn() as conn:
        rows = debtwatch.rows_for(conn)
    rows = [r for r in rows if r["debt"] > 0][:20]
    if not rows:
        return await update.message.reply_text("Qarzli agent yo'q ✅")
    kb = []
    for r in rows:
        mark = "🔴" if r["over"] else ("🟡" if r["near"] else "🟢")
        kb.append([InlineKeyboardButton(
            f"{mark} {r['name']} — {int(r['debt']):,}".replace(",", " "),
            callback_data=f"qrzshop:{r['sd_id']}")])
    await update.message.reply_text(
        "Qaysi agentning do'konlarini ko'rasiz?",
        reply_markup=InlineKeyboardMarkup(kb))


async def cb_debt_shops(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    b = await _get_binding(q.message.chat_id)
    if not b or b["role"] not in ("debt", "admin"):
        return
    sd_id = q.data.split(":", 1)[1]
    with get_conn() as conn:
        rows = {r["sd_id"]: r for r in debtwatch.rows_for(conn)}
        name = rows.get(sd_id, {}).get("name", sd_id)
        text = debtwatch.shops_text(conn, sd_id, name)
    await q.message.reply_text(text, parse_mode="HTML")


DEBT_BUTTON_HANDLERS = {
    "💳 Hozirgi qarzlar": cmd_debt_now,
    "🏪 Qarzli do'konlar": cmd_debt_shops,
}

SUP_BUTTON_HANDLERS = {
    "📊 Oylik jadval": cmd_sup_oylik,
    "📋 Kunlik jadval": cmd_sup_kunlik,
    "💳 Qarz-vazvrat": cmd_sup_qarz,
    "⚡ Hozirgi holat": cmd_sup_hozir,
    "❓ Yordam": cmd_yordam,            # rolga qarab: supervayzer — o'z ligasi
}
