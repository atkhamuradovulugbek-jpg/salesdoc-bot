"""
period.py — «OY VARAQASI» (5-bosqich, 2026-07-31).

MUAMMO: ball plani `agents.yaml` faylida edi — egasi uni telefondan o'zgartira
olmasdi, va o'zgartirilsa BUTUN TARIX o'zgarardi (iyul bonusi avgust qoidasi
bilan qayta hisoblanardi). Bu — pul masalasi, config emas.

YECHIM (llm-council talabi): har oy uchun alohida **varaqa**.
  • Varaqa QORALAMA holida tahrirlanadi — agentlar ko'rmaydi.
  • **E'LON QILINSA MUZLAYDI** (status='published' + checksum) — keyin hech qachon
    o'zgarmaydi. Iyul bonusi doim iyul qoidasi bilan hisoblanadi.
  • Hisobot **o'z sanasiga qarab** varaqa oladi ("hozirgi" emas):
    `WHERE period_ym <= :report_period AND status='published' ORDER BY DESC LIMIT 1`.
    Shu bilan "kechagi karta" va "oy yakuni" eski qoida bilan to'g'ri chiqadi.
  • Varaqa yo'q bo'lsa — avvalgisi DAVOM ETADI (carry-forward), u ham bo'lmasa YAML.
    Ya'ni egasi hech narsa qilmasa — hech narsa o'zgarmaydi.

SANA EMAS, OY KALITI: `period_ym TEXT` ('2026-08'). UTC konteynerda `date`
chegarasi Toshkent vaqti bilan 31-kuni 19:00 da "otib ketardi" — oy kaliti bu
xato sinfini sxema darajasida yo'q qiladi.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import date

logger = logging.getLogger("nazorat.period")

DRAFT = "draft"
PUBLISHED = "published"

_MONTHS_UZ = ["", "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
              "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"]


# ------------------------------------------------------------------
# Oy kaliti bilan ishlash
# ------------------------------------------------------------------

def period_of(d: date) -> str:
    """Sana -> oy kaliti ('2026-08')."""
    return f"{d.year:04d}-{d.month:02d}"


def parse_period(ym: str) -> tuple[int, int]:
    y, m = ym.split("-")
    y, m = int(y), int(m)
    if not (2000 <= y <= 2100 and 1 <= m <= 12):
        raise ValueError(f"noto'g'ri oy: {ym}")
    return y, m


def next_period(ym: str) -> str:
    y, m = parse_period(ym)
    return f"{y + 1:04d}-01" if m == 12 else f"{y:04d}-{m + 1:02d}"


def month_label(ym: str) -> str:
    """'2026-08' -> 'Avgust 2026'."""
    y, m = parse_period(ym)
    return f"{_MONTHS_UZ[m]} {y}"


def starts_on(ym: str) -> date:
    y, m = parse_period(ym)
    return date(y, m, 1)


def is_future(ym: str, today: date) -> bool:
    """Varaqa hali BOSHLANMAGANmi (hech kim ko'rmagan — bekor qilsa bo'ladi)."""
    return starts_on(ym) > today


def is_over(ym: str, today: date) -> bool:
    """Oy TUGAGANmi? Tugagan oy — bonus hisoblangan oy, boshqa tegilmaydi."""
    return ym < period_of(today)


def can_edit(ym: str, today: date) -> bool:
    """Varaqani tuzatish mumkinmi?

    QOIDA (2026-08-06, egasi so'rovi): **oy tugamaguncha tuzatsa bo'ladi.**
    Joriy oy hali davom etyapti — hech kimning bonusi yakunlanmagan, shuning
    uchun xatoni to'g'rilash mumkin (tarixga yozib). Oy TUGAGANDAN keyin esa
    varaqa butunlay muzlaydi: o'sha oy bonusi keyin qayta hisoblanmasin."""
    return not is_over(ym, today)


# ------------------------------------------------------------------
# O'QISH — hisobot qaysi varaqani ishlatadi
# ------------------------------------------------------------------

@dataclass
class Resolved:
    """Hisobot sanasiga tegishli MUZLATILGAN varaqa."""
    period_ym: str
    checksum: str
    prizes_enabled: bool                                      # podium (1.5/1/0.5 mln)
    growth_enabled: bool = True                               # o'sish sovrini (700 ming)
    ball_plan: dict[str, int] = field(default_factory=dict)   # sd_id -> ball


def resolve(conn, day: date) -> Resolved | None:
    """Shu sanaga amal qiladigan e'lon qilingan varaqa (yo'q bo'lsa None -> YAML)."""
    ym = period_of(day)
    try:
        row = conn.execute(
            "SELECT period_ym, checksum, prizes_enabled, growth_enabled FROM nz_period "
            "WHERE period_ym <= ? AND status=? ORDER BY period_ym DESC LIMIT 1",
            (ym, PUBLISHED)).fetchone()
    except Exception:                                   # noqa: BLE001 — jadval yo'q (eski baza/test)
        return None
    if not row:
        return None
    src = row["period_ym"]
    plans = {r["sd_id"]: int(r["ball_plan"]) for r in conn.execute(
        "SELECT sd_id, ball_plan FROM nz_agent_plan WHERE period_ym=?", (src,))}
    return Resolved(period_ym=src, checksum=row["checksum"] or "",
                    prizes_enabled=bool(row["prizes_enabled"]),
                    growth_enabled=bool(row["growth_enabled"]), ball_plan=plans)


def apply_to(conn, agents: list, day: date) -> Resolved | None:
    """Agent obyektlariga varaqa ball planini qo'yadi (roster.py chaqiradi).

    Varaqada YO'Q agent (keyin qo'shilgan) YAML qiymatini SAQLAB QOLADI — jimgina
    0 ga tushib qolmaydi (llm-council: "carry-forward yangi agentni tashlab ketishi").
    """
    res = resolve(conn, day)
    if res is None:
        return None
    for a in agents:
        if a.sd_id in res.ball_plan:
            a.ball_plan = res.ball_plan[a.sd_id]
    return res


def prizes_enabled(conn, day: date) -> bool:
    """PODIUM sovrini shu sanada yoqilganmi (1.5/1/0.5 mln)."""
    res = resolve(conn, day)
    return True if res is None else res.prizes_enabled


def growth_enabled(conn, day: date) -> bool:
    """O'SISH sovrini shu sanada yoqilganmi (700 ming). Podiumdan MUSTAQIL:
    egasi 2026-08 da faqat o'sish sovrinini bekor qildi, podium qoldi."""
    res = resolve(conn, day)
    return True if res is None else res.growth_enabled


# ------------------------------------------------------------------
# QORALAMA — tahrirlash
# ------------------------------------------------------------------

def _checksum(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()[:12]


def get_row(conn, ym: str):
    try:
        return conn.execute("SELECT * FROM nz_period WHERE period_ym=?", (ym,)).fetchone()
    except Exception:                                   # noqa: BLE001 — jadval hali yo'q
        return None


def plans_of(conn, ym: str) -> dict[str, int]:
    try:
        return {r["sd_id"]: int(r["ball_plan"]) for r in conn.execute(
            "SELECT sd_id, ball_plan FROM nz_agent_plan WHERE period_ym=?", (ym,))}
    except Exception:                                   # noqa: BLE001
        return {}


def save_draft(conn, ym: str, plans: dict[str, int], prizes: bool,
               by: str, now: str, growth: bool = True) -> None:
    """Qoralamani saqlaydi. E'lon qilingan varaqa TAHRIRLANMAYDI (muzlagan)."""
    parse_period(ym)
    row = get_row(conn, ym)
    if row and row["status"] == PUBLISHED:
        raise PermissionError(
            f"{month_label(ym)} e'lon qilingan. O'zgartirish uchun avval "
            f"«✏️ Tuzatish» tugmasini bosing.")
    for v in plans.values():
        if not (0 <= int(v) <= 500):
            raise ValueError("ball plani 0 dan 500 gacha bo'lishi kerak")

    if row:
        conn.execute("UPDATE nz_period SET prizes_enabled=?, growth_enabled=?, "
                     "updated_at=?, updated_by=? WHERE period_ym=?",
                     (int(prizes), int(growth), now, by, ym))
    else:
        conn.execute(
            "INSERT INTO nz_period (period_ym, status, prizes_enabled, growth_enabled, "
            "created_at, updated_at, updated_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ym, DRAFT, int(prizes), int(growth), now, now, by))
    conn.execute("DELETE FROM nz_agent_plan WHERE period_ym=?", (ym,))
    conn.executemany(
        "INSERT INTO nz_agent_plan (sd_id, period_ym, ball_plan) VALUES (?, ?, ?)",
        [(k, ym, int(v)) for k, v in plans.items()])


def build_payload(conn, ym: str, agents: list) -> dict:
    """MUZLATILADIGAN huquqiy yozuv (kim, qancha ball, sovrin bormi)."""
    row = get_row(conn, ym)
    plans = plans_of(conn, ym)
    return {
        "period_ym": ym,
        "prizes_enabled": int(row["prizes_enabled"]) if row else 1,
        "growth_enabled": int(row["growth_enabled"]) if row else 1,
        "agents": sorted(
            [{"sd_id": a.sd_id, "name": a.short, "league": a.league,
              "ball_plan": int(plans.get(a.sd_id, a.ball_plan))} for a in agents],
            key=lambda x: x["sd_id"]),
    }


def publish(conn, ym: str, agents: list, by: str, now: str) -> str:
    """Varaqani MUZLATADI. Qaytadi: checksum."""
    row = get_row(conn, ym)
    if not row:
        raise LookupError(f"{month_label(ym)} varaqasi yo'q — avval saqlang.")
    if row["status"] == PUBLISHED:
        raise PermissionError(f"{month_label(ym)} allaqachon e'lon qilingan.")
    payload = build_payload(conn, ym, agents)
    payload["version"] = int(row["version"] or 1)      # tuzatish raqami muhrga kirsin
    chk = _checksum(payload)
    # E'lon paytidagi ro'yxat MUZLAYDI: varaqada yo'q agentning YAML qiymati ham
    # yoziladi, aks holda keyin YAML o'zgarsa muzlatilgan oy siljib ketardi.
    conn.execute("DELETE FROM nz_agent_plan WHERE period_ym=?", (ym,))
    conn.executemany(
        "INSERT INTO nz_agent_plan (sd_id, period_ym, ball_plan) VALUES (?, ?, ?)",
        [(a["sd_id"], ym, a["ball_plan"]) for a in payload["agents"]])
    conn.execute(
        "UPDATE nz_period SET status=?, payload=?, checksum=?, published_at=?, "
        "published_by=? WHERE period_ym=?",
        (PUBLISHED, json.dumps(payload, ensure_ascii=False), chk, now, by, ym))
    logger.info("Varaqa e'lon qilindi: %s checksum=%s (%d agent)",
                ym, chk, len(payload["agents"]))
    return chk


def reopen(conn, ym: str, today: date, now: str) -> int:
    """TUZATISH uchun varaqani qoralamaga qaytaradi. Qaytadi: nechanchi tuzatish.

    Avvalgi nusxa `nz_period_history` ga ko'chiriladi — agentlarga QAYSI raqamlar
    e'lon qilingani yo'qolmaydi. Oy tugagan bo'lsa — rad etiladi."""
    row = get_row(conn, ym)
    if not row or row["status"] != PUBLISHED:
        raise LookupError(f"{month_label(ym)} e'lon qilinmagan.")
    if not can_edit(ym, today):
        raise PermissionError(
            f"{month_label(ym)} tugagan — endi o'zgartirib bo'lmaydi. "
            f"O'sha oy bonusi shu raqamlar bilan hisoblangan.")
    ver = int(row["version"] or 1)
    conn.execute(
        "INSERT OR REPLACE INTO nz_period_history (period_ym, version, payload, checksum, "
        "prizes_enabled, growth_enabled, published_at, published_by, replaced_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ym, ver, row["payload"], row["checksum"], row["prizes_enabled"],
         row["growth_enabled"], row["published_at"], row["published_by"], now))
    conn.execute("UPDATE nz_period SET status=?, payload=NULL, checksum=NULL, "
                 "published_at=NULL, published_by=NULL, version=?, updated_at=? "
                 "WHERE period_ym=?", (DRAFT, ver + 1, now, ym))
    logger.info("Varaqa tuzatishga ochildi: %s (v%d -> v%d)", ym, ver, ver + 1)
    return ver + 1


def history(conn, ym: str) -> list[dict]:
    """Shu oyning avvalgi e'lon qilingan nusxalari (eng yangisi tepada)."""
    try:
        rows = conn.execute(
            "SELECT version, checksum, prizes_enabled, growth_enabled, published_at, "
            "replaced_at FROM nz_period_history WHERE period_ym=? ORDER BY version DESC",
            (ym,)).fetchall()
    except Exception:                                   # noqa: BLE001 — jadval hali yo'q
        return []
    return [dict(r) for r in rows]


def list_sheets(conn, limit: int = 12) -> list[dict]:
    try:
        rows = conn.execute(
            "SELECT period_ym, status, prizes_enabled, growth_enabled, checksum, "
            "published_at FROM nz_period ORDER BY period_ym DESC LIMIT ?", (limit,)).fetchall()
    except Exception:                                   # noqa: BLE001 — jadval hali yo'q
        return []
    return [{"period_ym": r["period_ym"], "label": month_label(r["period_ym"]),
             "status": r["status"], "prizes_enabled": bool(r["prizes_enabled"]),
             "growth_enabled": bool(r["growth_enabled"]),
             "checksum": r["checksum"], "published_at": r["published_at"]} for r in rows]


# ------------------------------------------------------------------
# EKRAN uchun — varaqa + ro'yxat farqi
# ------------------------------------------------------------------

def sheet_view(conn, ym: str, agents: list, today: date) -> dict:
    """Web ekrani: har agent uchun joriy/yangi ball + varaqa holati + ro'yxat farqi."""
    row = get_row(conn, ym)
    status = row["status"] if row else "yo'q"
    plans = plans_of(conn, ym)
    # Shu varaqadan OLDIN amal qilgan varaqa (taqqoslash uchun "avval qancha edi")
    prev = resolve(conn, starts_on(ym).replace(day=1) if row else today)
    prev_plans = {}
    prev_label = "YAML (boshlang'ich)"
    try:
        prev_row = conn.execute(
            "SELECT period_ym FROM nz_period WHERE period_ym < ? AND status=? "
            "ORDER BY period_ym DESC LIMIT 1", (ym, PUBLISHED)).fetchone()
    except Exception:                                   # noqa: BLE001 — jadval hali yo'q
        prev_row = None
    if prev_row:
        prev_plans = plans_of(conn, prev_row["period_ym"])
        prev_label = month_label(prev_row["period_ym"])
    elif prev:
        prev_plans = prev.ball_plan
        prev_label = month_label(prev.period_ym)

    from . import roster
    rows = []
    for a in agents:
        was = prev_plans.get(a.sd_id, a.ball_plan)
        now_v = plans.get(a.sd_id, was)
        rows.append({
            "sd_id": a.sd_id, "name": a.short, "league": a.league,
            "league_label": "Shahar" if a.league == "city" else "Viloyat",
            # XUDUD ism yonida — yangi agentning ismi yodda qolmaydi, xududidan
            # taniydi (egasi so'radi, 2026-07-31).
            "area": a.area,
            "seat_changed": bool(a.seat_changed), "seat_prev": a.seat_prev_name,
            "seat_since": a.start_date,
            # KUZATUV rejimidagi agentga qo'yilgan plan KARTADA KO'RINMAYDI —
            # egasi buni bilmasa "qo'ydim, chiqmadi" deb chalkashadi (2026-07-31).
            "observe": bool(a.observe_only),
            "observe_until": roster.observe_until(conn, a.sd_id) if a.observe_only else None,
            "was": int(was), "ball_plan": int(now_v),
            "changed": int(now_v) != int(was),
            # "yangi" belgisi FAQAT oldingi varaqa mavjud bo'lganda ma'noli —
            # birinchi varaqada hamma "yangi" bo'lib chiqib, belgini foydasiz qilardi.
            "is_new": bool(prev_plans) and a.sd_id not in prev_plans,
        })
    rows.sort(key=lambda r: (r["league"] != "city", -r["ball_plan"], r["name"]))

    # Ro'yxatdan CHIQQANLAR (oldingi varaqada bor edi, endi faol emas)
    live = {a.sd_id for a in agents}
    gone = [{"sd_id": k, "ball_plan": v} for k, v in prev_plans.items() if k not in live]

    return {
        "period_ym": ym, "label": month_label(ym), "status": status,
        "editable": status != PUBLISHED,
        # E'lon qilingan varaqani TUZATISH mumkinmi (oy tugamagan bo'lsa — ha)
        "can_fix": status == PUBLISHED and can_edit(ym, today),
        "is_over": is_over(ym, today),
        "version": int(row["version"] or 1) if row else 1,
        "history": history(conn, ym),
        "prizes_enabled": bool(row["prizes_enabled"]) if row else True,
        "growth_enabled": bool(row["growth_enabled"]) if row else True,
        "checksum": row["checksum"] if row else None,
        "published_at": row["published_at"] if row else None,
        "starts": starts_on(ym).isoformat(),
        "is_future": is_future(ym, today),
        "prev_label": prev_label,
        "rows": rows, "gone": gone,
        "changed_count": sum(1 for r in rows if r["changed"]),
        "new_count": sum(1 for r in rows if r["is_new"]),
    }
