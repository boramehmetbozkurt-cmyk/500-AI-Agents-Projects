from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable, Iterator, Literal

from config import get_settings
from science_world import (
    ScienceGraphStore,
    _digest,
    _normalize_ensembl_gene,
    _normalize_openalex_author,
    _normalize_openalex_work,
    _normalize_uniprot,
)

ImportKind = Literal[
    "openalex_authors",
    "openalex_works",
    "ensembl_genes",
    "ncbi_genes",
    "uniprot_proteins",
]


def file_sha256(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def iter_json_lines(path: str | Path) -> Iterator[dict[str, Any]]:
    source = Path(path)
    opener = gzip.open if source.suffix == ".gz" else open
    with opener(source, "rt", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            row = json.loads(text)
            if isinstance(row, dict):
                yield row


def _normalize_ncbi_gene(row: dict[str, Any]) -> dict[str, Any]:
    gene = row.get("gene") if isinstance(row.get("gene"), dict) else row
    gene_id = str(gene.get("gene_id") or gene.get("geneId") or gene.get("geneID") or "")
    symbol = str(gene.get("symbol") or gene.get("gene_symbol") or gene_id)
    if not gene_id:
        gene_id = f"symbol:{symbol}"
    return {
        "entity_type": "gene",
        "canonical_key": f"ncbi:gene:{gene_id}",
        "source_id": "ncbi_datasets",
        "external_id": gene_id,
        "name": symbol,
        "description": gene.get("description"),
        "taxname": gene.get("taxname") or gene.get("tax_name"),
        "tax_id": gene.get("tax_id") or gene.get("taxId"),
        "chromosomes": gene.get("chromosomes") or [],
        "common_name": gene.get("common_name"),
        "nomenclature_authority": gene.get("nomenclature_authority"),
        "type": gene.get("type"),
        "orientation": gene.get("orientation"),
        "genomic_ranges": gene.get("genomic_ranges") or gene.get("genomicRanges") or [],
    }


def normalize_record(kind: ImportKind, row: dict[str, Any]) -> dict[str, Any]:
    if kind == "openalex_authors":
        return _normalize_openalex_author(row)
    if kind == "openalex_works":
        return _normalize_openalex_work(row)
    if kind == "ensembl_genes":
        return _normalize_ensembl_gene(row, str(row.get("display_name") or row.get("id") or "gene"))
    if kind == "ncbi_genes":
        return _normalize_ncbi_gene(row)
    if kind == "uniprot_proteins":
        return _normalize_uniprot(row)
    raise ValueError(f"unsupported import kind: {kind}")


class ScienceImportStore:
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
                CREATE TABLE IF NOT EXISTS science_source_releases (
                    workspace_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    release_id TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    byte_size INTEGER NOT NULL,
                    registered_at INTEGER NOT NULL,
                    PRIMARY KEY(workspace_id, source_id, release_id, source_sha256)
                );

                CREATE TABLE IF NOT EXISTS science_import_checkpoints (
                    workspace_id TEXT NOT NULL,
                    import_key TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    release_id TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    last_record_index INTEGER NOT NULL DEFAULT -1,
                    records_seen INTEGER NOT NULL DEFAULT 0,
                    entities_written INTEGER NOT NULL DEFAULT 0,
                    errors INTEGER NOT NULL DEFAULT 0,
                    started_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    completed_at INTEGER,
                    PRIMARY KEY(workspace_id, import_key)
                );
                """
            )
            conn.commit()

    @staticmethod
    def import_key(kind: str, release_id: str, source_sha256: str) -> str:
        return _digest({"kind": kind, "release_id": release_id, "source_sha256": source_sha256})

    def register_release(
        self,
        workspace_id: str,
        *,
        source_id: str,
        release_id: str,
        source_path: str,
        source_sha256: str,
        byte_size: int,
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO science_source_releases(
                    workspace_id, source_id, release_id, source_path,
                    source_sha256, byte_size, registered_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workspace_id,
                    source_id,
                    release_id,
                    source_path,
                    source_sha256,
                    byte_size,
                    int(time.time()),
                ),
            )
            conn.commit()

    def checkpoint(self, workspace_id: str, import_key: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM science_import_checkpoints WHERE workspace_id=? AND import_key=?",
                (workspace_id, import_key),
            ).fetchone()
        return dict(row) if row else None

    def start(
        self,
        workspace_id: str,
        *,
        import_key: str,
        kind: str,
        release_id: str,
        source_sha256: str,
        source_path: str,
    ) -> dict[str, Any]:
        now = int(time.time())
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO science_import_checkpoints(
                    workspace_id, import_key, kind, release_id, source_sha256,
                    source_path, status, started_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'running', ?, ?)
                ON CONFLICT(workspace_id, import_key) DO UPDATE SET
                    status=CASE
                        WHEN science_import_checkpoints.status='complete' THEN 'complete'
                        ELSE 'running'
                    END,
                    updated_at=excluded.updated_at
                """,
                (
                    workspace_id,
                    import_key,
                    kind,
                    release_id,
                    source_sha256,
                    source_path,
                    now,
                    now,
                ),
            )
            conn.commit()
        return self.checkpoint(workspace_id, import_key) or {}

    def update(
        self,
        workspace_id: str,
        import_key: str,
        *,
        last_record_index: int,
        records_seen: int,
        entities_written: int,
        errors: int,
        status: str = "running",
    ) -> None:
        completed_at = int(time.time()) if status == "complete" else None
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE science_import_checkpoints
                SET status=?, last_record_index=?, records_seen=?, entities_written=?,
                    errors=?, updated_at=?, completed_at=?
                WHERE workspace_id=? AND import_key=?
                """,
                (
                    status,
                    last_record_index,
                    records_seen,
                    entities_written,
                    errors,
                    int(time.time()),
                    completed_at,
                    workspace_id,
                    import_key,
                ),
            )
            conn.commit()


def _source_id_for_kind(kind: ImportKind) -> str:
    return {
        "openalex_authors": "openalex",
        "openalex_works": "openalex",
        "ensembl_genes": "ensembl",
        "ncbi_genes": "ncbi_datasets",
        "uniprot_proteins": "uniprot",
    }[kind]


def _batches(rows: Iterable[dict[str, Any]], size: int) -> Iterator[list[dict[str, Any]]]:
    batch: list[dict[str, Any]] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def import_jsonl(
    *,
    workspace_id: str,
    kind: ImportKind,
    path: str | Path,
    release_id: str,
    graph_store: ScienceGraphStore | None = None,
    import_store: ScienceImportStore | None = None,
    batch_size: int = 500,
    checkpoint_every: int = 1000,
    max_records: int | None = None,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    actual_sha256 = file_sha256(source)
    if expected_sha256 and actual_sha256.lower() != expected_sha256.lower():
        raise ValueError("source sha256 does not match expected checksum")

    graph = graph_store or ScienceGraphStore()
    imports = import_store or ScienceImportStore()
    source_id = _source_id_for_kind(kind)
    imports.register_release(
        workspace_id,
        source_id=source_id,
        release_id=release_id,
        source_path=str(source),
        source_sha256=actual_sha256,
        byte_size=source.stat().st_size,
    )
    key = imports.import_key(kind, release_id, actual_sha256)
    checkpoint = imports.start(
        workspace_id,
        import_key=key,
        kind=kind,
        release_id=release_id,
        source_sha256=actual_sha256,
        source_path=str(source),
    )
    if checkpoint.get("status") == "complete":
        return {"status": "complete", "resumed": True, **checkpoint}

    resume_after = int(checkpoint.get("last_record_index", -1))
    records_seen = int(checkpoint.get("records_seen", 0))
    entities_written = int(checkpoint.get("entities_written", 0))
    errors = int(checkpoint.get("errors", 0))
    last_index = resume_after
    pending: list[dict[str, Any]] = []

    try:
        for index, raw in enumerate(iter_json_lines(source)):
            if index <= resume_after:
                continue
            if max_records is not None and records_seen >= max_records:
                break
            last_index = index
            records_seen += 1
            try:
                normalized = normalize_record(kind, raw)
                normalized["source_release"] = release_id
                normalized["source_file_sha256"] = actual_sha256
                normalized["source_record_digest"] = _digest(raw)
                pending.append(normalized)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                errors += 1

            if len(pending) >= batch_size:
                entities_written += graph.upsert_entities(workspace_id, pending)
                pending = []

            if records_seen % checkpoint_every == 0:
                if pending:
                    entities_written += graph.upsert_entities(workspace_id, pending)
                    pending = []
                imports.update(
                    workspace_id,
                    key,
                    last_record_index=last_index,
                    records_seen=records_seen,
                    entities_written=entities_written,
                    errors=errors,
                )

        if pending:
            entities_written += graph.upsert_entities(workspace_id, pending)
        imports.update(
            workspace_id,
            key,
            last_record_index=last_index,
            records_seen=records_seen,
            entities_written=entities_written,
            errors=errors,
            status="complete" if max_records is None else "paused",
        )
    except Exception:
        imports.update(
            workspace_id,
            key,
            last_record_index=last_index,
            records_seen=records_seen,
            entities_written=entities_written,
            errors=errors + 1,
            status="failed",
        )
        raise

    return {
        "status": "complete" if max_records is None else "paused",
        "import_key": key,
        "kind": kind,
        "source_id": source_id,
        "release_id": release_id,
        "source_sha256": actual_sha256,
        "last_record_index": last_index,
        "records_seen": records_seen,
        "entities_written": entities_written,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="OSIRIS Science Genome resumable JSONL importer")
    parser.add_argument("--kind", required=True, choices=[
        "openalex_authors",
        "openalex_works",
        "ensembl_genes",
        "ncbi_genes",
        "uniprot_proteins",
    ])
    parser.add_argument("--path", required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--workspace", default="reference")
    parser.add_argument("--expected-sha256")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--checkpoint-every", type=int, default=1000)
    parser.add_argument("--max-records", type=int)
    args = parser.parse_args()
    result = import_jsonl(
        workspace_id=args.workspace,
        kind=args.kind,
        path=args.path,
        release_id=args.release,
        batch_size=max(1, args.batch_size),
        checkpoint_every=max(1, args.checkpoint_every),
        max_records=args.max_records,
        expected_sha256=args.expected_sha256,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
