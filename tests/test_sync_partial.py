"""
Sync "chala javob" himoyasi (2026-10-25).

24.10.2026 20:10: Sales Doctor 5622 o'rniga 2000 buyurtma qaytardi, sync oraliqdagi
eski buyurtmalarni O'CHIRIB, 2000 tasini yozdi → 9–23.10 yo'qoldi. Endi yangi soni
bazadagidan 10%+ kam bo'lsa: oraliq o'chirilmaydi, kelganlari upsert qilinadi,
sync_log'ga "partial" yoziladi va "partial: ..." qaytadi.
"""

import asyncio
import os
import sys
import tempfile
from datetime import date
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
    "DATA_DIR": tempfile.mkdtemp(prefix="sync-test-"),
})

import pytest  # noqa: E402

import db  # noqa: E402
import sync  # noqa: E402
from db import get_conn  # noqa: E402

TODAY = date.today().isoformat()


class FakeApi:
    """Faqat FAST rejimda chaqiriladigan metodlar."""

    def __init__(self, orders):
        self.orders = orders

    async def login(self):
        pass

    async def get_balance(self):
        return []

    async def get_stock(self):
        return []

    async def get_visits(self, date_from, date_to):
        return []

    async def get_orders(self, date_from, date_to, statuses=None):
        return self.orders


def api_order(i: int) -> dict:
    return {"SD_id": f"new{i}", "dateCreate": f"{TODAY} 10:00:00", "status": 3,
            "agent": {"SD_id": "a1"}, "client": {"SD_id": "c1"},
            "totalSummaAfterDiscount": 100_000, "totalReturnsSumma": 0,
            "orderProducts": [{"product": {"SD_id": "p1", "name": "X"},
                               "quantity": 1, "summa": 100_000}]}


@pytest.fixture()
def seed(monkeypatch, tmp_path):
    """Alohida vaqtinchalik baza: 1 mijoz (aks holda sync FULL rejimga o'tadi) +
    n_old ta bugungi eski buyurtma (item'lari bilan)."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()

    def _seed(n_old: int):
        with get_conn() as conn:
            conn.execute("INSERT INTO clients (sd_id, name) VALUES ('c1', 'Dokon')")
            conn.executemany(
                "INSERT INTO orders (sd_id, date, status, agent_sd_id, client_sd_id, "
                "total_after_discount, total_returns) VALUES (?,?,?,?,?,?,?)",
                [(f"old{i}", TODAY, 3, "a1", "c1", 50_000, 0) for i in range(n_old)])
            conn.executemany(
                "INSERT INTO order_items (order_sd_id, product_sd_id, product_name, "
                "quantity, summa, returned, block) VALUES (?,?,?,?,?,?,?)",
                [(f"old{i}", "p1", "X", 1, 50_000, 0, 0) for i in range(n_old)])
    return _seed


def _run(monkeypatch, orders, mode="fast") -> str:
    monkeypatch.setattr(sync, "get_api", lambda: FakeApi(orders))
    return asyncio.run(sync._run_sync_impl("test", None, mode))


def _counts():
    with get_conn() as conn:
        o = conn.execute("SELECT COUNT(*) c FROM orders").fetchone()["c"]
        old = conn.execute("SELECT COUNT(*) c FROM orders WHERE sd_id LIKE 'old%'").fetchone()["c"]
        items = conn.execute("SELECT COUNT(*) c FROM order_items").fetchone()["c"]
        log = conn.execute("SELECT status, note FROM sync_log ORDER BY id DESC LIMIT 1").fetchone()
    return o, old, items, log


# ---------- looks_partial ----------

@pytest.mark.parametrize("new,old,partial", [
    (2000, 5622, True),     # 24.10 holati
    (4000, 5100, True),     # 23.10 12:00 holati (78%)
    (0, 200, True),         # umuman bo'sh
    (180, 200, False),      # aynan 90% — chegara, chala emas
    (179, 200, True),
    (250, 245, False),      # odatdagi o'sish
    (10, 50, False),        # kichik to'plam tekshirilmaydi
    (0, 0, False),          # oy boshi / yakshanba ertalab
])
def test_looks_partial(new, old, partial):
    assert sync.looks_partial(new, old) is partial


# ---------- haqiqiy yozish yo'li ----------

def test_chala_kelsa_eski_saqlanadi_kelgani_qoshiladi(seed, monkeypatch):
    seed(200)
    res = _run(monkeypatch, [api_order(i) for i in range(100)])
    assert res.startswith("partial")
    o, old, items, log = _counts()
    assert old == 200                       # eski oraliq O'CHIRILMADI
    assert o == 300                         # kelgan 100 tasi qo'shildi
    assert items == 300                     # eski item'lar ham joyida, yangilari qo'shildi
    assert log["status"] == "partial" and "100/200" in log["note"]


def test_umuman_bosh_kelsa_eski_saqlanadi(seed, monkeypatch):
    seed(200)
    res = _run(monkeypatch, [])
    assert res.startswith("partial")
    o, old, items, log = _counts()
    assert (o, old, items) == (200, 200, 200)
    assert log["status"] == "partial"


def test_toliq_kelsa_eski_almashtiriladi(seed, monkeypatch):
    seed(200)
    res = _run(monkeypatch, [api_order(i) for i in range(190)])
    assert res == "ok"
    o, old, items, log = _counts()
    assert (o, old, items) == (190, 0, 190)
    assert log["status"] == "ok"


def test_kichik_toplam_tekshirilmaydi(seed, monkeypatch):
    """Bugun rejimi ertalab: bazada 50 ta, 10 ta keldi — odatdagidek almashtiriladi."""
    seed(50)
    res = _run(monkeypatch, [api_order(i) for i in range(10)], mode="today")
    assert res == "ok"
    o, old, _, _ = _counts()
    assert (o, old) == (10, 0)
