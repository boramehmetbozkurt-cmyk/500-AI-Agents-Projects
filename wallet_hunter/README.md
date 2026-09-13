# Wallet Hunter

Wallet Hunter is a standalone, read-only EVM wallet intelligence and airdrop-discovery project. It is intentionally separate from OSIRIS Fusion.

Its job is to take a public `0x...` wallet address and produce a ranked report of:

- native and token balances across supported EVM chains;
- token USD value and DEX liquidity where public market data exists;
- obvious spam / fake-airdrop indicators;
- curated, official claim or eligibility opportunities;
- estimated value, risk and next action;
- evidence URLs for every actionable opportunity.

## Security boundary

Wallet Hunter never asks for, stores or transmits a seed phrase or private key. It never signs transactions and never auto-approves token allowances. Claim execution remains user-authorized in the wallet. A future transaction-simulation module may prepare an unsigned transaction, but signing must stay in MetaMask or another user-controlled wallet.

The default mode is public, passive and read-only.

## v0.1 data path

```text
public wallet address
  -> address validation
  -> parallel Blockscout chain scan
  -> token balance normalization
  -> DEX Screener price/liquidity enrichment
  -> spam/risk scoring
  -> trusted opportunity registry
  -> eligibility check where an official address API exists
  -> ranked JSON report
```

Supported chain profiles in v0.1:

- Ethereum
- Base
- Arbitrum One
- Optimism
- Polygon

Blockscout exposes address and token-balance APIs for EVM explorers, and DEX Screener exposes token-pair market data. The implementation is defensive: unavailable providers do not turn into fabricated balances or fabricated airdrop eligibility.

## Install

```bash
cd wallet_hunter
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e .
```

## Run

```bash
wallet-hunter scan 0x91825471DE3b732E418d18b06A9e0C0ba8735358
```

JSON output:

```bash
wallet-hunter scan 0x91825471DE3b732E418d18b06A9e0C0ba8735358 --json
```

Load an admin-curated opportunity registry:

```bash
wallet-hunter scan 0x91825471DE3b732E418d18b06A9e0C0ba8735358 \
  --opportunities opportunities.example.json
```

## Opportunity registry

There is no universal on-chain standard for airdrop eligibility. Wallet Hunter therefore does **not** guess. A claim opportunity is accepted only from an admin-curated JSON manifest containing an official HTTPS source and, optionally, an official address-eligibility endpoint.

If an opportunity cannot be programmatically verified, its status is `manual_check`, not `eligible`.

See `opportunities.example.json` for the manifest contract.

## What v0.1 solves

The first version solves the failure mode we found during the OSIRIS test: research results are not enough. Wallet Hunter creates a dedicated pipeline for `wallet -> balances -> value -> liquidity -> risk -> claim opportunity -> evidence`.

The next production milestones are transaction simulation, allowance analysis, gas/net-value calculation, WalletConnect handoff and a continuously maintained official opportunity feed.