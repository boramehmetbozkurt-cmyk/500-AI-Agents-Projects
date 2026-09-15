from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from ops_commercial_metrics import summarize
from ops_dataset_ingest_benchmark import run_ingest_benchmark
from ops_external_benchmark import evaluate
from ops_production_probe import _safe_target
from ops_signal_calibration import calibrate


def test_external_benchmark_requires_real_external_metadata_for_claim() -> None:
    payload = {
        "evaluator": {
            "assessor": "Independent Lab",
            "evidence_uri": "evidence://report-1",
            "independent_external_validation": True,
            "third_party_baseline_comparison": True,
        },
        "cases": [
            {"case_id": "a", "scores": {"ORBYTHRA": 0.9, "RAG": 0.7}},
            {"case_id": "b", "scores": {"ORBYTHRA": 0.8, "RAG": 0.8}},
        ],
    }
    result = evaluate(payload)
    assert result["external_claim_ready"] is True
    assert result["systems"]["ORBYTHRA"]["win_share"] == pytest.approx(0.75)


def test_signal_calibration_metrics_and_boundary() -> None:
    payload = {
        "evaluator": {"independent_external_validation": False},
        "records": [
            {"record_id": "1", "signal_score": 0.9, "outcome": 1},
            {"record_id": "2", "signal_score": 0.2, "outcome": 0},
        ],
    }
    result = calibrate(payload, bins=5)
    assert result["metrics"]["brier_score"] == pytest.approx(0.025)
    assert result["external_claim_ready"] is False


def test_commercial_metrics_require_source_evidence_for_claim() -> None:
    now = datetime(2026, 9, 15, tzinfo=UTC)
    payload = {
        "as_of": now.isoformat(),
        "accounts": [
            {
                "account_id": "pilot-a",
                "started_at": (now - timedelta(days=60)).isoformat(),
                "last_active_at": (now - timedelta(days=1)).isoformat(),
                "mrr": 500,
                "usage_events": 40,
                "status": "active",
            }
        ],
    }
    result = summarize(payload)
    assert result["mrr"] == 500
    assert result["arr_run_rate"] == 6000
    assert result["retention_30d"] == 1.0
    assert result["claim_ready"] is False


def test_production_probe_rejects_insecure_remote_http() -> None:
    with pytest.raises(ValueError):
        _safe_target("http://example.com", "/health")
    url, target = _safe_target("http://127.0.0.1:8787", "/health")
    assert url == "http://127.0.0.1:8787/health"
    assert target == url


def test_real_importer_benchmark_uses_supplied_file(tmp_path) -> None:
    source = tmp_path / "authors.jsonl"
    rows = [
        {"id": "https://openalex.org/A1", "display_name": "Ada One"},
        {"id": "https://openalex.org/A2", "display_name": "Ada Two"},
    ]
    source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    result = run_ingest_benchmark(
        kind="openalex_authors",
        path=source,
        release_id="test-release",
    )
    assert result["real_input_file"] is True
    assert result["records_seen"] == 2
    assert result["entities_written"] == 2
    assert result["production_scale_claim"] is False
