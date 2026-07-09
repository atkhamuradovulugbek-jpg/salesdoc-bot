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
from .data import (AgentSnapshot, MONTHS_UZ, agent_debt, agent_full_returns_by_shop,
                   agent_month_net_sales, agent_returns_by_shop, agent_returns_month,
                   agent_strike, agent_toy_day)


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
        """Bitta agent uchun 3 karta dict: [ball, plan, toy]."""
        s = self.snap[sd_id]
        ball = s.evening_dict(self._growth_pct.get(sd_id))
        # Bugungi o'rin (savdodan) + kechagiga nisbatan o'zgarish
        yd = self.today - timedelta(days=1)
        ball["today_rank"] = self.daily_rank(sd_id, "today")
        ball["yesterday_rank"] = self.daily_rank(sd_id, yd)
        ball["league_size"] = len([a for a in self.by_league[s.league] if not a.agent.observe_only])
        return [ball, s.plan_dict(), s.toy_dict()]

    def daily_rank(self, sd_id: str, when) -> int | None:
        """Agentning liga ichidagi KUNLIK o'rni (ball, teng bo'lsa savdo).
        when='today' yoki date obyekti (kechagi kun)."""
        league = self.snap[sd_id].league
        entries = []
        for s in self.by_league[league]:
            if s.agent.observe_only:
                continue
            if when == "today":
                ball, sales = s.today_ball, s.today_sales
            else:
                ball, sales = s.balls.get(when, 0), s.day_sales.get(when, 0.0)
            entries.append((s.agent.sd_id, ball, sales))
        ranked = sorted(entries, key=lambda e: (-e[1], -e[2]))
        for i, (aid, _, _) in enumerate(ranked, 1):
            if aid == sd_id:
                return i
        return None

    def morning_card(self, sd_id: str) -> dict:
        """Ertalabki qarz/vazvrat kartasi (kechagi vazvrat + qarz ro'yxati)."""
        s = self.snap[sd_id]
        ag = s.agent
        yesterday_d = self.today - timedelta(days=1)
        yesterday = yesterday_d.isoformat()
        returns_date = yesterday_d.strftime("%d.%m.%Y")   # 03.07.2026
        st = self.rules.statuses_ok
        fs = self.rules.status_full_return
        dfrom = self.month_first_iso()
        with get_conn() as conn:
            partial = agent_returns_by_shop(conn, sd_id, yesterday, st)      # qisman
            full = agent_full_returns_by_shop(conn, sd_id, yesterday, fs)    # to'liq
            m_partial, m_full = agent_returns_month(conn, sd_id, dfrom, self.today.isoformat(), st, fs)
            # 50 000 so'mdan yuqori BARCHA do'konlar (raqamli to'liq ro'yxat)
            debt_total, debts = agent_debt(conn, sd_id, self.today.isoformat(),
                                           min_debt=50_000, limit=200)
        partial_total = sum(r[1] for r in partial)
        full_total = sum(r[1] for r in full)
        day_total = partial_total + full_total
        month_total = m_partial + m_full

        debt_limit = ag.debt_limit or self.rules.debt_limit[s.league]
        returns_month_pct = (month_total / s.month_sales * 100) if s.month_sales else 0
        return {
            "name": ag.short,
            "league_label": "Shahar ligasi" if s.league == "city" else "Viloyat ligasi",
            "date_label": f"{self.today.day}-{MONTHS_UZ[self.today.month].upper()}",
            "returns_date": returns_date,
            "full_returns": full, "full_total": full_total,       # to'liq (status 4)
            "partial_returns": partial, "partial_total": partial_total,  # qisman (status 3)
            "returns_total": day_total,                            # kunlik jami
            "returns_month": month_total, "returns_month_pct": returns_month_pct,
            "returns_month_full": m_full, "returns_month_partial": m_partial,
            "ball_note": None,
            "debts": debts, "debts_all": debts, "debt_total": debt_total,
            "debt_limit": debt_limit,
        }

    def month_first_iso(self) -> str:
        return self.today.replace(day=1).isoformat()

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
                streak_note = f"{s.agent.short} {cnt} kun ketma-ket 4 ball to'pladi!"
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

    # ---------- supervayzer tablosi (strike rate markazda) ----------

    def _league_label2(self, league: str) -> str:
        return "shahar" if league == "city" else "viloyat"

    def supervisor_monthly(self, league: str) -> dict:
        """OYLIK supervayzer jadvali: strike, oy savdo, prognoz, ball, toy. Eng yomondan."""
        dfrom = self.month_first_iso()
        dto = self.today.isoformat()
        wd_p, wd_t = self.wd_passed_val(), self.wd_total_val()
        rows = []
        league_sales = league_prognoz = 0.0
        with get_conn() as conn:
            for s in self.by_league[league]:
                if s.agent.observe_only:
                    continue
                kirdi, sotdi, strike = agent_strike(conn, s.agent.sd_id, dfrom, dto)
                prognoz = (s.month_sales / wd_p * wd_t) if wd_p else 0
                league_sales += s.month_sales
                league_prognoz += prognoz
                rows.append({
                    "name": s.agent.short, "strike": strike,
                    "month_sales": s.month_sales, "prognoz": prognoz,
                    "ball": s.month_ball, "ball_plan": s.agent.ball_plan,
                    "toy": s.toy_blocks,
                })
        rows.sort(key=lambda r: r["strike"])
        focus = [f"{r['name']} (strike {r['strike']:.0f}%)" for r in rows[:3] if r["strike"] < 45]
        return {
            "title": f"supervayzer · oylik · {self._league_label2(league)}",
            "date_label": f"{self.today.day}-{MONTHS_UZ[self.today.month].upper()}",
            "rows": rows, "league_sales": league_sales, "league_prognoz": league_prognoz,
            "focus": focus, "month_label": MONTHS_UZ[self.today.month],
        }

    def supervisor_daily(self, league: str) -> dict:
        """KUNLIK supervayzer jadvali: bugungi savdo, ball, toy, vizit (kirdi/oldi)."""
        day = self.today.isoformat()
        st = self.rules.statuses_ok
        sku = self.rules.toy.sku_ids
        rows = []
        league_today = 0.0
        with get_conn() as conn:
            for s in self.by_league[league]:
                if s.agent.observe_only:
                    continue
                kirdi, sotdi, _ = agent_strike(conn, s.agent.sd_id, day, day)
                toy_day = agent_toy_day(conn, s.agent.sd_id, day, sku, st)
                league_today += s.today_sales
                rows.append({
                    "name": s.agent.short, "sales": s.today_sales, "ball": s.today_ball,
                    "toy": toy_day, "kirdi": kirdi, "sotdi": sotdi,
                })
        rows.sort(key=lambda r: -r["sales"])   # bugun eng ko'p sotgan yuqorida
        return {
            "title": f"supervayzer · kunlik · {self._league_label2(league)}",
            "date_label": f"{self.today.day}-{MONTHS_UZ[self.today.month].upper()}",
            "rows": rows, "league_today": league_today,
        }

    def wd_passed_val(self) -> int:
        from .core.workdays import workdays_passed
        return workdays_passed(self.today.year, self.today.month, self.today, self.rules.sunday_off)

    def wd_total_val(self) -> int:
        from .core.workdays import month_workdays
        return len(month_workdays(self.today.year, self.today.month, self.rules.sunday_off))

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
