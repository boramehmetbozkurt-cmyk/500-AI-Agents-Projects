from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def _parse_time(value: Any) -> datetime:
    text = str(value or "").strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def summarize(payload: dict[str, Any]) -> dict[str, Any]:
    accounts = payload.get("accounts") or []
    if not isinstance(accounts, list):
        raise ValueError("accounts must be a list")
    as_of = _parse_time(payload.get("as_of") or datetime.now(UTC).isoformat())
    active_cutoff = as_of - timedelta(days=30)

    paying = 0
    mrr = 0.0
    active_30d = 0
    retained_30d = 0
    eligible_30d = 0
    total_usage = 0
    normalized: list[dict[str, Any]] = []
    for index, account in enumerate(accounts):
        if not isinstance(account, dict):
            raise ValueError(f"account {index} must be an object")
        account_id = str(account.get("account_id") or index)
        started = _parse_time(account["started_at"])
        last_active = _parse_time(account.get("last_active_at") or account["started_at"])
        monthly_mrr = float(account.get("mrr", 0.0))
        usage = int(account.get("usage_events", 0))
        status = str(account.get("status") or "active")
        if monthly_mrr < 0 or usage < 0:
            raise ValueError("mrr and usage_events cannot be negative")
        if status == "active" and monthly_mrr > 0:
            paying += 1
            mrr += monthly_mrr
        if last_active >= active_cutoff:
            active_30d += 1
        if started <= active_cutoff:
            eligible_30d += 1
            if last_active >= active_cutoff:
                retained_30d += 1
        total_usage += usage
        normalized.append(
            {
                "account_id": account_id,
                "started_at": started.isoformat().replace("+00:00", "Z"),
                "last_active_at": last_active.isoformat().replace("+00:00", "Z"),
                "status": status,
                "mrr": round(monthly_mrr, 2),
                "usage_events": usage,
            }
        )

    count = len(accounts)
    retention = retained_30d / eligible_30d if eligible_30d else None
    return {
        "schema": "orbythra.commercial-metrics.v1",
        "product": "ORBYTHRA",
        "as_of": as_of.isoformat().replace("+00:00", "Z"),
        "account_count": count,
        "paying_accounts": paying,
        "mrr": round(mrr, 2),
        "arr_run_rate": round(mrr * 12, 2),
        "active_accounts_30d": active_30d,
        "retention_30d": round(retention, 6) if retention is not None else None,
        "retention_30d_denominator": eligible_30d,
        "total_usage_events": total_usage,
        "mean_usage_per_account": round(total_usage / count, 3) if count else 0.0,
        "accounts": normalized,
        "source_system": payload.get("source_system"),
        "evidence_uri": payload.get("evidence_uri"),
        "claim_ready": bool(payload.get("source_system") and payload.get("evidence_uri")),
        "claim_boundary": (
            "Metrics are only as real as the supplied billing/usage export. A source-system identifier "
            "and reviewable evidence location are required before using these figures in buyer claims."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize real ORBYTHRA commercial usage exports")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = summarize(payload)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
