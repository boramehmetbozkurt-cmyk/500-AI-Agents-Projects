from pathlib import Path


def test_public_demo_is_search_first_and_answer_producing() -> None:
    demo = Path(__file__).resolve().parents[2] / "orbythra_live_demo" / "index.html"
    text = demo.read_text(encoding="utf-8")

    required = [
        'id="searchForm"',
        'id="query"',
        'id="answer"',
        'id="sources"',
        'id="confidence"',
        'backendSearch(query)',
        'publicSearch(query)',
        'tr.wikipedia.org',
        'api.openalex.org',
        '/investigate',
    ]
    missing = [token for token in required if token not in text]
    assert not missing, f"Universal Search demo contract missing: {missing}"


def test_command_center_prioritizes_answer_before_technical_panels() -> None:
    ui = Path(__file__).resolve().parents[1] / "ui" / "index.html"
    text = ui.read_text(encoding="utf-8")

    answer_at = text.index("ORBYTHRA Answer")
    sources_at = text.index("Sources")
    plan_at = text.index("Search Plan")
    log_at = text.index("Technical Event Log")

    assert answer_at < sources_at < plan_at < log_at
    assert "ASK ORBYTHRA" in text
