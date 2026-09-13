from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChainConfig:
    key: str
    name: str
    native_symbol: str
    blockscout_base_url: str
    dexscreener_chain_id: str


CHAINS: dict[str, ChainConfig] = {
    "ethereum": ChainConfig(
        key="ethereum",
        name="Ethereum",
        native_symbol="ETH",
        blockscout_base_url="https://eth.blockscout.com",
        dexscreener_chain_id="ethereum",
    ),
    "base": ChainConfig(
        key="base",
        name="Base",
        native_symbol="ETH",
        blockscout_base_url="https://base.blockscout.com",
        dexscreener_chain_id="base",
    ),
    "arbitrum": ChainConfig(
        key="arbitrum",
        name="Arbitrum One",
        native_symbol="ETH",
        blockscout_base_url="https://arbitrum.blockscout.com",
        dexscreener_chain_id="arbitrum",
    ),
    "optimism": ChainConfig(
        key="optimism",
        name="Optimism",
        native_symbol="ETH",
        blockscout_base_url="https://optimism.blockscout.com",
        dexscreener_chain_id="optimism",
    ),
    "polygon": ChainConfig(
        key="polygon",
        name="Polygon",
        native_symbol="POL",
        blockscout_base_url="https://polygon.blockscout.com",
        dexscreener_chain_id="polygon",
    ),
}
