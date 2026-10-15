"""
quick.py — «HOZIRGI HOLAT» yengil yangilash (2026-08-11, supervayzerlar so'rovi).

MUAMMO: supervayzer jadval tugmasini bosganda bot BAZADAN o'qiydi, baza esa
kuniga 6 marta yangilanadi (03:00/10:00/12:00/15:00/20:00/20:10). Soat 17:00 da
bosilsa 15:00 dagi raqam ko'rinardi — 2 soat eski.

O'LCHOV (jonli API, 2026-08-11):
    bugungi buyurtmalar ....  2.1s   (138 ta)
    bugungi vizitlar .......  2.4s   (1139 ta)
    ulanish ................  0.7s
    ────────────────────────────────
    JAMI ...................  ~5s
  taqqos: oylik buyurtma 25s + balans 11s → hozirgi "tez" sync 2-3 daqiqa.

Shuning uchun `sync.run_sync(mode="today")` — faqat bugungi buyurtma va vizit.
Qarz/ombor/oylik tarix TORTILMAYDI (kun davomida deyarli o'zgarmaydi).

HIMOYA (egasi tasdiqladi):
  • 90 soniya KUTISH — yaqinda yangilangan bo'lsa API'ga qayta borilmaydi;
  • hisobot vaqtida (blackout) — yangilanmaydi, hisobot buzilmasin;
  • boshqa sync ketayotgan bo'lsa — kutmaydi, bordagi ma'lumotni beradi.

Kutish DB'dan o'qiladi (`sync_log`), chunki bot va web AYRIM jarayonlar —
xotiradagi o'zgaruvchi ular orasida bo'linmaydi.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from db import get_conn

from . import taskq          # blackout oynasi shu yerdan (aylanma import yo'q:
                            # taskq quick'ni faqat funksiya ichida import qiladi)
from .nz_config import TIMEZONE

logger = logging.getLogger("nazorat.quick")
TZ = ZoneInfo(TIMEZONE)

COOLDOWN_SEC = 90            # egasi tanladi (2026-08-11)
MODE = "today"


def _now() -> datetime:
    return datetime.now(TZ)


def last_refresh(conn, kind: str = MODE) -> datetime | None:
    """Oxirgi MUVAFFAQIYATLI yengil yangilash vaqti (yo'q bo'lsa None).

    kind='today' — savdo/vizit; kind='debt' — balanslar. Ikkisi ALOHIDA
    sanaladi: savdo yangilangani qarz tugmasini bloklamasligi kerak."""
    row = conn.execute(
        "SELECT run_at FROM sync_log WHERE type LIKE ? AND status='ok' "
        "ORDER BY id DESC LIMIT 1", (f"%_{kind}",)).fetchone()
    if not row or not row["run_at"]:
        return None
    try:
        return datetime.fromisoformat(row["run_at"])
    except ValueError:
        return None


def last_any_sync(conn) -> datetime | None:
    """Oxirgi HAR QANDAY muvaffaqiyatli sync (ekranda "qachon yangilangan" uchun)."""
    row = conn.execute(
        "SELECT run_at FROM sync_log WHERE status='ok' ORDER BY id DESC LIMIT 1").fetchone()
    if not row or not row["run_at"]:
        return None
    try:
        return datetime.fromisoformat(row["run_at"])
    except ValueError:
        return None


def seconds_since(dt: datetime | None) -> int | None:
    if dt is None:
        return None
    return max(0, int((_now() - dt).total_seconds()))


def cooldown_left(conn, kind: str = MODE) -> int:
    """Kutish tugashiga necha soniya qoldi (0 = hozir yangilash mumkin)."""
    age = seconds_since(last_refresh(conn, kind))
    if age is None:
        return 0
    return max(0, COOLDOWN_SEC - age)


def age_text(sec: int | None) -> str:
    """Odam tiliga: '40 soniya oldin' / '12 daqiqa oldin'."""
    if sec is None:
        return "hali yangilanmagan"
    if sec < 60:
        return f"{sec} soniya oldin"
    if sec < 3600:
        return f"{sec // 60} daqiqa oldin"
    h = sec // 3600
    return f"{h} soat oldin"


async def refresh(reason: str = "manual", force: bool = False) -> tuple[bool, str]:
    """Yengil yangilash. Qaytadi: (yangilandimi, izoh).

    Xato bo'lsa ham HECH QACHON ko'tarmaydi — chaqiruvchi bordagi ma'lumot bilan
    davom etishi kerak (yangilanmagani hisobotni buzmasin)."""
    with get_conn() as conn:
        left = 0 if force else cooldown_left(conn)
        if left:
            age = seconds_since(last_refresh(conn))
            return False, age_text(age)

    # Hisobot vaqti — tegmaymiz (kechki/ertalabki job o'z sync'ini qiladi)
    if taskq.in_blackout():
        return False, "hisobot vaqti"

    try:
        from sync import run_sync
        res = await run_sync(f"quick_{reason}", mode=MODE)
    except Exception as e:                                # noqa: BLE001
        logger.exception("Yengil yangilash xatosi")
        return False, f"xato: {type(e).__name__}"

    if res == "busy":
        return False, "boshqa yangilash ketyapti"
    if res != "ok":
        logger.warning("Yengil yangilash: %s", res)
        return False, "xato"
    return True, "yangilandi"
