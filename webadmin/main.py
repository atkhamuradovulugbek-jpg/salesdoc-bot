"""
webadmin/main.py — Siribom admin web dastur (PWA) FastAPI serveri.

FAQAT O'QIYDI: botlar bazasini (bot.db) ko'rsatadi, hech narsa yozmaydi.
Botlarga xalaqit bermaydi — start_all.py 3-jarayon sifatida ishga tushiradi.

Kirish: parol (WEB_PASSWORD muhit o'zgaruvchisi).

Lokal ishga tushirish:
    WEB_PASSWORD=sinov-parol uvicorn webadmin.main:app --reload --port 8000

Railway: start_all.py orqali `uvicorn webadmin.main:app --host 0.0.0.0 --port $PORT`.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Loyiha ildizini import yo'liga qo'shish (db.py, nazorat/ uchun).
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from webadmin import auth, control, present, reportdata  # noqa: E402

app = FastAPI(title="Siribom Nazorat", docs_url=None, redoc_url=None)

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Faqat WEB_PASSWORD. Eski WEB_PIN zapasi OLIB TASHLANDI (2026-07-30, parol o'rnatilgach):
# aks holda kimdir WEB_PASSWORD ni o'chirsa, zaif PIN jimgina qayta yonardi (tuzoq).
SECRET = os.getenv("WEB_PASSWORD", "")
_limiter = auth.RateLimiter()


@app.on_event("startup")
def _ensure_tables():
    """nz_ jadvallari mavjudligiga ishonch (CREATE TABLE IF NOT EXISTS — idempotent).

    Botlar ham shuni qiladi, lekin web ULARDAN OLDIN ko'tarilishi mumkin: o'shanda
    ball plan ekrani "no such table" bilan qulardi. Ma'lumotga tegmaydi."""
    try:
        from db import get_conn
        from nazorat import storage
        with get_conn() as conn:
            storage.init_nz_tables(conn)
    except Exception:                                    # noqa: BLE001
        import logging
        logging.getLogger("webadmin").exception("nz jadvallarini tayyorlab bo'lmadi")


@app.middleware("http")
async def no_cache(request, call_next):
    """Deploy'dan keyin telefon eski HTML/CSS/JS'ni ushlab qolmasin."""
    resp = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".html", ".css", ".js", ".json")):
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp


# ──────────────────────────────────────────
# AUTH (PIN → token). xarajat-bot bilan bir xil sxema.
# ──────────────────────────────────────────

def check_auth(authorization: str = Header(default="")):
    if not SECRET:
        raise HTTPException(500, "Server sozlanmagan: WEB_PASSWORD muhit o'zgaruvchisi yo'q")
    token = authorization[7:] if authorization.startswith("Bearer ") else ""
    if not auth.token_valid(SECRET, token):
        raise HTTPException(401, "Kirish talab qilinadi")


class LoginBody(BaseModel):
    password: str | None = None
    pin: str | None = None          # eski mijoz uchun (moslik)

    @property
    def secret(self) -> str:
        return (self.password or self.pin or "").strip()


def _client_key(request: Request) -> str:
    """Blok HAR MIJOZ uchun alohida bo'lsin (Railway proksisi orqasida x-forwarded-for).

    OXIRGI qiymat olinadi — u ishonchli proksi qo'shgani. Birinchisini olsak, mijoz
    o'zi X-Forwarded-For yozib blokdan qutulib ketardi (2026-07-30 review topdi)."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        parts = [p.strip() for p in fwd.split(",") if p.strip()]
        if parts:
            return parts[-1]
    return request.client.host if request.client else "?"


def _wait_text(seconds: int) -> str:
    """Odam tiliga: '40 soniya' / '2 daqiqa'."""
    if seconds < 60:
        return f"{seconds} soniya"
    return f"{seconds // 60 + (1 if seconds % 60 else 0)} daqiqa"


def _password_or_raise(request: Request, given: str) -> None:
    """Parolni tekshiradi; xato bo'lsa 5-xato blokini qo'llab HTTPException ko'taradi.
    /api/login va prezentatsiya kirishi BIR xil cheklovni ishlatadi."""
    if not SECRET:
        raise HTTPException(500, "Server sozlanmagan: WEB_PASSWORD muhit o'zgaruvchisi yo'q")
    key = _client_key(request)

    left = _limiter.blocked_for(key)
    if left:
        raise HTTPException(429, f"Bir oz kutish kerak: {_wait_text(left)}.")
    if not auth.password_ok(SECRET, given):
        blocked = _limiter.fail(key)
        if blocked:
            raise HTTPException(429, f"5 marta xato kiritildi. {_wait_text(blocked)} "
                                    f"kutib, qayta urinib ko'ring.")
        raise HTTPException(401, "Parol noto'g'ri")
    _limiter.reset(key)


@app.post("/api/login")
def login(body: LoginBody, request: Request):
    _password_or_raise(request, body.secret)
    return {"token": auth.make_token(SECRET), "weak": auth.is_weak(SECRET),
            "days": auth.TOKEN_DAYS}


# ──────────────────────────────────────────
# API (hammasi faqat o'qish)
# ──────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/report")
def report(authorization: str = Header(default="")):
    """Bosh sahifa + Savdo + Agentlar(strike) + Qarz + Vazvrat tablari uchun."""
    check_auth(authorization)
    return reportdata.get_report() | {"weak_auth": auth.is_weak(SECRET)}


@app.post("/api/refresh")
def refresh(authorization: str = Header(default="")):
    """⟳ tugmasi. Avval BUGUNGI ma'lumotni tortishni so'raydi (botga vazifa),
    keyin bordagi hisobotni qaytaradi. Mijoz bir necha soniyadan keyin qayta
    so'rab yangi raqamni oladi."""
    check_auth(authorization)
    q = control.request_quick()
    return reportdata.get_report(force=True) | {"quick": q} | control.data_age()


@app.get("/api/stock")
def stock(authorization: str = Header(default="")):
    check_auth(authorization)
    return reportdata.stock_overview()


@app.get("/api/agent/{sd_id}")
def agent(sd_id: str, authorization: str = Header(default="")):
    check_auth(authorization)
    d = reportdata.agent_detail(sd_id)
    if d is None:
        raise HTTPException(404, "Agent topilmadi")
    return d


# ──────────────────────────────────────────
# BOSHQARUV (2-4 bosqich): web faqat navbatga qo'yadi, botlar bajaradi
# ──────────────────────────────────────────

@app.get("/api/connections")
def connections(authorization: str = Header(default="")):
    """Ulanish ekrani (kesh yo'q — foydalanuvchi amalidan keyin darhol yangilanadi)."""
    check_auth(authorization)
    return control.connections()


class SyncBody(BaseModel):
    mode: str = "fast"


@app.post("/api/sync")
def sync_now(body: SyncBody, authorization: str = Header(default="")):
    check_auth(authorization)
    if body.mode not in ("fast", "full"):
        raise HTTPException(400, "mode: fast yoki full")
    return control.request_sync(body.mode)


class BindBody(BaseModel):
    code: str
    chat_id: int


@app.post("/api/bind/approve")
def bind_approve(body: BindBody, authorization: str = Header(default="")):
    check_auth(authorization)
    return control.approve_binding(body.code, body.chat_id)


@app.post("/api/bind/reject")
def bind_reject(body: BindBody, authorization: str = Header(default="")):
    check_auth(authorization)
    return control.reject_binding(body.code, body.chat_id)


class UnbindBody(BaseModel):
    code: str
    confirm_name: str


@app.post("/api/bind/disconnect")
def bind_disconnect(body: UnbindBody, authorization: str = Header(default="")):
    """Uzish — ism yozib tasdiqlash SHART (bir noto'g'ri bosish = agent bir oy
    hisobot olmaydi; llm-council talabi)."""
    check_auth(authorization)
    from nazorat import binding as nzbinding
    expected = nzbinding.display_name(body.code)
    if (body.confirm_name or "").strip().lower() != expected.strip().lower():
        raise HTTPException(400, f"Tasdiqlash uchun ismni aynan yozing: {expected}")
    return control.disconnect_binding(body.code)


# ──────────────────────────────────────────
# BALL PLAN — «OY VARAQASI» (5-bosqich)
# ──────────────────────────────────────────

@app.get("/api/periods")
def periods(authorization: str = Header(default="")):
    check_auth(authorization)
    return control.period_overview()


@app.get("/api/period/{ym}")
def period_sheet(ym: str, authorization: str = Header(default="")):
    check_auth(authorization)
    try:
        return control.period_sheet(ym)
    except ValueError as e:
        raise HTTPException(400, str(e))


class PeriodSaveBody(BaseModel):
    plans: dict[str, int]
    prizes_enabled: bool = True          # podium (1.5/1/0.5 mln)
    growth_enabled: bool = True          # o'sish sovrini (700 ming)


@app.post("/api/period/{ym}/save")
def period_save(ym: str, body: PeriodSaveBody, authorization: str = Header(default="")):
    """Qoralama — agentlar ko'rmaydi. E'lon qilingan varaqa tahrirlanmaydi."""
    check_auth(authorization)
    try:
        return control.period_save(ym, body.plans, body.prizes_enabled,
                                   body.growth_enabled)
    except PermissionError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/period/{ym}/preview")
def period_preview(ym: str, authorization: str = Header(default="")):
    check_auth(authorization)
    try:
        return control.period_preview(ym)
    except ValueError as e:
        raise HTTPException(400, str(e))


class PeriodPublishBody(BaseModel):
    confirm_month: str


@app.post("/api/period/{ym}/publish")
def period_publish(ym: str, body: PeriodPublishBody,
                   authorization: str = Header(default="")):
    """E'lon = MUZLATISH. Oy nomini yozib tasdiqlash SHART (uzish bilan bir xil
    sinf: bir noto'g'ri bosish 18 kishining bonusini o'zgartiradi)."""
    check_auth(authorization)
    from nazorat import period as nzperiod
    try:
        expected = nzperiod.month_label(ym).split()[0]
    except ValueError as e:
        raise HTTPException(400, str(e))
    if (body.confirm_month or "").strip().lower() != expected.lower():
        raise HTTPException(400, f"Tasdiqlash uchun oy nomini yozing: {expected}")
    return control.period_publish(ym)


@app.post("/api/period/{ym}/reopen")
def period_reopen(ym: str, authorization: str = Header(default="")):
    """E'lon qilingan varaqani TUZATISH uchun ochadi (oy tugamagan bo'lsa)."""
    check_auth(authorization)
    try:
        return control.period_reopen(ym)
    except PermissionError as e:
        raise HTTPException(409, str(e))
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


# ──────────────────────────────────────────
# PREZENTATSIYALAR (/p/<nom>) — faqat admin, cookie bilan (Safari havolasi uchun)
# ──────────────────────────────────────────

def _p_ok(request: Request) -> bool:
    return bool(SECRET) and auth.token_valid(SECRET, request.cookies.get(present.COOKIE, ""))


def _p_html(body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(body, status_code=status, headers=present.HEADERS)


def _p_login_redirect(nxt: str) -> RedirectResponse:
    from urllib.parse import quote
    return RedirectResponse(f"/p/kirish?next={quote(present.safe_next(nxt), safe='/')}",
                            status_code=303, headers=present.HEADERS)


@app.get("/p/kirish")
def p_login_page(next: str = "/p/"):
    return _p_html(present.login_page(next))


@app.post("/p/kirish")
def p_login(body: LoginBody, request: Request, authorization: str = Header(default="")):
    token = authorization[7:] if authorization.startswith("Bearer ") else ""
    if token:                                    # panel tokeni (avtomatik kirish) — blokka sanalmaydi
        if not (SECRET and auth.token_valid(SECRET, token)):
            raise HTTPException(401, "Panel tokeni eskirgan")
    else:
        _password_or_raise(request, body.secret)
        token = auth.make_token(SECRET)
    resp = JSONResponse({"ok": True}, headers=present.HEADERS)
    https = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    resp.set_cookie(present.COOKIE, token, max_age=auth.TOKEN_DAYS * 86400, path=present.PREFIX,
                    httponly=True, secure=https, samesite="lax")
    return resp


@app.get("/p/chiqish")
def p_logout():
    resp = _p_login_redirect("/p/")
    resp.delete_cookie(present.COOKIE, path=present.PREFIX)
    return resp


@app.get("/p")
@app.get("/p/")
def p_list(request: Request):
    if not _p_ok(request):
        return _p_login_redirect("/p/")
    return _p_html(present.list_page(present.listing()))


@app.get("/p/{slug}")
def p_show(slug: str, request: Request):
    f = present.file_for(slug)
    if not _p_ok(request):
        return _p_login_redirect(f"/p/{slug}" if f else "/p/")
    if f is None:
        return _p_html("<h1>Topilmadi</h1>", 404)
    return FileResponse(f, media_type="text/html; charset=utf-8", headers=present.HEADERS)


# ──────────────────────────────────────────
# STATIK FAYLLAR (PWA) — mount OXIRIDA bo'lishi shart (catch-all)
# ──────────────────────────────────────────

@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
