from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path

TABLES = (
    "audit_events",
    "evidence_snapshots",
    "pilot_runs",
    "crypto_nonces",
)


def integrity(path: Path) -> str:
    with sqlite3.connect(path) as conn:
        return str(conn.execute("PRAGMA integrity_check").fetchone()[0])


def existing_tables(path: Path) -> set[str]:
    with sqlite3.connect(path) as conn:
        return {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}


def counts(path: Path, tables: set[str]) -> dict[str, int]:
    output: dict[str, int] = {}
    with sqlite3.connect(path) as conn:
        for table in sorted(tables):
            if table in TABLES or table.startswith("privacy_") or table.startswith("enterprise_"):
                safe = table.replace('"', '""')
                output[table] = int(conn.execute(f'SELECT COUNT(*) FROM "{safe}"').fetchone()[0])
    return output


def sqlite_backup(source: Path, destination: Path) -> None:
    with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)


def run() -> dict[str, object]:
    source = Path(os.getenv("ORBYTHRA_DB_PATH", "./data/orbythra.db")).expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"database_not_found:{source}")

    started = time.perf_counter()
    source_integrity = integrity(source)
    source_tables = existing_tables(source)
    source_counts = counts(source, source_tables)

    with tempfile.TemporaryDirectory(prefix="orbythra-restore-") as tmp:
        backup = Path(tmp) / "backup.db"
        restored = Path(tmp) / "restored.db"
        sqlite_backup(source, backup)
        backup_integrity = integrity(backup)
        sqlite_backup(backup, restored)
        restored_integrity = integrity(restored)
        restored_tables = existing_tables(restored)
        restored_counts = counts(restored, restored_tables)

    passed = (
        source_integrity == "ok"
        and backup_integrity == "ok"
        and restored_integrity == "ok"
        and source_tables == restored_tables
        and source_counts == restored_counts
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    return {
        "drill": "sqlite_backup_restore",
        "passed": passed,
        "source_integrity": source_integrity,
        "backup_integrity": backup_integrity,
        "restored_integrity": restored_integrity,
        "table_count": len(source_tables),
        "tracked_row_counts": source_counts,
        "elapsed_ms": elapsed_ms,
        "validation_boundary": "CI/evaluation SQLite restore drill; production PostgreSQL restore and measured RPO/RTO remain deployment evidence",
    }


def main() -> int:
    report = run()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
