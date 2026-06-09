"""
sync.py — Sales Doctor'dan ma'lumot tortib SQLite bazaga yozadi.
Scheduler va "Hozir yangilash" tugmasi shu faylni ishlatadi.
"""

import logging
from datetime import date, timedelta, timezone
from zoneinfo import ZoneInfo

from config import DEAD_OUTLET_LOOKBACK_DAYS, TIMEZONE
from db import (
    get_conn, log_sync,
    upsert_agent, upsert_balance, upsert_client,
    upsert_order, replace_order_items, upsert_product,
    upsert_stock, upsert_visit,
)
from salesdoc_api import get_api

logger = logging.getLogger(__name__)

TZ = ZoneInfo(TIMEZONE)


def _now_str() -> str:
    from datetime import datetime
    return datetime.now(TZ).isoformat(timespec="seconds")


async def run_sync(sync_type: str = "scheduled") -> str:
    """
    Barcha ma'lumotlarni tortadi.
    Muvaffaqiyatli bo'lsa 'ok' qaytaradi, xato bo'lsa xabar matni.
    """
    api = get_api()
    now = _now_str()
    today = date.today().isoformat()
    lookback_from = (date.today() - timedelta(days=DEAD_OUTLET_LOOKBACK_DAYS)).isoformat()

    try:
        await api.login()

        with get_conn() as conn:
            # 1. Agentlar
            agents = await api.get_agents()
            logger.info("Agentlar: %d ta", len(agents))
            for a in agents:
                upsert_agent(conn, str(a["SD_id"]), a.get("code_1C", ""),
                             a["name"], a.get("active", "Y"), now)

            # 2. Mahsulotlar
            products = await api.get_products()
            logger.info("Mahsulotlar: %d ta", len(products))
            for p in products:
                cat = p.get("category", {})
                cat_id = str(cat.get("SD_id", "")) if isinstance(cat, dict) else ""
                upsert_product(conn, str(p["SD_id"]), p.get("code_1C", ""),
                               p["name"], cat_id, now)

            # 3. Mijozlar
            clients = await api.get_clients()
            logger.info("Mijozlar: %d ta", len(clients))
            for c in clients:
                agents_list = c.get("agents", [])
                primary = str(agents_list[0]["id"]) if agents_list else None
                city = c.get("city", {})
                territory = str(city.get("SD_id", "")) if isinstance(city, dict) else ""
                upsert_client(conn, str(c["SD_id"]), c.get("code_1C", ""),
                              c["name"], primary, territory, now)

            # 4. Buyurtmalar (oxirgi LOOKBACK_DAYS kun)
            orders = await api.get_orders(lookback_from, today)
            logger.info("Buyurtmalar: %d ta", len(orders))
            for o in orders:
                agent_block = o.get("agent", {})
                agent_id = str(agent_block.get("SD_id", "")) if isinstance(agent_block, dict) else ""
                client_block = o.get("client", {})
                client_id = str(client_block.get("SD_id", "")) if isinstance(client_block, dict) else ""
                upsert_order(
                    conn, str(o["SD_id"]),
                    o.get("dateDocument", today),
                    int(o.get("status", 0)),
                    agent_id, client_id,
                    float(o.get("totalSummaAfterDiscount", 0) or 0),
                )
                items = o.get("orderProducts", [])
                parsed_items = []
                for item in items:
                    prod = item.get("product", {})
                    parsed_items.append({
                        "product_sd_id": str(prod.get("SD_id", "")),
                        "product_name": prod.get("name", ""),
                        "quantity": float(item.get("quantity", 0) or 0),
                        "summa": float(item.get("summa", 0) or 0),
                    })
                replace_order_items(conn, str(o["SD_id"]), parsed_items)

            # 5. Balanslar (qarzlar)
            balances = await api.get_balance()
            logger.info("Balanslar: %d ta", len(balances))
            for b in balances:
                upsert_balance(conn, str(b["SD_id"]), b.get("name", ""),
                               float(b.get("balance", 0) or 0), now)

            # 6. Ombor qoldiqlari
            warehouses = await api.get_stock()
            logger.info("Omborlar: %d ta", len(warehouses))
            for wh in warehouses:
                wh_name = wh.get("name", "Ombor")
                for prod in wh.get("products", []):
                    upsert_stock(conn,
                                 str(prod.get("SD_id", "")),
                                 prod.get("name", ""),
                                 wh_name,
                                 float(prod.get("quantity", 0) or 0),
                                 now)

            # 7. Bugungi vizitlar
            visits = await api.get_visits(today, today)
            logger.info("Vizitlar (bugun): %d ta", len(visits))
            for v in visits:
                upsert_visit(
                    conn,
                    v.get("date", today),
                    str(v.get("agent_id", "")),
                    v.get("agent_name", ""),
                    str(v.get("client_id", "")),
                    v.get("client_name", ""),
                    int(v.get("planned", 0) or 0),
                    int(v.get("visited", 0) or 0),
                    int(v.get("has_order", 0) or 0),
                    float(v.get("order_summa", 0) or 0),
                )

            log_sync(conn, now, sync_type, "ok")

        logger.info("Sinxronizatsiya tugadi.")
        return "ok"

    except Exception as exc:
        logger.exception("Sinxronizatsiya xatosi: %s", exc)
        with get_conn() as conn:
            log_sync(conn, now, sync_type, "error", str(exc))
        return str(exc)
