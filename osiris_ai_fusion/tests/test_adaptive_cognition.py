from __future__ import annotations

from adaptive_cognition import (
    CognitiveMemory,
    build_cognitive_plan,
    evaluate_report,
    refinement_directives,
)


def _report() -> dict:
    return {
        "bluf": "Evidence-backed answer with enough detail to explain the main result and uncertainty.",
        "claims": [
            {
                "text": "Supported claim",
                "kind": "observation",
                "confidence": 0.8,
                "evidence_ids": ["ev1"],
            }
        ],
        "historical_timeline": [
            {
                "date": "2024",
                "title": "Milestone",
                "summary": "A supported event.",
                "evidence_ids": ["ev1"],
            }
        ],
        "developed_ideas": [
            {
                "title": "Testable direction",
                "thesis": "Build a constrained experiment.",
                "next_experiment": "Run an A/B benchmark.",
                "risks": ["dataset bias"],
            }
        ],
        "map_markers": [{"lat": 38.42, "lon": 27.14, "label": "Izmir"}],
        "data_gaps": ["More independent sources would improve confidence."],
        "overall_confidence": 0.75,
    }


def _evidence() -> list[dict]:
    return [
        {
            "domain": "example.org",
            "providers": ["provider-a"],
            "evidence_ids": ["ev1"],
        },
        {
            "domain": "example.net",
            "providers": ["provider-b"],
            "evidence_ids": ["ev2"],
        },
    ]


def test_cognitive_memory_is_tenant_isolated(tmp_path) -> None:
    memory = CognitiveMemory(str(tmp_path / "memory.sqlite3"))
    evaluation = {"score": 0.88}
    memory.remember("Cupra Formentor engine history", _report(), evaluation, "tenant-a")

    assert memory.recall("Formentor engine history", "tenant-a")
    assert memory.recall("Formentor engine history", "tenant-b") == []


def test_cognitive_plan_is_bounded_and_multistep() -> None:
    plan = build_cognitive_plan(
        "Cupra Formentor tarihçesini analiz et ve haritada göster, sonra yeni ürün fikirleri geliştir",
        [{"summary": "previous engine research"}],
    )
    assert plan["complexity"] >= 4
    assert plan["memory_hits"] == 1
    assert plan["adaptation_policy"]["max_refinement_passes"] == 1
    assert plan["adaptation_policy"]["new_external_tool_calls_during_refinement"] == 0
    assert len(plan["objectives"]) >= 2


def test_self_evaluation_rewards_evidence_and_requested_outputs() -> None:
    result = evaluate_report(
        "Tarihçesini çıkar, haritada göster ve fikir geliştir",
        _report(),
        _evidence(),
    )
    assert 0.0 <= result["score"] <= 1.0
    assert result["metrics"]["evidence_coverage"] == 1.0
    assert result["metrics"]["timeline_quality"] > 0
    assert result["metrics"]["spatial_quality"] > 0
    assert result["metrics"]["idea_quality"] > 0


def test_weak_report_requests_bounded_refinement() -> None:
    result = evaluate_report(
        "Tarihçesini çıkar ve haritada göster",
        {
            "bluf": "Short answer.",
            "claims": [{"text": "uncited", "evidence_ids": []}],
            "historical_timeline": [],
            "map_markers": [],
            "developed_ideas": [],
            "overall_confidence": 0.9,
        },
        [],
    )
    assert result["refinement_required"] is True
    directives = refinement_directives(result)
    assert directives
    assert any("evidence" in item.lower() for item in directives)
