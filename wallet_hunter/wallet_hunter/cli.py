from __future__ import annotations

import argparse
import asyncio
import json
from decimal import Decimal

from .hunter import WalletHunter


def _money(value: Decimal | None) -> str:
    return "?" if value is None else f"${value:,.2f}"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wallet-hunter")
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="Scan a public EVM wallet address")
    scan.add_argument("address")
    scan.add_argument("--opportunities", help="Path to a trusted opportunity registry JSON file")
    scan.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    scan.add_argument("--max-tokens", type=int, default=30)
    return parser


async def _run_scan(args: argparse.Namespace) -> int:
    hunter = WalletHunter(max_tokens_per_chain=args.max_tokens)
    report = await hunter.scan(args.address, registry_path=args.opportunities)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return 0

    print(f"Wallet Hunter v0.1 — {report.address}")
    print(f"Known portfolio value: {_money(report.total_known_value_usd)}")
    for chain in report.chains:
        print(f"\n[{chain.chain}] {chain.native_amount} {chain.native_symbol} ({_money(chain.native_value_usd)})")
        if chain.errors:
            for error in chain.errors:
                print(f"  ! {error}")
        for token in chain.tokens:
            print(
                f"  {token.symbol}: {token.amount} | value {_money(token.value_usd)} | "
                f"liquidity {_money(token.liquidity_usd)} | risk {token.risk_score}/100"
            )
            for warning in token.warnings:
                print(f"    - {warning}")

    if report.opportunities:
        print("\nOpportunities")
        for item in report.opportunities:
            print(
                f"  {item.name}: {item.status} | value {_money(item.estimated_value_usd)} | "
                f"risk {item.risk_score}/100"
            )
            print(f"    {item.source_url}")
            for note in item.notes:
                print(f"    - {note}")

    print("\nSafety")
    for warning in report.warnings:
        print(f"  - {warning}")
    return 0


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    if args.command == "scan":
        raise SystemExit(asyncio.run(_run_scan(args)))
    raise SystemExit(2)
