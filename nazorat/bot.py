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
from datetime import date

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup,
                      ReplyKeyboardMarkup, Update)
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)

from db import get_conn, init_db

from . import storage
from .build import DayContext
from .cards import (render_ball_card, render_debt_card, render_group_daily,
                    render_plan_card, render_returns_card, render_toy_card)
from .core.rules import load_agents
from .nz_config import ADMIN_IDS, DRY_RUN, NAZORAT_BOT_TOKEN
from .storage import init_nz_tables

logger = logging.getLogger("nazorat.bot")

AGENTS_CFG = load_agents()
CODE_TO_AGENT = {a.code.upper(): a for a in AGENTS_CFG.agents}
CODE_TO_SUP = {s.code.upper(): s for s in AGENTS_CFG.supervisors}
SD_TO_AGENT = {a.sd_id: a for a in AGENTS_CFG.agents}

# Agent uchun doimiy tugmalar (matn buyruq o'rniga — foydalanuvchi qarori 2026-07-14)
AGENT_KB = ReplyKeyboardMarkup(
    [["📊 Bugungi natija", "📅 Oylik ball"],
     ["🎁 Happy Toy", "💳 Qarzlar", "↩️ Vazvratlar"],
     ["❓ Yordam"]],
    resize_keyboard=True,
)

# Admin uchun tugmalar (ulanganlarni ko'rish/uzish)
ADMIN_KB = ReplyKeyboardMarkup(
    [["👥 Ulanganlar"]],
    resize_keyboard=True,
)


def _period(dc) -> str:
    """Karta tagidagi izoh uchun davr: '1–14 iyul'."""
    from .data import MONTHS_UZ
    t = dc.today
    return f"1–{t.day} {MONTHS_UZ[t.month].lower()}"


def _now() -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Asia/Tashkent")).isoformat(timespec="seconds")


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
            reply_markup=AGENT_KB)
        return
    await update.message.reply_text(WELCOME, parse_mode=ParseMode.HTML)


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Ulangan bo'lsa — TUGMA bosilganini tekshiradi. Ulanmagan bo'lsa — matn KOD deb
    olinadi va ADMIN TASDIG'IGA yuboriladi (eng xavfsiz — foydalanuvchi qarori 2026-07-14)."""
    chat_id = update.effective_chat.id
    raw = (update.message.text or "").strip()

    # Admin tugmasi (ulanganlarni ko'rish/uzish)
    if chat_id in ADMIN_IDS and raw == "👥 Ulanganlar":
        return await cmd_admin_connected(update, ctx)

    with get_conn() as conn:
        binding = storage.binding_by_chat(conn, chat_id)

    # Allaqachon ulangan — FAQAT tugmalar ishlaydi (matn yozsa — tugmalarni eslatadi)
    if binding:
        handler = BUTTON_HANDLERS.get(raw)
        if handler:
            return await handler(update, ctx)
        await update.message.reply_text(
            "⌨️ Iltimos, pastdagi tugmalardan foydalaning 👇", reply_markup=AGENT_KB)
        return

    # Ulanmagan — matn kod deb olinadi
    code = raw.upper()
    agent = CODE_TO_AGENT.get(code)
    sup = CODE_TO_SUP.get(code)
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
    else:
        return await update.message.reply_text(
            "❌ Kod noto'g'ri. Iltimos, kodingizni tekshirib qayta yuboring.")

    # Admin tasdig'i uchun so'rov
    user = update.effective_user
    who = f"@{user.username}" if (user and user.username) else (
        (user.full_name if user else None) or str(chat_id))
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


async def cmd_bugun(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    b = await _get_binding(update.effective_chat.id)
    if not b or b["role"] != "agent":
        return await update.message.reply_text("Avval kodingizni yuboring: /start")
    dc = DayContext()
    p = _period(dc)
    cards = dc.evening_cards(b["sd_id"])
    await update.message.reply_photo(render_ball_card(cards[0]),
                                     caption=f"📊 Bugungi natija + oylik ball · {p}")
    await update.message.reply_photo(render_plan_card(cards[1]),
                                     caption=f"📅 Oylik savdo reja · {p}")
    await update.message.reply_photo(render_toy_card(cards[2]),
                                     caption=f"🎁 Happy Toy · {p}")


async def cmd_toy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    b = await _get_binding(update.effective_chat.id)
    if not b or b["role"] != "agent":
        return await update.message.reply_text("Avval kodingizni yuboring: /start")
    dc = DayContext()
    await update.message.reply_photo(render_toy_card(dc.evening_cards(b["sd_id"])[2]),
                                     caption=f"🎁 Happy Toy · {_period(dc)}")


async def cmd_qarz(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    b = await _get_binding(update.effective_chat.id)
    if not b or b["role"] != "agent":
        return await update.message.reply_text("Avval kodingizni yuboring: /start")
    dc = DayContext()
    await update.message.reply_photo(render_debt_card(dc.morning_card(b["sd_id"])),
                                     caption="💳 Qarzdorliklar · bugungi holat (50 ming so'mdan yuqori do'konlar)")


async def cmd_vazvrat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    b = await _get_binding(update.effective_chat.id)
    if not b or b["role"] != "agent":
        return await update.message.reply_text("Avval kodingizni yuboring: /start")
    dc = DayContext()
    await update.message.reply_photo(render_returns_card(dc.morning_card(b["sd_id"])),
                                     caption=f"↩️ Vazvratlar · kunlik (kecha) + oylik jami ({_period(dc)})")


async def cmd_oy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    b = await _get_binding(update.effective_chat.id)
    if not b or b["role"] != "agent":
        return await update.message.reply_text("Avval kodingizni yuboring: /start")
    dc = DayContext()
    s = dc.snap[b["sd_id"]]
    # Matnli taqvim (ballar kun bo'yicha)
    lines = [f"📅 <b>{s.today.strftime('%B')} — ball taqvimi</b>\n"]
    for d in sorted(s.balls.keys()):
        bar = "🔥" if s.balls[d] == 4 else "✅" if s.balls[d] == 3 else \
              "🟢" if s.balls[d] == 2 else "🟡" if s.balls[d] == 1 else "⚪️"
        lines.append(f"{d.day:2d}-kun: {bar} {s.balls[d]} ball")
    lines.append(f"\n<b>Jami: {s.month_ball} ball</b>")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_yordam(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
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
        reply_markup=AGENT_KB,
    )


async def _send_self_report(app, chat_id: int, binding):
    if binding["role"] == "agent":
        dc = DayContext()
        cards = dc.evening_cards(binding["sd_id"])
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
    agent = CODE_TO_AGENT.get(code)
    sup = CODE_TO_SUP.get(code)
    if agent:
        role, sd_id, name = "agent", agent.sd_id, agent.name
    elif sup:
        role, sd_id, name = "supervisor", None, sup.name
    else:
        return await q.edit_message_text("❌ Kod topilmadi.")

    if decision == "no":
        await q.edit_message_text(f"❌ Rad etildi: {name} ({code})")
        try:
            await ctx.application.bot.send_message(
                target, "❌ Ulanish so'rovingiz rad etildi. Administrator bilan bog'laning.")
        except TelegramError:
            pass
        return

    # Tasdiqlandi — ulaymiz
    with get_conn() as conn:
        old_chat = storage.bind_code(conn, code, target, role, sd_id, _now())
    await q.edit_message_text(f"✅ Tasdiqlandi: {name} ({code}) → chat {target}")
    try:
        if role == "agent":
            await ctx.application.bot.send_message(
                target, f"✅ Ulandingiz!\n👤 {name}\n"
                        f"Har kuni 10:00 (qarz/vazvrat) va 20:00 (natija) da hisobot keladi.\n"
                        f"Quyidagi tugmalardan foydalaning 👇", reply_markup=AGENT_KB)
        else:
            await ctx.application.bot.send_message(target, f"✅ Ulandingiz!\n👤 {name}")
    except TelegramError:
        pass
    if old_chat and old_chat != target:
        try:
            await ctx.application.bot.send_message(
                old_chat, "⚠️ Kodingiz boshqa qurilmaga ulandi (admin tasdig'i bilan).")
        except TelegramError:
            pass


async def cmd_admin_connected(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin: ulangan agentlar ro'yxati, har biriga 'Uzish' tugmasi."""
    if update.effective_chat.id not in ADMIN_IDS:
        return
    with get_conn() as conn:
        rows = storage.list_bindings(conn)
    agents = [r for r in rows if r["role"] == "agent"]
    if not agents:
        return await update.message.reply_text("Hozircha ulangan agent yo'q.", reply_markup=ADMIN_KB)
    await update.message.reply_text(f"👥 Ulangan agentlar: {len(agents)} ta")
    for r in agents:
        ag = SD_TO_AGENT.get(r["sd_id"])
        name = ag.short if ag else r["code"]
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"❌ {name}ni uzish", callback_data=f"nzunbind:{r['code']}")]])
        await update.message.reply_text(f"👤 {name} — {r['code']}", reply_markup=kb)


async def on_unbind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin 'Uzish' bosdi — agent ulanishini o'chiradi."""
    q = update.callback_query
    await q.answer()
    if q.message.chat.id not in ADMIN_IDS:
        return
    code = q.data.split(":", 1)[1]
    with get_conn() as conn:
        old_chat = storage.unbind(conn, code)
    agent = CODE_TO_AGENT.get(code)
    name = agent.short if agent else code
    await q.edit_message_text(f"🔌 Uzildi: {name} ({code})")
    if old_chat:
        try:
            await ctx.application.bot.send_message(
                old_chat, "🔌 Siz botdan uzildingiz. Qayta ulanish uchun kodingizni yuboring.")
        except TelegramError:
            pass


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
    "📅 Oylik ball": cmd_oy,
    "🎁 Happy Toy": cmd_toy,
    "💳 Qarzlar": cmd_qarz,
    "↩️ Vazvratlar": cmd_vazvrat,
    "❓ Yordam": cmd_yordam,
}
