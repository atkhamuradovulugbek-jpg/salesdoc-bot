"""
podium.py — oylik podium (liga bo'yicha alohida) va kunlik ball reytingi.
Podium: plandan OSHGAN ballar donasida. Teng bo'lsa savdo summasi hal qiladi.
"""

from dataclasses import dataclass, field

from .rules import PodiumRules


@dataclass
class PodiumEntry:
    sd_id: str
    name: str
    total_ball: int
    ball_plan: int
    month_net_sales: float          # tie-break uchun (sof savdo)
    observe_only: bool = False

    @property
    def over(self) -> int:
        return self.total_ball - self.ball_plan


@dataclass
class PodiumResult:
    # (o'rin, entry, sovrin) — faqat sovrin olganlar
    winners: list[tuple[int, PodiumEntry, int]] = field(default_factory=list)
    # to'liq reyting (sovrinsizlar ham), over bo'yicha kamayish tartibida
    ranking: list[PodiumEntry] = field(default_factory=list)


def rank_podium(
    entries: list[PodiumEntry],
    rules: PodiumRules,
    last_month_first_sd_id: str | None = None,
) -> PodiumResult:
    """
    Liga ichida podium. Qatnashish: over >= min_over va observe_only emas.
    no_repeat_first: o'tgan oy 1-o'rin egasi bu oy yana 1-bo'lsa, u 2-sovrin oladi,
    1-sovrin keyingi agentga o'tadi (agar bor bo'lsa).
    """
    real = [e for e in entries if not e.observe_only]
    ranking = sorted(real, key=lambda e: (-e.over, -e.month_net_sales))
    eligible = [e for e in ranking if e.over >= rules.min_over]

    winners: list[tuple[int, PodiumEntry, int]] = []
    order = eligible[: len(rules.prizes)]

    # Ketma-ket 2 oy 1-o'rin taqiqi
    if (
        rules.no_repeat_first
        and last_month_first_sd_id
        and order
        and order[0].sd_id == last_month_first_sd_id
        and len(eligible) > 1
    ):
        # 1-o'rinni keyingi agent oladi, avvalgi g'olib bir pog'ona pastga
        order = [eligible[1], eligible[0]] + eligible[2: len(rules.prizes)]

    for i, e in enumerate(order):
        winners.append((i + 1, e, rules.prizes[i]))

    return PodiumResult(winners=winners, ranking=ranking)


def daily_rating(day_entries: list[dict]) -> list[dict]:
    """
    Guruhga chiqadigan KUNLIK ball reytingi (yig'indisiz!).
    day_entries: [{sd_id, name, ball, sales}] — ball kamayish, teng bo'lsa summa hal.
    """
    return sorted(day_entries, key=lambda e: (-e["ball"], -e["sales"]))
