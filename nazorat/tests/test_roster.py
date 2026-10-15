"""Roster: inactive_sd_ids + unknown_active_agents (ketgan/yangi agent)."""

import sqlite3

from nazorat.storage import inactive_sd_ids, unknown_active_agents


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE agents (sd_id TEXT PRIMARY KEY, name TEXT, active TEXT)")
    conn.execute("CREATE TABLE orders (agent_sd_id TEXT, date TEXT)")
    return conn


def test_inactive_detects_departed_agent():
    conn = _db()
    conn.executemany("INSERT INTO agents VALUES (?,?,?)", [
        ("d0_51", "Bahodir", "Y"),
        ("d0_152", "Eliza", "N"),      # ketgan
        ("d0_138", "Xikmatilla", "Y"),
    ])
    out = inactive_sd_ids(conn, ["d0_51", "d0_152", "d0_138"])
    assert out == {"d0_152"}


def test_inactive_empty_when_table_missing():
    conn = sqlite3.connect(":memory:")   # agents jadvali yo'q
    conn.row_factory = sqlite3.Row
    assert inactive_sd_ids(conn, ["d0_51"]) == set()   # xato bermaydi, hech kim chiqmaydi


def test_inactive_empty_ids():
    assert inactive_sd_ids(_db(), []) == set()


def test_unknown_active_finds_new_agent_excludes_sklad():
    conn = _db()
    conn.executemany("INSERT INTO agents VALUES (?,?,?)", [
        ("d0_51", "Bahodir", "Y"),                 # yaml'da bor
        ("d0_147", "Odilova Gulchehra (Sergeli)", "Y"),  # yangi, yaml'da yo'q
        ("d0_73", "Sklad Beshyag'och", "Y"),       # sklad — chiqariladi
        ("d0_9", "Eski agent", "N"),               # faol emas — hisobga olinmaydi
    ])
    conn.executemany("INSERT INTO orders VALUES (?,?)", [
        ("d0_51", "2026-07-10"), ("d0_147", "2026-07-15"),
        ("d0_73", "2026-07-15"), ("d0_9", "2026-07-15"),
    ])
    out = unknown_active_agents(conn, {"d0_51"}, "2026-07-01")
    ids = {a["sd_id"] for a in out}
    assert ids == {"d0_147"}          # faqat yangi haqiqiy agent
    assert out[0]["name"].startswith("Odilova")


def test_unknown_active_none_when_no_orders():
    conn = _db()
    conn.execute("INSERT INTO agents VALUES ('d0_147','Odilova (Sergeli)','Y')")
    # orders yo'q — savdo qilmagan yangi agent chiqmaydi
    assert unknown_active_agents(conn, set(), "2026-07-01") == []
