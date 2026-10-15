"""Kunduzgi GPS trevoga: build_last_map + find_missing testlari (sof funksiyalar)."""

from datetime import datetime
from types import SimpleNamespace

from nazorat.monitor import build_last_map, find_missing

AGENTS = [SimpleNamespace(sd_id="a1"), SimpleNamespace(sd_id="a2")]


def _v(agent="a1", start="2026-07-17 10:00:00", end="2026-07-17 10:05:00",
       shop="Chorsu market", visited="1"):
    return {"agent_id": agent, "start_date": start, "end_date": end,
            "client_name": shop, "visited": visited}


def test_last_map_takes_latest_visit():
    visits = [
        _v(start="2026-07-17 09:00:00", end="2026-07-17 09:05:00", shop="Birinchi"),
        _v(start="2026-07-17 12:40:00", end="2026-07-17 12:48:00", shop="Oxirgi do'kon"),
    ]
    m = build_last_map(visits, AGENTS)
    assert m["a1"]["total"] == 2
    assert m["a1"]["shop"] == "Oxirgi do'kon"
    assert m["a1"]["last"].strftime("%H:%M") == "12:48"
    assert m["a2"]["last"] is None


def test_find_missing_thresholds():
    visits = [_v(start="2026-07-17 12:40:00", end="2026-07-17 12:48:00")]
    m = build_last_map(visits, AGENTS)

    # 30 daqiqa o'tgan — hali trevoga emas
    assert find_missing(m, datetime(2026, 7, 17, 13, 18), 45, 90) == []
    # 52 daqiqa — sariq
    r = find_missing(m, datetime(2026, 7, 17, 13, 40), 45, 90)
    assert len(r) == 1 and r[0]["level"] == "yellow" and r[0]["mins"] == 52
    # 95 daqiqa — qizil
    r = find_missing(m, datetime(2026, 7, 17, 14, 23), 45, 90)
    assert r[0]["level"] == "red"
    # vizit qilmagan agent (a2) trevogaga tushmaydi
    assert all(x["sd_id"] == "a1" for x in r)


def test_find_missing_sorted_worst_first():
    visits = [
        _v(agent="a1", start="2026-07-17 12:00:00", end="2026-07-17 12:05:00"),
        _v(agent="a2", start="2026-07-17 13:00:00", end="2026-07-17 13:05:00"),
    ]
    m = build_last_map(visits, AGENTS)
    r = find_missing(m, datetime(2026, 7, 17, 14, 10), 45, 90)
    assert [x["sd_id"] for x in r] == ["a1", "a2"]   # eng uzoq yo'qolgan birinchi
