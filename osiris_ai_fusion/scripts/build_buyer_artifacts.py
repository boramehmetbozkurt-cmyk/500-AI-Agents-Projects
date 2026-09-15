from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
EXCLUDED_PARTS = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "dist",
    "data",
}
EXCLUDED_SUFFIXES = {".sqlite3", ".db", ".pyc", ".pyo"}

DATA_RIGHTS = [
    {
        "source": "OpenAlex",
        "data_class": "scholarly metadata",
        "license": "CC0/public domain",
        "commercial_posture": "allowed for metadata",
        "important_boundary": "Full-text PDFs/TEI retain source-content licenses; metadata license does not grant article-content rights.",
        "url": "https://openalex.org/",
    },
    {
        "source": "Wikidata",
        "data_class": "structured knowledge",
        "license": "CC0",
        "commercial_posture": "allowed",
        "important_boundary": "Use dumps rather than WDQS for material bulk mirroring.",
        "url": "https://www.wikidata.org/",
    },
    {
        "source": "NCBI",
        "data_class": "molecular/reference biology",
        "license": "public molecular data with upstream-rights caveat",
        "commercial_posture": "review record/source-specific upstream rights",
        "important_boundary": "NCBI places no restriction on molecular data, but submitters/countries can assert patent/copyright/other rights.",
        "url": "https://www.ncbi.nlm.nih.gov/",
    },
    {
        "source": "Ensembl",
        "data_class": "genome annotation/comparative genomics",
        "license": "project-generated data generally unrestricted",
        "commercial_posture": "review third-party constraints",
        "important_boundary": "Keep stable IDs, assembly/release and source provenance.",
        "url": "https://www.ensembl.org/",
    },
    {
        "source": "UniProt",
        "data_class": "protein knowledge",
        "license": "CC BY 4.0 for copyrightable database parts",
        "commercial_posture": "allowed with attribution and rights review",
        "important_boundary": "Medical/genetic information is informational/research context; other patent/rights can apply.",
        "url": "https://www.uniprot.org/",
    },
    {
        "source": "ClinVar",
        "data_class": "public human variant assertions",
        "license": "NCBI public archive; attribution requested",
        "commercial_posture": "research/information only",
        "important_boundary": "Submitted classifications are assertions and must not be represented as patient-specific diagnosis.",
        "url": "https://www.ncbi.nlm.nih.gov/clinvar/",
    },
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def included_file(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return False
    if path.suffix in EXCLUDED_SUFFIXES:
        return False
    return path.is_file()


def file_inventory() -> list[dict[str, Any]]:
    rows = []
    for path in sorted(ROOT.rglob("*")):
        if not included_file(path):
            continue
        rows.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return rows


def distribution_license(metadata: importlib.metadata.PackageMetadata) -> str:
    expression = metadata.get("License-Expression")
    if expression:
        return expression
    license_value = metadata.get("License")
    if license_value and len(license_value) <= 200:
        return license_value.strip()
    classifiers = metadata.get_all("Classifier") or []
    license_classifiers = [
        item.split(" :: ")[-1]
        for item in classifiers
        if item.startswith("License ::")
    ]
    return "; ".join(license_classifiers) or "NOASSERTION"


def package_inventory() -> list[dict[str, str]]:
    packages: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for dist in importlib.metadata.distributions():
        name = dist.metadata.get("Name") or "unknown"
        version = dist.version or "unknown"
        key = (name.lower(), version)
        if key in seen:
            continue
        seen.add(key)
        packages.append(
            {
                "name": name,
                "version": version,
                "license": distribution_license(dist.metadata),
                "purl": f"pkg:pypi/{name.lower().replace('_', '-')}@{version}",
            }
        )
    return sorted(packages, key=lambda item: (item["name"].lower(), item["version"]))


def root_license() -> dict[str, Any]:
    path = REPO_ROOT / "LICENSE"
    if not path.is_file():
        return {"present": False}
    text = path.read_text(encoding="utf-8", errors="replace")
    first_lines = [line for line in text.splitlines()[:8] if line.strip()]
    return {
        "present": True,
        "path": "../LICENSE",
        "sha256": sha256_file(path),
        "summary": first_lines,
        "classification": "MIT upstream license; preserve copyright and permission notice",
        "exclusivity_note": "MIT upstream material is not exclusive proprietary IP; ORBYTHRA-specific value must be separately inventoried.",
    }


def spdx_document(packages: list[dict[str, str]], generated_at: str) -> dict[str, Any]:
    namespace_seed = os.getenv("GITHUB_SHA") or generated_at
    namespace = hashlib.sha256(namespace_seed.encode("utf-8")).hexdigest()[:24]
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "ORBYTHRA resolved Python environment",
        "documentNamespace": f"https://orbythra.invalid/spdx/{namespace}",
        "creationInfo": {
            "created": generated_at,
            "creators": ["Tool: ORBYTHRA buyer artifact generator"],
        },
        "packages": [
            {
                "name": item["name"],
                "SPDXID": f"SPDXRef-Package-{index}",
                "versionInfo": item["version"],
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": False,
                "licenseConcluded": item["license"] or "NOASSERTION",
                "licenseDeclared": item["license"] or "NOASSERTION",
                "externalRefs": [
                    {
                        "referenceCategory": "PACKAGE-MANAGER",
                        "referenceType": "purl",
                        "referenceLocator": item["purl"],
                    }
                ],
            }
            for index, item in enumerate(packages, start=1)
        ],
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build(output: Path) -> dict[str, Path]:
    output.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    files = file_inventory()
    packages = package_inventory()
    commit = os.getenv("GITHUB_SHA") or "unknown"
    asset = {
        "schema": "orbythra.asset-manifest.v1",
        "generated_at": generated_at,
        "commit": commit,
        "product": "ORBYTHRA — Verifiable Temporal Reality Operating System",
        "version": "1.3.0",
        "files": files,
        "file_count": len(files),
        "total_bytes": sum(int(row["bytes"]) for row in files),
        "root_license": root_license(),
        "data_rights_registry": DATA_RIGHTS,
        "privacy_boundary": "Shared Science Genome Graph excludes patient-identifiable and raw personal genome data.",
        "engineering_intelligence": {
            "prompt_version": "2.0",
            "canonical_prompt": "prompts/engineering_system_v2_tr.md",
            "api": "/engineering/analyze",
        },
    }
    asset_path = output / "orbythra-asset-manifest.json"
    sbom_path = output / "orbythra-python-sbom.spdx.json"
    rights_path = output / "orbythra-data-rights.json"
    hashes_path = output / "orbythra-file-hashes.sha256"
    write_json(asset_path, asset)
    write_json(sbom_path, spdx_document(packages, generated_at))
    write_json(rights_path, {"generated_at": generated_at, "sources": DATA_RIGHTS})
    hashes_path.write_text(
        "".join(f"{row['sha256']}  {row['path']}\n" for row in files),
        encoding="utf-8",
    )
    return {
        "asset_manifest": asset_path,
        "sbom": sbom_path,
        "data_rights": rights_path,
        "file_hashes": hashes_path,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate ORBYTHRA buyer due-diligence artifacts"
    )
    parser.add_argument("--output", default="dist/buyer-dataroom")
    args = parser.parse_args()
    paths = build(Path(args.output))
    print(json.dumps({key: str(value) for key, value in paths.items()}, indent=2))


if __name__ == "__main__":
    main()
