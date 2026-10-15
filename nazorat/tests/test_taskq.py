"""
VAZIFA NAVBATI (2-bosqich): navbatga qo'yish, takrordan himoya, blackout oynasi.

Muhim: web sync'ni O'ZI ishlatmaydi — navbatga qo'yadi. Kechki hisobot atrofida
(19:50–20:35) sync boshlanmaydi, navbatda kutadi (2026-07-15 nosozligi qaytmasin).
"""

import sqlite3
from datetime import datetime, timedelta, timezone

from nazorat import taskq
from nazorat.storage import init_nz_tables

TZ = timezone(timedelta(hours=5))


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_nz_tables(conn)
    conn.execute("CREATE TABLE sync_log (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                 "run_at TEXT, type TEXT, status TEXT, note TEXT)")
    return conn


# ── navbat ──

def test_enqueue_and_next_pending():
    conn = _db()
    jid, note = taskq.enqueue(conn, "sync_fast")
    assert jid and "navbat" in note
    job = taskq.next_pending(conn)
    assert job["kind"] == "sync_fast" and job["status"] == "pending"


def test_dedupe_blocks_double_press():
    """Foydalanuvchi tugmani ikki marta bossa — ikkinchi vazifa qo'shilmaydi."""
    conn = _db()
    jid1, _ = taskq.enqueue(conn, "sync_fast", dedupe_minutes=5)
    jid2, note = taskq.enqueue(conn, "sync_fast", dedupe_minutes=5)
    assert jid1 is not None
    assert jid2 is None and "navbatda" in note


def test_dedupe_allows_other_kind():
    conn = _db()
    taskq.enqueue(conn, "sync_fast", dedupe_minutes=5)
    jid, _ = taskq.enqueue(conn, "sync_full", dedupe_minutes=5)
    assert jid is not None


def test_mark_running_only_once():
    """Ikki ishchi bir vaqtda olsa — faqat biri bajaradi (ikki marta sync bo'lmaydi)."""
    conn = _db()
    jid, _ = taskq.enqueue(conn, "sync_fast")
    assert taskq.mark_running(conn, jid) is True
    assert taskq.mark_running(conn, jid) is False


def test_done_and_error_recorded():
    conn = _db()
    a, _ = taskq.enqueue(conn, "sync_fast")
    b, _ = taskq.enqueue(conn, "unbind", {"code": "TSH-01"})
    taskq.mark_running(conn, a); taskq.mark_done(conn, a, "ok")
    taskq.mark_running(conn, b); taskq.mark_error(conn, b, "TelegramError: chat not found")
    rows = {r["id"]: r for r in taskq.recent(conn)}
    assert rows[a]["status"] == "done" and rows[a]["result"] == "ok"
    assert rows[b]["status"] == "error" and "TelegramError" in rows[b]["result"]
    assert taskq.pending_count(conn) == 0


def test_pending_count_counts_running_too():
    conn = _db()
    jid, _ = taskq.enqueue(conn, "sync_full")
    assert taskq.pending_count(conn) == 1
    taskq.mark_running(conn, jid)
    assert taskq.pending_count(conn) == 1          # running ham "kutilmoqda"
    taskq.mark_done(conn, jid)
    assert taskq.pending_count(conn) == 0


# ── blackout (kechki hisobot tinchligi) ──

def test_blackout_covers_evening_report():
    """20:10 kechki hisobot: 19:50–20:35 oynasida tez sync BOSHLANMAYDI."""
    assert taskq.in_blackout(datetime(2026, 7, 30, 19, 49, tzinfo=TZ)) is False
    assert taskq.in_blackout(datetime(2026, 7, 30, 19, 50, tzinfo=TZ)) is True
    assert taskq.in_blackout(datetime(2026, 7, 30, 20, 9, tzinfo=TZ)) is True   # eng xavfli daqiqa
    assert taskq.in_blackout(datetime(2026, 7, 30, 20, 10, tzinfo=TZ)) is True
    assert taskq.in_blackout(datetime(2026, 7, 30, 20, 35, tzinfo=TZ)) is True
    assert taskq.in_blackout(datetime(2026, 7, 30, 20, 36, tzinfo=TZ)) is False
    assert taskq.in_blackout(datetime(2026, 7, 30, 14, 0, tzinfo=TZ)) is False


def test_blackout_covers_morning_report_too():
    """2026-07-30 review: ertalabki 10:00 hisobot ham himoyalanishi kerak edi."""
    assert taskq.in_blackout(datetime(2026, 7, 30, 9, 40, tzinfo=TZ)) is True    # 10:00 - 20
    assert taskq.in_blackout(datetime(2026, 7, 30, 10, 0, tzinfo=TZ)) is True
    assert taskq.in_blackout(datetime(2026, 7, 30, 10, 25, tzinfo=TZ)) is True
    assert taskq.in_blackout(datetime(2026, 7, 30, 10, 26, tzinfo=TZ)) is False


def test_full_sync_has_wider_window():
    """To'liq sync 10-15 daqiqa — unga kengroq oldindan zapas (45 daq)."""
    assert taskq.in_blackout(datetime(2026, 7, 30, 19, 30, tzinfo=TZ), kind="sync_fast") is False
    assert taskq.in_blackout(datetime(2026, 7, 30, 19, 30, tzinfo=TZ), kind="sync_full") is True


def test_blackout_window_text():
    a, b = taskq.blackout_window()
    assert a == "19:50" and b == "20:35"


def test_sync_skipped_but_other_jobs_run_during_blackout():
    """Blackout paytida sync navbatda qoladi, LEKIN ulanish vazifalari bajariladi."""
    conn = _db()
    taskq.enqueue(conn, "sync_fast")
    taskq.enqueue(conn, "unbind", {"code": "TSH-01"})
    job = taskq.next_pending(conn, skip_sync=True)
    assert job["kind"] == "unbind"                # sync o'tkazib yuborildi
    job2 = taskq.next_pending(conn, skip_sync=False)
    assert job2["kind"] == "sync_fast"            # oyna tugagach navbatda turadi


def test_reap_stale_running_frees_stuck_job():
    """Deploy paytida yarim qolgan 'running' vazifa tozalanadi (tugma qotib qolmasin)."""
    conn = _db()
    jid, _ = taskq.enqueue(conn, "sync_fast")
    taskq.mark_running(conn, jid)
    # started_at ni 1 soat oldinga surib qo'yamiz (tashlandiq)
    old = (datetime.now(TZ) - timedelta(hours=1)).isoformat(timespec="seconds")
    conn.execute("UPDATE nz_jobs SET started_at=? WHERE id=?", (old, jid))
    n = taskq.reap_stale(conn)
    assert n == 1
    row = taskq.recent(conn)[0]
    assert row["status"] == "error"
    # endi yangi sync qo'yish mumkin (dedupe to'smaydi)
    jid2, note = taskq.enqueue(conn, "sync_fast", dedupe_minutes=5)
    assert jid2 is not None


def test_failed_sync_can_be_retried():
    """2026-07-30 review: xato bilan tugagan vazifa QAYTA urinishga to'smaydi."""
    conn = _db()
    jid, _ = taskq.enqueue(conn, "sync_fast", dedupe_minutes=5)
    taskq.mark_running(conn, jid); taskq.mark_error(conn, jid, "sync: timeout")
    jid2, note = taskq.enqueue(conn, "sync_fast", dedupe_minutes=5)
    assert jid2 is not None                       # xatodan keyin qayta urinish mumkin


# ── sync holati ──

def test_last_sync_reads_sync_log():
    conn = _db()
    assert taskq.last_sync(conn) is None
    conn.execute("INSERT INTO sync_log (run_at, type, status, note) VALUES "
                 "('2026-07-30T12:00:00+05:00','scheduled_fast','ok','orders=2703 (skipped=0)')")
    s = taskq.last_sync(conn)
    assert s["status"] == "ok" and "2703" in s["note"] and s["type"] == "scheduled_fast"
