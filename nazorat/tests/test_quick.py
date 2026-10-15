"""
«HOZIRGI HOLAT» yengil yangilash testlari (2026-08-11).

Eng muhim regressiyalar:
  • 90 soniya kutish ishlaydi (API'ga qayta borilmaydi);
  • kutish tugagach yana ruxsat beriladi;
  • `force=True` kutishni chetlab o'tadi (avtomatik 30 daqiqalik ish uchun);
  • hisobot vaqtida (blackout) yangilanmaydi;
  • xato bo'lsa CHAQIRUVCHI QULAMAYDI — (False, izoh) qaytadi.
"""

import asyncio
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from nazorat import quick

TZ = ZoneInfo("Asia/Tashkent")


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE sync_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, run_at TEXT, type TEXT,
        status TEXT, note TEXT)""")
    yield c
    c.close()


def add_sync(c, minutes_ago: float, typ="quick_manual_today", status="ok"):
    at = (datetime.now(TZ) - timedelta(minutes=minutes_ago)).isoformat(timespec="seconds")
    c.execute("INSERT INTO sync_log (run_at, type, status, note) VALUES (?,?,?,?)",
              (at, typ, status, ""))


# ── kutish (cooldown) ──

def test_no_history_allows_refresh(conn):
    assert quick.cooldown_left(conn) == 0


def test_recent_refresh_blocks(conn):
    add_sync(conn, minutes_ago=0.2)                  # 12 soniya oldin
    left = quick.cooldown_left(conn)
    assert 0 < left <= quick.COOLDOWN_SEC


def test_old_refresh_allows(conn):
    add_sync(conn, minutes_ago=5)
    assert quick.cooldown_left(conn) == 0


def test_only_successful_counts(conn):
    """Xato bilan tugagan urinish kutishni BOSHLAMASIN — aks holda xatodan keyin
    90 soniya qayta urinib bo'lmasdi."""
    add_sync(conn, minutes_ago=0.1, status="error")
    assert quick.cooldown_left(conn) == 0


def test_other_sync_types_do_not_block(conn):
    """To'liq/tez sync kutishni boshlamaydi — u boshqa maqsad uchun."""
    add_sync(conn, minutes_ago=0.1, typ="scheduled_full")
    assert quick.cooldown_left(conn) == 0


# ── "qachon yangilangan" matni ──

def test_age_text():
    assert quick.age_text(None) == "hali yangilanmagan"
    assert quick.age_text(40) == "40 soniya oldin"
    assert quick.age_text(120) == "2 daqiqa oldin"
    assert quick.age_text(7200) == "2 soat oldin"


def test_last_any_sync_takes_newest(conn):
    add_sync(conn, minutes_ago=60, typ="scheduled_full")
    add_sync(conn, minutes_ago=2, typ="quick_auto_today")
    age = quick.seconds_since(quick.last_any_sync(conn))
    assert 100 <= age <= 180, age


# ── refresh() xatti-harakati ──

def test_refresh_respects_cooldown(conn, monkeypatch):
    add_sync(conn, minutes_ago=0.2)
    monkeypatch.setattr(quick, "get_conn", lambda: _Ctx(conn))
    called = []
    monkeypatch.setattr("sync.run_sync", lambda *a, **k: called.append(1))
    ok, note = asyncio.run(quick.refresh("test"))
    assert ok is False and not called, "kutish ichida API'ga BORMASLIGI kerak"
    assert "oldin" in note


def test_force_skips_cooldown(conn, monkeypatch):
    """Avtomatik 30 daqiqalik ish force bilan ishlaydi."""
    add_sync(conn, minutes_ago=0.2)
    monkeypatch.setattr(quick, "get_conn", lambda: _Ctx(conn))
    monkeypatch.setattr(quick.taskq, "in_blackout", lambda *a, **k: False)

    async def fake_sync(*a, **k):
        return "ok"
    import sync as sync_mod
    monkeypatch.setattr(sync_mod, "run_sync", fake_sync)

    ok, note = asyncio.run(quick.refresh("auto", force=True))
    assert ok is True and note == "yangilandi"


def test_blackout_blocks(conn, monkeypatch):
    monkeypatch.setattr(quick, "get_conn", lambda: _Ctx(conn))
    monkeypatch.setattr(quick.taskq, "in_blackout", lambda *a, **k: True)
    ok, note = asyncio.run(quick.refresh("test", force=True))
    assert ok is False and note == "hisobot vaqti"


def test_busy_is_not_an_error(conn, monkeypatch):
    monkeypatch.setattr(quick, "get_conn", lambda: _Ctx(conn))
    monkeypatch.setattr(quick.taskq, "in_blackout", lambda *a, **k: False)

    async def busy(*a, **k):
        return "busy"
    import sync as sync_mod
    monkeypatch.setattr(sync_mod, "run_sync", busy)

    ok, note = asyncio.run(quick.refresh("test", force=True))
    assert ok is False and "yangilash" in note


def test_exception_does_not_propagate(conn, monkeypatch):
    """Yangilash qulasa ham chaqiruvchi (jadval ko'rsatish) DAVOM etishi kerak."""
    monkeypatch.setattr(quick, "get_conn", lambda: _Ctx(conn))
    monkeypatch.setattr(quick.taskq, "in_blackout", lambda *a, **k: False)

    async def boom(*a, **k):
        raise RuntimeError("tarmoq yo'q")
    import sync as sync_mod
    monkeypatch.setattr(sync_mod, "run_sync", boom)

    ok, note = asyncio.run(quick.refresh("test", force=True))
    assert ok is False and note.startswith("xato")


class _Ctx:
    """get_conn() o'rniga — test ulanishini qaytaradi, yopmaydi."""

    def __init__(self, c):
        self.c = c

    def __enter__(self):
        return self.c

    def __exit__(self, *a):
        return False
