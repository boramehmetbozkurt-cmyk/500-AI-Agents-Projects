from __future__ import annotations

import argparse
import asyncio
import json
import sys

from osiris_client import OsirisClient


async def run(base_url: str, timeout: float) -> int:
    try:
        async with OsirisClient(base_url=base_url, timeout=timeout, max_response_bytes=2_000_000) as client:
            probe = await client.passive_contract_probe()
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": f"{type(exc).__name__}: {exc}"}))
        return 1

    health = probe.get("health")
    stats = probe.get("stats")
    ok = isinstance(health, dict) and isinstance(stats, dict)
    summary = {
        "status": "ok" if ok else "failed",
        "base_url": probe.get("base_url"),
        "registered_tool_count": len(probe.get("registered_tools", [])),
        "health": health,
        "stats_keys": sorted(stats.keys()) if isinstance(stats, dict) else [],
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Passive live smoke test for OSIRIS public API")
    parser.add_argument("--base-url", default="https://osirisai.live")
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()
    return asyncio.run(run(args.base_url, args.timeout))


if __name__ == "__main__":
    sys.exit(main())
