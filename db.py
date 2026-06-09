"""
db.py — SQLite ma'lumotlar bazasi.
Barcha jadvallar shu yerda yaratiladi.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "bot.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Barcha jadvallarni yaratadi (agar mavjud bo'lmasa)."""
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS agents (
                sd_id       TEXT PRIMARY KEY,
                code_1c     TEXT,
                name        TEXT NOT NULL,
                active      TEXT DEFAULT 'Y',
                updated_at  TEXT
            );

            CREATE TABLE IF NOT EXISTS products (
                sd_id       TEXT PRIMARY KEY,
                code_1c     TEXT,
                name        TEXT NOT NULL,
                category    TEXT,
                updated_at  TEXT
            );

            CREATE TABLE IF NOT EXISTS clients (
                sd_id               TEXT PRIMARY KEY,
                code_1c             TEXT,
                name                TEXT NOT NULL,
                primary_agent_sd_id TEXT,
                territory           TEXT,
                updated_at          TEXT
            );

            CREATE TABLE IF NOT EXISTS orders (
                sd_id                   TEXT PRIMARY KEY,
                date                    TEXT NOT NULL,
                status                  INTEGER,
                agent_sd_id             TEXT,
                client_sd_id            TEXT,
                total_after_discount    REAL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS order_items (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                order_sd_id     TEXT NOT NULL,
                product_sd_id   TEXT,
                product_name    TEXT,
                quantity        REAL DEFAULT 0,
                summa           REAL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS balances (
                client_sd_id    TEXT PRIMARY KEY,
                client_name     TEXT,
                balance         REAL DEFAULT 0,
                updated_at      TEXT
            );

            CREATE TABLE IF NOT EXISTS stock (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                product_sd_id   TEXT,
                product_name    TEXT,
                warehouse       TEXT,
                quantity        REAL DEFAULT 0,
                updated_at      TEXT,
                UNIQUE(product_sd_id, warehouse)
            );

            CREATE TABLE IF NOT EXISTS visits (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                date            TEXT NOT NULL,
                agent_sd_id     TEXT,
                agent_name      TEXT,
                client_sd_id    TEXT,
                client_name     TEXT,
                planned         INTEGER DEFAULT 0,
                visited         INTEGER DEFAULT 0,
                has_order       INTEGER DEFAULT 0,
                order_summa     REAL DEFAULT 0,
                UNIQUE(date, agent_sd_id, client_sd_id)
            );

            CREATE TABLE IF NOT EXISTS sync_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at      TEXT NOT NULL,
                type        TEXT DEFAULT 'scheduled',
                status      TEXT DEFAULT 'ok',
                note        TEXT
            );

            CREATE TABLE IF NOT EXISTS settings (
                key     TEXT PRIMARY KEY,
                value   TEXT
            );

            CREATE TABLE IF NOT EXISTS categories (
                sd_id       TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                active      TEXT,
                updated_at  TEXT
            );

            CREATE TABLE IF NOT EXISTS agent_plans (
                agent_sd_id   TEXT PRIMARY KEY,
                sales_plan    REAL DEFAULT 0,
                visit_plan    INTEGER DEFAULT 0,
                updated_at    TEXT
            );
        """)


def upsert_agent(conn: sqlite3.Connection, sd_id: str, code_1c: str, name: str, active: str, updated_at: str) -> None:
    conn.execute("""
        INSERT INTO agents (sd_id, code_1c, name, active, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(sd_id) DO UPDATE SET
            code_1c=excluded.code_1c,
            name=excluded.name,
            active=excluded.active,
            updated_at=excluded.updated_at
    """, (sd_id, code_1c, name, active, updated_at))


def upsert_product(conn: sqlite3.Connection, sd_id: str, code_1c: str, name: str, category: str, updated_at: str) -> None:
    conn.execute("""
        INSERT INTO products (sd_id, code_1c, name, category, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(sd_id) DO UPDATE SET
            code_1c=excluded.code_1c,
            name=excluded.name,
            category=excluded.category,
            updated_at=excluded.updated_at
    """, (sd_id, code_1c, name, category, updated_at))


def upsert_client(conn: sqlite3.Connection, sd_id: str, code_1c: str, name: str,
                  primary_agent_sd_id: str | None, territory: str | None, updated_at: str) -> None:
    conn.execute("""
        INSERT INTO clients (sd_id, code_1c, name, primary_agent_sd_id, territory, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(sd_id) DO UPDATE SET
            code_1c=excluded.code_1c,
            name=excluded.name,
            primary_agent_sd_id=excluded.primary_agent_sd_id,
            territory=excluded.territory,
            updated_at=excluded.updated_at
    """, (sd_id, code_1c, name, primary_agent_sd_id, territory, updated_at))


def upsert_order(conn: sqlite3.Connection, sd_id: str, date: str, status: int,
                 agent_sd_id: str, client_sd_id: str, total: float) -> None:
    conn.execute("""
        INSERT INTO orders (sd_id, date, status, agent_sd_id, client_sd_id, total_after_discount)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(sd_id) DO UPDATE SET
            date=excluded.date,
            status=excluded.status,
            agent_sd_id=excluded.agent_sd_id,
            client_sd_id=excluded.client_sd_id,
            total_after_discount=excluded.total_after_discount
    """, (sd_id, date, status, agent_sd_id, client_sd_id, total))


def replace_order_items(conn: sqlite3.Connection, order_sd_id: str, items: list[dict]) -> None:
    conn.execute("DELETE FROM order_items WHERE order_sd_id=?", (order_sd_id,))
    conn.executemany("""
        INSERT INTO order_items (order_sd_id, product_sd_id, product_name, quantity, summa)
        VALUES (?, ?, ?, ?, ?)
    """, [
        (order_sd_id,
         i.get("product_sd_id", ""),
         i.get("product_name", ""),
         i.get("quantity", 0),
         i.get("summa", 0))
        for i in items
    ])


def upsert_balance(conn: sqlite3.Connection, client_sd_id: str, client_name: str,
                   balance: float, updated_at: str) -> None:
    conn.execute("""
        INSERT INTO balances (client_sd_id, client_name, balance, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(client_sd_id) DO UPDATE SET
            client_name=excluded.client_name,
            balance=excluded.balance,
            updated_at=excluded.updated_at
    """, (client_sd_id, client_name, balance, updated_at))


def upsert_stock(conn: sqlite3.Connection, product_sd_id: str, product_name: str,
                 warehouse: str, quantity: float, updated_at: str) -> None:
    conn.execute("""
        INSERT INTO stock (product_sd_id, product_name, warehouse, quantity, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(product_sd_id, warehouse) DO UPDATE SET
            product_name=excluded.product_name,
            quantity=excluded.quantity,
            updated_at=excluded.updated_at
    """, (product_sd_id, product_name, warehouse, quantity, updated_at))


def upsert_visit(conn: sqlite3.Connection, date: str, agent_sd_id: str, agent_name: str,
                 client_sd_id: str, client_name: str, planned: int, visited: int,
                 has_order: int, order_summa: float) -> None:
    conn.execute("""
        INSERT INTO visits (date, agent_sd_id, agent_name, client_sd_id, client_name,
                            planned, visited, has_order, order_summa)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date, agent_sd_id, client_sd_id) DO UPDATE SET
            agent_name=excluded.agent_name,
            client_name=excluded.client_name,
            planned=excluded.planned,
            visited=excluded.visited,
            has_order=excluded.has_order,
            order_summa=excluded.order_summa
    """, (date, agent_sd_id, agent_name, client_sd_id, client_name,
          planned, visited, has_order, order_summa))


def log_sync(conn: sqlite3.Connection, run_at: str, sync_type: str, status: str, note: str = "") -> None:
    conn.execute("""
        INSERT INTO sync_log (run_at, type, status, note)
        VALUES (?, ?, ?, ?)
    """, (run_at, sync_type, status, note))
