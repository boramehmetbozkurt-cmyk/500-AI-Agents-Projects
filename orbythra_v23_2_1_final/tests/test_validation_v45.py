from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient

from app.api import app

client = TestClient(app)


def _headers(role: str = "operator", workspace: str = "v45-validation") -> dict[str, str]:
    return {"X-API-Key": "test-secret", "X-Workspace-ID": workspace}


def _body(**overrides):
    base = {
        "suite": "independent-adversarial",
        "commit_sha": "a" * 40,
        "configuration_sha256": hashlib.sha256(b"config").hexdigest(),
        "result": "PASS",
        "total": 1000,
        "passed": 1000,
        "failed": 0,
        "artifact_sha256": hashlib.sha256(b"artifact").hexdigest(),
        "external_validator": "controlled-test-lab",
    }
    base.update(overrides)
    return base


def test_v45_evidence_chain_and_export_are_verifiable():
    workspace = "v45-chain"
    first = client.post("/v4.5/validation/evidence", json=_body(), headers=_headers(workspace=workspace))
    assert first.status_code == 200, first.text
    second = client.post("/v4.5/validation/evidence", json=_body(commit_sha="b" * 40), headers=_headers(workspace=workspace))
    assert second.status_code == 200, second.text
    a, b = first.json(), second.json()
    assert a["sequence"] == 1
    assert b["sequence"] == 2
    assert b["previous_sha256"] == a["evidence_sha256"]

    verified = client.get("/v4.5/validation/verify", headers=_headers("evaluator", workspace))
    assert verified.status_code == 200, verified.text
    assert verified.json()["valid"] is True
    assert verified.json()["entries"] == 2

    exported = client.get("/v4.5/validation/export", headers=_headers("evaluator", workspace))
    assert exported.status_code == 200, exported.text
    payload = exported.json()
    assert payload["schema"] == "orbythra.validation-evidence.v4.5"
    assert len(payload["bundle_sha256"]) == 64
    assert payload["verification"]["head_sha256"] == b["evidence_sha256"]


def test_v45_rejects_inconsistent_counts():
    response = client.post(
        "/v4.5/validation/evidence",
        json=_body(total=1000, passed=999, failed=0),
        headers=_headers(workspace="v45-bad-count"),
    )
    assert response.status_code == 422


def test_v45_rejects_false_pass():
    response = client.post(
        "/v4.5/validation/evidence",
        json=_body(result="PASS", total=1000, passed=999, failed=1),
        headers=_headers(workspace="v45-false-pass"),
    )
    assert response.status_code == 422


def test_v45_rejects_false_fail():
    response = client.post(
        "/v4.5/validation/evidence",
        json=_body(result="FAIL", total=1000, passed=1000, failed=0),
        headers=_headers(workspace="v45-false-fail"),
    )
    assert response.status_code == 422


def test_v45_empty_ledger_fails_closed():
    response = client.get("/v4.5/validation/verify", headers=_headers("evaluator", "v45-empty"))
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "validation_evidence_invalid"


def test_v45_workspace_isolation():
    client.post("/v4.5/validation/evidence", json=_body(), headers=_headers(workspace="v45-a"))
    other = client.get("/v4.5/validation/verify", headers=_headers("evaluator", "v45-b"))
    assert other.status_code == 409
