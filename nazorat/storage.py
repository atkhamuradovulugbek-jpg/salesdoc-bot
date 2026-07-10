"""
storage.py — nazorat botining o'z jadvallari (asosiy bot.db ichida, nz_ prefiksi).

nz_bindings        — kod ↔ Telegram chat bog'lanishi (agent/supervayzer/admin)
nz_sent_log        — yuborilgan xabarlar jurnali (idempotentlik: qayta ishga
                     tushganda dublikat yubormaslik)
nz_balance_history — har kuni har mijoz qarz qoldig'i (qarz YOSHI shundan chiqadi)
nz_month_results   — oy yakunlari (podium/o'sish g'oliblari, "ketma-ket 2 oy yo'q"
                     qoidasi tarixdan tekshiriladi), admin tasdig'i holati
nz_raw_cache       — Sales Doctor xom javoblari (zlib siqilgan, audit uchun)
"""

import json
import sqlite3
import zlib
from datetime import date, timedelta

RAW_CACHE_KEEP_DAYS = 60


def init_nz_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS nz_bindings (
            code        TEXT PRIMARY KEY,
            chat_id     INTEGER NOT NULL,
            role        TEXT NOT NULL DEFAULT 'agent',   -- agent / supervisor / admin
            sd_id       TEXT,
            bound_at    TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS nz_sent_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            day         TEXT NOT NULL,          -- hisobot sanasi (YYYY-MM-DD)
            kind        TEXT NOT NULL,          -- morning / evening / group_daily / alert:...
            target      TEXT NOT NULL,          -- chat_id yoki 'group'
            sent_at     TEXT NOT NULL,
            UNIQUE(day, kind, target)
        );

        CREATE TABLE IF NOT EXISTS nz_balance_history (
            day             TEXT NOT NULL,
            client_sd_id    TEXT NOT NULL,
            balance         REAL DEFAULT 0,
            PRIMARY KEY (day, client_sd_id)
        );

        CREATE TABLE IF NOT EXISTS nz_month_results (
            year        INTEGER NOT NULL,
            month       INTEGER NOT NULL,
            league      TEXT NOT NULL,
            payload     TEXT NOT NULL,          -- JSON: winners, growth, toy, kpi
            confirmed   INTEGER DEFAULT 0,      -- admin /tasdiqla bosdimi
            created_at  TEXT NOT NULL,
            PRIMARY KEY (year, month, league)
        );

        CREATE TABLE IF NOT EXISTS nz_raw_cache (
            day         TEXT NOT NULL,
            method      TEXT NOT NULL,
            payload     BLOB,                   -- zlib(json)
            saved_at    TEXT NOT NULL,
            PRIMARY KEY (day, method)
        );
    """)


# ------------------------------------------------------------------
# Kod ulash (bindings)
# ------------------------------------------------------------------

def bind_code(conn: sqlite3.Connection, code: str, chat_id: int, role: str,
              sd_id: str | None, now: str) -> int | None:
    """
    Kodni chatga bog'laydi. Kod avval boshqa chatga ulangan bo'lsa,
    eski chat_id qaytariladi (adminga xabar berish uchun), bog'lanish yangilanadi.
    """
    old = conn.execute("SELECT chat_id FROM nz_bindings WHERE code=?", (code,)).fetchone()
    old_chat = old["chat_id"] if old and old["chat_id"] != chat_id else None
    conn.execute("""
        INSERT INTO nz_bindings (code, chat_id, role, sd_id, bound_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET
            chat_id=excluded.chat_id, role=excluded.role,
            sd_id=excluded.sd_id, bound_at=excluded.bound_at
    """, (code, chat_id, role, sd_id, now))
    return old_chat


def binding_by_chat(conn: sqlite3.Connection, chat_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM nz_bindings WHERE chat_id=?", (chat_id,)
    ).fetchone()


def chat_for_sd_id(conn: sqlite3.Connection, sd_id: str) -> int | None:
    row = conn.execute(
        "SELECT chat_id FROM nz_bindings WHERE sd_id=? AND role='agent'", (sd_id,)
    ).fetchone()
    return row["chat_id"] if row else None


def chat_for_supervisor(conn: sqlite3.Connection, code: str) -> int | None:
    """Supervayzer kodiga bog'langan chat (v2'da ulanadi; ulanmagan bo'lsa None)."""
    if not code:
        return None
    row = conn.execute(
        "SELECT chat_id FROM nz_bindings WHERE code=? AND role='supervisor'", (code,)
    ).fetchone()
    return row["chat_id"] if row else None


# ------------------------------------------------------------------
# Idempotent yuborish jurnali
# ------------------------------------------------------------------

def already_sent(conn: sqlite3.Connection, day: str, kind: str, target: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM nz_sent_log WHERE day=? AND kind=? AND target=?",
        (day, kind, target),
    ).fetchone()
    return row is not None


def mark_sent(conn: sqlite3.Connection, day: str, kind: str, target: str, now: str) -> None:
    conn.execute("""
        INSERT OR IGNORE INTO nz_sent_log (day, kind, target, sent_at)
        VALUES (?, ?, ?, ?)
    """, (day, kind, target, now))


# ------------------------------------------------------------------
# Qarz tarixi va yoshi
# ------------------------------------------------------------------

def snapshot_balances(conn: sqlite3.Connection, day: str) -> int:
    """Bugungi balances jadvalini tarixga ko'chiradi. Qaytadi: yozuvlar soni."""
    cur = conn.execute("""
        INSERT OR REPLACE INTO nz_balance_history (day, client_sd_id, balance)
        SELECT ?, client_sd_id, balance FROM balances WHERE balance < 0
    """, (day,))
    return cur.rowcount


def debt_age_days(conn: sqlite3.Connection, client_sd_id: str, today: str) -> int | None:
    """
    Qarz YOSHI: oxirgi uzluksiz qarzdorlik davri necha kun.
    Tarixda eng so'nggi qarzsiz (yoki yozuvsiz) kundan keyingi davr sanaladi.
    Tarix yetarli bo'lmasa None (bot yaqinda ishga tushgan).
    """
    rows = conn.execute("""
        SELECT day FROM nz_balance_history
        WHERE client_sd_id=? AND day<=? ORDER BY day DESC LIMIT 120
    """, (client_sd_id, today)).fetchall()
    if not rows:
        return None
    days = [r["day"] for r in rows]
    # Uzluksizlikni tekshiramiz: bugungi kundan orqaga ketma-ket kunlar
    streak = 0
    expect = date.fromisoformat(today)
    for d in days:
        dd = date.fromisoformat(d)
        # 1-2 kunlik uzilishga yo'l qo'yamiz (sync o'tkazib yuborgan bo'lishi mumkin)
        if (expect - dd).days > 2:
            break
        streak = (date.fromisoformat(today) - dd).days + 1
        expect = dd - timedelta(days=1)
    return streak if streak > 0 else None


# ------------------------------------------------------------------
# Oy natijalari
# ------------------------------------------------------------------

def save_month_result(conn: sqlite3.Connection, year: int, month: int, league: str,
                      payload: dict, now: str) -> None:
    conn.execute("""
        INSERT INTO nz_month_results (year, month, league, payload, confirmed, created_at)
        VALUES (?, ?, ?, ?, 0, ?)
        ON CONFLICT(year, month, league) DO UPDATE SET
            payload=excluded.payload, created_at=excluded.created_at
    """, (year, month, league, json.dumps(payload, ensure_ascii=False), now))


def get_month_result(conn: sqlite3.Connection, year: int, month: int, league: str) -> dict | None:
    row = conn.execute("""
        SELECT payload, confirmed FROM nz_month_results
        WHERE year=? AND month=? AND league=?
    """, (year, month, league)).fetchone()
    if not row:
        return None
    data = json.loads(row["payload"])
    data["confirmed"] = bool(row["confirmed"])
    return data


def confirm_month(conn: sqlite3.Connection, year: int, month: int) -> None:
    conn.execute(
        "UPDATE nz_month_results SET confirmed=1 WHERE year=? AND month=?",
        (year, month),
    )


def last_first_place(conn: sqlite3.Connection, year: int, month: int, league: str) -> str | None:
    """O'tgan oy podium 1-o'rin sd_id (ketma-ket taqiq uchun)."""
    data = get_month_result(conn, year, month, league)
    if not data:
        return None
    winners = data.get("podium", [])
    for w in winners:
        if w.get("place") == 1:
            return w.get("sd_id")
    return None


def last_growth_winner(conn: sqlite3.Connection, year: int, month: int, league: str) -> str | None:
    data = get_month_result(conn, year, month, league)
    if not data:
        return None
    g = data.get("growth")
    return g.get("sd_id") if g else None


# ------------------------------------------------------------------
# Xom kesh (audit)
# ------------------------------------------------------------------

def save_raw(conn: sqlite3.Connection, day: str, method: str, data, now: str) -> None:
    blob = zlib.compress(json.dumps(data, ensure_ascii=False).encode(), level=6)
    conn.execute("""
        INSERT OR REPLACE INTO nz_raw_cache (day, method, payload, saved_at)
        VALUES (?, ?, ?, ?)
    """, (day, method, blob, now))
    # Eski keshni tozalash
    cutoff = (date.fromisoformat(day) - timedelta(days=RAW_CACHE_KEEP_DAYS)).isoformat()
    conn.execute("DELETE FROM nz_raw_cache WHERE day < ?", (cutoff,))


def load_raw(conn: sqlite3.Connection, day: str, method: str):
    row = conn.execute(
        "SELECT payload FROM nz_raw_cache WHERE day=? AND method=?", (day, method)
    ).fetchone()
    if not row:
        return None
    return json.loads(zlib.decompress(row["payload"]).decode())
