from __future__ import annotations

import re
import unicodedata
from typing import Any


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _orcid(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("https://orcid.org/", "")
    return raw


def _strings(values: Any) -> set[str]:
    if not isinstance(values, list):
        return set()
    result: set[str] = set()
    for value in values:
        if isinstance(value, dict):
            value = value.get("name") or value.get("id") or value.get("symbol")
        normalized = _norm(value)
        if normalized:
            result.add(normalized)
    return result


def resolve_scientist(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Resolve cross-source scientist identity with auditable deterministic rules."""

    reasons: list[str] = []
    score = 0.0
    left_orcid, right_orcid = _orcid(left.get("orcid")), _orcid(right.get("orcid"))
    if left_orcid and right_orcid:
        if left_orcid == right_orcid:
            return {"match": True, "score": 1.0, "reasons": ["exact_orcid"]}
        return {"match": False, "score": 0.0, "reasons": ["conflicting_orcid"]}

    if _norm(left.get("name")) and _norm(left.get("name")) == _norm(right.get("name")):
        score += 0.55
        reasons.append("exact_normalized_name")

    left_institutions = _strings(left.get("institutions"))
    right_institutions = _strings(right.get("institutions"))
    if left_institutions & right_institutions:
        score += 0.20
        reasons.append("institution_overlap")

    left_topics = _strings(left.get("topics"))
    right_topics = _strings(right.get("topics"))
    if left_topics & right_topics:
        score += 0.10
        reasons.append("topic_overlap")

    birth_left = str(left.get("birth_date") or left.get("date_of_birth") or "")[:10]
    birth_right = str(right.get("birth_date") or right.get("date_of_birth") or "")[:10]
    if birth_left and birth_right:
        if birth_left == birth_right:
            score += 0.15
            reasons.append("birth_date_match")
        else:
            score -= 0.35
            reasons.append("birth_date_conflict")

    score = max(0.0, min(1.0, score))
    return {"match": score >= 0.70, "score": round(score, 3), "reasons": reasons}


def resolve_gene(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Resolve NCBI/Ensembl-style public gene records without guessing missing identifiers."""

    reasons: list[str] = []
    score = 0.0
    if _norm(left.get("name")) and _norm(left.get("name")) == _norm(right.get("name")):
        score += 0.60
        reasons.append("symbol_match")

    left_chr = _strings(left.get("chromosomes")) or {_norm(left.get("seq_region_name"))}
    right_chr = _strings(right.get("chromosomes")) or {_norm(right.get("seq_region_name"))}
    left_chr.discard("")
    right_chr.discard("")
    if left_chr and right_chr and left_chr & right_chr:
        score += 0.20
        reasons.append("chromosome_match")

    left_desc, right_desc = _norm(left.get("description")), _norm(right.get("description"))
    if left_desc and right_desc and (left_desc in right_desc or right_desc in left_desc):
        score += 0.10
        reasons.append("description_overlap")

    left_species = _norm(left.get("species") or left.get("taxname"))
    right_species = _norm(right.get("species") or right.get("taxname"))
    if left_species and right_species:
        if left_species == right_species or {left_species, right_species} <= {
            "homosapiens",
            "human",
        }:
            score += 0.10
            reasons.append("species_match")
        else:
            score -= 0.50
            reasons.append("species_conflict")

    score = max(0.0, min(1.0, score))
    return {"match": score >= 0.70, "score": round(score, 3), "reasons": reasons}


def resolve_gene_protein(gene: dict[str, Any], protein: dict[str, Any]) -> dict[str, Any]:
    symbol = _norm(gene.get("name"))
    protein_genes = {_norm(value) for value in protein.get("genes") or []}
    protein_genes.discard("")
    match = bool(symbol and symbol in protein_genes)
    return {
        "match": match,
        "score": 1.0 if match else 0.0,
        "reasons": ["protein_gene_symbol_crossref"] if match else [],
    }


def resolve_variant_gene(variant: dict[str, Any], gene: dict[str, Any]) -> dict[str, Any]:
    symbol = _norm(gene.get("name"))
    variant_genes = set()
    for item in variant.get("genes") or []:
        if isinstance(item, dict):
            item = item.get("symbol") or item.get("name")
        value = _norm(item)
        if value:
            variant_genes.add(value)
    match = bool(symbol and symbol in variant_genes)
    return {
        "match": match,
        "score": 1.0 if match else 0.0,
        "reasons": ["variant_gene_symbol_crossref"] if match else [],
    }
