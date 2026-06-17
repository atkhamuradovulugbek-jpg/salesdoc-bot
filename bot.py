"""
bot.py — Telegram bot: menyular, tugmalar, handlerlar.
"""

import asyncio
import logging
from datetime import date, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import NetworkError, RetryAfter, TimedOut
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import reports
try:
    import image_reports
    _IMAGE_REPORTS_OK = True
except Exception as _img_err:
    _IMAGE_REPORTS_OK = False
    image_reports = None  # type: ignore
    logging.getLogger(__name__).error("image_reports yuklanmadi: %s", _img_err)
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
     InlineKeyboardButton("🔴 Tez tugaydiganlar", callback_data="menu:low_stock")],
    [InlineKeyboardButton("💀 O'lik do'konlar", callback_data="menu:dead_outlets"),
     InlineKeyboardButton("🕵️ Agent nazorati", callback_data="menu:agent_monitor")],
    [InlineKeyboardButton("📊 Agent planlari", callback_data="menu:plans"),
     InlineKeyboardButton("📤 Guruh sozlash", callback_data="menu:groupset")],
    [InlineKeyboardButton("🔄 Tez yangilash", callback_data="menu:sync_now"),
     InlineKeyboardButton("📥 To'liq yangilash", callback_data="menu:sync_full")],
])


async def setgroup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Guruh ichida ishlatilsa — shu guruh ID'sini saqlaydi."""
    if not is_allowed(update.effective_user.id):
        await deny(update)
        return
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text(
            "⚠️ Bu buyruq faqat <b>guruh</b> ichida ishlaydi.\n\n"
            "1. Avval botni guruhga qo'shing\n"
            "2. Guruh ichida <code>/setgroup</code> yozing",
            parse_mode=ParseMode.HTML,
        )
        return
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("report_chat_id", str(chat.id)))
    await update.message.reply_text(
        f"✅ <b>Bu guruh saqlandi!</b>\n\n"
        f"Guruh: <code>{chat.title}</code>\n"
        f"ID: <code>{chat.id}</code>\n\n"
        f"Endi har kuni 20:00 da bot bu guruhga har agent uchun hisobot yuboradi.",
        parse_mode=ParseMode.HTML,
    )


async def cleargroup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update.effective_user.id):
        await deny(update)
        return
    with get_conn() as conn:
        conn.execute("DELETE FROM settings WHERE key='report_chat_id'")
    await update.message.reply_text("✅ Guruh sozlamasi o'chirildi. Endi hisobot yuborilmaydi.")


async def version_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    img_status = "✅ RASM rejimi — Pillow ishlaydi" if _IMAGE_REPORTS_OK else "❌ MATN rejimi — Pillow yuklanmagan"
    await update.message.reply_text(
        f"🤖 <b>Bot versiyasi:</b> rasm-kartochkalar\n{img_status}",
        parse_mode=ParseMode.HTML,
    )


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

    if data == "menu:agent_monitor":
        await query.message.edit_text("🕵️ Agent holati tekshirilmoqda...")
        from agent_monitor import run_snapshot
        try:
            text = await run_snapshot()
        except Exception as exc:
            logger.exception("Agent nazorati (qo'lda) xatosi: %s", exc)
            text = f"⚠️ Xatolik:\n<code>{str(exc)[:300]}</code>"
        await send_report(query, text, back_to="back:main")
        return

    if data == "menu:low_stock":
        messages = reports.low_stock_report(max_days=5)
        await query.message.edit_text(
            _truncate(messages[0]), parse_mode=ParseMode.HTML,
        )
        for msg in messages[1:-1]:
            await query.message.reply_text(_truncate(msg), parse_mode=ParseMode.HTML)
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

    # --- Agent planlari ---
    if data == "menu:plans":
        with get_conn() as conn:
            agents = conn.execute("""
                SELECT a.sd_id, a.name,
                       COALESCE(p.sales_plan, 0) AS sp,
                       COALESCE(p.visit_plan, 0) AS vp
                FROM agents a
                LEFT JOIN agent_plans p ON p.agent_sd_id = a.sd_id
                WHERE a.active='Y'
                ORDER BY a.name
            """).fetchall()
        buttons = []
        for a in agents:
            mark = "✏️" if a["sp"] > 0 else "📌"  # ✏️ = qo'lda o'zgartirilgan, 📌 = default
            buttons.append([InlineKeyboardButton(
                f"{mark} {a['name']}",
                callback_data=f"planedit:{a['sd_id']}"
            )])
        buttons.append([InlineKeyboardButton("◀️ Orqaga", callback_data="back:main")])
        await query.message.edit_text(
            "📊 <b>Agent planlari</b>\n\n"
            f"<b>Standart planlar (avtomatik):</b>\n"
            f"🏙️ Shahar: <b>{reports.DEFAULT_CITY_SALES_PLAN:,}</b> so'm\n".replace(",", " ") +
            f"🏘️ Viloyat: <b>{reports.DEFAULT_REGION_SALES_PLAN:,}</b> so'm\n".replace(",", " ") +
            f"🚶 Vizit (hamma): <b>{reports.DEFAULT_VISIT_PLAN}</b> ta\n\n"
            "📌 = standart plan ishlatiladi\n"
            "✏️ = qo'lda o'zgartirilgan\n\n"
            "Bitta agentni boshqacha qilmoqchi bo'lsangiz, tanlang:",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    if data.startswith("planedit:"):
        agent_id = data.split(":", 1)[1]
        with get_conn() as conn:
            a = conn.execute("SELECT name FROM agents WHERE sd_id=?", (agent_id,)).fetchone()
            p = conn.execute("SELECT sales_plan, visit_plan FROM agent_plans WHERE agent_sd_id=?", (agent_id,)).fetchone()
        sp = float(p["sales_plan"]) if p else 0
        vp = int(p["visit_plan"]) if p else 0
        # Defaultlarni ko'rsatamiz agar maxsus yo'q bo'lsa
        if sp <= 0:
            kind = reports.classify_agent(a["name"])
            if kind == "city":
                sp_display = reports.DEFAULT_CITY_SALES_PLAN
            elif kind == "region":
                sp_display = reports.DEFAULT_REGION_SALES_PLAN
            else:
                sp_display = 0
            sp_note = "  <i>(standart)</i>"
        else:
            sp_display = sp
            sp_note = "  <i>(qo'lda o'rnatilgan)</i>"
        vp_display = vp if vp > 0 else reports.DEFAULT_VISIT_PLAN
        vp_note = "  <i>(qo'lda)</i>" if vp > 0 else "  <i>(standart)</i>"

        await query.message.edit_text(
            f"👤 <b>{a['name']}</b>\n\n"
            f"💵 Oylik savdo: <b>{int(sp_display):,} so'm</b>{sp_note}\n".replace(",", " ") +
            f"🚶 Oylik vizit: <b>{vp_display}</b> ta{vp_note}\n\n"
            "Qaysisini o'zgartirasiz?",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💵 Savdo plani", callback_data=f"setsales:{agent_id}")],
                [InlineKeyboardButton("🚶 Vizit plani", callback_data=f"setvisit:{agent_id}")],
                [InlineKeyboardButton("◀️ Orqaga", callback_data="menu:plans")],
            ]),
        )
        return

    if data.startswith("setsales:"):
        agent_id = data.split(":", 1)[1]
        context.user_data["waiting_for"] = f"sales_plan:{agent_id}"
        await query.message.edit_text(
            "💵 <b>Oylik savdo planini yozing:</b>\n\n"
            "Misol: <code>50000000</code> (50 mln so'm uchun)\n"
            "yoki: <code>50 000 000</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Bekor qilish", callback_data=f"planedit:{agent_id}")]]),
        )
        return

    if data.startswith("setvisit:"):
        agent_id = data.split(":", 1)[1]
        context.user_data["waiting_for"] = f"visit_plan:{agent_id}"
        await query.message.edit_text(
            "🚶 <b>Oylik vizit planini yozing:</b>\n\n"
            "Misol: <code>750</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Bekor qilish", callback_data=f"planedit:{agent_id}")]]),
        )
        return

    # --- Guruh sozlash ---
    if data == "menu:groupset":
        with get_conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key='report_chat_id'").fetchone()
        current = row["value"] if row else "o'rnatilmagan"
        is_set = bool(row and row["value"])
        buttons = []
        if is_set:
            buttons.append([InlineKeyboardButton("🚀 Hozir sinash (kartochkalar)", callback_data="testsend")])
            buttons.append([InlineKeyboardButton("🔥 Ball sinash (jadval)", callback_data="testball")])
        buttons.append([InlineKeyboardButton("◀️ Orqaga", callback_data="back:main")])
        await query.message.edit_text(
            "📤 <b>Guruh sozlash</b>\n\n"
            "Bot har kuni 20:00 da har faol agent uchun alohida hisobot yuboradi.\n"
            "Hisobotlar shahar va viloyat bo'yicha ajratiladi.\n\n"
            f"<b>Hozirgi guruh ID:</b> <code>{current}</code>\n\n"
            "<b>Qanday sozlash:</b>\n"
            "1️⃣ Botni guruhga qo'shing (admin sifatida)\n"
            "2️⃣ Guruh ichida yozing: <code>/setgroup</code>\n"
            "3️⃣ Bot saqlaydi va 20:00 da yuboradi\n\n"
            "<i>O'chirish uchun guruhda:</i> <code>/cleargroup</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    # --- Hozir sinash (qo'lda guruhga yuborish) ---
    if data == "testsend":
        img_status = "🖼 <b>RASM</b> rejimi (Pillow OK)" if _IMAGE_REPORTS_OK else "📝 <b>MATN</b> rejimi (Pillow yo'q!)"
        await query.message.edit_text(
            f"🚀 <b>Hozir guruhga yuborilmoqda...</b>\n{img_status}\n<i>~30 sekund kutilsin.</i>",
            parse_mode=ParseMode.HTML,
        )
        try:
            sent = await send_agent_cards_to_group(context.application)
            mode = "rasm" if _IMAGE_REPORTS_OK else "matn"
            txt = f"✅ <b>Yuborildi!</b>\nJami: <b>{sent}</b> ta agent kartochkasi ({mode} ko'rinishda) + ball jadvallari"
        except Exception as exc:
            txt = f"⚠️ <b>Xato:</b>\n<code>{str(exc)[:300]}</code>"
        await query.message.edit_text(
            txt, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Orqaga", callback_data="back:main")]]),
        )
        return

    # --- Ball jadvali sinash (faqat ball jadvallari RASM) ---
    if data == "testball":
        await query.message.edit_text(
            "🔥 <b>Ball jadvallari (rasm) guruhga yuborilmoqda...</b>",
            parse_mode=ParseMode.HTML,
        )
        try:
            with get_conn() as conn:
                row = conn.execute("SELECT value FROM settings WHERE key='report_chat_id'").fetchone()
            if not row or not row["value"]:
                txt = "⚠️ Guruh sozlanmagan. Avval /setgroup yozing."
            else:
                chat_id = int(row["value"])
                today_str = date.today().strftime("%d.%m.%Y")
                sent_count = 0
                # Shahar
                city_png = image_reports.render_ball_table("city")
                if city_png:
                    await context.application.bot.send_photo(
                        chat_id, photo=city_png,
                        caption=f"🔥 <b>BUGUNGI BALL JADVALI</b>  ·  SHAHAR AGENTLARI  ·  📅 {today_str}",
                        parse_mode=ParseMode.HTML,
                    )
                    sent_count += 1
                    await asyncio.sleep(1.0)
                # Viloyat
                region_png = image_reports.render_ball_table("region")
                if region_png:
                    await context.application.bot.send_photo(
                        chat_id, photo=region_png,
                        caption=f"🔥 <b>BUGUNGI BALL JADVALI</b>  ·  VILOYAT AGENTLARI  ·  📅 {today_str}",
                        parse_mode=ParseMode.HTML,
                    )
                    sent_count += 1
                if sent_count == 0:
                    txt = "⚠️ Ball jadvali yaratish uchun ma'lumot yo'q.\n<i>Avval to'liq yangilash yoki kuting.</i>"
                else:
                    txt = f"✅ <b>{sent_count} ta ball jadvali (rasm) guruhga yuborildi!</b>"
        except Exception as exc:
            txt = f"⚠️ <b>Xato:</b>\n<code>{str(exc)[:300]}</code>"
        await query.message.edit_text(
            txt, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Orqaga", callback_data="back:main")]]),
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

        result = await run_sync("manual", progress_cb=progress_cb, mode="fast")
        if result == "ok":
            txt = "✅ <b>Tez yangilash tugadi!</b>\n<i>(balans, ombor, bugungi vizit va buyurtma)</i>"
        elif result == "busy":
            txt = "⏳ <b>Boshqa sync hozir ishlamoqda.</b>\n<i>Bir necha daqiqa kuting.</i>"
        else:
            txt = f"⚠️ <b>Xato yuz berdi:</b>\n<code>{result[:300]}</code>"
        await msg.edit_text(
            txt, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Orqaga", callback_data="back:main")]]),
        )
        return

    # --- To'liq yangilash (~15 min) ---
    if data == "menu:sync_full":
        msg = await query.message.edit_text(
            "📥 <b>To'liq yangilash boshlanmoqda...</b>\n"
            "<i>~15 daqiqa olishi mumkin. Kutishingiz shart emas — orqada ishlaydi.</i>",
            parse_mode=ParseMode.HTML,
        )
        import time as _time
        last_edit_full = [_time.time()]

        async def progress_cb_full(text: str):
            now_t = _time.time()
            if now_t - last_edit_full[0] < 1.5:
                return
            last_edit_full[0] = now_t
            try:
                await msg.edit_text(
                    f"📥 <b>To'liq yangilash...</b>\n\n{text}",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass

        result = await run_sync("manual", progress_cb=progress_cb_full, mode="full")
        if result == "ok":
            txt = "✅ <b>To'liq yangilash tugadi!</b>\n<i>(hamma ma'lumotlar yangi)</i>"
        elif result == "busy":
            txt = "⏳ <b>Boshqa sync hozir ishlamoqda.</b>\n<i>Tugashini kuting.</i>"
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

    waiting = context.user_data.get("waiting_for") or ""

    # Plan o'rnatish (savdo)
    if waiting.startswith("sales_plan:"):
        agent_id = waiting.split(":", 1)[1]
        try:
            value = float(update.message.text.replace(" ", "").replace(",", "").replace(".", ""))
        except ValueError:
            await update.message.reply_text("⚠️ Faqat raqam yozing. Misol: <code>50000000</code>", parse_mode=ParseMode.HTML)
            return
        with get_conn() as conn:
            from datetime import datetime
            now = datetime.now().isoformat(timespec="seconds")
            conn.execute("""
                INSERT INTO agent_plans (agent_sd_id, sales_plan, visit_plan, updated_at)
                VALUES (?, ?, COALESCE((SELECT visit_plan FROM agent_plans WHERE agent_sd_id=?), 0), ?)
                ON CONFLICT(agent_sd_id) DO UPDATE SET sales_plan=excluded.sales_plan, updated_at=excluded.updated_at
            """, (agent_id, value, agent_id, now))
        context.user_data["waiting_for"] = None
        await update.message.reply_text(
            f"✅ Savdo plani saqlandi: <b>{int(value):,} so'm</b>".replace(",", " "),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Planlar ro'yxati", callback_data="menu:plans")]]),
        )
        return

    # Plan o'rnatish (vizit)
    if waiting.startswith("visit_plan:"):
        agent_id = waiting.split(":", 1)[1]
        try:
            value = int(update.message.text.replace(" ", "").replace(",", ""))
        except ValueError:
            await update.message.reply_text("⚠️ Faqat raqam yozing. Misol: <code>750</code>", parse_mode=ParseMode.HTML)
            return
        with get_conn() as conn:
            from datetime import datetime
            now = datetime.now().isoformat(timespec="seconds")
            conn.execute("""
                INSERT INTO agent_plans (agent_sd_id, sales_plan, visit_plan, updated_at)
                VALUES (?, COALESCE((SELECT sales_plan FROM agent_plans WHERE agent_sd_id=?), 0), ?, ?)
                ON CONFLICT(agent_sd_id) DO UPDATE SET visit_plan=excluded.visit_plan, updated_at=excluded.updated_at
            """, (agent_id, agent_id, value, now))
        context.user_data["waiting_for"] = None
        await update.message.reply_text(
            f"✅ Vizit plani saqlandi: <b>{value}</b> ta",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Planlar ro'yxati", callback_data="menu:plans")]]),
        )
        return

    if waiting in ("dsales", "visits", "topprods"):
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


async def _send_with_retry(coro_factory, what: str, max_attempts: int = 6):
    """Telegram 'Flood control' va vaqtinchalik tarmoq xatolarini
    avtomatik kutib qayta yuboradi. coro_factory — har urinishda YANGI
    coroutine qaytaruvchi funksiya (lambda)."""
    for attempt in range(1, max_attempts + 1):
        try:
            return await coro_factory()
        except RetryAfter as exc:
            wait = float(getattr(exc, "retry_after", 5)) + 1
            logger.warning("Flood control (%s): %.0f s kutilmoqda (urinish %d/%d)",
                           what, wait, attempt, max_attempts)
            await asyncio.sleep(wait)
        except (TimedOut, NetworkError) as exc:
            logger.warning("Tarmoq xatosi (%s): %s — qayta urinish %d/%d",
                           what, exc, attempt, max_attempts)
            await asyncio.sleep(3)
    logger.error("%s yuborilmadi (%d urinishdan keyin ham bo'lmadi)", what, max_attempts)
    return None


async def send_agent_cards_to_group(app: Application, chat_id: int = None) -> int:
    """Har faol agent uchun hisobot kartochkasini RASM ko'rinishida guruhga yuboradi.
    Shahar agentlari va viloyat agentlari alohida guruhlanadi.
    Har bo'lim oxirida ball jadvali rasmi yuboriladi."""
    if chat_id is None:
        with get_conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key='report_chat_id'").fetchone()
            if not row or not row["value"]:
                logger.info("Guruh sozlanmagan — agent kartochkalari yuborilmadi.")
                return 0
            chat_id = int(row["value"])

    with get_conn() as conn:
        agents = conn.execute(
            "SELECT sd_id, name FROM agents WHERE active='Y' ORDER BY name"
        ).fetchall()

    city_agents = []
    region_agents = []
    other_agents = []
    for a in agents:
        kind = reports.classify_agent(a["name"])
        if kind == "city":
            city_agents.append(a)
        elif kind == "region":
            region_agents.append(a)
        else:
            other_agents.append(a)

    today_str = date.today().strftime("%d.%m.%Y")
    sent = 0

    async def send_section(header: str, group: list) -> int:
        """Bo'lim sarlavhasi + har agent uchun PNG kartochka (caption bilan)."""
        if not group:
            return 0
        await _send_with_retry(
            lambda: app.bot.send_message(chat_id, header, parse_mode=ParseMode.HTML),
            "section header",
        )
        await asyncio.sleep(1.0)
        cnt = 0
        total = len(group)
        for i, a in enumerate(group, 1):
            try:
                if _IMAGE_REPORTS_OK:
                    png = image_reports.render_agent_card(a["sd_id"])
                    if not png:
                        continue
                    caption = f"👤 <b>{a['name']}</b>  ·  📅 {today_str}  ·  ({i}/{total})"
                    res = await _send_with_retry(
                        lambda: app.bot.send_photo(
                            chat_id, photo=png, caption=caption,
                            parse_mode=ParseMode.HTML,
                        ),
                        f"kartochka ({a['name']})",
                    )
                    if res is None:
                        continue
                else:
                    # Pillow yo'q bo'lsa — eski matn formatda yuborish
                    text = reports.agent_report_card(a["sd_id"], index=i, total=total)
                    if not text:
                        continue
                    await _send_with_retry(
                        lambda: app.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML),
                        f"kartochka matn ({a['name']})",
                    )
                cnt += 1
                await asyncio.sleep(1.2)
            except Exception as exc:
                logger.error("Kartochka yuborishda xato (%s): %s", a["name"], exc)
        return cnt

    async def send_ball_image(category: str, label: str) -> None:
        try:
            if _IMAGE_REPORTS_OK:
                png = image_reports.render_ball_table(category)
                if not png:
                    logger.info("Ball jadvali (%s) — ma'lumot yo'q", category)
                    return
                caption = f"🔥 <b>BUGUNGI BALL JADVALI</b>  ·  {label}  ·  📅 {today_str}"
                await _send_with_retry(
                    lambda: app.bot.send_photo(
                        chat_id, photo=png, caption=caption,
                        parse_mode=ParseMode.HTML,
                    ),
                    f"ball jadvali ({category})",
                )
            else:
                # Eski matn formatda
                ball_text = reports.daily_ball_report(category)
                if ball_text:
                    await _send_with_retry(
                        lambda: app.bot.send_message(chat_id, ball_text, parse_mode=ParseMode.HTML),
                        f"ball matn ({category})",
                    )
            await asyncio.sleep(1.2)
        except Exception as exc:
            logger.error("Ball jadvali (%s) xatosi: %s", category, exc)

    sent += await send_section(
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n🏙️ <b>SHAHAR AGENTLARI</b>\n📅 {today_str}\n━━━━━━━━━━━━━━━━━━━━━━━━━━",
        city_agents,
    )
    if city_agents:
        await send_ball_image("city", "SHAHAR AGENTLARI")

    sent += await send_section(
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n🏘️ <b>VILOYAT AGENTLARI</b>\n📅 {today_str}\n━━━━━━━━━━━━━━━━━━━━━━━━━━",
        region_agents,
    )
    if region_agents:
        await send_ball_image("region", "VILOYAT AGENTLARI")

    if other_agents:
        sent += await send_section(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n❓ <b>BOSHQA AGENTLAR</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━",
            other_agents,
        )
    logger.info("Guruhga %d ta agent kartochkasi (PNG) + 2 ta ball jadvali (PNG) yuborildi", sent)
    return sent


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
    # Adminlarga bot holati haqida xabar
    if _IMAGE_REPORTS_OK:
        status_msg = "✅ Bot ishga tushdi\n🖼 <b>RASM rejimi</b> — Pillow OK, kartochkalar rasm ko'rinishida yuboriladi."
    else:
        status_msg = "⚠️ Bot ishga tushdi\n📝 <b>MATN rejimi</b> — Pillow o'rnatilmagan, kartochkalar matn ko'rinishida yuboriladi.\n<i>Railway loglarini tekshiring.</i>"
    for admin_id in ADMIN_IDS:
        try:
            await app.bot.send_message(admin_id, status_msg, parse_mode=ParseMode.HTML)
        except Exception:
            pass


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
    app.add_handler(CommandHandler("version", version_cmd))
    app.add_handler(CommandHandler("setgroup", setgroup_cmd))
    app.add_handler(CommandHandler("cleargroup", cleargroup_cmd))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message))

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
