"""
reports.py — Bazadan ma'lumot o'qib, tayyor matn hisobotlar qaytaradi.
Bot (bot.py) shu funksiyalarni chaqiradi.
"""

from datetime import date, timedelta

from db import get_conn


def _fmt(amount: float) -> str:
    """Sonni o'qish uchun: 12345678 → '12 345 678 so'm'."""
    try:
        return f"{int(round(amount)):,}".replace(",", " ") + " so'm"
    except (ValueError, TypeError):
        return "0 so'm"


def _num(amount: float) -> str:
    """Faqat son, so'msiz."""
    try:
        return f"{int(round(amount)):,}".replace(",", " ")
    except (ValueError, TypeError):
        return "0"


MIN_DEBT = 50_000  # Eng kam qarz summasi (so'mda)

SEP = "━━━━━━━━━━━━━━━━━━━━━━━━━━"


def _header(emoji: str, title: str, subtitle: str = "") -> str:
    parts = [SEP, f"{emoji} <b>{title}</b>"]
    if subtitle:
        parts.append(f"📅 <i>{subtitle}</i>")
    parts.append(SEP)
    return "\n".join(parts)


def _rank(i: int) -> str:
    """1 → 🥇, 2 → 🥈, 3 → 🥉, qolgan → '04.'"""
    if i == 1:
        return "🥇"
    if i == 2:
        return "🥈"
    if i == 3:
        return "🥉"
    return f"<code>{i:2d}.</code>"


def _footer(label: str, value: str) -> str:
    return f"{SEP}\n💎 <b>{label}:</b> <b>{value}</b>\n{SEP}"


# ------------------------------------------------------------------
# Kunlik savdo
# ------------------------------------------------------------------

def daily_sales_report(date_from: str, date_to: str = None) -> str:
    """Savdo hisoboti. date_to bo'lmasa — bitta kun."""
    if date_to is None:
        date_to = date_from
    is_single = (date_from == date_to)
    title = "KUNLIK SAVDO" if is_single else "SAVDO (DAVR)"
    subtitle = date_from if is_single else f"{date_from} — {date_to}"

    with get_conn() as conn:
        rows = conn.execute("""
            SELECT a.name AS agent, SUM(o.total_after_discount) AS total,
                   COUNT(DISTINCT o.client_sd_id) AS akb
            FROM orders o
            LEFT JOIN agents a ON a.sd_id = o.agent_sd_id
            WHERE o.date >= ? AND o.date <= ? AND o.status IN (1, 2, 3)
            GROUP BY o.agent_sd_id
            ORDER BY total DESC
        """, (date_from, date_to)).fetchall()

        total_akb_row = conn.execute("""
            SELECT COUNT(DISTINCT client_sd_id) AS cnt FROM orders
            WHERE date >= ? AND date <= ? AND status IN (1,2,3)
        """, (date_from, date_to)).fetchone()
    total_akb = total_akb_row["cnt"] if total_akb_row else 0

    if not rows:
        return _header("💰", title, subtitle) + "\n\n<i>Bu davrda savdo yo'q yoki ma'lumot hali yuklanmagan.</i>"

    lines = [_header("💰", title, subtitle), ""]
    total = 0.0
    for i, r in enumerate(rows, 1):
        agent = r["agent"] or "Noma'lum"
        lines.append(f"{_rank(i)} {agent}")
        lines.append(f"     💵 <b>{_fmt(r['total'])}</b>  ·  🛒 {r['akb']} ta")
        total += r["total"] or 0
    lines.append("")
    lines.append(_footer("JAMI", f"{_fmt(total)}  ·  🛒 AKB: {total_akb}"))
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
    subtitle = f"{month_names[month]} {year}"

    with get_conn() as conn:
        rows = conn.execute("""
            SELECT
                a.name AS agent,
                SUM(o.total_after_discount) AS total,
                COUNT(DISTINCT o.client_sd_id) AS akb
            FROM orders o
            LEFT JOIN agents a ON a.sd_id = o.agent_sd_id
            WHERE o.date >= ? AND o.date < ? AND o.status IN (1, 2, 3)
            GROUP BY o.agent_sd_id
            ORDER BY total DESC
        """, (date_from, date_to)).fetchall()

        total_akb_row = conn.execute("""
            SELECT COUNT(DISTINCT client_sd_id) AS cnt FROM orders
            WHERE date >= ? AND date < ? AND status IN (1,2,3)
        """, (date_from, date_to)).fetchone()
    total_akb = total_akb_row["cnt"] if total_akb_row else 0

    if not rows:
        return _header("📈", "OYLIK SAVDO", subtitle) + "\n\n<i>Bu oyda ma'lumot yo'q.</i>"

    lines = [_header("📈", "OYLIK SAVDO", subtitle), ""]
    grand_total = 0.0
    for i, r in enumerate(rows, 1):
        agent = r["agent"] or "Noma'lum"
        lines.append(f"{_rank(i)} {agent}")
        lines.append(f"     💵 <b>{_fmt(r['total'])}</b>  ·  🛒 AKB: {r['akb']}")
        grand_total += r["total"] or 0
    lines.append("")
    lines.append(_footer("JAMI", f"{_fmt(grand_total)}  ·  🛒 AKB: {total_akb}"))
    return "\n".join(lines)


# ------------------------------------------------------------------
# Agentlar qarzi (umumiy ro'yxat)
# ------------------------------------------------------------------

def agents_debt_report() -> str:
    """Agentlar qarzi — har bir agentning JAMI qarzi (hamma do'konlar)."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT
                a.name AS agent,
                SUM(ABS(b.balance)) AS debt,
                COUNT(*) AS shops
            FROM balances b
            JOIN clients c ON c.sd_id = b.client_sd_id
            LEFT JOIN agents a ON a.sd_id = c.primary_agent_sd_id
            WHERE b.balance < 0
            GROUP BY c.primary_agent_sd_id
            ORDER BY debt DESC
        """).fetchall()

    if not rows:
        return _header("🏪", "AGENTLAR QARZI") + "\n\n<i>Qarzdor agent yo'q.</i>"

    lines = [_header("🏪", "AGENTLAR QARZI"), ""]
    total = 0.0
    for i, r in enumerate(rows, 1):
        agent = r["agent"] or "Agentsiz"
        lines.append(f"{_rank(i)} {agent}")
        lines.append(f"     💸 <b>{_fmt(r['debt'])}</b>  ·  🏪 {r['shops']} ta do'kon")
        total += r["debt"] or 0
    lines.append("")
    lines.append(_footer("JAMI QARZ", _fmt(total)))
    return "\n".join(lines)


# ------------------------------------------------------------------
# Bitta agent qarzdor do'konlari
# ------------------------------------------------------------------

def agent_debt_detail(agent_sd_id: str) -> str:
    """Bitta agent qarzdor do'konlari (eng kami MIN_DEBT)."""
    with get_conn() as conn:
        agent_row = conn.execute("SELECT name FROM agents WHERE sd_id=?", (agent_sd_id,)).fetchone()
        agent_name = agent_row["name"] if agent_row else "Noma'lum agent"

        rows = conn.execute("""
            SELECT b.client_name AS shop, ABS(b.balance) AS debt
            FROM balances b
            JOIN clients c ON c.sd_id = b.client_sd_id
            WHERE c.primary_agent_sd_id = ? AND b.balance <= ?
            ORDER BY debt DESC
        """, (agent_sd_id, -MIN_DEBT)).fetchall()

    if not rows:
        return _header("👤", agent_name, "qarzdorlar") + f"\n\n<i>Qarzdor do'kon yo'q (eng kami {_fmt(MIN_DEBT)}).</i>"

    total = sum(r["debt"] or 0 for r in rows)
    lines = [
        _header("👤", agent_name, f"qarzdorlar · eng kami {_fmt(MIN_DEBT)}"),
        "",
    ]
    for i, r in enumerate(rows, 1):
        lines.append(f"{_rank(i)} {r['shop']}")
        lines.append(f"     💸 <b>{_fmt(r['debt'])}</b>")
    lines.append("")
    lines.append(_footer("JAMI", f"{_fmt(total)}  ·  🏪 {len(rows)} ta do'kon"))
    return "\n".join(lines)


# ------------------------------------------------------------------
# Vizitlar
# ------------------------------------------------------------------

def visits_report(date_from: str, date_to: str = None) -> str:
    """Vizit hisoboti. date_to bo'lmasa, faqat date_from kuni uchun."""
    if date_to is None:
        date_to = date_from
    subtitle = date_from if date_from == date_to else f"{date_from} — {date_to}"

    with get_conn() as conn:
        rows = conn.execute("""
            SELECT agent_name, COUNT(*) AS cnt
            FROM visits
            WHERE date >= ? AND date <= ? AND visited = 1
            GROUP BY agent_sd_id
            ORDER BY cnt DESC
        """, (date_from, date_to)).fetchall()
        all_agents = conn.execute("SELECT name FROM agents WHERE active='Y'").fetchall()

    if not rows:
        return _header("🚶", "VIZITLAR", subtitle) + "\n\n<i>Bu davrda vizit ma'lumoti yo'q.</i>"

    visited_names = {r["agent_name"] for r in rows}
    lines = [_header("🚶", "VIZITLAR", subtitle), ""]
    total = 0
    for i, r in enumerate(rows, 1):
        lines.append(f"{_rank(i)} {r['agent_name']}")
        lines.append(f"     👣 <b>{r['cnt']}</b> ta tashrif")
        total += r["cnt"]
    lines.append("")
    lines.append(_footer("JAMI", f"{total} ta tashrif"))

    # 0 vizit faqat bitta kun bo'lsa ma'noli (oylik uchun emas)
    if date_from == date_to:
        zero_visit = [a["name"] for a in all_agents if a["name"] not in visited_names]
        if zero_visit:
            lines.append(f"\n⚠️ <b>{date_from} kuni 0 vizit:</b>\n" + "\n".join(f"   • {n}" for n in zero_visit))

    return "\n".join(lines)


# ------------------------------------------------------------------
# TOP tovarlar
# ------------------------------------------------------------------

def top_products_report(date_from: str, date_to: str, top_n: int = 20) -> str:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT oi.product_name AS name,
                   SUM(oi.summa) AS total,
                   SUM(oi.quantity) AS qty
            FROM order_items oi
            JOIN orders o ON o.sd_id = oi.order_sd_id
            WHERE o.date >= ? AND o.date <= ? AND o.status IN (1,2,3)
            GROUP BY oi.product_sd_id
            ORDER BY total DESC
            LIMIT ?
        """, (date_from, date_to, top_n)).fetchall()

    subtitle = f"{date_from} — {date_to}" if date_from != date_to else date_from
    if not rows:
        return _header("🏆", f"TOP {top_n} TOVAR", subtitle) + "\n\n<i>Ma'lumot yo'q.</i>"

    lines = [_header("🏆", f"TOP {top_n} TOVAR", subtitle), ""]
    grand_total = 0.0
    for i, r in enumerate(rows, 1):
        lines.append(f"{_rank(i)} {r['name']}")
        lines.append(f"     💵 <b>{_fmt(r['total'])}</b>  ·  📦 {_num(r['qty'])} dona")
        grand_total += r["total"] or 0
    lines.append("")
    lines.append(_footer("JAMI", _fmt(grand_total)))
    return "\n".join(lines)


# ------------------------------------------------------------------
# Sklad ostatka
# ------------------------------------------------------------------

STOCK_AVG_DAYS = 30  # o'rtacha kunlik sotuv hisoblanadigan davr


def _stock_color(days: float) -> str:
    """Necha kunlik qoldiq → rang belgi."""
    if days < 2:
        return "🔴"
    if days <= 5:
        return "🟡"
    return "🟢"


def _days_str(days: float) -> str:
    if days >= 999:
        return "∞"
    if days >= 100:
        return "100+"
    if days < 1:
        return "0"
    return f"{int(round(days))}"


def _color_order(days: float) -> int:
    """🔴 → 0, 🟡 → 1, 🟢 → 2 (sortlash uchun)"""
    if days < 2:
        return 0
    if days <= 5:
        return 1
    return 2


def stock_report() -> list[str]:
    """
    Kategoriya bo'yicha sklad ostatka.
    Ichida: 🔴 → 🟡 → 🟢 (kritik birinchi).
    Bir xil rangli mahsulotlar alifbo tartibida.
    """
    with get_conn() as conn:
        rows = conn.execute(f"""
            SELECT
                s.product_sd_id,
                MAX(s.product_name) AS name,
                SUM(s.quantity) AS stock,
                MAX(s.updated_at) AS upd,
                COALESCE(cat.name, 'Kategoriyasiz') AS cat_name,
                COALESCE((
                    SELECT SUM(oi.quantity)
                    FROM order_items oi
                    JOIN orders o ON o.sd_id = oi.order_sd_id
                    WHERE oi.product_sd_id = s.product_sd_id
                      AND o.status IN (1, 2, 3)
                      AND o.date >= date('now', '-{STOCK_AVG_DAYS} days')
                ), 0) AS sold
            FROM stock s
            LEFT JOIN products p ON p.sd_id = s.product_sd_id
            LEFT JOIN categories cat ON cat.sd_id = p.category
            WHERE s.quantity > 0
            GROUP BY s.product_sd_id
        """).fetchall()

    if not rows:
        return ["📦 <b>SKLAD OSTATKA</b>\n\n<i>Ma'lumot yo'q.</i>"]

    # Mahsulotlarni kategoriya bo'yicha guruhlash
    by_cat: dict[str, list] = {}
    for r in rows:
        stock = float(r["stock"] or 0)
        sold = float(r["sold"] or 0)
        avg_daily = sold / STOCK_AVG_DAYS if sold > 0 else 0
        days = stock / avg_daily if avg_daily > 0 else 9999
        item = {"name": r["name"], "stock": stock, "days": days}
        by_cat.setdefault(r["cat_name"], []).append(item)

    # Har kategoriya ichida: rang (kritik birinchi) → nom alifbo
    for cat in by_cat.values():
        cat.sort(key=lambda x: (_color_order(x["days"]), x["name"].lower()))

    # Kategoriyalarni eng kritik mahsulotning kunligi bo'yicha
    cat_sorted = sorted(by_cat.items(), key=lambda kv: min(it["days"] for it in kv[1]))

    last_updated = rows[0]["upd"] if rows else ""

    def _make_header(part: str = "") -> str:
        title = "📦 <b>SKLAD OSTATKA</b>"
        if part:
            title += f" <i>({part})</i>"
        return f"<i>yangilangan: {last_updated[:19]}</i>\n{title}\n"

    messages = []
    current = _make_header()
    for cat_name, items in cat_sorted:
        cat_header = f"\n\n📁 <b>{cat_name}</b>"
        # Agar yangi kategoriya joylashishi mumkin bo'lmasa — yangi xabar
        if len(current) + len(cat_header) > 3800:
            messages.append(current)
            part_n = len(messages) + 1
            current = _make_header(f"{part_n}-qism")
            cat_header = f"\n📁 <b>{cat_name}</b>"
        current += cat_header
        for it in items:
            color = _stock_color(it["days"])
            days_text = _days_str(it["days"])
            line = f"\n{color} {it['name']} — <b>{_num(it['stock'])}</b> blok / <b>{days_text}</b> kunlik"
            if len(current) + len(line) > 3800:
                messages.append(current)
                part_n = len(messages) + 1
                current = _make_header(f"{part_n}-qism") + f"\n📁 <b>{cat_name}</b> <i>(davomi)</i>" + line
            else:
                current += line
    if current:
        messages.append(current)
    return messages


# ------------------------------------------------------------------
# O'lik do'konlar
# ------------------------------------------------------------------

def dead_outlets_report(dead_days: int = 14, lookback_days: int = 90) -> str:
    """Agent bo'yicha o'lik do'konlar SONI ko'rsatiladi (uzun ro'yxat o'rniga)."""
    lookback_from = (date.today() - timedelta(days=lookback_days)).isoformat()
    dead_from = (date.today() - timedelta(days=dead_days)).isoformat()

    with get_conn() as conn:
        active = conn.execute("""
            SELECT DISTINCT client_sd_id FROM orders
            WHERE date >= ? AND status IN (1,2,3)
        """, (lookback_from,)).fetchall()
        active_ids = {r["client_sd_id"] for r in active}

        recent = conn.execute("""
            SELECT DISTINCT client_sd_id FROM orders
            WHERE date >= ? AND status IN (1,2,3)
        """, (dead_from,)).fetchall()
        recent_ids = {r["client_sd_id"] for r in recent}

        dead_ids = active_ids - recent_ids
        if not dead_ids:
            return f"💀 <b>O'lik do'konlar yo'q</b> (chegara: {dead_days} kun)"

        placeholders = ",".join("?" * len(dead_ids))
        rows = conn.execute(f"""
            SELECT
                COALESCE(a.name, 'Agentsiz') AS agent,
                c.primary_agent_sd_id,
                COUNT(*) AS cnt
            FROM clients c
            LEFT JOIN agents a ON a.sd_id = c.primary_agent_sd_id
            WHERE c.sd_id IN ({placeholders})
            GROUP BY c.primary_agent_sd_id
            ORDER BY cnt DESC
        """, list(dead_ids)).fetchall()

    lines = [
        _header("💀", "O'LIK DO'KONLAR", f"oxirgi {dead_days} kunda buyurtma yo'q"),
        "",
        f"<b>Jami:</b> <code>{len(dead_ids)}</code> ta do'kon\n",
    ]
    for i, r in enumerate(rows, 1):
        lines.append(f"{_rank(i)} {r['agent']}")
        lines.append(f"     💀 <b>{r['cnt']}</b> ta do'kon")
    lines.append("")
    lines.append("<i>👆 Bitta agentning do'konlarini ko'rish uchun pastdagi tugmalardan birini bosing.</i>")
    return "\n".join(lines)


def dead_outlets_by_agent(agent_sd_id: str, dead_days: int = 14, lookback_days: int = 90, limit: int = 50) -> str:
    """Bitta agentning o'lik do'konlari ro'yxati."""
    lookback_from = (date.today() - timedelta(days=lookback_days)).isoformat()
    dead_from = (date.today() - timedelta(days=dead_days)).isoformat()

    with get_conn() as conn:
        agent_row = conn.execute("SELECT name FROM agents WHERE sd_id=?", (agent_sd_id,)).fetchone()
        agent_name = agent_row["name"] if agent_row else "Noma'lum"

        rows = conn.execute("""
            SELECT c.name AS shop, MAX(o.date) AS last_order
            FROM clients c
            LEFT JOIN orders o ON o.client_sd_id = c.sd_id AND o.status IN (1,2,3)
            WHERE c.primary_agent_sd_id = ?
            GROUP BY c.sd_id
            HAVING MAX(o.date) IS NOT NULL
               AND MAX(o.date) >= ?
               AND MAX(o.date) < ?
            ORDER BY last_order ASC
            LIMIT ?
        """, (agent_sd_id, lookback_from, dead_from, limit + 1)).fetchall()

    if not rows:
        return f"💀 <b>{agent_name}</b> — o'lik do'kon yo'q."

    truncated = len(rows) > limit
    rows = rows[:limit]
    lines = [_header("💀", agent_name, "o'lik do'konlar"), ""]
    for i, r in enumerate(rows, 1):
        days_ago = (date.today() - date.fromisoformat(r["last_order"])).days
        lines.append(f"{_rank(i)} {r['shop']}")
        lines.append(f"     📅 {r['last_order']}  ·  ⏱ <b>{days_ago}</b> kun")
    if truncated:
        lines.append(f"\n<i>...va yana ko'p. Faqat birinchi {limit} ko'rsatildi.</i>")
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
    lines = [_header("🔔", "KUNLIK XULOSA", today), ""]

    # Savdo
    lines.append(f"💰 <b>Bugungi savdo</b>")
    lines.append(f"     💵 <b>{_fmt(today_sales)}</b>")
    if yesterday_sales > 0:
        diff_pct = (today_sales - yesterday_sales) / yesterday_sales * 100
        arrow = "📈" if diff_pct >= 0 else "📉"
        lines.append(f"     {arrow} kecha: {_fmt(yesterday_sales)} ({diff_pct:+.0f}%)")
        # Tushish ogohlantirish
        if today_sales < yesterday_sales:
            drop_pct = (yesterday_sales - today_sales) / yesterday_sales * 100
            if drop_pct >= SALES_DROP_ALERT_PERCENT:
                lines.append(f"     ⚠️ <b>Savdo {drop_pct:.0f}% tushdi!</b>")

    lines.append("")
    lines.append(f"🚶 <b>Vizitlar:</b> <code>{today_visits}</code> ta")
    if zero_visit_agents:
        lines.append(f"     ⚠️ 0 vizit: {', '.join(zero_visit_agents)}")

    if debt_agents:
        lines.append("")
        lines.append(f"💳 <b>Qarzi yuqori agentlar:</b>")
        for name, d in debt_agents:
            lines.append(f"     • {name} — <b>{_fmt(d)}</b>")

    lines.append("")
    lines.append(f"💀 <b>O'lik do'konlar:</b> <code>{dead_count}</code> ta")
    lines.append("")
    lines.append(_footer("BU OY", _fmt(month_sales)))

    return "\n".join(lines)
