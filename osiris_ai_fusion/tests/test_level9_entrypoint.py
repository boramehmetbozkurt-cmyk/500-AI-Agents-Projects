from __future__ import annotations

from app_level9 import app


def test_level9_entrypoint_mounts_operator_and_enterprise_routes() -> None:
    schema_paths = set(app.openapi()["paths"])
    assert "/operator" in schema_paths
    assert "/operator/goals" in schema_paths
    assert "/operator/actions" in schema_paths
    assert "/enterprise/readiness" in schema_paths
    assert "/enterprise/moat" in schema_paths
    assert "/enterprise/fingerprint" in schema_paths
    assert "/enterprise/pilots" in schema_paths
    assert app.version == "1.4.0"
