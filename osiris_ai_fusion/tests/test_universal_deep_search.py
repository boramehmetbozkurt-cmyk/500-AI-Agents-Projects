from planner import deterministic_tools
from providers import provider_specs, route_providers


def test_unknown_factual_lookup_defaults_to_provider_federation() -> None:
    tools = deterministic_tools("Ada Lovelace analytical engine")
    assert "provider_federation" in tools


def test_unclassified_query_has_bilingual_global_fallbacks() -> None:
    routed = [item.provider_id for item in route_providers("Orbythra Xylophone 987654")]
    assert "wikipedia_tr" in routed
    assert "wikipedia_en" in routed
    assert "wikidata_global" in routed


def test_current_global_query_can_route_to_gdelt() -> None:
    routed = [item.provider_id for item in route_providers("latest global AI news today")]
    assert "gdelt_news_global" in routed


def test_science_registry_includes_open_and_biomedical_sources() -> None:
    specs = provider_specs()
    assert "openalex" in specs
    assert "crossref" in specs
    assert "europe_pmc" in specs
