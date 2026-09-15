"""Cover the deep-research ablation benchmark, including what it refuses to claim."""

from __future__ import annotations

from pathlib import Path

import pytest

from config import get_settings
from ops_deep_research_benchmark import run_benchmark

CASES = Path(__file__).resolve().parents[1] / "benchmarks" / "deep_research_cases.json"


@pytest.fixture(autouse=True)
def deterministic_planner(monkeypatch):
    monkeypatch.setenv("AI_PLANNER_ENABLED", "false")
    monkeypatch.setenv("SUBQUERY_PLANNING_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def result():
    return run_benchmark(CASES)


def test_the_result_declares_what_it_is_not(result):
    # A benchmark that oversells is worse than no benchmark, so every limit the
    # harness knows about is a machine-readable field rather than prose alone.
    assert result["schema"] == "orbythra.deep-research-benchmark-result.v1"
    assert result["benchmark_kind"] == "synthetic_offline_pipeline_ablation"
    assert result["independent_external_validation"] is False
    assert result["third_party_baseline_comparison"] is False
    assert result["models_recall_from_decomposition"] is False
    assert result["production_measurement"] is False
    assert result["network_required"] is False


def test_every_case_runs_all_three_variants(result):
    assert result["cases"]
    for case in result["cases"]:
        assert set(case["variants"]) == {"baseline_raw", "normalized_only", "orbythra_full"}


def test_normalization_is_what_removes_duplicate_sources(result):
    # The corpus carries one document under three URL spellings, so a pipeline
    # without normalization must show duplicates and one with it must not.
    assert result["overall"]["baseline_raw"]["mean_duplicate_rate"] > 0
    assert result["overall"]["normalized_only"]["mean_duplicate_rate"] == 0.0
    assert result["overall"]["orbythra_full"]["mean_duplicate_rate"] == 0.0


def test_deduplication_never_loses_a_distinct_source(result):
    for case in result["cases"]:
        baseline = case["variants"]["baseline_raw"]["distinct_sources"]
        normalized = case["variants"]["normalized_only"]["distinct_sources"]
        assert normalized == baseline


def test_recursion_answers_more_questions_and_the_cost_is_reported(result):
    overall = result["overall"]
    assert (
        overall["orbythra_full"]["total_questions_answered"]
        > overall["normalized_only"]["total_questions_answered"]
    )
    # The extra calls are the price; reporting one without the other would be
    # presenting a benefit with its cost hidden.
    assert (
        overall["orbythra_full"]["total_tool_calls"]
        > overall["normalized_only"]["total_tool_calls"]
    )


def test_subtopic_coverage_is_reported_as_a_non_result(result):
    # The synthetic federation applies no ranking and no truncation, which is the
    # mechanism by which decomposition would improve recall. Coverage is therefore
    # expected to be flat, and the benchmark shows that rather than hiding it.
    coverages = {
        name: result["overall"][name]["mean_subtopic_coverage"]
        for name in ("baseline_raw", "normalized_only", "orbythra_full")
    }
    assert len(set(coverages.values())) == 1


def test_the_benchmark_is_reproducible(result):
    assert run_benchmark(CASES) == result


def test_an_empty_case_file_produces_an_empty_result(tmp_path):
    empty = tmp_path / "cases.json"
    empty.write_text('{"schema": "x", "cases": []}', encoding="utf-8")
    report = run_benchmark(empty)
    assert report["cases"] == []
    assert report["overall"]["baseline_raw"]["mean_duplicate_rate"] == 0.0
