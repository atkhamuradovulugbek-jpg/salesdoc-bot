"""
reports.py — Bazadan ma'lumot o'qib, tayyor matn hisobotlar qaytaradi.
Bot (bot.py) shu funksiyalarni chaqiradi.
"""

from datetime import date, timedelta

from db import get_conn


def _fmt(amount: float) -> str:
    """Sonni o'qish uchun: 12345678 → '12.3 mln'."""
    if amount >= 1_000_000:
        return f"{amount / 1_000_000:.1f} mln so'm"
    if amount >= 1_000:
        return f"{amount / 1_000:.0f} ming so'm"
    return f"{amount:.0f} so'm"


# ------------------------------------------------------------------
# Kunlik savdo
# ------------------------------------------------------------------

def daily_sales_report(day: str) -> str:
    """
    day — YYYY-MM-DD
    Qaytaradi: agent bo'yicha savdo va jami.
    """
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT a.name AS agent, SUM(o.total_after_discount) AS total
            FROM orders o
            LEFT JOIN agents a ON a.sd_id = o.agent_sd_id
            WHERE o.date = ? AND o.status IN (1, 2, 3)
            GROUP BY o.agent_sd_id
            ORDER BY total DESC
        """, (day,)).fetchall()

    if not rows:
        return f"💰 <b>{day} — savdo yo'q yoki ma'lumot yuklanmagan.</b>"

    lines = [f"💰 <b>Kunlik savdo — {day}</b>\n"]
    total = 0.0
    for i, r in enumerate(rows, 1):
        agent = r["agent"] or "Noma'lum"
        lines.append(f"{i}. {agent} — {_fmt(r['total'])}")
        total += r["total"] or 0
    lines.append(f"\n<b>JAMI: {_fmt(total)}</b>")
    return "\n".join(lines)


# ------------------------------------------------------------------
# Oylik savdo + AKB
# ------------------------------------------------------------------

def monthly_sales_report(year: int, month: int) -> str:
    date_from = f"{year:04d}-{month:02d}-01"
    if month == 12:
        date_to = f"{year + 1:04d}-01-01"
    else:
        date_to = f"{year:04d}-{month + 1:02d}-01"

    month_names = ["", "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
                   "Iyul", "Avgust", "Sentyabr", "Oktyabr", "Noyabr", "Dekabr"]

    with get_conn() as conn:
        rows = conn.execute("""
            SELECT
                o.agent_sd_id,
                a.name AS agent,
                SUM(o.total_after_discount) AS total,
                COUNT(DISTINCT o.client_sd_id) AS akb
            FROM orders o
            LEFT JOIN agents a ON a.sd_id = o.agent_sd_id
            WHERE o.date >= ? AND o.date < ? AND o.status IN (1, 2, 3)
            GROUP BY o.agent_sd_id
            ORDER BY total DESC
        """, (date_from, date_to)).fetchall()

    if not rows:
        return f"📈 <b>{month_names[month]} {year} — ma'lumot yo'q.</b>"

    lines = [f"📈 <b>{year} — {month_names[month]} oylik savdo</b>\n"]
    grand_total = 0.0
    all_clients: set = set()

    for i, r in enumerate(rows, 1):
        agent = r["agent"] or "Noma'lum"
        lines.append(f"{i}. {agent} — {_fmt(r['total'])} | AKB: {r['akb']}")
        grand_total += r["total"] or 0

    # Umumiy unikal mijozlar
    with get_conn() as conn:
        row = conn.execute("""
            SELECT COUNT(DISTINCT client_sd_id) AS cnt
            FROM orders
            WHERE date >= ? AND date < ? AND status IN (1,2,3)
        """, (date_from, date_to)).fetchone()
    total_akb = row["cnt"] if row else 0

    lines.append(f"\n<b>JAMI: {_fmt(grand_total)} | Umumiy AKB: {total_akb}</b>")
    return "\n".join(lines)


# ------------------------------------------------------------------
# Agentlar qarzi (umumiy ro'yxat)
# ------------------------------------------------------------------

def agents_debt_report() -> str:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT
                a.name AS agent,
                SUM(ABS(b.balance)) AS debt
            FROM balances b
            JOIN clients c ON c.sd_id = b.client_sd_id
            LEFT JOIN agents a ON a.sd_id = c.primary_agent_sd_id
            WHERE b.balance < 0
            GROUP BY c.primary_agent_sd_id
            ORDER BY debt DESC
        """).fetchall()

    if not rows:
        return "🏪 <b>Hozirda qarzdor agent yo'q.</b>"

    lines = ["🏪 <b>Agentlar qarzi</b>\n"]
    total = 0.0
    for i, r in enumerate(rows, 1):
        agent = r["agent"] or "Agentsiz"
        lines.append(f"{i}. {agent} — {_fmt(r['debt'])}")
        total += r["debt"] or 0
    lines.append(f"\n<b>JAMI qarz: {_fmt(total)}</b>")
    return "\n".join(lines)


# ------------------------------------------------------------------
# Bitta agent qarzdor do'konlari
# ------------------------------------------------------------------

def agent_debt_detail(agent_sd_id: str) -> str:
    with get_conn() as conn:
        agent_row = conn.execute("SELECT name FROM agents WHERE sd_id=?", (agent_sd_id,)).fetchone()
        agent_name = agent_row["name"] if agent_row else "Noma'lum agent"

        rows = conn.execute("""
            SELECT b.client_name AS shop, ABS(b.balance) AS debt
            FROM balances b
            JOIN clients c ON c.sd_id = b.client_sd_id
            WHERE c.primary_agent_sd_id = ? AND b.balance < 0
            ORDER BY debt DESC
        """, (agent_sd_id,)).fetchall()

    if not rows:
        return f"👤 <b>{agent_name}</b> — qarzdor do'kon yo'q."

    lines = [f"👤 <b>{agent_name} — qarzdor do'konlar</b>\n"]
    total = 0.0
    for i, r in enumerate(rows, 1):
        lines.append(f"{i}. {r['shop']} — {_fmt(r['debt'])}")
        total += r["debt"] or 0
    lines.append(f"\n<b>Jami: {_fmt(total)}</b>")
    return "\n".join(lines)


# ------------------------------------------------------------------
# Vizitlar
# ------------------------------------------------------------------

def visits_report(day: str) -> str:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT agent_name, COUNT(*) AS cnt
            FROM visits
            WHERE date = ? AND visited = 1
            GROUP BY agent_sd_id
            ORDER BY cnt DESC
        """, (day,)).fetchall()

        all_agents = conn.execute("SELECT name FROM agents WHERE active='Y'").fetchall()

    if not rows:
        return f"🚶 <b>{day} — vizit ma'lumoti yo'q.</b>"

    visited_names = {r["agent_name"] for r in rows}
    lines = [f"🚶 <b>Vizitlar — {day}</b>\n"]
    total = 0
    for i, r in enumerate(rows, 1):
        lines.append(f"{i}. {r['agent_name']} — {r['cnt']} ta tashrif")
        total += r["cnt"]
    lines.append(f"\n<b>Jami: {total} ta tashrif</b>")

    zero_visit = [a["name"] for a in all_agents if a["name"] not in visited_names]
    if zero_visit:
        lines.append("\n⚠️ <b>0 vizit:</b> " + ", ".join(zero_visit))

    return "\n".join(lines)


# ------------------------------------------------------------------
# TOP tovarlar
# ------------------------------------------------------------------

def top_products_report(date_from: str, date_to: str, top_n: int = 20) -> str:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT oi.product_name AS name, SUM(oi.summa) AS total
            FROM order_items oi
            JOIN orders o ON o.sd_id = oi.order_sd_id
            WHERE o.date >= ? AND o.date <= ? AND o.status IN (1,2,3)
            GROUP BY oi.product_sd_id
            ORDER BY total DESC
            LIMIT ?
        """, (date_from, date_to, top_n)).fetchall()

    if not rows:
        return f"🏆 <b>{date_from} — {date_to} — ma'lumot yo'q.</b>"

    lines = [f"🏆 <b>TOP {top_n} tovar ({date_from} — {date_to})</b>\n"]
    for i, r in enumerate(rows, 1):
        lines.append(f"{i}. {r['name']} — {_fmt(r['total'])}")
    return "\n".join(lines)


# ------------------------------------------------------------------
# Sklad ostatka
# ------------------------------------------------------------------

def stock_report() -> str:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT product_name, warehouse, quantity, updated_at
            FROM stock
            ORDER BY warehouse, quantity DESC
        """).fetchall()

    if not rows:
        return "📦 <b>Sklad ma'lumoti yuklanmagan.</b>"

    last_updated = rows[0]["updated_at"] if rows else ""
    lines = [f"📦 <b>Sklad ostatka</b> (yangilangan: {last_updated[:10]})\n"]
    current_wh = None
    for r in rows:
        if r["warehouse"] != current_wh:
            current_wh = r["warehouse"]
            lines.append(f"\n🏭 <b>{current_wh}</b>")
        qty = r["quantity"]
        lines.append(f"  • {r['product_name']} — {qty:,.0f} dona")
    return "\n".join(lines)


# ------------------------------------------------------------------
# O'lik do'konlar
# ------------------------------------------------------------------

def dead_outlets_report(dead_days: int = 14, lookback_days: int = 90) -> str:
    today = date.today().isoformat()
    lookback_from = (date.today() - timedelta(days=lookback_days)).isoformat()
    dead_from = (date.today() - timedelta(days=dead_days)).isoformat()

    with get_conn() as conn:
        # Faol bo'lgan do'konlar (lookback ichida kamida 1 buyurtma)
        active = conn.execute("""
            SELECT DISTINCT client_sd_id FROM orders
            WHERE date >= ? AND status IN (1,2,3)
        """, (lookback_from,)).fetchall()
        active_ids = {r["client_sd_id"] for r in active}

        # So'nggi dead_days ichida buyurtma berganlar
        recent = conn.execute("""
            SELECT DISTINCT client_sd_id FROM orders
            WHERE date >= ? AND status IN (1,2,3)
        """, (dead_from,)).fetchall()
        recent_ids = {r["client_sd_id"] for r in recent}

        dead_ids = active_ids - recent_ids
        if not dead_ids:
            return f"💀 <b>O'lik do'konlar yo'q</b> (chegarа: {dead_days} kun)\n\nHamma do'konlar so'nggi {dead_days} kunda faol."

        placeholders = ",".join("?" * len(dead_ids))
        rows = conn.execute(f"""
            SELECT
                c.sd_id, c.name AS shop, c.primary_agent_sd_id,
                a.name AS agent,
                MAX(o.date) AS last_order
            FROM clients c
            LEFT JOIN agents a ON a.sd_id = c.primary_agent_sd_id
            LEFT JOIN orders o ON o.client_sd_id = c.sd_id AND o.status IN (1,2,3)
            WHERE c.sd_id IN ({placeholders})
            GROUP BY c.sd_id
            ORDER BY a.name, last_order ASC
        """, list(dead_ids)).fetchall()

    lines = [f"💀 <b>O'lik do'konlar</b> (oxirgi {dead_days} kunda buyurtma yo'q)\n"]
    current_agent = None
    count = 0
    for r in rows:
        agent = r["agent"] or "Agentsiz"
        if agent != current_agent:
            current_agent = agent
            lines.append(f"\n👤 <b>{agent}</b>")
        last = r["last_order"] or "hech qachon"
        if r["last_order"]:
            days_ago = (date.today() - date.fromisoformat(r["last_order"])).days
            last = f"{r['last_order']} ({days_ago} kun oldin)"
        lines.append(f"  • {r['shop']} — oxirgi buyurtma: {last}")
        count += 1
    lines.insert(1, f"Jami: {count} ta do'kon\n")
    return "\n".join(lines)


# ------------------------------------------------------------------
# Kunlik digest (20:00 da avtomatik yuboriladi)
# ------------------------------------------------------------------

def daily_digest() -> str:
    from config import DEBT_ALERT_THRESHOLD, SALES_DROP_ALERT_PERCENT
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    month_from = f"{date.today().year:04d}-{date.today().month:02d}-01"

    with get_conn() as conn:
        # Bugungi savdo
        row = conn.execute("""
            SELECT SUM(total_after_discount) AS total FROM orders
            WHERE date=? AND status IN (1,2,3)
        """, (today,)).fetchone()
        today_sales = float(row["total"] or 0) if row else 0.0

        # Kechagi savdo
        row2 = conn.execute("""
            SELECT SUM(total_after_discount) AS total FROM orders
            WHERE date=? AND status IN (1,2,3)
        """, (yesterday,)).fetchone()
        yesterday_sales = float(row2["total"] or 0) if row2 else 0.0

        # Bugungi vizitlar
        vis_row = conn.execute("""
            SELECT COUNT(*) AS cnt FROM visits WHERE date=? AND visited=1
        """, (today,)).fetchone()
        today_visits = vis_row["cnt"] if vis_row else 0

        # 0 vizit qilgan agentlar
        all_agents = conn.execute("SELECT sd_id, name FROM agents WHERE active='Y'").fetchall()
        visited_agents = conn.execute("""
            SELECT DISTINCT agent_sd_id FROM visits WHERE date=? AND visited=1
        """, (today,)).fetchall()
        visited_ids = {r["agent_sd_id"] for r in visited_agents}
        zero_visit_agents = [a["name"] for a in all_agents if a["sd_id"] not in visited_ids]

        # Oy savdosi
        month_row = conn.execute("""
            SELECT SUM(total_after_discount) AS total FROM orders
            WHERE date >= ? AND date <= ? AND status IN (1,2,3)
        """, (month_from, today)).fetchone()
        month_sales = float(month_row["total"] or 0) if month_row else 0.0

        # Qarzi yuqori agentlar
        debt_agents = []
        if DEBT_ALERT_THRESHOLD > 0:
            debt_rows = conn.execute("""
                SELECT a.name AS agent, SUM(ABS(b.balance)) AS debt
                FROM balances b
                JOIN clients c ON c.sd_id = b.client_sd_id
                LEFT JOIN agents a ON a.sd_id = c.primary_agent_sd_id
                WHERE b.balance < 0
                GROUP BY c.primary_agent_sd_id
                HAVING debt > ?
                ORDER BY debt DESC
            """, (DEBT_ALERT_THRESHOLD,)).fetchall()
            debt_agents = [(r["agent"] or "Noma'lum", r["debt"]) for r in debt_rows]

        # Yangi o'lik do'konlar (bugun o'lik, kecha emas — soddalashtirilgan: oxirgi 14 kun)
        from config import DEAD_OUTLET_DAYS, DEAD_OUTLET_LOOKBACK_DAYS
        dead_from_dt = (date.today() - timedelta(days=DEAD_OUTLET_DAYS)).isoformat()
        lookback_from_dt = (date.today() - timedelta(days=DEAD_OUTLET_LOOKBACK_DAYS)).isoformat()
        active_set = conn.execute("""
            SELECT DISTINCT client_sd_id FROM orders WHERE date >= ? AND status IN (1,2,3)
        """, (lookback_from_dt,)).fetchall()
        recent_set = conn.execute("""
            SELECT DISTINCT client_sd_id FROM orders WHERE date >= ? AND status IN (1,2,3)
        """, (dead_from_dt,)).fetchall()
        dead_count = len(set(r["client_sd_id"] for r in active_set) -
                         set(r["client_sd_id"] for r in recent_set))

    # Matn yig'ish
    lines = [f"🔔 <b>KUNLIK XULOSA — {today}</b>\n"]

    # Savdo
    if yesterday_sales > 0:
        diff_pct = (today_sales - yesterday_sales) / yesterday_sales * 100
        arrow = "↑" if diff_pct >= 0 else "↓"
        diff_str = f"kecha: {_fmt(yesterday_sales)} → {diff_pct:+.0f}% {arrow}"
    else:
        diff_str = "kecha ma'lumot yo'q"
    lines.append(f"💰 Bugungi savdo: {_fmt(today_sales)}\n   ({diff_str})")

    # Savdo tushish ogohlantirishи
    if yesterday_sales > 0 and today_sales < yesterday_sales:
        drop_pct = (yesterday_sales - today_sales) / yesterday_sales * 100
        if drop_pct >= SALES_DROP_ALERT_PERCENT:
            lines.append(f"📉 <b>Diqqat: savdo {drop_pct:.0f}% tushdi!</b>")

    lines.append(f"🚶 Vizitlar: {today_visits} ta")

    if zero_visit_agents:
        lines.append("⚠️ Bugun 0 vizit: " + ", ".join(zero_visit_agents))

    if debt_agents:
        debt_list = ", ".join(f"{name} ({_fmt(d)})" for name, d in debt_agents)
        lines.append(f"💳 Qarzi yuqori: {debt_list}")

    lines.append(f"💀 O'lik do'konlar: {dead_count} ta")
    lines.append(f"\n📊 Bu oy: {_fmt(month_sales)}")

    return "\n".join(lines)
