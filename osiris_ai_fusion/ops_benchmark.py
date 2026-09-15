from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path
from typing import Any

import science_world_bridge as bridge_module
from science_edges import ScienceEdgeStore
from science_world import ScienceGraphStore
from science_world_bridge import ScienceWorldBridgeStore
from world import WorldStore


def _rate(count: int, elapsed: float) -> float:
    return round(count / max(elapsed, 1e-9), 2)


def run_benchmark(entity_count: int = 1000, work_count: int = 1000) -> dict[str, Any]:
    entity_count = max(1, int(entity_count))
    work_count = max(1, int(work_count))
    with tempfile.TemporaryDirectory(prefix="osiris-benchmark-") as temp:
        db = str(Path(temp) / "bench.sqlite3")
        science = ScienceGraphStore(db)
        edges = ScienceEdgeStore(db)
        world = WorldStore(db)
        bridge = ScienceWorldBridgeStore(db)
        original_world = bridge_module.world_store
        bridge_module.world_store = world
        try:
            scientists = [
                {
                    "entity_type": "scientist",
                    "canonical_key": f"openalex:author:A{i}",
                    "source_id": "openalex",
                    "external_id": f"A{i}",
                    "name": f"Scientist {i}",
                    "institutions": [{"id": f"I{i % 100}", "name": f"Institution {i % 100}"}],
                    "topics": [{"id": f"T{i % 40}", "name": f"Topic {i % 40}", "score": 0.9}],
                }
                for i in range(entity_count)
            ]
            works = [
                {
                    "entity_type": "work",
                    "canonical_key": f"openalex:work:W{i}",
                    "source_id": "openalex",
                    "external_id": f"W{i}",
                    "name": f"Work {i}",
                    "authors": [
                        {
                            "id": f"A{i % entity_count}",
                            "name": f"Scientist {i % entity_count}",
                            "position": "first",
                        }
                    ],
                    "topics": [{"id": f"T{i % 40}", "name": f"Topic {i % 40}", "score": 0.8}],
                }
                for i in range(work_count)
            ]

            started = time.perf_counter()
            written = science.upsert_entities("bench", [*scientists, *works])
            ingest_elapsed = time.perf_counter() - started

            started = time.perf_counter()
            graph_result = edges.rebuild("bench", limit=entity_count + work_count + 10)
            edge_elapsed = time.perf_counter() - started

            started = time.perf_counter()
            bridge_result = bridge.sync(
                "bench",
                entity_limit=entity_count + work_count + 10,
                edge_limit=graph_result["edges_written"] + 10,
            )
            bridge_elapsed = time.perf_counter() - started

            started = time.perf_counter()
            snapshot = world.snapshot("bench")
            snapshot_elapsed = time.perf_counter() - started

            started = time.perf_counter()
            graph = world.graph("bench", limit=min(500, entity_count + work_count))
            graph_elapsed = time.perf_counter() - started

            return {
                "schema": "osiris.core-benchmark.v1",
                "synthetic": True,
                "database": "sqlite",
                "input": {"scientists": entity_count, "works": work_count},
                "entity_ingest": {
                    "written": written,
                    "seconds": round(ingest_elapsed, 6),
                    "records_per_second": _rate(written, ingest_elapsed),
                },
                "relationship_rebuild": {
                    **graph_result,
                    "seconds": round(edge_elapsed, 6),
                    "edges_per_second": _rate(graph_result["edges_written"], edge_elapsed),
                },
                "world_bridge": {
                    **bridge_result,
                    "seconds": round(bridge_elapsed, 6),
                    "events_per_second": _rate(
                        bridge_result["entity_events_created"] + bridge_result["edge_events_created"],
                        bridge_elapsed,
                    ),
                },
                "world_snapshot": {
                    "state_count": snapshot["state_count"],
                    "seconds": round(snapshot_elapsed, 6),
                },
                "world_graph": {
                    "nodes": len(graph["nodes"]),
                    "edges": len(graph["edges"]),
                    "seconds": round(graph_elapsed, 6),
                },
                "interpretation": (
                    "Synthetic single-process SQLite benchmark for repeatability/regression only; "
                    "it is not a production capacity claim or cloud SLA."
                ),
            }
        finally:
            bridge_module.world_store = original_world


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a reproducible OSIRIS core benchmark")
    parser.add_argument("--scientists", type=int, default=1000)
    parser.add_argument("--works", type=int, default=1000)
    parser.add_argument("--output")
    args = parser.parse_args()
    result = run_benchmark(args.scientists, args.works)
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
