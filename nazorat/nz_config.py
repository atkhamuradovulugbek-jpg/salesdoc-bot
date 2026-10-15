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
# 20:10 (20:00 emas) — asosiy bot AYNAN 20:00 da sync qiladi; ikkalasi bir vaqtda
# Sales Doctor'ga urilsa nazorat sync BO'SH (orders=0) qaytib, eski 15:00 ma'lumotini
# yuborardi (2026-07-15 topildi: sync_log 20:00 da nazorat_fast=0 vs scheduled_fast=2044).
# 10 daqiqa kechiktirib, nazorat yolg'iz (to'qnashuvsiz) sync qiladi → to'g'ri raqam.
# Qulf (_today_locked) ham shu vaqtdan ochiladi — reveal ham 20:10.
EVENING_MINUTE: int = int(os.getenv("NZ_EVENING_MINUTE", "10"))
# Hisobotdan oldin sync (fresh ma'lumot uchun)
SYNC_BEFORE_MIN: int = int(os.getenv("NZ_SYNC_BEFORE_MIN", "10"))

# WATCHDOG: hisobotdan shuncha daqiqa keyin adminga "nima ketdi/ketmadi" xabari
# (2026-07-18 fail-loud: kechki job jimgina yarmida qulagan edi).
WATCHDOG_AFTER_MIN: int = int(os.getenv("NZ_WATCHDOG_AFTER_MIN", "30"))

# GPS kunlik xulosa supervayzerlarga ham boradimi (bosqichli ochish):
# 0 = faqat adminga (sinov), 1 = supervayzerlarga ham. Admin doim oladi.
GPS_TO_SUPERVISORS: bool = os.getenv("NZ_GPS_TO_SUPERVISORS", "0") not in ("0", "false", "False", "")

# Kunduzgi GPS trevoga (yo'qolish nazorati, 2-bosqich)
GPS_CHECK_MIN: int = int(os.getenv("NZ_GPS_CHECK_MIN", "20"))          # necha daqiqada tekshirish
GPS_MISSING_MIN: int = int(os.getenv("NZ_GPS_MISSING_MIN", "45"))      # sariq chegara (IKKALA liga)
GPS_MISSING_RED_MIN: int = int(os.getenv("NZ_GPS_MISSING_RED_MIN", "90"))  # qizil (adminga ham)
GPS_ESCALATE_MIN: int = int(os.getenv("NZ_GPS_ESCALATE_MIN", "30"))    # supervayzer javobsiz -> admin
# 0 = trevogalar faqat adminga (sinov), 1 = supervayzerlarga (qizil baribir adminga ham boradi)
ALERTS_TO_SUPERVISORS: bool = os.getenv("NZ_ALERTS_TO_SUPERVISORS", "0") not in ("0", "false", "False", "")

TIMEZONE: str = "Asia/Tashkent"
