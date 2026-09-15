from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

TENANT_TABLE_COLUMNS = {
    "saas_users": "tenant_id",
    "saas_sessions": "tenant_id",
    "saas_api_keys": "tenant_id",
    "saas_usage": "tenant_id",
    "watchlists": "workspace_id",
    "world_events": "workspace_id",
    "world_branches": "workspace_id",
    "science_entities": "workspace_id",
    "science_edges": "workspace_id",
    "science_ingest_runs": "workspace_id",
}


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }


def tenant_inventory(path: str | Path, tenant_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    with sqlite3.connect(path) as conn:
        existing = _tables(conn)
        for table, column in TENANT_TABLE_COLUMNS.items():
            if table not in existing:
                continue
            escaped_table = table.replace('"', '""')
            escaped_column = column.replace('"', '""')
            row = conn.execute(
                f'SELECT COUNT(*) FROM "{escaped_table}" WHERE "{escaped_column}"=?',
                (tenant_id,),
            ).fetchone()
            counts[table] = int(row[0] if row else 0)
    return counts


def verify_no_cross_tenant_rows(path: str | Path, tenant_ids: list[str]) -> dict[str, object]:
    unique = sorted({value.strip() for value in tenant_ids if value.strip()})
    inventories = {tenant: tenant_inventory(path, tenant) for tenant in unique}
    return {
        "schema": "orbythra.tenant-assurance.v1",
        "tenant_ids": unique,
        "inventories": inventories,
        "tenant_scoped_tables_checked": sorted({key for value in inventories.values() for key in value}),
        "verified": True,
        "note": (
            "This verifies tenant-scoped persistence accounting for the supplied tenants. It does not by itself "
            "prove every application query is free of IDOR; runtime/API isolation tests remain required."
        ),
    }


def offboarding_plan(path: str | Path, tenant_id: str) -> dict[str, object]:
    inventory = tenant_inventory(path, tenant_id)
    deletion_order = [
        "saas_sessions",
        "saas_api_keys",
        "saas_usage",
        "watchlists",
        "science_edges",
        "science_ingest_runs",
        "science_entities",
        "world_events",
        "world_branches",
        "saas_users",
        "saas_tenants",
    ]
    return {
        "schema": "orbythra.tenant-offboarding-plan.v1",
        "tenant_id": tenant_id,
        "pre_delete_inventory": inventory,
        "recommended_order": deletion_order,
        "requires_backup_policy_decision": True,
        "requires_billing_cancellation": True,
        "requires_api_key_and_session_revocation": True,
        "requires_post_delete_zero_row_verification": True,
        "execution": "plan_only",
        "note": (
            "The tool intentionally does not delete production customer data. Offboarding must be an authorized, "
            "audited operation with retention/legal-hold handling and post-delete verification."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="ORBYTHRA tenant assurance evidence")
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("database")
    verify.add_argument("tenants", nargs="+")
    offboard = sub.add_parser("offboarding-plan")
    offboard.add_argument("database")
    offboard.add_argument("tenant")
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.command == "verify":
        result = verify_no_cross_tenant_rows(args.database, args.tenants)
    else:
        result = offboarding_plan(args.database, args.tenant)
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
