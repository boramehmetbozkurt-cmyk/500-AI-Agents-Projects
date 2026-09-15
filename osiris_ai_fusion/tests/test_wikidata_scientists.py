import json

from wikidata_scientists import (
    build_scientist_taxonomy,
    extract_scientists,
    scientist_occupation_ids,
)


def _claim_entity(qid):
    return {
        "mainsnak": {
            "snaktype": "value",
            "datavalue": {"value": {"entity-type": "item", "id": qid}, "type": "wikibase-entityid"},
        },
        "type": "statement",
        "rank": "normal",
    }


def _claim_string(value):
    return {
        "mainsnak": {"snaktype": "value", "datavalue": {"value": value, "type": "string"}},
        "type": "statement",
        "rank": "normal",
    }


def _claim_time(value):
    return {
        "mainsnak": {
            "snaktype": "value",
            "datavalue": {
                "value": {
                    "time": value,
                    "precision": 11,
                    "calendarmodel": "http://www.wikidata.org/entity/Q1985727",
                    "before": 0,
                    "after": 0,
                    "timezone": 0,
                },
                "type": "time",
            },
        },
        "type": "statement",
        "rank": "normal",
    }


def test_wikidata_dump_taxonomy_and_scientist_extraction(tmp_path):
    dump = tmp_path / "wikidata.json"
    rows = [
        {"type": "item", "id": "Q901", "claims": {}, "labels": {"en": {"language": "en", "value": "scientist"}}},
        {
            "type": "item",
            "id": "Q169470",
            "claims": {"P279": [_claim_entity("Q901")]},
            "labels": {"en": {"language": "en", "value": "physicist"}},
        },
        {
            "type": "item",
            "id": "Q100",
            "claims": {
                "P31": [_claim_entity("Q5")],
                "P106": [_claim_entity("Q169470")],
                "P496": [_claim_string("0000-0001-2345-6789")],
                "P569": [_claim_time("+1879-03-14T00:00:00Z")],
                "P101": [_claim_entity("Q413")],
            },
            "labels": {"en": {"language": "en", "value": "Example Physicist"}},
            "aliases": {"en": [{"language": "en", "value": "E. Physicist"}]},
        },
        {
            "type": "item",
            "id": "Q200",
            "claims": {"P31": [_claim_entity("Q5")], "P106": [_claim_entity("Q999999")]},
            "labels": {"en": {"language": "en", "value": "Not Scientist"}},
        },
    ]
    dump.write_text("[\n" + ",\n".join(json.dumps(row) for row in rows) + "\n]\n", encoding="utf-8")
    taxonomy = tmp_path / "taxonomy.sqlite3"
    result = build_scientist_taxonomy(dump, taxonomy)
    assert result["subclass_edges_inserted"] == 1
    assert {"Q901", "Q169470"}.issubset(scientist_occupation_ids(taxonomy))

    output = tmp_path / "scientists.jsonl"
    extracted = extract_scientists(dump, taxonomy, output, release_id="test-2026")
    assert extracted["scientists_written"] == 1
    scientist = json.loads(output.read_text(encoding="utf-8").strip())
    assert scientist["canonical_key"] == "wikidata:item:Q100"
    assert scientist["name"] == "Example Physicist"
    assert scientist["orcid"] == "0000-0001-2345-6789"
    assert scientist["scientist_occupation_ids"] == ["Q169470"]
    assert scientist["classification_basis"]["occupation_descendant_of"] == "Q901"
