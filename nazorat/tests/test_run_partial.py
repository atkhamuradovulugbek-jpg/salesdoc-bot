"""
20:10 hisobotidan oldingi sync "partial" (chala) qaytarsa (2026-10-25).

Sales Doctor chala javob berganda sync eski (to'liq) ma'lumotni saqlab qoldi.
Ma'lumot yangi bo'lsa (asosiy botning 20:00 sync'i) — hisobot shu bilan ketadi va
adminga xabar; eski bo'lsa — yuborilmaydi. Oddiy xato — avvalgidek yuborilmaydi.
"""

import asyncio
import os
import tempfile

import dotenv

dotenv.load_dotenv = lambda *a, **k: False
for k, v in {
    "TELEGRAM_BOT_TOKEN": "test-token",
    "NAZORAT_BOT_TOKEN": "test-token",
    "NAZORAT_ADMIN_IDS": "1",
    "SALESDOC_BASE_URL": "http://salesdoc.invalid",
    "SALESDOC_LOGIN": "test",
    "SALESDOC_PASSWORD": "test",
    "ADMIN_TELEGRAM_IDS": "",
    "ALLOWED_TELEGRAM_IDS": "",
    "DATA_DIR": tempfile.mkdtemp(prefix="run-partial-test-"),
}.items():
    os.environ.setdefault(k, v)

import pytest  # noqa: E402

import db  # noqa: E402
import sync  # noqa: E402
from nazorat import jobs, run  # noqa: E402

PARTIAL = "partial: buyurtmalar chala keldi (2000/5622) — eski ma'lumot saqlandi"


@pytest.fixture()
def harness(monkeypatch):
    """run_sync natijasi + ma'lumot yoshi beriladi; admin xabarlari va job chaqiruvlari yig'iladi."""
    db.init_db()
    msgs: list[str] = []
    calls: list[int] = []

    def setup(result: str, age: float | None):
        async def fake_run_sync(*a, **k):
            return result

        async def fake_admins(app, photo=None, text=None):
            msgs.append(text or "")

        async def job(app):
            calls.append(1)

        monkeypatch.setattr(sync, "run_sync", fake_run_sync)
        monkeypatch.setattr(run, "_data_age_min", lambda: age)
        monkeypatch.setattr(jobs, "_admins", fake_admins)
        return job

    return setup, msgs, calls


def _go(job):
    asyncio.run(run._sync_then(object(), job))


def test_chala_lekin_malumot_yangi_hisobot_ketadi(harness):
    setup, msgs, calls = harness
    _go(setup(PARTIAL, age=10))
    assert calls == [1]
    assert len(msgs) == 1 and "chala" in msgs[0] and "yuboriladi" in msgs[0]


def test_chala_va_malumot_eski_hisobot_ketmaydi(harness):
    setup, msgs, calls = harness
    _go(setup(PARTIAL, age=120))
    assert calls == []
    assert len(msgs) == 1 and "yuborilmadi" in msgs[0]


def test_chala_va_yosh_nomalum_hisobot_ketmaydi(harness):
    setup, msgs, calls = harness
    _go(setup(PARTIAL, age=None))
    assert calls == []


def test_oddiy_xato_avvalgidek_toxtatadi(harness):
    setup, msgs, calls = harness
    _go(setup("RuntimeError: Sales Doctor javob bermadi", age=5))
    assert calls == []
    assert "Sync xatosi" in msgs[0]


def test_ok_hisobot_ketadi(harness):
    setup, msgs, calls = harness
    _go(setup("ok", age=1))
    assert calls == [1]
    assert msgs == []
