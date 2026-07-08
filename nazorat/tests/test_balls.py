"""Ball shkalasi va vazvrat qayta hisobi testlari."""

from datetime import date

from nazorat.core.balls import ball_for_pct, daily_ball, month_balls, zero_streak
from nazorat.core.rules import load_rules

RULES = load_rules()
SCALE = RULES.ball_scale
PLAN = 2_000_000  # shahar kunlik reja


def test_scale_chegaralar():
    # Spec: 0-79% = 0, 80-89 = 1, 90-99 = 2, 100-149 = 3, 150+ = 4
    assert ball_for_pct(0, SCALE) == 0
    assert ball_for_pct(79.9, SCALE) == 0
    assert ball_for_pct(80, SCALE) == 1
    assert ball_for_pct(89.9, SCALE) == 1
    assert ball_for_pct(90, SCALE) == 2
    assert ball_for_pct(99.9, SCALE) == 2
    assert ball_for_pct(100, SCALE) == 3
    assert ball_for_pct(149.9, SCALE) == 3
    assert ball_for_pct(150, SCALE) == 4
    assert ball_for_pct(300, SCALE) == 4


def test_daily_ball_summa():
    assert daily_ball(2_450_000, PLAN, SCALE) == 3   # 122%
    assert daily_ball(1_500_000, PLAN, SCALE) == 0   # 75%
    assert daily_ball(0, PLAN, SCALE) == 0


def test_vazvrat_ballni_kamaytiradi():
    """Egasining misoli: 4 ball olgandi, 1 mln tovar qaytdi — ball kamayadi."""
    d = date(2026, 7, 7)
    wd = [d]
    # 3.1 mln savdo = 155% = 4 ball
    no_ret = month_balls({d: 3_100_000}, {}, PLAN, SCALE, wd, net_returns=True)
    assert no_ret[d] == 4
    # 1 mln vazvrat keldi: 2.1 mln = 105% = 3 ball
    with_ret = month_balls({d: 3_100_000}, {d: 1_000_000}, PLAN, SCALE, wd, net_returns=True)
    assert with_ret[d] == 3
    # brutto rejimida vazvrat ta'sir qilmaydi
    brutto = month_balls({d: 3_100_000}, {d: 1_000_000}, PLAN, SCALE, wd, net_returns=False)
    assert brutto[d] == 4


def test_savdosiz_ish_kuni_nol_ball():
    d1, d2 = date(2026, 7, 6), date(2026, 7, 7)
    balls = month_balls({d2: 2_000_000}, {}, PLAN, SCALE, [d1, d2])
    assert balls[d1] == 0 and balls[d2] == 3


def test_zero_streak():
    days = [date(2026, 7, d) for d in (3, 4, 6, 7)]   # 5-iyul yakshanba emas, shunchaki misol
    balls = {days[0]: 2, days[1]: 0, days[2]: 0, days[3]: 0}
    assert zero_streak(balls, days[3]) == 3
    balls[days[3]] = 1
    assert zero_streak(balls, days[3]) == 0
