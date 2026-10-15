"""
reportdata.py — FAQAT O'QIYDIGAN ma'lumot qatlami (admin web dastur uchun).

MUHIM: bu modul bazaga HECH NARSA YOZMAYDI. Faqat SELECT.
Raqamlar botlar bilan AYNAN bir xil chiqishi uchun nazorat botining hisob-kitob
qatlamini (DayContext, agent_strike, ...) qayta ishlatadi — kod takrorlanmaydi.

today (bugun) — Asia/Tashkent bo'yicha (Railway UTC bo'lsa ham to'g'ri kun chiqsin).
Natija 60 soniya keshlanadi (bir foydalanuvchi, ko'p tab almashtiradi).
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone

from db import get_conn
from nazorat.build import DayContext
from nazorat.core.balls import zero_streak
from nazorat.data import agent_returns_month, agent_strike

# Asia/Tashkent — yil davomida UTC+5 (yozgi vaqt yo'q). Tashqi kutubxonasiz, aniq.
TZ = timezone(timedelta(hours=5))
CACHE_TTL = 60  # soniya


def today_tashkent() -> date:
    return datetime.now(TZ).date()


def _league_label(league: str) -> str:
    return "Shahar" if league == "city" else "Viloyat"


# ------------------------------------------------------------------
# Kesh — DayContext og'ir (har agentga bir necha so'rov), 60s ushlab turamiz
# ------------------------------------------------------------------

_cache: dict = {"ts": 0.0, "day": None, "report": None, "dc": None}


def _last_sync(conn) -> str | None:
    row = conn.execute(
        "SELECT run_at, type, status FROM sync_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return row["run_at"] if row else None


def _build(day: date) -> tuple[dict, DayContext]:
    dc = DayContext(today=day)
    rules = dc.rules
    st = rules.statuses_ok
    fs = rules.status_full_return
    ph = ",".join("?" * len(st))
    dfrom = day.replace(day=1).isoformat()
    dto = day.isoformat()
    yesterday = (day - timedelta(days=1))
    wd_p = dc.wd_passed_val()
    wd_t = dc.wd_total_val()

    rows: list[dict] = []
    totals = {
        "today": 0.0, "yesterday": 0.0, "month": 0.0,
        "city_today": 0.0, "region_today": 0.0,
        "city_month": 0.0, "region_month": 0.0,
        "debt": 0.0, "returns_month": 0.0,
    }
    signals: list[dict] = []

    with get_conn() as conn:
        updated = _last_sync(conn)
        # AKB (unikal do'kon) — bugun va oy — bitta guruhli so'rovdan
        akb_today = {
            r["a"]: r["akb"] for r in conn.execute(
                f"SELECT agent_sd_id a, COUNT(DISTINCT client_sd_id) akb FROM orders "
                f"WHERE date=? AND status IN ({ph}) GROUP BY agent_sd_id",
                (dto, *st)).fetchall()
        }
        akb_month = {
            r["a"]: r["akb"] for r in conn.execute(
                f"SELECT agent_sd_id a, COUNT(DISTINCT client_sd_id) akb FROM orders "
                f"WHERE date>=? AND date<=? AND status IN ({ph}) GROUP BY agent_sd_id",
                (dfrom, dto, *st)).fetchall()
        }

        for league in ("city", "region"):
            sales_plan = rules.monthly_sales_plan[league]
            for s in dc.by_league[league]:
                sid = s.agent.sd_id
                kirdi, sotdi, strike = agent_strike(conn, sid, dfrom, dto)
                m_partial, m_full = agent_returns_month(conn, sid, dfrom, dto, st, fs)
                ret_month = m_partial + m_full
                plan_pct = s.month_sales / sales_plan * 100 if sales_plan else 0
                prognoz = (s.month_sales / wd_p * wd_t) if wd_p else 0
                prognoz_pct = prognoz / sales_plan * 100 if sales_plan else 0
                limit = s.agent.debt_limit or rules.debt_limit[league]
                debt_frac = s.debt_total / limit if limit else 0
                ret_pct = (ret_month / s.month_sales * 100) if s.month_sales else 0
                zs = zero_streak(s.balls, day)
                y_sales = s.day_sales.get(yesterday, 0.0)

                rows.append({
                    "sd_id": sid,
                    "name": s.agent.short,
                    "league": league,
                    "league_label": _league_label(league),
                    "code": s.agent.code,
                    "area": s.agent.area,
                    "observe": bool(s.agent.observe_only),
                    # O'RINDIQ ALMASHUVI — hamma ro'yxatda bir xil belgi
                    "seat_changed": bool(s.agent.seat_changed),
                    "seat_prev": s.agent.seat_prev_name,
                    "seat_since": s.agent.start_date,
                    # savdo
                    "today_sales": round(s.today_sales),
                    "yesterday_sales": round(y_sales),
                    "today_ball": s.today_ball,
                    "today_akb": int(akb_today.get(sid, 0)),
                    "month_sales": round(s.month_sales),
                    "month_akb": int(akb_month.get(sid, 0)),
                    "sales_plan": round(sales_plan),
                    "plan_pct": round(plan_pct, 1),
                    "prognoz": round(prognoz),
                    "prognoz_pct": round(prognoz_pct, 1),
                    # ball
                    "month_ball": s.month_ball,
                    "ball_plan": s.agent.ball_plan,
                    # strike (2x uchun eng muhim)
                    "strike": round(strike, 1),
                    "kirdi": kirdi,
                    "sotdi": sotdi,
                    # toy
                    "toy_blocks": round(s.toy_blocks, 1),
                    # qarz / vazvrat
                    "debt": round(s.debt_total),
                    "debt_limit": round(limit),
                    "debt_frac": round(debt_frac, 2),
                    "returns_month": round(ret_month),
                    "returns_partial": round(m_partial),
                    "returns_full": round(m_full),
                    "returns_pct": round(ret_pct, 1),
                    # vizit
                    "visits_today": s.visits_today,
                    "visits_month": s.visits_month,
                    "zero_streak": zs,
                })

                totals["today"] += s.today_sales
                totals["yesterday"] += y_sales
                totals["month"] += s.month_sales
                totals[f"{league}_today"] += s.today_sales
                totals[f"{league}_month"] += s.month_sales
                totals["debt"] += s.debt_total
                totals["returns_month"] += ret_month

                # signallar (observe_only agentlar signalga kirmaydi — nazorat botidek)
                if not s.agent.observe_only:
                    if zs >= rules.alerts.dead_days_zero_ball:
                        signals.append({"level": "bad", "name": s.agent.short,
                                        "text": f"{zs} kun ketma-ket 0 ball"})
                    if debt_frac > 1:
                        signals.append({"level": "bad", "name": s.agent.short,
                                        "text": f"qarz limitdan oshdi ({s.debt_total/1e6:.1f} / {limit/1e6:.0f} mln)"})
                    elif debt_frac >= 0.9:
                        signals.append({"level": "warn", "name": s.agent.short,
                                        "text": f"qarz limitga yaqin ({s.debt_total/1e6:.1f} / {limit/1e6:.0f} mln)"})
                    if strike and strike < 45 and kirdi >= 5:
                        signals.append({"level": "warn", "name": s.agent.short,
                                        "text": f"strike past ({strike:.0f}%)"})

    diff_pct = ((totals["today"] - totals["yesterday"]) / totals["yesterday"] * 100
                if totals["yesterday"] else None)

    report = {
        "day": dto,
        "day_label": f"{day.day}-{_MONTHS[day.month]} {day.year}",
        "updated": updated,
        "wd_passed": wd_p,
        "wd_total": wd_t,
        "agent_count": len([r for r in rows if not r["observe"]]),
        "observe_count": len([r for r in rows if r["observe"]]),
        "totals": {k: round(v) for k, v in totals.items()},
        "today_diff_pct": round(diff_pct, 1) if diff_pct is not None else None,
        "signals": signals,
        "agents": rows,
    }
    return report, dc


_MONTHS = ["", "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
           "Iyul", "Avgust", "Sentyabr", "Oktyabr", "Noyabr", "Dekabr"]


def get_report(force: bool = False) -> dict:
    now = time.time()
    day = today_tashkent()
    if (not force and _cache["report"] is not None
            and _cache["day"] == day and now - _cache["ts"] < CACHE_TTL):
        return _cache["report"]
    report, dc = _build(day)
    _cache.update(ts=now, day=day, report=report, dc=dc)
    return report


def get_context() -> DayContext:
    """Keshdagi DayContext (drill uchun). Kesh eskirgan bo'lsa qayta quradi."""
    get_report()
    return _cache["dc"]


# ------------------------------------------------------------------
# Bitta agent — batafsil (scorecard + qarz do'konlari + vazvrat do'konlari)
# ------------------------------------------------------------------

def agent_detail(sd_id: str) -> dict | None:
    report = get_report()
    dc = _cache["dc"]
    if sd_id not in dc.snap:
        return None
    row = next((r for r in report["agents"] if r["sd_id"] == sd_id), None)
    ball, plan, toy = dc.evening_cards(sd_id)   # nazorat botining aynan dict'lari
    morning = dc.morning_card(sd_id)            # qarz + vazvrat do'kon-do'kon
    return {
        "row": row,
        "ball": ball, "plan": plan, "toy": toy,
        "debts": [{"shop": d[0], "debt": round(d[1]), "age": d[2]} for d in morning["debts"]],
        "debt_total": round(morning["debt_total"]),
        "debt_limit": round(morning["debt_limit"]),
        "returns_full": [{"shop": s, "sum": round(v)} for s, v in morning["full_returns"]],
        "returns_partial": [{"shop": s, "sum": round(v)} for s, v in morning["partial_returns"]],
        "returns_month": round(morning["returns_month"]),
        "returns_date": morning["returns_date"],
    }


# ------------------------------------------------------------------
# Sklad (ostatka + tez tugaydigan) — asosiy botning mantiqi (30 kunlik o'rtacha)
# ------------------------------------------------------------------

STOCK_AVG_DAYS = 30


def _stock_days(stock: float, sold: float) -> float:
    if stock <= 0:
        return 0.0
    avg_daily = sold / STOCK_AVG_DAYS if sold > 0 else 0
    return stock / avg_daily if avg_daily > 0 else 9999.0


def stock_overview(max_low_days: int = 5) -> dict:
    with get_conn() as conn:
        rows = conn.execute(f"""
            SELECT s.product_sd_id,
                   MAX(s.product_name) AS name,
                   SUM(s.quantity) AS stock,
                   MAX(s.updated_at) AS upd,
                   COALESCE(cat.name, 'Kategoriyasiz') AS cat_name,
                   COALESCE((
                       SELECT SUM(oi.quantity) FROM order_items oi
                       JOIN orders o ON o.sd_id = oi.order_sd_id
                       WHERE oi.product_sd_id = s.product_sd_id
                         AND o.status IN (1,2,3)
                         AND o.date >= date('now','-{STOCK_AVG_DAYS} days')
                   ), 0) AS sold
            FROM stock s
            LEFT JOIN products p ON p.sd_id = s.product_sd_id
            LEFT JOIN categories cat ON cat.sd_id = p.category
            GROUP BY s.product_sd_id
        """).fetchall()

    items = []
    updated = None
    for r in rows:
        stock = float(r["stock"] or 0)
        sold = float(r["sold"] or 0)
        days = _stock_days(stock, sold)
        updated = updated or r["upd"]
        items.append({
            "name": r["name"], "cat": r["cat_name"],
            "stock": round(stock), "days": round(days) if days < 9999 else None,
        })

    low = sorted([it for it in items if it["days"] is not None and it["days"] <= max_low_days],
                 key=lambda x: x["days"])
    # to'liq ostatka: kritik (kam kun) birinchi
    def _order(it):
        d = it["days"]
        return (999999 if d is None else d, it["name"].lower())
    full = sorted(items, key=_order)
    return {
        "updated": (updated or "")[:19],
        "low_days": max_low_days,
        "low": low,
        "count": len(items),
        "critical": len([it for it in items if it["days"] is not None and it["days"] < 2]),
        "full": full[:400],
    }
