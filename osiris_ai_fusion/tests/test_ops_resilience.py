from __future__ import annotations

import sqlite3
from pathlib import Path

from ops_disaster_recovery import exercise
from ops_tenant_assurance import offboarding_plan, verify_no_cross_tenant_rows


def test_disaster_recovery_synthetic_exercise() -> None:
    result = exercise(rows=25)
    assert result["schema"] == "orbythra.disaster-recovery-evidence.v1"
    assert result["production_exercise"] is False
    assert result["integrity_verified"] is True
    assert result["source_table_counts"] == result["restored_table_counts"]
    assert result["rpo_claim_seconds"] is None


def test_tenant_assurance_inventory_and_offboarding_plan(tmp_path: Path) -> None:
    db = tmp_path / "tenant.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE saas_tenants(id TEXT PRIMARY KEY, name TEXT)")
        conn.execute("CREATE TABLE saas_users(id TEXT PRIMARY KEY, tenant_id TEXT, email TEXT)")
        conn.execute("CREATE TABLE saas_sessions(id TEXT PRIMARY KEY, tenant_id TEXT)")
        conn.execute("CREATE TABLE science_entities(workspace_id TEXT, canonical_key TEXT)")
        conn.execute("INSERT INTO saas_tenants VALUES ('tenant_a', 'A')")
        conn.execute("INSERT INTO saas_tenants VALUES ('tenant_b', 'B')")
        conn.execute("INSERT INTO saas_users VALUES ('u1', 'tenant_a', 'a@example.com')")
        conn.execute("INSERT INTO saas_users VALUES ('u2', 'tenant_b', 'b@example.com')")
        conn.execute("INSERT INTO saas_sessions VALUES ('s1', 'tenant_a')")
        conn.execute("INSERT INTO science_entities VALUES ('tenant_a', 'x')")
        conn.commit()

    evidence = verify_no_cross_tenant_rows(db, ["tenant_a", "tenant_b"])
    assert evidence["verified"] is True
    assert evidence["inventories"]["tenant_a"]["saas_users"] == 1
    assert evidence["inventories"]["tenant_b"]["saas_users"] == 1
    assert evidence["inventories"]["tenant_a"]["science_entities"] == 1

    plan = offboarding_plan(db, "tenant_a")
    assert plan["execution"] == "plan_only"
    assert plan["requires_api_key_and_session_revocation"] is True
    assert plan["requires_post_delete_zero_row_verification"] is True
