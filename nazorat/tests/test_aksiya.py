"""
«300 000 AKSIYA» hisobi testlari (2026-10-06).

Topshiriqdagi tekshiruv jadvali + egasi tasdiqlagan qoidalar:
  • har buyurtma ALOHIDA (ikki buyurtma qo'shilmaydi);
  • faqat yetkazilgan (status 3);
  • VAZVRAT AYIRILADI (2026-10-06 qarori);
  • stavka ANIQ kasr (100000/15) — tiyin yo'qolmaydi.
"""

import pytest

from nazorat import aksiya

cfg = aksiya.load_config()


# ── 1. Bitta buyurtma → aksiya ──

@pytest.mark.parametrize("summa,kutilgan", [
    (0, 0), (299_999, 0), (290_000, 0),
    (300_000, 1), (590_000, 1),
    (600_000, 2), (900_000, 3),
    (1_000_000, 3), (3_000_000, 10),
])
def test_units_for_order(summa, kutilgan):
    assert aksiya.units_for_order(summa, cfg) == kutilgan


def test_negative_sum_is_zero():
    assert aksiya.units_for_order(-500_000, cfg) == 0


# ── 2. Kunlik bonus — topshiriqdagi jadval ──

@pytest.mark.parametrize("n,shahar,viloyat", [
    (9,       0,       0),
    (10,  50_000,      0),
    (12,  60_000,      0),
    (14,  70_000,      0),
    (15, 100_000, 80_000),
    (16, 106_667, 85_333),
    (18, 120_000, 96_000),
    (20, 133_333, 106_667),
    (25, 166_667, 133_333),
])
def test_daily_bonus(n, shahar, viloyat):
    assert aksiya.daily_bonus(n, "shahar", cfg) == shahar
    assert aksiya.daily_bonus(n, "viloyat", cfg) == viloyat


def test_exact_fraction_no_drift():
    """100000/15 ni o'nlik kasr qilib yozsak 15 ta aksiyada 100 000 chiqmasdi."""
    assert aksiya.daily_bonus(15, "shahar", cfg) == 100_000
    assert aksiya.daily_bonus(30, "shahar", cfg) == 200_000
    assert aksiya.daily_bonus(45, "shahar", cfg) == 300_000


def test_zero_units():
    assert aksiya.daily_bonus(0, "shahar", cfg) == 0
    assert aksiya.daily_bonus(0, "viloyat", cfg) == 0


# ── 3. Liga (zaxira yo'l — ism qavsidan) ──

@pytest.mark.parametrize("ism,kutilgan", [
    ("Jalolov Bahodir (Yunusobod)", "shahar"),
    ("Abdulaziz Abdusattarov (Olmazor)", "shahar"),
    ("Mamatov Arthur (Mirobod-Yakkasaroy)", "shahar"),
    ("Rashidova Rano (Chinoz+Oqqurg'on+Quyi Chirchiq)", "viloyat"),
    ("Sofiya Mirsoatova (Angren)", "viloyat"),
    ("Sklad Beshyag'och", None),
    ("", None),
    ("Noma'lum Odam", None),
])
def test_league_for_agent(ism, kutilgan):
    assert aksiya.league_for_agent(ism, cfg) == kutilgan


# ── 4. Eshik va keyingi pog'ona (shaxsiy xabar uchun) ──

def test_to_threshold():
    assert aksiya.to_threshold(8, "shahar", cfg) == 2
    assert aksiya.to_threshold(10, "shahar", cfg) == 0
    assert aksiya.to_threshold(12, "viloyat", cfg) == 3


def test_next_tier_gain():
    assert aksiya.next_tier_gain(12, "shahar", cfg) == (3, 100_000)
    assert aksiya.next_tier_gain(20, "shahar", cfg) is None   # eng yuqori pog'ona
    assert aksiya.next_tier_gain(9, "viloyat", cfg) == (6, 80_000)


# ── 5. compute_day ──

def order(oid, client, agent, summa, status=3, lines=None, ret=0, day="2026-10-06"):
    return dict(order_id=oid, order_date=day, client=client, agent=agent,
                status=status, total_sum=summa, returns=ret, lines=lines or [])


BAHODIR = "Jalolov Bahodir (Yunusobod)"


def test_compute_day_basic():
    """Topshiriqdagi misol: 590k + 300k = 2 aksiya; yetkazilmagan hisoblanmaydi."""
    orders = [
        order(1, "A", BAHODIR, 590_000),
        order(2, "A", BAHODIR, 300_000),
        order(3, "B", BAHODIR, 900_000, status=1),      # Yangi — hisoblanmaydi
    ]
    r = aksiya.compute_day(orders, "2026-10-06", cfg)
    assert r[BAHODIR]["units"] == 2
    assert r[BAHODIR]["orders_count"] == 2
    assert r[BAHODIR]["league"] == "shahar"


def test_two_small_orders_do_not_merge():
    """ENG MUHIM QOIDA: 200k + 200k = 400k, lekin 0 aksiya."""
    orders = [order(1, "A", BAHODIR, 200_000), order(2, "A", BAHODIR, 200_000)]
    r = aksiya.compute_day(orders, "2026-10-06", cfg)
    assert r[BAHODIR]["units"] == 0


def test_returns_reduce_units():
    """Egasi qarori: 300 olib 60 qaytardi → 240 → 0 aksiya."""
    orders = [order(1, "A", BAHODIR, 300_000, ret=60_000)]
    r = aksiya.compute_day(orders, "2026-10-06", cfg)
    assert r[BAHODIR]["units"] == 0


def test_priced_gift_line_excluded():
    """Sovg'a narx bilan kiritilgan bo'lsa summadan chiqariladi."""
    lines = [{"product_name": "Makaron 400g", "summa": 50_000}]
    orders = [order(1, "A", BAHODIR, 330_000, lines=lines)]
    r = aksiya.compute_day(orders, "2026-10-06", cfg)
    assert r[BAHODIR]["units"] == 0        # 330k - 50k = 280k


def test_free_gift_does_not_change_sum():
    lines = [{"product_name": "Jele", "summa": 0}]
    orders = [order(1, "A", BAHODIR, 300_000, lines=lines)]
    r = aksiya.compute_day(orders, "2026-10-06", cfg)
    assert r[BAHODIR]["units"] == 1


def test_excluded_agent_skipped():
    orders = [order(1, "A", "Sklad Beshyag'och", 3_000_000)]
    assert aksiya.compute_day(orders, "2026-10-06", cfg) == {}


def test_other_day_skipped():
    orders = [order(1, "A", BAHODIR, 600_000, day="2026-10-05")]
    assert aksiya.compute_day(orders, "2026-10-06", cfg) == {}


def test_bonus_attached():
    orders = [order(i, f"D{i}", BAHODIR, 300_000) for i in range(12)]
    r = aksiya.compute_day(orders, "2026-10-06", cfg)
    assert r[BAHODIR]["units"] == 12
    assert r[BAHODIR]["bonus"] == 60_000
    assert r[BAHODIR]["fire"] is False


def test_fire_flag_city_at_15():
    orders = [order(i, f"D{i}", BAHODIR, 300_000) for i in range(15)]
    r = aksiya.compute_day(orders, "2026-10-06", cfg)
    assert r[BAHODIR]["fire"] is True
    assert r[BAHODIR]["bonus"] == 100_000


# ── 6. Nazorat ro'yxati belgilari ──

def test_big_order_flagged():
    orders = [order(1, "Katta do'kon", BAHODIR, 2_000_000)]
    r = aksiya.compute_day(orders, "2026-10-06", cfg)
    assert len(r[BAHODIR]["big_orders"]) == 1
    assert r[BAHODIR]["big_orders"][0]["client"] == "Katta do'kon"


def test_multi_order_same_client_flagged():
    orders = [order(1, "A", BAHODIR, 400_000), order(2, "A", BAHODIR, 500_000)]
    r = aksiya.compute_day(orders, "2026-10-06", cfg)
    assert len(r[BAHODIR]["multi_orders"]) == 1
    assert r[BAHODIR]["multi_orders"][0]["client"] == "A"


def test_no_gift_flagged_only_for_300k_plus():
    orders = [
        order(1, "A", BAHODIR, 400_000),                                   # sovg'asiz
        order(2, "B", BAHODIR, 400_000, lines=[{"product_name": "Jele", "summa": 0}]),
        order(3, "C", BAHODIR, 100_000),                                   # 300k dan kam
    ]
    r = aksiya.compute_day(orders, "2026-10-06", cfg)
    flagged = [x["client"] for x in r[BAHODIR]["no_gift_orders"]]
    assert flagged == ["A"]


# ── 7. Liga yig'indisi ──

def test_league_totals():
    RANO = "Rashidova Rano (Chinoz+Oqqurg'on+Quyi Chirchiq)"
    orders = ([order(i, f"D{i}", BAHODIR, 300_000) for i in range(10)] +
              [order(100 + i, f"E{i}", RANO, 300_000) for i in range(15)])
    r = aksiya.compute_day(orders, "2026-10-06", cfg)
    sh = aksiya.league_totals(r, "shahar")
    vl = aksiya.league_totals(r, "viloyat")
    assert sh == {"agents": 1, "units": 10, "bonus": 50_000, "passed": 1, "fire": 0}
    assert vl == {"agents": 1, "units": 15, "bonus": 80_000, "passed": 1, "fire": 0}


# ── 8. Format ──

def test_fmt_sum():
    assert aksiya.fmt_sum(150_000) == "150 000"
    assert aksiya.fmt_sum(1_500_000) == "1 500 000"
    assert aksiya.fmt_sum(0) == "0"
