import json
from pathlib import Path

from capabilities import capability_catalog
from config import get_settings
from correlation import correlate_evidence
from planner import deterministic_tools
from providers import provider_catalog, route_providers
from source_policy import enforce_source_policy
from store import FusionStore


def _reset_settings() -> None:
    get_settings.cache_clear()


def test_commercial_policy_blocks_unlicensed_opensky(monkeypatch):
    monkeypatch.setenv("COMMERCIAL_MODE", "true")
    monkeypatch.setenv("STRICT_COMMERCIAL_SOURCES", "true")
    monkeypatch.delenv("LICENSED_PROVIDERS", raising=False)
    _reset_settings()
    allowed, warnings = enforce_source_policy(["earthquakes", "flights"])
    assert "earthquakes" in allowed
    assert "flights" not in allowed
    assert any("BLOCKED flights" in warning for warning in warnings)
    _reset_settings()


def test_commercial_policy_allows_licensed_opensky(monkeypatch):
    monkeypatch.setenv("COMMERCIAL_MODE", "true")
    monkeypatch.setenv("LICENSED_PROVIDERS", "opensky")
    _reset_settings()
    allowed, _ = enforce_source_policy(["flights"])
    assert allowed == ["flights"]
    _reset_settings()


def test_commercial_policy_fails_closed_for_unapproved_federation(monkeypatch):
    monkeypatch.setenv("COMMERCIAL_MODE", "true")
    monkeypatch.setenv("STRICT_COMMERCIAL_SOURCES", "true")
    monkeypatch.delenv("LICENSED_PROVIDERS", raising=False)
    _reset_settings()
    allowed, warnings = enforce_source_policy(["provider_federation"])
    assert allowed == []
    assert any("provider_registry" in warning for warning in warnings)
    _reset_settings()


def test_geo_temporal_correlation_uses_evidence_ids():
    evidence = {
        "earthquakes": {
            "ok": True,
            "evidence_id": "ev_eq",
            "data": {
                "events": [
                    {
                        "lat": 38.42,
                        "lon": 27.14,
                        "timestamp": "2026-09-12T00:00:00+00:00",
                        "title": "earthquake",
                    }
                ]
            },
        },
        "fires": {
            "ok": True,
            "evidence_id": "ev_fire",
            "data": {
                "items": [
                    {
                        "latitude": 38.50,
                        "longitude": 27.20,
                        "timestamp": "2026-09-12T01:00:00+00:00",
                        "name": "fire",
                    }
                ]
            },
        },
    }
    candidates, markers = correlate_evidence(evidence)
    assert candidates
    assert {"ev_eq", "ev_fire"}.issubset(set(candidates[0].evidence_ids))
    assert len(markers) == 2


def test_store_cases_investigations_watchlists_and_alerts(tmp_path):
    store = FusionStore(str(tmp_path / "fusion.sqlite3"))
    case = store.create_case("Ege daily brief")
    assert case["status"] == "open"

    investigation_id = store.start_investigation(
        "İzmir son 24 saat",
        case_id=case["id"],
    )
    store.finish_investigation(investigation_id, {"report": {"bluf": "ok"}})
    investigations = store.list_investigations()
    assert investigations[0]["status"] == "completed"
    assert investigations[0]["result_digest"]

    watchlist = store.create_watchlist(
        {
            "name": "Ege watch",
            "query": "Ege olağandışı olaylar",
            "scope": {"region": "Ege"},
            "allowed_tools": ["earthquakes", "fires"],
            "cadence_seconds": 3600,
            "min_confidence": 0.6,
            "enabled": True,
        }
    )
    alert = store.create_alert(watchlist, "Yeni değişiklik", {"x": 1})
    assert alert is not None
    assert store.create_alert(watchlist, "Aynı sonuç", {"x": 1}) is None
    assert store.acknowledge_alert(alert["id"]) is True
    assert store.list_alerts()[0]["acknowledged"] is True


def test_production_ui_files_exist_and_stream_real_backend():
    root = Path(__file__).resolve().parents[1]
    html = (root / "ui" / "index.html").read_text(encoding="utf-8")
    js = (root / "ui" / "assets" / "app.js").read_text(encoding="utf-8")
    css = root / "ui" / "assets" / "styles.css"
    assert "OSIRIS FUSION" in html
    assert 'fetch("/investigate/stream"' in js
    assert "sessionStorage" in js
    assert css.exists()


def test_sports_is_provider_domain_not_special_autonomous_tool(monkeypatch):
    monkeypatch.delenv("FUSION_SPORTS_URL", raising=False)
    monkeypatch.delenv("FUSION_WEB_SEARCH_URL", raising=False)
    _reset_settings()
    tools = deterministic_tools("Bugünkü Dortmund maç skorunu tahmin et")
    assert tools == ["provider_federation"]
    assert "sports_research" not in tools
    assert "direct_reasoning" not in tools
    _reset_settings()


def test_configured_sports_provider_still_uses_federation(monkeypatch):
    monkeypatch.setenv("FUSION_SPORTS_URL", "https://example.invalid/sports")
    monkeypatch.delenv("FUSION_WEB_SEARCH_URL", raising=False)
    _reset_settings()
    tools = deterministic_tools("Bugünkü Dortmund maç skorunu tahmin et")
    routed = [provider.provider_id for provider in route_providers("Bugünkü Dortmund maçı")]
    assert tools == ["provider_federation"]
    assert "sports" in routed
    assert "sports_research" not in tools
    _reset_settings()


def test_science_query_routes_to_multiple_live_providers(monkeypatch):
    monkeypatch.delenv("FUSION_SCIENCE_URL", raising=False)
    monkeypatch.delenv("FUSION_WEB_SEARCH_URL", raising=False)
    monkeypatch.setenv("FUSION_PROVIDER_FANOUT", "3")
    routed = [
        provider.provider_id
        for provider in route_providers("machine learning research paper")
    ]
    assert "openalex" in routed
    assert "crossref" in routed
    assert deterministic_tools("machine learning research paper") == [
        "provider_federation"
    ]


def test_provider_manifest_can_add_multiple_providers(monkeypatch, tmp_path):
    manifest = [
        {
            "provider_id": "finance_alpha",
            "domains": ["finance"],
            "description": "Alpha finance",
            "transport": "get_json",
            "url": "https://example.invalid/alpha",
            "query_param": "q",
            "keywords": ["hisse"],
            "priority": 99,
        },
        {
            "provider_id": "finance_beta",
            "domains": ["finance"],
            "description": "Beta finance",
            "transport": "get_json",
            "url": "https://example.invalid/beta",
            "query_param": "q",
            "keywords": ["hisse"],
            "priority": 98,
        },
    ]
    (tmp_path / "finance.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv("FUSION_PROVIDER_DIR", str(tmp_path))
    monkeypatch.setenv("FUSION_PROVIDER_FANOUT", "3")
    routed = [provider.provider_id for provider in route_providers("Tesla hisse araştır")]
    assert "finance_alpha" in routed
    assert "finance_beta" in routed


def test_general_web_is_fallback_not_central_router(monkeypatch):
    monkeypatch.setenv("FUSION_WEB_SEARCH_URL", "https://example.invalid/search")
    monkeypatch.delenv("FUSION_NEWS_URL", raising=False)
    query = "Bugün Zorblax-99 olayı gerçekleşti mi?"
    routed = [provider.provider_id for provider in route_providers(query)]
    assert routed == ["general_web"]
    assert deterministic_tools(query) == ["provider_federation"]


def test_generic_fresh_finance_query_uses_federation(monkeypatch):
    monkeypatch.setenv("FUSION_WEB_SEARCH_URL", "https://example.invalid/search")
    monkeypatch.delenv("FUSION_FINANCE_URL", raising=False)
    _reset_settings()
    tools = deterministic_tools("Apple'ın bugünkü fiyatı nedir?")
    assert tools == ["provider_federation"]
    assert "direct_reasoning" not in tools
    _reset_settings()


def test_non_fresh_writing_uses_direct_reasoning(monkeypatch):
    monkeypatch.delenv("FUSION_WEB_SEARCH_URL", raising=False)
    _reset_settings()
    assert deterministic_tools("Bana kısa bir slogan yaz") == ["direct_reasoning"]
    _reset_settings()


def test_calculation_uses_calculator(monkeypatch):
    monkeypatch.delenv("FUSION_WEB_SEARCH_URL", raising=False)
    _reset_settings()
    assert deterministic_tools("hesapla 12 * (3 + 2)") == ["calculator"]
    _reset_settings()


def test_capability_catalog_exposes_federation_as_ready(monkeypatch):
    monkeypatch.delenv("FUSION_SPORTS_URL", raising=False)
    _reset_settings()
    rows = {row["name"]: row for row in capability_catalog()}
    assert rows["provider_federation"]["ready"] is True
    assert rows["provider_federation"]["auto_execute"] is True
    assert rows["sports_research"]["auto_execute"] is False
    _reset_settings()


def test_provider_catalog_has_multiple_real_live_domains(monkeypatch):
    monkeypatch.delenv("FUSION_FINANCE_URL", raising=False)
    rows = {row["provider_id"]: row for row in provider_catalog()}
    assert rows["openalex"]["ready"] is True
    assert rows["crossref"]["ready"] is True
    assert rows["wikipedia_tr"]["ready"] is True
    assert rows["osm_nominatim"]["ready"] is True
    assert rows["hn_algolia"]["ready"] is True
    assert rows["finance"]["ready"] is False
