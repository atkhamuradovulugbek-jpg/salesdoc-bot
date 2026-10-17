"""
Prezentatsiya generatori — hisob qatlami (vaqtinchalik baza, tarmoq yo'q).
Qo'lda hisoblangan kichik misol bilan har formula tekshiriladi.
"""

import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import dotenv  # noqa: E402

dotenv.load_dotenv = lambda *a, **k: False
for k, v in {"NAZORAT_BOT_TOKEN": "test", "TELEGRAM_BOT_TOKEN": "test", "SALESDOC_BASE_URL": "http://x.invalid",
             "SALESDOC_LOGIN": "t", "SALESDOC_PASSWORD": "t",
             "DATA_DIR": tempfile.mkdtemp(prefix="pres-test-")}.items():
    os.environ.setdefault(k, v)

import pytest  # noqa: E402

import db  # noqa: E402
from nazorat import storage  # noqa: E402
from tools.presentation import compute, fromhtml, render  # noqa: E402

BAH, ABD = "d0_51", "d0_130"                 # agents.yaml dagi haqiqiy shahar o'rindiqlari
OCT = [date(2026, 10, d) for d in range(1, 13) if date(2026, 10, d).weekday() != 6]   # 10 ish kuni
_n = iter(range(1, 10**6))


def order(agent, day, total, shop, status=3, ret=0.0):
    with db.get_conn() as c:
        c.execute("""INSERT INTO orders (sd_id, date, status, agent_sd_id, client_sd_id, total_after_discount,
                     total_returns) VALUES (?,?,?,?,?,?,?)""", (f"o{next(_n)}", str(day), status, agent, shop, total, ret))


def visit(agent, day, visited, with_order):
    with db.get_conn() as c:
        for i in range(visited):
            c.execute("""INSERT INTO visits (date, agent_sd_id, client_sd_id, visited, has_order)
                         VALUES (?,?,?,?,?)""", (str(day), agent, f"{agent}-c{i}", 1, 1 if i < with_order else 0))


@pytest.fixture(autouse=True)
def tmpdb(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "bot.db")
    db.init_db()
    with db.get_conn() as c:
        storage.init_nz_tables(c)
        c.executemany("INSERT INTO agents (sd_id, code_1c, name, active, updated_at) VALUES (?,?,?,?,?)",
                      [(BAH, "", "Jalolov Bahodir (Yunusobod)", "Y", ""),
                       (ABD, "", "Abdulaziz Abdusattarov (Olmazor)", "Y", "")])
    # Bahodir: har ish kuni bitta do'konda 3 000 000 (= 10 aksiya), 30 tashrif / 15 buyurtma
    for d in OCT:
        order(BAH, d, 3_000_000, f"s{d.day}")
        visit(BAH, d, 30, 15)
    order(BAH, date(2026, 9, 10), 60_000_000, "sep")         # sentyabr (yetkazilgan)
    visit(BAH, date(2026, 9, 10), 600, 300)
    # Abdulaziz: ozgina yetmagan / 300–330 / qaytim holatlari
    order(ABD, date(2026, 10, 6), 280_000, "a1")                 # 250–299 ming
    order(ABD, date(2026, 10, 7), 310_000, "a2")                 # 300–330 ming oralig'i
    order(ABD, date(2026, 10, 8), 900_000, "a3", ret=300_000)    # sof 600 000 → 2 aksiya (3 emas)
    order(ABD, date(2026, 10, 9), 500_000, "a4", status=4)       # to'liq vazvrat — sanalmaydi
    visit(ABD, date(2026, 10, 6), 10, 3)
    yield


def _row(t, name):
    nc = min(t["namecols"])
    return next(r for r in t["rows"] if r[nc]["t"].split("\n")[0].replace(" *", "") == name)


def test_weeks_in_month_numbering():
    w = compute.weeks_in(date(2026, 10, 1), date(2026, 10, 12))
    assert [(n, d[0].day, d[-1].day) for n, d in w] == [(1, 1, 3), (2, 5, 10)]
    w = compute.weeks_in(date(2026, 11, 1), date(2026, 11, 15))          # 1-noyabr yakshanba
    assert [(n, d[0].day, d[-1].day) for n, d in w] == [(1, 2, 7), (2, 9, 14)]


def test_plan_prognoz_and_holat():
    m = compute.compute(date(2026, 10, 1), date(2026, 10, 12), "shahar", prognoz_days=26)
    r = _row(m["tables"][0], "Bahodir")
    # 30 mln × 26 ÷ 10 = 78; sentyabr 60 → +30%; plan 50 → 156%
    assert [c["t"] for c in r[1:8]] == ["30.0", "~78", "60.0", "+30%", "50", "156%", "O'syapti, plan yopiladi"]
    assert r[7]["c"] == "g"
    assert "10 ish kunlik savdo × 26 ÷ 10" in m["cover"]["src"][1]
    cal = compute.compute(date(2026, 10, 1), date(2026, 10, 12), "shahar")   # calendar: oktyabr = 27 kun
    assert _row(cal["tables"][0], "Bahodir")[2]["t"] == "~81"


def test_kim_qancha_sotdi():
    m = compute.compute(date(2026, 10, 1), date(2026, 10, 12), "shahar")
    r = _row(m["tables"][1], "Bahodir")
    # 300 tashrif / 150 buyurtma → 5.0 (yashil); chek 30 mln ÷ 150 = 200 ming; sentyabr 5.0 / 200
    assert [c["t"] for c in r[1:10]] == ["30.0", "300", "150", "5.0", "5.0", "0.0", "200", "200", "0"]
    assert r[4]["c"] == "g" and r[6]["c"] == "m"


def test_weekly_rating_formula():
    m = compute.compute(date(2026, 10, 1), date(2026, 10, 12), "shahar")
    t = m["tables"][2]
    assert t["head"][2:4] == ["1-hafta\n(1–3 okt)", "2-hafta\n(5–10 okt)"]
    r = _row(t, "Bahodir")
    # 1-hafta (aksiyasiz): reja min(1.5/1.5,1)×4=4 + b10 min(5/7,1)×2 + nol 2 → /8×10 = 9.3
    # 2-hafta: 4 + 1.43 + aksiya min(10/15,1)×2=1.33 + 2 = 8.8 ;  8.8 − 9.3 = −0.5 → ▼
    assert (r[2]["t"], r[3]["t"], r[5]["t"]) == ("9.3", "8.8", "▼")
    assert r[6]["t"] == "Reja 150% • 10 tashrifga 5.0 buyurtma • nol kun 0 • kuniga 10.0 aksiya"
    assert "8 balldan 10 ga" in t["note"]


def test_aksiya_bot_rule_and_projection():
    m = compute.compute(date(2026, 10, 1), date(2026, 10, 12), "shahar")
    r = _row(m["tables"][3], "Bahodir")
    # 7 kun × 10 aksiya × 5 000; prognoz × 24 ÷ 7
    assert [c["t"] for c in r[2:10]] == ["21.0", "70", "350 000", "7", "0", "10.0", "~240", "~1 200 000"]
    a = _row(m["tables"][3], "Abdulaziz")
    assert a[3]["t"] == "3"            # 280k→0 · 310k→1 · 900k−300k qaytim=600k→2 · status 4 sanalmaydi
    assert "7 ish kuni o'tdi, 24 dan" in m["tables"][3]["note"]


def test_near_miss_and_band():
    m = compute.compute(date(2026, 10, 1), date(2026, 10, 12), "shahar")
    r = _row(m["tables"][5], "Abdulaziz")
    # 250–299: 1 (280k) · 300/600/900+30k oralig'i: 2 (310k va sof 600k) · do'kon-kun 3 (status 4 kirmaydi)
    assert [c["t"] for c in r[1:7]] == ["1", "0", "0", "2", "3", "67%"]


def test_seat_history_and_new_agent(monkeypatch):
    cfg = compute.load_config()
    cfg["seat_history"] = {ABD: [{"name": "Yangi", "hud": "Olmazor", "from": "2026-10-07", "to": "2026-10-31"}]}
    m = compute.compute(date(2026, 10, 1), date(2026, 10, 12), "shahar", cfg=cfg)
    r = _row(m["tables"][0], "Yangi")
    assert r[0]["t"].startswith("Yangi *") and r[3]["t"] == "—" and r[4]["t"] == "—"
    assert "Yangi agent: Yangi (7-oktyabrdan)" in m["tables"][0]["note"]


def test_overrides_and_render_end_to_end():
    ov = {"xulosa": [{"title": "Qo'lda sarlavha"}], "final": {"f3": "Keyingi majlis — dushanba"}}
    m = compute.compute(date(2026, 10, 1), date(2026, 10, 12), "shahar", overrides=ov)
    assert m["xulosa"]["cards"][0][0] == "Qo'lda sarlavha" and m["final"]["f3"] == "Keyingi majlis — dushanba"
    html = render.render(m)
    back = fromhtml.parse(html)
    assert back["cover"]["topbar"] == "SHAHAR LIGASI  •  1–12 OKTYABR 2026"
    assert back["final"]["big"].startswith("17 ish kuni qoldi")
    assert len(back["tables"]) == 6 and "lgRing" in html
