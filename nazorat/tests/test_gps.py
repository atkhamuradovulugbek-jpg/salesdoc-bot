"""GPS kunlik xulosa: analyze_visits + severity testlari (sof funksiyalar)."""

from types import SimpleNamespace

from nazorat.gps import analyze_visits, severity


def _v(agent="a1", start="2026-07-17 09:00:00", end="2026-07-17 09:05:00",
       gps="1", visited="1"):
    return {"agent_id": agent, "start_date": start, "end_date": end,
            "gps_visit": gps, "visited": visited}


AGENTS = [SimpleNamespace(sd_id="a1"), SimpleNamespace(sd_id="a2")]


def test_analyze_counts_first_last_fake_fast():
    visits = [
        _v(start="2026-07-17 09:10:00", end="2026-07-17 09:15:00"),            # normal
        _v(start="2026-07-17 12:00:00", end="2026-07-17 12:00:30"),            # tez (<60s)
        _v(start="2026-07-17 16:40:00", end="2026-07-17 16:50:00", gps="0"),   # soxta
        _v(agent="boshqa"),                                                     # ro'yxatda yo'q
        _v(visited="0"),                                                        # bo'lmagan vizit
    ]
    s = analyze_visits(visits, AGENTS)["a1"]
    assert s["total"] == 3
    assert s["fast"] == 1
    assert s["fake"] == 1
    assert s["first"].strftime("%H:%M") == "09:10"
    assert s["last"].strftime("%H:%M") == "16:50"
    # a2 hech narsa qilmagan
    assert analyze_visits(visits, AGENTS)["a2"]["total"] == 0


def test_severity_zero_is_red():
    assert severity({"total": 0, "fake": 0, "fast": 0, "first": None, "last": None}) == "red"


def test_severity_heavy_fast_is_red():
    visits = [_v(start=f"2026-07-17 10:{i:02d}:00", end=f"2026-07-17 10:{i:02d}:20")
              for i in range(10)]                       # 10 ta tez vizit
    visits.append(_v(start="2026-07-17 16:00:00", end="2026-07-17 16:10:00"))
    s = analyze_visits(visits, AGENTS)["a1"]
    assert severity(s) == "red"


def test_severity_good_day_is_ok():
    visits = [_v(start=f"2026-07-17 {h:02d}:00:00", end=f"2026-07-17 {h:02d}:10:00")
              for h in range(9, 17)]                    # 09:00–16:10, 8 ta normal vizit
    s = analyze_visits(visits, AGENTS)["a1"]
    assert severity(s) == "ok"


def test_severity_early_end_is_red():
    visits = [_v(start="2026-07-17 09:00:00", end="2026-07-17 09:10:00"),
              _v(start="2026-07-17 12:30:00", end="2026-07-17 12:40:00")]
    visits += [_v(start=f"2026-07-17 11:{i:02d}:00", end=f"2026-07-17 11:{i:02d}:00".replace("00:", "0"))
               for i in range(0, 0)]  # (bo'sh — faqat 2 vizit)
    s = analyze_visits(visits, AGENTS)["a1"]
    assert s["last"].strftime("%H:%M") == "12:40"
    assert severity(s) == "red"      # oxirgi vizit 13:30 dan oldin
