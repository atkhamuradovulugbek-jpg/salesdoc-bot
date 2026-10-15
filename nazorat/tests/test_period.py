"""
«OY VARAQASI» testlari (5-bosqich).

Eng muhim regressiyalar:
  • E'lon qilingan varaqa MUZLAYDI — keyin tahrirlab bo'lmaydi.
  • Hisobot O'Z SANASIGA qarab varaqa oladi (iyul kartasi iyul planini ko'radi,
    avgust e'lon qilingan bo'lsa ham).
  • Varaqa yo'q bo'lsa — YAML qiymati saqlanadi (hech narsa o'zgarmaydi).
  • Varaqada yo'q agent (keyin qo'shilgan) 0 ga TUSHMAYDI.
"""

import sqlite3
from datetime import date

import pytest

from nazorat import period, storage
from nazorat.core.rules import Agent


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    storage.init_nz_tables(c)
    yield c
    c.close()


def mk(sd_id, ball=70, league="city", name=None):
    return Agent(sd_id=sd_id, name=name or sd_id, display=name or sd_id,
                 league=league, code="X-" + sd_id, ball_plan=ball)


NOW = "2026-07-31T10:00:00+05:00"


# ── oy kaliti ──

def test_period_of_and_next():
    assert period.period_of(date(2026, 8, 5)) == "2026-08"
    assert period.next_period("2026-12") == "2027-01"
    assert period.month_label("2026-08") == "Avgust 2026"


def test_parse_rejects_garbage():
    with pytest.raises(ValueError):
        period.parse_period("2026-13")


# ── varaqa yo'q → YAML o'zgarmaydi ──

def test_no_sheet_keeps_yaml(conn):
    agents = [mk("d0_51", 70)]
    assert period.apply_to(conn, agents, date(2026, 8, 5)) is None
    assert agents[0].ball_plan == 70


# ── qoralama agentlarga TA'SIR QILMAYDI ──

def test_draft_is_invisible(conn):
    period.save_draft(conn, "2026-08", {"d0_51": 75}, True, "web", NOW)
    agents = [mk("d0_51", 70)]
    period.apply_to(conn, agents, date(2026, 8, 5))
    assert agents[0].ball_plan == 70, "qoralama hisobotga tushmasligi kerak"


# ── e'lon qilingach kuchga kiradi ──

def test_published_applies(conn):
    period.save_draft(conn, "2026-08", {"d0_51": 75}, True, "web", NOW)
    period.publish(conn, "2026-08", [mk("d0_51", 70)], "web", NOW)
    agents = [mk("d0_51", 70)]
    res = period.apply_to(conn, agents, date(2026, 8, 5))
    assert agents[0].ball_plan == 75
    assert res.period_ym == "2026-08" and res.checksum


# ── ASOSIY: eski oy MUZLAB QOLADI ──

def test_july_unaffected_by_august(conn):
    period.save_draft(conn, "2026-07", {"d0_51": 70}, True, "web", NOW)
    period.publish(conn, "2026-07", [mk("d0_51", 70)], "web", NOW)
    period.save_draft(conn, "2026-08", {"d0_51": 75}, True, "web", NOW)
    period.publish(conn, "2026-08", [mk("d0_51", 70)], "web", NOW)

    july = [mk("d0_51", 999)]
    period.apply_to(conn, july, date(2026, 7, 20))
    assert july[0].ball_plan == 70, "iyul kartasi iyul planini ko'rishi shart"

    aug = [mk("d0_51", 999)]
    period.apply_to(conn, aug, date(2026, 8, 20))
    assert aug[0].ball_plan == 75


# ── carry-forward: keyingi oy varaqasi bo'lmasa avvalgisi davom etadi ──

def test_carry_forward(conn):
    period.save_draft(conn, "2026-08", {"d0_51": 75}, True, "web", NOW)
    period.publish(conn, "2026-08", [mk("d0_51", 70)], "web", NOW)
    agents = [mk("d0_51", 70)]
    res = period.apply_to(conn, agents, date(2026, 11, 3))
    assert agents[0].ball_plan == 75 and res.period_ym == "2026-08"


# ── yangi agent 0 ga tushmaydi ──

def test_new_agent_keeps_yaml_value(conn):
    period.save_draft(conn, "2026-08", {"d0_51": 75}, True, "web", NOW)
    period.publish(conn, "2026-08", [mk("d0_51", 70)], "web", NOW)
    agents = [mk("d0_51", 70), mk("d0_99", 50)]        # d0_99 keyin qo'shilgan
    period.apply_to(conn, agents, date(2026, 8, 15))
    assert agents[0].ball_plan == 75
    assert agents[1].ball_plan == 50, "varaqada yo'q agent 0 ga tushmasligi kerak"


# ── muzlagan varaqa tahrirlanmaydi ──

def test_published_is_frozen(conn):
    period.save_draft(conn, "2026-08", {"d0_51": 75}, True, "web", NOW)
    period.publish(conn, "2026-08", [mk("d0_51", 70)], "web", NOW)
    with pytest.raises(PermissionError):
        period.save_draft(conn, "2026-08", {"d0_51": 99}, True, "web", NOW)
    with pytest.raises(PermissionError):
        period.publish(conn, "2026-08", [mk("d0_51", 70)], "web", NOW)


def test_publish_without_draft_fails(conn):
    with pytest.raises(LookupError):
        period.publish(conn, "2026-09", [mk("d0_51")], "web", NOW)


def test_ball_range_validated(conn):
    with pytest.raises(ValueError):
        period.save_draft(conn, "2026-08", {"d0_51": 5000}, True, "web", NOW)


# ── UNDO: faqat boshlanmagan oy ──

def test_reopen_allowed_while_month_runs(conn):
    """Egasi so'rovi (2026-08-06): JORIY oyni e'londan keyin ham tuzatsa bo'ladi."""
    period.save_draft(conn, "2026-08", {"d0_51": 75}, True, "web", NOW)
    period.publish(conn, "2026-08", [mk("d0_51", 70)], "web", NOW)
    ver = period.reopen(conn, "2026-08", date(2026, 8, 10), NOW)     # oy DAVOM etyapti
    assert ver == 2
    assert period.get_row(conn, "2026-08")["status"] == period.DRAFT
    agents = [mk("d0_51", 70)]
    period.apply_to(conn, agents, date(2026, 8, 10))
    assert agents[0].ball_plan == 70, "tuzatish paytida e'lon qilingan reja amal qilmaydi"


def test_reopen_blocked_after_month_ends(conn):
    """Tugagan oy MUZLAYDI — bonus hisoblangan, qayta ochilmaydi."""
    period.save_draft(conn, "2026-08", {"d0_51": 75}, True, "web", NOW)
    period.publish(conn, "2026-08", [mk("d0_51", 70)], "web", NOW)
    with pytest.raises(PermissionError):
        period.reopen(conn, "2026-08", date(2026, 9, 1), NOW)


def test_reopen_archives_previous_version(conn):
    """Agentlarga QAYSI raqamlar e'lon qilingani yo'qolmaydi."""
    period.save_draft(conn, "2026-08", {"d0_51": 75}, True, "web", NOW)
    period.publish(conn, "2026-08", [mk("d0_51", 70)], "web", NOW)
    old_chk = period.get_row(conn, "2026-08")["checksum"]
    period.reopen(conn, "2026-08", date(2026, 8, 10), NOW)
    hist = period.history(conn, "2026-08")
    assert len(hist) == 1
    assert hist[0]["version"] == 1 and hist[0]["checksum"] == old_chk


def test_republish_bumps_version_and_applies(conn):
    period.save_draft(conn, "2026-08", {"d0_51": 75}, True, "web", NOW)
    period.publish(conn, "2026-08", [mk("d0_51", 70)], "web", NOW)
    period.reopen(conn, "2026-08", date(2026, 8, 10), NOW)
    period.save_draft(conn, "2026-08", {"d0_51": 50}, True, "web", NOW, growth=False)
    chk2 = period.publish(conn, "2026-08", [mk("d0_51", 70)], "web", NOW)

    row = period.get_row(conn, "2026-08")
    assert row["version"] == 2 and row["status"] == period.PUBLISHED
    assert chk2 != period.history(conn, "2026-08")[0]["checksum"], "muhr yangilanishi kerak"
    agents = [mk("d0_51", 70)]
    period.apply_to(conn, agents, date(2026, 8, 10))
    assert agents[0].ball_plan == 50, "tuzatilgan reja kuchga kirishi kerak"
    assert period.growth_enabled(conn, date(2026, 8, 10)) is False


def test_published_sheet_needs_reopen_before_edit(conn):
    """To'g'ridan-to'g'ri saqlash rad etiladi — avval «Tuzatish» bosilishi kerak."""
    period.save_draft(conn, "2026-08", {"d0_51": 75}, True, "web", NOW)
    period.publish(conn, "2026-08", [mk("d0_51", 70)], "web", NOW)
    with pytest.raises(PermissionError):
        period.save_draft(conn, "2026-08", {"d0_51": 50}, True, "web", NOW)


def test_can_edit_rule(conn):
    assert period.can_edit("2026-09", date(2026, 8, 6)) is True     # kelasi oy
    assert period.can_edit("2026-08", date(2026, 8, 6)) is True     # joriy oy
    assert period.can_edit("2026-07", date(2026, 8, 6)) is False    # tugagan oy


# ── sovrin o'chirish ──

def test_prizes_switch(conn):
    assert period.prizes_enabled(conn, date(2026, 8, 5)) is True    # varaqa yo'q → yoqilgan
    period.save_draft(conn, "2026-08", {"d0_51": 75}, False, "web", NOW)
    period.publish(conn, "2026-08", [mk("d0_51", 70)], "web", NOW)
    assert period.prizes_enabled(conn, date(2026, 8, 5)) is False
    assert period.prizes_enabled(conn, date(2026, 7, 5)) is True    # iyul o'zgarmaydi


# ── o'sish sovrini PODIUMDAN mustaqil (egasi 2026-08 da faqat 700 mingni bekor qildi) ──

def test_growth_switch_is_independent(conn):
    period.save_draft(conn, "2026-08", {"d0_51": 75}, True, "web", NOW, growth=False)
    period.publish(conn, "2026-08", [mk("d0_51", 70)], "web", NOW)
    assert period.prizes_enabled(conn, date(2026, 8, 5)) is True, "podium QOLISHI kerak"
    assert period.growth_enabled(conn, date(2026, 8, 5)) is False, "o'sish sovrini o'chsin"


def test_growth_defaults_on(conn):
    assert period.growth_enabled(conn, date(2026, 8, 5)) is True     # varaqa yo'q
    period.save_draft(conn, "2026-08", {"d0_51": 75}, True, "web", NOW)
    period.publish(conn, "2026-08", [mk("d0_51", 70)], "web", NOW)
    assert period.growth_enabled(conn, date(2026, 8, 5)) is True


def test_growth_switch_does_not_touch_past(conn):
    """Eski oy MUZLAGAN — keyin o'chirilsa ham iyul o'sish sovrini o'chmaydi."""
    period.save_draft(conn, "2026-07", {"d0_51": 70}, True, "web", NOW)
    period.publish(conn, "2026-07", [mk("d0_51", 70)], "web", NOW)
    period.save_draft(conn, "2026-08", {"d0_51": 75}, True, "web", NOW, growth=False)
    period.publish(conn, "2026-08", [mk("d0_51", 70)], "web", NOW)
    assert period.growth_enabled(conn, date(2026, 7, 20)) is True
    assert period.growth_enabled(conn, date(2026, 8, 20)) is False


# ── e'londa ro'yxat muzlaydi (YAML keyin o'zgarsa ham) ──

def test_publish_freezes_missing_agents(conn):
    period.save_draft(conn, "2026-08", {"d0_51": 75}, True, "web", NOW)
    # d0_99 qoralamada yo'q, lekin e'lon paytida faol → YAML qiymati muzlaydi
    period.publish(conn, "2026-08", [mk("d0_51", 70), mk("d0_99", 60)], "web", NOW)
    agents = [mk("d0_51", 0), mk("d0_99", 0)]
    period.apply_to(conn, agents, date(2026, 8, 5))
    assert (agents[0].ball_plan, agents[1].ball_plan) == (75, 60)


# ── ekran ma'lumoti ──

def test_sheet_view_marks_changes(conn):
    period.save_draft(conn, "2026-07", {"d0_51": 70, "d0_60": 60}, True, "web", NOW)
    period.publish(conn, "2026-07", [mk("d0_51", 70), mk("d0_60", 60)], "web", NOW)
    period.save_draft(conn, "2026-08", {"d0_51": 75, "d0_60": 60}, True, "web", NOW)

    agents = [mk("d0_51", 70, name="Bahodir"), mk("d0_60", 60, name="Jasmina"),
              mk("d0_99", 50, name="Yangi", league="region")]
    v = period.sheet_view(conn, "2026-08", agents, date(2026, 7, 31))
    by = {r["sd_id"]: r for r in v["rows"]}
    assert by["d0_51"]["was"] == 70 and by["d0_51"]["ball_plan"] == 75
    assert by["d0_51"]["changed"] is True
    assert by["d0_60"]["changed"] is False
    assert by["d0_99"]["is_new"] is True, "yangi agent ajratib ko'rsatilishi kerak"
    assert v["changed_count"] == 1
    assert v["editable"] is True and v["is_future"] is True


def test_first_sheet_marks_nobody_new(conn):
    """Birinchi varaqada hamma 'yangi' bo'lib chiqmasin (belgi ma'nosini yo'qotadi)."""
    v = period.sheet_view(conn, "2026-08", [mk("d0_51", 70), mk("d0_60", 60)],
                          date(2026, 7, 31))
    assert v["new_count"] == 0
    assert all(r["was"] == r["ball_plan"] for r in v["rows"])


def test_sheet_view_lists_departed(conn):
    period.save_draft(conn, "2026-07", {"d0_51": 70, "d0_152": 60}, True, "web", NOW)
    period.publish(conn, "2026-07", [mk("d0_51", 70), mk("d0_152", 60)], "web", NOW)
    v = period.sheet_view(conn, "2026-08", [mk("d0_51", 70)], date(2026, 7, 31))
    assert [g["sd_id"] for g in v["gone"]] == ["d0_152"]
