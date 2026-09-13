from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator


EVM_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


class WalletScanRequest(BaseModel):
    address: str
    chains: list[str] = Field(default_factory=lambda: ["ethereum", "base", "arbitrum", "optimism", "polygon"])

    @field_validator("address")
    @classmethod
    def validate_address(cls, value: str) -> str:
        if not EVM_ADDRESS_RE.fullmatch(value):
            raise ValueError("invalid EVM address")
        return value


class TokenPosition(BaseModel):
    chain: str
    contract: str
    symbol: str | None = None
    name: str | None = None
    decimals: int | None = None
    raw_balance: int | None = None
    balance: float | None = None
    price_usd: float | None = None
    liquidity_usd: float | None = None
    value_usd: float | None = None
    source: list[str] = Field(default_factory=list)


class NativeBalance(BaseModel):
    chain: str
    symbol: str
    balance: float
    source: str


class SecuritySignal(BaseModel):
    provider: str
    contract: str
    chain: str
    severity: Literal["info", "low", "medium", "high", "critical"]
    code: str
    detail: str
    source: str | None = None


class Opportunity(BaseModel):
    id: str
    title: str
    chain: str
    reward_symbol: str | None = None
    status: Literal["confirmed", "candidate", "unknown", "rejected"] = "unknown"
    estimated_value_usd: float | None = None
    estimated_gas_usd: float | None = None
    net_value_usd: float | None = None
    official_url: str
    evidence: list[str] = Field(default_factory=list)
    risk_score: int = Field(default=50, ge=0, le=100)
    risk_reasons: list[str] = Field(default_factory=list)


class ChainResult(BaseModel):
    chain: str
    native: NativeBalance | None = None
    tokens: list[TokenPosition] = Field(default_factory=list)
    security: list[SecuritySignal] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class WalletReport(BaseModel):
    address: str
    chains: list[ChainResult]
    opportunities: list[Opportunity]
    warnings: list[str] = Field(default_factory=list)


class SimulationRequest(BaseModel):
    chain: str
    from_address: str
    to: str
    data: str
    value_wei: int = 0

    @field_validator("from_address", "to")
    @classmethod
    def validate_evm_address(cls, value: str) -> str:
        if not EVM_ADDRESS_RE.fullmatch(value):
            raise ValueError("invalid EVM address")
        return value

    @field_validator("data")
    @classmethod
    def validate_data(cls, value: str) -> str:
        if not value.startswith("0x") or len(value) % 2 != 0:
            raise ValueError("data must be 0x-prefixed hex")
        return value


class SimulationResult(BaseModel):
    chain: str
    ok: bool
    result: str | None = None
    error: str | None = None
    broadcast: bool = False
