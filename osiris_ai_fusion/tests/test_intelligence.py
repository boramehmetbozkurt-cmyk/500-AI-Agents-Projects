from intelligence import METHODOLOGY_VERSION, score_world_state


def _snapshot():
    return {
        "workspace_id": "tenant_demo",
        "branch_id": "reality",
        "observed_at": 1_000_000,
        "valid_at": 1_000_000,
        "states": [
            {
                "truth_status": "verified",
                "effective": {
                    "evidence_ids": ["ev_1"],
                    "source_ids": ["src_1"],
                    "observed_at": 999_900,
                },
            },
            {
                "truth_status": "claimed",
                "effective": {
                    "evidence_ids": [],
                    "source_ids": ["src_2"],
                    "observed_at": 999_800,
                },
            },
        ],
    }


def test_intelligence_scores_are_bounded_and_explainable():
    graph = {
        "nodes": [{"entity_id": "a"}, {"entity_id": "b"}],
        "edges": [{"source": "a", "target": "b"}],
    }
    pulse = {
        "categories": [
            {
                "entity_type": "technology",
                "change_score": 3.0,
                "delta": 4,
                "unusual": True,
            }
        ]
    }
    result = score_world_state(_snapshot(), graph, pulse, now=1_000_000)

    assert result["methodology"] == METHODOLOGY_VERSION
    assert result["calibrated_forecast"] is False
    assert result["top_change_signals"][0]["entity_type"] == "technology"
    assert result["counts"] == {
        "states": 2,
        "nodes": 2,
        "edges": 1,
        "pulse_categories": 1,
    }
    for value in result["scores"].values():
        assert 0 <= value <= 100
    for value in result["components"].values():
        assert 0 <= value <= 100


def test_more_evidence_improves_decision_confidence():
    graph = {"nodes": [{"entity_id": "a"}], "edges": []}
    pulse = {"categories": []}
    weak = _snapshot()
    weak["states"][0]["truth_status"] = "belief_only"
    weak["states"][0]["effective"]["evidence_ids"] = []
    weak["states"][0]["effective"]["source_ids"] = []
    weak["states"][1]["truth_status"] = "belief_only"
    weak["states"][1]["effective"]["source_ids"] = []

    strong = _snapshot()
    strong["states"][1]["truth_status"] = "verified"
    strong["states"][1]["effective"]["evidence_ids"] = ["ev_2"]

    weak_result = score_world_state(weak, graph, pulse, now=1_000_000)
    strong_result = score_world_state(strong, graph, pulse, now=1_000_000)

    assert strong_result["scores"]["decision_confidence"] > weak_result["scores"]["decision_confidence"]
