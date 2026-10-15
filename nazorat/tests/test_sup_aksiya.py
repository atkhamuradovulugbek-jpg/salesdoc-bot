"""
SUPERVAYZER AKSIYA jadvallari testlari (2026-10-08).

Tarmoq yo'q: soxta update/bot, vaqtinchalik SQLite.
  • oylik aksiya — 05.10 dan, prognoz — ish kunlari kalendari bo'yicha DINAMIK
  • kunlik savdo — SOF (qaytim ayirilgan), Monitor bilan bir xil
  • Ball/Toy yo'q; barcha SUP yo'llari (oylik/kunlik/hozirgi holat/namuna/20:10) yangi jadvalda
  • qarz-vazvrat va GPS yo'llari o'zgarmagan; rollar aralashmaydi
"""

import asyncio
import inspect
import os
import tempfile
from datetime import date
from io import BytesIO
from types import SimpleNamespace

import dotenv

dotenv.load_dotenv = lambda *a, **k: False
for k, v in {"NAZORAT_BOT_TOKEN": "test", "TELEGRAM_BOT_TOKEN": "test",
             "SALESDOC_BASE_URL": "http://salesdoc.invalid", "SALESDOC_LOGIN": "t",
             "SALESDOC_PASSWORD": "t", "DATA_DIR": tempfile.mkdtemp(prefix="nz-sup-")}.items():
    os.environ.setdefault(k, v)

import pytest  # noqa: E402
from PIL import Image  # noqa: E402

import db  # noqa: E402
from nazorat import aksiya_cards as ac  # noqa: E402
from nazorat import bot, jobs, storage  # noqa: E402
from nazorat import sup_cards as sc  # noqa: E402
from nazorat.build import DayContext  # noqa: E402
from nazorat.core.rules import Agent, AgentsConfig  # noqa: E402

OCT7 = date(2026, 10, 7)
CFG = AgentsConfig(agents=[
    Agent(sd_id="c1", name="Bahodir", area="Yunusobod", league="city", code="T-C1", ball_plan=70),
    Agent(sd_id="c2", name="Saodat", area="Uchtepa", league="city", code="T-C2", ball_plan=55),
    Agent(sd_id="c3", name="Eski", area="Yashnabod", league="city", code="T-C3", ball_plan=70,
          start_date="2026-10-06", seat_changed=True),
    Agent(sd_id="r1", name="Rano", area="Chinoz", league="region", code="T-R1", ball_plan=70),
])
SD_NAMES = {"c1": "Jalolov Bahodir (Yunusobod)", "c2": "Saodat Hakimova (Uchtepa)",
            "c3": "Samiya Yorbekova (Yashnabod)",
            "r1": "Rashidova Rano (Chinoz+Oqqurg'on+Quyi Chirchiq)"}
SUP_CITY, SUP_REGION = "SPV-TSH-01", "SPV-TVL-01"          # haqiqiy YAML kodlari (ligasi bilan)


@pytest.fixture(autouse=True)
def tmpdb(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "bot.db")
    db.init_db()
    with db.get_conn() as c:
        storage.init_nz_tables(c)
        c.executemany("INSERT INTO agents (sd_id, code_1c, name, active, updated_at) VALUES (?,?,?,?,?)",
                      [(k, "", v, "Y", "") for k, v in SD_NAMES.items()])
    yield


_seq = iter(range(1, 10**6))


def order(agent, day, total, shop="s1", status=2, ret=0.0, oid=None):
    oid = oid or f"o{next(_seq)}"
    with db.get_conn() as c:
        c.execute("""INSERT INTO orders (sd_id, date, status, agent_sd_id, client_sd_id,
                                         total_after_discount, total_returns) VALUES (?,?,?,?,?,?,?)
                     ON CONFLICT(sd_id) DO UPDATE SET status=excluded.status,
                        total_after_discount=excluded.total_after_discount,
                        total_returns=excluded.total_returns""",
                  (oid, str(day), status, agent, shop, total, ret))
    return oid


def blocks(agent, day, n):
    for i in range(n):
        order(agent, day, 300_000, shop=f"{agent}-{day}-{i}")


def ctx(day):
    return DayContext(today=day, agents_cfg=CFG)


def mrow(x, sd):
    return next(r for r in x["rows"] if r["sd_id"] == sd)


# ── Oylik: aksiya + dinamik prognoz ──────────────────────────────

def test_monthly_aksiya_from_oct5_and_forecast_x8_on_oct7():
    blocks("c1", date(2026, 10, 2), 26)                  # aksiyadan oldin — kirmaydi
    blocks("c1", date(2026, 10, 5), 8)
    blocks("c1", date(2026, 10, 6), 13)
    blocks("c1", OCT7, 16)
    r = mrow(sc.monthly_dict(ctx(OCT7), "city"), "c1")
    assert (r["aksiya"], r["aksiya_fc"]) == (37, 296)    # 37 × 24/3


def test_forecast_is_dynamic_by_calendar():
    blocks("c1", OCT7, 16)
    # 12.10 (dushanba): o'tgan ish kunlari 5,6,7,8,9,10,12 = 7 (11 — yakshanba), jami 24
    r = mrow(sc.monthly_dict(ctx(date(2026, 10, 12)), "city"), "c1")
    assert (r["aksiya"], r["aksiya_fc"]) == (16, 55)     # 16 × 24/7 = 54.86 → 55
    ag = CFG.agents[0]
    assert sc.aksiya_forecast(10, ag, date(2026, 10, 11)) == (40, 6, 24)   # yakshanba: 6 ish kuni


def test_prestart_has_no_forecast():
    blocks("c1", date(2026, 10, 3), 20)
    r = mrow(sc.monthly_dict(ctx(date(2026, 10, 3)), "city"), "c1")
    assert (r["aksiya"], r["aksiya_fc"]) == (0, None)


def test_seat_changed_agent_uses_own_start():
    blocks("c3", date(2026, 10, 5), 12)                  # avvalgi o'rindiq egasi
    blocks("c3", date(2026, 10, 6), 10)
    r = mrow(sc.monthly_dict(ctx(OCT7), "city"), "c3")
    assert (r["aksiya"], r["aksiya_fc"]) == (10, 115)    # 10 × 23/2


@pytest.mark.parametrize("asof,expect", [
    (date(2026, 11, 30), (7, 25, 25)),                   # noyabr: 25 ish kuni, oy oxiri
    (date(2028, 2, 29), (7, 25, 25)),                    # kabisa fevral: 29 kun, 25 ish kuni
    (date(2028, 2, 1), (175, 1, 25)),                    # 1-ish kuni: 7 × 25
    (date(2027, 2, 27), (7, 24, 24)),                    # oddiy fevral: 24 ish kuni
    (date(2026, 12, 31), (7, 27, 27)),
])
def test_forecast_month_lengths(asof, expect):
    assert sc.aksiya_forecast(7, CFG.agents[0], asof) == expect


def test_monthly_keeps_strike_sort_and_sales_forecast():
    for i in range(3):
        order("c1", date(2026, 10, 5 + i), 2_000_000, shop=f"a{i}")
    order("c2", OCT7, 1_000_000)
    with db.get_conn() as c:
        c.executemany("INSERT INTO visits (date, agent_sd_id, client_sd_id, visited, has_order) "
                      "VALUES (?,?,?,?,?)",
                      [("2026-10-07", "c1", f"v{i}", 1, int(i < 2)) for i in range(4)] +
                      [("2026-10-07", "c2", f"w{i}", 1, 1) for i in range(4)])
    dc = ctx(OCT7)
    new, old = sc.monthly_dict(dc, "city"), dc.supervisor_monthly("city")
    assert [r["strike"] for r in new["rows"]] == sorted(r["strike"] for r in new["rows"])
    assert sorted(r["prognoz"] for r in new["rows"]) == sorted(r["prognoz"] for r in old["rows"])
    assert (new["league_sales"], new["league_prognoz"]) == (old["league_sales"], old["league_prognoz"])
    assert all("ball" not in r and "toy" not in r for r in new["rows"])


# ── Kunlik: sof savdo, aksiya, mukofot ───────────────────────────

def test_daily_net_sales_matches_monitor_with_returns():
    import aksiya_jadval as aj
    order("c1", OCT7, 1_000_000, shop="x", ret=300_000)
    order("c1", OCT7, 500_000, shop="y")
    dc = ctx(OCT7)
    r = mrow(sc.daily_dict(dc, "city"), "c1")
    assert r["sales"] == 1_200_000                                   # sof
    monitor = next(i for i in aj.compute_items("city", OCT7) if i["name"].startswith("Jalolov"))
    assert monitor["sales"] == r["sales"]
    old = next(x for x in dc.supervisor_daily("city")["rows"] if x["name"] == "Bahodir")
    assert old["sales"] == 1_500_000                                 # eski jadval qaytimni ayirmasdi


def test_daily_units_rewards_sort_and_total():
    blocks("c1", OCT7, 16)
    blocks("r1", OCT7, 16)
    order("c2", OCT7, 9_000_000, shop="big")                         # 30 aksiya
    oid = order("c2", OCT7, 300_000, shop="z", status=1)
    order("c2", OCT7, 300_000, shop="z", status=3, oid=oid)          # status o'zgardi — 1 marta
    order("c2", OCT7, 900_000, shop="q", status=4)                   # to'liq vazvrat — kirmaydi
    city = sc.daily_dict(ctx(OCT7), "city")
    assert [r["sd_id"] for r in city["rows"]][:2] == ["c2", "c1"]
    assert (mrow(city, "c2")["units"], mrow(city, "c2")["reward"]) == (31, 206_667)
    assert (mrow(city, "c1")["units"], mrow(city, "c1")["reward"]) == (16, 106_667)
    assert city["league_today"] == 9_300_000 + 4_800_000
    reg = sc.daily_dict(ctx(OCT7), "region")
    assert (mrow(reg, "r1")["units"], mrow(reg, "r1")["reward"]) == (16, 85_333)
    assert all("ball" not in r and "toy" not in r for r in city["rows"])


def test_render_full_names_no_clipping():
    blocks("r1", OCT7, 3)
    for fn, lg in ((sc.monthly_png, "region"), (sc.daily_png, "region"), (sc.monthly_png, "city")):
        assert Image.open(BytesIO(fn(ctx(OCT7), lg))).size[0] == 1080
    c = sc.Card()
    area = "Chinoz+Oqqurg'on+Quyi Chirchiq"
    assert c.d.textlength(area, font=sc._fit(c, area, 18, 12, sc.NAME_W, False)) <= sc.NAME_W


# ── 20:10 va barcha SUP yo'llari ─────────────────────────────────

def test_evening_job_uses_new_tables_and_debt_morning_unchanged():
    ev = inspect.getsource(jobs.evening_job)
    assert "sup_monthly_png(dc, lg)" in ev and "sup_daily_png(dc, lg)" in ev
    assert "render_supervisor_monthly(" not in ev and "render_supervisor_daily(" not in ev
    assert "render_supervisor_debt(dc.supervisor_debt(lg))" in inspect.getsource(jobs.morning_job)
    assert "_gps_summary(app, day, today, rep)" in ev                  # GPS xulosa joyida


def test_sup_png_fallback_if_module_missing(monkeypatch):
    monkeypatch.setattr(jobs, "sup_cards", None)
    monkeypatch.setattr(jobs, "render_supervisor_monthly", lambda x: b"OLD")
    assert jobs.sup_monthly_png(ctx(OCT7), "city") == b"OLD"


class Msg:
    def __init__(self):
        self.photos, self.texts = [], []

    async def reply_photo(self, photo, caption=None, reply_markup=None, **k):
        self.photos.append((photo, caption, reply_markup))

    async def reply_text(self, text, reply_markup=None, **k):
        self.texts.append((text, reply_markup))


def _upd(chat, text=None):
    m = Msg()
    m.text = text
    return SimpleNamespace(effective_chat=SimpleNamespace(id=chat), effective_user=None, message=m)


def bind(code, chat, role, sd=None):
    with db.get_conn() as c:
        storage.bind_code(c, code, chat, role, sd, "2026-10-01T00:00:00+05:00")


def _kb(kb):
    return [getattr(b, "text", b) for r in kb.keyboard for b in r]


@pytest.fixture()
def sup_env(monkeypatch):
    monkeypatch.setattr(bot, "DayContext", lambda today=None, **k: DayContext(today=today or OCT7,
                                                                               agents_cfg=CFG))
    monkeypatch.setattr(bot, "sup_monthly_png", lambda dc, lg: f"M:{lg}".encode())
    monkeypatch.setattr(bot, "sup_daily_png", lambda dc, lg: f"D:{lg}".encode())

    async def refresh(*a, **k):
        return True, "ok"
    monkeypatch.setattr(bot, "quick", SimpleNamespace(refresh=refresh, last_any_sync=lambda c: None,
                                                      seconds_since=lambda x: 0, age_text=lambda a: ""))
    bind(SUP_CITY, 333, "supervisor"); bind(SUP_REGION, 444, "supervisor")


def _on_text(chat, text):
    u = _upd(chat, text)
    asyncio.run(bot.on_text(u, SimpleNamespace(application=SimpleNamespace(bot_data={}))))
    return u.message


@pytest.mark.parametrize("button,expect,cap", [
    ("📊 Oylik jadval", b"M:city", "📊 Oylik jadval · strike + oy savdo + aksiya"),
    ("📋 Kunlik jadval", b"D:city", "📋 Kunlik jadval · bugungi sof savdo/aksiya/vizit"),
    ("⚡ Hozirgi holat", b"D:city", "📋 Kunlik jadval · bugungi sof savdo/aksiya/vizit"),
])
def test_sup_buttons_use_new_tables_own_league(sup_env, button, expect, cap):
    m = _on_text(333, button)
    photo, caption, kb = m.photos[0]
    assert photo == expect and caption.startswith(cap) and "ball" not in caption.lower()
    assert _kb(kb) == _kb(bot.SUPERVISOR_KB)
    assert _on_text(444, button).photos[0][0] == expect.replace(b"city", b"region")


def test_sup_menu_and_help_own_league_only(sup_env):
    assert _kb(bot.SUPERVISOR_KB) == ["📊 Oylik jadval", "📋 Kunlik jadval", "💳 Qarz-vazvrat",
                                      "⚡ Hozirgi holat", "❓ Yordam"]
    text, kb = _on_text(333, "❓ Yordam").texts[0]
    assert "Ligangiz: <b>shahar</b>" in text and "100 000÷15" in text and "5 000" in text
    assert "80 000" not in text and "4 000" not in text and "ball" not in text.lower()
    assert _kb(kb) == _kb(bot.SUPERVISOR_KB)
    u = _upd(444)
    asyncio.run(bot.cmd_yordam(u, None))                              # /yordam
    text = u.message.texts[0][0]
    assert "viloyat" in text and "80 000÷15" in text and "100 000" not in text


def test_unknown_league_supervisor_gets_no_tariff_or_table(sup_env):
    bind("SPV-NOMA-99", 555, "supervisor")                            # config'da yo'q kod
    assert _on_text(555, "📊 Oylik jadval").texts[0][0] == "Liga aniqlanmadi."
    text, _ = _on_text(555, "❓ Yordam").texts[0]
    assert "aniqlanmadi" in text and "÷15" not in text


def test_start_and_old_button_refresh_sup_menu(sup_env):
    u = _upd(333)
    asyncio.run(bot.cmd_start(u, None))
    assert _kb(u.message.texts[0][1]) == _kb(bot.SUPERVISOR_KB)
    assert _kb(_on_text(333, "📅 Oylik ball").texts[0][1]) == _kb(bot.SUPERVISOR_KB)


def test_roles_do_not_mix(sup_env):
    bind("T-C1", 111, "agent", "c1")
    m = _on_text(111, "📊 Oylik jadval")                               # agentda SUP tugmasi ishlamaydi
    assert m.photos == [] and "📊 Oylik jadval" not in _kb(m.texts[0][1])
    m = _on_text(333, "📊 Bugungi natija")                             # SUPda agent tugmasi ishlamaydi
    assert m.photos == [] and _kb(m.texts[0][1]) == _kb(bot.SUPERVISOR_KB)


def test_admin_sample_to_supervisor_uses_new_tables(sup_env, monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", {999})
    monkeypatch.setattr(bot, "render_supervisor_debt", lambda x: b"QARZ")
    monkeypatch.setattr(bot.sup_plan, "plan_png", lambda dc, lg: f"P:{lg}".encode())
    sent = []

    class FB:
        async def send_photo(self, chat, photo, caption=None, **k):
            sent.append((chat, photo, caption))

        async def send_message(self, chat, text, **k):
            sent.append((chat, None, text))

    async def answer(*a, **k):
        return None
    q = SimpleNamespace(message=SimpleNamespace(chat=SimpleNamespace(id=999)), data=f"nzsample:{SUP_CITY}",
                        answer=answer)
    asyncio.run(bot.on_send_sample(SimpleNamespace(callback_query=q),
                                   SimpleNamespace(application=SimpleNamespace(bot=FB()))))
    photos = [p for chat, p, _ in sent if chat == 333 and p]
    assert photos == [b"M:city", b"D:city", b"P:city", b"QARZ"]


# ── Supervayzer PLAN JADVALI (2026-10-15, yo'nalish plani) ───────

def test_sup_plan_numbers(monkeypatch):
    from nazorat import sup_plan as sp
    monkeypatch.setattr(sp, "monthly_plan", lambda: {"city": 270_000_000, "region": 1_000_000_000})
    order("c1", date(2026, 10, 6), 6_000_000)
    order("c1", OCT7, 3_000_000)
    order("c2", OCT7, 9_000_000)
    x = sp.plan_dict(ctx(OCT7), "city")
    # oktabr: 27 ish kuni (yakshanbasiz); 7-oktabrgacha 6 kun ishlandi, 21 qoldi
    assert (x["wd_total"], x["wd_passed"], x["wd_rem"]) == (27, 6, 21)
    assert (x["done"], x["today"]) == (18_000_000, 12_000_000)
    assert x["need_today"] == 12_000_000          # (270 − 6) ÷ 22
    assert x["need_next"] == 12_000_000           # (270 − 18) ÷ 21
    assert x["share"] == 4_000_000                # 12 mln ÷ 3 agent
    assert (x["avg"], x["prognoz"], x["gap"]) == (3_000_000, 81_000_000, 189_000_000)
    assert [r["name"].split()[0] for r in x["focus"]] == ["Samiya", "Jalolov"]
    assert Image.open(BytesIO(sp.render(x))).size[0] == 1080


def test_sup_plan_in_evening_job_not_on_sunday():
    ev = inspect.getsource(jobs.evening_job)
    assert "sup_plan.plan_png(dc, lg)" in ev and "today.weekday() != 6" in ev
