"""
nz_config.py — nazorat botining sozlamalari (.env dan).
Asosiy bot config.py'dan ALOHIDA: o'z tokeni, o'z adminlari.
Sales Doctor va DB asosiy bot bilan umumiy.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# Telegram (ALOHIDA bot)
NAZORAT_BOT_TOKEN: str = os.environ["NAZORAT_BOT_TOKEN"]
ADMIN_IDS: set[int] = {
    int(x.strip()) for x in os.getenv("NAZORAT_ADMIN_IDS", "").split(",") if x.strip()
}

# DRY_RUN: True bo'lsa hamma hisobot FAQAT adminga keladi (agentlarga/guruhga emas).
# Sinov davri uchun. Jonli chiqishdan oldin False qilinadi.
DRY_RUN: bool = os.getenv("DRY_RUN", "true").lower() not in ("0", "false", "no", "")

# Guruh chat ID'lari (podium/kunlik reyting tashlanadi). settings jadvalidan ham
# olinadi; bu yerda .env orqali override qilish mumkin.
GROUP_CITY_CHAT_ID: int = int(os.getenv("GROUP_CITY_CHAT_ID", "0") or 0)
GROUP_REGION_CHAT_ID: int = int(os.getenv("GROUP_REGION_CHAT_ID", "0") or 0)

# Vaqtlar (Asia/Tashkent)
MORNING_HOUR: int = int(os.getenv("NZ_MORNING_HOUR", "10"))
MORNING_MINUTE: int = int(os.getenv("NZ_MORNING_MINUTE", "0"))
EVENING_HOUR: int = int(os.getenv("NZ_EVENING_HOUR", "20"))
EVENING_MINUTE: int = int(os.getenv("NZ_EVENING_MINUTE", "0"))
# Hisobotdan oldin sync (fresh ma'lumot uchun)
SYNC_BEFORE_MIN: int = int(os.getenv("NZ_SYNC_BEFORE_MIN", "10"))

TIMEZONE: str = "Asia/Tashkent"
