"""
toy.py — Happy Toy aksiyasi hisobi.
Manba: order qatorlari (faqat toy SKU). Blok = qatordagi `block` maydoni.
Faqat yetkazilgan va QAYTMAGAN mahsulot sanaladi: returned dona blokka
aylantirilib ayiriladi.
"""

from dataclasses import dataclass

from .rules import ToyRules


@dataclass
class ToyLine:
    """Bitta order qatori (toy SKU bo'yicha)."""
    blocks: float          # order qatoridagi block
    quantity: float        # dona
    returned: float        # qaytgan dona


def net_blocks(lines: list[ToyLine], rules: ToyRules) -> float:
    """Oylik sof bloklar: sotilgan blok − qaytgan (dona → blok)."""
    total = 0.0
    for ln in lines:
        blocks = ln.blocks
        if ln.returned > 0 and rules.units_per_block > 0:
            blocks -= ln.returned / rules.units_per_block
        total += blocks
    return max(total, 0.0)


@dataclass
class ToyStatus:
    blocks: float
    reached_bonus: int          # hozirgacha kafolatlangan bonus (0 bo'lishi mumkin)
    next_tier_blocks: float | None   # keyingi daraja chegarasi
    next_tier_bonus: int | None
    blocks_to_next: float | None


def toy_status(blocks: float, rules: ToyRules) -> ToyStatus:
    """Bloklar soni → qaysi daraja olindi, keyingisiga qancha qoldi."""
    tiers = sorted(rules.tiers, key=lambda t: t.blocks)   # 105, 135, 150
    reached = 0
    nxt = None
    for t in tiers:
        if blocks >= t.blocks:
            reached = t.bonus
        elif nxt is None:
            nxt = t
    return ToyStatus(
        blocks=blocks,
        reached_bonus=reached,
        next_tier_blocks=nxt.blocks if nxt else None,
        next_tier_bonus=nxt.bonus if nxt else None,
        blocks_to_next=(nxt.blocks - blocks) if nxt else None,
    )
