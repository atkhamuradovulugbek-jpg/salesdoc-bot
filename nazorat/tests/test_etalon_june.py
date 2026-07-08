"""
MAJBURIY ETALON TEST — iyun 2026 real natijalari.
Fixture jonli API'dan olingan (tests/fixtures/june_2026.json).
Bu test o'tmasa — hisob mantig'i yoki data_map NOTO'G'RI.

Etalon (egasi bergan):
  Jalolov Bahodir  (d0_51):  70 656 600 so'm savdo = 75 ball
  Rashidova Rano   (d0_89):  ~100.2 mln = 80 ball
  Usmonbek         (d0_140): ~40.75 mln = 19 ball

Eslatma: iyun ballari BRUTTO hisoblangan (vazvrat qoidasi iyuldan kiritildi),
shuning uchun testda net_returns=False.
"""

import json
from datetime import date
from pathlib import Path

import pytest

from nazorat.core.balls import month_balls, total_balls
from nazorat.core.rules import load_rules
from nazorat.core.workdays import month_workdays

FIXTURE = Path(__file__).parent / "fixtures" / "june_2026.json"


@pytest.fixture(scope="module")
def june_data():
    return json.loads(FIXTURE.read_text())


@pytest.fixture(scope="module")
def rules():
    return load_rules()


def _month_ball(june_data, rules, sd_id: str, league: str) -> tuple[int, float]:
    rec = june_data[sd_id]
    day_sales = {date.fromisoformat(k): v for k, v in rec["day_sales"].items()}
    day_returns = {date.fromisoformat(k): v for k, v in rec["day_returns"].items()}
    wd = month_workdays(2026, 6, rules.sunday_off)
    balls = month_balls(
        day_sales, day_returns,
        daily_plan=rules.daily_plan[league],
        scale=rules.ball_scale,
        workdays=wd,
        net_returns=False,   # iyun etaloni brutto
    )
    return total_balls(balls), sum(day_sales.values())


def test_june_workdays_26(rules):
    assert len(month_workdays(2026, 6, rules.sunday_off)) == 26


def test_bahodir_75_ball(june_data, rules):
    ball, sales = _month_ball(june_data, rules, "d0_51", "city")
    assert round(sales) == 70_656_600
    assert ball == 75


def test_rano_80_ball(june_data, rules):
    ball, sales = _month_ball(june_data, rules, "d0_89", "region")
    assert 100_000_000 < sales < 101_000_000
    assert ball == 80


def test_usmonbek_19_ball(june_data, rules):
    ball, sales = _month_ball(june_data, rules, "d0_140", "region")
    assert 40_500_000 < sales < 41_000_000
    assert ball == 19
