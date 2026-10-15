"""
roster.py — AGENT RO'YXATINING YAGONA MANBASI (1-bosqich, 2026-07-30).

MUAMMO (llm-council eng o'tkir tashxisi): ro'yxat IKKI joyda edi — `agents.yaml`
(fayl) va `agents` jadvali (Sales Doctor sync). Ikkisi mos kelmasa xato chiqardi:
2026-07-18 kechki job ketgan agent (Eliza d0_152) ustida `KeyError` bilan qulab,
admin/supervayzer/GPS hisobotlarini JIMGINA yubormadi. Bir xil 3 qatorli filtr
build.py, gps.py, monitor.py da alohida takrorlangan, bot.py da esa YO'Q edi.

QOIDA (endi):
  • KIM BOR — buni **Sales Doctor** belgilaydi (`agents` jadvali, active='Y').
  • YAML faqat **BEZAYDI** (qisqa ism, liga, kod, ball_plan, kuzatuv, start_date).
  • Ketgan agent (active!='Y') hamma joydan avtomatik chiqadi — xato bermaydi.
  • Noma'lum sd_id (YAML'da bor, bazada YO'Q) — jimgina o'tkaziladi + log
    (fatal EMAS; masalan YAML'da xato yozilgan id yoki sync hali yurmagan).
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from . import period
from .core.rules import Agent, AgentsConfig, load_agents
from .nz_config import TIMEZONE

logger = logging.getLogger("nazorat.roster")


def _today() -> date:
    """Toshkent sanasi (UTC konteynerda oy chegarasi otib ketmasin)."""
    return datetime.now(ZoneInfo(TIMEZONE)).date()


def _status_map(conn, ids: list[str]) -> dict[str, str] | None:
    """sd_id -> active bayrog'i. `agents` jadvali yo'q/o'qilmasa None (test/lokal rejim)."""
    if not ids:
        return {}
    ph = ",".join("?" * len(ids))
    try:
        rows = conn.execute(
            f"SELECT sd_id, COALESCE(active,'Y') AS active FROM agents WHERE sd_id IN ({ph})",
            ids).fetchall()
    except Exception:                                   # noqa: BLE001 — jadval yo'q (test)
        return None
    return {r["sd_id"]: (r["active"] or "Y") for r in rows}


def classify(conn, cfg: AgentsConfig | None = None, day: date | None = None
             ) -> tuple[list[Agent], set[str], set[str]]:
    """Ro'yxatni ajratadi: (faol agentlar, ketganlar, bazada topilmaganlar).

    Faol = Sales Doctor'da active='Y' (yoki baza mavjud emas — lokal/test rejimi).
    Ball plani shu SANAGA amal qiladigan «oy varaqasi»dan olinadi (5-bosqich);
    varaqa yo'q bo'lsa YAML qiymati qoladi — hech narsa o'zgarmaydi.
    """
    cfg = cfg or load_agents()
    ids = [a.sd_id for a in cfg.agents]
    st = _status_map(conn, ids)
    if st is None:
        agents = list(cfg.agents)
        _decorate(conn, agents, day)
        return agents, set(), set()                    # baza yo'q — hamma qoladi

    active: list[Agent] = []
    departed: set[str] = set()
    unknown: set[str] = set()
    for a in cfg.agents:
        flag = st.get(a.sd_id)
        if flag is None:
            unknown.add(a.sd_id)
            active.append(a)                           # bazada yo'q — chiqarmaymiz
        elif flag != "Y":
            departed.add(a.sd_id)                      # ishdan ketgan
        else:
            active.append(a)
    if departed:
        logger.info("Ro'yxat: %d ketgan agent chiqarildi (%s)",
                    len(departed), ", ".join(sorted(departed)))
    if unknown:
        logger.warning("Ro'yxat: %d sd_id bazada topilmadi (yaml'da xato bo'lishi mumkin): %s",
                       len(unknown), ", ".join(sorted(unknown)))
    _decorate(conn, active, day)
    return active, departed, unknown


def apply_terms(conn, agents: list[Agent], today: date) -> None:
    """O'RINDIQ holatini qo'llaydi (`nz_agent_terms`): agent almashgan bo'lsa YANGI
    ismi, uning boshlanish sanasi va kuzatuv rejimi.

    YAML'dagi ism ESKI bo'lishi mumkin — o'rindiqda agent almashsa sync yangi ismni
    `nz_agent_terms` ga yozadi. Hisobotlar buni qo'llaydi; **ball plan ekrani ham
    qo'llashi SHART**, aks holda egasi "Behruz"ga plan qo'yaman deb aslida boshqa
    odamga qo'yib yuboradi (2026-07-31 da shu holat yuz berdi)."""
    from . import storage
    for ag in agents:
        term = storage.get_agent_term(conn, ag.sd_id)
        if not term:
            continue
        if term["start_date"]:
            ag.start_date = term["start_date"]
        # KUZATUV REJIMI O'CHIRILDI (2026-08-06, egasi qarori): yangi agent ham
        # birinchi kunidanoq ball planini ko'radi va sovrinda qatnashadi — "hamma
        # barobar" tamoyili. `observe_until` bazada qoladi (tarix uchun), LEKIN
        # o'qilmaydi; qayta yoqish kerak bo'lsa shu yerga bir qator qaytariladi.
        if term["is_new"] and term["short_name"]:
            # `!=` sharti SHART: bu funksiya bir necha marta chaqirilishi mumkin —
            # tekshiruvsiz ikkinchi chaqiruvda "avval" maydoniga YANGI ism yozilardi.
            if term["short_name"] != ag.short:
                ag.seat_prev_name = ag.short          # YAML'dagi eski agent
                ag.seat_changed = True
                ag.display = term["short_name"]


def observe_until(conn, sd_id: str) -> str | None:
    """Kuzatuv rejimi qachongacha (ekranda ko'rsatish uchun)."""
    from . import storage
    term = storage.get_agent_term(conn, sd_id)
    return term["observe_until"] if term else None


def _decorate(conn, agents: list[Agent], day: date | None) -> None:
    """YAML ustiga BAZADAGI haqiqatni qo'yadi — ikkalasi ham shu yerda, bir marta:
      • o'rindiq holati (`nz_agent_terms`): almashgan agentning HAQIQIY ismi, kuzatuvi;
      • «oy varaqasi» (`nz_period`): amaldagi ball plani.

    Nega SHU YERDA: avval har bir joy o'zi qo'llardi — natijada hisobotlar yangi
    ismni, Ulanish ekrani va GPS trevogalari esa ESKI ismni ko'rsatardi
    (2026-07-31: "Behruz" deb ko'ringan o'rindiqda aslida Ibragimova ishlardi).
    Endi `roster` dan o'tgan HAR BIR yo'l bir xil ismni ko'radi.

    Xato bo'lsa — YAML bilan davom etadi (hisobot HECH QACHON shu tufayli qulamasin).
    """
    d = day or _today()
    try:
        apply_terms(conn, agents, d)
    except Exception:                                   # noqa: BLE001
        logger.exception("O'rindiq holati qo'llanmadi — YAML ismi ishlatiladi")
    try:
        period.apply_to(conn, agents, d)
    except Exception:                                   # noqa: BLE001
        logger.exception("Oy varaqasi qo'llanmadi — YAML ball plani ishlatiladi")


def active_agents(conn, cfg: AgentsConfig | None = None,
                  league: str | None = None, day: date | None = None) -> list[Agent]:
    """Faol agentlar (xohlasa bitta liga bo'yicha). Hamma joyda SHU ishlatiladi."""
    active, _, _ = classify(conn, cfg, day)
    return [a for a in active if league is None or a.league == league]
