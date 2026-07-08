"""Podium ranjirlash testlari: teng ball, hech kim oshmagan, 2-oy taqiqi, kuzatuv rejimi."""

from nazorat.core.podium import PodiumEntry, daily_rating, rank_podium
from nazorat.core.rules import load_rules

PODIUM = load_rules().podium


def _e(sd, ball, plan, sales, observe=False):
    return PodiumEntry(sd_id=sd, name=sd, total_ball=ball, ball_plan=plan,
                       month_net_sales=sales, observe_only=observe)


def test_oddiy_podium():
    res = rank_podium([
        _e("a", 79, 70, 60e6),   # +9
        _e("b", 65, 60, 55e6),   # +5
        _e("c", 62, 60, 50e6),   # +2
        _e("d", 66, 70, 70e6),   # -4 — qatnashmaydi
    ], PODIUM)
    assert [(w[1].sd_id, w[0], w[2]) for w in res.winners] == [
        ("a", 1, 1_500_000), ("b", 2, 1_000_000), ("c", 3, 500_000)]


def test_teng_ball_summa_hal_qiladi():
    res = rank_podium([
        _e("kam_summa", 65, 60, 50e6),
        _e("kop_summa", 65, 60, 62e6),
    ], PODIUM)
    assert res.winners[0][1].sd_id == "kop_summa"


def test_hech_kim_oshmagan():
    res = rank_podium([_e("a", 60, 70, 50e6), _e("b", 55, 60, 40e6)], PODIUM)
    assert res.winners == []
    assert len(res.ranking) == 2   # reyting baribir bor


def test_ketma_ket_2_oy_taqiqi():
    entries = [_e("champion", 80, 70, 70e6), _e("second", 68, 60, 55e6)]
    res = rank_podium(entries, PODIUM, last_month_first_sd_id="champion")
    assert res.winners[0][1].sd_id == "second"       # 1-o'rin keyingisiga
    assert res.winners[1][1].sd_id == "champion"     # chempion 2-sovrin oladi


def test_kuzatuv_rejimi_sovrin_olmaydi():
    res = rank_podium([_e("yangi", 90, 0, 80e6, observe=True), _e("a", 65, 60, 50e6)], PODIUM)
    assert all(w[1].sd_id != "yangi" for w in res.winners)


def test_kunlik_reyting_teng_ballda_summa():
    rating = daily_rating([
        {"sd_id": "a", "name": "A", "ball": 3, "sales": 2_210_000},
        {"sd_id": "b", "name": "B", "ball": 3, "sales": 2_450_000},
        {"sd_id": "c", "name": "C", "ball": 4, "sales": 3_120_000},
    ])
    assert [r["sd_id"] for r in rating] == ["c", "b", "a"]
