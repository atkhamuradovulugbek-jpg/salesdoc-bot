"""
Login API (0.5-bosqich): parol bilan kirish, noto'g'ri parol, blok, token bilan himoya.
Haqiqiy FastAPI ilovasi orqali (TestClient) — uchidan-uchiga.
"""

import importlib
import os

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

PW = "juda-uzun-maxfiy-parol-2026"


def _app(monkeypatch, password="", pin=""):
    """WEB_PASSWORD/WEB_PIN bilan ilovani qaytadan yuklaydi (SECRET import paytida o'qiladi)."""
    monkeypatch.setenv("WEB_PASSWORD", password)
    monkeypatch.setenv("WEB_PIN", pin)
    import webadmin.main as m
    importlib.reload(m)
    return m


def test_login_with_password_returns_token(monkeypatch):
    m = _app(monkeypatch, password=PW)
    c = TestClient(m.app)
    r = c.post("/api/login", json={"password": PW})
    assert r.status_code == 200
    body = r.json()
    assert body["token"] and body["weak"] is False


def test_wrong_password_401(monkeypatch):
    m = _app(monkeypatch, password=PW)
    c = TestClient(m.app)
    r = c.post("/api/login", json={"password": "xato"})
    assert r.status_code == 401


def test_protected_endpoint_needs_valid_token(monkeypatch):
    m = _app(monkeypatch, password=PW)
    c = TestClient(m.app)
    assert c.get("/api/stock").status_code == 401                      # tokensiz
    assert c.get("/api/stock", headers={"Authorization": "Bearer yolgon"}).status_code == 401


def test_health_is_public(monkeypatch):
    m = _app(monkeypatch, password=PW)
    assert TestClient(m.app).get("/api/health").status_code == 200


def test_blocked_after_five_wrong_attempts(monkeypatch):
    m = _app(monkeypatch, password=PW)
    c = TestClient(m.app)
    codes = [c.post("/api/login", json={"password": f"xato{i}"}).status_code
             for i in range(6)]
    assert codes[:4] == [401, 401, 401, 401]
    assert codes[4] == 429                                            # 5-xato → blok
    assert codes[5] == 429                                            # blok davom etadi
    # blok paytida TO'G'RI parol ham o'tmaydi
    assert c.post("/api/login", json={"password": PW}).status_code == 429


def test_old_pin_alone_does_not_work(monkeypatch):
    """WEB_PIN zapasi olib tashlandi (2026-07-30): faqat WEB_PASSWORD ishlaydi.
    Aks holda parol o'chirilsa zaif PIN jimgina qayta yonardi."""
    m = _app(monkeypatch, password="", pin="123456")
    c = TestClient(m.app)
    assert c.post("/api/login", json={"pin": "123456"}).status_code == 500   # sozlanmagan


def test_password_disables_old_pin(monkeypatch):
    m = _app(monkeypatch, password=PW, pin="123456")
    c = TestClient(m.app)
    assert c.post("/api/login", json={"pin": "123456"}).status_code == 401
    assert c.post("/api/login", json={"password": PW}).status_code == 200


def test_unconfigured_server_returns_500(monkeypatch):
    m = _app(monkeypatch, password="", pin="")
    c = TestClient(m.app)
    assert c.post("/api/login", json={"password": "x"}).status_code == 500
