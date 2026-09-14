from __future__ import annotations

import asyncio

import httpx

from .config import CHAINS, settings
from .models import ChainResult, NativeBalance, Opportunity, WalletReport, WalletScanRequest
from .providers import (
    DexScreenerProvider,
    EtherscanV2Provider,
    GoPlusProvider,
    ManifestOpportunityProvider,
    OfficialEligibilityProvider,
    RpcClient,
)


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
            manifest = ManifestOpportunityProvider().load()
            scoped = self._scope_opportunities(manifest, chains, request.address)
            checker = OfficialEligibilityProvider(client)
            checked = await asyncio.gather(
                *(checker.check(opportunity, request.address) for opportunity in scoped)
            )

        opportunities = self._rank_opportunities(checked, results)
        warnings: list[str] = []
        if unknown:
            warnings.append(f"Unsupported chains ignored: {', '.join(unknown)}")
        if not settings.etherscan_api_key:
            warnings.append(
                "ETHERSCAN_API_KEY is not configured; ERC-20 discovery is limited to native balances."
            )
        warnings.append(
            "Wallet Hunter never signs or broadcasts transactions. Claimable status is confirmed only when a trusted official wallet-specific eligibility source positively confirms the scanned address."
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
    def _scope_opportunities(
        opportunities: list[Opportunity],
        chains: list[str],
        address: str,
    ) -> list[Opportunity]:
        selected = set(chains)
        normalized_address = address.lower()
        scoped: list[Opportunity] = []
        for opportunity in opportunities:
            if opportunity.chain not in selected:
                continue
            item = opportunity.model_copy(deep=True)
            source = item.eligibility_source
            trusted_source = source is not None and source.trusted
            wallet_bound = item.eligibility_address == normalized_address
            if item.status == "confirmed" and not (trusted_source and wallet_bound):
                item.status = "candidate"
                reason = "Static confirmation is insufficient; trusted official wallet verification is required"
                if reason not in item.risk_reasons:
                    item.risk_reasons.append(reason)
            scoped.append(item)
        return scoped

    @staticmethod
    def _rank_opportunities(
        opportunities: list[Opportunity],
        chain_results: list[ChainResult],
    ) -> list[Opportunity]:
        risk_by_contract: dict[tuple[str, str], int] = {}
        for chain_result in chain_results:
            for signal in chain_result.security:
                key = (chain_result.chain, signal.contract.lower())
                risk_by_contract[key] = min(
                    100,
                    risk_by_contract.get(key, 0) + SEVERITY_PENALTY[signal.severity],
                )

        for opportunity in opportunities:
            if opportunity.reward_contract:
                token_risk = risk_by_contract.get(
                    (opportunity.chain, opportunity.reward_contract.lower()),
                    0,
                )
                opportunity.risk_score = max(opportunity.risk_score, token_risk)
            if opportunity.estimated_value_usd is not None and opportunity.estimated_gas_usd is not None:
                opportunity.net_value_usd = opportunity.estimated_value_usd - opportunity.estimated_gas_usd
            if opportunity.status != "confirmed":
                opportunity.risk_reasons.append("Eligibility is not confirmed by an official source for this wallet")
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
