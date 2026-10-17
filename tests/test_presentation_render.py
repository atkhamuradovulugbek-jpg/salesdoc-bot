"""Prezentatsiya generatori — render qatlami: dizayn/animatsiya aynan saqlanadi."""

from pathlib import Path

from tools.presentation import fromhtml, render

ROOT = Path(__file__).resolve().parent.parent
OKT = ROOT / "webadmin" / "presentations" / "oktyabr-2026.html"


def test_roundtrip_is_byte_identical():
    """Tasdiqlangan oktyabr sahifasi → model → HTML: bitta bayt ham farq qilmaydi."""
    src = OKT.read_text(encoding="utf-8")
    assert render.render(fromhtml.parse(src)) == src


def test_template_has_approved_animations():
    css = (render.TEMPLATE / "style.css").read_text(encoding="utf-8")
    js = (render.TEMPLATE / "app.js").read_text(encoding="utf-8")
    for k in ("lgPop", "lgRing", "lgCore", "arrUp", "arrDown", "arrFloat", "prefers-reduced-motion"):
        assert k in css
    assert "fxLogo" in js and "logo-fx" in js


def test_render_escapes_and_counts_slides():
    m = fromhtml.parse(OKT.read_text(encoding="utf-8"))
    m["tables"][0]["rows"][0][0]["t"] = "<b>X</b>\nY"
    out = render.render(m)
    assert "<b>X</b>" not in out and "&lt;b&gt;X&lt;/b&gt;" in out
    assert 'id="cnt">1 / 9<' in out
