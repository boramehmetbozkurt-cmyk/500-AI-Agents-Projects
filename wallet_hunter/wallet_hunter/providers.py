from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from .config import CHAINS, settings
from .models import Opportunity, SecuritySignal, TokenPosition


class RpcClient:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def call(self, chain: str, method: str, params: list[Any]) -> Any:
        url = settings.rpc_url(chain)
        response = await self.client.post(
            url,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        )
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise RuntimeError(str(payload["error"]))
        return payload.get("result")

    async def native_balance(self, chain: str, address: str) -> float:
        result = await self.call(chain, "eth_getBalance", [address, "latest"])
        return int(result, 16) / 10**18

    async def erc20_balance(self, chain: str, contract: str, address: str, decimals: int) -> tuple[int, float]:
        selector = "70a08231"  # balanceOf(address)
        encoded_address = address.lower().replace("0x", "").rjust(64, "0")
        result = await self.call(
            chain,
            "eth_call",
            [{"to": contract, "data": f"0x{selector}{encoded_address}"}, "latest"],
        )
        raw = int(result, 16)
        return raw, raw / (10**decimals)

    async def simulate(self, chain: str, from_address: str, to: str, data: str, value_wei: int = 0) -> str:
        tx = {
            "from": from_address,
            "to": to,
            "data": data,
            "value": hex(value_wei),
        }
        return await self.call(chain, "eth_call", [tx, "latest"])


class EtherscanV2Provider:
    endpoint = "https://api.etherscan.io/v2/api"

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def discover_tokens(self, chain: str, address: str) -> list[TokenPosition]:
        if not settings.etherscan_api_key:
            return []

        spec = CHAINS[chain]
        max_tokens = max(1, settings.wallet_hunter_max_tokens)
        page_size = min(100, max_tokens)
        discovered: dict[str, TokenPosition] = {}
        page = 1

        while len(discovered) < max_tokens and page <= 100:
            params = {
                "chainid": str(spec.chain_id),
                "module": "account",
                "action": "tokentx",
                "address": address,
                "page": str(page),
                "offset": str(page_size),
                "sort": "desc",
                "apikey": settings.etherscan_api_key,
            }
            response = await self.client.get(self.endpoint, params=params)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise RuntimeError("Etherscan returned a non-object response")

            rows = payload.get("result")
            status = str(payload.get("status", ""))
            message = str(payload.get("message", ""))

            if status == "0":
                no_rows = isinstance(rows, list) and not rows
                no_transactions = isinstance(rows, str) and "no transactions found" in rows.lower()
                if no_rows or no_transactions:
                    break
                detail = rows if isinstance(rows, str) else message
                raise RuntimeError(f"Etherscan API failure: {message or detail}")

            if status not in {"", "1"}:
                raise RuntimeError(f"Etherscan API failure: {message or status}")
            if not isinstance(rows, list):
                raise RuntimeError(
                    f"Etherscan API failure: {message or 'result is not a transaction list'}"
                )

            for row in rows:
                contract = str(row.get("contractAddress", "")).lower()
                if not contract.startswith("0x") or len(contract) != 42:
                    continue
                try:
                    decimals = int(row.get("tokenDecimal") or 18)
                except (TypeError, ValueError):
                    decimals = 18
                discovered.setdefault(
                    contract,
                    TokenPosition(
                        chain=chain,
                        contract=contract,
                        symbol=row.get("tokenSymbol") or None,
                        name=row.get("tokenName") or None,
                        decimals=decimals,
                        source=["etherscan-v2:tokentx"],
                    ),
                )
                if len(discovered) >= max_tokens:
                    break

            if len(rows) < page_size:
                break
            page += 1

        return list(discovered.values())[:max_tokens]


class DexScreenerProvider:
    endpoint = "https://api.dexscreener.com/latest/dex/tokens/{contract}"

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def enrich(self, token: TokenPosition) -> TokenPosition:
        try:
            response = await self.client.get(self.endpoint.format(contract=token.contract))
            response.raise_for_status()
            pairs = response.json().get("pairs") or []
            chain_id = CHAINS[token.chain].dexscreener_chain
            contract = token.contract.lower()
            pairs = [
                pair
                for pair in pairs
                if pair.get("chainId") == chain_id
                and str((pair.get("baseToken") or {}).get("address", "")).lower() == contract
            ]
            if not pairs:
                return token
            best = max(
                pairs,
                key=lambda pair: float((pair.get("liquidity") or {}).get("usd") or 0),
            )
            token.price_usd = float(best.get("priceUsd")) if best.get("priceUsd") else None
            token.liquidity_usd = float((best.get("liquidity") or {}).get("usd") or 0)
            if token.balance is not None and token.price_usd is not None:
                token.value_usd = token.balance * token.price_usd
            token.source.append("dexscreener")
        except Exception:
            pass
        return token


class GoPlusProvider:
    endpoint = "https://api.gopluslabs.io/api/v1/token_security/{chain_id}"

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def check(self, token: TokenPosition) -> list[SecuritySignal]:
        spec = CHAINS[token.chain]
        try:
            response = await self.client.get(
                self.endpoint.format(chain_id=spec.chain_id),
                params={"contract_addresses": token.contract},
            )
            response.raise_for_status()
            payload = response.json().get("result") or {}
            row = payload.get(token.contract.lower()) or payload.get(token.contract) or {}
        except Exception:
            return []

        flags = {
            "is_honeypot": ("critical", "honeypot", "Token is flagged as a honeypot"),
            "cannot_sell_all": ("high", "cannot_sell_all", "Token may prevent selling the full balance"),
            "is_blacklisted": ("high", "blacklist", "Token contract may blacklist addresses"),
            "hidden_owner": ("medium", "hidden_owner", "Token ownership may be obscured"),
            "can_take_back_ownership": ("medium", "take_back_ownership", "Ownership may be reclaimable"),
            "owner_change_balance": ("high", "owner_change_balance", "Owner may be able to alter balances"),
            "slippage_modifiable": ("medium", "slippage_modifiable", "Trading tax/slippage may be modifiable"),
        }
        signals: list[SecuritySignal] = []
        for field, (severity, code, detail) in flags.items():
            if str(row.get(field, "0")) == "1":
                signals.append(
                    SecuritySignal(
                        provider="goplus",
                        contract=token.contract,
                        chain=token.chain,
                        severity=severity,
                        code=code,
                        detail=detail,
                        source="https://gopluslabs.io/token-security",
                    )
                )
        return signals


class ManifestOpportunityProvider:
    def load(self) -> list[Opportunity]:
        path = Path(settings.wallet_hunter_opportunities)
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload if isinstance(payload, list) else payload.get("opportunities", [])
        return [Opportunity.model_validate(row) for row in rows]
