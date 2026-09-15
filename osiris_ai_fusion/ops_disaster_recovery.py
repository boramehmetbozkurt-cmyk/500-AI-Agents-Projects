from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any

from ops_backup import create_backup, restore_backup, table_counts


def _seed(path: Path, rows: int) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE evidence(id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        conn.executemany(
            "INSERT INTO evidence(payload) VALUES (?)",
            [(f"row-{index}",) for index in range(rows)],
        )
        conn.commit()


def exercise(source_path: str | Path | None = None, *, rows: int = 1000) -> dict[str, Any]:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="orbythra-dr-") as temp_dir:
        temp = Path(temp_dir)
        source = Path(source_path) if source_path else temp / "source.sqlite3"
        if source_path is None:
            _seed(source, max(1, rows))
        before = table_counts(source)

        backup_started = time.perf_counter()
        backup = create_backup(source, temp / "backups", label="orbythra-dr")
        backup_seconds = time.perf_counter() - backup_started

        restore_target = temp / "restored.sqlite3"
        restore_started = time.perf_counter()
        restored = restore_backup(
            backup["backup_path"],
            restore_target,
            manifest_path=backup["manifest_path"],
        )
        restore_seconds = time.perf_counter() - restore_started
        after = table_counts(restore_target)
        if before != after:
            raise AssertionError("restored table counts do not match source")

        total = time.perf_counter() - started
        return {
            "schema": "orbythra.disaster-recovery-evidence.v1",
            "exercise_type": "backup_restore_integrity",
            "production_exercise": source_path is not None,
            "source_table_counts": before,
            "restored_table_counts": after,
            "backup_sha256": backup["sha256"],
            "restored_sha256": restored["sha256"],
            "backup_seconds": round(backup_seconds, 6),
            "restore_seconds": round(restore_seconds, 6),
            "total_seconds": round(total, 6),
            "rto_observed_seconds": round(restore_seconds, 6),
            "rpo_claim_seconds": None,
            "integrity_verified": True,
            "interpretation": (
                "A reproducible integrity-checked restore exercise. When source_path is omitted it is a "
                "synthetic resilience regression, not production disaster-recovery evidence. A real RPO "
                "claim requires actual production backup cadence and timestamped operational evidence."
            ),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an ORBYTHRA disaster-recovery evidence exercise")
    parser.add_argument("--source")
    parser.add_argument("--rows", type=int, default=1000)
    parser.add_argument("--output")
    args = parser.parse_args()
    result = exercise(args.source, rows=args.rows)
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
