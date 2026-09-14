from __future__ import annotations

import argparse
import hashlib
import json
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "dist",
    "data",
    "backups",
}
EXCLUDED_NAMES = {".env", ".env.production", ".env.local"}
EXCLUDED_SUFFIXES = {".sqlite3", ".db", ".pyc", ".pyo", ".pem", ".key"}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def allowed(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return False
    if path.name in EXCLUDED_NAMES or path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    return path.is_file()


def source_files() -> list[Path]:
    return [path for path in sorted(ROOT.rglob("*")) if allowed(path)]


def build_carveout(output_dir: str | Path) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    commit = os.getenv("GITHUB_SHA") or "unknown"
    generated = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    short = commit[:12] if commit != "unknown" else "local"
    archive = output / f"osiris-fusion-v1.3-carveout-{short}.zip"
    files = source_files()
    manifest_files: list[dict[str, Any]] = []

    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in files:
            relative = path.relative_to(ROOT).as_posix()
            data = path.read_bytes()
            archive_path = f"osiris_ai_fusion/{relative}"
            bundle.writestr(archive_path, data)
            manifest_files.append(
                {
                    "path": archive_path,
                    "bytes": len(data),
                    "sha256": sha256_bytes(data),
                    "classification": "osiris_component_or_documentation",
                }
            )

        root_license = REPO_ROOT / "LICENSE"
        if root_license.is_file():
            data = root_license.read_bytes()
            bundle.writestr("UPSTREAM-MIT-LICENSE.txt", data)
            manifest_files.append(
                {
                    "path": "UPSTREAM-MIT-LICENSE.txt",
                    "bytes": len(data),
                    "sha256": sha256_bytes(data),
                    "classification": "required_upstream_license_notice",
                }
            )

        carveout_readme = (
            "OSIRIS Fusion v1.3 asset carve-out candidate\n\n"
            "This archive isolates the OSIRIS application subtree for buyer review. "
            "It is not a legal certification of exclusive ownership. Review THIRD_PARTY_NOTICES.md, "
            "the included upstream MIT license, generated SBOM/data-rights artifacts and Git provenance.\n\n"
            "Excluded by design: local databases, backups, caches, private keys, .env files and generated dist output.\n"
        ).encode("utf-8")
        bundle.writestr("CARVEOUT-README.txt", carveout_readme)
        manifest_files.append(
            {
                "path": "CARVEOUT-README.txt",
                "bytes": len(carveout_readme),
                "sha256": sha256_bytes(carveout_readme),
                "classification": "carveout_disclaimer",
            }
        )

        manifest = {
            "schema": "osiris.asset-carveout.v1",
            "product": "OSIRIS Fusion / OSIRIS World",
            "version": "1.3.0",
            "commit": commit,
            "generated_at": generated,
            "file_count": len(manifest_files),
            "files": manifest_files,
            "exclusions": {
                "parts": sorted(EXCLUDED_PARTS),
                "names": sorted(EXCLUDED_NAMES),
                "suffixes": sorted(EXCLUDED_SUFFIXES),
            },
            "ownership_boundary": (
                "Carve-out candidate for technical due diligence; upstream/open-source material remains "
                "subject to its licenses and is not represented as exclusive proprietary IP."
            ),
        }
        manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        bundle.writestr("CARVEOUT-MANIFEST.json", manifest_bytes)

    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    receipt = {
        "archive": archive.name,
        "sha256": archive_hash,
        "bytes": archive.stat().st_size,
        "commit": commit,
        "generated_at": generated,
        "source_file_count": len(files),
    }
    receipt_path = archive.with_suffix(".receipt.json")
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"archive_path": str(archive), "receipt_path": str(receipt_path), **receipt}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build OSIRIS-only asset carve-out ZIP")
    parser.add_argument("--output", default="dist/buyer-dataroom")
    args = parser.parse_args()
    print(json.dumps(build_carveout(args.output), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
