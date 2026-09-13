from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(slots=True)
class TokenPosition:
    chain: str
    contract: str
    name: str
    symbol: str
    amount: Decimal
    price_usd: Decimal | None = None
    value_usd: Decimal | None = None
    liquidity_usd: Decimal | None = None
    verified: bool | None = None
    risk_score: int = 0
    warnings: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ChainSnapshot:
    chain: str
    address: str
    native_symbol: str
    native_amount: Decimal
    native_price_usd: Decimal | None = None
    native_value_usd: Decimal | None = None
    transaction_count: int | None = None
    token_transfer_count: int | None = None
    tokens: list[TokenPosition] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Opportunity:
    id: str
    name: str
    source_url: str
    chains: list[str]
    status: str
    estimated_value_usd: Decimal | None = None
    risk_score: int = 0
    notes: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ScanReport:
    address: str
    chains: list[ChainSnapshot]
    opportunities: list[Opportunity]
    total_known_value_usd: Decimal
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        def normalize(value: Any) -> Any:
            if isinstance(value, Decimal):
                return str(value)
            if isinstance(value, list):
                return [normalize(item) for item in value]
            if isinstance(value, dict):
                return {key: normalize(item) for key, item in value.items()}
            return value

        return normalize(asdict(self))
