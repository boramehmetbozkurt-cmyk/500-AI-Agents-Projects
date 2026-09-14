from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from config import get_settings
from saas import AuthContext, require_identity

logger = logging.getLogger("osiris_fusion.science_world")

SCIENCE_SOURCES: list[dict[str, Any]] = [
    {
        "id": "openalex",
        "domain": "scientists_works_institutions_topics",
        "mode": "api_or_snapshot",
        "base_url": "https://api.openalex.org",
        "license": "CC0 metadata",
        "commercial_use": "allowed_for_metadata",
        "notes": "Use API for search/small sync and snapshot/CLI for bulk. Preserve identifiers and source provenance. Full-text files retain their own licenses.",
    },
    {
        "id": "wikidata",
        "domain": "historical_scientists_identifiers_places_dates",
        "mode": "sparql_or_dump",
        "base_url": "https://query.wikidata.org/sparql",
        "license": "CC0 structured data",
        "commercial_use": "allowed",
        "notes": "Use dumps for very large imports; WDQS is for bounded queries, not mirroring a substantial fraction of Wikidata.",
    },
    {
        "id": "ncbi_datasets",
        "domain": "genes_genomes_assemblies_taxonomy",
        "mode": "rest_api_or_bulk",
        "base_url": "https://api.ncbi.nlm.nih.gov/datasets/v2",
        "license": "US-government/public molecular data with upstream-rights caveat",
        "commercial_use": "review_upstream_rights",
        "notes": "NCBI places no restriction on molecular database reuse, but submitters may retain patent/copyright/other rights in portions of contributed data.",
    },
    {
        "id": "ensembl",
        "domain": "genes_transcripts_variation_comparative_genomics",
        "mode": "rest_api_or_bulk",
        "base_url": "https://rest.ensembl.org",
        "license": "project data generally unrestricted; third-party constraints may apply",
        "commercial_use": "review_third_party_constraints",
        "notes": "Keep Ensembl stable IDs, release/version and assembly coordinates with every imported feature.",
    },
    {
        "id": "uniprot",
        "domain": "proteins_functions_sequences_cross_references",
        "mode": "rest_api_or_bulk",
        "base_url": "https://rest.uniprot.org",
        "license": "CC BY 4.0 for copyrightable database parts",
        "commercial_use": "allowed_with_attribution_and_rights_review",
        "notes": "Retain accession, reviewed status, source database, release and attribution. Some records can involve patent/other rights.",
    },
    {
        "id": "clinvar",
        "domain": "human_variants_conditions_assertions",
        "mode": "ncbi_eutilities_or_bulk",
        "base_url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
        "license": "NCBI public archive; attribution requested; medical-use disclaimer applies",
        "commercial_use": "research_information_only",
        "notes": "Never present ClinVar assertions as diagnosis or patient-specific medical advice. Keep review status, submitter, assertion date and citations.",
    },
]

ENTITY_TYPES = {
    "scientist",
    "work",
    "institution",
    "field",
    "contribution",
    "organism",
    "assembly",
    "chromosome",
    "gene",
    "transcript",
    "protein",
    "variant",
    "phenotype",
    "pathway",
    "sequence_reference",
    "database_crossref",
}

EDGE_TYPES = {
    "authored",
    "coauthored_with",
    "affiliated_with",
    "contributed_to",
    "discovered",
    "developed",
    "cites",
    "about_topic",
    "located_on",
    "transcribes_to",
    "translates_to",
    "encodes",
    "variant_of",
    "associated_with",
    "participates_in",
    "ortholog_of",
    "part_of_assembly",
    "cross_references",
    "source_asserts",
}

PERSONAL_GENOME_PATTERNS = (
    re.compile(r"\bpatient\b", re.I),
    re.compile(r"\bpersonal genome\b", re.I),
    re.compile(r"\bmy genome\b", re.I),
    re.compile(r"\bvcf\b", re.I),
    re.compile(r"\bbam\b", re.I),
    re.compile(r"\bcram\b", re.I),
    re.compile(r"\bfastq\b", re.I),
    re.compile(r"\bgenotype of\b", re.I),
)


class ScienceIngestRequest(BaseModel):
    kind: Literal["scientists", "works", "gene", "protein", "variant"]
    query: str = Field(min_length=1, max_length=500)
    species: str = Field(default="homo_sapiens", min_length=2, max_length=80)
    taxon: str = Field(default="human", min_length=1, max_length=80)
    limit: int = Field(default=25, ge=1, le=100)


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _public_reference_query(query: str) -> None:
    if any(pattern.search(query) for pattern in PERSONAL_GENOME_PATTERNS):
        raise ValueError(
            "Shared Science Genome Graph accepts public reference biology only; "
            "patient or personal raw-genome material must use a separate consented private vault."
        )


def _clean_openalex_id(value: Any) -> str:
    raw = str(value or "")
    return raw.rsplit("/", 1)[-1] if raw else ""


def _normalize_openalex_author(row: dict[str, Any]) -> dict[str, Any]:
    institutions = []
    for item in row.get("last_known_institutions") or []:
        if isinstance(item, dict):
            institutions.append(
                {
                    "id": _clean_openalex_id(item.get("id")),
                    "name": item.get("display_name"),
                    "country_code": item.get("country_code"),
                    "type": item.get("type"),
                }
            )
    topics = []
    for topic in row.get("topics") or []:
        if isinstance(topic, dict):
            topics.append(
                {
                    "id": _clean_openalex_id(topic.get("id")),
                    "name": topic.get("display_name"),
                    "score": topic.get("score"),
                }
            )
    author_id = _clean_openalex_id(row.get("id"))
    return {
        "entity_type": "scientist",
        "canonical_key": f"openalex:author:{author_id}",
        "source_id": "openalex",
        "external_id": author_id,
        "name": row.get("display_name") or author_id,
        "orcid": row.get("orcid"),
        "works_count": row.get("works_count"),
        "cited_by_count": row.get("cited_by_count"),
        "institutions": institutions,
        "topics": topics,
        "ids": row.get("ids") or {},
        "updated_date": row.get("updated_date"),
    }


def _normalize_openalex_work(row: dict[str, Any]) -> dict[str, Any]:
    work_id = _clean_openalex_id(row.get("id"))
    authors = []
    for authorship in row.get("authorships") or []:
        if not isinstance(authorship, dict):
            continue
        author = authorship.get("author") or {}
        authors.append(
            {
                "id": _clean_openalex_id(author.get("id")),
                "name": author.get("display_name"),
                "orcid": author.get("orcid"),
                "position": authorship.get("author_position"),
                "corresponding": bool(authorship.get("is_corresponding")),
            }
        )
    primary = row.get("primary_location") or {}
    return {
        "entity_type": "work",
        "canonical_key": f"openalex:work:{work_id}",
        "source_id": "openalex",
        "external_id": work_id,
        "name": row.get("display_name") or row.get("title") or work_id,
        "doi": row.get("doi"),
        "publication_year": row.get("publication_year"),
        "publication_date": row.get("publication_date"),
        "type": row.get("type"),
        "cited_by_count": row.get("cited_by_count"),
        "authors": authors,
        "topics": [
            {
                "id": _clean_openalex_id(topic.get("id")),
                "name": topic.get("display_name"),
                "score": topic.get("score"),
            }
            for topic in row.get("topics") or []
            if isinstance(topic, dict)
        ],
        "open_access": row.get("open_access") or {},
        "primary_location_license": primary.get("license"),
        "ids": row.get("ids") or {},
        "updated_date": row.get("updated_date"),
    }


def _normalize_ensembl_gene(row: dict[str, Any], symbol: str) -> dict[str, Any]:
    gene_id = str(row.get("id") or symbol)
    return {
        "entity_type": "gene",
        "canonical_key": f"ensembl:gene:{gene_id}",
        "source_id": "ensembl",
        "external_id": gene_id,
        "name": row.get("display_name") or symbol,
        "species": row.get("species"),
        "assembly_name": row.get("assembly_name"),
        "biotype": row.get("biotype"),
        "seq_region_name": row.get("seq_region_name"),
        "start": row.get("start"),
        "end": row.get("end"),
        "strand": row.get("strand"),
        "description": row.get("description"),
        "object_type": row.get("object_type"),
        "version": row.get("version"),
    }


def _normalize_uniprot(row: dict[str, Any]) -> dict[str, Any]:
    accession = str(row.get("primaryAccession") or "")
    protein = row.get("proteinDescription") or {}
    recommended = protein.get("recommendedName") or {}
    full_name = (recommended.get("fullName") or {}).get("value")
    genes = [
        (gene.get("geneName") or {}).get("value")
        for gene in row.get("genes") or []
        if isinstance(gene, dict)
    ]
    return {
        "entity_type": "protein",
        "canonical_key": f"uniprot:protein:{accession}",
        "source_id": "uniprot",
        "external_id": accession,
        "name": full_name or accession,
        "genes": [value for value in genes if value],
        "reviewed": str(row.get("entryType") or "").lower().startswith("uniprotkb reviewed"),
        "organism": row.get("organism") or {},
        "sequence": {
            "length": (row.get("sequence") or {}).get("length"),
            "molWeight": (row.get("sequence") or {}).get("molWeight"),
            "crc64": (row.get("sequence") or {}).get("crc64"),
        },
        "uniProtkbId": row.get("uniProtkbId"),
    }


async def _get_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    response = await client.get(url, params=params, headers=headers)
    response.raise_for_status()
    return response.json()


async def search_openalex_authors(query: str, limit: int = 25) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=12.0, follow_redirects=False) as client:
        payload = await _get_json(
            client,
            "https://api.openalex.org/authors",
            params={"search": query, "per_page": min(limit, 100)},
        )
    return [_normalize_openalex_author(row) for row in payload.get("results") or [] if isinstance(row, dict)]


async def search_openalex_works(query: str, limit: int = 25) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=12.0, follow_redirects=False) as client:
        payload = await _get_json(
            client,
            "https://api.openalex.org/works",
            params={"search": query, "per_page": min(limit, 100)},
        )
    return [_normalize_openalex_work(row) for row in payload.get("results") or [] if isinstance(row, dict)]


async def search_wikidata_people(query: str, limit: int = 10) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
        payload = await _get_json(
            client,
            "https://www.wikidata.org/w/api.php",
            params={
                "action": "wbsearchentities",
                "search": query,
                "language": "en",
                "format": "json",
                "limit": min(limit, 50),
                "type": "item",
            },
            headers={"User-Agent": "OSIRIS-World/1.3 science-graph"},
        )
    rows = []
    for item in payload.get("search") or []:
        if not isinstance(item, dict):
            continue
        entity_id = str(item.get("id") or "")
        rows.append(
            {
                "entity_type": "scientist_candidate",
                "canonical_key": f"wikidata:item:{entity_id}",
                "source_id": "wikidata",
                "external_id": entity_id,
                "name": item.get("label") or entity_id,
                "description": item.get("description"),
                "url": item.get("concepturi"),
                "verification_status": "candidate_requires_occupation_check",
            }
        )
    return rows


async def lookup_gene(symbol: str, species: str = "homo_sapiens", taxon: str = "human") -> dict[str, Any]:
    _public_reference_query(symbol)
    encoded_symbol = quote(symbol, safe="")
    encoded_species = quote(species, safe="")
    encoded_taxon = quote(taxon, safe="")
    ensembl_url = f"https://rest.ensembl.org/lookup/symbol/{encoded_species}/{encoded_symbol}"
    ncbi_url = (
        "https://api.ncbi.nlm.nih.gov/datasets/v2/gene/symbol/"
        f"{encoded_symbol}/taxon/{encoded_taxon}/dataset_report"
    )
    async with httpx.AsyncClient(timeout=12.0, follow_redirects=False) as client:
        ensembl_task = _get_json(
            client,
            ensembl_url,
            params={"content-type": "application/json"},
            headers={"Accept": "application/json"},
        )
        ncbi_task = _get_json(client, ncbi_url, headers={"Accept": "application/json"})
        ensembl_result, ncbi_result = await asyncio.gather(
            ensembl_task,
            ncbi_task,
            return_exceptions=True,
        )
    normalized = []
    errors: dict[str, str] = {}
    if isinstance(ensembl_result, dict):
        normalized.append(_normalize_ensembl_gene(ensembl_result, symbol))
    else:
        errors["ensembl"] = type(ensembl_result).__name__
    if isinstance(ncbi_result, dict):
        reports = ncbi_result.get("reports") or []
        for report in reports[:25]:
            if not isinstance(report, dict):
                continue
            gene = report.get("gene") or report
            gene_id = str(gene.get("gene_id") or gene.get("geneId") or symbol)
            normalized.append(
                {
                    "entity_type": "gene",
                    "canonical_key": f"ncbi:gene:{gene_id}",
                    "source_id": "ncbi_datasets",
                    "external_id": gene_id,
                    "name": gene.get("symbol") or symbol,
                    "description": gene.get("description"),
                    "taxname": gene.get("taxname"),
                    "chromosomes": gene.get("chromosomes") or [],
                    "common_name": gene.get("common_name"),
                    "nomenclature_authority": gene.get("nomenclature_authority"),
                }
            )
    else:
        errors["ncbi_datasets"] = type(ncbi_result).__name__
    return {"symbol": symbol, "species": species, "taxon": taxon, "records": normalized, "errors": errors}


async def search_uniprot(gene: str, limit: int = 25, taxon_id: int = 9606) -> list[dict[str, Any]]:
    _public_reference_query(gene)
    query = f"(gene_exact:{gene}) AND (organism_id:{taxon_id})"
    async with httpx.AsyncClient(timeout=12.0, follow_redirects=False) as client:
        payload = await _get_json(
            client,
            "https://rest.uniprot.org/uniprotkb/search",
            params={"query": query, "format": "json", "size": min(limit, 100)},
            headers={"Accept": "application/json"},
        )
    return [_normalize_uniprot(row) for row in payload.get("results") or [] if isinstance(row, dict)]


async def search_clinvar(term: str, limit: int = 20) -> list[dict[str, Any]]:
    _public_reference_query(term)
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    async with httpx.AsyncClient(timeout=12.0, follow_redirects=False) as client:
        search = await _get_json(
            client,
            f"{base}/esearch.fcgi",
            params={"db": "clinvar", "term": term, "retmode": "json", "retmax": min(limit, 100)},
        )
        ids = ((search.get("esearchresult") or {}).get("idlist") or [])[:limit]
        if not ids:
            return []
        summary = await _get_json(
            client,
            f"{base}/esummary.fcgi",
            params={"db": "clinvar", "id": ",".join(ids), "retmode": "json"},
        )
    result = summary.get("result") or {}
    rows = []
    for uid in result.get("uids") or []:
        record = result.get(str(uid)) or {}
        rows.append(
            {
                "entity_type": "variant",
                "canonical_key": f"clinvar:variation:{uid}",
                "source_id": "clinvar",
                "external_id": str(uid),
                "name": record.get("title") or f"ClinVar {uid}",
                "variation_set": record.get("variation_set"),
                "genes": record.get("genes") or [],
                "germline_classification": record.get("germline_classification"),
                "clinical_impact_classification": record.get("clinical_impact_classification"),
                "trait_set": record.get("trait_set") or [],
                "accession": record.get("accession"),
                "medical_use": "research_information_only_not_diagnostic",
            }
        )
    return rows


class ScienceGraphStore:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or get_settings().store_path
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS science_entities (
                    workspace_id TEXT NOT NULL,
                    canonical_key TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_digest TEXT NOT NULL,
                    observed_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY(workspace_id, canonical_key)
                );
                CREATE INDEX IF NOT EXISTS idx_science_entities_type
                    ON science_entities(workspace_id, entity_type, name);
                CREATE INDEX IF NOT EXISTS idx_science_entities_source
                    ON science_entities(workspace_id, source_id, external_id);

                CREATE TABLE IF NOT EXISTS science_edges (
                    workspace_id TEXT NOT NULL,
                    edge_key TEXT NOT NULL,
                    source_key TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    target_key TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    confidence REAL NOT NULL DEFAULT 0.5,
                    observed_at INTEGER NOT NULL,
                    PRIMARY KEY(workspace_id, edge_key)
                );
                CREATE INDEX IF NOT EXISTS idx_science_edges_nodes
                    ON science_edges(workspace_id, source_key, target_key);

                CREATE TABLE IF NOT EXISTS science_ingest_runs (
                    workspace_id TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    query TEXT NOT NULL,
                    status TEXT NOT NULL,
                    entity_count INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY(workspace_id, digest)
                );
                """
            )
            conn.commit()

    def upsert_entities(self, workspace_id: str, rows: list[dict[str, Any]]) -> int:
        now = int(time.time())
        count = 0
        with self._lock, self._connect() as conn:
            for row in rows:
                canonical_key = str(row.get("canonical_key") or "")
                entity_type = str(row.get("entity_type") or "")
                source_id = str(row.get("source_id") or "")
                external_id = str(row.get("external_id") or "")
                name = str(row.get("name") or external_id or canonical_key)
                if not canonical_key or not source_id or not entity_type:
                    continue
                payload = _stable_json(row)
                conn.execute(
                    """
                    INSERT INTO science_entities(
                        workspace_id, canonical_key, entity_type, source_id, external_id,
                        name, payload_json, payload_digest, observed_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(workspace_id, canonical_key) DO UPDATE SET
                        entity_type=excluded.entity_type,
                        source_id=excluded.source_id,
                        external_id=excluded.external_id,
                        name=excluded.name,
                        payload_json=excluded.payload_json,
                        payload_digest=excluded.payload_digest,
                        updated_at=excluded.updated_at
                    """,
                    (
                        workspace_id,
                        canonical_key,
                        entity_type,
                        source_id,
                        external_id,
                        name,
                        payload,
                        _digest(row),
                        now,
                        now,
                    ),
                )
                count += 1
            conn.commit()
        return count

    def list_entities(
        self,
        workspace_id: str,
        *,
        entity_type: str | None = None,
        source_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses = ["workspace_id=?"]
        params: list[Any] = [workspace_id]
        if entity_type:
            clauses.append("entity_type=?")
            params.append(entity_type)
        if source_id:
            clauses.append("source_id=?")
            params.append(source_id)
        params.append(limit)
        sql = (
            "SELECT payload_json FROM science_entities WHERE "
            + " AND ".join(clauses)
            + " ORDER BY updated_at DESC LIMIT ?"
        )
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def counts(self, workspace_id: str) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT entity_type, COUNT(*) AS n FROM science_entities WHERE workspace_id=? GROUP BY entity_type",
                (workspace_id,),
            ).fetchall()
        return {str(row["entity_type"]): int(row["n"]) for row in rows}


science_store = ScienceGraphStore(get_settings().store_path)
router = APIRouter(prefix="/science", tags=["science-genome"])
Identity = Annotated[AuthContext, Depends(require_identity)]


@router.get("")
async def science_info(auth: Identity) -> dict[str, Any]:
    return {
        "name": "OSIRIS Science Genome Graph",
        "workspace_id": auth.tenant_id,
        "purpose": "Evidence-bound graph for scientists, scholarship, genes, proteins and public genomic reference knowledge.",
        "entity_types": sorted(ENTITY_TYPES),
        "edge_types": sorted(EDGE_TYPES),
        "sources": SCIENCE_SOURCES,
        "privacy_boundary": (
            "The shared graph stores public reference biology and public scholarly metadata only. "
            "Personal raw genomes, patient records and identifiable case-level genetics require a separate consented private vault."
        ),
        "medical_boundary": "Genomic/ClinVar data is informational/research context, not diagnosis or treatment advice.",
        "counts": science_store.counts(auth.tenant_id),
    }


@router.get("/sources")
async def science_sources(_: Identity) -> dict[str, Any]:
    return {"sources": SCIENCE_SOURCES}


@router.get("/scientists/search")
async def scientists_search(
    auth: Identity,
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    openalex, wikidata = await asyncio.gather(
        search_openalex_authors(q, limit),
        search_wikidata_people(q, min(limit, 20)),
        return_exceptions=True,
    )
    errors: dict[str, str] = {}
    if isinstance(openalex, Exception):
        errors["openalex"] = type(openalex).__name__
        openalex = []
    if isinstance(wikidata, Exception):
        errors["wikidata"] = type(wikidata).__name__
        wikidata = []
    return {
        "query": q,
        "workspace_id": auth.tenant_id,
        "openalex": openalex,
        "wikidata_candidates": wikidata,
        "errors": errors,
        "note": "Wikidata text hits are candidates until occupation/field claims are verified during ingestion.",
    }


@router.get("/works/search")
async def works_search(
    auth: Identity,
    q: str = Query(min_length=2, max_length=300),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    rows = await search_openalex_works(q, limit)
    return {"query": q, "workspace_id": auth.tenant_id, "works": rows}


@router.get("/genes/{symbol}")
async def gene_lookup(
    symbol: str,
    auth: Identity,
    species: str = Query(default="homo_sapiens", min_length=2, max_length=80),
    taxon: str = Query(default="human", min_length=1, max_length=80),
) -> dict[str, Any]:
    try:
        result = await lookup_gene(symbol, species, taxon)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result["workspace_id"] = auth.tenant_id
    return result


@router.get("/proteins/search")
async def protein_search(
    auth: Identity,
    gene: str = Query(min_length=1, max_length=80),
    taxon_id: int = Query(default=9606, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    try:
        rows = await search_uniprot(gene, limit, taxon_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"gene": gene, "taxon_id": taxon_id, "workspace_id": auth.tenant_id, "proteins": rows}


@router.get("/variants/search")
async def variant_search(
    auth: Identity,
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    try:
        rows = await search_clinvar(q, limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "query": q,
        "workspace_id": auth.tenant_id,
        "variants": rows,
        "medical_boundary": "Research/information only. ClinVar submissions are assertions and are not direct diagnostic advice.",
    }


@router.post("/ingest")
async def ingest_science(body: ScienceIngestRequest, auth: Identity) -> dict[str, Any]:
    try:
        _public_reference_query(body.query)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    rows: list[dict[str, Any]] = []
    if body.kind == "scientists":
        rows = await search_openalex_authors(body.query, body.limit)
    elif body.kind == "works":
        rows = await search_openalex_works(body.query, body.limit)
    elif body.kind == "gene":
        result = await lookup_gene(body.query, body.species, body.taxon)
        rows = result["records"]
    elif body.kind == "protein":
        rows = await search_uniprot(body.query, body.limit)
    elif body.kind == "variant":
        rows = await search_clinvar(body.query, body.limit)
    stored = science_store.upsert_entities(auth.tenant_id, rows)
    return {
        "status": "ingested",
        "kind": body.kind,
        "query": body.query,
        "fetched": len(rows),
        "stored": stored,
        "workspace_id": auth.tenant_id,
        "digest": _digest({"kind": body.kind, "query": body.query, "rows": rows}),
    }


@router.get("/entities")
async def list_science_entities(
    auth: Identity,
    entity_type: str | None = Query(default=None, max_length=80),
    source_id: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=100, ge=1, le=1000),
) -> dict[str, Any]:
    rows = science_store.list_entities(
        auth.tenant_id,
        entity_type=entity_type,
        source_id=source_id,
        limit=limit,
    )
    return {"count": len(rows), "entities": rows, "workspace_id": auth.tenant_id}


@router.get("/import-plan")
async def import_plan(_: Identity) -> dict[str, Any]:
    return {
        "strategy": "search_first_then_snapshot_scale",
        "phases": [
            {
                "phase": 1,
                "name": "live_reference",
                "sources": ["openalex", "wikidata", "ncbi_datasets", "ensembl", "uniprot", "clinvar"],
                "goal": "Functional search, provenance, normalization and schema validation.",
            },
            {
                "phase": 2,
                "name": "scientist_backbone",
                "sources": ["openalex_snapshot", "wikidata_dump"],
                "goal": "Checkpointed bulk author/scientist identity graph; use dumps/snapshots rather than abusive API crawling.",
            },
            {
                "phase": 3,
                "name": "scholarly_contribution_graph",
                "sources": ["openalex_works", "crossref", "public_orcid_metadata_when_licensed"],
                "goal": "Works, authorships, institutions, citations, topics, identifiers and contribution evidence.",
            },
            {
                "phase": 4,
                "name": "human_reference_genome_graph",
                "sources": ["ncbi_datasets", "ensembl", "uniprot", "clinvar"],
                "goal": "Genes, transcripts, proteins, variants and cross-database identifiers with assembly/release provenance.",
            },
            {
                "phase": 5,
                "name": "continuous_sync",
                "sources": ["source_release_manifests", "delta_apis", "world_sensor_mesh"],
                "goal": "Incremental refresh, checksums, source releases, drift detection, rollback and buyer-auditable data lineage.",
            },
        ],
        "bulk_rule": "Use provider snapshots/dumps when importing a material share of a source; APIs remain for bounded lookup and delta sync.",
        "privacy_rule": "No personal raw-genome or identifiable patient data in the shared graph.",
    }
