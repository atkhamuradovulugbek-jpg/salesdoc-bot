"""
FAIL-LOUD (0-bosqich): RunReport hisobi + watchdog xabari + _guard izolyatsiyasi.

Asosiy regressiya: 2026-07-18 kechki job bitta ketgan agent ustida qulab tushdi va
admin/supervayzer/GPS JIMGINA yuborilmadi. Shu holat qaytmasligi tekshiriladi.
"""

import asyncio
import json
import sqlite3

from nazorat import health
from nazorat.storage import get_job_run, init_nz_tables, mark_job_notified, save_job_run


# ------------------------------------------------------------------
# RunReport
# ------------------------------------------------------------------

def test_report_counts_by_status():
    r = health.RunReport("evening", "2026-07-18")
    r.start("2026-07-18T20:10:00+05:00")
    for i in range(14):
        r.note("agent", health.SENT, f"Agent{i}")
    r.note("agent", health.FAIL, "Aisha", KeyError("d0_152"))
    r.note("agent", health.UNBOUND, "Behruz")

    t = r.totals()
    assert t[health.SENT] == 14
    assert t[health.FAIL] == 1
    assert t[health.UNBOUND] == 1
    assert r.failed is True


def test_report_ok_run_not_failed():
    r = health.RunReport("morning", "2026-07-18")
    r.note("agent", health.SENT, "Bahodir")
    r.note("agent", health.DUP, "Rano")          # avval yuborilgan — xato emas
    r.note("signal", health.SKIP, "Aisha")       # signal kerak bo'lmadi — xato emas
    assert r.failed is False


def test_watchdog_skip_shown_as_not_needed():
    """0-ball signali kerak bo'lmasa — 'kerak bo'lmadi', '0/16' kabi chalkash emas."""
    r = health.RunReport("evening", "2026-07-18")
    r.start("2026-07-18T20:10:00+05:00")
    r.note("agent", health.SENT, "Bahodir")
    for i in range(16):
        r.note("signal", health.SKIP, f"A{i}")
    txt = health.build_watchdog_text("evening", "18-Iyul", _row(r))
    assert "kerak bo'lmadi" in txt
    assert "0/16" not in txt
    assert "Hammasi joyida" in txt


def test_watchdog_dup_only_block_is_ok():
    r = health.RunReport("evening", "2026-07-18")
    r.start("2026-07-18T20:10:00+05:00")
    r.note("agent", health.DUP, "Bahodir")
    txt = health.build_watchdog_text("evening", "18-Iyul", _row(r))
    assert "avval yuborilgan" in txt
    assert "Hammasi joyida" in txt


def test_report_records_error_text_and_caps_list():
    r = health.RunReport("evening", "2026-07-18")
    for i in range(20):                           # MAX_ERRORS dan ko'p
        r.note("agent", health.FAIL, f"A{i}", ValueError(f"xato{i}"))
    errs = r.blocks["agent"]["errors"]
    assert len(errs) == health.MAX_ERRORS
    assert "ValueError: xato0" in errs[0]["err"]


def test_payload_roundtrip_and_last_block():
    r = health.RunReport("evening", "2026-07-18")
    r.note("agent", health.SENT, "Bahodir")
    r.note("gps", health.SENT, "city")
    data = json.loads(r.payload())
    assert data["last_block"] == "gps"
    assert data["blocks"]["agent"][health.SENT] == 1


# ------------------------------------------------------------------
# Watchdog xabari
# ------------------------------------------------------------------

def _row(rep: health.RunReport, finished: bool = True) -> dict:
    if finished:
        rep.finish("2026-07-18T20:12:00+05:00")
    return {"started_at": rep.started_at, "finished_at": rep.finished_at,
            "payload": rep.payload()}


def test_watchdog_all_ok_says_hammasi_joyida():
    r = health.RunReport("evening", "2026-07-18")
    r.start("2026-07-18T20:10:00+05:00")
    for i in range(16):
        r.note("agent", health.SENT, f"A{i}")
    r.note("admin", health.SENT)
    r.note("gps", health.SENT, "city")
    txt = health.build_watchdog_text("evening", "18-Iyul", _row(r))
    assert "Hammasi joyida" in txt
    assert "16/16" in txt
    assert "🚨" not in txt


def test_watchdog_partial_failure_names_who_and_error():
    r = health.RunReport("evening", "2026-07-18")
    r.start("2026-07-18T20:10:00+05:00")
    for i in range(14):
        r.note("agent", health.SENT, f"A{i}")
    r.note("agent", health.FAIL, "Aisha", KeyError("d0_152"))
    r.note("agent", health.FAIL, "Rano", TimeoutError("timed out"))
    txt = health.build_watchdog_text("evening", "18-Iyul", _row(r))
    assert "MUAMMO" in txt and "🚨" in txt
    assert "14/16" in txt
    assert "Aisha" in txt and "d0_152" in txt
    assert "Rano" in txt
    assert "Hammasi joyida" not in txt


def test_watchdog_unfinished_job_is_loud():
    """AYNAN 2026-07-18 holati: job yarmida qulagan — bu KO'RINISHI shart."""
    r = health.RunReport("evening", "2026-07-18")
    r.start("2026-07-18T20:10:00+05:00")
    for i in range(16):
        r.note("agent", health.SENT, f"A{i}")
    txt = health.build_watchdog_text("evening", "18-Iyul", _row(r, finished=False))
    assert "TUGAMADI" in txt
    assert "Agent kartalari" in txt          # oxirgi bosqich ko'rsatiladi
    assert "yuborilmagan" in txt
    assert "Hammasi joyida" not in txt


def test_watchdog_never_ran_is_loud():
    txt = health.build_watchdog_text("evening", "18-Iyul", None)
    assert "UMUMAN ISHLAMADI" in txt
    txt2 = health.build_watchdog_text("morning", "18-Iyul", {"started_at": None})
    assert "UMUMAN ISHLAMADI" in txt2


def test_watchdog_lists_unbound_agents():
    r = health.RunReport("evening", "2026-07-18")
    r.start("2026-07-18T20:10:00+05:00")
    r.note("agent", health.SENT, "Bahodir")
    r.note("agent", health.UNBOUND, "Behruz")
    r.note("agent", health.UNBOUND, "Gulchehra")
    txt = health.build_watchdog_text("evening", "18-Iyul", _row(r))
    assert "Ulanmagan: 2" in txt
    assert "Behruz" in txt


def test_watchdog_morning_label():
    r = health.RunReport("morning", "2026-07-18")
    r.start("2026-07-18T10:00:00+05:00")
    r.note("agent", health.SENT, "Bahodir")
    assert "ERTALABKI" in health.build_watchdog_text("morning", "18-Iyul", _row(r))


# ------------------------------------------------------------------
# nz_job_run saqlash
# ------------------------------------------------------------------

def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_nz_tables(conn)
    return conn


def test_job_run_saved_and_updated():
    conn = _db()
    r = health.RunReport("evening", "2026-07-18")
    r.start("2026-07-18T20:10:00+05:00")
    r.note("agent", health.SENT, "Bahodir")
    save_job_run(conn, r.day, r.job, r.started_at, r.finished_at, r.payload())
    row = get_job_run(conn, "2026-07-18", "evening")
    assert row["finished_at"] is None              # hali tugamagan

    r.finish("2026-07-18T20:12:00+05:00")
    save_job_run(conn, r.day, r.job, r.started_at, r.finished_at, r.payload())
    row = get_job_run(conn, "2026-07-18", "evening")
    assert row["finished_at"] == "2026-07-18T20:12:00+05:00"
    assert row["notified_at"] is None


def test_job_notified_flag_prevents_repeat():
    conn = _db()
    save_job_run(conn, "2026-07-18", "evening", "s", "f", "{}")
    mark_job_notified(conn, "2026-07-18", "evening", "2026-07-18T20:40:00+05:00")
    assert get_job_run(conn, "2026-07-18", "evening")["notified_at"] is not None


def test_job_run_missing_returns_none():
    assert get_job_run(_db(), "2026-07-18", "evening") is None


# ------------------------------------------------------------------
# _guard izolyatsiyasi (ASOSIY REGRESSIYA)
# ------------------------------------------------------------------

def test_guard_isolates_failure_and_continues():
    """Bitta agent xatosi qolgan agentlarni VA keyingi bloklarni o'ldirmasligi kerak."""
    from nazorat.jobs import _guard

    r = health.RunReport("evening", "2026-07-18")
    done: list[str] = []

    async def good(name):
        done.append(name)
        return health.SENT

    async def bad(name):
        raise KeyError("d0_152")

    async def scenario():
        for nm in ("Bahodir", "Aisha", "Rano"):
            fn = bad if nm == "Aisha" else good
            await _guard(r, "agent", lambda nm=nm, fn=fn: fn(nm), nm)
        # agentdan keyingi bloklar BARIBIR bajariladi
        await _guard(r, "admin", lambda: good("admin"))
        await _guard(r, "gps", lambda: good("gps"))

    asyncio.run(scenario())

    assert done == ["Bahodir", "Rano", "admin", "gps"]     # Aisha yiqildi, qolgani ketdi
    assert r.blocks["agent"][health.FAIL] == 1
    assert r.blocks["agent"][health.SENT] == 2
    assert r.blocks["admin"][health.SENT] == 1             # <- avval bu YUBORILMAY qolardi
    assert r.blocks["gps"][health.SENT] == 1


def test_guard_records_status_string_from_callee():
    from nazorat.jobs import _guard

    r = health.RunReport("morning", "2026-07-18")

    async def unbound():
        return health.UNBOUND

    asyncio.run(_guard(r, "agent", unbound, "Behruz"))
    assert r.blocks["agent"][health.UNBOUND] == 1
    assert r.failed is False
