from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from build_asset_carveout import REPO_ROOT, ROOT, source_files


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_standalone(output_dir: str | Path, *, init_git: bool = False) -> dict[str, object]:
    output = Path(output_dir).resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    manifest_files: list[dict[str, object]] = []
    for source in source_files():
        relative = source.relative_to(ROOT)
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        manifest_files.append(
            {
                "path": relative.as_posix(),
                "bytes": destination.stat().st_size,
                "sha256": _sha256(destination),
                "classification": "orbythra_component_or_documentation",
            }
        )

    license_source = REPO_ROOT / "LICENSE"
    if license_source.is_file():
        destination = output / "UPSTREAM-MIT-LICENSE.txt"
        shutil.copy2(license_source, destination)
        manifest_files.append(
            {
                "path": destination.name,
                "bytes": destination.stat().st_size,
                "sha256": _sha256(destination),
                "classification": "required_upstream_license_notice",
            }
        )

    readme = output / "STANDALONE-README.md"
    readme.write_text(
        "# ORBYTHRA Standalone Repository Candidate\n\n"
        "This directory is a git-ready technical carve-out of the ORBYTHRA application subtree.\n\n"
        "It deliberately excludes local databases, backups, caches, .env files and private-key material. "
        "Applicable upstream MIT material remains subject to the included notice and is not represented "
        "as exclusive proprietary IP. The acquisition-facing product name is ORBYTHRA even where legacy "
        "implementation paths retain OSIRIS naming for compatibility.\n\n"
        "Before a transaction, counsel should confirm the final source/IP schedule and contributor assignments.\n",
        encoding="utf-8",
    )
    manifest_files.append(
        {
            "path": readme.name,
            "bytes": readme.stat().st_size,
            "sha256": _sha256(readme),
            "classification": "standalone_boundary_notice",
        }
    )

    manifest = {
        "schema": "orbythra.standalone-repo-candidate.v1",
        "product": "ORBYTHRA",
        "generated_at": _utc_now(),
        "file_count": len(manifest_files),
        "files": sorted(manifest_files, key=lambda row: str(row["path"])),
        "remote_repository_created": False,
        "legal_exclusivity_certified": False,
        "claim_boundary": (
            "This is a git-ready standalone export, not proof that a remote repository has been created "
            "and not a legal opinion on exclusive ownership."
        ),
    }
    manifest_path = output / "STANDALONE-MANIFEST.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    git_initialized = False
    if init_git:
        try:
            subprocess.run(["git", "init", "-b", "main"], cwd=output, check=True)
            subprocess.run(["git", "add", "."], cwd=output, check=True)
            git_initialized = True
        except (OSError, subprocess.CalledProcessError):
            git_initialized = False

    return {
        "output_dir": str(output),
        "manifest": str(manifest_path),
        "file_count": len(manifest_files),
        "git_initialized": git_initialized,
        "remote_repository_created": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a git-ready standalone ORBYTHRA source export")
    parser.add_argument("--output", default="dist/orbythra-standalone")
    parser.add_argument("--init-git", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build_standalone(args.output, init_git=args.init_git), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
