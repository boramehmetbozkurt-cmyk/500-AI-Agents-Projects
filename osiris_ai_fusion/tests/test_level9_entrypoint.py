from __future__ import annotations

from app_level9 import app


def test_level9_entrypoint_mounts_operator_and_enterprise_routes() -> None:
    paths = {route.path for route in app.routes}
    assert "/operator" in paths
    assert "/operator/goals" in paths
    assert "/operator/actions" in paths
    assert "/enterprise/readiness" in paths
    assert "/enterprise/moat" in paths
    assert "/enterprise/fingerprint" in paths
    assert "/enterprise/pilots" in paths
    assert app.version == "1.4.0"
