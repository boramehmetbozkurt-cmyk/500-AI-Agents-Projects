from decimal import Decimal

import pytest

from wallet_hunter.hunter import validate_address
from wallet_hunter.risk import opportunity_source_risk, token_risk_score


def test_validate_address_accepts_evm_address() -> None:
    address = "0x91825471DE3b732E418d18b06A9e0C0ba8735358"
    assert validate_address(address) == address


def test_validate_address_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        validate_address("not-a-wallet")


def test_spam_like_token_gets_high_risk() -> None:
    score, warnings = token_risk_score(
        name="CLAIM REWARD AT bad.xyz",
        symbol="CLAIM",
        price_usd=None,
        liquidity_usd=None,
        verified=False,
    )
    assert score >= 80
    assert warnings


def test_liquid_verified_token_stays_low_risk() -> None:
    score, warnings = token_risk_score(
        name="Example",
        symbol="EX",
        price_usd=Decimal(1),
        liquidity_usd=Decimal(1000000),
        verified=True,
    )
    assert score == 0
    assert warnings == []


def test_official_https_source_is_low_risk() -> None:
    score, warnings = opportunity_source_risk(
        "https://portfolio.metamask.io/",
        ["metamask.io"],
    )
    assert score == 0
    assert warnings == []
