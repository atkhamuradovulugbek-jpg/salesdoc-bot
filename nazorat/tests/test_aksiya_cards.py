"""
AGENT AKSIYA KARTALARI testlari (2026-10-07).

Tarmoq yo'q: Telegram o'rniga soxta bot/update, baza — vaqtinchalik SQLite.
  • hisob Monitor helperi bilan (do'kon+kun, status, qaytim, pog'ona, kunlik yaxlitlash)
  • oylik daftar: oy uzunligi, biznes start (05.10), agent start, kelajak «—», JAMI
  • o'rin SAVDO bo'yicha (ball bo'yicha emas), oldingi ish kuni bilan taqqos
  • 20:10 job: har ulangan faol agentga 3 karta, 08.10 20:10 aktivatsiya, eski sana — eski to'plam
  • Happy Toy agentga hech bir yo'l bilan bormaydi (job, tugma, admin namuna callback)
"""

import asyncio
import os
import tempfile
from datetime import date, datetime
from io import BytesIO
from types import SimpleNamespace

import dotenv

dotenv.load_dotenv = lambda *a, **k: False          # haqiqiy .env o'qilmasin
for k, v in {"NAZORAT_BOT_TOKEN": "test", "TELEGRAM_BOT_TOKEN": "test",
             "SALESDOC_BASE_URL": "http://salesdoc.invalid", "SALESDOC_LOGIN": "t",
             "SALESDOC_PASSWORD": "t", "DATA_DIR": tempfile.mkdtemp(prefix="nz-aks-")}.items():
    os.environ.setdefault(k, v)

import pytest  # noqa: E402
from PIL import Image  # noqa: E402

import db  # noqa: E402
from nazorat import aksiya_cards as ac  # noqa: E402
from nazorat import bot, jobs, storage  # noqa: E402
from nazorat.build import DayContext  # noqa: E402
from nazorat.core.rules import Agent, AgentsConfig  # noqa: E402

TZ = ac.TZ
OCT7, OCT8 = date(2026, 10, 7), date(2026, 10, 8)

CFG = AgentsConfig(agents=[
    Agent(sd_id="c1", name="Bahodir", area="Yunusobod", league="city", code="T-C1", ball_plan=70),
    Agent(sd_id="c2", name="Saodat", area="Uchtepa", league="city", code="T-C2", ball_plan=70),
    Agent(sd_id="c3", name="Eski Ism", area="Yashnabod", league="city", code="T-C3", ball_plan=70,
          start_date="2026-10-06", seat_changed=True),
    Agent(sd_id="r1", name="Farangiz", area="Parkent", league="region", code="T-R1", ball_plan=70),
])
SD_NAMES = {"c1": "Jalolov Bahodir (Yunusobod)", "c2": "Saodat Hakimova (Uchtepa)",
            "c3": "Samiya Yorbekova (Yashnabod)", "r1": "Farangiz Jo'rayeva (Yangibozor +Parkent)"}


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
    """sync.py dagi bilan bir xil upsert (sd_id bo'yicha)."""
    oid = oid or f"o{next(_seq)}"
    with db.get_conn() as c:
        c.execute("""INSERT INTO orders (sd_id, date, status, agent_sd_id, client_sd_id,
                                         total_after_discount, total_returns)
                     VALUES (?,?,?,?,?,?,?)
                     ON CONFLICT(sd_id) DO UPDATE SET date=excluded.date, status=excluded.status,
                        total_after_discount=excluded.total_after_discount,
                        total_returns=excluded.total_returns""",
                  (oid, str(day), status, agent, shop, total, ret))
    return oid


def blocks(agent, day, n, start=0):
    """n ta do'konda 300 000 dan → n aksiya."""
    for i in range(n):
        order(agent, day, 300_000, shop=f"{agent}-{day}-{start + i}")


def ctx(today):
    return DayContext(today=today, agents_cfg=CFG)


def row(ledger, d):
    return next(r for r in ledger["rows"] if r[0].day == d)[1:]


# ── Kunlik hisob (Monitor helperi) ───────────────────────────────

def test_same_shop_day_pooled_then_floored():
    order("c1", OCT7, 150_000); order("c1", OCT7, 150_000)
    order("c1", OCT7, 400_000, shop="s2"); order("c1", OCT7, 300_000, shop="s2")
    order("c1", OCT7, 200_000, shop="s2")
    with db.get_conn() as c:
        assert ac.day_result(c, "c1", OCT7, "city") == (4, 0)       # 1 + 3


def test_boundary_and_no_cross_shop_or_day_pool():
    order("c1", OCT7, 299_999, shop="a"); order("c1", OCT7, 150_000, shop="b")
    order("c1", OCT7, 150_000, shop="c"); order("c1", date(2026, 10, 6), 150_000, shop="b")
    order("c1", OCT7, 300_000, shop="d")
    with db.get_conn() as c:
        assert ac.day_result(c, "c1", OCT7, "city")[0] == 1


def test_canceled_and_full_return_excluded():
    order("c1", OCT7, 300_000)
    order("c1", OCT7, 900_000, shop="x", status=4)
    order("c1", OCT7, 900_000, shop="y", status=5)
    with db.get_conn() as c:
        assert ac.day_result(c, "c1", OCT7, "city")[0] == 1


def test_status_change_counted_once():
    oid = order("c1", OCT7, 300_000, status=1)
    order("c1", OCT7, 300_000, status=2, oid=oid)
    order("c1", OCT7, 300_000, status=3, oid=oid)
    with db.get_conn() as c:
        assert ac.day_result(c, "c1", OCT7, "city")[0] == 1


@pytest.mark.parametrize("league,n,x", [
    ("city", 9, 0), ("city", 10, 50_000), ("city", 14, 70_000), ("city", 15, 100_000),
    ("city", 16, 106_667), ("city", 30, 200_000),
    ("region", 9, 0), ("region", 10, 40_000), ("region", 14, 56_000), ("region", 15, 80_000),
    ("region", 16, 85_333), ("region", 30, 160_000),
])
def test_daily_rates(league, n, x):
    ag = "c1" if league == "city" else "r1"
    blocks(ag, OCT7, n)
    with db.get_conn() as c:
        assert ac.day_result(c, ag, OCT7, league) == (n, x)


# ── Oylik daftar ─────────────────────────────────────────────────

def test_ledger_start_returns_future_and_total():
    blocks("c1", date(2026, 10, 2), 26)                 # start'dan oldin — hisobga kirmaydi
    blocks("c1", date(2026, 10, 5), 8)
    oid = order("c1", date(2026, 10, 6), 4_500_000, shop="big")  # 15 → keyin qaytim bilan 13
    order("c1", OCT7, 4_800_000, shop="z")              # 16
    order("c1", date(2026, 10, 6), 4_500_000, shop="big", ret=600_000, oid=oid)  # ertasi qaytim
    lg = ac.ledger_dict(ctx(OCT7), "c1", now=datetime(2026, 10, 7, 20, 30, tzinfo=TZ))
    assert len(lg["rows"]) == 31
    assert [row(lg, d) for d in (1, 2, 3, 4)] == [(None, None)] * 4
    assert row(lg, 5) == (8, 0) and row(lg, 6) == (13, 65_000) and row(lg, 7) == (16, 106_667)
    assert row(lg, 8) == (None, None) and row(lg, 31) == (None, None)
    assert (lg["total_units"], lg["total_reward"]) == (37, 171_667)
    assert lg["start_note"] == "Aksiya boshlangan sana: 5-oktabr 2026"
    assert "1–4 oktyabr: aksiya boshlanishidan oldin." in lg["footer"]
    assert "8–31: hali kelmagan kunlar." in lg["footer"]


def test_month_total_is_sum_of_rounded_daily_not_month_tier():
    blocks("c1", date(2026, 10, 6), 16)
    blocks("c1", OCT7, 16)
    blocks("c1", date(2026, 10, 5), 9)                  # 9 → 0, oylik 41 ga pog'ona QO'LLANMAYDI
    lg = ac.ledger_dict(ctx(OCT7), "c1")
    assert lg["total_units"] == 41
    assert lg["total_reward"] == 106_667 * 2            # 213 334 (oylik pog'ona 273 333 bo'lardi)


def test_past_eligible_zero_is_zero_not_dash():
    lg = ac.ledger_dict(ctx(OCT7), "c1")
    assert row(lg, 5) == (0, 0) and row(lg, 4) == (None, None)


def test_seat_changed_agent_counts_from_own_start():
    blocks("c3", date(2026, 10, 5), 12)                 # avvalgi o'rindiq egasining kuni
    blocks("c3", date(2026, 10, 6), 10)
    lg = ac.ledger_dict(ctx(OCT7), "c3")
    assert row(lg, 5) == (None, None) and row(lg, 6) == (10, 50_000)
    assert "hisobingiz boshlanishidan oldin" in lg["footer"]


@pytest.mark.parametrize("today,days,note", [
    (date(2026, 11, 3), 30, ""), (date(2027, 2, 10), 28, ""), (date(2028, 2, 10), 29, ""),
    (date(2026, 12, 31), 31, ""),
])
def test_month_lengths_and_no_start_note_outside_october(today, days, note):
    lg = ac.ledger_dict(ctx(today), "c1")
    assert len(lg["rows"]) == days and lg["start_note"] == note
    assert row(lg, 1) == (0, 0)                         # start'dan keyingi oy — 1-kundan hisob
    png = Image.open(BytesIO(ac.render_ledger(lg)))
    assert png.size[0] == 1080


# ── Kunlik natija: savdo, o'rin, taqqos ──────────────────────────

def test_daily_card_uses_current_sd_name_net_sales_and_units():
    order("c3", OCT7, 4_800_000, shop="q", ret=300_000)
    d = ac.daily_dict(ctx(OCT7), "c3")
    assert (d["name"], d["area"]) == ("Samiya Yorbekova", "Yashnabod")  # YAML "Eski Ism" emas
    assert d["sales"] == 4_500_000 and (d["units"], d["reward"]) == (15, 100_000)


def test_rank_is_by_net_sales_not_ball():
    # c1: brutto 3.2M, qaytim 1.0M → sof 2.2M (110% → 3 ball)
    # c2: 2.5M (125% → 3 ball). Ball teng → eski tartib brutto bo'yicha c1 ni 1 qilardi.
    order("c1", OCT7, 3_200_000, ret=1_000_000)
    order("c2", OCT7, 2_500_000)
    dc = ctx(OCT7)
    assert dc.daily_rank("c1", "today") == 1           # eski (ball) tartib
    assert ac.daily_dict(dc, "c2")["rank"] == 1 and ac.daily_dict(dc, "c1")["rank"] == 2
    assert ac.daily_dict(dc, "c1")["league_size"] == 3


def test_first_place_kept_message_and_logic():
    order("c1", date(2026, 10, 6), 5_000_000); order("c2", date(2026, 10, 6), 1_000_000)
    order("c1", OCT7, 5_000_000); order("c2", OCT7, 1_000_000)
    d = ac.daily_dict(ctx(OCT7), "c1")
    assert (d["rank"], d["prev_rank"], d["prev_label"]) == (1, 1, "Kecha")
    text, scheme, *_ = ac.rank_message(d["rank"], d["prev_rank"], d["prev_label"], d["word"])
    assert text == "Birinchi o'rinni saqladingiz. Barakalla, shu natijani davom ettiring!"
    assert "yuqori" not in text and scheme == "green"


def test_rank_movement_messages():
    up = ac.rank_message(1, 3, "Kecha", "bugun")[0]
    assert up == "Kecha 3-o'rinda edingiz, bugun 1-o'ringa ko'tarildingiz. Barakalla!"
    assert "Ertaga" in ac.rank_message(4, 2, "Kecha", "bugun")[0]
    assert "ham 3-o'rinda" in ac.rank_message(3, 3, "Kecha", "bugun")[0]
    assert ac.rank_message(2, None, "Kecha", "bugun") is None


def test_monday_compares_with_saturday_and_no_rank_on_empty_day():
    order("c1", date(2026, 10, 10), 3_000_000)          # shanba
    order("c1", date(2026, 10, 12), 3_000_000)          # dushanba
    d = ac.daily_dict(ctx(date(2026, 10, 12)), "c1")
    assert d["prev_label"] == "Shanba kuni" and d["prev_rank"] == 1
    sunday = ac.daily_dict(ctx(date(2026, 10, 11)), "c1", "kecha")
    assert sunday["rank"] is None                       # hech kim sotmagan kun — o'rin yo'q


def test_new_agent_without_previous_day_has_no_comparison():
    order("c3", date(2026, 10, 5), 1_000_000)           # o'rindiqning eski egasi
    order("c3", date(2026, 10, 6), 1_000_000)
    d = ac.daily_dict(ctx(date(2026, 10, 6)), "c3")
    assert d["rank"] == 1 and d["prev_rank"] is None


def test_render_daily_long_name_not_clipped():
    with db.get_conn() as c:
        c.execute("UPDATE agents SET name=? WHERE sd_id='c1'",
                  ("Abdurahimova Gulshoda Xudoyberdiyevna Toshkentova (Chinoz+Oqqurg'on+Quyi Chirchiq)",))
    order("c1", OCT7, 3_000_000)
    x = ac.daily_dict(ctx(OCT7), "c1")
    card = ac.Card()
    f = ac._fit(card, x["name"], 46, 28, ac.W - 2 * ac.PAD - 26)
    assert card.d.textlength(x["name"], font=f) <= ac.W - 2 * ac.PAD - 26
    assert Image.open(BytesIO(ac.render_daily(x))).size[0] == 1080


# ── Aktivatsiya va 20:10 job ─────────────────────────────────────

def test_activation_moment():
    assert not ac.active(datetime(2026, 10, 8, 20, 9, 59, tzinfo=TZ))
    assert ac.active(datetime(2026, 10, 8, 20, 10, 0, tzinfo=TZ))
    assert ac.BUSINESS_START == date(2026, 10, 5) and ac.ACTIVATION.date() == OCT8


def test_scheduler_next_evening_is_activation():
    from nazorat.run import setup_scheduler
    sched = setup_scheduler(SimpleNamespace(bot=None))
    trig = sched.get_job("evening").trigger
    nxt = trig.get_next_fire_time(None, datetime(2026, 10, 7, 22, 30, tzinfo=TZ))
    assert nxt == ac.ACTIVATION


class FakeBot:
    def __init__(self):
        self.photos, self.texts = [], []

    async def send_photo(self, chat_id, photo, caption=None, **k):
        self.photos.append((chat_id, photo, caption))
        return object()

    async def send_message(self, chat_id, text, **k):
        self.texts.append((chat_id, text))
        return object()


def bind(code, chat, role, sd):
    with db.get_conn() as c:
        storage.bind_code(c, code, chat, role, sd, "2026-10-01T00:00:00+05:00")


def _evening(monkeypatch, now, today):
    monkeypatch.setattr(ac, "active", lambda n=None: now >= ac.ACTIVATION)
    monkeypatch.setattr(jobs, "DRY_RUN", False)
    monkeypatch.setattr(ac, "agent_cards", lambda dc, sd, word="bugun": [b"NATIJA", b"REJA", b"DAFTAR"])
    monkeypatch.setattr(jobs, "render_ball_card", lambda x: b"BALL")
    monkeypatch.setattr(jobs, "render_plan_card", lambda x: b"REJA")
    monkeypatch.setattr(jobs, "render_toy_card", lambda x: b"TOY")
    app = SimpleNamespace(bot=FakeBot())
    dc = ctx(today)
    res = {ag.sd_id: asyncio.run(jobs._agent_evening_one(app, dc, ag, str(today))) for ag in dc.agents}
    return app.bot, res


def test_evening_new_set_for_every_bound_active_agent_from_activation(monkeypatch):
    bind("T-C1", 111, "agent", "c1"); bind("T-R1", 222, "agent", "r1")
    bind("SPV-X", 333, "supervisor", None)
    fb, res = _evening(monkeypatch, datetime(2026, 10, 8, 20, 10, 5, tzinfo=TZ), OCT8)
    assert res == {"c1": "sent", "c2": "unbound", "c3": "unbound", "r1": "sent"}
    assert [(c, p) for c, p, _ in fb.photos] == [(111, b"NATIJA"), (111, b"REJA"), (111, b"DAFTAR"),
                                                 (222, b"NATIJA"), (222, b"REJA"), (222, b"DAFTAR")]
    assert all(p != b"TOY" for _, p, _ in fb.photos)


def test_evening_is_idempotent(monkeypatch):
    bind("T-C1", 111, "agent", "c1")
    now = datetime(2026, 10, 8, 20, 10, 5, tzinfo=TZ)
    _evening(monkeypatch, now, OCT8)
    fb, res = _evening(monkeypatch, now, OCT8)
    assert res["c1"] == "dup" and fb.photos == []


def test_before_activation_and_late_old_date_keep_old_set(monkeypatch):
    bind("T-C1", 111, "agent", "c1")
    fb, _ = _evening(monkeypatch, datetime(2026, 10, 8, 20, 9, tzinfo=TZ), OCT8)
    assert [p for _, p, _ in fb.photos] == [b"BALL", b"REJA", b"TOY"]
    fb, _ = _evening(monkeypatch, datetime(2026, 10, 8, 20, 30, tzinfo=TZ), OCT7)   # kechikkan 07.10
    assert [p for _, p, _ in fb.photos] == [b"BALL", b"REJA", b"TOY"]


# ── Tugmalar / callback: Happy Toy agentga bormaydi ──────────────

class Msg:
    def __init__(self):
        self.photos, self.texts = [], []

    async def reply_photo(self, photo, caption=None, reply_markup=None, **k):
        self.photos.append((photo, caption))
        self.photo_kb = getattr(self, "photo_kb", []) + [reply_markup]

    async def reply_text(self, text, reply_markup=None, **k):
        self.texts.append((text, reply_markup))


def _upd(chat):
    return SimpleNamespace(effective_chat=SimpleNamespace(id=chat), effective_user=None, message=Msg())


@pytest.fixture()
def bot_env(monkeypatch):
    class FakeDate(date):
        @classmethod
        def today(cls):
            return OCT8
    monkeypatch.setattr(bot, "date", FakeDate)
    monkeypatch.setattr(bot, "DayContext", lambda today=None, **k: DayContext(today=today or OCT8,
                                                                               agents_cfg=CFG))
    monkeypatch.setattr(bot, "_today_locked", lambda: False)
    monkeypatch.setattr(bot, "AGENTS_CFG", CFG)
    bind("T-C1", 111, "agent", "c1")
    order("c1", OCT8, 4_800_000); order("c1", OCT7, 3_000_000); order("c2", OCT8, 1_000_000)

    def set_now(now):
        monkeypatch.setattr(ac, "active", lambda n=None: now >= ac.ACTIVATION)
    return set_now


def _kb_buttons(kb):
    return [getattr(b, "text", b) for r in kb.keyboard for b in r]


def test_buttons_after_activation_new_set_no_toy(bot_env):
    bot_env(datetime(2026, 10, 8, 20, 15, tzinfo=TZ))
    u = _upd(111)
    asyncio.run(bot.cmd_bugun(u, None))
    caps = [c for _, c in u.message.photos]
    assert len(caps) == 3 and caps[0].startswith("📊 Bugungi natija ·") and "ball" not in caps[0]
    assert caps[2] == "📒 Oylik aksiya daftari · Oktyabr 2026"
    u = _upd(111)
    asyncio.run(bot.cmd_kecha(u, None))
    assert len(u.message.photos) == 3 and not any("Toy" in (c or "") for _, c in u.message.photos)
    u = _upd(111)
    asyncio.run(bot.cmd_toy(u, None))
    assert u.message.photos == []
    assert "🎁 Happy Toy" not in _kb_buttons(u.message.texts[0][1])
    assert "🎁 Happy Toy" not in _kb_buttons(bot.agent_kb())


NOW_OCT7 = datetime(2026, 10, 7, 23, 40, tzinfo=TZ)     # avtomatik gate hali O'CHIQ


def test_interactive_new_flow_already_before_auto_activation(bot_env):
    bot_env(NOW_OCT7)
    assert not ac.active(NOW_OCT7)
    u = _upd(111)
    asyncio.run(bot.cmd_bugun(u, None))
    caps = [c for _, c in u.message.photos]
    assert len(caps) == 3 and caps[0].startswith("📊 Bugungi natija ·")
    assert caps[2] == "📒 Oylik aksiya daftari · Oktyabr 2026"
    kbs = u.message.photo_kb
    assert kbs[:2] == [None, None] and _kb_buttons(kbs[2]) == _kb_buttons(bot.AGENT_KB_NEW)
    u = _upd(111)
    asyncio.run(bot.cmd_toy(u, None))
    assert u.message.photos == [] and _kb_buttons(u.message.texts[0][1]) == _kb_buttons(bot.AGENT_KB_NEW)
    assert _kb_buttons(bot.agent_kb()) == _kb_buttons(bot.AGENT_KB_NEW)


def test_debt_and_returns_cards_unchanged_but_refresh_menu(bot_env):
    bot_env(NOW_OCT7)
    for cmd, cap in ((bot.cmd_qarz, "💳 Qarzdorliklar · bugungi holat"), (bot.cmd_vazvrat, "↩️ Vazvratlar ·")):
        u = _upd(111)
        asyncio.run(cmd(u, None))
        assert len(u.message.photos) == 1 and u.message.photos[0][1].startswith(cap)
        assert _kb_buttons(u.message.photo_kb[0]) == _kb_buttons(bot.AGENT_KB_NEW)


def test_start_and_free_text_give_new_menu(bot_env):
    bot_env(NOW_OCT7)
    u = _upd(111)
    asyncio.run(bot.cmd_start(u, None))
    assert _kb_buttons(u.message.texts[0][1]) == _kb_buttons(bot.AGENT_KB_NEW)
    assert _kb_buttons(_on_text(111, "salom").texts[0][1]) == _kb_buttons(bot.AGENT_KB_NEW)


def test_fallback_to_old_flow_if_module_missing(bot_env, monkeypatch):
    bot_env(NOW_OCT7)
    monkeypatch.setattr(bot, "aksiya_cards", None)
    u = _upd(111)
    asyncio.run(bot.cmd_toy(u, None))
    assert u.message.photos[0][1].startswith("🎁 Happy Toy")      # bot yiqilmaydi, eski oqim


def test_admin_sample_callback_sends_no_toy_after_activation(bot_env, monkeypatch):
    bot_env(datetime(2026, 10, 8, 20, 15, tzinfo=TZ))
    monkeypatch.setattr(bot, "ADMIN_IDS", {999})
    fb = FakeBot()

    async def answer(*a, **k):
        return None
    q = SimpleNamespace(message=SimpleNamespace(chat=SimpleNamespace(id=999)), data="nzsample:T-C1",
                        answer=answer)
    asyncio.run(bot.on_send_sample(SimpleNamespace(callback_query=q),
                                   SimpleNamespace(application=SimpleNamespace(bot=fb))))
    agent_caps = [c for chat, _, c in fb.photos if chat == 111]
    assert len(agent_caps) == 5 and not any("Toy" in (c or "") for c in agent_caps)
    assert agent_caps[2].startswith("🕐 Kechagi natija ·")


def test_non_admin_cannot_trigger_sample(bot_env, monkeypatch):
    bot_env(datetime(2026, 10, 8, 20, 15, tzinfo=TZ))
    monkeypatch.setattr(bot, "ADMIN_IDS", {999})
    fb = FakeBot()

    async def answer(*a, **k):
        return None
    q = SimpleNamespace(message=SimpleNamespace(chat=SimpleNamespace(id=111)), data="nzsample:T-C1",
                        answer=answer)
    asyncio.run(bot.on_send_sample(SimpleNamespace(callback_query=q),
                                   SimpleNamespace(application=SimpleNamespace(bot=fb))))
    assert fb.photos == [] and fb.texts == []


# ── Ball qoldiqlari agentdan olib tashlangan (08.10 20:10 dan) ───

def _on_text(chat, text):
    u = _upd(chat)
    u.message.text = text
    asyncio.run(bot.on_text(u, SimpleNamespace(application=SimpleNamespace(bot_data={}))))
    return u.message


def test_new_agent_menu_has_no_ball_or_toy():
    assert _kb_buttons(bot.AGENT_KB_NEW) == ["📊 Bugungi natija", "🕐 Kechagi natija",
                                             "💳 Qarzlar", "↩️ Vazvratlar", "❓ Yordam"]


def test_old_oylik_ball_button_gives_no_calendar_after_activation(bot_env):
    bot_env(datetime(2026, 10, 8, 20, 15, tzinfo=TZ))
    m = _on_text(111, "📅 Oylik ball")
    assert m.photos == [] and len(m.texts) == 1
    text, kb = m.texts[0]
    assert "taqvim" not in text and "ball" not in text.lower()
    assert "📅 Oylik ball" not in _kb_buttons(kb)


def test_oylik_ball_blocked_already_now(bot_env):
    bot_env(NOW_OCT7)
    m = _on_text(111, "📅 Oylik ball")
    assert m.photos == [] and "taqvim" not in m.texts[0][0]


def _help(chat, via_command=False):
    if via_command:
        u = _upd(chat)
        asyncio.run(bot.cmd_yordam(u, None))
        return u.message.texts[0]
    return _on_text(chat, "❓ Yordam").texts[0]


def test_city_agent_help_shows_only_city_rates(bot_env):
    bot_env(NOW_OCT7)
    text, kb = _help(111)                                        # c1 — shahar
    for w in ("ball", "toy", "podium", "viloyat", "4 000", "80 000", "40 000"):
        assert w not in text.lower()
    assert "shahar ligasi" in text and "5 000 so'm" in text and "100 000÷15" in text
    assert "10 ta = 50 000 so'm" in text and "15 ta = 100 000 so'm" in text
    assert "5-oktabr 2026" in text and "300 000" in text
    assert _kb_buttons(kb) == _kb_buttons(bot.AGENT_KB_NEW)


def test_region_agent_help_shows_only_region_rates(bot_env):
    bot_env(NOW_OCT7)
    bind("T-R1", 222, "agent", "r1")
    text, kb = _help(222, via_command=True)                      # /yordam
    for w in ("ball", "toy", "shahar", "5 000 so'm", "100 000", "50 000"):
        assert w not in text.lower()
    assert "viloyat ligasi" in text and "4 000 so'm" in text and "80 000÷15" in text
    assert "10 ta = 40 000 so'm" in text and "15 ta = 80 000 so'm" in text


def test_help_examples_match_reward_helper():
    import aksiya_jadval as aj
    for lg in ("city", "region"):
        t = ac.help_text(lg, "20:10")
        for n in (10, 15):
            assert f"{n} ta = {ac.fmt(aj.reward(n, lg))} so'm" in t


def test_unknown_league_help_has_no_rates(bot_env):
    bot_env(NOW_OCT7)
    with db.get_conn() as c:
        c.execute("UPDATE agents SET active='N' WHERE sd_id='c1'")    # ro'yxatdan chiqqan agent
    text, _ = _help(111)
    assert "aniqlanmadi" in text and "÷15" not in text and "5 000" not in text and "4 000" not in text
    text, kb = _help(777, via_command=True)                      # ulanmagan chat
    assert "÷15" not in text and kb is None


def test_supervisor_and_debt_roles_keep_their_menu(bot_env):
    bot_env(NOW_OCT7)
    bind("SPV-TSH-01", 333, "supervisor", None)
    m = _on_text(333, "❓ Yordam")
    assert _kb_buttons(m.texts[0][1]) == _kb_buttons(bot.SUPERVISOR_KB)
    text, kb = _help(333, via_command=True)                      # supervayzer — o'z SUP yordami
    assert _kb_buttons(kb) == _kb_buttons(bot.SUPERVISOR_KB) and "supervayzer" in text
    assert "100 000÷15" in text and "80 000÷15" not in text           # faqat o'z (shahar) ligasi
    from nazorat.core.rules import load_agents
    bind(load_agents().debt_controllers[0].code, 444, "debt", None)
    m = _on_text(444, "❓ Yordam")
    assert _kb_buttons(m.texts[0][1]) == _kb_buttons(bot.DEBT_KB)


def _alert(monkeypatch, now, today):
    monkeypatch.setattr(ac, "active", lambda n=None: now >= ac.ACTIVATION)
    monkeypatch.setattr(jobs, "DRY_RUN", False)
    app = SimpleNamespace(bot=FakeBot())
    dc = ctx(today)
    ag = next(a for a in dc.agents if a.sd_id == "c1")
    return asyncio.run(jobs._alert_one(app, dc, ag, str(today))), app.bot


def test_zero_ball_alert_removed_after_activation(monkeypatch):
    bind("T-C1", 111, "agent", "c1")                     # c1: oy boshidan savdo yo'q → 0 ball
    res, fb = _alert(monkeypatch, datetime(2026, 10, 8, 20, 10, 5, tzinfo=TZ), OCT8)
    assert res == "skip" and fb.texts == [] and fb.photos == []
    res, fb = _alert(monkeypatch, datetime(2026, 10, 7, 20, 10, 5, tzinfo=TZ), OCT7)
    assert res == "sent" and "natija bo'lmadi" in fb.texts[0][1]   # oldin — eski xatti-harakat


def test_supervisor_role_unchanged(bot_env, monkeypatch):
    bot_env(datetime(2026, 10, 8, 20, 15, tzinfo=TZ))
    bind("SPV-TSH-01", 333, "supervisor", None)
    m = _on_text(333, "📅 Oylik ball")                    # agent tugmasi supervayzerda ishlamaydi
    assert m.photos == [] and _kb_buttons(m.texts[0][1]) == _kb_buttons(bot.SUPERVISOR_KB)
    m = _on_text(333, "📊 Oylik jadval")                  # supervayzer jadvali joyida
    assert len(m.photos) == 1 and m.photos[0][1].startswith("📊 Oylik jadval")
