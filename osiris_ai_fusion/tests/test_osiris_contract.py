import pytest

from osiris_client import (
    FORBIDDEN_ACTIVE_PATHS,
    READ_ONLY_TOOLS,
    OsirisClient,
    normalize_tool_name,
)


def test_live_contract_uses_documented_flights_route():
    assert READ_ONLY_TOOLS["flights"] == "/api/flights"
    assert normalize_tool_name("aircraft") == "flights"
    client = OsirisClient(base_url="https://example.test")
    assert client.tool_url("aircraft") == "https://example.test/api/flights"


def test_active_routes_are_never_registered():
    registered = set(READ_ONLY_TOOLS.values())
    assert registered.isdisjoint(FORBIDDEN_ACTIVE_PATHS)
    assert "/api/scanner" not in registered
    assert "/api/osint/sweep" not in registered


def test_unknown_or_active_style_tool_is_denied():
    client = OsirisClient(base_url="https://example.test")
    with pytest.raises(PermissionError):
        client.tool_url("scanner")
    with pytest.raises(PermissionError):
        client.tool_url("osint_sweep")


def test_registered_routes_are_normalized_api_paths():
    assert READ_ONLY_TOOLS
    assert all(path.startswith("/api/") for path in READ_ONLY_TOOLS.values())
    assert len(READ_ONLY_TOOLS.values()) == len(set(READ_ONLY_TOOLS.values()))
