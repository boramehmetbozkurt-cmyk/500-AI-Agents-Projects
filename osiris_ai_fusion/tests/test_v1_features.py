from pathlib import Path

from config import get_settings
from correlation import correlate_evidence
from source_policy import enforce_source_policy
from store import FusionStore


def test_commercial_policy_blocks_unlicensed_opensky(monkeypatch):
    monkeypatch.setenv("COMMERCIAL_MODE", "true")
    monkeypatch.setenv("STRICT_COMMERCIAL_SOURCES", "true")
    monkeypatch.delenv("LICENSED_PROVIDERS", raising=False)
    get_settings.cache_clear()
    allowed, warnings = enforce_source_policy(["earthquakes", "flights"])
    assert "earthquakes" in allowed
    assert "flights" not in allowed
    assert any("BLOCKED flights" in warning for warning in warnings)
    get_settings.cache_clear()


def test_commercial_policy_allows_licensed_opensky(monkeypatch):
    monkeypatch.setenv("COMMERCIAL_MODE", "true")
    monkeypatch.setenv("LICENSED_PROVIDERS", "opensky")
    get_settings.cache_clear()
    allowed, _ = enforce_source_policy(["flights"])
    assert allowed == ["flights"]
    get_settings.cache_clear()


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
