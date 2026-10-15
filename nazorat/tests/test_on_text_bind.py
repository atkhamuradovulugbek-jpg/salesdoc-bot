"""
REGRESSIYA (2026-07-30 kritik): on_text ichida `binding` o'zgaruvchisi `binding`
MODULINI bosib qo'ygan edi — agent kod yozsa AttributeError, ulanish umuman ishlamas edi.
112 test o'tsa ham bu tutilmagan, chunki on_text ni hech qaysi test yurgizmasdi.

Bu test AYNAN o'sha oqimni haydaydi: ulanmagan chat + haqiqiy kod → nz_bind_request
qatori yoziladi + agentga "so'rov yuborildi" javobi + adminга tugmali xabar.
"""

import asyncio
import sqlite3
import symtable

import pytest


def test_on_text_does_not_shadow_binding_module():
    """Statik kafolat: hech qaysi handler `binding` modulini bosib qo'ymaydi."""
    src = open("nazorat/bot.py").read()
    st = symtable.symtable(src, "bot.py", "exec")

    def walk(t):
        yield t
        for c in t.get_children():
            yield from walk(c)

    poisoned = []
    for t in walk(st):
        if t.get_type() != "function":
            continue
        try:
            sym = t.lookup("binding")
        except KeyError:
            continue
        # `binding` ishlatilsa — u LOKAL bo'lmasligi kerak (modulni bosib qo'ymasin)
        if sym.is_local() and not sym.is_parameter():
            poisoned.append(t.get_name())
    assert poisoned == [], f"`binding` modulini bosib qo'ygan funksiyalar: {poisoned}"


class _Msg:
    def __init__(self, text, chat_id):
        self.text = text
        self.chat = type("C", (), {"id": chat_id})()
        self.replies = []

    async def reply_text(self, text, **kw):
        self.replies.append(text)


class _Update:
    def __init__(self, text, chat_id, username="sinov"):
        self.message = _Msg(text, chat_id)
        self.effective_chat = type("C", (), {"id": chat_id})()
        self.effective_user = type("U", (), {"username": username, "full_name": "Sinov"})()


class _Bot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text, kw.get("reply_markup")))


class _Ctx:
    def __init__(self):
        self.application = type("A", (), {"bot": _Bot(), "bot_data": {}})()


def test_valid_code_creates_pending_request_and_notifies(monkeypatch, tmp_path):
    """Haqiqiy oqim: kod yuborildi → nz_bind_request + agentga javob + adminга tugma."""
    # Izolyatsiya qilingan baza
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import importlib
    import db as _db
    importlib.reload(_db)
    import nazorat.storage as storage
    importlib.reload(storage)
    with _db.get_conn() as conn:
        storage.init_nz_tables(conn)

    import nazorat.bot as nzbot
    importlib.reload(nzbot)

    # Bitta haqiqiy agent kodi
    code = nzbot.AGENTS_CFG.agents[0].code
    monkeypatch.setattr(nzbot, "ADMIN_IDS", {700})

    upd = _Update(code, chat_id=999)
    ctx = _Ctx()
    asyncio.run(nzbot.on_text(upd, ctx))

    # 1) agentga "so'rov yuborildi" javobi keldi (AttributeError EMAS)
    assert any("administrator" in r.lower() for r in upd.message.replies), upd.message.replies
    # 2) nz_bind_request qatori yozildi (web ekranida ko'rinadi)
    with _db.get_conn() as conn:
        rows = conn.execute("SELECT code, chat_id, status FROM nz_bind_request").fetchall()
    assert len(rows) == 1 and rows[0]["chat_id"] == 999 and rows[0]["status"] == "pending"
    # 3) adminга tugmali xabar ketdi
    admin_msgs = [m for m in ctx.application.bot.sent if m[0] == 700]
    assert admin_msgs and admin_msgs[0][2] is not None    # reply_markup (Ha/Yo'q) bor


def test_wrong_code_still_replies(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import importlib
    import db as _db
    importlib.reload(_db)
    import nazorat.storage as storage
    importlib.reload(storage)
    with _db.get_conn() as conn:
        storage.init_nz_tables(conn)
    import nazorat.bot as nzbot
    importlib.reload(nzbot)
    monkeypatch.setattr(nzbot, "ADMIN_IDS", {700})

    upd = _Update("YOLGON-KOD-XXX", chat_id=111)
    asyncio.run(nzbot.on_text(upd, _Ctx()))
    assert any("noto'g'ri" in r.lower() or "notogri" in r.lower().replace("'", "")
               for r in upd.message.replies), upd.message.replies
    with _db.get_conn() as conn:
        n = conn.execute("SELECT COUNT(*) c FROM nz_bind_request").fetchone()["c"]
    assert n == 0                                          # noto'g'ri kod — so'rov yaratmaydi
