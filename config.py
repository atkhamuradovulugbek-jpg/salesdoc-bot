"""
config.py — .env fayldan barcha sozlamalarni o'qiydi.
Bu fayl bir marta ishga tushadi va hamma boshqa fayllar shu yerdan qiymat oladi.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_IDS: set[int] = {
    int(x.strip()) for x in os.getenv("ALLOWED_TELEGRAM_IDS", "").split(",") if x.strip()
}
ADMIN_IDS: set[int] = {
    int(x.strip()) for x in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",") if x.strip()
}

# Sales Doctor API
SALESDOC_BASE_URL: str = os.environ["SALESDOC_BASE_URL"].rstrip("/")
SALESDOC_LOGIN: str = os.environ["SALESDOC_LOGIN"]
SALESDOC_PASSWORD: str = os.environ["SALESDOC_PASSWORD"]

# Bot sozlamalari (chegaralar)
DEAD_OUTLET_DAYS: int = int(os.getenv("DEAD_OUTLET_DAYS", "14"))
DEAD_OUTLET_LOOKBACK_DAYS: int = int(os.getenv("DEAD_OUTLET_LOOKBACK_DAYS", "90"))
DEBT_ALERT_THRESHOLD: float = float(os.getenv("DEBT_ALERT_THRESHOLD", "0"))
SALES_DROP_ALERT_PERCENT: float = float(os.getenv("SALES_DROP_ALERT_PERCENT", "20"))

# Vaqt mintaqasi
TIMEZONE: str = "Asia/Tashkent"
