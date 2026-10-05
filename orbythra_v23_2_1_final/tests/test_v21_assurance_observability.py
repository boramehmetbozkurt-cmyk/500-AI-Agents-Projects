from __future__ import annotations

import time
import uuid

from fastapi.testclient import TestClient

from app.api import app
from app.telemetry import OTEL

HEADERS = {"X-API-Key": "test-secret", "X-Workspace-ID": "v21-test"}


def _dataset_and_prompt(client: TestClient) -> tuple[str, str]:
    suffix = uuid.uuid4().hex[:8]
    dataset = client.post(
        "/v21/assurance/datasets",
        headers=HEADERS,
        json={"name": f"golden-{suffix}", "description": "V21 deterministic golden dataset"},
    )
    assert dataset.status_code == 200, dataset.text
    dataset_id = dataset.json()["dataset_id"]

    version = client.post(
        f"/v21/assurance/datasets/{dataset_id}/versions",
        headers=HEADERS,
        json={
            "label": "golden",
            "source_refs": ["internal:test-fixture"],
            "examples": [
                {"input": {"question": "2+2"}, "expected_output": "4", "metadata": {"domain": "math"}},
                {
                    "input": {"question": "capital of France"},
                    "expected_output": "Paris",
                    "metadata": {"domain": "qa"},
                },
            ],
        },
    )
    assert version.status_code == 200, version.text

    prompt = client.post(
        "/v21/assurance/prompts",
        headers=HEADERS,
        json={
            "name": f"answer-{suffix}",
            "template": "Answer only with the verified answer: {{question}}",
            "model_id": "test-model",
            "parameters": {"temperature": 0},
            "tags": ["golden", "v21"],
        },
    )
    assert prompt.status_code == 200, prompt.text
    return version.json()["version_id"], prompt.json()["version_id"]


def _experiment(
    client: TestClient,
    dataset_version_id: str,
    prompt_version_id: str,
    name: str,
    scores: list[float],
) -> tuple[str, dict]:
    created = client.post(
        "/v21/assurance/experiments",
        headers=HEADERS,
        json={
            "name": name,
            "dataset_version_id": dataset_version_id,
            "prompt_version_id": prompt_version_id,
            "model_id": "test-model",
            "metadata": {"suite": "v21-regression"},
        },
    )
    assert created.status_code == 200, created.text
    experiment_id = created.json()["experiment_id"]

    submitted = client.post(
        f"/v21/assurance/experiments/{experiment_id}/results",
        headers=HEADERS,
        json={
            "seal_after_submit": True,
            "items": [
                {
                    "example_index": index,
                    "output": {"answer": "fixture"},
                    "scores": {"quality": score, "faithfulness": score},
                    "latency_ms": 10.0 + index,
                    "input_tokens": 10,
                    "output_tokens": 2,
                    "cost_usd": 0.001,
                }
                for index, score in enumerate(scores)
            ],
        },
    )
    assert submitted.status_code == 200, submitted.text
    return experiment_id, submitted.json()


def test_v21_versioned_dataset_prompt_and_experiment_comparison() -> None:
    client = TestClient(app)
    dataset_version_id, prompt_version_id = _dataset_and_prompt(client)

    frozen_dataset = client.get(f"/v21/assurance/datasets/versions/{dataset_version_id}", headers=HEADERS)
    assert frozen_dataset.status_code == 200, frozen_dataset.text
    assert frozen_dataset.json()["example_count"] == 2
    assert frozen_dataset.json()["examples"][0]["expected_output"] == "4"

    frozen_prompt = client.get(f"/v21/assurance/prompts/{prompt_version_id}", headers=HEADERS)
    assert frozen_prompt.status_code == 200, frozen_prompt.text
    assert frozen_prompt.json()["template"].startswith("Answer only")
    assert frozen_prompt.json()["parameters"]["temperature"] == 0

    baseline_id, baseline = _experiment(
        client, dataset_version_id, prompt_version_id, "baseline", [0.70, 0.80]
    )
    candidate_id, candidate = _experiment(
        client, dataset_version_id, prompt_version_id, "candidate", [0.90, 0.95]
    )

    assert baseline["aggregate_scores"]["quality"] == 0.75
    assert candidate["aggregate_scores"]["quality"] == 0.925
    assert baseline["status"] == "SEALED"
    assert candidate["status"] == "SEALED"

    compared = client.post(
        "/v21/assurance/experiments/compare",
        headers=HEADERS,
        json={
            "baseline_experiment_id": baseline_id,
            "candidate_experiment_id": candidate_id,
            "primary_metric": "quality",
            "minimum_improvement": 0.10,
        },
    )
    assert compared.status_code == 200, compared.text
    payload = compared.json()
    assert payload["passed"] is True
    assert payload["delta"] == 0.175
    assert len(payload["comparison_sha256"]) == 64


def test_v21_rejects_result_index_outside_frozen_dataset() -> None:
    client = TestClient(app)
    dataset_version_id, prompt_version_id = _dataset_and_prompt(client)
    created = client.post(
        "/v21/assurance/experiments",
        headers=HEADERS,
        json={
            "name": "out-of-range-" + uuid.uuid4().hex[:8],
            "dataset_version_id": dataset_version_id,
            "prompt_version_id": prompt_version_id,
            "model_id": "test-model",
            "metadata": {},
        },
    )
    assert created.status_code == 200, created.text
    experiment_id = created.json()["experiment_id"]
    rejected = client.post(
        f"/v21/assurance/experiments/{experiment_id}/results",
        headers=HEADERS,
        json={
            "items": [{
                "example_index": 2,
                "output": "invalid-index",
                "scores": {"quality": 1.0},
            }]
        },
    )
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["detail"] == "experiment_example_index_out_of_range"


def test_v21_trace_binds_evidence_policy_and_receipt_hashes() -> None:
    client = TestClient(app)
    trace_id = "1" * 32
    span_id = "2" * 16
    started = time.time_ns()

    recorded = client.post(
        "/v21/assurance/traces/spans",
        headers=HEADERS,
        json={
            "trace_id": trace_id,
            "span_id": span_id,
            "name": "model.assurance",
            "kind": "INTERNAL",
            "start_time_unix_nano": started,
            "end_time_unix_nano": started + 5_000_000,
            "status": "OK",
            "attributes": {
                "openinference.span.kind": "LLM",
                "gen_ai.request.model": "test-model",
            },
            "evidence_manifest_sha256": "a" * 64,
            "policy_decision_sha256": "b" * 64,
            "outcome_receipt_sha256": "c" * 64,
        },
    )
    assert recorded.status_code == 200, recorded.text
    assert len(recorded.json()["lineage_sha256"]) == 64

    lineage = client.get(
        f"/v21/assurance/traces/{trace_id}/lineage",
        headers=HEADERS,
    )
    assert lineage.status_code == 200, lineage.text
    payload = lineage.json()
    assert payload["span_count"] >= 1
    assert payload["bound_span_count"] >= 1
    assert payload["cryptographic_chain_complete"] is True
    assert len(payload["trace_sha256"]) == 64


def test_v21_w3c_trace_context_and_openapi_readiness() -> None:
    client = TestClient(app)
    incoming = "00-" + ("3" * 32) + "-" + ("4" * 16) + "-01"
    context = OTEL.begin(incoming)
    assert context.trace_id == "3" * 32
    assert context.parent_span_id == "4" * 16
    assert context.span_id != "4" * 16

    response = client.get("/health", headers={"traceparent": incoming})
    assert response.status_code == 200
    returned = response.headers["traceparent"]
    assert returned.startswith("00-" + ("3" * 32) + "-")
    assert returned.endswith("-01")

    readiness = client.get("/v21/assurance/readiness", headers=HEADERS)
    assert readiness.status_code == 200, readiness.text
    ready = readiness.json()
    assert ready["versioned_datasets"] is True
    assert ready["immutable_prompt_versions"] is True
    assert ready["frozen_experiment_inputs"] is True
    assert ready["trace_evidence_policy_receipt_binding"] is True
    assert ready["live_agi_claim"] is False

    paths = app.openapi()["paths"]
    assert "/v21/assurance/datasets" in paths
    assert "/v21/assurance/prompts" in paths
    assert "/v21/assurance/datasets/versions/{version_id}" in paths
    assert "/v21/assurance/prompts/{version_id}" in paths
    assert "/v21/assurance/experiments" in paths
    assert "/v21/assurance/traces/spans" in paths
