"""
O'RINDIQ ALMASHSA — ISM HAMMA JOYDA BIR XIL (2026-07-31 regressiyasi).

MUAMMO: hisobotlar (DayContext) `nz_agent_terms` ni qo'llardi va YANGI ismni
ko'rsatardi; Ulanish ekrani, GPS trevogalari va bot buyruqlari esa `roster` dan
to'g'ridan-to'g'ri olib, YAML'dagi ESKI ismni ko'rsatardi. Egasi ekranda
"Behruz"ni ko'rib, aslida Ibragimovaga ball plani qo'ygan.

QOIDA: bezash `roster._decorate` da — bir marta, hamma uchun.
"""

import sqlite3
from datetime import date

import pytest

from nazorat import binding, roster, storage
from nazorat.core.rules import Agent, AgentsConfig

NOW = "2026-07-31T10:00:00+05:00"


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    storage.init_nz_tables(c)
    c.execute(
        "INSERT INTO nz_agent_terms (sd_id, sd_name, short_name, start_date, "
        "observe_until, is_new, notified, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        ("d0_152", "Farangiz Qodirova", "Farangiz", "2026-07-27",
         "2026-08-31", 1, 1, NOW))
    yield c
    c.close()


def cfg_with_eliza():
    return AgentsConfig(agents=[
        Agent(sd_id="d0_152", name="Eliza Ismoilova", display="Eliza",
              area="Yangibozor+Parkent", league="city", code="TSH-YNB-02", ball_plan=60),
        Agent(sd_id="d0_51", name="Bahodir Toshev", display="Bahodir",
              area="Yunusobod", league="city", code="TSH-YNS-01", ball_plan=70),
    ])


def test_roster_returns_real_name(conn):
    agents = roster.active_agents(conn, cfg_with_eliza(), day=date(2026, 7, 31))
    by = {a.sd_id: a for a in agents}
    assert by["d0_152"].short == "Farangiz", "roster HAQIQIY ismni qaytarishi kerak"
    assert by["d0_51"].short == "Bahodir", "almashmagan o'rindiq tegilmasin"


def test_connection_list_shows_real_name(conn, monkeypatch):
    """Ulanish ekrani — egasi shu yerda eski ismni ko'rgan edi."""
    monkeypatch.setattr(binding, "load_agents", cfg_with_eliza)
    rows = {r["sd_id"]: r for r in binding.connection_list(conn) if r["sd_id"]}
    assert rows["d0_152"]["name"] == "Farangiz"
    assert rows["d0_152"]["area"] == "Yangibozor+Parkent", "xudud ham ko'rinsin"
    assert rows["d0_152"]["observe"] is False, "kuzatuv rejimi o'chirilgan"


def test_area_survives_seat_change(conn):
    """Xudud o'rindiqniki — agent almashsa ham o'zgarmaydi (egasi shundan taniydi)."""
    agents = roster.active_agents(conn, cfg_with_eliza(), day=date(2026, 7, 31))
    a = [x for x in agents if x.sd_id == "d0_152"][0]
    assert a.area == "Yangibozor+Parkent"


def test_start_date_applied(conn):
    """Yangi agent O'Z ish boshlagan kunidan sanaladi (eskisining savdosi aralashmaydi)."""
    agents = roster.active_agents(conn, cfg_with_eliza(), day=date(2026, 7, 31))
    a = [x for x in agents if x.sd_id == "d0_152"][0]
    assert a.start_date == "2026-07-27"


def test_seat_marker_keeps_previous_name(conn):
    """Ekranda «Farangiz · 🆕 27.07 dan · avval Eliza» chiqishi uchun kerak."""
    agents = roster.active_agents(conn, cfg_with_eliza(), day=date(2026, 7, 31))
    by = {a.sd_id: a for a in agents}
    assert by["d0_152"].seat_changed is True
    assert by["d0_152"].seat_prev_name == "Eliza"
    assert by["d0_51"].seat_changed is False, "almashmagan o'rindiqda belgi bo'lmasin"


def test_seat_marker_idempotent(conn):
    """Bezash bir necha marta qo'llansa ham «avval» maydoni BUZILMASIN.

    Tekshiruvsiz ikkinchi chaqiruvda seat_prev_name='Farangiz' bo'lib qolardi —
    ya'ni "avval Farangiz edi" degan bema'ni yozuv chiqardi."""
    cfg = cfg_with_eliza()
    roster.active_agents(conn, cfg, day=date(2026, 7, 31))
    roster.active_agents(conn, cfg, day=date(2026, 7, 31))
    roster.apply_terms(conn, cfg.agents, date(2026, 7, 31))
    a = [x for x in cfg.agents if x.sd_id == "d0_152"][0]
    assert a.seat_prev_name == "Eliza"
    assert a.short == "Farangiz"
