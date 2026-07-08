"""
forecast.py — "qayerga boradi / nima yo'qotyapti" dvigateli.
Prognoz + pul yo'qotish hisobi + BITTA eng foydali tavsiya.
"""

from dataclasses import dataclass

from .kpi import next_bonus_gap, plan_bonus
from .rules import Rules
from .toy import ToyStatus


@dataclass
class Projection:
    """Oy oxiriga prognoz."""
    ball_now: int
    ball_projected: float
    ball_plan: int
    sales_now: float
    sales_projected: float
    days_passed: int
    days_remaining: int

    @property
    def ball_gap(self) -> float:
        """Plandan farq (musbat = oshadi)."""
        return self.ball_projected - self.ball_plan

    @property
    def ball_per_day_needed(self) -> float:
        """Planga yetish uchun qolgan kunlarda kuniga kerak ball."""
        if self.days_remaining <= 0:
            return 0.0
        return max(self.ball_plan - self.ball_now, 0) / self.days_remaining


def project(
    ball_now: int, sales_now: float, ball_plan: int,
    days_passed: int, days_total: int,
) -> Projection:
    """Joriy o'rtacha temp bo'yicha oy oxiri prognozi."""
    days_remaining = days_total - days_passed
    if days_passed > 0:
        ball_proj = ball_now / days_passed * days_total
        sales_proj = sales_now / days_passed * days_total
    else:
        ball_proj = 0.0
        sales_proj = 0.0
    return Projection(
        ball_now=ball_now, ball_projected=ball_proj, ball_plan=ball_plan,
        sales_now=sales_now, sales_projected=sales_proj,
        days_passed=days_passed, days_remaining=days_remaining,
    )


@dataclass
class MoneyRisk:
    """Xavf ostidagi bitta pul."""
    kind: str          # 'toy' / 'kpi_bonus' / 'podium'
    amount: int        # qancha pul
    action: str        # nima qilish kerak (bitta gap, o'zbekcha)
    ease: float        # qanchalik oson erishiladi (kichik = oson)


def money_risks(
    proj: Projection,
    toy: ToyStatus,
    month_sales: float,
    sales_plan: float,
    rules: Rules,
    league: str,
) -> list[MoneyRisk]:
    """Har tizim bo'yicha 'shu tempda ketsa kuyadigan' pullarni yig'adi."""
    risks: list[MoneyRisk] = []
    days_left = max(proj.days_remaining, 1)

    # Happy Toy: keyingi darajaga yetmasa bonus kuyadi
    if toy.next_tier_blocks is not None and toy.blocks_to_next and toy.blocks_to_next > 0:
        per_day = toy.blocks_to_next / days_left
        risks.append(MoneyRisk(
            kind="toy",
            amount=toy.next_tier_bonus or 0,
            action=(
                f"Happy Toy soting — bonusgacha {toy.blocks_to_next:.0f} blok qoldi "
                f"(kuniga {per_day:.1f} blok soting)"
            ),
            ease=per_day,
        ))

    # KPI plan bonusi: keyingi pog'onaga yetishmayotgan summa
    gap = next_bonus_gap(month_sales, sales_plan, rules.kpi_plan_bonus[league])
    if gap is not None:
        need_sum, bonus = gap
        cur_bonus = plan_bonus(
            month_sales / sales_plan * 100 if sales_plan else 0,
            rules.kpi_plan_bonus[league],
        )
        extra = bonus - cur_bonus
        if extra > 0 and need_sum > 0:
            per_day = need_sum / days_left
            risks.append(MoneyRisk(
                kind="kpi_bonus",
                amount=extra,
                action=(
                    f"Reja pog'onasiga {need_sum:,.0f} so'm qoldi — kuniga "
                    f"{per_day:,.0f} so'm savdo qiling".replace(",", " ")
                ),
                ease=per_day / 1_000_000,   # mln birlikda solishtirish uchun
            ))

    # Podium: prognoz plandan past bo'lsa minimal sovrin xavf ostida
    if proj.ball_plan > 0 and proj.ball_gap < 0:
        risks.append(MoneyRisk(
            kind="podium",
            amount=min(rules.podium.prizes),
            action=(
                f"Reja balliga yetish uchun kuniga {proj.ball_per_day_needed:.1f} ball to'plang "
                f"(shu sur'atda: {proj.ball_projected:.0f}/{proj.ball_plan})"
            ),
            ease=proj.ball_per_day_needed,
        ))

    return risks


def best_action(risks: list[MoneyRisk]) -> MoneyRisk | None:
    """
    BITTA tavsiya: eng katta pul / eng oson erishiladigan nisbatga qarab.
    Ochko = amount / (1 + ease) — katta pul va oson harakat yutadi.
    """
    if not risks:
        return None
    return max(risks, key=lambda r: r.amount / (1 + max(r.ease, 0)))
