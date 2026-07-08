"""
kpi.py — KPI pul tizimi: tier komissiya + plan bonusi.
Komissiya butun oylik savdo summasiga qo'llanadi (pog'onali stavka emas).
"""

from .rules import CommissionStep, PlanBonusStep


def commission_pct(month_sales: float, steps: list[CommissionStep]) -> float:
    """Oylik savdo → komissiya foizi. Eng yuqori mos pog'ona olinadi."""
    best = 0.0
    for s in steps:
        if month_sales >= s.min_sales and s.pct > best:
            best = s.pct
    return best


def commission_amount(month_sales: float, steps: list[CommissionStep]) -> float:
    return month_sales * commission_pct(month_sales, steps) / 100


def plan_bonus(plan_pct: float, steps: list[PlanBonusStep]) -> int:
    """Plan bajarilishi (%) → bonus. Eng yuqori mos pog'ona."""
    best = 0
    for s in steps:
        if plan_pct >= s.min_pct and s.bonus > best:
            best = s.bonus
    return best


def next_bonus_gap(
    month_sales: float, sales_plan: float, steps: list[PlanBonusStep]
) -> tuple[float, int] | None:
    """
    Keyingi plan-bonus pog'onasiga yetish uchun qancha savdo kerak.
    Qaytadi: (yetishmayotgan so'm, o'sha pog'ona bonusi) yoki None (hammasi olingan).
    """
    if sales_plan <= 0:
        return None
    cur_pct = month_sales / sales_plan * 100
    future = [s for s in steps if s.min_pct > cur_pct]
    if not future:
        return None
    nxt = min(future, key=lambda s: s.min_pct)
    need = nxt.min_pct / 100 * sales_plan - month_sales
    return (max(need, 0.0), nxt.bonus)
