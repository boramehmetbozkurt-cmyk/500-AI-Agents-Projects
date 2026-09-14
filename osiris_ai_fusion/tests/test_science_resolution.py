from pathlib import Path

from ops_resolution_benchmark import run_benchmark
from science_resolution import resolve_gene, resolve_scientist


def test_orcid_conflict_fails_closed():
    result = resolve_scientist(
        {"name": "A", "orcid": "0000-0001-0000-0001"},
        {"name": "A", "orcid": "0000-0001-0000-0002"},
    )
    assert result["match"] is False
    assert result["reasons"] == ["conflicting_orcid"]


def test_gene_resolver_uses_symbol_and_location():
    result = resolve_gene(
        {"name": "BRCA1", "seq_region_name": "17", "species": "homo_sapiens"},
        {"name": "BRCA1", "chromosomes": ["17"], "taxname": "human"},
    )
    assert result["match"] is True
    assert result["score"] >= 0.8


def test_curated_science_resolution_benchmark_is_reproducible():
    root = Path(__file__).resolve().parents[1]
    result = run_benchmark(root / "benchmarks" / "science_resolution_cases.json")
    assert result["independent_external_validation"] is False
    assert result["overall"]["cases"] >= 10
    assert result["overall"]["accuracy"] == 1.0
