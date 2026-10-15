"""
ULANISH (3-bosqich): kod aniqlash, so'rovlar (kutilyapti/muddat), ro'yxat holati.

Muhim: kutilayotgan so'rov endi BAZADA saqlanadi (avval faqat Telegram tugmasida
yashardi) — web ekranida ko'rinishi uchun. Kod o'zi ulamaydi: tasdiq shart.
"""

import sqlite3
from datetime import datetime, timedelta, timezone

from nazorat import binding
from nazorat.core.rules import Agent, AgentsConfig, Supervisor
from nazorat.storage import init_nz_tables

TZ = timezone(timedelta(hours=5))

CFG = AgentsConfig(
    agents=[Agent(sd_id="d0_51", name="Atxamuradov Bahodir", display="Bahodir",
                  league="city", code="TSH-YNB-01", area="Yunusobod"),
            Agent(sd_id="d0_99", name="Aisha Karimova", display="Aisha",
                  league="region", code="TVL-CHQ-01", observe_only=True)],
    supervisors=[Supervisor(code="SPV-TSH-01", name="Shahar supervayzeri", league="city")],
)


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_nz_tables(conn)
    conn.execute("CREATE TABLE agents (sd_id TEXT PRIMARY KEY, name TEXT, active TEXT)")
    conn.executemany("INSERT INTO agents VALUES (?,?,?)",
                     [("d0_51", "Bahodir", "Y"), ("d0_99", "Aisha", "Y")])
    return conn


def _patch_cfg(monkeypatch):
    monkeypatch.setattr(binding, "load_agents", lambda: CFG)
    import nazorat.roster as r
    monkeypatch.setattr(r, "load_agents", lambda: CFG)


# ── kod aniqlash ──

def test_resolve_agent_and_supervisor(monkeypatch):
    _patch_cfg(monkeypatch)
    assert binding.resolve_code("TSH-YNB-01") == ("agent", "d0_51", "Atxamuradov Bahodir")
    assert binding.resolve_code("spv-tsh-01") == ("supervisor", None, "Shahar supervayzeri")
    assert binding.resolve_code("YO'Q-KOD") is None
    assert binding.resolve_code("") is None


def test_display_name_uses_short(monkeypatch):
    _patch_cfg(monkeypatch)
    assert binding.display_name("TSH-YNB-01") == "Bahodir"      # familiya emas
    assert binding.display_name("NOMA'LUM") == "NOMA'LUM"


# ── so'rovlar ──

def test_create_request_visible_as_pending(monkeypatch):
    _patch_cfg(monkeypatch)
    conn = _db()
    binding.create_request(conn, "TSH-YNB-01", 555, "@bahodir")
    p = binding.pending_requests(conn)
    assert len(p) == 1
    assert p[0]["name"] == "Bahodir" and p[0]["who"] == "@bahodir"
    assert p[0]["chat_id"] == 555 and p[0]["role"] == "agent"


def test_duplicate_request_updates_not_duplicates(monkeypatch):
    """Agent kodni ikki marta yuborsa — ikkita so'rov ko'rinmasin."""
    _patch_cfg(monkeypatch)
    conn = _db()
    a = binding.create_request(conn, "TSH-YNB-01", 555, "@b")
    b = binding.create_request(conn, "TSH-YNB-01", 555, "@b2")
    assert a == b
    assert len(binding.pending_requests(conn)) == 1


def test_expired_request_disappears(monkeypatch):
    _patch_cfg(monkeypatch)
    conn = _db()
    binding.create_request(conn, "TSH-YNB-01", 555, "@b")
    old = (datetime.now(TZ) - timedelta(hours=1)).isoformat(timespec="seconds")
    conn.execute("UPDATE nz_bind_request SET expires_at=?", (old,))
    assert binding.pending_requests(conn) == []                 # muddati o'tdi
    row = conn.execute("SELECT status FROM nz_bind_request").fetchone()
    assert row["status"] == "expired"


def test_request_for_unknown_code_has_no_role(monkeypatch):
    _patch_cfg(monkeypatch)
    conn = _db()
    binding.create_request(conn, "YOLGON-01", 777, "@x")
    p = binding.pending_requests(conn)
    assert p[0]["role"] is None                                 # kod topilmadi


# ── ro'yxat (yashil/qizil) ──

def test_connection_list_marks_connected(monkeypatch):
    _patch_cfg(monkeypatch)
    conn = _db()
    conn.execute("INSERT INTO nz_bindings (code, chat_id, role, sd_id, bound_at) "
                 "VALUES ('TSH-YNB-01', 555, 'agent', 'd0_51', '2026-07-30T10:00:00+05:00')")
    rows = binding.connection_list(conn)
    by_code = {r["code"]: r for r in rows}
    assert by_code["TSH-YNB-01"]["connected"] is True
    assert by_code["TSH-YNB-01"]["chat_id"] == 555
    assert by_code["TVL-CHQ-01"]["connected"] is False
    assert by_code["SPV-TSH-01"]["connected"] is False
    assert by_code["SPV-TSH-01"]["role"] == "supervisor"


def test_connection_list_excludes_departed_agent(monkeypatch):
    """Ishdan ketgan agent ulanish ro'yxatida ko'rinmaydi (roster qoidasi)."""
    _patch_cfg(monkeypatch)
    conn = _db()
    conn.execute("UPDATE agents SET active='N' WHERE sd_id='d0_99'")
    codes = [r["code"] for r in binding.connection_list(conn)]
    assert "TVL-CHQ-01" not in codes
    assert "TSH-YNB-01" in codes and "SPV-TSH-01" in codes


def test_connection_list_puts_not_connected_first(monkeypatch):
    _patch_cfg(monkeypatch)
    conn = _db()
    conn.execute("INSERT INTO nz_bindings (code, chat_id, role, sd_id, bound_at) "
                 "VALUES ('TSH-YNB-01', 555, 'agent', 'd0_51', 'x')")
    rows = binding.connection_list(conn)
    assert rows[0]["connected"] is False        # e'tibor kerak bo'lganlar tepada


def test_observe_flag_passed_through(monkeypatch):
    _patch_cfg(monkeypatch)
    rows = binding.connection_list(_db())
    by_code = {r["code"]: r for r in rows}
    assert by_code["TVL-CHQ-01"]["observe"] is True
    assert by_code["TSH-YNB-01"]["observe"] is False
