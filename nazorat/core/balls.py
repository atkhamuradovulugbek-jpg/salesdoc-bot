"""
balls.py — kunlik va oylik ball hisobi.
Etalon: iyun 2026 — Bahodir 75, Rano 80, Usmonbek 19 (tests/test_etalon_june.py).
"""

from datetime import date

from .rules import BallStep


def ball_for_pct(pct: float, scale: list[BallStep]) -> int:
    """Kunlik reja bajarilishi (%) → ball. Shkala yuqoridan pastga tekshiriladi."""
    for step in sorted(scale, key=lambda s: -s.min_pct):
        if pct >= step.min_pct:
            return step.ball
    return 0


def daily_ball(net_sales: float, daily_plan: float, scale: list[BallStep]) -> int:
    """Bitta kun uchun ball. net_sales — vazvrat ayirilgan kun savdosi."""
    if daily_plan <= 0:
        return 0
    pct = net_sales / daily_plan * 100
    return ball_for_pct(pct, scale)


def month_balls(
    day_sales: dict[date, float],
    day_returns: dict[date, float],
    daily_plan: float,
    scale: list[BallStep],
    workdays: list[date],
    net_returns: bool = True,
) -> dict[date, int]:
    """
    Oy bo'yicha har ish kuni balli.
    day_sales — kun → brutto savdo; day_returns — kun → o'sha kun savdosiga
    tegishli vazvrat summasi (order sanasi bo'yicha).
    net_returns=True bo'lsa ball (savdo - vazvrat)dan hisoblanadi.
    Savdo bo'lmagan ish kuni ham 0 ball bilan qaytadi (o'lik kun detektori uchun).
    """
    result: dict[date, int] = {}
    for d in workdays:
        sales = day_sales.get(d, 0.0)
        if net_returns:
            sales -= day_returns.get(d, 0.0)
        result[d] = daily_ball(max(sales, 0.0), daily_plan, scale)
    return result


def total_balls(balls: dict[date, int]) -> int:
    return sum(balls.values())


def zero_streak(balls: dict[date, int], upto: date) -> int:
    """upto kunigacha (shu kun bilan) ketma-ket 0 ball kunlar soni (faqat ish kunlari)."""
    streak = 0
    for d in sorted(balls.keys(), reverse=True):
        if d > upto:
            continue
        if balls[d] == 0:
            streak += 1
        else:
            break
    return streak
