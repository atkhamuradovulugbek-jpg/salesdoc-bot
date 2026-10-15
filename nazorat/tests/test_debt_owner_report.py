"""
22:00 UMUMIY QARZ HISOBOTI egasiga ham (2026-10-07, egasi qarori).

  • 22:00 rasmlari: ulangan qarz nazoratchilari + egasi (admin) chati
  • test qarz profili uzilsa — unga bormaydi, egasi va haqiqiy nazoratchi oladi
  • soatlik ogohlantirish — FAQAT nazoratchilarga (egasiga emas)
  • idempotent: qayta ishga tushsa dublikat yo'q
Tarmoq yo'q: soxta bot, refresh_debt o'chirilgan.
"""

import asyncio
import os
import tempfile
from types import SimpleNamespace

import dotenv

dotenv.load_dotenv = lambda *a, **k: False
for k, v in {"NAZORAT_BOT_TOKEN": "test", "TELEGRAM_BOT_TOKEN": "test",
             "SALESDOC_BASE_URL": "http://salesdoc.invalid", "SALESDOC_LOGIN": "t",
             "SALESDOC_PASSWORD": "t", "DATA_DIR": tempfile.mkdtemp(prefix="nz-debt-")}.items():
    os.environ.setdefault(k, v)

import pytest  # noqa: E402

import db  # noqa: E402
from nazorat import debtwatch, storage  # noqa: E402
from nazorat.core.rules import load_agents  # noqa: E402

OWNER, REAL, TEST = 999, 500, 600
CODES = [d.code for d in load_agents().debt_controllers]     # [haqiqiy, TEST — egasi]


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "bot.db")
    db.init_db()
    with db.get_conn() as c:
        storage.init_nz_tables(c)
        storage.bind_code(c, CODES[0], REAL, "debt", None, "2026-08-13T15:42:00+05:00")
        storage.bind_code(c, CODES[1], TEST, "debt", None, "2026-08-13T15:20:00+05:00")
    monkeypatch.setattr(debtwatch, "ADMIN_IDS", {OWNER})

    async def no_refresh():
        return True, "test"
    monkeypatch.setattr(debtwatch, "refresh_debt", no_refresh)
    rows = [{"sd_id": "a1", "name": "Bahodir", "area": "Yunusobod", "league": "city",
             "debt": 4_000_000, "limit": 3_000_000, "pct": 133.3, "over": True, "near": False}]
    monkeypatch.setattr(debtwatch, "rows_for", lambda conn, lg=None, today=None: rows)
    yield


class FakeBot:
    def __init__(self):
        self.photos, self.texts = [], []

    async def send_photo(self, chat_id, photo, caption=None, **k):
        self.photos.append(chat_id)

    async def send_message(self, chat_id, text, **k):
        self.texts.append(chat_id)


def run(coro_fn):
    app = SimpleNamespace(bot=FakeBot())
    res = asyncio.run(coro_fn(app))
    return res, app.bot


def test_evening_goes_to_controllers_and_owner():
    _, fb = run(debtwatch.evening_report)
    assert sorted(fb.photos) == sorted([REAL, TEST, OWNER] * 2)      # shahar + viloyat


def test_after_test_profile_unbind_owner_and_real_only():
    with db.get_conn() as c:
        assert storage.unbind(c, CODES[1]) == TEST
    _, fb = run(debtwatch.evening_report)
    assert sorted(fb.photos) == sorted([REAL, OWNER] * 2) and TEST not in fb.photos


def test_owner_gets_report_even_without_controllers():
    with db.get_conn() as c:
        storage.unbind(c, CODES[0]); storage.unbind(c, CODES[1])
    res, fb = run(debtwatch.evening_report)
    assert fb.photos == [OWNER, OWNER] and res == "2 rasm"


def test_owner_bound_as_controller_not_duplicated():
    with db.get_conn() as c:
        storage.bind_code(c, CODES[1], OWNER, "debt", None, "2026-10-07T23:00:00+05:00")
        assert debtwatch._evening_chats(c) == [REAL, OWNER]


def test_evening_idempotent():
    run(debtwatch.evening_report)
    res, fb = run(debtwatch.evening_report)
    assert fb.photos == [] and res == "0 rasm"


def test_hourly_alerts_stay_with_controllers_only(monkeypatch):
    monkeypatch.setattr(debtwatch, "newly_over", lambda conn, rows, now: rows)
    _, fb = run(debtwatch.hourly_check)
    assert sorted(fb.texts) == [REAL, TEST] and OWNER not in fb.texts
