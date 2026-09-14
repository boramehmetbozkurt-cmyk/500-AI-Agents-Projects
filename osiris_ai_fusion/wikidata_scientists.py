from __future__ import annotations

import argparse
import bz2
import gzip
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterator

SCIENTIST_QID = "Q901"
HUMAN_QID = "Q5"
PROP_INSTANCE_OF = "P31"
PROP_SUBCLASS_OF = "P279"
PROP_OCCUPATION = "P106"
PROP_ORCID = "P496"
PROP_BIRTH = "P569"
PROP_DEATH = "P570"
PROP_FIELD = "P101"
PROP_EDUCATED_AT = "P69"
PROP_AWARD = "P166"
PROP_NOTABLE_WORK = "P800"


def _open_text(path: Path):
    if path.suffix == ".bz2":
        return bz2.open(path, "rt", encoding="utf-8")
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("rt", encoding="utf-8")


def iter_wikidata_entities(path: str | Path) -> Iterator[dict[str, Any]]:
    source = Path(path)
    with _open_text(source) as handle:
        for raw in handle:
            text = raw.strip()
            if not text or text in {"[", "]"}:
                continue
            if text.endswith(","):
                text = text[:-1]
            try:
                row = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("type") == "item" and row.get("id"):
                yield row


def _snak_value(statement: dict[str, Any]) -> Any:
    mainsnak = statement.get("mainsnak") or {}
    if mainsnak.get("snaktype") != "value":
        return None
    datavalue = mainsnak.get("datavalue") or {}
    return datavalue.get("value")


def entity_ids(entity: dict[str, Any], prop: str) -> list[str]:
    values: list[str] = []
    for statement in (entity.get("claims") or {}).get(prop) or []:
        if not isinstance(statement, dict):
            continue
        value = _snak_value(statement)
        if isinstance(value, dict):
            entity_id = value.get("id")
            if entity_id:
                values.append(str(entity_id))
    return list(dict.fromkeys(values))


def string_values(entity: dict[str, Any], prop: str) -> list[str]:
    values: list[str] = []
    for statement in (entity.get("claims") or {}).get(prop) or []:
        if not isinstance(statement, dict):
            continue
        value = _snak_value(statement)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    return list(dict.fromkeys(values))


def time_values(entity: dict[str, Any], prop: str) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for statement in (entity.get("claims") or {}).get(prop) or []:
        if not isinstance(statement, dict):
            continue
        value = _snak_value(statement)
        if isinstance(value, dict) and value.get("time"):
            values.append(
                {
                    "time": value.get("time"),
                    "precision": value.get("precision"),
                    "calendarmodel": value.get("calendarmodel"),
                    "before": value.get("before"),
                    "after": value.get("after"),
                }
            )
    return values


def label_for(entity: dict[str, Any]) -> str:
    labels = entity.get("labels") or {}
    for language in ("en", "tr"):
        value = labels.get(language)
        if isinstance(value, dict) and value.get("value"):
            return str(value["value"])
    for value in labels.values():
        if isinstance(value, dict) and value.get("value"):
            return str(value["value"])
    return str(entity.get("id") or "")


def aliases_for(entity: dict[str, Any], limit: int = 50) -> list[str]:
    aliases = entity.get("aliases") or {}
    values: list[str] = []
    for language in ("en", "tr"):
        for item in aliases.get(language) or []:
            if isinstance(item, dict) and item.get("value"):
                values.append(str(item["value"]))
    return list(dict.fromkeys(values))[:limit]


def build_scientist_taxonomy(
    dump_path: str | Path,
    taxonomy_db: str | Path,
    *,
    reset: bool = False,
) -> dict[str, int]:
    db_path = Path(taxonomy_db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subclass_edges(
                child TEXT NOT NULL,
                parent TEXT NOT NULL,
                PRIMARY KEY(child, parent)
            )
            """
        )
        if reset:
            conn.execute("DELETE FROM subclass_edges")
            conn.commit()

        scanned = 0
        inserted = 0
        pending: list[tuple[str, str]] = []
        for entity in iter_wikidata_entities(dump_path):
            scanned += 1
            child = str(entity["id"])
            for parent in entity_ids(entity, PROP_SUBCLASS_OF):
                pending.append((child, parent))
            if len(pending) >= 5000:
                before = conn.total_changes
                conn.executemany("INSERT OR IGNORE INTO subclass_edges(child, parent) VALUES (?, ?)", pending)
                inserted += conn.total_changes - before
                pending = []
                conn.commit()
        if pending:
            before = conn.total_changes
            conn.executemany("INSERT OR IGNORE INTO subclass_edges(child, parent) VALUES (?, ?)", pending)
            inserted += conn.total_changes - before
        conn.execute("CREATE INDEX IF NOT EXISTS idx_subclass_parent ON subclass_edges(parent, child)")
        conn.commit()
    return {"entities_scanned": scanned, "subclass_edges_inserted": inserted}


def scientist_occupation_ids(taxonomy_db: str | Path) -> set[str]:
    with sqlite3.connect(taxonomy_db) as conn:
        rows = conn.execute(
            """
            WITH RECURSIVE descendants(qid) AS (
                SELECT ?
                UNION
                SELECT e.child
                FROM subclass_edges e
                JOIN descendants d ON e.parent = d.qid
            )
            SELECT qid FROM descendants
            """,
            (SCIENTIST_QID,),
        ).fetchall()
    return {str(row[0]) for row in rows}


def normalize_scientist(entity: dict[str, Any], scientist_occupations: set[str], release_id: str) -> dict[str, Any] | None:
    if HUMAN_QID not in entity_ids(entity, PROP_INSTANCE_OF):
        return None
    occupations = entity_ids(entity, PROP_OCCUPATION)
    scientific = sorted(set(occupations) & scientist_occupations)
    if not scientific:
        return None
    qid = str(entity["id"])
    return {
        "entity_type": "scientist",
        "canonical_key": f"wikidata:item:{qid}",
        "source_id": "wikidata",
        "external_id": qid,
        "name": label_for(entity),
        "aliases": aliases_for(entity),
        "orcid": (string_values(entity, PROP_ORCID) or [None])[0],
        "birth": time_values(entity, PROP_BIRTH),
        "death": time_values(entity, PROP_DEATH),
        "occupation_ids": occupations,
        "scientist_occupation_ids": scientific,
        "field_ids": entity_ids(entity, PROP_FIELD),
        "educated_at_ids": entity_ids(entity, PROP_EDUCATED_AT),
        "award_ids": entity_ids(entity, PROP_AWARD),
        "notable_work_ids": entity_ids(entity, PROP_NOTABLE_WORK),
        "source_release": release_id,
        "classification_basis": {
            "instance_of_human": HUMAN_QID,
            "occupation_descendant_of": SCIENTIST_QID,
        },
    }


def extract_scientists(
    dump_path: str | Path,
    taxonomy_db: str | Path,
    output_jsonl: str | Path,
    *,
    release_id: str,
    max_records: int | None = None,
) -> dict[str, int]:
    scientific_occupations = scientist_occupation_ids(taxonomy_db)
    if len(scientific_occupations) <= 1:
        raise ValueError("scientist occupation taxonomy is empty; build taxonomy from a Wikidata dump first")
    output = Path(output_jsonl)
    output.parent.mkdir(parents=True, exist_ok=True)
    scanned = 0
    written = 0
    with output.open("w", encoding="utf-8") as handle:
        for entity in iter_wikidata_entities(dump_path):
            scanned += 1
            scientist = normalize_scientist(entity, scientific_occupations, release_id)
            if scientist is None:
                continue
            handle.write(json.dumps(scientist, ensure_ascii=False, sort_keys=True) + "\n")
            written += 1
            if max_records is not None and written >= max_records:
                break
    return {
        "entities_scanned": scanned,
        "scientists_written": written,
        "scientist_occupation_classes": len(scientific_occupations),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract historical-to-present scientist records from a Wikidata dump")
    sub = parser.add_subparsers(dest="command", required=True)

    taxonomy = sub.add_parser("build-taxonomy")
    taxonomy.add_argument("--dump", required=True)
    taxonomy.add_argument("--taxonomy-db", required=True)
    taxonomy.add_argument("--reset", action="store_true")

    extract = sub.add_parser("extract")
    extract.add_argument("--dump", required=True)
    extract.add_argument("--taxonomy-db", required=True)
    extract.add_argument("--output", required=True)
    extract.add_argument("--release", required=True)
    extract.add_argument("--max-records", type=int)

    args = parser.parse_args()
    started = time.perf_counter()
    if args.command == "build-taxonomy":
        result = build_scientist_taxonomy(args.dump, args.taxonomy_db, reset=args.reset)
    else:
        result = extract_scientists(
            args.dump,
            args.taxonomy_db,
            args.output,
            release_id=args.release,
            max_records=args.max_records,
        )
    result["seconds"] = round(time.perf_counter() - started, 3)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
