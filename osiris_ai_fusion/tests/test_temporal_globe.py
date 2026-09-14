from pathlib import Path


def test_temporal_globe_assets_are_wired_to_atlas_api():
    root = Path(__file__).resolve().parents[1]
    html = (root / "ui" / "assets" / "temporal-globe.html").read_text(encoding="utf-8")
    js = (root / "ui" / "assets" / "temporal-globe.js").read_text(encoding="utf-8")
    css = root / "ui" / "assets" / "temporal-globe.css"

    assert "ORBYTHRA Temporal Globe" in html
    assert 'data-mode="physical"' in html
    assert 'data-mode="history"' in html
    assert 'data-mode="digital"' in html
    assert 'data-mode="metaverse"' in html
    assert 'data-mode="future"' in html
    assert 'type="range"' in html
    assert "sessionStorage" in js
    assert "/world/atlas/features" in js
    assert "/world/atlas/portals" in js
    assert "/world/forks" in js
    assert "three@0.186.0" in js
    assert "SphereGeometry" in js
    assert "latLonToVector3" in js
    assert "FUTURE_TRUTH" in js
    assert css.exists()


def test_temporal_globe_keeps_virtual_coordinates_separate_from_earth():
    root = Path(__file__).resolve().parents[1]
    js = (root / "ui" / "assets" / "temporal-globe.js").read_text(encoding="utf-8")

    assert "feature.space?.earth_anchor" in js
    assert "unanchored.push(feature)" in js
    assert "coordinate-space" in js
    assert "truth_mode" in js
