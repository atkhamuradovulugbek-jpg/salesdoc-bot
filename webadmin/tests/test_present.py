"""
Prezentatsiyalar (/p/<nom>): parolsiz HTML ochilmaydi, login'dan keyin qaytadi,
blok ishlaydi, kesh/indeks sarlavhalari, yo'l chetlab o'tish yo'q.
"""

import importlib

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

PW = "juda-uzun-maxfiy-parol-2026"
SLUG = "oktyabr-2026"
MARK = "OKTYABR"                       # prezentatsiya ichidagi matn


def _client(monkeypatch):
    monkeypatch.setenv("WEB_PASSWORD", PW)
    import webadmin.main as m
    importlib.reload(m)
    return m, TestClient(m.app)


def test_without_login_redirects_and_no_content(monkeypatch):
    _, c = _client(monkeypatch)
    for path in (f"/p/{SLUG}", "/p/", "/p"):
        r = c.get(path, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"].startswith("/p/kirish?next=/p/")
        assert MARK not in r.text
    r = c.get(f"/p/{SLUG}", follow_redirects=False)
    assert r.headers["location"] == f"/p/kirish?next=/p/{SLUG}"
    assert "noindex" in r.headers["x-robots-tag"]


def test_login_then_open_with_headers(monkeypatch):
    _, c = _client(monkeypatch)
    r = c.post("/p/kirish", json={"password": PW})
    assert r.status_code == 200 and "nz_p" in r.cookies
    r = c.get(f"/p/{SLUG}")
    assert r.status_code == 200 and MARK in r.text and len(r.text) > 100_000
    assert "no-store" in r.headers["cache-control"] and "private" in r.headers["cache-control"]
    assert "noindex" in r.headers["x-robots-tag"]
    assert SLUG in c.get("/p/").text


def test_wrong_password_and_block(monkeypatch):
    _, c = _client(monkeypatch)
    codes = [c.post("/p/kirish", json={"password": "xato"}).status_code for _ in range(5)]
    assert codes[:4] == [401] * 4 and codes[4] == 429
    assert c.post("/p/kirish", json={"password": PW}).status_code == 429   # blokda to'g'risi ham yo'q
    assert c.get(f"/p/{SLUG}", follow_redirects=False).status_code == 303


def test_panel_token_auto_login_and_stale_token_not_counted(monkeypatch):
    m, c = _client(monkeypatch)
    for _ in range(6):                                   # eskirgan/soxta token blokka sanalmaydi
        assert c.post("/p/kirish", json={}, headers={"Authorization": "Bearer 1.x"}).status_code == 401
    assert c.post("/p/kirish", json={"password": PW}).status_code == 200
    c2 = TestClient(m.app)
    tok = m.auth.make_token(PW)
    assert c2.post("/p/kirish", json={}, headers={"Authorization": f"Bearer {tok}"}).status_code == 200
    assert c2.get(f"/p/{SLUG}").status_code == 200


def test_forged_cookie_and_path_traversal(monkeypatch):
    _, c = _client(monkeypatch)
    c.cookies.set("nz_p", "9999999999.soxta", path="/p")
    assert c.get(f"/p/{SLUG}", follow_redirects=False).status_code == 303
    c.post("/p/kirish", json={"password": PW})
    for bad in ("..%2Fmain", "..%2F..%2Fdb.py", "OKTYABR-2026", "x.html"):
        r = c.get(f"/p/{bad}", follow_redirects=False)
        assert r.status_code in (303, 404) and MARK not in r.text


def test_safe_next_blocks_open_redirect():
    from webadmin import present
    assert present.safe_next("https://evil.example") == "/p/"
    assert present.safe_next("//evil.example") == "/p/"
    assert present.safe_next("/p/oktyabr-2026") == "/p/oktyabr-2026"
