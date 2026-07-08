"""
build.py — yuqori daraja: barcha agentlar snapshotlari + guruh/admin/oy yakuni
dict'larini yig'adi. bot.py shu funksiyalarni chaqirib, cards.py bilan chizadi.
"""

from __future__ import annotations

from datetime import date, timedelta

from db import get_conn

from . import storage
from .core.growth import GrowthEntry, growth_winner
from .core.podium import PodiumEntry, daily_rating, rank_podium
from .core.rules import Rules, load_agents, load_rules
from .data import (AgentSnapshot, MONTHS_UZ, agent_debt, agent_month_net_sales,
                   agent_returns_by_shop)


def prev_month(today: date) -> tuple[int, int]:
    first = today.replace(day=1)
    last_prev = first - timedelta(days=1)
    return last_prev.year, last_prev.month


class DayContext:
    """Bir kun uchun barcha agentlarning snapshotlari + liga hisoblari (bir marta o'qiydi)."""

    def __init__(self, today: date | None = None,
                 rules: Rules | None = None, agents_cfg=None):
        self.today = today or date.today()
        self.rules = rules or load_rules()
        self.agents_cfg = agents_cfg or load_agents()
        self.agents = self.agents_cfg.agents
        self.by_league: dict[str, list[AgentSnapshot]] = {"city": [], "region": []}
        self.snap: dict[str, AgentSnapshot] = {}
        self._growth_pct: dict[str, float | None] = {}
        self._load()

    def _load(self):
        py, pm = prev_month(self.today)
        prev_from = date(py, pm, 1).isoformat()
        # o'tgan oyning oxirgi kuni
        prev_to = (self.today.replace(day=1) - timedelta(days=1)).isoformat()
        st = self.rules.statuses_ok
        with get_conn() as conn:
            for ag in self.agents:
                s = AgentSnapshot(conn, ag, self.rules, self.today)
                self.snap[ag.sd_id] = s
                self.by_league[ag.league].append(s)
                # o'sish %: o'tgan oy sof savdo bilan
                prev_net = agent_month_net_sales(conn, ag.sd_id, prev_from, prev_to, st)
                cur_net = s.month_net_sales
                if prev_net > 0:
                    self._growth_pct[ag.sd_id] = (cur_net - prev_net) / prev_net * 100
                else:
                    self._growth_pct[ag.sd_id] = None

    # ---------- shaxsiy kartalar ----------

    def evening_cards(self, sd_id: str) -> list[dict]:
        """Bitta agent uchun 3 karta dict: [evening, plan, toy]."""
        s = self.snap[sd_id]
        return [
            s.evening_dict(self._growth_pct.get(sd_id)),
            s.plan_dict(),
            s.toy_dict(),
        ]

    def morning_card(self, sd_id: str) -> dict:
        """Ertalabki qarz/vazvrat kartasi (kechagi vazvrat + qarz ro'yxati)."""
        s = self.snap[sd_id]
        ag = s.agent
        yesterday = (self.today - timedelta(days=1)).isoformat()
        st = self.rules.statuses_ok
        with get_conn() as conn:
            returns = agent_returns_by_shop(conn, sd_id, yesterday, st)
            debt_total, debts = agent_debt(conn, sd_id, self.today.isoformat())
        returns_total = sum(r[1] for r in returns)

        # Vazvrat ballni o'zgartirganmi? (kechagi kun ballini net/brutto solishtir)
        ball_note = None
        if self.rules.returns_reduce_ball and returns_total > 0:
            from .core.balls import daily_ball
            dp = self.rules.daily_plan[s.league]
            y_date = self.today - timedelta(days=1)
            y_sales = s.day_sales.get(y_date, 0.0)
            b_gross = daily_ball(y_sales, dp, self.rules.ball_scale)
            b_net = daily_ball(max(y_sales - returns_total, 0), dp, self.rules.ball_scale)
            if b_net < b_gross:
                ball_note = (f"{y_date.day}-{MONTHS_UZ[y_date.month]} balling qayta hisoblandi: "
                             f"{b_gross} » {b_net} ball "
                             f"(kun savdosidan {returns_total:,.0f} ayirildi)".replace(",", " "))

        debt_limit = ag.debt_limit or self.rules.debt_limit[s.league]
        return {
            "name": ag.name.split()[0] if " " in ag.name else ag.name,
            "league_label": "Shahar ligasi" if s.league == "city" else "Viloyat ligasi",
            "date_label": f"{self.today.day}-{MONTHS_UZ[self.today.month].upper()}",
            "returns": returns, "returns_total": returns_total, "ball_note": ball_note,
            "debts": debts, "debt_total": debt_total, "debt_limit": debt_limit,
            "debt_more": max(len(debts) - 7, 0),
        }

    # ---------- guruh ----------

    def group_daily(self, league: str) -> dict:
        """Guruhga kunlik ball reytingi (yig'indisiz)."""
        entries = []
        for s in self.by_league[league]:
            if s.agent.observe_only:
                continue
            entries.append({"sd_id": s.agent.sd_id, "name": s.agent.short,
                            "ball": s.today_ball, "sales": s.today_sales})
        rating = daily_rating(entries)
        rows = [(e["name"], e["ball"], e["sales"]) for e in rating]

        # Seriya: ketma-ket 4 ball qilgan bormi?
        streak_note = None
        for s in self.by_league[league]:
            days = sorted([d for d in s.balls if d <= self.today], reverse=True)
            cnt = 0
            for d in days:
                if s.balls[d] == 4:
                    cnt += 1
                else:
                    break
            if cnt >= 3:
                streak_note = f"Seriya: {s.agent.short} {cnt} kun ketma-ket 4 ball!"
                break

        return {
            "league_label": "Shahar ligasi" if league == "city" else "Viloyat ligasi",
            "date_label": f"{self.today.day}-{MONTHS_UZ[self.today.month].upper()}",
            "rows": rows, "streak_note": streak_note,
        }

    # ---------- admin ----------

    def admin_evening(self, league: str) -> dict:
        rows, signals = [], []
        for s in sorted(self.by_league[league], key=lambda x: -x.today_sales):
            if s.agent.observe_only:
                continue   # ketayotgan/yangi agent — jadval va signaldan tashqarida
            sales_plan = self.rules.monthly_sales_plan[league]
            plan_pct = s.month_sales / sales_plan * 100 if sales_plan else 0
            limit = s.agent.debt_limit or self.rules.debt_limit[league]
            frac = s.debt_total / limit if limit else 0
            rows.append((s.agent.short, s.today_sales, s.month_ball,
                         plan_pct, s.toy_blocks, s.debt_total / 1_000_000, frac))
            # signallar
            from .core.balls import zero_streak
            zs = zero_streak(s.balls, self.today)
            if zs >= self.rules.alerts.dead_days_zero_ball:
                signals.append(("bad", f"{s.agent.short}: {zs} kun ketma-ket 0 ball"))
            if frac > 1:
                signals.append(("bad", f"{s.agent.short}: qarz limitdan oshdi "
                                       f"({s.debt_total/1e6:.1f} / {limit/1e6:.0f} mln)"))
            elif frac >= 0.9:
                signals.append(("warn", f"{s.agent.short}: qarz limitga yaqin "
                                        f"({s.debt_total/1e6:.1f} / {limit/1e6:.0f} mln)"))
        return {
            "title": f"kechki svodka · {'shahar' if league=='city' else 'viloyat'}",
            "date_label": f"{self.today.day}-{MONTHS_UZ[self.today.month].upper()}",
            "rows": rows, "signals": signals,
        }

    # ---------- podium / o'sish (oy yakuni va joriy holat) ----------

    def podium_result(self, league: str, last_first_sd_id: str | None = None):
        entries = [
            PodiumEntry(sd_id=s.agent.sd_id, name=s.agent.short,
                        total_ball=s.month_ball, ball_plan=s.agent.ball_plan,
                        month_net_sales=s.month_net_sales, observe_only=s.agent.observe_only)
            for s in self.by_league[league]
        ]
        return rank_podium(entries, self.rules.podium, last_first_sd_id)

    def growth_result(self, league: str, last_winner_sd_id: str | None = None):
        py, pm = prev_month(self.today)
        prev_from = date(py, pm, 1).isoformat()
        prev_to = (self.today.replace(day=1) - timedelta(days=1)).isoformat()
        st = self.rules.statuses_ok
        entries = []
        with get_conn() as conn:
            for s in self.by_league[league]:
                prev_net = agent_month_net_sales(conn, s.agent.sd_id, prev_from, prev_to, st)
                entries.append(GrowthEntry(
                    sd_id=s.agent.sd_id, name=s.agent.short,
                    prev_net_sales=prev_net, cur_net_sales=s.month_net_sales,
                    observe_only=s.agent.observe_only))
        return growth_winner(entries, self.rules.growth, last_winner_sd_id)


def _first(name: str) -> str:
    return name.split()[0] if " " in name else name
