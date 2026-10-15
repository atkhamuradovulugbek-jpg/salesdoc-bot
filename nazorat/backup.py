"""
backup.py — bazaning kunlik zaxira nusxasi (0.5-bosqich).

NEGA (llm-council: "eng katta e'tibordan chetda qolgan xavf"): hamma narsa BITTA
faylda (`bot.db`, Railway volume). Nusxa yo'q edi — fayl buzilsa yoki sync yarmida
uzilsa, hammasi yo'qoladi va 16 agentga "savdo 0" kartalari ketadi.

USUL: `VACUUM INTO` (SQLite'ning issiq, xavfsiz nusxasi — botlar ishlab turганда ham
to'g'ri nusxa beradi, WAL bilan mos) → gzip → admin Telegramiga DOCUMENT.
Nusxa /tmp da yasaladi (volume to'lmasin) va yuborilgach o'chiriladi.
Nusxa KONTEYNERDAN TASHQARIDA (Telegramda) saqlanadi — asosiy maqsad shu.

Jonli hajm (2026-07-30): bot.db 29MB → VACUUM 27MB → gzip 7.6MB (Telegram 50MB limiti).
"""

from __future__ import annotations

import gzip
import logging
import os
import shutil
import sqlite3
import tempfile
from datetime import date
from pathlib import Path

from db import DB_PATH, get_conn

from . import storage

logger = logging.getLogger("nazorat.backup")

TG_LIMIT = 45 * 1024 * 1024      # Telegram bot document limiti (50MB) — zapas bilan


def make_snapshot(dest: str | Path) -> Path:
    """Bazaning issiq (xavfsiz) nusxasi. Ishlab turgan botlarga xalaqit bermaydi.
    Sync/publish'dan OLDIN ham shu funksiya ishlatiladi (keyingi bosqichlar)."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("VACUUM INTO ?", (str(dest),))
    finally:
        conn.close()
    return dest


def gzip_file(src: str | Path) -> Path:
    src = Path(src)
    gz = src.with_suffix(src.suffix + ".gz")
    with open(src, "rb") as fi, gzip.open(gz, "wb", compresslevel=6) as fo:
        shutil.copyfileobj(fi, fo)
    return gz


def _human(n: int) -> str:
    return f"{n / 1_048_576:.1f} MB"


async def send_db_backup(app, admin_ids, reason: str = "kunlik") -> str:
    """Nusxa yasab, adminга Telegram document qilib yuboradi. Kuniga bir marta (dedup).
    Qaytadi: 'sent' | 'dup' | 'too_big'. Xato bo'lsa — ko'taradi (watchdog ushlaydi)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    day = date.today().isoformat()
    with get_conn() as conn:
        if storage.already_sent(conn, day, "backup", "admin"):
            return "dup"

    tmpdir = tempfile.mkdtemp(prefix="nzbackup-")
    try:
        snap = make_snapshot(Path(tmpdir) / f"bot-{day}.db")
        raw_size = snap.stat().st_size
        gz = gzip_file(snap)
        snap.unlink()                      # siqilgani yetarli
        gz_size = gz.stat().st_size

        if gz_size > TG_LIMIT:
            logger.error("Backup juda katta: %s", _human(gz_size))
            for aid in admin_ids:
                await app.bot.send_message(
                    aid, f"⚠️ Baza nusxasi juda katta ({_human(gz_size)}) — Telegramга "
                         f"sig'madi. Claude'ga ayting, boshqa usul kerak.")
            return "too_big"

        now = datetime.now(ZoneInfo("Asia/Tashkent")).strftime("%d.%m.%Y %H:%M")
        cap = (f"💾 Baza nusxasi ({reason}) · {now}\n"
               f"Hajmi: {_human(gz_size)} (siqilmagan {_human(raw_size)})\n"
               f"Bu faylni o'chirmang — baza buzilsa shundan tiklanadi.")
        sent_any = False
        with open(gz, "rb") as f:
            data = f.read()
        for aid in admin_ids:
            await app.bot.send_document(aid, document=data,
                                        filename=gz.name, caption=cap)
            sent_any = True
        if sent_any:
            with get_conn() as conn:
                storage.mark_sent(conn, day, "backup", "admin",
                                  datetime.now(ZoneInfo("Asia/Tashkent")).isoformat(timespec="seconds"))
        logger.info("Baza nusxasi yuborildi: %s", _human(gz_size))
        return "sent"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def sanity_ok(conn, table: str, min_ratio: float = 0.5) -> tuple[bool, int, int]:
    """Sync'dan keyin jadval qatorlari keskin kamayib ketmaganini tekshiradi.
    Qaytadi: (ok, hozirgi, oldingi). settings'dagi oxirgi son bilan solishtiradi.
    (Keyingi bosqichda sync ichida ishlatiladi — bo'sh baza 16 agentga 'savdo 0'
    kartasi yubormasligi uchun.)"""
    cur = conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]
    row = conn.execute("SELECT value FROM settings WHERE key=?",
                       (f"rowcount_{table}",)).fetchone()
    prev = int(row["value"]) if row and str(row["value"]).isdigit() else 0
    ok = prev == 0 or cur >= prev * min_ratio
    return ok, cur, prev
