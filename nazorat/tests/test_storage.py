"""nz_ jadvallar testlari (xotirada SQLite)."""

import sqlite3

import pytest

from nazorat import storage


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    # snapshot uchun asosiy botdagi balances jadvali kerak
    c.execute("CREATE TABLE balances (client_sd_id TEXT PRIMARY KEY, client_name TEXT, balance REAL, updated_at TEXT)")
    storage.init_nz_tables(c)
    return c


def test_kod_ulash_va_qayta_ulash(conn):
    old = storage.bind_code(conn, "TSH-YNB-01", 111, "agent", "d0_51", "2026-07-08")
    assert old is None
    row = storage.binding_by_chat(conn, 111)
    assert row["code"] == "TSH-YNB-01" and row["sd_id"] == "d0_51"
    # Boshqa chat o'sha kodni kiritdi — eski chat qaytadi (adminga signal)
    old = storage.bind_code(conn, "TSH-YNB-01", 222, "agent", "d0_51", "2026-07-09")
    assert old == 111
    assert storage.binding_by_chat(conn, 111) is None
    assert storage.chat_for_sd_id(conn, "d0_51") == 222


def test_idempotent_yuborish(conn):
    assert not storage.already_sent(conn, "2026-07-08", "evening", "111")
    storage.mark_sent(conn, "2026-07-08", "evening", "111", "2026-07-08T20:00")
    assert storage.already_sent(conn, "2026-07-08", "evening", "111")
    # qayta mark_sent xato bermaydi
    storage.mark_sent(conn, "2026-07-08", "evening", "111", "2026-07-08T20:05")


def test_qarz_yoshi(conn):
    # 5 kun ketma-ket qarz
    for d in ("2026-07-04", "2026-07-05", "2026-07-06", "2026-07-07", "2026-07-08"):
        conn.execute("INSERT INTO nz_balance_history VALUES (?, 'shop1', -500000)", (d,))
    assert storage.debt_age_days(conn, "shop1", "2026-07-08") == 5
    # Uzilishdan keyin faqat yangi davr sanaladi
    conn.execute("INSERT INTO nz_balance_history VALUES ('2026-06-20', 'shop2', -100000)")
    conn.execute("INSERT INTO nz_balance_history VALUES ('2026-07-08', 'shop2', -100000)")
    assert storage.debt_age_days(conn, "shop2", "2026-07-08") == 1
    # Tarix yo'q — None
    assert storage.debt_age_days(conn, "shop3", "2026-07-08") is None


def test_snapshot_balances(conn):
    conn.execute("INSERT INTO balances VALUES ('shop1', 'Do`kon 1', -700000, 'x')")
    conn.execute("INSERT INTO balances VALUES ('shop2', 'Do`kon 2', 300000, 'x')")  # qarz emas
    n = storage.snapshot_balances(conn, "2026-07-08")
    assert n == 1
    assert storage.debt_age_days(conn, "shop1", "2026-07-08") == 1


def test_oy_natijalari_va_taqiq(conn):
    storage.save_month_result(conn, 2026, 6, "city", {
        "podium": [{"place": 1, "sd_id": "d0_51", "prize": 1500000}],
        "growth": {"sd_id": "d0_150", "pct": 14},
    }, "2026-07-03")
    assert storage.last_first_place(conn, 2026, 6, "city") == "d0_51"
    assert storage.last_growth_winner(conn, 2026, 6, "city") == "d0_150"
    assert storage.last_first_place(conn, 2026, 5, "city") is None
    data = storage.get_month_result(conn, 2026, 6, "city")
    assert data["confirmed"] is False
    storage.confirm_month(conn, 2026, 6)
    assert storage.get_month_result(conn, 2026, 6, "city")["confirmed"] is True


def test_raw_cache(conn):
    payload = {"orders": [{"SD_id": "x", "sum": 1}] * 100}
    storage.save_raw(conn, "2026-07-08", "getOrder", payload, "2026-07-08T20:00")
    assert storage.load_raw(conn, "2026-07-08", "getOrder") == payload
    assert storage.load_raw(conn, "2026-07-07", "getOrder") is None
