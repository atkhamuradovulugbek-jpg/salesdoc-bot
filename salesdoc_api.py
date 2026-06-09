"""
salesdoc_api.py — Sales Doctor API V2 bilan ishlash.
Login, token saqlash, barcha GET metodlar, auto re-login va backoff.
"""

import asyncio
import logging
import time
from datetime import date

import httpx

from config import SALESDOC_BASE_URL, SALESDOC_LOGIN, SALESDOC_PASSWORD

logger = logging.getLogger(__name__)

PAUSE_BETWEEN_REQUESTS = 0.4  # sekundlarda


class SalesDocClient:
    def __init__(self) -> None:
        self._user_id: str | None = None
        self._token: str | None = None
        self._client = httpx.AsyncClient(timeout=30.0)

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    async def login(self) -> None:
        """Login qilib token oladi."""
        payload = {
            "method": "login",
            "auth": {
                "login": SALESDOC_LOGIN,
                "password": SALESDOC_PASSWORD,
            },
        }
        data = await self._raw_post(payload)
        result = data["result"]
        self._user_id = str(result["userId"])
        self._token = str(result["token"])
        logger.info("Sales Doctor login muvaffaqiyatli. userId=%s", self._user_id)

    def _auth_block(self) -> dict:
        return {"userId": self._user_id, "token": self._token}

    # ------------------------------------------------------------------
    # Low-level POST with retry + re-login
    # ------------------------------------------------------------------

    async def _raw_post(self, payload: dict) -> dict:
        """HTTP POST yuboradi. 429 → backoff, network xato → 3 marta urinadi."""
        url = SALESDOC_BASE_URL
        for attempt in range(5):
            try:
                resp = await self._client.post(url, json=payload)
                if resp.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning("429 rate-limit. %s sek kutilmoqda...", wait)
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.RequestError as exc:
                logger.error("So'rov xatosi (urinish %s): %s", attempt + 1, exc)
                if attempt == 4:
                    raise
                await asyncio.sleep(2 ** attempt)
        raise RuntimeError("Sales Doctor javob bermadi (5 urinishdan keyin)")

    async def _post(self, payload: dict) -> dict:
        """Avto re-login bilan POST."""
        if not self._token:
            await self.login()
        try:
            data = await self._raw_post(payload)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                logger.warning("Token eskirdi, qayta login...")
                await self.login()
                payload["auth"] = self._auth_block()
                data = await self._raw_post(payload)
            else:
                raise
        # API o'zida ham 401 qaytarishi mumkin (HTTP 200 bilan)
        if isinstance(data, dict) and data.get("status") == 401:
            logger.warning("API 401, qayta login...")
            await self.login()
            payload["auth"] = self._auth_block()
            data = await self._raw_post(payload)
        return data

    # ------------------------------------------------------------------
    # Pagination helper
    # ------------------------------------------------------------------

    async def _paginate(self, method: str, params: dict) -> list[dict]:
        """Barcha sahifalarni o'qib, birlashtirib qaytaradi."""
        result_key_map = {
            "getAgent": "agent",
            "getProduct": "product",
            "getClient": "client",
            "getBalance": "balance",
            "getVisit": "visit",
            "getStock": "warehouse",
            "getOrder": "order",
        }
        key = result_key_map.get(method, method)
        all_items: list[dict] = []
        page = 1
        while True:
            payload = {
                "method": method,
                "auth": self._auth_block(),
                "params": {**params, "pagination": {"limit": 1000, "page": page}},
            }
            data = await self._post(payload)
            result = data.get("result", {})
            items = result.get(key, [])
            all_items.extend(items)
            total = result.get("pagination", {}).get("total", len(all_items))
            if len(all_items) >= total or not items:
                break
            page += 1
            await asyncio.sleep(PAUSE_BETWEEN_REQUESTS)
        return all_items

    # ------------------------------------------------------------------
    # Ommaviy metodlar
    # ------------------------------------------------------------------

    async def get_agents(self) -> list[dict]:
        return await self._paginate("getAgent", {})

    async def get_products(self) -> list[dict]:
        return await self._paginate("getProduct", {})

    async def get_clients(self) -> list[dict]:
        return await self._paginate("getClient", {})

    async def get_balance(self) -> list[dict]:
        return await self._paginate("getBalance", {})

    async def get_visits(self, date_from: str, date_to: str) -> list[dict]:
        """date_from/date_to — YYYY-MM-DD formatida."""
        params = {
            "filter": {
                "period": {
                    "date": {"from": date_from, "to": date_to}
                }
            }
        }
        return await self._paginate("getVisit", params)

    async def get_stock(self) -> list[dict]:
        return await self._paginate("getStock", {})

    async def get_orders(self, date_from: str, date_to: str,
                         statuses: list[int] | None = None) -> list[dict]:
        if statuses is None:
            statuses = [1, 2, 3]
        params = {
            "filter": {
                "status": statuses,
                "agent": "all",
                "period": {
                    "date": {"from": date_from, "to": date_to}
                },
            }
        }
        return await self._paginate("getOrder", params)

    async def close(self) -> None:
        await self._client.aclose()


# Yagona global instance
_client: SalesDocClient | None = None


def get_api() -> SalesDocClient:
    global _client
    if _client is None:
        _client = SalesDocClient()
    return _client
