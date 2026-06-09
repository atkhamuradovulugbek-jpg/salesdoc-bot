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
    [InlineKeyboardButton("💸 Qarzdorliklar jami", callback_data="menu:agents_debt"),
     InlineKeyboardButton("👤 Qarzdorlik Agentlar", callback_data="menu:agent_detail")],
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
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "👋 <b>SalesDoc Monitoring Bot</b>\n"
        "<i>Shiribom uchun ichki tizim</i>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📊 Bo'limni tanlang 👇",
        parse_mode=ParseMode.HTML,
        reply_markup=MAIN_MENU_KEYBOARD,
    )


async def show_main_menu(update: Update, text: str = "Bosh menyu:") -> None:
    await update.effective_message.edit_text(
        text, parse_mode=ParseMode.HTML, reply_markup=MAIN_MENU_KEYBOARD
    )


MAX_TG = 4000  # xavfsiz chegara (asl: 4096)


def _month_range(year: int, month: int) -> tuple[str, str]:
    """(YYYY-MM-01, YYYY-MM-DD) — oyning birinchi va oxirgi kuni."""
    d_from = f"{year:04d}-{month:02d}-01"
    if month == 12:
        next_first = date(year + 1, 1, 1)
    else:
        next_first = date(year, month + 1, 1)
    d_to = (next_first - timedelta(days=1)).isoformat()
    return d_from, d_to


def _truncate(text: str) -> str:
    """Telegram chegarasidan oshsa, oxiriga ogohlantirish qo'shadi."""
    if len(text) <= MAX_TG:
        return text
    cut = text[:MAX_TG - 100].rsplit("\n", 1)[0]
    return cut + "\n\n<i>...xabar uzun bo'lgani uchun qisqartirildi.</i>"


async def send_report(query, text: str, back_to: str = "back:main") -> None:
    """Hisobotni xavfsiz uzunlikda yuboradi."""
    safe = _truncate(text)
    await query.message.edit_text(
        safe, parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Orqaga", callback_data=back_to)]]),
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
        [InlineKeyboardButton("📝 Boshqa sana / davr", callback_data=f"custom:{prefix}")],
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
        await send_report(query, reports.agents_debt_report())
        return

    if data == "menu:agent_detail":
        await show_agent_list(update, "👤 <b>Qarzdor agentni tanlang:</b>", "adetail", debt_only=True)
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
        messages = reports.stock_report()
        # Birinchi xabarni edit qilamiz
        await query.message.edit_text(
            _truncate(messages[0]), parse_mode=ParseMode.HTML,
        )
        # Qolganlarni yangi xabar qilib yuboramiz
        for msg in messages[1:-1]:
            await query.message.reply_text(_truncate(msg), parse_mode=ParseMode.HTML)
        # Oxirgi xabar bilan "Orqaga" tugmasi
        if len(messages) > 1:
            await query.message.reply_text(
                _truncate(messages[-1]), parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Bosh menyu", callback_data="back:main")]]),
            )
        else:
            await query.message.edit_reply_markup(
                InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Orqaga", callback_data="back:main")]])
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
        msg = await query.message.edit_text(
            "🔄 <b>Yangilanmoqda...</b>\n\n📡 Boshlanmoqda...",
            parse_mode=ParseMode.HTML,
        )
        import time
        last_edit = [time.time()]

        async def progress_cb(text: str):
            # Telegram'ni "edit flood" qilmaslik uchun har 1 sek dan ortiq tezda edit qilmaymiz
            now = time.time()
            if now - last_edit[0] < 1.0:
                return
            last_edit[0] = now
            try:
                await msg.edit_text(
                    f"🔄 <b>Yangilanmoqda...</b>\n\n{text}",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass

        result = await run_sync("manual", progress_cb=progress_cb)
        if result == "ok":
            txt = "✅ <b>Ma'lumotlar muvaffaqiyatli yangilandi!</b>"
        else:
            txt = f"⚠️ <b>Xato yuz berdi:</b>\n<code>{result[:300]}</code>"
        await msg.edit_text(
            txt, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Orqaga", callback_data="back:main")]]),
        )
        return

    # --- Custom sana so'rovi (text input bilan) ---
    if data.startswith("custom:"):
        prefix = data.split(":", 1)[1]
        context.user_data["waiting_for"] = prefix
        await query.message.edit_text(
            "📝 <b>Sana yoki davrni yozing:</b>\n\n"
            "Bitta kun: <code>05.06.2026</code>\n"
            "Davr: <code>01.06.2026 - 05.06.2026</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Orqaga", callback_data="back:main")]]),
        )
        return

    # --- Kunlik savdo sana tanlovi ---
    if data.startswith("dsales:"):
        parts = data.split(":")
        if parts[1] == "month":
            year, month = int(parts[2]), int(parts[3])
            d_from, d_to = _month_range(year, month)
            text = reports.daily_sales_report(d_from, d_to)
        else:
            text = reports.daily_sales_report(parts[1])
        await send_report(query, text)
        return

    # --- Oylik savdo ---
    if data.startswith("msales:"):
        parts = data.split(":")
        year, month = int(parts[1]), int(parts[2])
        await send_report(query, reports.monthly_sales_report(year, month))
        return

    # --- Agent tanlovi (qarz) ---
    if data.startswith("adetail:"):
        agent_id = data.split(":", 1)[1]
        await send_report(query, reports.agent_debt_detail(agent_id))
        return

    # --- Agentning o'lik do'konlari ---
    if data.startswith("deadag:"):
        parts = data.split(":")
        days = int(parts[1])
        agent_id = parts[2]
        await send_report(query, reports.dead_outlets_by_agent(agent_id, dead_days=days))
        return

    # --- Vizitlar ---
    if data.startswith("visits:"):
        parts = data.split(":")
        if parts[1] == "month":
            year, month = int(parts[2]), int(parts[3])
            d_from, d_to = _month_range(year, month)
            await send_report(query, reports.visits_report(d_from, d_to))
        else:
            await send_report(query, reports.visits_report(parts[1]))
        return

    # --- TOP tovarlar ---
    if data.startswith("topprods:"):
        parts = data.split(":")
        if parts[1] == "month":
            year, month = int(parts[2]), int(parts[3])
            d_from, d_to = _month_range(year, month)
        else:
            d_from = d_to = parts[1]
        await send_report(query, reports.top_products_report(d_from, d_to))
        return

    # --- O'lik do'konlar (umumiy hisobot) ---
    if data.startswith("dead:"):
        days = int(data.split(":")[1])
        text = reports.dead_outlets_report(dead_days=days)
        # Pastida agentlarni tanlash uchun tugmalar qo'shamiz
        with get_conn() as conn:
            agents_list = conn.execute("SELECT sd_id, name FROM agents WHERE active='Y' ORDER BY name").fetchall()
        buttons = [
            [InlineKeyboardButton(f"👤 {a['name']}", callback_data=f"deadag:{days}:{a['sd_id']}")]
            for a in agents_list
        ]
        buttons.append([InlineKeyboardButton("◀️ Orqaga", callback_data="back:main")])
        await query.message.edit_text(
            _truncate(text), parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return


async def show_agent_list(update: Update, title: str, prefix: str, debt_only: bool = False) -> None:
    with get_conn() as conn:
        if debt_only:
            # Qarzdor mijozlari bor agentlar (faol bo'lmaganlar ham)
            agents = conn.execute("""
                SELECT DISTINCT a.sd_id, a.name
                FROM agents a
                JOIN clients c ON c.primary_agent_sd_id = a.sd_id
                JOIN balances b ON b.client_sd_id = c.sd_id
                WHERE b.balance < 0
                ORDER BY a.name
            """).fetchall()
        else:
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
# Sana parseri (custom input uchun)
# ------------------------------------------------------------------

import re
from datetime import datetime as _dt


def parse_date_input(text: str) -> tuple[str | None, str | None]:
    """
    Foydalanuvchi yozgan sana(lar)ni parselash:
    - "05.06.2026" → (2026-06-05, 2026-06-05)
    - "01.06.2026 - 05.06.2026" → (2026-06-01, 2026-06-05)
    Formatlar: DD.MM.YYYY, DD-MM-YYYY, DD/MM/YYYY, YYYY-MM-DD
    """
    text = text.strip()
    parts = re.split(r"\s*[-—–]\s*", text, maxsplit=1)

    def _parse_one(s: str) -> str | None:
        s = s.strip()
        for fmt in ("%d.%m.%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y.%m.%d"):
            try:
                return _dt.strptime(s, fmt).date().isoformat()
            except ValueError:
                continue
        return None

    if len(parts) == 1:
        d = _parse_one(parts[0])
        return (d, d) if d else (None, None)
    d_from = _parse_one(parts[0])
    d_to = _parse_one(parts[1])
    if d_from and d_to and d_from > d_to:
        d_from, d_to = d_to, d_from
    return (d_from, d_to)


# ------------------------------------------------------------------
# Noma'lum xabar
# ------------------------------------------------------------------

async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update.effective_user.id):
        await deny(update)
        return

    waiting = context.user_data.get("waiting_for")
    if waiting:
        # Foydalanuvchi sana kiritdi
        d_from, d_to = parse_date_input(update.message.text)
        if not d_from:
            await update.message.reply_text(
                "⚠️ Sana noto'g'ri. Misol: <code>05.06.2026</code> yoki <code>01.06.2026 - 05.06.2026</code>",
                parse_mode=ParseMode.HTML,
            )
            return
        context.user_data["waiting_for"] = None

        if waiting == "dsales":
            text = reports.daily_sales_report(d_from, d_to)
        elif waiting == "visits":
            text = reports.visits_report(d_from, d_to)
        elif waiting == "topprods":
            text = reports.top_products_report(d_from, d_to)
        else:
            text = "Noma'lum hisobot turi."

        safe = _truncate(text)
        await update.message.reply_text(
            safe, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Bosh menyu", callback_data="back:main")]]),
        )
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

async def post_init(app: Application) -> None:
    from scheduler import setup_scheduler
    setup_scheduler(app)


def main() -> None:
    init_db()
    logger.info("Bot ishga tushmoqda...")

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message))

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
