"""Cover opportunity-manifest resolution.

WALLET_HUNTER_OPPORTUNITIES defaults to a bare filename. Resolving it against the
process working directory made the result depend on where the service was started:
the README's `cd wallet_hunter && uvicorn ...` found the file, while a container or
supervisor starting elsewhere silently evaluated no opportunities at all — which
looks exactly like a wallet that qualifies for nothing.
"""

from __future__ import annotations

import json

from wallet_hunter.config import settings
from wallet_hunter.models import WalletScanRequest
from wallet_hunter.providers import PROJECT_DIR, ManifestOpportunityProvider
from wallet_hunter.scanner import WalletScanner

MANIFEST = {
    "opportunities": [
        {
            "id": "test-claim",
            "title": "Test claim",
            "chain": "base",
            "official_url": "https://example.com/claim",
        }
    ]
}


def test_default_manifest_loads_from_any_working_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "wallet_hunter_opportunities", "opportunities.example.json")
    monkeypatch.chdir(tmp_path)

    provider = ManifestOpportunityProvider()

    assert provider.path() == PROJECT_DIR / "opportunities.example.json"
    assert provider.path().exists()
    assert [o.id for o in provider.load()] == ["example-official-claim"]


def test_manifest_relative_to_the_working_directory_still_wins(tmp_path, monkeypatch):
    # An operator who drops a manifest next to the process keeps the old behaviour.
    (tmp_path / "local.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
    monkeypatch.setattr(settings, "wallet_hunter_opportunities", "local.json")
    monkeypatch.chdir(tmp_path)

    provider = ManifestOpportunityProvider()

    assert [o.id for o in provider.load()] == ["test-claim"]


def test_absolute_manifest_path_is_used_verbatim(tmp_path, monkeypatch):
    manifest = tmp_path / "absolute.json"
    manifest.write_text(json.dumps(MANIFEST), encoding="utf-8")
    monkeypatch.setattr(settings, "wallet_hunter_opportunities", str(manifest))

    provider = ManifestOpportunityProvider()

    assert provider.path() == manifest
    assert [o.id for o in provider.load()] == ["test-claim"]


def test_missing_manifest_loads_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "wallet_hunter_opportunities", "no-such-manifest.json")
    monkeypatch.chdir(tmp_path)

    provider = ManifestOpportunityProvider()

    assert not provider.path().exists()
    assert provider.load() == []


async def test_scan_warns_when_the_manifest_is_missing(tmp_path, monkeypatch):
    # An unsupported-only chain list keeps this scan entirely offline: no chain is
    # selected, so no RPC or provider call is made.
    monkeypatch.setattr(settings, "wallet_hunter_opportunities", "no-such-manifest.json")
    monkeypatch.chdir(tmp_path)

    report = await WalletScanner().scan(
        WalletScanRequest(
            address="0x" + "ab" * 20,
            chains=["not-a-chain"],
        )
    )

    assert report.opportunities == []
    assert any("no-such-manifest.json" in warning for warning in report.warnings)
    assert any("Unsupported chains ignored" in warning for warning in report.warnings)


async def test_scan_does_not_warn_when_the_manifest_is_present(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "wallet_hunter_opportunities", "opportunities.example.json")
    monkeypatch.chdir(tmp_path)

    report = await WalletScanner().scan(
        WalletScanRequest(
            address="0x" + "ab" * 20,
            chains=["not-a-chain"],
        )
    )

    assert not any("Opportunity manifest not found" in warning for warning in report.warnings)
