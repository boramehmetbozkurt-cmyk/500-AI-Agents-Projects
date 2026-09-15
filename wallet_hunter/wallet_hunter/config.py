from __future__ import annotations

from dataclasses import dataclass

from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True)
class ChainSpec:
    key: str
    chain_id: int
    rpc_env: str
    rpc_default: str
    dexscreener_chain: str
    native_symbol: str


CHAINS: dict[str, ChainSpec] = {
    "ethereum": ChainSpec("ethereum", 1, "RPC_ETHEREUM", "https://ethereum-rpc.publicnode.com", "ethereum", "ETH"),
    "base": ChainSpec("base", 8453, "RPC_BASE", "https://mainnet.base.org", "base", "ETH"),
    "arbitrum": ChainSpec("arbitrum", 42161, "RPC_ARBITRUM", "https://arb1.arbitrum.io/rpc", "arbitrum", "ETH"),
    "optimism": ChainSpec("optimism", 10, "RPC_OPTIMISM", "https://mainnet.optimism.io", "optimism", "ETH"),
    "polygon": ChainSpec("polygon", 137, "RPC_POLYGON", "https://polygon-rpc.com", "polygon", "POL"),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    etherscan_api_key: str | None = None
    wallet_hunter_timeout: float = 12.0
    wallet_hunter_max_tokens: int = 50
    wallet_hunter_opportunities: str = "opportunities.example.json"

    rpc_ethereum: str = CHAINS["ethereum"].rpc_default
    rpc_base: str = CHAINS["base"].rpc_default
    rpc_arbitrum: str = CHAINS["arbitrum"].rpc_default
    rpc_optimism: str = CHAINS["optimism"].rpc_default
    rpc_polygon: str = CHAINS["polygon"].rpc_default

    def rpc_url(self, chain: str) -> str:
        value = getattr(self, f"rpc_{chain}", None)
        if not value:
            raise KeyError(f"No RPC configured for {chain}")
        return value


settings = Settings()
