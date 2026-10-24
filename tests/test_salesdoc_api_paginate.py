"""
Sales Doctor sahifalash himoyasi (2026-10-25).

24.10.2026 20:10: 3-sahifa HTTP 200 bilan BO'SH keldi → 5622 o'rniga 2000 buyurtma,
9–23.10 bazadan o'chib ketdi, agentlarga noto'g'ri oylik hisobot ketdi.
Endi bo'sh yoki takror sahifa 3 marta (1, 2, 4 sek kutib) qayta so'raladi;
takror sahifa baribir kelsa — xato ko'tariladi (chala ro'yxat "to'liq" bo'lib ketmasin).
"""

import asyncio
import os
import sys
import tempfile
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
    "DATA_DIR": tempfile.mkdtemp(prefix="paginate-test-"),
})

import pytest  # noqa: E402

import salesdoc_api  # noqa: E402


def _page(n: int, start: int = 0) -> list[dict]:
    return [{"SD_id": f"o{start + i}"} for i in range(n)]


def _resp(items, status=200) -> dict:
    return {"status": status, "result": {"order": items}}


def _client(responses: list):
    """_post o'rniga navbatdagi tayyor javobni qaytaradigan mijoz + so'ralgan sahifalar."""
    c = salesdoc_api.SalesDocClient()
    c._user_id, c._token = "u", "t"
    calls: list[int] = []

    async def fake_post(payload):
        calls.append(payload["params"]["page"])
        return responses.pop(0)

    c._post = fake_post
    return c, calls


@pytest.fixture(autouse=True)
def waits(monkeypatch):
    """Haqiqiy kutish yo'q — faqat necha sekund kutilgani yoziladi."""
    rec: list[float] = []

    async def fake_sleep(s):
        rec.append(s)

    monkeypatch.setattr(salesdoc_api.asyncio, "sleep", fake_sleep)
    return rec


def _orders(c):
    return asyncio.run(c.get_orders("2026-10-01", "2026-10-24"))


def test_oddiy_qisqa_royxat_bir_sorov(waits):
    c, calls = _client([_resp(_page(10))])
    assert len(_orders(c)) == 10
    assert calls == [1]
    assert waits == []                      # qayta so'rash bo'lmadi


def test_ortadagi_bosh_sahifa_qayta_soraladi(waits):
    """24.10 holati: 1–2 to'liq, 3-sahifa bo'sh keldi → qayta so'ralganda keldi."""
    c, calls = _client([_resp(_page(1000)), _resp(_page(1000, 1000)),
                        _resp([]), _resp(_page(500, 2000))])
    got = _orders(c)
    assert len(got) == 2500
    assert calls == [1, 2, 3, 3]
    assert 1 in waits                       # 1 sek kutib qayta so'raldi


def test_bosh_sahifa_uch_marta_qayta_soraladi(waits):
    """Haqiqatan bo'sh (yoki API yotgan) — 3 marta urinib, bo'sh qaytaradi (xato emas:
    sync.py chala himoyasi eski ma'lumotni saqlaydi)."""
    c, calls = _client([_resp([])] * 4)
    assert _orders(c) == []
    assert calls == [1, 1, 1, 1]
    assert [w for w in waits if w >= 1] == [1, 2, 4]


def test_buzilgan_javob_bosh_deb_qayta_soraladi(waits):
    """result=None / status 500 (HTTP 200 bilan) — bo'sh sahifa kabi qayta so'raladi."""
    c, calls = _client([{"status": 500, "result": None}, _resp(_page(10))])
    assert len(_orders(c)) == 10
    assert calls == [1, 1]


def test_takror_sahifa_bir_marta_keyin_togri(waits):
    first = _page(1000)
    c, calls = _client([_resp(first), _resp(first), _resp(_page(300, 1000))])
    got = _orders(c)
    assert len(got) == 1300
    assert calls == [1, 2, 2]


def test_takror_sahifa_doimiy_xato_kotaradi(waits):
    """Server `page` ni e'tiborga olmasa — 1-sahifani "hammasi" deb qaytarmaymiz."""
    first = _page(1000)
    c, calls = _client([_resp(first)] + [_resp(first)] * 4)
    with pytest.raises(RuntimeError, match="sahifalash buzildi"):
        _orders(c)
    assert calls == [1, 2, 2, 2, 2]
