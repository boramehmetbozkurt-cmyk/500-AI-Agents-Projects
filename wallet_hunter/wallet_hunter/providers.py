from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from .chains import ChainConfig


class ProviderError(RuntimeError):
    pass


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


class BlockscoutClient:
    def __init__(self, timeout: float = 12.0) -> None:
        self.timeout = timeout

    async def address_info(self, client: httpx.AsyncClient, chain: ChainConfig, address: str) -> dict[str, Any]:
        url = f"{chain.blockscout_base_url}/api/v2/addresses/{address}"
        response = await client.get(url, timeout=self.timeout, follow_redirects=False)
        if response.status_code == 404:
            return {"coin_balance": "0", "exchange_rate": None}
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ProviderError(f"Unexpected Blockscout address response for {chain.key}")
        return data

    async def counters(self, client: httpx.AsyncClient, chain: ChainConfig, address: str) -> dict[str, Any]:
        url = f"{chain.blockscout_base_url}/api/v2/addresses/{address}/counters"
        response = await client.get(url, timeout=self.timeout, follow_redirects=False)
        if response.status_code == 404:
            return {}
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}

    async def token_balances(self, client: httpx.AsyncClient, chain: ChainConfig, address: str) -> list[dict[str, Any]]:
        url = f"{chain.blockscout_base_url}/api/v2/addresses/{address}/token-balances"
        response = await client.get(url, timeout=self.timeout, follow_redirects=False)
        if response.status_code == 404:
            return []
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise ProviderError(f"Unexpected Blockscout token response for {chain.key}")
        return [item for item in data if isinstance(item, dict)]

    @staticmethod
    def parse_native_amount(info: dict[str, Any]) -> Decimal:
        raw = _decimal(info.get("coin_balance")) or Decimal(0)
        return raw / (Decimal(10) ** 18)

    @staticmethod
    def parse_token(item: dict[str, Any]) -> dict[str, Any]:
        token = item.get("token") or {}
        if not isinstance(token, dict):
            token = {}
        raw = _decimal(item.get("value")) or Decimal(0)
        decimals_raw = token.get("decimals")
        try:
            decimals = int(decimals_raw) if decimals_raw is not None else 0
        except (TypeError, ValueError):
            decimals = 0
        amount = raw / (Decimal(10) ** max(decimals, 0))
        return {
            "contract": str(token.get("address") or token.get("address_hash") or ""),
            "name": str(token.get("name") or "Unknown"),
            "symbol": str(token.get("symbol") or "UNKNOWN"),
            "amount": amount,
            "exchange_rate": _decimal(token.get("exchange_rate")),
            "verified": token.get("is_verified") if isinstance(token.get("is_verified"), bool) else None,
        }


class DexScreenerClient:
    BASE_URL = "https://api.dexscreener.com"

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    async def token_market(self, client: httpx.AsyncClient, chain: ChainConfig, token_address: str) -> dict[str, Decimal | str | None]:
        if not token_address.startswith("0x") or len(token_address) != 42:
            return {"price_usd": None, "liquidity_usd": None, "evidence": None}
        url = f"{self.BASE_URL}/token-pairs/v1/{chain.dexscreener_chain_id}/{token_address}"
        response = await client.get(url, timeout=self.timeout, follow_redirects=False)
        if response.status_code == 404:
            return {"price_usd": None, "liquidity_usd": None, "evidence": url}
        response.raise_for_status()
        data = response.json()
        pairs = data if isinstance(data, list) else []
        token_lower = token_address.lower()
        candidates: list[tuple[Decimal, Decimal | None, str | None]] = []
        for pair in pairs:
            if not isinstance(pair, dict):
                continue
            base = pair.get("baseToken") or {}
            if not isinstance(base, dict) or str(base.get("address", "")).lower() != token_lower:
                continue
            liquidity_obj = pair.get("liquidity") or {}
            liquidity = _decimal(liquidity_obj.get("usd")) if isinstance(liquidity_obj, dict) else None
            price = _decimal(pair.get("priceUsd"))
            evidence = pair.get("url") if isinstance(pair.get("url"), str) else url
            candidates.append((liquidity or Decimal(0), price, evidence))
        if not candidates:
            return {"price_usd": None, "liquidity_usd": None, "evidence": url}
        liquidity, price, evidence = max(candidates, key=lambda item: item[0])
        return {"price_usd": price, "liquidity_usd": liquidity, "evidence": evidence}
