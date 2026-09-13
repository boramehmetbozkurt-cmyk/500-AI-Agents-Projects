from __future__ import annotations

import asyncio

import httpx

from .config import CHAINS, settings
from .models import ChainResult, NativeBalance, Opportunity, WalletReport, WalletScanRequest
from .providers import DexScreenerProvider, EtherscanV2Provider, GoPlusProvider, ManifestOpportunityProvider, RpcClient


SEVERITY_PENALTY = {
    "info": 0,
    "low": 5,
    "medium": 15,
    "high": 30,
    "critical": 60,
}


class WalletScanner:
    async def scan(self, request: WalletScanRequest) -> WalletReport:
        chains = [c for c in request.chains if c in CHAINS]
        unknown = sorted(set(request.chains) - set(chains))

        timeout = httpx.Timeout(settings.wallet_hunter_timeout)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            results = await asyncio.gather(
                *(self._scan_chain(client, chain, request.address) for chain in chains)
            )

        opportunities = self._rank_opportunities(ManifestOpportunityProvider().load(), results)
        warnings: list[str] = []
        if unknown:
            warnings.append(f"Unsupported chains ignored: {', '.join(unknown)}")
        if not settings.etherscan_api_key:
            warnings.append(
                "ETHERSCAN_API_KEY is not configured; ERC-20 discovery is limited to native balances."
            )
        warnings.append(
            "Wallet Hunter never signs or broadcasts transactions. Claimable status must be confirmed by an official eligibility source."
        )
        return WalletReport(
            address=request.address,
            chains=results,
            opportunities=opportunities,
            warnings=warnings,
        )

    async def _scan_chain(
        self,
        client: httpx.AsyncClient,
        chain: str,
        address: str,
    ) -> ChainResult:
        rpc = RpcClient(client)
        etherscan = EtherscanV2Provider(client)
        dexscreener = DexScreenerProvider(client)
        goplus = GoPlusProvider(client)
        result = ChainResult(chain=chain)

        try:
            native = await rpc.native_balance(chain, address)
            result.native = NativeBalance(
                chain=chain,
                symbol=CHAINS[chain].native_symbol,
                balance=native,
                source="json-rpc:eth_getBalance",
            )
        except Exception as exc:
            result.errors.append(f"native balance: {exc}")

        try:
            tokens = await etherscan.discover_tokens(chain, address)
        except Exception as exc:
            tokens = []
            result.errors.append(f"token discovery: {exc}")

        for token in tokens:
            decimals = token.decimals if token.decimals is not None else 18
            try:
                raw, balance = await rpc.erc20_balance(chain, token.contract, address, decimals)
                token.raw_balance = raw
                token.balance = balance
                token.source.append("json-rpc:balanceOf")
            except Exception as exc:
                result.errors.append(f"{token.contract} balanceOf: {exc}")
                continue

            if not token.raw_balance:
                continue

            await dexscreener.enrich(token)
            result.tokens.append(token)
            try:
                result.security.extend(await goplus.check(token))
            except Exception as exc:
                result.errors.append(f"{token.contract} security: {exc}")

        result.tokens.sort(key=lambda t: (t.value_usd or 0.0, t.liquidity_usd or 0.0), reverse=True)
        return result

    @staticmethod
    def _rank_opportunities(
        opportunities: list[Opportunity],
        chain_results: list[ChainResult],
    ) -> list[Opportunity]:
        risk_by_chain: dict[str, int] = {}
        for chain_result in chain_results:
            penalty = sum(SEVERITY_PENALTY[s.severity] for s in chain_result.security)
            risk_by_chain[chain_result.chain] = min(100, penalty)

        for opportunity in opportunities:
            opportunity.risk_score = max(opportunity.risk_score, risk_by_chain.get(opportunity.chain, 0))
            if opportunity.estimated_value_usd is not None and opportunity.estimated_gas_usd is not None:
                opportunity.net_value_usd = opportunity.estimated_value_usd - opportunity.estimated_gas_usd
            if opportunity.status != "confirmed":
                opportunity.risk_reasons.append("Eligibility is not confirmed by an official source")
                opportunity.risk_score = max(opportunity.risk_score, 40)
            if opportunity.net_value_usd is not None and opportunity.net_value_usd <= 0:
                opportunity.risk_reasons.append("Estimated gas cost is greater than or equal to reward value")
                opportunity.risk_score = max(opportunity.risk_score, 70)

        return sorted(
            opportunities,
            key=lambda o: (
                o.status == "confirmed",
                o.net_value_usd if o.net_value_usd is not None else -1.0,
                -o.risk_score,
            ),
            reverse=True,
        )
