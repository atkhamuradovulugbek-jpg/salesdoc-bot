"""
growth.py — "Eng zo'r o'sish" sovrini (liga bo'yicha).
O'tgan oyga nisbatan SOF savdo (vazvrat ayirilgan) foiz o'sishi eng katta agent.
"""

from dataclasses import dataclass

from .rules import GrowthRules


@dataclass
class GrowthEntry:
    sd_id: str
    name: str
    prev_net_sales: float
    cur_net_sales: float
    observe_only: bool = False

    @property
    def growth_pct(self) -> float | None:
        """O'tgan oy 0 bo'lsa o'sish hisoblanmaydi (yangi agent)."""
        if self.prev_net_sales <= 0:
            return None
        return (self.cur_net_sales - self.prev_net_sales) / self.prev_net_sales * 100


def growth_winner(
    entries: list[GrowthEntry],
    rules: GrowthRules,
    last_month_winner_sd_id: str | None = None,
) -> GrowthEntry | None:
    """G'olib: eng katta o'sish, kamida min_pct, ketma-ket 2 oy emas."""
    candidates = [
        e for e in entries
        if not e.observe_only
        and e.growth_pct is not None
        and e.growth_pct >= rules.min_pct
        and not (rules.no_repeat and e.sd_id == last_month_winner_sd_id)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda e: e.growth_pct)
