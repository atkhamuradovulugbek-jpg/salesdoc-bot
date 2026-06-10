"""
sync.py — Sales Doctor'dan ma'lumot tortib SQLite bazaga yozadi.
Optimallashtirilgan: parallel HTTP + bulk DB inserts.
"""

import asyncio
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from config import DEAD_OUTLET_LOOKBACK_DAYS, TIMEZONE
from db import get_conn, log_sync
from salesdoc_api import get_api

logger = logging.getLogger(__name__)

TZ = ZoneInfo(TIMEZONE)


def _now_str() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def _safe_str(v) -> str:
    if v is None:
        return ""
    return str(v)


def _safe_id(v) -> str:
    return _safe_str(v).strip()


def _nested_id(parent, key: str = "SD_id") -> str:
    if not isinstance(parent, dict):
        return ""
    return _safe_id(parent.get(key))


def _normalize_date(value, fallback: str) -> str:
    if not value:
        return fallback
    s = str(value).strip()
    if not s or s.startswith("0000") or s.startswith("1970"):
        return fallback
    return s[:10]


def _to_int(v, default: int = 0) -> int:
    try:
        return int(v) if v is not None else default
    except (ValueError, TypeError):
        return default


def _to_float(v, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (ValueError, TypeError):
        return default


async def run_sync(sync_type: str = "scheduled", progress_cb=None) -> str:
    """
    Sales Doctor → SQLite. Bulk insert. Ixtiyoriy progress callback.
    """
    api = get_api()
    now = _now_str()
    today = date.today().isoformat()
    lookback_from = (date.today() - timedelta(days=DEAD_OUTLET_LOOKBACK_DAYS)).isoformat()

    async def progress(text: str):
        if progress_cb:
            try:
                await progress_cb(text)
            except Exception:
                pass

    try:
        await progress("📡 Sales Doctor ga ulanyapmiz...")
        await api.login()

        visits_from = today  # Faqat bugungi (oldin ishlagan tezkor versiya)

        await progress("👥 Agentlar tortilmoqda...")
        agents = await api.get_agents();      logger.info("✓ agents: %d", len(agents))

        await progress(f"📁 Kategoriyalar tortilmoqda...\n<i>(agentlar: {len(agents)})</i>")
        categories = await api.get_categories(); logger.info("✓ categories: %d", len(categories))

        await progress(f"📦 Mahsulotlar tortilmoqda...\n<i>(kategoriyalar: {len(categories)})</i>")
        products = await api.get_products();  logger.info("✓ products: %d", len(products))

        await progress(f"💳 Qarz/balanslar tortilmoqda...\n<i>(mahsulotlar: {len(products)})</i>")
        balances = await api.get_balance();   logger.info("✓ balances: %d", len(balances))

        await progress(f"🏭 Ombor qoldiqlari tortilmoqda...\n<i>(balanslar: {len(balances)})</i>")
        warehouses = await api.get_stock();   logger.info("✓ warehouses: %d", len(warehouses))

        await progress(f"🚶 Bugungi vizitlar tortilmoqda...")
        visits = await api.get_visits(visits_from, today); logger.info("✓ visits: %d", len(visits))

        await progress(f"🏪 Mijozlar tortilmoqda... <i>(ko'p ma'lumot)</i>")
        clients = await api.get_clients();    logger.info("✓ clients: %d", len(clients))

        await progress(f"💰 Buyurtmalar tortilmoqda...\n<i>(mijozlar: {len(clients)}, eng katta qism)</i>")
        orders = await api.get_orders(lookback_from, today); logger.info("✓ orders: %d", len(orders))

        await progress(f"💾 Bazaga yozilmoqda...\n<i>(buyurtmalar: {len(orders)})</i>")

        logger.info(
            "Tortildi: agents=%d, products=%d, clients=%d, orders=%d, "
            "balances=%d, warehouses=%d, visits=%d",
            len(agents), len(products), len(clients), len(orders),
            len(balances), len(warehouses), len(visits),
        )

        # ============================================================
        # Ma'lumotlarni tayyorlash (Python ichida)
        # ============================================================

        # Agents
        agent_rows = []
        for a in agents:
            sd_id = _safe_id(a.get("SD_id"))
            if not sd_id:
                continue
            agent_rows.append((
                sd_id,
                _safe_str(a.get("code_1C")),
                _safe_str(a.get("name")) or "(nomsiz agent)",
                _safe_str(a.get("active")) or "Y",
                now,
            ))

        # Categories
        category_rows = []
        for c in categories:
            sd_id = _safe_id(c.get("SD_id"))
            if not sd_id:
                continue
            category_rows.append((
                sd_id,
                _safe_str(c.get("name")) or "(nomsiz)",
                _safe_str(c.get("active")) or "Y",
                now,
            ))

        # Products
        product_rows = []
        for p in products:
            sd_id = _safe_id(p.get("SD_id"))
            if not sd_id:
                continue
            product_rows.append((
                sd_id,
                _safe_str(p.get("code_1C")),
                _safe_str(p.get("name")) or "(nomsiz mahsulot)",
                _nested_id(p.get("category")),
                now,
            ))

        # Clients
        client_rows = []
        for c in clients:
            sd_id = _safe_id(c.get("SD_id"))
            if not sd_id:
                continue
            agents_list = c.get("agents") or []
            primary = ""
            if agents_list and isinstance(agents_list[0], dict):
                primary = _safe_id(agents_list[0].get("id"))
            client_rows.append((
                sd_id,
                _safe_str(c.get("code_1C")),
                _safe_str(c.get("name")) or "(nomsiz mijoz)",
                primary or None,
                _nested_id(c.get("city")),
                now,
            ))

        # Orders + order_items
        order_rows = []
        item_rows = []
        order_sd_ids = []
        skipped_no_date = 0
        for o in orders:
            sd_id = _safe_id(o.get("SD_id"))
            if not sd_id:
                continue
            order_date = _normalize_date(o.get("dateCreate"), "")
            if not order_date:
                order_date = _normalize_date(o.get("orderCreated"), "")
            if not order_date:
                order_date = _normalize_date(o.get("dateDocument"), today)
            if not order_date:
                skipped_no_date += 1
                continue
            order_rows.append((
                sd_id, order_date, _to_int(o.get("status")),
                _nested_id(o.get("agent")), _nested_id(o.get("client")),
                _to_float(o.get("totalSummaAfterDiscount")),
            ))
            order_sd_ids.append(sd_id)
            for item in (o.get("orderProducts") or []):
                if not isinstance(item, dict):
                    continue
                prod = item.get("product") or {}
                item_rows.append((
                    sd_id,
                    _nested_id(prod),
                    _safe_str(prod.get("name")) if isinstance(prod, dict) else "",
                    _to_float(item.get("quantity")),
                    _to_float(item.get("summa")),
                ))

        # Balances
        balance_rows = []
        for b in balances:
            sd_id = _safe_id(b.get("SD_id"))
            if not sd_id:
                continue
            balance_rows.append((
                sd_id, _safe_str(b.get("name")) or "(nomsiz)",
                _to_float(b.get("balance")), now,
            ))

        # Stock (faqat faol omborlar va faol mahsulotlar)
        active_whs = [wh for wh in warehouses if _safe_str(wh.get("active")) == "Y"]
        stock_rows = []
        for wh in active_whs:
            wh_name = _safe_str(wh.get("name")) or "Ombor"
            for prod in (wh.get("products") or []):
                if not isinstance(prod, dict):
                    continue
                prod_id = _safe_id(prod.get("SD_id"))
                if not prod_id:
                    continue
                if _safe_str(prod.get("active")) != "Y":
                    continue
                stock_rows.append((
                    prod_id,
                    _safe_str(prod.get("name")) or "(nomsiz)",
                    wh_name,
                    _to_float(prod.get("quantity")),
                    now,
                ))

        # Visits
        visit_rows = []
        for v in visits:
            visit_date = _normalize_date(v.get("date"), today)
            agent_id = _safe_id(v.get("agent_id"))
            client_id = _safe_id(v.get("client_id"))
            if not agent_id or not client_id:
                continue
            visit_rows.append((
                visit_date, agent_id, _safe_str(v.get("agent_name")),
                client_id, _safe_str(v.get("client_name")),
                _to_int(v.get("planned")), _to_int(v.get("visited")),
                _to_int(v.get("has_order")), _to_float(v.get("order_summa")),
            ))

        # ============================================================
        # Bulk INSERT — bittagina tranzaksiya
        # ============================================================
        logger.info("Bazaga yozish: agents=%d, products=%d, clients=%d, "
                    "orders=%d (items=%d), balances=%d, stock=%d, visits=%d",
                    len(agent_rows), len(product_rows), len(client_rows),
                    len(order_rows), len(item_rows), len(balance_rows),
                    len(stock_rows), len(visit_rows))

        with get_conn() as conn:
            conn.executemany("""
                INSERT INTO agents (sd_id, code_1c, name, active, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(sd_id) DO UPDATE SET
                    code_1c=excluded.code_1c, name=excluded.name,
                    active=excluded.active, updated_at=excluded.updated_at
            """, agent_rows)

            conn.executemany("""
                INSERT INTO categories (sd_id, name, active, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(sd_id) DO UPDATE SET
                    name=excluded.name, active=excluded.active,
                    updated_at=excluded.updated_at
            """, category_rows)

            conn.executemany("""
                INSERT INTO products (sd_id, code_1c, name, category, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(sd_id) DO UPDATE SET
                    code_1c=excluded.code_1c, name=excluded.name,
                    category=excluded.category, updated_at=excluded.updated_at
            """, product_rows)

            conn.executemany("""
                INSERT INTO clients (sd_id, code_1c, name, primary_agent_sd_id, territory, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(sd_id) DO UPDATE SET
                    code_1c=excluded.code_1c, name=excluded.name,
                    primary_agent_sd_id=excluded.primary_agent_sd_id,
                    territory=excluded.territory, updated_at=excluded.updated_at
            """, client_rows)

            conn.executemany("""
                INSERT INTO orders (sd_id, date, status, agent_sd_id, client_sd_id, total_after_discount)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(sd_id) DO UPDATE SET
                    date=excluded.date, status=excluded.status,
                    agent_sd_id=excluded.agent_sd_id, client_sd_id=excluded.client_sd_id,
                    total_after_discount=excluded.total_after_discount
            """, order_rows)

            # Order items — eski yozuvlarni o'chirib, yangini yozish
            if order_sd_ids:
                # Bulk DELETE (chunkable)
                CHUNK = 500
                for i in range(0, len(order_sd_ids), CHUNK):
                    chunk = order_sd_ids[i:i + CHUNK]
                    placeholders = ",".join("?" * len(chunk))
                    conn.execute(
                        f"DELETE FROM order_items WHERE order_sd_id IN ({placeholders})",
                        chunk,
                    )
                conn.executemany("""
                    INSERT INTO order_items (order_sd_id, product_sd_id, product_name, quantity, summa)
                    VALUES (?, ?, ?, ?, ?)
                """, item_rows)

            conn.executemany("""
                INSERT INTO balances (client_sd_id, client_name, balance, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(client_sd_id) DO UPDATE SET
                    client_name=excluded.client_name, balance=excluded.balance,
                    updated_at=excluded.updated_at
            """, balance_rows)

            # Stock — to'liq yangilash
            conn.execute("DELETE FROM stock")
            conn.executemany("""
                INSERT INTO stock (product_sd_id, product_name, warehouse, quantity, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(product_sd_id, warehouse) DO UPDATE SET
                    product_name=excluded.product_name, quantity=excluded.quantity,
                    updated_at=excluded.updated_at
            """, stock_rows)

            conn.executemany("""
                INSERT INTO visits (date, agent_sd_id, agent_name, client_sd_id, client_name,
                                    planned, visited, has_order, order_summa)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date, agent_sd_id, client_sd_id) DO UPDATE SET
                    agent_name=excluded.agent_name, client_name=excluded.client_name,
                    planned=excluded.planned, visited=excluded.visited,
                    has_order=excluded.has_order, order_summa=excluded.order_summa
            """, visit_rows)

            conn.execute(
                "INSERT INTO sync_log (run_at, type, status, note) VALUES (?, ?, ?, ?)",
                (now, sync_type, "ok", f"orders={len(order_rows)} (skipped={skipped_no_date})"),
            )

        logger.info("✅ Sinxronizatsiya muvaffaqiyatli tugadi.")
        return "ok"

    except Exception as exc:
        logger.exception("Sinxronizatsiya xatosi")
        try:
            with get_conn() as conn:
                conn.execute(
                    "INSERT INTO sync_log (run_at, type, status, note) VALUES (?, ?, ?, ?)",
                    (now, sync_type, "error", str(exc)[:500]),
                )
        except Exception:
            pass
        return f"{type(exc).__name__}: {exc}"
