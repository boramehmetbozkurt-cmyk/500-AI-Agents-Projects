from __future__ import annotations

import app.unified_answer as unified


def test_supported_query_language_detection() -> None:
    cases = {
        "What is Bitcoin?": "en",
        "BTC nedir?": "tr",
        "Was ist Bitcoin?": "de",
        "Qu'est-ce que Bitcoin ?": "fr",
        "¿Qué es Bitcoin?": "es",
        "Che cos'è Bitcoin?": "it",
        "ما هو البيتكوين؟": "ar",
    }
    for query, expected in cases.items():
        assert unified._detect_language(query) == expected


def test_generator_prompt_requests_detected_language(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class _Adapter:
        def __init__(self, timeout: int = 25) -> None:
            pass

        def generate(self, *, model_id: str, prompt: str):
            captured["prompt"] = prompt
            return {"output": "Bitcoin ist ...", "confidence": 0.9}

    class _State:
        llm_provider_configured = True

    monkeypatch.setattr(unified, "GovernedHttpModelAdapter", _Adapter)
    monkeypatch.setattr(unified, "provider_status", lambda: _State())
    answer, confidence, generator, warnings = unified._generate_answer(
        query="Was ist Bitcoin?", model_id="default", sources=[], texts={}, response_language="de"
    )
    assert "Reply in German" in captured["prompt"]
    assert answer == "Bitcoin ist ..."
    assert confidence == 0.9
    assert generator == "governed_llm_provider"
    assert warnings == []