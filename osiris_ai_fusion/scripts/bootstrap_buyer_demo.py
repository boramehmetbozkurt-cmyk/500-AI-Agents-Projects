from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reality_atlas import (  # noqa: E402
    AtlasFeatureCreate,
    CoordinateSpace,
    GeoPoseAnchor,
    HistoricalDate,
    RealityAtlasStore,
    TemporalExtent,
)
from science_world import ScienceGraphStore  # noqa: E402
from world import WorldEventCreate, WorldForkCreate, WorldStore  # noqa: E402


def build_demo(output: Path) -> dict[str, object]:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    db_path = output / "orbythra-demo.sqlite3"
    workspace = "default"

    world = WorldStore(str(db_path))
    world.append_batch(
        workspace,
        [
            WorldEventCreate(
                entity_id="orbythra",
                entity_type="technology_platform",
                entity_label="ORBYTHRA",
                predicate="capability",
                value="verifiable_temporal_reality_os",
                statement_kind="fact",
                confidence=1.0,
                evidence_ids=["demo:architecture"],
                source_ids=["demo:release"],
            ),
            WorldEventCreate(
                entity_id="industrial_world_models",
                entity_type="technology_trend",
                entity_label="Industrial World Models",
                predicate="adoption_signal",
                value="rising",
                statement_kind="claim",
                confidence=0.82,
                evidence_ids=["demo:market-evidence"],
                source_ids=["demo:market-source"],
            ),
            WorldEventCreate(
                entity_id="science_genome_graph",
                entity_type="science_infrastructure",
                entity_label="Science Genome Graph",
                predicate="connected_to",
                value="orbythra",
                object_entity_id="orbythra",
                object_entity_type="technology_platform",
                object_entity_label="ORBYTHRA",
                statement_kind="fact",
                confidence=1.0,
                evidence_ids=["demo:science-bridge-test"],
                source_ids=["demo:release"],
            ),
        ],
    )
    fork = world.create_fork(
        workspace,
        WorldForkCreate(
            name="Accelerated industrial adoption",
            hypothesis="Industrial digital-twin adoption accelerates materially over baseline.",
        ),
    )
    world.append_event(
        workspace,
        WorldEventCreate(
            entity_id="industrial_world_models",
            entity_type="technology_trend",
            entity_label="Industrial World Models",
            predicate="adoption_signal",
            value="accelerated",
            statement_kind="assumption",
            confidence=0.65,
            evidence_ids=["demo:scenario-assumption"],
            source_ids=["demo:buyer-demo"],
            branch_id=str(fork["id"]),
        ),
    )

    atlas = RealityAtlasStore(str(db_path))
    atlas.upsert_batch(
        workspace,
        [
            AtlasFeatureCreate(
                feature_id="demo_izmir_present",
                name="Izmir present-day demonstrator",
                feature_type="city_demo",
                realm="physical",
                truth_mode="claim",
                confidence=0.95,
                temporal=TemporalExtent(start=HistoricalDate(year=2026), open_ended=True),
                space=CoordinateSpace(
                    space_id="earth",
                    kind="earth_geodetic",
                    crs="EPSG:4979",
                    earth_anchor=GeoPoseAnchor(latitude=38.4237, longitude=27.1428),
                ),
                source_ids=["demo:geospatial"],
                metadata={"synthetic_demo_record": True},
            ),
            AtlasFeatureCreate(
                feature_id="demo_izmir_future",
                name="Izmir future digital-twin scenario",
                feature_type="digital_twin_demo",
                realm="digital_twin",
                truth_mode="planned",
                confidence=0.55,
                temporal=TemporalExtent(start=HistoricalDate(year=2030), open_ended=True),
                space=CoordinateSpace(
                    space_id="izmir-digital-twin",
                    kind="digital_twin",
                    earth_anchor=GeoPoseAnchor(latitude=38.4237, longitude=27.1428),
                    platform="ORBYTHRA buyer demo",
                ),
                source_ids=["demo:scenario"],
                metadata={"synthetic_demo_record": True},
            ),
        ],
    )

    science = ScienceGraphStore(str(db_path))
    science.upsert_entities(
        workspace,
        [
            {
                "entity_type": "gene",
                "canonical_key": "demo:gene:BRCA1",
                "source_id": "demo_reference",
                "external_id": "BRCA1",
                "name": "BRCA1",
                "medical_use": "illustrative_demo_only",
                "synthetic_demo_record": True,
            },
            {
                "entity_type": "protein",
                "canonical_key": "demo:protein:BRCA1",
                "source_id": "demo_reference",
                "external_id": "BRCA1-protein",
                "name": "BRCA1 protein demo node",
                "medical_use": "illustrative_demo_only",
                "synthetic_demo_record": True,
            },
            {
                "entity_type": "scientist",
                "canonical_key": "demo:scientist:example",
                "source_id": "demo_reference",
                "external_id": "example-scientist",
                "name": "Example Scientist",
                "synthetic_demo_record": True,
            },
        ],
    )

    manifest = {
        "schema": "orbythra.buyer-demo.v1",
        "workspace_id": workspace,
        "database": db_path.name,
        "requires_external_secrets": False,
        "network_required_for_seed": False,
        "records": {
            "world_state": world.snapshot(workspace)["state_count"],
            "world_branches": len(world.list_branches(workspace)),
            "science_entities": science.counts(workspace),
            "atlas_features": 2,
        },
        "safety": {
            "synthetic_or_illustrative": True,
            "medical_decisions": False,
            "transaction_signing": False,
        },
        "launch": (
            "APP_ENV=development SAAS_ENABLED=false UI_ENABLED=true "
            f"FUSION_STORE_PATH={db_path.as_posix()} uvicorn app:app --host 127.0.0.1 --port 8787"
        ),
        "entrypoints": [
            "/",
            "/world-globe",
            "/science-explorer",
            "/engineering-lab",
            "/intelligence",
        ],
    }
    (output / "demo-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output / "README.txt").write_text(
        "ORBYTHRA buyer-safe local demo\n\n"
        "This seed contains illustrative data only and needs no provider/API secrets.\n"
        "Run from the osiris_ai_fusion directory:\n\n"
        + str(manifest["launch"])
        + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a reproducible ORBYTHRA buyer demo")
    parser.add_argument("--output", default="dist/buyer-demo")
    args = parser.parse_args()
    manifest = build_demo(Path(args.output))
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
