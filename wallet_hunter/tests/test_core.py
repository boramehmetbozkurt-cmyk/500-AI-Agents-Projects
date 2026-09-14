import httpx
import pytest
from pydantic import ValidationError

from wallet_hunter.config import settings
from wallet_hunter.models import (
    ChainResult,
    Opportunity,
    SecuritySignal,
    TokenPosition,
    WalletScanRequest,
)
from wallet_hunter.providers import DexScreenerProvider, EtherscanV2Provider
from wallet_hunter.scanner import WalletScanner


VALID = "0x91825471DE3b732E418d18b06A9e0C0ba8735358"
TOKEN_A = "0x1111111111111111111111111111111111111111"
TOKEN_B = "0x2222222222222222222222222222222222222222"


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
        eligibility_address=VALID,
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

    ranked = WalletScanner._rank_opportunities(
        [unknown, confirmed],
        [ChainResult(chain="base")],
    )
    assert ranked[0].id == "confirmed"
    assert ranked[0].net_value_usd == 19
    assert ranked[1].risk_score >= 40


def test_confirmed_opportunity_requires_wallet_binding_and_requested_chain():
    generic = Opportunity(
        id="generic",
        title="generic",
        chain="base",
        status="confirmed",
        official_url="https://example.com/generic",
        risk_score=10,
    )
    bound = Opportunity(
        id="bound",
        title="bound",
        chain="base",
        status="confirmed",
        eligibility_address=VALID,
        official_url="https://example.com/bound",
        risk_score=10,
    )
    other_chain = Opportunity(
        id="polygon",
        title="polygon",
        chain="polygon",
        status="candidate",
        official_url="https://example.com/polygon",
    )

    scoped = WalletScanner._scope_opportunities(
        [generic, bound, other_chain],
        ["base"],
        VALID,
    )
    by_id = {item.id: item for item in scoped}
    assert set(by_id) == {"generic", "bound"}
    assert by_id["generic"].status == "candidate"
    assert by_id["bound"].status == "confirmed"


def test_security_penalty_only_applies_to_matching_reward_contract():
    chain = ChainResult(
        chain="base",
        security=[
            SecuritySignal(
                provider="goplus",
                contract=TOKEN_A,
                chain="base",
                severity="critical",
                code="honeypot",
                detail="flagged",
            )
        ],
    )
    matching = Opportunity(
        id="matching",
        title="matching",
        chain="base",
        reward_contract=TOKEN_A,
        status="candidate",
        official_url="https://example.com/matching",
        risk_score=10,
    )
    unrelated = Opportunity(
        id="unrelated",
        title="unrelated",
        chain="base",
        reward_contract=TOKEN_B,
        status="candidate",
        official_url="https://example.com/unrelated",
        risk_score=10,
    )

    ranked = WalletScanner._rank_opportunities([matching, unrelated], [chain])
    by_id = {item.id: item for item in ranked}
    assert by_id["matching"].risk_score == 60
    assert by_id["unrelated"].risk_score == 40


@pytest.mark.asyncio
async def test_etherscan_logical_api_failure_is_raised(monkeypatch):
    monkeypatch.setattr(settings, "etherscan_api_key", "test-key")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": "0", "message": "NOTOK", "result": "Invalid API Key"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = EtherscanV2Provider(client)
        with pytest.raises(RuntimeError, match="Etherscan API failure"):
            await provider.discover_tokens("base", VALID)


@pytest.mark.asyncio
async def test_etherscan_paginates_until_distinct_token_limit(monkeypatch):
    monkeypatch.setattr(settings, "etherscan_api_key", "test-key")
    monkeypatch.setattr(settings, "wallet_hunter_max_tokens", 2)
    pages: list[str] = []

    def row(contract: str, symbol: str) -> dict[str, str]:
        return {
            "contractAddress": contract,
            "tokenDecimal": "18",
            "tokenSymbol": symbol,
            "tokenName": symbol,
        }

    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params["page"]
        pages.append(page)
        rows = [row(TOKEN_A, "A"), row(TOKEN_A, "A")]
        if page == "2":
            rows = [row(TOKEN_B, "B"), row(TOKEN_A, "A")]
        return httpx.Response(200, json={"status": "1", "message": "OK", "result": rows})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tokens = await EtherscanV2Provider(client).discover_tokens("base", VALID)

    assert {token.contract for token in tokens} == {TOKEN_A, TOKEN_B}
    assert pages == ["1", "2"]


@pytest.mark.asyncio
async def test_dexscreener_ignores_quote_token_price():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "pairs": [
                    {
                        "chainId": "base",
                        "baseToken": {"address": TOKEN_B},
                        "quoteToken": {"address": TOKEN_A},
                        "priceUsd": "123.45",
                        "liquidity": {"usd": 100000},
                    }
                ]
            },
        )

    token = TokenPosition(chain="base", contract=TOKEN_A, balance=2)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        enriched = await DexScreenerProvider(client).enrich(token)

    assert enriched.price_usd is None
    assert enriched.value_usd is None
