"""
bot.py — Telegram bot: menyular, tugmalar, handlerlar.
"""

import asyncio
import logging
from datetime import date, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import reports
from config import ADMIN_IDS, ALLOWED_IDS, TELEGRAM_BOT_TOKEN
from db import get_conn, init_db
from sync import run_sync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Ruxsat tekshiruvi
# ------------------------------------------------------------------

def is_allowed(user_id: int) -> bool:
    return user_id in ALLOWED_IDS


async def deny(update: Update) -> None:
    await update.effective_message.reply_text("⛔ Sizda ruxsat yo'q.")


# ------------------------------------------------------------------
# Asosiy menyu
# ------------------------------------------------------------------

MAIN_MENU_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("💰 Kunlik savdo", callback_data="menu:daily_sales"),
     InlineKeyboardButton("📈 Oylik savdo", callback_data="menu:monthly_sales")],
    [InlineKeyboardButton("🏪 Agentlar qarzi", callback_data="menu:agents_debt"),
     InlineKeyboardButton("👤 Agentni ochish", callback_data="menu:agent_detail")],
    [InlineKeyboardButton("🚶 Vizitlar", callback_data="menu:visits"),
     InlineKeyboardButton("🏆 TOP tovarlar", callback_data="menu:top_products")],
    [InlineKeyboardButton("📦 Sklad ostatka", callback_data="menu:stock"),
     InlineKeyboardButton("💀 O'lik do'konlar", callback_data="menu:dead_outlets")],
    [InlineKeyboardButton("🔄 Hozir yangilash", callback_data="menu:sync_now")],
])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update.effective_user.id):
        await deny(update)
        return
    await update.message.reply_text(
        "👋 <b>SalesDoc monitoring botiga xush kelibsiz!</b>\n\nQuyidagi bo'limlardan birini tanlang:",
        parse_mode=ParseMode.HTML,
        reply_markup=MAIN_MENU_KEYBOARD,
    )


async def show_main_menu(update: Update, text: str = "Bosh menyu:") -> None:
    await update.effective_message.edit_text(
        text, parse_mode=ParseMode.HTML, reply_markup=MAIN_MENU_KEYBOARD
    )


# ------------------------------------------------------------------
# Sana tanlash tugmalari yordamchisi
# ------------------------------------------------------------------

def date_picker_keyboard(prefix: str, back: str = "back:main") -> InlineKeyboardMarkup:
    today = date.today()
    yesterday = today - timedelta(days=1)
    first_this_month = today.replace(day=1)
    first_last_month = (first_this_month - timedelta(days=1)).replace(day=1)

    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Bugun", callback_data=f"{prefix}:{today.isoformat()}"),
         InlineKeyboardButton("📅 Kecha", callback_data=f"{prefix}:{yesterday.isoformat()}")],
        [InlineKeyboardButton("🗓 Bu oy", callback_data=f"{prefix}:month:{today.year}:{today.month}"),
         InlineKeyboardButton("🗓 O'tgan oy", callback_data=f"{prefix}:month:{first_last_month.year}:{first_last_month.month}")],
        [InlineKeyboardButton("◀️ Orqaga", callback_data=back)],
    ])


def month_picker_keyboard(prefix: str) -> InlineKeyboardMarkup:
    today = date.today()
    months = []
    for i in range(6):
        d = (today.replace(day=1) - timedelta(days=30 * i))
        months.append(InlineKeyboardButton(
            f"{d.year}-{d.month:02d}",
            callback_data=f"{prefix}:{d.year}:{d.month}"
        ))
    rows = [months[i:i+3] for i in range(0, len(months), 3)]
    rows.append([InlineKeyboardButton("◀️ Orqaga", callback_data="back:main")])
    return InlineKeyboardMarkup(rows)


def dead_picker_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("14 kun", callback_data="dead:14"),
         InlineKeyboardButton("30 kun", callback_data="dead:30"),
         InlineKeyboardButton("7 kun", callback_data="dead:7")],
        [InlineKeyboardButton("◀️ Orqaga", callback_data="back:main")],
    ])


# ------------------------------------------------------------------
# Callback handler
# ------------------------------------------------------------------

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if not is_allowed(query.from_user.id):
        await query.message.reply_text("⛔ Sizda ruxsat yo'q.")
        return

    data = query.data

    # --- Orqaga ---
    if data == "back:main":
        await show_main_menu(update, "Bosh menyu:")
        return

    # --- Menyu tanlovilar ---
    if data == "menu:daily_sales":
        await query.message.edit_text(
            "💰 <b>Kunlik savdo</b>\nQaysi kun uchun?",
            parse_mode=ParseMode.HTML,
            reply_markup=date_picker_keyboard("dsales"),
        )
        return

    if data == "menu:monthly_sales":
        await query.message.edit_text(
            "📈 <b>Oylik savdo</b>\nQaysi oy uchun?",
            parse_mode=ParseMode.HTML,
            reply_markup=month_picker_keyboard("msales"),
        )
        return

    if data == "menu:agents_debt":
        text = reports.agents_debt_report()
        await query.message.edit_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Orqaga", callback_data="back:main")]]),
        )
        return

    if data == "menu:agent_detail":
        await show_agent_list(update, "👤 <b>Agentni tanlang:</b>", "adetail")
        return

    if data == "menu:visits":
        await query.message.edit_text(
            "🚶 <b>Vizitlar</b>\nQaysi kun?",
            parse_mode=ParseMode.HTML,
            reply_markup=date_picker_keyboard("visits"),
        )
        return

    if data == "menu:top_products":
        await query.message.edit_text(
            "🏆 <b>TOP tovarlar</b>\nQaysi davr?",
            parse_mode=ParseMode.HTML,
            reply_markup=date_picker_keyboard("topprods"),
        )
        return

    if data == "menu:stock":
        text = reports.stock_report()
        await query.message.edit_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Orqaga", callback_data="back:main")]]),
        )
        return

    if data == "menu:dead_outlets":
        await query.message.edit_text(
            "💀 <b>O'lik do'konlar</b>\nNecha kundan beri buyurtma yo'qlarni ko'rmoqchisiz?",
            parse_mode=ParseMode.HTML,
            reply_markup=dead_picker_keyboard(),
        )
        return

    if data == "menu:sync_now":
        await query.message.edit_text("🔄 <b>Yangilanmoqda...</b> Bir oz kuting.", parse_mode=ParseMode.HTML)
        result = await run_sync("manual")
        if result == "ok":
            txt = "✅ <b>Ma'lumotlar yangilandi!</b>"
        else:
            txt = f"⚠️ <b>Xato yuz berdi:</b>\n<code>{result[:300]}</code>"
        await query.message.edit_text(
            txt, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Orqaga", callback_data="back:main")]]),
        )
        return

    # --- Kunlik savdo sana tanlovi ---
    if data.startswith("dsales:"):
        parts = data.split(":")
        if parts[1] == "month":
            year, month = int(parts[2]), int(parts[3])
            d_from = f"{year:04d}-{month:02d}-01"
            if month == 12:
                d_to = f"{year + 1:04d}-01-01"
            else:
                d_to = f"{year:04d}-{month + 1:02d}-01"
            # Oylik uchun har bir kun savdosi
            text = reports.daily_sales_report(d_from)
        else:
            text = reports.daily_sales_report(parts[1])
        await query.message.edit_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Orqaga", callback_data="back:main")]]),
        )
        return

    # --- Oylik savdo ---
    if data.startswith("msales:"):
        parts = data.split(":")
        year, month = int(parts[1]), int(parts[2])
        text = reports.monthly_sales_report(year, month)
        await query.message.edit_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Orqaga", callback_data="back:main")]]),
        )
        return

    # --- Agent tanlovi (qarz) ---
    if data.startswith("adetail:"):
        agent_id = data.split(":", 1)[1]
        text = reports.agent_debt_detail(agent_id)
        await query.message.edit_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Orqaga", callback_data="back:main")]]),
        )
        return

    # --- Vizitlar ---
    if data.startswith("visits:"):
        parts = data.split(":")
        if parts[1] == "month":
            day = f"{parts[2]}-{parts[3]}-01"
        else:
            day = parts[1]
        text = reports.visits_report(day)
        await query.message.edit_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Orqaga", callback_data="back:main")]]),
        )
        return

    # --- TOP tovarlar ---
    if data.startswith("topprods:"):
        parts = data.split(":")
        today = date.today()
        if parts[1] == "month":
            year, month = int(parts[2]), int(parts[3])
            d_from = f"{year:04d}-{month:02d}-01"
            if month == 12:
                d_to = f"{year + 1:04d}-01-01"
            else:
                d_to = f"{year:04d}-{month + 1:02d}-01"
        else:
            d_from = d_to = parts[1]
        text = reports.top_products_report(d_from, d_to)
        await query.message.edit_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Orqaga", callback_data="back:main")]]),
        )
        return

    # --- O'lik do'konlar ---
    if data.startswith("dead:"):
        days = int(data.split(":")[1])
        text = reports.dead_outlets_report(dead_days=days)
        await query.message.edit_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Orqaga", callback_data="back:main")]]),
        )
        return


async def show_agent_list(update: Update, title: str, prefix: str) -> None:
    with get_conn() as conn:
        agents = conn.execute("SELECT sd_id, name FROM agents WHERE active='Y' ORDER BY name").fetchall()

    if not agents:
        await update.effective_message.edit_text(
            "Agent ma'lumoti yuklanmagan. Avval 🔄 Hozir yangilash tugmasini bosing.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Orqaga", callback_data="back:main")]]),
        )
        return

    buttons = [
        [InlineKeyboardButton(a["name"], callback_data=f"{prefix}:{a['sd_id']}")]
        for a in agents
    ]
    buttons.append([InlineKeyboardButton("◀️ Orqaga", callback_data="back:main")])
    await update.effective_message.edit_text(
        title, parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


# ------------------------------------------------------------------
# Noma'lum xabar
# ------------------------------------------------------------------

async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update.effective_user.id):
        await deny(update)
        return
    await update.message.reply_text(
        "Menyudan foydalaning 👇",
        reply_markup=MAIN_MENU_KEYBOARD,
    )


# ------------------------------------------------------------------
# Digest yuborish (scheduler ishlatadi)
# ------------------------------------------------------------------

async def send_daily_digest(app: Application) -> None:
    text = reports.daily_digest()
    for admin_id in ADMIN_IDS:
        try:
            await app.bot.send_message(admin_id, text, parse_mode=ParseMode.HTML)
        except Exception as exc:
            logger.error("Digest yuborishda xato (user %s): %s", admin_id, exc)


async def notify_admins(app: Application, text: str) -> None:
    for admin_id in ADMIN_IDS:
        try:
            await app.bot.send_message(admin_id, text, parse_mode=ParseMode.HTML)
        except Exception as exc:
            logger.error("Admin xabarnomasi xato (user %s): %s", admin_id, exc)


# ------------------------------------------------------------------
# Ishga tushirish
# ------------------------------------------------------------------

def main() -> None:
    init_db()
    logger.info("Bot ishga tushmoqda...")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message))

    # Scheduler shu yerdan ulanadi
    from scheduler import setup_scheduler
    setup_scheduler(app)

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
