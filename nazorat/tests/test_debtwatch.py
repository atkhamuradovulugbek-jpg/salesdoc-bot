"""
QARZ NAZORATI testlari (2026-08-13).

Eng muhim regressiyalar:
  • limitdan oshgan agent YUQORIDA turadi (nazoratchi birinchi shuni ko'rsin);
  • ogohlantirish HAR AGENT UCHUN BIR MARTA — soatlik tekshiruvda takrorlanmaydi;
  • qarz tushib yana oshsa — yana bir marta xabar beriladi;
  • nazoratchi ulanmagan bo'lsa API'ga BORILMAYDI (bekorga yuk bo'lmasin);
  • agent/supervayzer rollariga TEGILMAYDI.
"""

import sqlite3
from datetime import date

import pytest

from nazorat import debtwatch, storage
from nazorat.core.rules import Agent

TODAY = date(2026, 8, 13)


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    storage.init_nz_tables(c)
    yield c
    c.close()


def row(sd_id, name, debt, limit, area="Xudud", league="city"):
    return {"sd_id": sd_id, "name": name, "area": area, "league": league,
            "debt": debt, "limit": limit, "pct": debt / limit * 100 if limit else 0,
            "over": debt > limit,
            "near": (not debt > limit) and debt >= limit * debtwatch.NEAR_FRAC}


NOW = "2026-08-13T12:00:00+05:00"


# ── ogohlantirish: bir marta ──

def test_first_crossing_alerts(conn):
    rows = [row("d0_51", "Bahodir", 4_000_000, 3_000_000)]
    fresh = debtwatch.newly_over(conn, rows, NOW)
    assert [r["sd_id"] for r in fresh] == ["d0_51"]


def test_second_check_does_not_repeat(conn):
    rows = [row("d0_51", "Bahodir", 4_000_000, 3_000_000)]
    debtwatch.newly_over(conn, rows, NOW)
    again = debtwatch.newly_over(conn, rows, NOW)
    assert again == [], "bir xil agent uchun xabar TAKRORLANMASLIGI kerak"


def test_normal_agent_never_alerts(conn):
    rows = [row("d0_60", "Jasmina", 500_000, 3_000_000)]
    assert debtwatch.newly_over(conn, rows, NOW) == []


def test_drop_then_cross_again_alerts(conn):
    """Qarz to'lanib tushsa, keyin yana oshsa — YANA xabar berilsin."""
    over = [row("d0_51", "Bahodir", 4_000_000, 3_000_000)]
    under = [row("d0_51", "Bahodir", 1_000_000, 3_000_000)]
    assert len(debtwatch.newly_over(conn, over, NOW)) == 1
    assert debtwatch.newly_over(conn, under, NOW) == []      # tushdi — xabar yo'q
    assert len(debtwatch.newly_over(conn, over, NOW)) == 1   # qayta oshdi — xabar bor


def test_exactly_at_limit_is_not_over(conn):
    """Aynan limitga teng — hali oshmagan (qat'iy > qoidasi)."""
    rows = [row("d0_51", "Bahodir", 3_000_000, 3_000_000)]
    assert rows[0]["over"] is False
    assert debtwatch.newly_over(conn, rows, NOW) == []


# ── karta ma'lumoti ──

def test_card_dict_shape():
    rows = [row("a", "A", 5_000_000, 3_000_000), row("b", "B", 100_000, 3_000_000)]
    d = debtwatch.card_dict(rows, "SHAHAR", "kechki", TODAY)
    assert d["title"] == "SHAHAR" and d["mode"] == "kechki"
    assert "13" in d["date_label"] and len(d["rows"]) == 2


def test_near_flag():
    assert row("a", "A", 2_800_000, 3_000_000)["near"] is True     # 93%
    assert row("b", "B", 2_600_000, 3_000_000)["near"] is False    # 87%
    assert row("c", "C", 4_000_000, 3_000_000)["near"] is False    # oshgan


# ── nazoratchi ulanmagan bo'lsa ──

def test_no_controller_means_no_chats(conn):
    assert debtwatch._controller_chats(conn) == []


def test_controller_found_after_binding(conn):
    storage.bind_code(conn, "QRZ-01", 12345, "debt", None, NOW)
    assert debtwatch._controller_chats(conn) == [12345]


def test_agent_binding_is_not_a_controller(conn):
    """Agent roli qarz nazoratchisi sifatida olinmasin."""
    storage.bind_code(conn, "TSH-YNB-01", 999, "agent", "d0_51", NOW)
    assert debtwatch._controller_chats(conn) == []


# ── ogohlantirish matni ──

def test_alert_text_has_key_facts():
    t = debtwatch.alert_text(row("d0_51", "Bahodir", 4_500_000, 3_000_000, "Yunusobod"))
    assert "Bahodir" in t and "Yunusobod" in t
    assert "4 500 000" in t and "3 000 000" in t
    assert "berilmasin" in t.lower()
