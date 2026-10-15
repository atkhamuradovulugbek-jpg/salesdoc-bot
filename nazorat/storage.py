"""
storage.py — nazorat botining o'z jadvallari (asosiy bot.db ichida, nz_ prefiksi).

nz_bindings        — kod ↔ Telegram chat bog'lanishi (agent/supervayzer/admin)
nz_sent_log        — yuborilgan xabarlar jurnali (idempotentlik: qayta ishga
                     tushganda dublikat yubormaslik)
nz_balance_history — har kuni har mijoz qarz qoldig'i (qarz YOSHI shundan chiqadi)
nz_month_results   — oy yakunlari (podium/o'sish g'oliblari, "ketma-ket 2 oy yo'q"
                     qoidasi tarixdan tekshiriladi), admin tasdig'i holati
nz_raw_cache       — Sales Doctor xom javoblari (zlib siqilgan, audit uchun)
"""

import json
import sqlite3
import zlib
from datetime import date, timedelta

RAW_CACHE_KEEP_DAYS = 60


def init_nz_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS nz_bindings (
            code        TEXT PRIMARY KEY,
            chat_id     INTEGER NOT NULL,
            role        TEXT NOT NULL DEFAULT 'agent',   -- agent / supervisor / admin
            sd_id       TEXT,
            bound_at    TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS nz_sent_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            day         TEXT NOT NULL,          -- hisobot sanasi (YYYY-MM-DD)
            kind        TEXT NOT NULL,          -- morning / evening / group_daily / alert:...
            target      TEXT NOT NULL,          -- chat_id yoki 'group'
            sent_at     TEXT NOT NULL,
            UNIQUE(day, kind, target)
        );

        CREATE TABLE IF NOT EXISTS nz_balance_history (
            day             TEXT NOT NULL,
            client_sd_id    TEXT NOT NULL,
            balance         REAL DEFAULT 0,
            PRIMARY KEY (day, client_sd_id)
        );

        CREATE TABLE IF NOT EXISTS nz_month_results (
            year        INTEGER NOT NULL,
            month       INTEGER NOT NULL,
            league      TEXT NOT NULL,
            payload     TEXT NOT NULL,          -- JSON: winners, growth, toy, kpi
            confirmed   INTEGER DEFAULT 0,      -- admin /tasdiqla bosdimi
            created_at  TEXT NOT NULL,
            PRIMARY KEY (year, month, league)
        );

        CREATE TABLE IF NOT EXISTS nz_raw_cache (
            day         TEXT NOT NULL,
            method      TEXT NOT NULL,
            payload     BLOB,                   -- zlib(json)
            saved_at    TEXT NOT NULL,
            PRIMARY KEY (day, method)
        );

        CREATE TABLE IF NOT EXISTS nz_agent_terms (
            sd_id           TEXT PRIMARY KEY,   -- o'rindiq (agent sd_id)
            sd_name         TEXT,               -- oxirgi ko'rilgan Sales Doctor ismi
            short_name      TEXT,               -- avtomatik qisqa ism (o'zgarishda)
            start_date      TEXT,               -- joriy agent shu sanadan (yangi bo'lsa); NULL = eski/to'liq oy
            observe_until   TEXT,               -- kuzatuv rejimi shu sanagacha (yangi agentning 1-to'liq oyi)
            is_new          INTEGER DEFAULT 0,  -- 1 = o'rindiqda agent ALMASHDI (aniqlangan)
            notified        INTEGER DEFAULT 1,  -- admin xabardor qilindimi (0 = kutmoqda)
            updated_at      TEXT
        );

        -- VAZIFA NAVBATI (2-bosqich): web hech narsa bajarmaydi — shu jadvalga
        -- "vazifa" yozadi, nazorat boti (yagona yozuvchi) bajaradi. Sync kechki
        -- hisobot vaqtida (blackout) navbatda kutadi.
        CREATE TABLE IF NOT EXISTS nz_jobs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            kind         TEXT NOT NULL,           -- sync_fast/sync_full/bind_approve/...
            payload      TEXT,                    -- JSON
            status       TEXT NOT NULL DEFAULT 'pending',  -- pending/running/done/error
            requested_by TEXT,                    -- 'web' / 'telegram'
            created_at   TEXT NOT NULL,
            started_at   TEXT,
            finished_at  TEXT,
            result       TEXT
        );

        -- ULANISH SO'ROVLARI (3-bosqich): agent kod yozganda shu yerga tushadi.
        -- Avval "kutilyapti" holati faqat Telegram tugmasida yashardi — web'da
        -- ko'rinishi uchun bazada saqlanadi. Kod bir martalik + muddatli.
        CREATE TABLE IF NOT EXISTS nz_bind_request (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            code         TEXT NOT NULL,
            chat_id      INTEGER NOT NULL,
            who          TEXT,                    -- @username yoki ism (kim so'radi)
            role         TEXT,                    -- agent / supervisor
            sd_id        TEXT,
            requested_at TEXT NOT NULL,
            expires_at   TEXT NOT NULL,
            status       TEXT NOT NULL DEFAULT 'pending',  -- pending/approved/rejected/expired
            decided_at   TEXT,
            decided_by   TEXT                     -- 'web' / 'telegram'
        );

        -- Job yurishi natijasi (FAIL-LOUD): kechki/ertalabki hisobot nima yubordi,
        -- nima xato bo'ldi, tugadimi. Watchdog (20:40/10:30) shundan xabar quradi.
        CREATE TABLE IF NOT EXISTS nz_job_run (
            day         TEXT NOT NULL,           -- hisobot sanasi
            job         TEXT NOT NULL,           -- evening / morning
            started_at  TEXT,
            finished_at TEXT,                    -- NULL = job TUGAMAGAN (qulagan)
            payload     TEXT,                    -- JSON: blok bo'yicha ok/xato/xatolar
            notified_at TEXT,                    -- watchdog xabar yuborgan vaqt (dedup)
            PRIMARY KEY (day, job)
        );

        -- «OY VARAQASI» (5-bosqich): har oy uchun ball plani + sovrin holati.
        -- Qoralama tahrirlanadi, E'LON QILINGACH MUZLAYDI (payload+checksum =
        -- huquqiy yozuv). Hisobot O'Z SANASIGA qarab varaqa oladi — iyul bonusi
        -- doim iyul qoidasi bilan hisoblanadi. Batafsil: nazorat/period.py.
        CREATE TABLE IF NOT EXISTS nz_period (
            period_ym      TEXT PRIMARY KEY,        -- '2026-08' (SANA emas: UTC oy chegarasi xatosi yo'q)
            status         TEXT NOT NULL DEFAULT 'draft',   -- draft / published
            prizes_enabled INTEGER NOT NULL DEFAULT 1,      -- 0 = PODIUM sovrini yo'q (1.5/1/0.5 mln)
            growth_enabled INTEGER NOT NULL DEFAULT 1,      -- 0 = O'SISH sovrini yo'q (700 ming)
            payload        TEXT,                    -- MUZLATILGAN JSON (e'londan keyin)
            checksum       TEXT,                    -- payload imzosi (qaysi qoida bilan hisoblangan)
            created_at     TEXT,
            updated_at     TEXT,
            updated_by     TEXT,
            published_at   TEXT,
            published_by   TEXT
        );

        CREATE TABLE IF NOT EXISTS nz_agent_plan (
            sd_id       TEXT NOT NULL,
            period_ym   TEXT NOT NULL,
            ball_plan   INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (sd_id, period_ym)
        );

        -- TUZATISH TARIXI: joriy oy varaqasi e'londan keyin ham tuzatilishi mumkin
        -- (oy tugamaguncha). Har tuzatishda AVVALGI nusxa shu yerga ko'chiriladi —
        -- "qachon nima e'lon qilingan edi" savoli javobsiz qolmasin.
        CREATE TABLE IF NOT EXISTS nz_period_history (
            period_ym      TEXT NOT NULL,
            version        INTEGER NOT NULL,
            payload        TEXT,
            checksum       TEXT,
            prizes_enabled INTEGER,
            growth_enabled INTEGER,
            published_at   TEXT,
            published_by   TEXT,
            replaced_at    TEXT NOT NULL,
            PRIMARY KEY (period_ym, version)
        );

        -- QARZ NAZORATI (2026-08-13): agent limitdan oshgani BIR MARTA xabar
        -- qilinsin. Har soatlik tekshiruvda bir xil xabar takrorlanmasligi uchun
        -- "oshgan" holati shu yerda eslab qolinadi.
        CREATE TABLE IF NOT EXISTS nz_debt_state (
            sd_id       TEXT PRIMARY KEY,
            over        INTEGER NOT NULL DEFAULT 0,   -- 1 = hozir limitdan oshgan
            debt        REAL,
            changed_at  TEXT
        );

        CREATE TABLE IF NOT EXISTS nz_gps_episodes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            sd_id       TEXT NOT NULL,
            day         TEXT NOT NULL,           -- YYYY-MM-DD
            last_seen   TEXT NOT NULL,           -- yo'qolishdan oldingi oxirgi faollik (ISO)
            level       TEXT NOT NULL,           -- yellow / red
            alerted_at  TEXT NOT NULL,
            red_at      TEXT,
            acked_at    TEXT,
            acked_by    INTEGER,
            reason      TEXT,
            returned_at TEXT,
            escalated_at TEXT,
            UNIQUE(sd_id, day, last_seen)
        );
    """)
    _add_missing_columns(conn)


# Jadval ALLAQACHON mavjud bo'lsa `CREATE TABLE IF NOT EXISTS` yangi ustunni
# QO'SHMAYDI — shuning uchun keyin qo'shilgan ustunlar shu yerda sanaladi.
# Idempotent: bor bo'lsa jimgina o'tkazib yuboriladi.
_LATER_COLUMNS = [
    ("nz_period", "growth_enabled", "INTEGER NOT NULL DEFAULT 1"),
    ("nz_period", "version", "INTEGER NOT NULL DEFAULT 1"),
]


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    for table, col, decl in _LATER_COLUMNS:
        try:
            have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            if have and col not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
        except sqlite3.Error:                     # noqa: BLE001 — jadval yo'q/qulf
            pass


# ------------------------------------------------------------------
# Kod ulash (bindings)
# ------------------------------------------------------------------

def bind_code(conn: sqlite3.Connection, code: str, chat_id: int, role: str,
              sd_id: str | None, now: str) -> int | None:
    """
    Kodni chatga bog'laydi. Kod avval boshqa chatga ulangan bo'lsa,
    eski chat_id qaytariladi (adminga xabar berish uchun), bog'lanish yangilanadi.
    """
    old = conn.execute("SELECT chat_id FROM nz_bindings WHERE code=?", (code,)).fetchone()
    old_chat = old["chat_id"] if old and old["chat_id"] != chat_id else None
    conn.execute("""
        INSERT INTO nz_bindings (code, chat_id, role, sd_id, bound_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET
            chat_id=excluded.chat_id, role=excluded.role,
            sd_id=excluded.sd_id, bound_at=excluded.bound_at
    """, (code, chat_id, role, sd_id, now))
    return old_chat


def binding_by_chat(conn: sqlite3.Connection, chat_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM nz_bindings WHERE chat_id=?", (chat_id,)
    ).fetchone()


def chat_for_sd_id(conn: sqlite3.Connection, sd_id: str) -> int | None:
    row = conn.execute(
        "SELECT chat_id FROM nz_bindings WHERE sd_id=? AND role='agent'", (sd_id,)
    ).fetchone()
    return row["chat_id"] if row else None


def list_bindings(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Barcha ulanishlar (admin ko'rish/uzish uchun)."""
    return conn.execute(
        "SELECT code, chat_id, role, sd_id, bound_at FROM nz_bindings ORDER BY role, code"
    ).fetchall()


def unbind(conn: sqlite3.Connection, code: str) -> int | None:
    """Kodni uzadi (o'chiradi). Qaytadi: uzilgan chat_id (agentni ogohlantirish uchun)."""
    row = conn.execute("SELECT chat_id FROM nz_bindings WHERE code=?", (code,)).fetchone()
    conn.execute("DELETE FROM nz_bindings WHERE code=?", (code,))
    return row["chat_id"] if row else None


def chat_for_supervisor(conn: sqlite3.Connection, code: str) -> int | None:
    """Supervayzer kodiga bog'langan chat (v2'da ulanadi; ulanmagan bo'lsa None)."""
    if not code:
        return None
    row = conn.execute(
        "SELECT chat_id FROM nz_bindings WHERE code=? AND role='supervisor'", (code,)
    ).fetchone()
    return row["chat_id"] if row else None


# ------------------------------------------------------------------
# Idempotent yuborish jurnali
# ------------------------------------------------------------------

def already_sent(conn: sqlite3.Connection, day: str, kind: str, target: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM nz_sent_log WHERE day=? AND kind=? AND target=?",
        (day, kind, target),
    ).fetchone()
    return row is not None


def mark_sent(conn: sqlite3.Connection, day: str, kind: str, target: str, now: str) -> None:
    conn.execute("""
        INSERT OR IGNORE INTO nz_sent_log (day, kind, target, sent_at)
        VALUES (?, ?, ?, ?)
    """, (day, kind, target, now))


# ------------------------------------------------------------------
# Job yurishi (FAIL-LOUD kuzatuvi)
# ------------------------------------------------------------------

def save_job_run(conn: sqlite3.Connection, day: str, job: str, started_at: str | None,
                 finished_at: str | None, payload: str) -> None:
    """Job holatini yozadi/yangilaydi (notified_at saqlanadi)."""
    conn.execute("""
        INSERT INTO nz_job_run (day, job, started_at, finished_at, payload)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(day, job) DO UPDATE SET
            started_at=excluded.started_at,
            finished_at=excluded.finished_at,
            payload=excluded.payload
    """, (day, job, started_at, finished_at, payload))


def get_job_run(conn: sqlite3.Connection, day: str, job: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM nz_job_run WHERE day=? AND job=?", (day, job)
    ).fetchone()


def mark_job_notified(conn: sqlite3.Connection, day: str, job: str, now: str) -> None:
    conn.execute("UPDATE nz_job_run SET notified_at=? WHERE day=? AND job=?",
                 (now, day, job))


# ------------------------------------------------------------------
# Qarz tarixi va yoshi
# ------------------------------------------------------------------

def snapshot_balances(conn: sqlite3.Connection, day: str) -> int:
    """Bugungi balances jadvalini tarixga ko'chiradi. Qaytadi: yozuvlar soni."""
    cur = conn.execute("""
        INSERT OR REPLACE INTO nz_balance_history (day, client_sd_id, balance)
        SELECT ?, client_sd_id, balance FROM balances WHERE balance < 0
    """, (day,))
    return cur.rowcount


def debt_age_days(conn: sqlite3.Connection, client_sd_id: str, today: str) -> int | None:
    """
    Qarz YOSHI: oxirgi uzluksiz qarzdorlik davri necha kun.
    Tarixda eng so'nggi qarzsiz (yoki yozuvsiz) kundan keyingi davr sanaladi.
    Tarix yetarli bo'lmasa None (bot yaqinda ishga tushgan).
    """
    rows = conn.execute("""
        SELECT day FROM nz_balance_history
        WHERE client_sd_id=? AND day<=? ORDER BY day DESC LIMIT 120
    """, (client_sd_id, today)).fetchall()
    if not rows:
        return None
    days = [r["day"] for r in rows]
    # Uzluksizlikni tekshiramiz: bugungi kundan orqaga ketma-ket kunlar
    streak = 0
    expect = date.fromisoformat(today)
    for d in days:
        dd = date.fromisoformat(d)
        # 1-2 kunlik uzilishga yo'l qo'yamiz (sync o'tkazib yuborgan bo'lishi mumkin)
        if (expect - dd).days > 2:
            break
        streak = (date.fromisoformat(today) - dd).days + 1
        expect = dd - timedelta(days=1)
    return streak if streak > 0 else None


# ------------------------------------------------------------------
# Oy natijalari
# ------------------------------------------------------------------

def save_month_result(conn: sqlite3.Connection, year: int, month: int, league: str,
                      payload: dict, now: str) -> None:
    conn.execute("""
        INSERT INTO nz_month_results (year, month, league, payload, confirmed, created_at)
        VALUES (?, ?, ?, ?, 0, ?)
        ON CONFLICT(year, month, league) DO UPDATE SET
            payload=excluded.payload, created_at=excluded.created_at
    """, (year, month, league, json.dumps(payload, ensure_ascii=False), now))


def get_month_result(conn: sqlite3.Connection, year: int, month: int, league: str) -> dict | None:
    row = conn.execute("""
        SELECT payload, confirmed FROM nz_month_results
        WHERE year=? AND month=? AND league=?
    """, (year, month, league)).fetchone()
    if not row:
        return None
    data = json.loads(row["payload"])
    data["confirmed"] = bool(row["confirmed"])
    return data


def confirm_month(conn: sqlite3.Connection, year: int, month: int) -> None:
    conn.execute(
        "UPDATE nz_month_results SET confirmed=1 WHERE year=? AND month=?",
        (year, month),
    )


def last_first_place(conn: sqlite3.Connection, year: int, month: int, league: str) -> str | None:
    """O'tgan oy podium 1-o'rin sd_id (ketma-ket taqiq uchun)."""
    data = get_month_result(conn, year, month, league)
    if not data:
        return None
    winners = data.get("podium", [])
    for w in winners:
        if w.get("place") == 1:
            return w.get("sd_id")
    return None


def last_growth_winner(conn: sqlite3.Connection, year: int, month: int, league: str) -> str | None:
    data = get_month_result(conn, year, month, league)
    if not data:
        return None
    g = data.get("growth")
    return g.get("sd_id") if g else None


# ------------------------------------------------------------------
# Xom kesh (audit)
# ------------------------------------------------------------------

def save_raw(conn: sqlite3.Connection, day: str, method: str, data, now: str) -> None:
    blob = zlib.compress(json.dumps(data, ensure_ascii=False).encode(), level=6)
    conn.execute("""
        INSERT OR REPLACE INTO nz_raw_cache (day, method, payload, saved_at)
        VALUES (?, ?, ?, ?)
    """, (day, method, blob, now))
    # Eski keshni tozalash
    cutoff = (date.fromisoformat(day) - timedelta(days=RAW_CACHE_KEEP_DAYS)).isoformat()
    conn.execute("DELETE FROM nz_raw_cache WHERE day < ?", (cutoff,))


def load_raw(conn: sqlite3.Connection, day: str, method: str):
    row = conn.execute(
        "SELECT payload FROM nz_raw_cache WHERE day=? AND method=?", (day, method)
    ).fetchone()
    if not row:
        return None
    return json.loads(zlib.decompress(row["payload"]).decode())


# ------------------------------------------------------------------
# Agent almashinuvi (o'rindiqda yangi agent) — avtomatik aniqlash
# ------------------------------------------------------------------

def _short_name(sd_name: str) -> str:
    """Sales Doctor ismidan qisqa ism (birinchi so'z, hudud qavsi olib tashlanadi)."""
    if not sd_name:
        return ""
    base = sd_name.split("(")[0].strip()   # "Behruz Eshpo'latov (Mirzo...)" -> "Behruz Eshpo'latov"
    return base.split()[0] if base else sd_name


def _observe_until(start_iso: str) -> str | None:
    """KUZATUV REJIMI O'CHIRILGAN (2026-08-06, egasi qarori).

    Avval yangi agent birinchi to'liq oyi oxirigacha kuzatuvda bo'lardi: ball
    hisoblanardi, lekin PLAN VA SOVRIN qo'llanmasdi. Egasi buni bekor qildi —
    yangi agent ham birinchi kunidanoq to'liq qatnashadi.

    Funksiya SAQLANDI (qayta yoqish oson bo'lsin uchun) — endi None qaytaradi,
    ya'ni `nz_agent_terms.observe_until` bo'sh yoziladi."""
    return None


def _new_occupant_start(conn: sqlite3.Connection, sd_id: str,
                        month_first_iso: str, today_iso: str) -> str:
    """Yangi agentning boshlanish sanasi = joriy oyda oxirgi 3+ kunlik tanaffusdan
    keyingi birinchi savdo (eski agent ketib, yangi boshlaganini bildiradi).
    Tanaffus bo'lmasa — oydagi birinchi savdo. Savdo yo'q bo'lsa — bugun."""
    rows = conn.execute("""
        SELECT DISTINCT date d FROM orders
        WHERE agent_sd_id=? AND date>=? AND date<=? AND status IN (1,2,3)
        ORDER BY date
    """, (sd_id, month_first_iso, today_iso)).fetchall()
    dates = [r["d"] for r in rows]
    if not dates:
        return today_iso
    start = dates[0]
    for prev, cur in zip(dates, dates[1:]):
        if (date.fromisoformat(cur) - date.fromisoformat(prev)).days >= 3:
            start = cur
    return start


def sync_agent_terms(conn: sqlite3.Connection, sd_ids: list[str],
                     today_iso: str, now_iso: str) -> list[dict]:
    """Har o'rindiq uchun Sales Doctor ismini kuzatadi. Ism o'zgarsa — YANGI AGENT:
    start_date (birinchi savdodan) + kuzatuv rejimi belgilanadi. Birinchi ko'rishda
    (baseline) o'zgarish emas — shunchaki eslab qo'yiladi. Qaytadi: o'zgarishlar ro'yxati."""
    month_first_iso = today_iso[:8] + "01"
    changes: list[dict] = []
    for sd_id in sd_ids:
        row = conn.execute("SELECT name FROM agents WHERE sd_id=?", (sd_id,)).fetchone()
        cur_name = ((row["name"] if row else "") or "").strip()
        term = conn.execute("SELECT * FROM nz_agent_terms WHERE sd_id=?", (sd_id,)).fetchone()
        if term is None:
            conn.execute("""
                INSERT INTO nz_agent_terms (sd_id, sd_name, short_name, start_date,
                                            observe_until, is_new, notified, updated_at)
                VALUES (?, ?, ?, NULL, NULL, 0, 1, ?)
            """, (sd_id, cur_name, _short_name(cur_name), now_iso))
        elif cur_name and (term["sd_name"] or "").strip() != cur_name:
            start = _new_occupant_start(conn, sd_id, month_first_iso, today_iso)
            observe_until = _observe_until(start)
            conn.execute("""
                UPDATE nz_agent_terms SET sd_name=?, short_name=?, start_date=?,
                    observe_until=?, is_new=1, notified=0, updated_at=? WHERE sd_id=?
            """, (cur_name, _short_name(cur_name), start, observe_until, now_iso, sd_id))
            changes.append({"sd_id": sd_id, "old_name": term["sd_name"] or "—",
                            "new_name": cur_name, "short_name": _short_name(cur_name),
                            "start_date": start, "observe_until": observe_until})
    return changes


def get_agent_term(conn: sqlite3.Connection, sd_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM nz_agent_terms WHERE sd_id=?", (sd_id,)).fetchone()


def pending_term_changes(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Admin hali xabardor qilinmagan o'zgarishlar (notified=0)."""
    return conn.execute(
        "SELECT * FROM nz_agent_terms WHERE is_new=1 AND notified=0"
    ).fetchall()


def mark_terms_notified(conn: sqlite3.Connection, sd_ids: list[str], now_iso: str) -> None:
    for sd_id in sd_ids:
        conn.execute("UPDATE nz_agent_terms SET notified=1, updated_at=? WHERE sd_id=?",
                     (now_iso, sd_id))


# ------------------------------------------------------------------
# GPS trevoga epizodlari (kunduzgi yo'qolish nazorati, 2-bosqich)
# ------------------------------------------------------------------

def gps_episode_get(conn, sd_id: str, day: str, last_seen: str):
    return conn.execute(
        "SELECT * FROM nz_gps_episodes WHERE sd_id=? AND day=? AND last_seen=?",
        (sd_id, day, last_seen)).fetchone()


def gps_episode_create(conn, sd_id: str, day: str, last_seen: str, level: str, now: str) -> int:
    cur = conn.execute(
        "INSERT OR IGNORE INTO nz_gps_episodes (sd_id, day, last_seen, level, alerted_at, red_at) "
        "VALUES (?,?,?,?,?,?)",
        (sd_id, day, last_seen, level, now, now if level == "red" else None))
    if cur.lastrowid:
        return cur.lastrowid
    row = gps_episode_get(conn, sd_id, day, last_seen)
    return row["id"] if row else 0


def gps_episode_to_red(conn, eid: int, now: str) -> None:
    conn.execute("UPDATE nz_gps_episodes SET level='red', red_at=? WHERE id=?", (now, eid))


def gps_open_episodes(conn, day: str):
    """Bugungi hali 'qaytmagan' epizodlar."""
    return conn.execute(
        "SELECT * FROM nz_gps_episodes WHERE day=? AND returned_at IS NULL", (day,)).fetchall()


def gps_mark_returned(conn, eid: int, now: str) -> None:
    conn.execute("UPDATE nz_gps_episodes SET returned_at=? WHERE id=?", (now, eid))


def gps_week_count(conn, sd_id: str, since_day: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) c FROM nz_gps_episodes WHERE sd_id=? AND day>=?",
        (sd_id, since_day)).fetchone()
    return int(row["c"] or 0)


def gps_ack(conn, eid: int, chat_id: int, now: str):
    conn.execute("UPDATE nz_gps_episodes SET acked_at=?, acked_by=? WHERE id=? AND acked_at IS NULL",
                 (now, chat_id, eid))
    return conn.execute("SELECT * FROM nz_gps_episodes WHERE id=?", (eid,)).fetchone()


def gps_set_reason(conn, eid: int, reason: str) -> None:
    conn.execute("UPDATE nz_gps_episodes SET reason=? WHERE id=?", (reason[:200], eid))


def gps_unacked_red(conn, day: str, older_than: str):
    """Qizil, javob berilmagan, hali eskalatsiya qilinmagan epizodlar."""
    return conn.execute(
        "SELECT * FROM nz_gps_episodes WHERE day=? AND level='red' AND acked_at IS NULL "
        "AND escalated_at IS NULL AND COALESCE(red_at, alerted_at) <= ?",
        (day, older_than)).fetchall()


def gps_mark_escalated(conn, eid: int, now: str) -> None:
    conn.execute("UPDATE nz_gps_episodes SET escalated_at=? WHERE id=?", (now, eid))


# ------------------------------------------------------------------
# Jonli roster: Sales Doctor'da active='N' bo'lgan agentlarni ajratish
# (yangi bot yaml ro'yxatidan foydalanadi; ketgan agent shu orqali chiqariladi)
# ------------------------------------------------------------------

def inactive_sd_ids(conn, ids) -> set:
    """Yaml ro'yxatidagi sd_id'lardan agents jadvalida active!='Y' bo'lganlari.
    Jadval yo'q/bo'sh bo'lsa (test) — bo'sh (hech kim chiqarilmaydi)."""
    ids = list(ids)
    if not ids:
        return set()
    ph = ",".join("?" * len(ids))
    try:
        rows = conn.execute(
            f"SELECT sd_id FROM agents WHERE sd_id IN ({ph}) AND active IS NOT NULL AND active!='Y'",
            ids).fetchall()
    except Exception:
        return set()
    return {r["sd_id"] for r in rows}


def unknown_active_agents(conn, yaml_ids, since_day: str) -> list:
    """Sales Doctor'da faol (active='Y'), yaml ro'yxatida YO'Q, lekin since_day'dan beri
    savdosi bor agentlar (yangi ishga kirgan / o'rindiq). 'Sklad' nomlilar chiqariladi."""
    try:
        rows = conn.execute(
            "SELECT a.sd_id, a.name FROM agents a "
            "WHERE a.active='Y' AND a.sd_id IN "
            "  (SELECT DISTINCT agent_sd_id FROM orders WHERE date>=?) "
            "ORDER BY a.sd_id", (since_day,)).fetchall()
    except Exception:
        return []
    out = []
    for r in rows:
        if r["sd_id"] in yaml_ids:
            continue
        if "sklad" in (r["name"] or "").lower():
            continue
        out.append({"sd_id": r["sd_id"], "name": r["name"]})
    return out
