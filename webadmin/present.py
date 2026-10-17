"""
present.py — himoyalangan web-prezentatsiyalar (2026-10-17, egasi so'rovi).

Fayllar: webadmin/presentations/<nom>.html (mustaqil HTML). Yangi oy qo'shish — shu papkaga
fayl tashlab deploy qilish kifoya; havola: /p/<nom>.

Himoya: admin panel bilan BIR parol (WEB_PASSWORD) va bir xil 5-xato bloki. Kirgandan keyin
imzolangan token HttpOnly cookie'da (faqat /p yo'lida) saqlanadi — Safari'da havola bilan
ochish uchun (Authorization sarlavhasi yuborib bo'lmaydi). SOF MANTIQ — FastAPI'siz, testlanadi.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

DIR = Path(__file__).resolve().parent / "presentations"
COOKIE = "nz_p"
PREFIX = "/p"
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")

HEADERS = {
    "Cache-Control": "no-store, private, max-age=0",
    "Pragma": "no-cache",
    "X-Robots-Tag": "noindex, nofollow, noarchive",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


def file_for(slug: str) -> Path | None:
    """Nom xavfsiz bo'lsa va fayl bo'lsa — yo'li (yo'l chetlab o'tish mumkin emas)."""
    if not _SLUG.match(slug or ""):
        return None
    p = DIR / f"{slug}.html"
    return p if p.is_file() else None


def listing() -> list[str]:
    return sorted((p.stem for p in DIR.glob("*.html") if _SLUG.match(p.stem)), reverse=True)


def safe_next(nxt: str | None) -> str:
    """Login'dan keyin faqat /p ichiga qaytariladi (ochiq yo'naltirish yo'q)."""
    nxt = nxt or ""
    if nxt == PREFIX + "/" or re.match(r"^/p/[a-z0-9][a-z0-9-]{0,60}$", nxt):
        return nxt
    return PREFIX + "/"


def _page(title: str, body: str) -> str:
    return f"""<!doctype html><html lang="uz"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow"><title>{html.escape(title)}</title>
<style>
:root{{color-scheme:dark}}*{{box-sizing:border-box}}
body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
background:#0b0d17;color:#f5f5ff;font:16px -apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;
padding:24px 16px}}
.box{{width:100%;max-width:380px;background:#151827;border:1px solid #2a2f4a;border-radius:18px;padding:28px 22px}}
h1{{font-size:21px;margin:0 0 6px}}p{{color:#abb0c5;margin:0 0 18px;font-size:14px}}
input{{width:100%;font-size:17px;padding:14px;border-radius:12px;border:1px solid #2f3555;background:#0f1220;
color:#fff;margin-bottom:12px}}
button,a.btn{{display:block;width:100%;text-align:center;font-size:17px;font-weight:600;padding:14px;border:0;
border-radius:12px;background:#8b6cff;color:#fff;text-decoration:none;margin-bottom:10px}}
.err{{color:#ff789a;font-size:14px;min-height:20px;margin-bottom:8px}}
</style></head><body><div class="box">{body}</div></body></html>"""


def login_page(nxt: str) -> str:
    nxt_js = json.dumps(safe_next(nxt))
    return _page("Kirish · Prezentatsiya", f"""
<h1>🎬 Prezentatsiya</h1><p>Admin panel paroli bilan kiring.</p>
<form id="f" autocomplete="on">
<input id="pw" type="password" name="password" autocomplete="current-password" placeholder="Parol" required>
<div class="err" id="err"></div><button id="b" type="submit">Kirish</button></form>
<script>
const NEXT = {nxt_js};
async function go(opts) {{
  const r = await fetch("/p/kirish", Object.assign({{method: "POST", credentials: "same-origin",
    headers: {{"Content-Type": "application/json"}}}}, opts));
  if (r.ok) {{ location.replace(NEXT); return true; }}
  return r;
}}
// Shu qurilmada admin panelga kirilgan bo'lsa — parolsiz (panel tokeni bilan)
(async () => {{
  let t = ""; try {{ t = localStorage.getItem("nz_token") || ""; }} catch (e) {{}}
  if (t) {{ await go({{body: JSON.stringify({{}}), headers: {{"Content-Type": "application/json",
    "Authorization": "Bearer " + t}}}}); }}
}})();
document.getElementById("f").addEventListener("submit", async (e) => {{
  e.preventDefault();
  const b = document.getElementById("b"), err = document.getElementById("err");
  b.disabled = true; err.textContent = "";
  try {{
    const r = await go({{body: JSON.stringify({{password: document.getElementById("pw").value}})}});
    if (r !== true) {{ let m = "Kirib bo'lmadi";
      try {{ m = (await r.json()).detail || m; }} catch (x) {{}} err.textContent = m; }}
  }} catch (x) {{ err.textContent = "Internet aloqasini tekshiring"; }}
  b.disabled = false;
}});
</script>""")


def list_page(slugs: list[str]) -> str:
    items = "".join(f'<a class="btn" href="{PREFIX}/{s}">{html.escape(s)}</a>' for s in slugs) \
        or "<p>Hozircha prezentatsiya yo'q.</p>"
    return _page("Prezentatsiyalar", f"<h1>🎬 Prezentatsiyalar</h1><p>Faqat siz ko'rasiz.</p>{items}"
                 f'<p style="margin-top:14px"><a href="{PREFIX}/chiqish" style="color:#abb0c5">Chiqish</a></p>')
