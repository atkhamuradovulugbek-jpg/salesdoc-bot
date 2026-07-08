"""
data.py — DB'dan o'qib, core hisoblarini yuritib, kartalar uchun tayyor dict beradi.
Bu qatlam core (sof funksiyalar) va cards (chizish) orasidagi ko'prik.
"""

from __future__ import annotations

from datetime import date, timedelta

from db import get_conn

from .core.balls import daily_ball, month_balls, total_balls, zero_streak
from .core.forecast import best_action, money_risks, project
from .core.growth import GrowthEntry, growth_winner
from .core.kpi import commission_amount, next_bonus_gap, plan_bonus
from .core.podium import PodiumEntry, daily_rating, rank_podium
from .core.rules import Agent, AgentsConfig, Rules
from .core.toy import ToyLine, net_blocks, toy_status
from .core.workdays import month_workdays, workdays_passed, workdays_remaining
from . import storage

MONTHS_UZ = ["", "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
             "Iyul", "Avgust", "Sentyabr", "Oktyabr", "Noyabr", "Dekabr"]

# Do'konni "haqiqiy" agentga bog'lash (reports.py bilan bir xil mantiq):
# do'konga eng ko'p zakaz bergan AKTIV agent. Ketgan agent qarzi yangisiga o'tadi.
_CLIENT_AGENT_CTE = """
    client_agent AS (
        SELECT client_sd_id, agent_sd_id FROM (
            SELECT o.client_sd_id, o.agent_sd_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY o.client_sd_id
                       ORDER BY COUNT(*) DESC, MAX(o.date) DESC
                   ) AS rn
            FROM orders o
            JOIN agents a ON a.sd_id = o.agent_sd_id AND a.active = 'Y'
            GROUP BY o.client_sd_id, o.agent_sd_id
        ) WHERE rn = 1
    )
"""


def agent_debt(conn, sd_id: str, today: str, min_debt: float = 50_000,
               limit: int = 20) -> tuple[float, list[tuple[str, float, int | None]]]:
    """Agentning qarz qoldig'i: (jami, [(do'kon, summa, yosh_kun)])."""
    rows = conn.execute(f"""
        WITH {_CLIENT_AGENT_CTE}
        SELECT b.client_sd_id AS cid, b.client_name AS shop, ABS(b.balance) AS debt
        FROM balances b
        JOIN clients c ON c.sd_id = b.client_sd_id
        LEFT JOIN client_agent ca ON ca.client_sd_id = c.sd_id
        WHERE COALESCE(ca.agent_sd_id, c.primary_agent_sd_id)=? AND b.balance <= ?
        ORDER BY debt DESC LIMIT ?
    """, (sd_id, -min_debt, limit)).fetchall()
    shops = []
    for r in rows:
        age = storage.debt_age_days(conn, r["cid"], today)
        shops.append((r["shop"] or "Do'kon", float(r["debt"]), age))
    total = sum(s[1] for s in shops)
    return total, shops


def agent_debt_total(conn, sd_id: str) -> float:
    """Faqat jami qarz (karta uchun tez)."""
    row = conn.execute(f"""
        WITH {_CLIENT_AGENT_CTE}
        SELECT COALESCE(SUM(ABS(b.balance)),0) AS d
        FROM balances b
        JOIN clients c ON c.sd_id = b.client_sd_id
        LEFT JOIN client_agent ca ON ca.client_sd_id = c.sd_id
        WHERE COALESCE(ca.agent_sd_id, c.primary_agent_sd_id)=? AND b.balance < 0
    """, (sd_id,)).fetchone()
    return float(row["d"] or 0)


def agent_returns_by_shop(conn, sd_id: str, day: str,
                          statuses: list[int]) -> list[tuple[str, float]]:
    """Berilgan kundagi vazvratlar do'kon bo'yicha (ertalabki karta uchun)."""
    ph = ",".join("?" * len(statuses))
    rows = conn.execute(f"""
        SELECT c.name AS shop, SUM(o.total_returns) AS ret
        FROM orders o LEFT JOIN clients c ON c.sd_id = o.client_sd_id
        WHERE o.agent_sd_id=? AND o.date=? AND o.status IN ({ph}) AND o.total_returns>0
        GROUP BY o.client_sd_id ORDER BY ret DESC
    """, (sd_id, day, *statuses)).fetchall()
    return [(r["shop"] or "Do'kon", float(r["ret"] or 0)) for r in rows]


# ------------------------------------------------------------------
# Xom ma'lumot yig'ish (bitta agent, bitta oy)
# ------------------------------------------------------------------

def _month_bounds(today: date) -> tuple[str, str, str]:
    first = today.replace(day=1)
    return first.isoformat(), today.isoformat(), f"{first.isoformat()}"


def agent_day_sales(conn, sd_id: str, dfrom: str, dto: str,
                    statuses: list[int]) -> dict[date, float]:
    ph = ",".join("?" * len(statuses))
    rows = conn.execute(f"""
        SELECT date, SUM(total_after_discount) AS s
        FROM orders WHERE agent_sd_id=? AND date>=? AND date<=? AND status IN ({ph})
        GROUP BY date
    """, (sd_id, dfrom, dto, *statuses)).fetchall()
    return {date.fromisoformat(r["date"]): float(r["s"] or 0) for r in rows}


def agent_day_returns(conn, sd_id: str, dfrom: str, dto: str,
                      statuses: list[int]) -> dict[date, float]:
    ph = ",".join("?" * len(statuses))
    rows = conn.execute(f"""
        SELECT date, SUM(total_returns) AS r
        FROM orders WHERE agent_sd_id=? AND date>=? AND date<=? AND status IN ({ph})
        GROUP BY date
    """, (sd_id, dfrom, dto, *statuses)).fetchall()
    return {date.fromisoformat(r["date"]): float(r["r"] or 0) for r in rows}


def agent_toy_lines(conn, sd_id: str, dfrom: str, dto: str,
                    sku_ids: list[str], statuses: list[int]) -> list[ToyLine]:
    ph_s = ",".join("?" * len(statuses))
    ph_k = ",".join("?" * len(sku_ids))
    rows = conn.execute(f"""
        SELECT oi.block AS block, oi.quantity AS qty, oi.returned AS ret
        FROM order_items oi JOIN orders o ON o.sd_id = oi.order_sd_id
        WHERE o.agent_sd_id=? AND o.date>=? AND o.date<=?
          AND o.status IN ({ph_s}) AND oi.product_sd_id IN ({ph_k})
    """, (sd_id, dfrom, dto, *statuses, *sku_ids)).fetchall()
    return [ToyLine(blocks=float(r["block"] or 0), quantity=float(r["qty"] or 0),
                    returned=float(r["ret"] or 0)) for r in rows]


def agent_month_net_sales(conn, sd_id: str, dfrom: str, dto: str,
                          statuses: list[int]) -> float:
    """Oylik SOF savdo (vazvrat ayirilgan) — o'sish/podium tie-break uchun."""
    ph = ",".join("?" * len(statuses))
    row = conn.execute(f"""
        SELECT COALESCE(SUM(total_after_discount - total_returns),0) AS s
        FROM orders WHERE agent_sd_id=? AND date>=? AND date<=? AND status IN ({ph})
    """, (sd_id, dfrom, dto, *statuses)).fetchone()
    return float(row["s"] or 0)


def agent_visits(conn, sd_id: str, dfrom: str, dto: str) -> tuple[int, int]:
    """(oylik vizit, bugungi vizit) — visited=1."""
    m = conn.execute("""
        SELECT COUNT(*) c FROM visits WHERE agent_sd_id=? AND date>=? AND date<=? AND visited=1
    """, (sd_id, dfrom, dto)).fetchone()["c"]
    t = conn.execute("""
        SELECT COUNT(*) c FROM visits WHERE agent_sd_id=? AND date=? AND visited=1
    """, (sd_id, dto)).fetchone()["c"]
    return int(m or 0), int(t or 0)


# ------------------------------------------------------------------
# Bitta agent uchun to'liq hisob (barcha kartalar shundan chizadi)
# ------------------------------------------------------------------

class AgentSnapshot:
    """Bitta agentning bir kundagi to'liq holati."""

    def __init__(self, conn, agent: Agent, rules: Rules, today: date):
        self.agent = agent
        self.rules = rules
        self.today = today
        self.league = agent.league
        self.month_first = today.replace(day=1)
        dfrom = self.month_first.isoformat()
        dto = today.isoformat()
        st = rules.statuses_ok

        self.day_sales = agent_day_sales(conn, agent.sd_id, dfrom, dto, st)
        self.day_returns = agent_day_returns(conn, agent.sd_id, dfrom, dto, st)
        self.toy_lines = agent_toy_lines(conn, agent.sd_id, dfrom, dto, rules.toy.sku_ids, st)
        self.month_net_sales = agent_month_net_sales(conn, agent.sd_id, dfrom, dto, st)
        self.visits_month, self.visits_today = agent_visits(conn, agent.sd_id, dfrom, dto)

        self.workdays = month_workdays(today.year, today.month, rules.sunday_off)
        self.wd_passed = workdays_passed(today.year, today.month, today, rules.sunday_off)
        self.wd_remaining = workdays_remaining(today.year, today.month, today, rules.sunday_off)
        self.wd_total = len(self.workdays)

        # Ball (net — vazvrat ayirilgan, iyul qoidasi)
        self.balls = month_balls(
            self.day_sales, self.day_returns,
            daily_plan=rules.daily_plan[self.league],
            scale=rules.ball_scale,
            workdays=[d for d in self.workdays if d <= today],
            net_returns=rules.returns_reduce_ball,
        )
        self.month_ball = total_balls(self.balls)
        self.today_sales = self.day_sales.get(today, 0.0)
        self.today_returns = self.day_returns.get(today, 0.0)
        self.today_ball = daily_ball(
            max(self.today_sales - (self.today_returns if rules.returns_reduce_ball else 0), 0),
            rules.daily_plan[self.league], rules.ball_scale,
        )

        # Oylik savdo (brutto) — KPI plan uchun
        self.month_sales = sum(self.day_sales.values())
        self.month_returns = sum(self.day_returns.values())

        # Toy
        self.toy_blocks = net_blocks(self.toy_lines, rules.toy)
        self.toy = toy_status(self.toy_blocks, rules.toy)

        # Qarz (jami — kartalarda ko'rsatiladi)
        self.debt_total = agent_debt_total(conn, agent.sd_id)

    # ---- kartalar uchun dict'lar ----

    def evening_dict(self, growth_pct: float | None) -> dict:
        r = self.rules
        sales_plan = r.monthly_sales_plan[self.league]
        proj = project(self.month_ball, self.month_sales, self.agent.ball_plan,
                       self.wd_passed, self.wd_total)
        kpi_pct = self.month_sales / sales_plan * 100 if sales_plan else 0
        gap = next_bonus_gap(self.month_sales, sales_plan, r.kpi_plan_bonus[self.league])
        daily_plan = r.daily_plan[self.league]
        today_pct = self.today_sales / daily_plan * 100 if daily_plan else 0
        ret_pct = self.month_returns / self.month_sales * 100 if self.month_sales else 0

        # Eng foydali harakat
        risks = money_risks(proj, self.toy, self.month_sales, sales_plan, r, self.league)
        act = best_action(risks)

        return {
            "name": self.agent.short,
            "league_label": "Shahar ligasi" if self.league == "city" else "Viloyat ligasi",
            "date_label": f"{self.today.day}-{MONTHS_UZ[self.today.month].upper()}",
            "ball_today": self.today_ball, "today_sales": self.today_sales, "today_pct": today_pct,
            "month_ball": self.month_ball, "ball_plan": self.agent.ball_plan,
            "prognoz_ball": proj.ball_projected, "per_day_needed": proj.ball_per_day_needed,
            "growth_pct": growth_pct, "kpi_pct": kpi_pct,
            "kpi_gap": gap if (gap and gap[0] > 0) else None,
            "returns_today": self.today_returns, "returns_month_pct": ret_pct,
            "debt": self.debt_total, "debt_limit": self.agent.debt_limit
                or r.debt_limit[self.league],
            "action": act.action if act else None,
            "observe_only": self.agent.observe_only,
        }

    def plan_dict(self) -> dict:
        r = self.rules
        sales_plan = r.monthly_sales_plan[self.league]
        plan_pct = self.month_sales / sales_plan * 100 if sales_plan else 0
        plan_remaining = max(sales_plan - self.month_sales, 0)
        daily_avg = self.month_sales / self.wd_passed if self.wd_passed else 0
        prognoz = daily_avg * self.wd_total
        prognoz_pct = prognoz / sales_plan * 100 if sales_plan else 0
        daily_required = plan_remaining / self.wd_remaining if self.wd_remaining else 0
        daily_plan = r.daily_plan[self.league]
        today_pct = self.today_sales / daily_required * 100 if daily_required else (
            self.today_sales / daily_plan * 100 if daily_plan else 0)

        visit_plan = 750
        visit_remaining = max(visit_plan - self.visits_month, 0)
        visit_daily_req = visit_remaining / self.wd_remaining if self.wd_remaining else 0

        if prognoz_pct >= 100:
            status = f"Prognoz plandan yuqori — shu tempda oy {prognoz_pct:.0f}% bilan yopiladi. Davom et!"
            scheme = "ok"
        elif prognoz_pct >= 80:
            status = f"Prognoz {prognoz_pct:.0f}% — tempni biroz oshirsang plan bajariladi."
            scheme = "warn"
        else:
            status = f"Prognoz {prognoz_pct:.0f}% — savdo faolligini oshirish kerak."
            scheme = "warn"

        return {
            "name": self.agent.short,
            "date_label": f"{self.today.day}-{MONTHS_UZ[self.today.month].upper()}",
            "month_label": MONTHS_UZ[self.today.month],
            "wd_total": self.wd_total, "wd_passed": self.wd_passed, "wd_remaining": self.wd_remaining,
            "sales_plan": sales_plan, "sales_done": self.month_sales, "plan_pct": plan_pct,
            "plan_remaining": plan_remaining, "prognoz": prognoz, "prognoz_pct": prognoz_pct,
            "daily_required": daily_required, "today_sales": self.today_sales, "today_pct": today_pct,
            "visit_plan": visit_plan, "visits_done": self.visits_month,
            "visit_remaining": visit_remaining, "visit_daily_required": visit_daily_req,
            "today_visits": self.visits_today,
            "status_text": status, "status_scheme": scheme,
        }

    def toy_dict(self) -> dict:
        r = self.rules
        tiers = sorted([(t.blocks, t.bonus) for t in r.toy.tiers])
        per_day = (self.toy.blocks_to_next / max(self.wd_remaining, 1)
                   if self.toy.blocks_to_next else 0)
        return {
            "name": self.agent.short,
            "date_label": f"{self.today.day}-{MONTHS_UZ[self.today.month].upper()}",
            "blocks": self.toy.blocks, "tiers": tiers,
            "reached_bonus": self.toy.reached_bonus,
            "next_blocks": self.toy.next_tier_blocks, "next_bonus": self.toy.next_tier_bonus,
            "to_next": self.toy.blocks_to_next or 0, "per_day_needed": per_day,
        }
