"""Offline ablation of the Universal Deep Search retrieval pipeline.

What this measures: one synthetic corpus run through three configurations of
ORBYTHRA's own pipeline, so the contribution of evidence normalization and of
recursive subquery planning is a number rather than a claim in prose.

What it does not measure, stated plainly because a benchmark that oversells is
worse than no benchmark:

* It is **not** independent. The system under test and the harness share an author.
* It is **not** a comparison against third-party search, RAG or deep-research
  products. That needs those products running, which this repository cannot do.
* It does **not** demonstrate a recall gain from decomposition. The synthetic
  federation answers any question whose text contains a document's terms, with no
  relevance ranking and no result truncation. Truncation is the mechanism by which
  decomposition improves recall against a real backend, and modelling it here would
  only measure the assumption. So `subtopic_coverage` is expected to be identical
  across variants, and it is reported precisely so that non-result is visible.

What the numbers therefore support: deduplication (real, from URL spellings that
genuinely vary in the corpus) and per-question attribution (real, from the sealed
pipeline actually issuing and recording distinct questions), against their cost in
tool calls.

The corpus is synthetic and the providers are in-process, so there are no network
calls, no API keys, and byte-identical output on every run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from evidence_schema import canonical_url, extract_source_items, normalize_evidence
from provenance import make_evidence_record
from subquery import plan_subqueries

VARIANTS = (
    # (name, normalize evidence, plan subqueries)
    ("baseline_raw", False, False),
    ("normalized_only", True, False),
    ("orbythra_full", True, True),
)


def _ask(corpus: list[dict[str, Any]], question: str) -> list[dict[str, Any]]:
    """The synthetic federation: a document answers a question that contains its terms."""
    lowered = question.casefold()
    results: list[dict[str, Any]] = []
    for provider in corpus:
        documents = [
            document
            for document in provider["documents"]
            if all(term.casefold() in lowered for term in document["terms"])
        ]
        if documents:
            results.append(
                {
                    "ok": True,
                    "provider_id": provider["provider_id"],
                    "source_url": f"https://federation.test/{provider['provider_id']}",
                    "payload": {"items": documents},
                }
            )
    return results


def _subtopic_by_url(case: dict[str, Any]) -> dict[str, str]:
    """Label lookup keyed the same way the pipeline deduplicates."""
    mapping: dict[str, str] = {}
    for provider in case["corpus"]:
        for document in provider["documents"]:
            key = canonical_url(document["url"]) or document["url"]
            mapping[key] = document["subtopic"]
    return mapping


def _collect(case: dict[str, Any], questions: list[str]) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for index, question in enumerate(questions):
        key = "provider_federation" if index == 0 else f"provider_federation#sq{index}"
        evidence[key] = make_evidence_record(
            tool="provider_federation",
            source_url="https://federation.test",
            data={"status": "ok", "results": _ask(case["corpus"], question)},
            query=question,
        )
    return evidence


def _raw_urls(evidence: dict[str, Any]) -> list[str]:
    """What a consumer sees with no normalization: every payload, parsed per provider."""
    urls: list[str] = []
    for record in evidence.values():
        for entry in record["data"]["results"]:
            urls.extend(item["url"] for item in extract_source_items(entry["payload"]))
    return urls


def _run_variant(case: dict[str, Any], *, normalize: bool, recurse: bool) -> dict[str, Any]:
    questions = [case["question"]]
    if recurse:
        questions += [item.query for item in asyncio.run(plan_subqueries(case["question"]))]

    evidence = _collect(case, questions)
    if normalize:
        urls = [item.url for item in normalize_evidence(evidence, now=0) if item.url]
    else:
        urls = _raw_urls(evidence)

    canonical = [canonical_url(url) or url for url in urls]
    distinct = set(canonical)
    reported = len(canonical)
    labels = _subtopic_by_url(case)
    covered = sorted({labels[key] for key in distinct if key in labels})
    answered = sorted(
        {
            str(record.get("query"))
            for record in evidence.values()
            if record["data"]["results"]
        }
    )

    return {
        "tool_calls": len(questions),
        "questions_asked": questions,
        "questions_answered": len(answered),
        # How much of what a consumer is shown is the same document twice.
        "sources_reported": reported,
        "distinct_sources": len(distinct),
        "duplicate_rate": round(1 - (len(distinct) / reported), 4) if reported else 0.0,
        "subtopics_covered": covered,
        "subtopic_coverage": round(len(covered) / len(case["subtopics"]), 4),
    }


def run_benchmark(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases", [])

    case_rows = [
        {
            "id": case["id"],
            "question": case["question"],
            "variants": {
                name: _run_variant(case, normalize=normalize, recurse=recurse)
                for name, normalize, recurse in VARIANTS
            },
        }
        for case in cases
    ]

    def _mean(rows: list[dict[str, Any]], key: str) -> float:
        return round(sum(row[key] for row in rows) / len(rows), 4) if rows else 0.0

    overall = {
        name: {
            "mean_duplicate_rate": _mean(
                [row["variants"][name] for row in case_rows], "duplicate_rate"
            ),
            "mean_distinct_sources": _mean(
                [row["variants"][name] for row in case_rows], "distinct_sources"
            ),
            "mean_subtopic_coverage": _mean(
                [row["variants"][name] for row in case_rows], "subtopic_coverage"
            ),
            "total_questions_answered": sum(
                row["variants"][name]["questions_answered"] for row in case_rows
            ),
            "total_tool_calls": sum(
                row["variants"][name]["tool_calls"] for row in case_rows
            ),
        }
        for name, _, _ in VARIANTS
    }

    return {
        "schema": "orbythra.deep-research-benchmark-result.v1",
        "benchmark_kind": "synthetic_offline_pipeline_ablation",
        "independent_external_validation": False,
        "third_party_baseline_comparison": False,
        "models_recall_from_decomposition": False,
        "production_measurement": False,
        "network_required": False,
        "note": (
            "Baselines are ORBYTHRA's own pipeline with evidence normalization and "
            "recursive subquery planning switched off. The synthetic federation "
            "applies no relevance ranking and no result truncation, so subtopic "
            "coverage is expected to be identical across variants; it is reported so "
            "that non-result stays visible. Deduplication and per-question "
            "attribution are what these numbers support. Comparison against external "
            "search, RAG or deep-research products, and evaluation by an independent "
            "party, remain open gates and are not claimed here."
        ),
        "cases": case_rows,
        "overall": overall,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the ORBYTHRA deep-research pipeline ablation benchmark"
    )
    parser.add_argument("--cases", default="benchmarks/deep_research_cases.json")
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
