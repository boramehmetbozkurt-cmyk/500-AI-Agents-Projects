import pytest
from pydantic import ValidationError

from wallet_hunter.models import ChainResult, Opportunity, WalletScanRequest
from wallet_hunter.scanner import WalletScanner


VALID = "0x91825471DE3b732E418d18b06A9e0C0ba8735358"


def test_wallet_address_validation():
    request = WalletScanRequest(address=VALID)
    assert request.address == VALID


def test_wallet_address_rejects_invalid_input():
    with pytest.raises(ValidationError):
        WalletScanRequest(address="not-an-address")


def test_confirmed_positive_net_value_ranks_first():
    confirmed = Opportunity(
        id="confirmed",
        title="confirmed",
        chain="base",
        reward_symbol="TEST",
        status="confirmed",
        estimated_value_usd=20,
        estimated_gas_usd=1,
        official_url="https://example.com/confirmed",
        risk_score=10,
    )
    unknown = Opportunity(
        id="unknown",
        title="unknown",
        chain="base",
        status="unknown",
        estimated_value_usd=100,
        estimated_gas_usd=1,
        official_url="https://example.com/unknown",
        risk_score=10,
    )

    ranked = WalletScanner._rank_opportunities([unknown, confirmed], [ChainResult(chain="base")])
    assert ranked[0].id == "confirmed"
    assert ranked[0].net_value_usd == 19
    assert ranked[1].risk_score >= 40
