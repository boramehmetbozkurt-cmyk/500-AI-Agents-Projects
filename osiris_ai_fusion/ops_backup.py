from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def sqlite_integrity(path: str | Path) -> str:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    uri = f"file:{source.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=10) as conn:
        row = conn.execute("PRAGMA integrity_check").fetchone()
    result = str(row[0] if row else "missing")
    if result.lower() != "ok":
        raise ValueError(f"SQLite integrity_check failed: {result}")
    return result


def table_counts(path: str | Path) -> dict[str, int]:
    source = Path(path)
    uri = f"file:{source.resolve().as_posix()}?mode=ro"
    counts: dict[str, int] = {}
    with sqlite3.connect(uri, uri=True, timeout=10) as conn:
        names = [
            str(row[0])
            for row in conn.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
        ]
        for name in names:
            escaped = name.replace('"', '""')
            counts[name] = int(conn.execute(f'SELECT COUNT(*) FROM "{escaped}"').fetchone()[0])
    return counts


def create_backup(
    source_path: str | Path,
    output_dir: str | Path,
    *,
    label: str = "osiris",
) -> dict[str, Any]:
    source = Path(source_path)
    if not source.is_file():
        raise FileNotFoundError(source)
    sqlite_integrity(source)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    backup = output / f"{label}-{timestamp}.sqlite3"
    temp = output / f".{backup.name}.tmp"
    if temp.exists():
        temp.unlink()

    source_uri = f"file:{source.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(source_uri, uri=True, timeout=10) as src, sqlite3.connect(temp) as dst:
        src.backup(dst)
        dst.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    os.replace(temp, backup)
    sqlite_integrity(backup)

    manifest = {
        "schema": "osiris.sqlite-backup.v1",
        "created_at": timestamp,
        "source": source.name,
        "backup": backup.name,
        "sha256": sha256_file(backup),
        "bytes": backup.stat().st_size,
        "integrity_check": "ok",
        "table_counts": table_counts(backup),
    }
    manifest_path = backup.with_suffix(backup.suffix + ".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"backup_path": str(backup), "manifest_path": str(manifest_path), **manifest}


def verify_backup(backup_path: str | Path, manifest_path: str | Path | None = None) -> dict[str, Any]:
    backup = Path(backup_path)
    manifest_file = Path(manifest_path) if manifest_path else backup.with_suffix(backup.suffix + ".manifest.json")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    actual_hash = sha256_file(backup)
    if actual_hash != manifest.get("sha256"):
        raise ValueError("Backup SHA256 does not match manifest")
    sqlite_integrity(backup)
    actual_counts = table_counts(backup)
    if actual_counts != manifest.get("table_counts"):
        raise ValueError("Backup table counts do not match manifest")
    return {"valid": True, "sha256": actual_hash, "table_counts": actual_counts}


def restore_backup(
    backup_path: str | Path,
    target_path: str | Path,
    *,
    manifest_path: str | Path | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    backup = Path(backup_path)
    target = Path(target_path)
    verification = verify_backup(backup, manifest_path)
    if target.exists() and not overwrite:
        raise FileExistsError(f"restore target already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".restore.tmp")
    if temp.exists():
        temp.unlink()
    source_uri = f"file:{backup.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(source_uri, uri=True, timeout=10) as src, sqlite3.connect(temp) as dst:
        src.backup(dst)
    sqlite_integrity(temp)
    if table_counts(temp) != verification["table_counts"]:
        temp.unlink(missing_ok=True)
        raise ValueError("Restored database table counts differ from verified backup")
    os.replace(temp, target)
    return {
        "restored": True,
        "target": str(target),
        "sha256": sha256_file(target),
        "integrity_check": "ok",
        "table_counts": table_counts(target),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="OSIRIS integrity-checked SQLite backup/restore")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create")
    create.add_argument("source")
    create.add_argument("output_dir")
    create.add_argument("--label", default="osiris")

    verify = sub.add_parser("verify")
    verify.add_argument("backup")
    verify.add_argument("--manifest")

    restore = sub.add_parser("restore")
    restore.add_argument("backup")
    restore.add_argument("target")
    restore.add_argument("--manifest")
    restore.add_argument("--overwrite", action="store_true")

    args = parser.parse_args()
    if args.command == "create":
        result = create_backup(args.source, args.output_dir, label=args.label)
    elif args.command == "verify":
        result = verify_backup(args.backup, args.manifest)
    else:
        result = restore_backup(
            args.backup,
            args.target,
            manifest_path=args.manifest,
            overwrite=args.overwrite,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
