"""
O'RINDIQ ALMASHUVI ball plan ekranida (2026-07-31 regressiyasi).

MUAMMO: `agents.yaml` da d0_144 = "Behruz", lekin o'rindiqda agent ALMASHGAN
(`nz_agent_terms`: Ibragimova, 24-iyuldan, 31-avgustgacha kuzatuv). Hisobotlar
yangi ismni ko'rsatardi, ball plan ekrani esa ESKI ismni — egasi "Behruz"ga plan
qo'ydim deb, aslida boshqa odamga qo'ygan bo'lardi.
"""

import sqlite3
from datetime import date

import pytest

from nazorat import period, roster, storage
from nazorat.core.rules import Agent

NOW = "2026-07-31T10:00:00+05:00"


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    storage.init_nz_tables(c)
    c.execute(
        "INSERT INTO nz_agent_terms (sd_id, sd_name, short_name, start_date, "
        "observe_until, is_new, notified, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        ("d0_144", "Ibragimova Jumagul", "Ibragimova", "2026-07-24",
         "2026-08-31", 1, 1, NOW))
    yield c
    c.close()


def behruz():
    return Agent(sd_id="d0_144", name="Behruz Yo'ldoshev", display="Behruz",
                 league="city", code="X-144", ball_plan=0)


def test_seat_change_shows_real_name(conn):
    agents = [behruz()]
    roster.apply_terms(conn, agents, date(2026, 7, 31))
    assert agents[0].short == "Ibragimova", "ekran o'rindiqdagi HAQIQIY ismni ko'rsatishi kerak"
    assert agents[0].start_date == "2026-07-24"


def test_new_agent_is_not_put_in_observation(conn):
    """KUZATUV REJIMI O'CHIRILGAN (2026-08-06, egasi qarori).

    `observe_until` bazada TURIBDI, lekin o'qilmaydi — yangi agent ham birinchi
    kunidanoq ball planini ko'radi va sovrinda qatnashadi."""
    agents = [behruz()]
    roster.apply_terms(conn, agents, date(2026, 7, 31))   # observe_until=2026-08-31
    assert agents[0].observe_only is False, "yangi agent kuzatuvga OLINMASLIGI kerak"


def test_sheet_view_shows_new_agent_as_full(conn):
    """Ball plan ekrani: yangi agent ham TO'LIQ qatnashuvchi — kuzatuv yozuvi yo'q."""
    agents = [behruz()]
    roster.apply_terms(conn, agents, date(2026, 7, 31))
    row = period.sheet_view(conn, "2026-08", agents, date(2026, 7, 31))["rows"][0]
    assert row["name"] == "Ibragimova"
    assert row["observe"] is False
    assert row["observe_until"] is None


def test_name_stays_new_later(conn):
    """Vaqt o'tsa ham o'rindiqdagi ism yangicha qoladi."""
    agents = [behruz()]
    roster.apply_terms(conn, agents, date(2026, 9, 1))
    assert agents[0].short == "Ibragimova"


def test_publish_freezes_real_name(conn):
    agents = [behruz()]
    roster.apply_terms(conn, agents, date(2026, 7, 31))
    period.save_draft(conn, "2026-08", {"d0_144": 50}, True, "web", NOW)
    period.publish(conn, "2026-08", agents, "web", NOW)
    row = period.get_row(conn, "2026-08")
    import json
    payload = json.loads(row["payload"])
    assert payload["agents"][0]["name"] == "Ibragimova", \
        "muzlatilgan yozuvda HAQIQIY ism turishi kerak"
    assert payload["agents"][0]["ball_plan"] == 50
