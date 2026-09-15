from __future__ import annotations

import argparse
import json
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from science_importer import ImportKind, ScienceImportStore, import_jsonl
from science_world import ScienceGraphStore


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_ingest_benchmark(
    *,
    kind: ImportKind,
    path: str | Path,
    release_id: str,
    max_records: int | None = None,
    batch_size: int = 500,
    checkpoint_every: int = 1000,
    workspace_id: str = "benchmark",
    database_path: str | None = None,
) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)

    temp: tempfile.TemporaryDirectory[str] | None = None
    if database_path is None:
        temp = tempfile.TemporaryDirectory(prefix="orbythra-ingest-")
        database_path = str(Path(temp.name) / "science.sqlite3")

    try:
        graph = ScienceGraphStore(database_path)
        imports = ScienceImportStore(database_path)
        started = time.perf_counter()
        result = import_jsonl(
            workspace_id=workspace_id,
            kind=kind,
            path=source,
            release_id=release_id,
            graph_store=graph,
            import_store=imports,
            batch_size=max(1, batch_size),
            checkpoint_every=max(1, checkpoint_every),
            max_records=max_records,
        )
        elapsed = max(time.perf_counter() - started, 1e-9)
        records = int(result.get("records_seen", 0))
        entities = int(result.get("entities_written", 0))
        db = Path(database_path)
        return {
            "schema": "orbythra.dataset-ingest-benchmark.v1",
            "product": "ORBYTHRA",
            "generated_at": _utc_now(),
            "measurement_scope": "actual_science_importer_path",
            "real_input_file": True,
            "production_scale_claim": False,
            "kind": kind,
            "release_id": release_id,
            "source_path": source.name,
            "source_bytes": source.stat().st_size,
            "source_sha256": result.get("source_sha256"),
            "max_records": max_records,
            "elapsed_seconds": round(elapsed, 6),
            "records_seen": records,
            "entities_written": entities,
            "errors": int(result.get("errors", 0)),
            "records_per_second": round(records / elapsed, 3),
            "entities_per_second": round(entities / elapsed, 3),
            "database_bytes": db.stat().st_size if db.exists() else 0,
            "entity_counts": graph.counts(workspace_id),
            "import_result": result,
            "claim_boundary": (
                "This measures the real ORBYTHRA importer on the supplied file. It is not labelled "
                "production-scale until a diligence record identifies the real source snapshot, release, "
                "size and operating environment."
            ),
        }
    finally:
        if temp is not None:
            temp.cleanup()


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure ORBYTHRA real-file science ingest throughput")
    parser.add_argument(
        "--kind",
        required=True,
        choices=[
            "openalex_authors",
            "openalex_works",
            "ensembl_genes",
            "ncbi_genes",
            "uniprot_proteins",
        ],
    )
    parser.add_argument("--path", required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--workspace", default="benchmark")
    parser.add_argument("--max-records", type=int)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--checkpoint-every", type=int, default=1000)
    parser.add_argument("--database-path")
    parser.add_argument("--output")
    args = parser.parse_args()

    result = run_ingest_benchmark(
        kind=args.kind,
        path=args.path,
        release_id=args.release,
        max_records=args.max_records,
        batch_size=args.batch_size,
        checkpoint_every=args.checkpoint_every,
        workspace_id=args.workspace,
        database_path=args.database_path,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
