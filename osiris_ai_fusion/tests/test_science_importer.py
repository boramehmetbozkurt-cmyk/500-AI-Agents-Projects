import json

from science_importer import ScienceImportStore, file_sha256, import_jsonl
from science_world import ScienceGraphStore


def test_bulk_import_registers_release_checksum_and_entities(tmp_path):
    source = tmp_path / "authors.jsonl"
    rows = [
        {"id": "https://openalex.org/A1", "display_name": "Scientist One", "works_count": 1},
        {"id": "https://openalex.org/A2", "display_name": "Scientist Two", "works_count": 2},
    ]
    source.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    db = str(tmp_path / "science.sqlite3")
    graph = ScienceGraphStore(db)
    imports = ScienceImportStore(db)

    result = import_jsonl(
        workspace_id="reference",
        kind="openalex_authors",
        path=source,
        release_id="2026-q3-test",
        graph_store=graph,
        import_store=imports,
        batch_size=1,
        checkpoint_every=1,
    )
    assert result["status"] == "complete"
    assert result["records_seen"] == 2
    assert result["source_sha256"] == file_sha256(source)
    stored = graph.list_entities("reference", entity_type="scientist")
    assert {row["external_id"] for row in stored} == {"A1", "A2"}
    assert all(row["source_release"] == "2026-q3-test" for row in stored)
    assert all(row["source_record_digest"] for row in stored)


def test_completed_import_is_idempotent_and_returns_checkpoint(tmp_path):
    source = tmp_path / "genes.jsonl"
    source.write_text(
        json.dumps({"gene_id": "675", "symbol": "BRCA2", "description": "DNA repair"}) + "\n",
        encoding="utf-8",
    )
    db = str(tmp_path / "science.sqlite3")
    graph = ScienceGraphStore(db)
    imports = ScienceImportStore(db)
    first = import_jsonl(
        workspace_id="reference",
        kind="ncbi_genes",
        path=source,
        release_id="test-release",
        graph_store=graph,
        import_store=imports,
    )
    second = import_jsonl(
        workspace_id="reference",
        kind="ncbi_genes",
        path=source,
        release_id="test-release",
        graph_store=graph,
        import_store=imports,
    )
    assert first["status"] == "complete"
    assert second["status"] == "complete"
    assert second["resumed"] is True
    assert len(graph.list_entities("reference", entity_type="gene")) == 1


def test_import_fails_closed_on_wrong_checksum(tmp_path):
    source = tmp_path / "proteins.jsonl"
    source.write_text(json.dumps({"primaryAccession": "P1"}) + "\n", encoding="utf-8")
    try:
        import_jsonl(
            workspace_id="reference",
            kind="uniprot_proteins",
            path=source,
            release_id="r1",
            graph_store=ScienceGraphStore(str(tmp_path / "science.sqlite3")),
            import_store=ScienceImportStore(str(tmp_path / "science.sqlite3")),
            expected_sha256="0" * 64,
        )
    except ValueError as exc:
        assert "checksum" in str(exc)
    else:
        raise AssertionError("expected checksum mismatch to fail closed")
