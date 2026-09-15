import base64

import pytest

import cognitive_runtime
from cognitive_runtime import build_secure_capsule, enrich_research_context


def test_secure_capsule_reports_integrity_without_key(monkeypatch) -> None:
    monkeypatch.delenv("ORBYTHRA_AES256_KEY_B64", raising=False)
    result = build_secure_capsule({"query": "test", "value": 7})
    assert result["enabled"] is False
    assert result["algorithm"] == "AES-256-GCM"
    assert len(result["integrity_sha256"]) == 64
    assert "ciphertext_b64" not in result


def test_secure_capsule_encrypts_when_key_is_configured(monkeypatch) -> None:
    key = bytes(range(32))
    monkeypatch.setenv("ORBYTHRA_AES256_KEY_B64", base64.b64encode(key).decode("ascii"))
    result = build_secure_capsule({"query": "secret research", "value": 42})
    assert result["enabled"] is True
    assert result["algorithm"] == "AES-256-GCM"
    assert result["nonce_b64"]
    assert result["ciphertext_b64"]
    assert "secret research" not in result["ciphertext_b64"]


@pytest.mark.asyncio
async def test_enrichment_merges_digital_map_visuals_and_source_timeline(monkeypatch) -> None:
    async def fake_entity(_query: str):
        return {
            "map_markers": [
                {
                    "lat": 38.4237,
                    "lon": 27.1428,
                    "label": "İzmir",
                    "tool": "wikipedia_tr",
                    "source_url": "https://tr.wikipedia.org/wiki/Izmir",
                }
            ],
            "visual_assets": [
                {
                    "title": "Reference",
                    "url": "https://upload.wikimedia.org/example.jpg",
                    "thumbnail_url": "https://upload.wikimedia.org/example.jpg",
                    "source_url": "https://tr.wikipedia.org/wiki/Izmir",
                    "provider": "wikipedia_tr",
                    "kind": "entity_reference",
                }
            ],
        }

    monkeypatch.setattr(cognitive_runtime, "_wikipedia_entity_enrichment", fake_entity)
    enriched = await enrich_research_context(
        "İzmir tarihi",
        [
            {
                "title": "Historic source",
                "snippet": "Source summary",
                "published_at": 946684800,
                "evidence_ids": ["ev_1"],
                "url": "https://example.com/history",
            }
        ],
        [],
    )
    assert enriched["digital_map"]["enabled"] is True
    assert enriched["digital_map"]["marker_count"] == 1
    assert enriched["map_markers"][0]["label"] == "İzmir"
    assert enriched["visual_assets"]
    assert enriched["source_timeline"][0]["date"] == "2000-01-01"
