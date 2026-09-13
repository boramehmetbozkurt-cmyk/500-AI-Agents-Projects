from __future__ import annotations

import httpx
from fastapi import FastAPI, HTTPException

from .config import CHAINS, settings
from .models import SimulationRequest, SimulationResult, WalletReport, WalletScanRequest
from .providers import RpcClient
from .scanner import WalletScanner


app = FastAPI(
    title="Wallet Hunter",
    version="0.1.0",
    description="Read-only multichain wallet intelligence and claim-opportunity ranking API",
)
scanner = WalletScanner()


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "ok": True,
        "version": "0.1.0",
        "mode": "read-only",
        "chains": sorted(CHAINS),
        "etherscan_token_discovery": bool(settings.etherscan_api_key),
    }


@app.post("/scan", response_model=WalletReport)
async def scan_wallet(request: WalletScanRequest) -> WalletReport:
    if not request.chains:
        raise HTTPException(status_code=400, detail="at least one chain is required")
    return await scanner.scan(request)


@app.post("/simulate", response_model=SimulationResult)
async def simulate(request: SimulationRequest) -> SimulationResult:
    if request.chain not in CHAINS:
        raise HTTPException(status_code=400, detail="unsupported chain")

    timeout = httpx.Timeout(settings.wallet_hunter_timeout)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        rpc = RpcClient(client)
        try:
            result = await rpc.simulate(
                request.chain,
                request.from_address,
                request.to,
                request.data,
                request.value_wei,
            )
            return SimulationResult(chain=request.chain, ok=True, result=result, broadcast=False)
        except Exception as exc:
            return SimulationResult(chain=request.chain, ok=False, error=str(exc), broadcast=False)
