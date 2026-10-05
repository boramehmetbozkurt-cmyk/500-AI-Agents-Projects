from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.store import STORE

client = TestClient(app)
ADMIN = {"X-API-Key": "test-secret", "X-Workspace-ID": "prod-test"}
VIEWER = {"X-API-Key": "other-secret", "X-Workspace-ID": "prod-test"}


def test_ready_reports_database_backend_and_rbac() -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["database_ready"] is True
    assert body["database_backend"] == "sqlite"
    assert "rbac" in body["capabilities"]
    assert "operational_metrics" in body["capabilities"]


def test_viewer_cannot_create_evidence_snapshot() -> None:
    response = client.post(
        "/v1/evidence/snapshots",
        json={"label": "forbidden", "evidence": [{"id": "e1", "support": 1.0, "authority": 1.0}]},
        headers=VIEWER,
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "insufficient_role"


def test_viewer_cannot_read_metrics() -> None:
    response = client.get("/v1/metrics", headers=VIEWER)
    assert response.status_code == 403


def test_admin_can_read_metrics() -> None:
    client.get("/health")
    response = client.get("/v1/metrics", headers=ADMIN)
    assert response.status_code == 200
    assert response.json()["request_total"] >= 1


def test_security_headers_are_present() -> None:
    response = client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["content-security-policy"].startswith("default-src")


def test_database_store_is_live() -> None:
    assert STORE.ping() is True
    assert STORE.backend == "sqlite"
