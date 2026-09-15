"""Cover normalization of heterogeneous provider payloads into one evidence schema."""

from __future__ import annotations

from evidence_schema import (
    canonical_url,
    compact_sources,
    domain_of,
    extract_source_items,
    normalize_evidence,
    parse_timestamp,
)

NOW = 1_757_000_000


def record(tool: str, data, *, ok: bool = True, evidence_id: str | None = None) -> dict:
    return {
        "evidence_id": evidence_id or f"ev_{tool}",
        "tool": tool,
        "source_url": f"https://example.test/{tool}",
        "fetched_at": NOW,
        "ok": ok,
        "data": data,
        "error": None if ok else "ConnectError: down",
        "digest": "d" * 64,
    }


def federated(*results) -> dict:
    return {"status": "ok", "results": list(results)}


def provider_result(provider_id: str, payload) -> dict:
    return {"ok": True, "provider_id": provider_id, "source_url": "https://api.test", "payload": payload}


class TestCanonicalUrl:
    def test_same_document_spelled_differently_collapses_to_one_url(self):
        variants = [
            "https://www.example.com/a/b/",
            "http://example.com/a/b",
            "https://example.com/a/b?utm_source=twitter&fbclid=xyz",
            "https://example.com/a/b#section-2",
        ]
        assert len({canonical_url(url) for url in variants}) == 1

    def test_meaningful_query_parameters_are_kept_and_ordered(self):
        assert canonical_url("https://e.com/s?b=2&a=1") == canonical_url("https://e.com/s?a=1&b=2")
        assert canonical_url("https://e.com/s?a=1") != canonical_url("https://e.com/s?a=2")

    def test_non_http_values_are_rejected(self):
        for value in ["ftp://e.com/x", "connector://provider", "not a url", "", None, 42]:
            assert canonical_url(value) is None

    def test_domain_is_reported_without_the_www_prefix(self):
        assert domain_of(canonical_url("https://www.example.com/a")) == "example.com"


class TestParseTimestamp:
    def test_accepts_seconds_milliseconds_and_iso8601(self):
        assert parse_timestamp(1_757_000_000) == 1_757_000_000
        assert parse_timestamp(1_757_000_000_000) == 1_757_000_000
        assert parse_timestamp("2026-09-15T00:00:00Z") == 1_789_430_400

    def test_rejects_unparseable_values(self):
        for value in ["", "yesterday", None, True, {}]:
            assert parse_timestamp(value) is None


class TestExtraction:
    def test_sources_are_found_at_any_nesting_depth(self):
        payload = {"data": {"hits": [{"link": "https://a.test/x", "headline": "Deep hit"}]}}
        items = extract_source_items(payload)
        assert [item["title"] for item in items] == ["Deep hit"]
        assert items[0]["url"] == "https://a.test/x"

    def test_a_repeated_url_inside_one_payload_is_returned_once(self):
        payload = [
            {"url": "https://a.test/x", "title": "First"},
            {"url": "https://www.a.test/x/", "title": "Same doc, different spelling"},
        ]
        assert len(extract_source_items(payload)) == 1

    def test_objects_without_a_url_are_not_sources(self):
        assert extract_source_items({"title": "No link here", "count": 3}) == []


class TestNormalizeEvidence:
    def test_the_same_article_from_two_providers_becomes_one_corroborated_item(self):
        evidence = {
            "provider_federation": record(
                "provider_federation",
                federated(
                    provider_result("alpha_news", {"items": [{"url": "https://n.test/story", "title": "Story"}]}),
                    provider_result("beta_news", {"items": [{"url": "https://www.n.test/story/", "title": "Story"}]}),
                ),
            )
        }
        items = normalize_evidence(evidence, now=NOW)

        assert len(items) == 1
        assert items[0].corroboration == 2
        assert sorted(items[0].providers) == ["alpha_news", "beta_news"]
        assert items[0].domain == "n.test"

    def test_distinct_urls_stay_distinct(self):
        evidence = {
            "t": record("t", federated(provider_result("alpha", {
                "items": [
                    {"url": "https://n.test/one", "title": "One"},
                    {"url": "https://n.test/two", "title": "Two"},
                ]
            })))
        }
        assert len(normalize_evidence(evidence, now=NOW)) == 2

    def test_failed_records_contribute_no_sources(self):
        evidence = {
            "broken": record("broken", federated(provider_result("alpha", {
                "items": [{"url": "https://n.test/x", "title": "X"}]
            })), ok=False)
        }
        assert normalize_evidence(evidence, now=NOW) == []

    def test_items_carry_the_evidence_ids_they_came_from(self):
        evidence = {
            "t": record("t", {"items": [{"url": "https://n.test/x", "title": "X"}]}, evidence_id="ev_abc")
        }
        assert normalize_evidence(evidence, now=NOW)[0].evidence_ids == ["ev_abc"]

    def test_the_richest_snippet_wins_when_items_merge(self):
        evidence = {
            "t": record("t", federated(
                provider_result("alpha", {"url": "https://n.test/x", "title": "X", "summary": "short"}),
                provider_result("beta", {"url": "https://n.test/x", "title": "X", "summary": "a much longer summary"}),
            ))
        }
        assert normalize_evidence(evidence, now=NOW)[0].snippet == "a much longer summary"

    def test_the_provider_endpoint_is_not_mistaken_for_a_source(self):
        # A provider result carries source_url: the API we called. Counting it as a
        # document invented one extra "source" per provider and let two providers
        # corroborate each other's endpoints.
        evidence = {
            "t": record("t", federated(
                provider_result("alpha", {"items": [{"url": "https://n.test/real", "title": "Real"}]}),
                provider_result("beta", {"items": [{"url": "https://n.test/real", "title": "Real"}]}),
            ))
        }
        items = normalize_evidence(evidence, now=NOW)

        assert [item.url for item in items] == ["https://n.test/real"]
        assert all("api.test" not in (item.url or "") for item in items)

    def test_a_payload_without_a_results_list_is_attributed_to_its_tool(self):
        evidence = {"earthquakes": record("earthquakes", {"features": [{"url": "https://q.test/e1", "title": "M4.1"}]})}
        item = normalize_evidence(evidence, now=NOW)[0]
        assert item.tools == ["earthquakes"]
        assert item.providers == []
        assert item.corroboration == 1


class TestRanking:
    def test_corroborated_sources_outrank_single_origin_ones(self):
        evidence = {
            "t": record("t", federated(
                provider_result("alpha", {"url": "https://n.test/shared", "title": "Shared"}),
                provider_result("beta", {"url": "https://n.test/shared", "title": "Shared"}),
                provider_result("alpha", {"url": "https://n.test/lonely", "title": "Lonely"}),
            ))
        }
        titles = [item.title for item in normalize_evidence(evidence, now=NOW)]
        assert titles.index("Shared") < titles.index("Lonely")

    def test_fresher_sources_outrank_older_ones(self):
        evidence = {
            "t": record("t", federated(provider_result("alpha", {"items": [
                {"url": "https://n.test/new", "title": "New", "published_at": NOW - 3600},
                {"url": "https://n.test/old", "title": "Old", "published_at": NOW - 400 * 86400},
            ]})))
        }
        titles = [item.title for item in normalize_evidence(evidence, now=NOW)]
        assert titles == ["New", "Old"]

    def test_every_item_explains_its_own_score(self):
        evidence = {"t": record("t", {"url": "https://n.test/x", "title": "X"})}
        item = normalize_evidence(evidence, now=NOW)[0]
        assert 0.0 <= item.score <= 1.0
        assert item.score_reasons
        assert any("authority" in reason for reason in item.score_reasons)

    def test_results_are_capped_and_ordered_deterministically(self):
        payload = {"items": [{"url": f"https://n.test/{i}", "title": f"T{i}"} for i in range(50)]}
        evidence = {"t": record("t", payload)}
        first = normalize_evidence(evidence, limit=10, now=NOW)
        second = normalize_evidence(evidence, limit=10, now=NOW)
        assert len(first) == 10
        assert [item.item_id for item in first] == [item.item_id for item in second]


def test_compact_sources_projects_only_what_the_analyst_needs():
    evidence = {"t": record("t", {"url": "https://n.test/x", "title": "X", "summary": "s" * 900})}
    compact = compact_sources(normalize_evidence(evidence, now=NOW), limit=5)

    assert len(compact) == 1
    assert set(compact[0]) == {
        "item_id", "title", "url", "snippet", "published_at",
        "corroboration", "score", "evidence_ids",
    }
    assert len(compact[0]["snippet"]) <= 400
