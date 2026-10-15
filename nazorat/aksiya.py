"""
aksiya.py — «300 000 AKSIYA» hisobi (2026-10-06, egasi topshirig'i).

NIMA: agentlar ball emas, AKSIYA yig'adi. Bitta buyurtmadagi har to'liq
300 000 so'm = 1 aksiya. Kun oxirida yig'ilgan aksiya soniga qarab bonus.

MUHIM QOIDALAR (egasi bilan tasdiqlangan):
  • Har buyurtma ALOHIDA sanaladi. Bir do'konning bir kundagi ikki buyurtmasi
    qo'shilmaydi: 200k + 200k = 0 aksiya (hech qaysisi 300k ga yetmagan).
  • Faqat YETKAZILGAN (status 3) buyurtma hisoblanadi.
  • VAZVRAT AYIRILADI (2026-10-06 qarori): "300 olib 60 qaytardi → 240 → 0".
  • Chegirmali buyurtma oddiy aksiya kabi — chegirmadan KEYINGI summadan.

BU MODUL SOF: Telegram ham, baza ham, API ham yo'q — faqat hisob. Shuning
uchun testlanadi va boshqa joyga ulanganda hech narsani buzmaydi.

TEKSHIRUV (jonli baza, sentabr 2026, vazvrat ayirilgan holda):
    SHAHAR 705 aksiya · VILOYAT 939 aksiya
"""

from __future__ import annotations

import logging
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

import yaml

logger = logging.getLogger("nazorat.aksiya")

CONFIG_PATH = Path(__file__).parent / "config" / "aksiya.yaml"
_cfg_cache: dict | None = None


def load_config(path: Path | None = None, reload: bool = False) -> dict:
    """aksiya.yaml ni o'qiydi (keshlanadi)."""
    global _cfg_cache
    if _cfg_cache is not None and not reload and path is None:
        return _cfg_cache
    p = path or CONFIG_PATH
    with open(p, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if path is None:
        _cfg_cache = cfg
    return cfg


# ------------------------------------------------------------------
# 1. Bitta buyurtma → nechta aksiya
# ------------------------------------------------------------------

def units_for_order(net_sum: float, cfg: dict | None = None) -> int:
    """Buyurtmaning SOF summasidan aksiya soni (butun qismi).

    290 000 → 0 · 300 000 → 1 · 590 000 → 1 · 600 000 → 2 · 3 000 000 → 10
    """
    cfg = cfg or load_config()
    step = cfg["threshold_sum"]
    if not step or net_sum is None or net_sum <= 0:
        return 0
    return int(net_sum // step)


def net_sum_for_order(order: dict, cfg: dict | None = None) -> float:
    """Buyurtmaning aksiya hisobiga kiradigan summasi.

    Bazadagi `total_sum` (= total_after_discount) qisman vazvrat AYIRILGAN
    sof summa. Agar manba xom summa bersa va vazvrat alohida kelsa —
    `returns` maydoni ayiriladi (subtract_returns: true)."""
    cfg = cfg or load_config()
    total = float(order.get("total_sum") or 0)
    if cfg.get("subtract_returns", True):
        total -= float(order.get("returns") or 0)
    # Sovg'a qatori NARX bilan kiritilgan bo'lsa — summadan chiqariladi.
    # (narxsiz sovg'a summaga allaqachon ta'sir qilmaydi)
    for ln in (order.get("lines") or []):
        if is_gift_line(ln, cfg) and float(ln.get("summa") or 0) > 0:
            total -= float(ln["summa"])
    return max(total, 0.0)


def is_gift_line(line: dict, cfg: dict | None = None) -> bool:
    """Sovg'a qatorimi? (nomida makaron/jele bo'lsa yoki is_gift belgisi)."""
    cfg = cfg or load_config()
    if line.get("is_gift"):
        return True
    name = str(line.get("product_name") or line.get("name") or "").lower()
    return any(k.lower() in name for k in cfg.get("gift_keywords", []))


def has_gift(order: dict, cfg: dict | None = None) -> bool:
    """Buyurtmada sovg'a qatori bormi (nazorat ro'yxati uchun)."""
    return any(is_gift_line(ln, cfg) for ln in (order.get("lines") or []))


# ------------------------------------------------------------------
# 2. Liga
# ------------------------------------------------------------------

def league_for_agent(agent_name: str, cfg: dict | None = None) -> str | None:
    """Agent ismidan ligasini topadi: "Jalolov Bahodir (Yunusobod)" → shahar.

    DIQQAT — bu ZAXIRA yo'l. Asosiy manba `agents.yaml` dagi `league` maydoni
    (roster.py). Ism bo'yicha topish faqat agent ro'yxatda bo'lmaganda yoki
    tekshiruv uchun ishlatiladi — aks holda liga IKKI joyda bo'lib, mos
    kelmay qolish xavfi tug'iladi (2026-07-18 da aynan shunday nosozlik bo'lgan).
    """
    cfg = cfg or load_config()
    if not agent_name:
        return None
    nm = agent_name.strip()
    if nm in (cfg.get("excluded_agents") or []):
        return None
    low = nm.lower()
    for key, lg in (cfg.get("leagues") or {}).items():
        for terr in (lg.get("territories") or []):
            if str(terr).lower() in low:
                return key
    return None


def league_label(league: str, cfg: dict | None = None) -> str:
    cfg = cfg or load_config()
    return ((cfg.get("leagues") or {}).get(league) or {}).get("label", league.upper())


# ------------------------------------------------------------------
# 3. Kunlik bonus
# ------------------------------------------------------------------

def _rate(tier: dict) -> Fraction:
    """Pog'ona stavkasi — ANIQ kasr.

    `rate_total/rate_units` berilsa (masalan 100000/15) kasr saqlanadi:
    6666.6667 deb yozsak 15 ta aksiyada 100 000 o'rniga 100 000.0005 chiqardi."""
    if "rate_total" in tier and "rate_units" in tier:
        return Fraction(int(tier["rate_total"]), int(tier["rate_units"]))
    return Fraction(str(tier["rate"]))


def daily_bonus(units: int, league: str, cfg: dict | None = None) -> int:
    """Bir agentning bir kunlik bonusi (so'm, butunga yaxlitlangan).

    Eng yuqori MOS kelgan pog'ona ishlaydi. Eshikdan past — 0."""
    cfg = cfg or load_config()
    lg = (cfg.get("leagues") or {}).get(league)
    if not lg or units is None or units < lg.get("min_units", 0):
        return 0
    best: Fraction | None = None
    for tier in sorted(lg.get("tiers") or [], key=lambda t: t["min_n"]):
        if units >= tier["min_n"]:
            best = _rate(tier)
    if best is None:
        return 0
    total = best * units
    # Fraction → eng yaqin butun (0.5 yuqoriga)
    return int(total + Fraction(1, 2)) if total >= 0 else -int(-total + Fraction(1, 2))


def to_threshold(units: int, league: str, cfg: dict | None = None) -> int:
    """Eshikka yana nechta aksiya kerak (eshikdan o'tgan bo'lsa 0)."""
    cfg = cfg or load_config()
    lg = (cfg.get("leagues") or {}).get(league) or {}
    return max(0, int(lg.get("min_units", 0)) - int(units or 0))


def next_tier_gain(units: int, league: str, cfg: dict | None = None
                   ) -> tuple[int, int] | None:
    """Keyingi pog'onagacha: (yana nechta aksiya, o'shanda bonus). Yo'q bo'lsa None.

    Shaxsiy xabardagi "15 ga yana 3 ta — 100 000 bo'lardi" uchun."""
    cfg = cfg or load_config()
    lg = (cfg.get("leagues") or {}).get(league) or {}
    nxt = [t["min_n"] for t in (lg.get("tiers") or []) if t["min_n"] > (units or 0)]
    if not nxt:
        return None
    target = min(nxt)
    return target - units, daily_bonus(target, league, cfg)


# ------------------------------------------------------------------
# 4. Bir kunlik hisob
# ------------------------------------------------------------------

def is_delivered(order: dict, cfg: dict | None = None) -> bool:
    """Yetkazilganmi? Status raqam ham, matn ham bo'lishi mumkin."""
    cfg = cfg or load_config()
    st = order.get("status")
    want = cfg.get("delivered_status", 3)
    if isinstance(st, str):
        if st.strip().isdigit():
            return int(st) == int(want)
        return st.strip().lower() in ("доставлен", "yetkazilgan", "delivered")
    return st == want


def compute_day(orders: list[dict], day: str, cfg: dict | None = None,
                league_of=None) -> dict[str, dict]:
    """Bir kun uchun agent bo'yicha hisob.

    orders — buyurtmalar ro'yxati, har biri:
        {order_id, order_date, client, agent, agent_sd_id?, status,
         total_sum, returns?, lines?}
    league_of — ixtiyoriy funksiya (agent dict → 'shahar'|'viloyat'|None).
        Berilmasa ism bo'yicha topiladi. Ishlab chiqarishda roster'dan keladi.

    Qaytadi: {agent: {units, bonus, league, orders_count, big_orders,
                      multi_orders, no_gift_orders, ...}}
    """
    cfg = cfg or load_config()
    excl_names = set(cfg.get("excluded_agents") or [])
    excl_ids = set(cfg.get("excluded_sd_ids") or [])
    big = float(cfg.get("big_order_alert") or 0)

    acc: dict[str, dict] = {}
    per_client: dict[tuple[str, str], list[dict]] = defaultdict(list)

    for o in orders:
        if str(o.get("order_date") or "")[:10] != day:
            continue
        agent = (o.get("agent") or "").strip()
        if agent in excl_names or (o.get("agent_sd_id") in excl_ids):
            continue
        lg = league_of(o) if league_of else league_for_agent(agent, cfg)
        if not lg:
            continue
        if not is_delivered(o, cfg):
            continue

        net = net_sum_for_order(o, cfg)
        u = units_for_order(net, cfg)

        a = acc.setdefault(agent, {
            "agent": agent, "agent_sd_id": o.get("agent_sd_id"),
            "league": lg, "units": 0, "orders_count": 0, "net_sum": 0.0,
            "big_orders": [], "no_gift_orders": [], "multi_orders": [],
        })
        a["units"] += u
        a["orders_count"] += 1
        a["net_sum"] += net
        if big and net > big:
            a["big_orders"].append({"client": o.get("client"), "sum": net,
                                    "order_id": o.get("order_id")})
        if u >= 1 and not has_gift(o, cfg):
            a["no_gift_orders"].append({"client": o.get("client"), "sum": net,
                                        "order_id": o.get("order_id")})
        per_client[(agent, str(o.get("client") or ""))].append(o)

    # Bir do'konga bir kunda 2+ buyurtma (bo'lib kiritish belgisi)
    for (agent, client), lst in per_client.items():
        if len(lst) >= 2 and agent in acc:
            acc[agent]["multi_orders"].append({
                "client": client,
                "sums": [net_sum_for_order(x, cfg) for x in lst],
            })

    for a in acc.values():
        a["bonus"] = daily_bonus(a["units"], a["league"], cfg)
        a["to_threshold"] = to_threshold(a["units"], a["league"], cfg)
        lg = (cfg.get("leagues") or {}).get(a["league"]) or {}
        a["fire"] = a["units"] >= int(lg.get("fire_at", 10 ** 9))
    return acc


def league_totals(day_result: dict[str, dict], league: str) -> dict:
    """Liga bo'yicha yig'indi (guruh xabari sarlavhasi uchun)."""
    rows = [r for r in day_result.values() if r["league"] == league]
    return {
        "agents": len(rows),
        "units": sum(r["units"] for r in rows),
        "bonus": sum(r["bonus"] for r in rows),
        "passed": sum(1 for r in rows if r["bonus"] > 0),
        "fire": sum(1 for r in rows if r.get("fire")),
    }


def fmt_sum(n: float) -> str:
    """150000 → '150 000' (egasi talabi: ming ajratgich — bo'sh joy)."""
    return f"{int(round(n)):,}".replace(",", " ")
