from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from science_resolution import (
    resolve_gene,
    resolve_gene_protein,
    resolve_scientist,
    resolve_variant_gene,
)


def _evaluate(
    cases: list[dict[str, Any]],
    resolver: Callable[..., dict[str, Any]],
    left_key: str,
    right_key: str,
) -> dict[str, Any]:
    correct = 0
    rows: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        result = resolver(case[left_key], case[right_key])
        expected = bool(case["expected"])
        predicted = bool(result["match"])
        passed = predicted == expected
        correct += int(passed)
        rows.append(
            {
                "case": index + 1,
                "expected": expected,
                "predicted": predicted,
                "score": result["score"],
                "reasons": result["reasons"],
                "passed": passed,
            }
        )
    total = len(cases)
    return {
        "cases": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else 0.0,
        "results": rows,
    }


def run_benchmark(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    scientists = _evaluate(payload.get("scientists", []), resolve_scientist, "left", "right")
    genes = _evaluate(payload.get("genes", []), resolve_gene, "left", "right")
    gene_protein = _evaluate(
        payload.get("gene_protein", []),
        resolve_gene_protein,
        "gene",
        "protein",
    )
    variant_gene = _evaluate(
        payload.get("variant_gene", []),
        resolve_variant_gene,
        "variant",
        "gene",
    )
    total = sum(item["cases"] for item in (scientists, genes, gene_protein, variant_gene))
    correct = sum(item["correct"] for item in (scientists, genes, gene_protein, variant_gene))
    return {
        "schema": "orbythra.science-resolution-benchmark-result.v1",
        "independent_external_validation": False,
        "benchmark_kind": "curated_deterministic_regression",
        "overall": {
            "cases": total,
            "correct": correct,
            "accuracy": round(correct / total, 4) if total else 0.0,
        },
        "scientist_identity": scientists,
        "gene_cross_source": genes,
        "gene_protein_crossref": gene_protein,
        "variant_gene_crossref": variant_gene,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ORBYTHRA science resolution benchmark")
    parser.add_argument(
        "--cases",
        default="benchmarks/science_resolution_cases.json",
    )
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    result = run_benchmark(Path(args.cases))
    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
