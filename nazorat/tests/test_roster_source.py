"""
RO'YXAT YAGONA MANBASI (1-bosqich): roster.classify / active_agents.

Regressiya: 2026-07-18 da ro'yxat ikki joyda edi (YAML + `agents` jadvali) va ketgan
agent (Eliza d0_152) kechki jobni KeyError bilan qulatgan. Endi "kim bor"ni Sales
Doctor belgilaydi, YAML faqat bezaydi.
"""

import sqlite3

from nazorat import roster
from nazorat.core.rules import Agent, AgentsConfig


def _cfg(*rows) -> AgentsConfig:
    return AgentsConfig(agents=[
        Agent(sd_id=sd, name=nm, display=nm, league=lg, code=f"C-{sd}")
        for sd, nm, lg in rows
    ])


def _db(*rows) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE agents (sd_id TEXT PRIMARY KEY, name TEXT, active TEXT)")
    conn.executemany("INSERT INTO agents VALUES (?,?,?)", rows)
    return conn


CFG = _cfg(("d0_51", "Bahodir", "city"),
           ("d0_152", "Eliza", "region"),
           ("d0_99", "Aisha", "region"))


def test_departed_agent_excluded():
    """AYNAN 2026-07-18 holati: Eliza active='N' → ro'yxatdan chiqadi."""
    conn = _db(("d0_51", "Bahodir", "Y"), ("d0_152", "Eliza", "N"), ("d0_99", "Aisha", "Y"))
    active, departed, unknown = roster.classify(conn, CFG)
    assert [a.sd_id for a in active] == ["d0_51", "d0_99"]
    assert departed == {"d0_152"}
    assert unknown == set()


def test_unknown_sd_id_kept_but_flagged():
    """YAML'da bor, bazada YO'Q (masalan id xato yozilgan) — chiqarilmaydi, lekin belgilanadi."""
    conn = _db(("d0_51", "Bahodir", "Y"), ("d0_99", "Aisha", "Y"))
    active, departed, unknown = roster.classify(conn, CFG)
    assert "d0_152" in [a.sd_id for a in active]      # jimgina tashlab ketilmaydi
    assert unknown == {"d0_152"}
    assert departed == set()


def test_null_active_treated_as_active():
    conn = _db(("d0_51", "Bahodir", None), ("d0_152", "Eliza", "Y"), ("d0_99", "Aisha", "Y"))
    active, departed, _ = roster.classify(conn, CFG)
    assert len(active) == 3 and departed == set()


def test_no_agents_table_keeps_everyone():
    """Lokal/test rejimi: `agents` jadvali yo'q → hech kim chiqarilmaydi (xato ham yo'q)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    active, departed, unknown = roster.classify(conn, CFG)
    assert len(active) == 3
    assert departed == set() and unknown == set()


def test_all_departed_gives_empty_list_not_error():
    conn = _db(("d0_51", "B", "N"), ("d0_152", "E", "N"), ("d0_99", "A", "N"))
    active, departed, _ = roster.classify(conn, CFG)
    assert active == []
    assert len(departed) == 3


def test_active_agents_filters_by_league():
    conn = _db(("d0_51", "Bahodir", "Y"), ("d0_152", "Eliza", "N"), ("d0_99", "Aisha", "Y"))
    assert [a.sd_id for a in roster.active_agents(conn, CFG, league="city")] == ["d0_51"]
    assert [a.sd_id for a in roster.active_agents(conn, CFG, league="region")] == ["d0_99"]
    assert len(roster.active_agents(conn, CFG)) == 2       # ligasiz — hammasi


def test_empty_config_is_safe():
    conn = _db(("d0_51", "Bahodir", "Y"))
    active, departed, unknown = roster.classify(conn, _cfg())
    assert active == [] and departed == set() and unknown == set()


def test_yaml_decorates_display_and_league():
    """Sales Doctor "kim bor"ni beradi, YAML esa qisqa ism/liga/kodni (bezash)."""
    conn = _db(("d0_51", "Atxamuradov Bahodir Sales Doctor ismi", "Y"))
    active = roster.active_agents(conn, _cfg(("d0_51", "Bahodir", "city")))
    assert active[0].short == "Bahodir"        # YAML display'i ustun
    assert active[0].league == "city"
    assert active[0].code == "C-d0_51"
