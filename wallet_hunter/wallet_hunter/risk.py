from __future__ import annotations

import decimal
import urllib.parse


SPAM_MARKERS = ("claim", "airdrop", "visit", "http", ".com", ".xyz", "reward")


def token_risk_score(
    *,
    name: str,
    symbol: str,
    price_usd: decimal.Decimal | None,
    liquidity_usd: decimal.Decimal | None,
    verified: bool | None,
) -> tuple[int, list[str]]:
    score = 0
    warnings: list[str] = []
    label = f"{name} {symbol}".lower()

    if any(marker in label for marker in SPAM_MARKERS):
        score += 35
        warnings.append("token name/symbol resembles a promotional or phishing token")
    if verified is False:
        score += 20
        warnings.append("token contract is not marked verified by explorer metadata")
    if price_usd is None:
        score += 15
        warnings.append("no reliable USD price found")
    if liquidity_usd is None:
        score += 20
        warnings.append("no DEX liquidity evidence found")
    elif liquidity_usd < decimal.Decimal(10000):
        score += 25
        warnings.append("very low DEX liquidity")
    elif liquidity_usd < decimal.Decimal(50000):
        score += 15
        warnings.append("low DEX liquidity")
    elif liquidity_usd < decimal.Decimal(250000):
        score += 5
        warnings.append("limited DEX liquidity")

    return min(score, 100), warnings


def opportunity_source_risk(
    source_url: str,
    allowed_domains: list[str],
) -> tuple[int, list[str]]:
    warnings: list[str] = []
    parsed = urllib.parse.urlparse(source_url)
    host = (parsed.hostname or "").lower()
    score = 0

    if parsed.scheme != "https":
        score += 50
        warnings.append("claim source is not HTTPS")
    trusted = any(
        host == domain.lower() or host.endswith("." + domain.lower())
        for domain in allowed_domains
    )
    if not trusted:
        score += 50
        warnings.append("claim source host is outside the manifest allowlist")
    return min(score, 100), warnings
