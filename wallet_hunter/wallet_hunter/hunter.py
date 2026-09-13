from __future__ import annotations

import asyncio
import re
from decimal import Decimal
from pathlib import Path

import httpx

from .chains import CHAINS, ChainConfig
from .models import ChainSnapshot, Opportunity, ScanReport, TokenPosition
from .providers import BlockscoutClient, DexScreenerClient
from .registry import load_registry, spec_to_opportunity
from .risk import token_risk_score

ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


def validate_address(address: str) -> str:
    if not ADDRESS_RE.fullmatch(address):
        raise ValueError("Expected a 20-byte EVM address starting with 0x")
    return address


class WalletHunter:
    def __init__(self, *, max_tokens_per_chain: int = 30) -> None:
        self.max_tokens_per_chain = max(1, min(max_tokens_per_chain, 100))
        self.blockscout = BlockscoutClient()
        self.dex = DexScreenerClient()

    async def _scan_chain(
        self,
        client: httpx.AsyncClient,
        chain: ChainConfig,
        address: str,
    ) -> ChainSnapshot:
        try:
            info, counters, raw_tokens = await asyncio.gather(
                self.blockscout.address_info(client, chain, address),
                self.blockscout.counters(client, chain, address),
                self.blockscout.token_balances(client, chain, address),
            )
        except Exception as exc:  # provider isolation: one chain must not kill the report
            return ChainSnapshot(
                chain=chain.key,
                address=address,
                native_symbol=chain.native_symbol,
                native_amount=Decimal(0),
                errors=[f"chain provider unavailable: {type(exc).__name__}"],
            )

        native_amount = self.blockscout.parse_native_amount(info)
        native_price = None
        try:
            native_price = Decimal(str(info["exchange_rate"])) if info.get("exchange_rate") not in (None, "") else None
        except Exception:
            native_price = None

        snapshot = ChainSnapshot(
            chain=chain.key,
            address=address,
            native_symbol=chain.native_symbol,
            native_amount=native_amount,
            native_price_usd=native_price,
            native_value_usd=(native_amount * native_price) if native_price is not None else None,
            transaction_count=_int_or_none(counters.get("transactions_count")),
            token_transfer_count=_int_or_none(counters.get("token_transfers_count")),
        )

        parsed = [self.blockscout.parse_token(item) for item in raw_tokens]
        parsed = [item for item in parsed if item["contract"] and item["amount"] > 0]
        parsed = parsed[: self.max_tokens_per_chain]

        async def enrich(item: dict) -> TokenPosition:
            price = item["exchange_rate"]
            liquidity = None
            evidence = [
                f"{chain.blockscout_base_url}/address/{address}?tab=tokens",
                f"{chain.blockscout_base_url}/token/{item['contract']}",
            ]
            try:
                market = await self.dex.token_market(client, chain, item["contract"])
                if market.get("price_usd") is not None:
                    price = market["price_usd"]
                liquidity = market.get("liquidity_usd")
                if market.get("evidence"):
                    evidence.append(str(market["evidence"]))
            except Exception:
                pass

            value = item["amount"] * price if price is not None else None
            risk, warnings = token_risk_score(
                name=item["name"],
                symbol=item["symbol"],
                price_usd=price,
                liquidity_usd=liquidity,
                verified=item["verified"],
            )
            return TokenPosition(
                chain=chain.key,
                contract=item["contract"],
                name=item["name"],
                symbol=item["symbol"],
                amount=item["amount"],
                price_usd=price,
                value_usd=value,
                liquidity_usd=liquidity,
                verified=item["verified"],
                risk_score=risk,
                warnings=warnings,
                evidence=evidence,
            )

        snapshot.tokens = await asyncio.gather(*(enrich(item) for item in parsed)) if parsed else []
        snapshot.tokens.sort(key=lambda token: token.value_usd or Decimal(0), reverse=True)
        return snapshot

    async def _load_opportunities(
        self,
        client: httpx.AsyncClient,
        address: str,
        registry_path: str | Path | None,
    ) -> list[Opportunity]:
        if registry_path is None:
            return []
        specs = load_registry(registry_path)
        results: list[Opportunity] = []
        for spec in specs:
            if not spec.eligibility_url_template:
                results.append(spec_to_opportunity(spec, "manual_check", ["No official machine-readable eligibility endpoint is configured."]))
                continue
            url = spec.eligibility_url_template.replace("{address}", address)
            try:
                response = await client.get(url, timeout=10.0, follow_redirects=False)
                response.raise_for_status()
                payload = response.json()
                eligible = _extract_eligible(payload)
                status = "eligible" if eligible is True else "not_eligible" if eligible is False else "manual_check"
                notes = [f"Eligibility endpoint checked: {url}"]
                results.append(spec_to_opportunity(spec, status, notes))
                results[-1].evidence.append(url)
            except Exception as exc:
                results.append(spec_to_opportunity(spec, "manual_check", [f"Eligibility check failed: {type(exc).__name__}"]))
        return results

    async def scan(self, address: str, *, registry_path: str | Path | None = None) -> ScanReport:
        address = validate_address(address)
        headers = {"User-Agent": "wallet-hunter/0.1"}
        async with httpx.AsyncClient(headers=headers) as client:
            chains, opportunities = await asyncio.gather(
                asyncio.gather(*(self._scan_chain(client, chain, address) for chain in CHAINS.values())),
                self._load_opportunities(client, address, registry_path),
            )

        total = Decimal(0)
        for chain in chains:
            if chain.native_value_usd is not None:
                total += chain.native_value_usd
            for token in chain.tokens:
                if token.value_usd is not None and token.risk_score < 80:
                    total += token.value_usd

        opportunities.sort(
            key=lambda item: (
                item.status == "eligible",
                item.estimated_value_usd or Decimal(0),
                -item.risk_score,
            ),
            reverse=True,
        )
        return ScanReport(
            address=address,
            chains=list(chains),
            opportunities=opportunities,
            total_known_value_usd=total,
            warnings=[
                "Unknown or spam tokens can display fake prices. Never use this report as permission to sign a transaction.",
                "Seed phrases/private keys are never required by Wallet Hunter.",
            ],
        )


def _int_or_none(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _extract_eligible(payload: object) -> bool | None:
    if isinstance(payload, bool):
        return payload
    if isinstance(payload, (int, float)) and payload in (0, 1):
        return bool(payload)
    if isinstance(payload, dict):
        for key in ("eligible", "isEligible", "is_eligible", "result"):
            value = payload.get(key)
            if isinstance(value, bool):
                return value
            if value in (0, 1, "0", "1"):
                return str(value) == "1"
    return None
