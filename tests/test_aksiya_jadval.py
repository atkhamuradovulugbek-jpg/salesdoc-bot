"""
SalesDoc Monitor — AKSIYA umumiy jadvali testlari.

Tarmoq yo'q: haqiqiy .env o'qilmaydi, socket ulanishi bloklangan, Telegram
o'rniga soxta bot. Baza — vaqtinchalik SQLite.
"""

import asyncio
import os
import socket
import sys
import tempfile
from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import dotenv  # noqa: E402

dotenv.load_dotenv = lambda *a, **k: False  # haqiqiy .env o'qilmasin
os.environ.update({
    "TELEGRAM_BOT_TOKEN": "test-token",
    "SALESDOC_BASE_URL": "http://salesdoc.invalid",
    "SALESDOC_LOGIN": "test",
    "SALESDOC_PASSWORD": "test",
    "ADMIN_TELEGRAM_IDS": "",
    "ALLOWED_TELEGRAM_IDS": "",
    "DATA_DIR": tempfile.mkdtemp(prefix="aksiya-test-"),
})

import pytest  # noqa: E402
from PIL import Image  # noqa: E402

import aksiya_jadval as aj  # noqa: E402
import bot  # noqa: E402
import db  # noqa: E402
from image_reports import _ball_for_pct  # noqa: E402

CITY_A = "Jalolov Bahodir (Yunusobod)"
CITY_B = "Saodat Hakimova (Uchtepa)"
REGION_A = "Farangiz Jo'rayeva (Yangibozor +Parkent)"
FORMER = "Sherzod Sobiq (Yunusobod)"

D8 = date(2026, 10, 8)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def _blocked(*a, **k):
        raise RuntimeError("testda tarmoq taqiqlangan")
    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


@pytest.fixture
def tmpdb(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "bot.db")
    db.init_db()
    with db.get_conn() as conn:
        conn.executemany(
            "INSERT INTO agents (sd_id, code_1c, name, active, updated_at) VALUES (?,?,?,?,?)",
            [
                ("c1", "", CITY_A, "Y", ""),
                ("c2", "", CITY_B, "Y", ""),
                ("r1", "", REGION_A, "Y", ""),
                ("x9", "", FORMER, "N", ""),
            ],
        )
    return tmp_path


def upsert(*orders):
    """sync.py dagi bilan bir xil upsert (sd_id bo'yicha)."""
    with db.get_conn() as conn:
        conn.executemany("""
            INSERT INTO orders (sd_id, date, status, agent_sd_id, client_sd_id,
                                total_after_discount, total_returns)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sd_id) DO UPDATE SET
                date=excluded.date, status=excluded.status,
                agent_sd_id=excluded.agent_sd_id, client_sd_id=excluded.client_sd_id,
                total_after_discount=excluded.total_after_discount,
                total_returns=excluded.total_returns
        """, orders)


def o(oid, total, shop="s1", day="2026-10-08", status=1, agent="c1", ret=0):
    return {"id": oid, "agent": agent, "shop": shop, "day": day,
            "status": status, "total": total, "returns": ret}


def by_name(items):
    return {it["name"]: it for it in items}


# ── Do'kon-kun bloklari ──────────────────────────────────────────

def test_split_order_150_150_is_one():
    assert aj.agent_units([o(1, 150_000), o(2, 150_000)]) == {"c1": 1}


def test_400_300_200_is_three():
    assert aj.agent_units([o(1, 400_000), o(2, 300_000), o(3, 200_000)]) == {"c1": 3}


@pytest.mark.parametrize("net,units", [
    (299_999, 0), (300_000, 1), (599_999, 1), (600_000, 2), (0, 0), (-50_000, 0),
])
def test_300000_boundary(net, units):
    assert aj.units_for_shop_day(net) == units


def test_float_noise_does_not_lose_block():
    assert aj.agent_units([o(1, 100_000.1), o(2, 199_999.9)]) == {"c1": 1}


def test_different_shops_not_pooled():
    assert aj.agent_units([o(1, 150_000, shop="s1"), o(2, 150_000, shop="s2")]) == {"c1": 0}


def test_different_days_not_pooled_no_carry():
    orders = [o(1, 200_000, day="2026-10-08"), o(2, 200_000, day="2026-10-09")]
    assert aj.agent_units(orders) == {"c1": 0}


def test_unknown_shop_orders_not_pooled():
    assert aj.agent_units([o(1, 150_000, shop=None), o(2, 150_000, shop=None)]) == {"c1": 0}


def test_return_900_minus_300_is_two():
    assert aj.agent_units([o(1, 900_000, ret=300_000)]) == {"c1": 2}


def test_return_applied_before_pooling():
    # 400k + (300k − 200k qaytim) = 500k → 1 (har buyurtmani alohida emas)
    assert aj.agent_units([o(1, 400_000), o(2, 300_000, ret=200_000)]) == {"c1": 1}


def test_negative_shop_day_is_zero():
    assert aj.agent_units([o(1, 100_000, ret=400_000), o(2, 200_000)]) == {"c1": 0}


def test_same_order_id_counted_once():
    assert aj.agent_units([o(1, 300_000, status=1), o(1, 300_000, status=3)]) == {"c1": 1}


@pytest.mark.parametrize("status", [4, 0, 5, None])
def test_canceled_and_full_return_excluded(status):
    assert aj.agent_units([o(1, 300_000), o(2, 900_000, status=status)]) == {"c1": 1}


def test_agent_total_is_sum_of_blocks():
    orders = [o(1, 350_000, shop="s1"), o(2, 350_000, shop="s2"), o(3, 250_000, shop="s3")]
    assert aj.agent_units(orders) == {"c1": 2}  # 1 + 1 + 0, umumiy 950k→3 EMAS


# ── Mukofot ──────────────────────────────────────────────────────

@pytest.mark.parametrize("n,expected", [
    (0, 0), (9, 0), (10, 50_000), (14, 70_000), (15, 100_000), (16, 106_667), (30, 200_000),
])
def test_city_tiers(n, expected):
    assert aj.reward(n, "city") == expected


@pytest.mark.parametrize("n,expected", [
    (0, 0), (9, 0), (10, 40_000), (11, 44_000), (13, 52_000), (14, 56_000),
    (15, 80_000), (16, 85_333), (30, 160_000),
])
def test_region_tiers(n, expected):
    assert aj.reward(n, "region") == expected


def test_final_rounding_once():
    assert aj.reward(16, "region") != 16 * 5333  # oldin yaxlitlab ko'paytirish = 85 328
    assert aj.reward(25, "city") == 166_667
    assert isinstance(aj.reward(16, "region"), int)


# ── Baza orqali (sync bilan bir xil jadval) ──────────────────────

def test_status_change_not_double_counted(tmpdb):
    for st in (1, 2, 3):  # NEW → SHIPPED → DELIVERED, bir xil sd_id
        upsert(("o1", "2026-10-08", st, "c1", "s1", 300_000, 0))
    it = by_name(aj.compute_items("city", D8))[CITY_A]
    assert (it["units"], it["sales"]) == (1, 300_000)


def test_next_day_return_reduces_original_day(tmpdb):
    upsert(("o1", "2026-10-08", 2, "c1", "s1", 900_000, 0))
    # ertasi kuni qaytim — sync shu buyurtmani asl sanasi bilan yangilaydi
    upsert(("o1", "2026-10-08", 3, "c1", "s1", 900_000, 300_000))
    upsert(("o2", "2026-10-09", 1, "c1", "s9", 100_000, 0))
    d8 = by_name(aj.compute_items("city", D8))[CITY_A]
    d9 = by_name(aj.compute_items("city", date(2026, 10, 9)))[CITY_A]
    assert (d8["units"], d8["sales"]) == (2, 600_000)
    assert (d9["units"], d9["sales"]) == (0, 100_000)


def test_db_canceled_excluded_and_other_day_ignored(tmpdb):
    upsert(
        ("o1", "2026-10-08", 1, "c1", "s1", 300_000, 0),
        ("o2", "2026-10-08", 4, "c1", "s1", 900_000, 0),
        ("o3", "2026-10-08", 5, "c1", "s1", 900_000, 0),
        ("o4", "2026-10-07", 3, "c1", "s1", 900_000, 0),
    )
    it = by_name(aj.compute_items("city", D8))[CITY_A]
    assert (it["units"], it["sales"]) == (1, 300_000)


def test_active_agents_only_and_league_split(tmpdb):
    upsert(("o1", "2026-10-08", 1, "x9", "s1", 3_000_000, 0))  # sobiq agent
    city = aj.compute_items("city", D8)
    region = aj.compute_items("region", D8)
    assert {it["name"] for it in city} == {CITY_A, CITY_B}
    assert {it["name"] for it in region} == {REGION_A}


def test_sorted_by_sales_and_color_from_sales_not_reward(tmpdb):
    upsert(
        # A: 3.1M, 31 ta do'konda 100k dan → 0 aksiya, 0 so'm, lekin 155% → apelsin
        *[(f"a{i}", "2026-10-08", 1, "c1", f"s{i}", 100_000, 0) for i in range(31)],
        # B: 1.7M bitta do'konda → 5 aksiya, 0 so'm, 85% → sariq
        ("b1", "2026-10-08", 1, "c2", "t1", 1_700_000, 0),
    )
    items = aj.compute_items("city", D8)
    assert [it["name"] for it in items] == [CITY_A, CITY_B]
    a, b = items
    assert (a["units"], a["bonus"]) == (0, 0)
    assert a["bg"] == _ball_for_pct(155)[2] != _ball_for_pct(0)[2]
    assert (b["units"], b["bonus"]) == (5, 0)
    assert b["bg"] == _ball_for_pct(85)[2]


# ── Rasm ─────────────────────────────────────────────────────────

LONG_NAME = ("Rashidova Rano (Chinoz+Oqqurg'on+Quyi Chirchiq) Bo'stonliq "
             "Keles Yangiyo'l Parkent Qibray Angren Olmaliq Chirchiq")


@pytest.mark.parametrize("name", [CITY_A, REGION_A, LONG_NAME, "Buranbayeva Yulduz  (Yangiyo'l)"])
def test_full_name_never_truncated(name):
    max_w = aj.COLS[1] - 2 * aj.NAME_PAD
    f, lines = aj._fit_name(name, max_w)
    assert " ".join(lines).split() == name.split()
    assert len(lines) <= 2 or f.size == aj.NAME_MIN_SIZE


def test_render_title_and_table_only_no_footer(tmpdb):
    upsert(("o1", "2026-10-08", 1, "c1", "s1", 4_500_000, 0))
    png = aj.render_aksiya_table("city", D8)
    img = Image.open(BytesIO(png))
    assert img.size == (aj.W, aj.H_TITLE + aj.H_HEAD + 2 * aj.H_ROW)  # JAMI/footer qatori yo'q
    # eng pastki qator — oxirgi agent qatori rangi (bo'sh krem joy emas)
    assert img.getpixel((aj.COLS[0] // 2, img.size[1] - 10)) != aj.BG_CREAM


def test_render_none_when_no_agents(tmpdb):
    with db.get_conn() as conn:
        conn.execute("UPDATE agents SET active='N'")
    assert aj.render_aksiya_table("city", D8) is None


# ── Faollashish sanasi va dublikat yo'qligi ──────────────────────

def test_activation_date():
    assert not aj.is_active(date(2026, 10, 7))
    assert aj.is_active(date(2026, 10, 8))
    assert aj.is_active(date(2026, 10, 9))


def test_tashkent_date_independent_of_server_tz():
    utc = timezone.utc
    assert aj.tashkent_today(datetime(2026, 10, 7, 18, 59, tzinfo=utc)) == date(2026, 10, 7)
    assert aj.tashkent_today(datetime(2026, 10, 7, 19, 0, tzinfo=utc)) == date(2026, 10, 8)
    assert aj.tashkent_today(datetime(2026, 10, 8, 15, 0, tzinfo=utc)) == date(2026, 10, 8)


class FakeBot:
    def __init__(self):
        self.calls = []

    async def send_photo(self, chat_id, photo, caption=None, parse_mode=None):
        self.calls.append(("photo", chat_id, photo, caption))
        return object()  # Telegram Message o'rnida (None = yuborilmadi)

    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None):
        self.calls.append(("message", chat_id, text))
        return object()


class FakeApp:
    def __init__(self):
        self.bot = FakeBot()


def run_dispatch(monkeypatch, today):
    async def no_sleep(*_a, **_k):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    monkeypatch.setattr(aj, "tashkent_today", lambda: today)
    monkeypatch.setattr(bot.image_reports, "render_agent_card", lambda sd: f"card:{sd}".encode())
    monkeypatch.setattr(bot.image_reports, "render_ball_table", lambda cat: f"ball:{cat}".encode())
    days = []

    def fake_aksiya(cat, day):
        days.append(day)
        return f"aksiya:{cat}".encode()

    monkeypatch.setattr(aj, "render_aksiya_table", fake_aksiya)
    app = FakeApp()
    sent = asyncio.run(bot.send_agent_cards_to_group(app, chat_id=-100))
    photos = [c[2].decode() for c in app.bot.calls if c[0] == "photo"]
    return sent, photos, app.bot.calls, days


def test_before_activation_old_ball_table_unchanged(tmpdb, monkeypatch):
    sent, photos, _calls, days = run_dispatch(monkeypatch, date(2026, 10, 7))
    assert sent == 3
    assert photos == ["card:c1", "card:c2", "ball:city", "card:r1", "ball:region"]
    assert days == []


def test_from_activation_aksiya_replaces_ball_once(tmpdb, monkeypatch):
    sent, photos, calls, days = run_dispatch(monkeypatch, D8)
    assert sent == 3  # individual kartochkalar soni o'zgarmagan
    assert photos == ["card:c1", "card:c2", "aksiya:city", "card:r1", "aksiya:region"]
    assert not any(p.startswith("ball:") for p in photos)
    assert days == [D8, D8]
    captions = [c[3] for c in calls if c[0] == "photo" and c[2].startswith(b"aksiya:")]
    assert captions == [
        "<b>AKSIYA JADVALI</b>  ·  SHAHAR  ·  📅 08.10.2026",
        "<b>AKSIYA JADVALI</b>  ·  VILOYAT  ·  📅 08.10.2026",
    ]
    assert all(c[1] == -100 for c in calls)  # faqat berilgan guruh
