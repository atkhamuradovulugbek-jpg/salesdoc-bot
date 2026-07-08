"""KPI komissiya, plan bonus, Toy darajalari va o'sish sovrini testlari."""

from nazorat.core.growth import GrowthEntry, growth_winner
from nazorat.core.kpi import commission_amount, commission_pct, next_bonus_gap, plan_bonus
from nazorat.core.rules import load_rules
from nazorat.core.toy import ToyLine, net_blocks, toy_status

RULES = load_rules()


# ---------- KPI komissiya (egasi tasdiqlagan pog'onalar) ----------

def test_komissiya_shahar():
    steps = RULES.kpi_commission["city"]
    assert commission_pct(19_000_000, steps) == 0
    assert commission_pct(25_000_000, steps) == 2
    assert commission_pct(35_000_000, steps) == 3
    assert commission_pct(45_000_000, steps) == 4
    assert commission_pct(50_000_000, steps) == 5
    assert commission_pct(65_000_000, steps) == 6
    assert commission_amount(50_000_000, steps) == 2_500_000


def test_komissiya_viloyat():
    steps = RULES.kpi_commission["region"]
    assert commission_pct(29_000_000, steps) == 0
    assert commission_pct(35_000_000, steps) == 3
    assert commission_pct(55_000_000, steps) == 4
    assert commission_pct(60_000_000, steps) == 5
    assert commission_pct(85_000_000, steps) == 6


def test_plan_bonus():
    city = RULES.kpi_plan_bonus["city"]
    assert plan_bonus(79, city) == 0
    assert plan_bonus(80, city) == 500_000
    assert plan_bonus(90, city) == 750_000
    assert plan_bonus(100, city) == 1_000_000
    region = RULES.kpi_plan_bonus["region"]
    assert plan_bonus(99, region) == 0
    assert plan_bonus(100, region) == 1_000_000


def test_next_bonus_gap():
    city = RULES.kpi_plan_bonus["city"]
    # 84% da (42 mln / 50 mln plan) keyingi pog'ona 90% = 45 mln → 3 mln kerak
    gap = next_bonus_gap(42_000_000, 50_000_000, city)
    assert gap is not None
    need, bonus = gap
    assert round(need) == 3_000_000
    assert bonus == 750_000
    # 100%+ da boshqa pog'ona yo'q
    assert next_bonus_gap(51_000_000, 50_000_000, city) is None


# ---------- Happy Toy ----------

def test_toy_status_darajalar():
    st = toy_status(78, RULES.toy)
    assert st.reached_bonus == 0
    assert st.next_tier_blocks == 105 and st.next_tier_bonus == 600_000
    assert st.blocks_to_next == 27
    st = toy_status(110, RULES.toy)
    assert st.reached_bonus == 600_000 and st.next_tier_blocks == 135
    st = toy_status(150, RULES.toy)
    assert st.reached_bonus == 1_200_000 and st.next_tier_blocks is None


def test_toy_vazvrat_ayiriladi():
    # 5 blok sotildi, 24 dona (=1 blok) qaytdi → sof 4 blok
    lines = [ToyLine(blocks=5, quantity=120, returned=24)]
    assert net_blocks(lines, RULES.toy) == 4


# ---------- O'sish sovrini ----------

def _g(sd, prev, cur, observe=False):
    return GrowthEntry(sd_id=sd, name=sd, prev_net_sales=prev, cur_net_sales=cur,
                       observe_only=observe)


def test_osish_golibi():
    w = growth_winner([
        _g("a", 50e6, 58e6),    # +16%
        _g("b", 40e6, 44e6),    # +10% — chegarada, qatnashadi
        _g("c", 60e6, 63e6),    # +5% — yetmaydi
    ], RULES.growth)
    assert w.sd_id == "a"


def test_osish_minimal_chegara():
    # Hech kim +10% ga yetmasa — g'olib yo'q
    assert growth_winner([_g("a", 50e6, 52e6)], RULES.growth) is None


def test_osish_ketma_ket_taqiq():
    w = growth_winner([_g("a", 50e6, 60e6), _g("b", 40e6, 45e6)],
                      RULES.growth, last_month_winner_sd_id="a")
    assert w.sd_id == "b"   # +12.5% — keyingi nomzod


def test_osish_yangi_agent_plansiz():
    # O'tgan oyi 0 — o'sish hisoblanmaydi (bo'linish xatosi ham yo'q)
    assert growth_winner([_g("yangi", 0, 30e6)], RULES.growth) is None
