# Wallet Hunter

Standalone, read-only EVM wallet intelligence service for finding and ranking **real-value claim/quest candidates** without ever handling a seed phrase or private key.

## What it does

`wallet address -> multichain scan -> token discovery -> USD/liquidity enrichment -> token security checks -> opportunity matching -> net-value/risk ranking -> optional read-only transaction simulation`

Supported EVM networks in v0.1:

- Ethereum
- Base
- Arbitrum One
- Optimism
- Polygon

## Safety boundary

Wallet Hunter is **read-only by default**. It does not store private keys, seed phrases, or sign/broadcast transactions. Claim actions are returned only as plans for a user-controlled wallet. Any future signing integration must require explicit wallet approval.

## Data adapters

- JSON-RPC: native balances and `eth_call` simulation
- Etherscan API v2: ERC-20 transfer history / token discovery when an API key is configured
- DexScreener: best-effort price and liquidity enrichment
- GoPlus: best-effort token-security signals
- Curated opportunity manifests: official claim/quest metadata and explicit eligibility status

No adapter is treated as ground truth by itself. A claim is labelled `confirmed` only when an official/allowlisted eligibility source confirms it. Otherwise the result is `candidate` or `unknown`.

## Quick start

```bash
cd wallet_hunter
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .[dev]
cp .env.example .env
uvicorn wallet_hunter.api:app --reload
```

Then:

```bash
curl -X POST http://127.0.0.1:8000/scan \
  -H 'content-type: application/json' \
  -d '{"address":"0x91825471DE3b732E418d18b06A9e0C0ba8735358","chains":["ethereum","base","arbitrum","optimism","polygon"]}'
```

## Result model

Every opportunity includes:

- chain
- asset / reward symbol when known
- status: `confirmed`, `candidate`, `unknown`, or `rejected`
- estimated USD value when verifiable
- estimated gas cost when available
- net estimated value
- liquidity signal
- security flags
- evidence/source URLs
- risk score and human-readable reasons

## Environment

See `.env.example`. For useful token-history discovery, configure `ETHERSCAN_API_KEY`. Public RPCs can be replaced with your own provider endpoints.

## Important

Adding a token contract to MetaMask does **not** create a balance. Wallet Hunter only reports real on-chain balances or explicitly verified claim opportunities. Unknown dust tokens and unsolicited airdrops are treated as hostile until proven otherwise.
