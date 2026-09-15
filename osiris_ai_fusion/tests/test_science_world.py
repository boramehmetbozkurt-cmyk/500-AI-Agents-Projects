from science_world import (
    SCIENCE_SOURCES,
    ScienceGraphStore,
    _normalize_ensembl_gene,
    _normalize_openalex_author,
    _normalize_openalex_work,
    _normalize_uniprot,
    _public_reference_query,
)


def test_science_source_registry_is_explicit_and_commercially_classified():
    ids = [row["id"] for row in SCIENCE_SOURCES]
    assert len(ids) == len(set(ids))
    assert {"openalex", "wikidata", "ncbi_datasets", "ensembl", "uniprot", "clinvar"}.issubset(ids)
    for row in SCIENCE_SOURCES:
        assert row["base_url"].startswith("https://")
        assert row["license"]
        assert row["commercial_use"]
        assert row["notes"]


def test_personal_raw_genome_material_is_rejected_from_shared_graph():
    for query in ("my genome", "patient VCF", "sample.bam", "personal genome FASTQ"):
        try:
            _public_reference_query(query)
        except ValueError as exc:
            assert "private vault" in str(exc)
        else:
            raise AssertionError(f"expected shared-graph rejection for {query}")
    _public_reference_query("BRCA2")


def test_openalex_author_normalization_preserves_identity_and_provenance():
    row = {
        "id": "https://openalex.org/A123",
        "display_name": "Ada Example",
        "orcid": "https://orcid.org/0000-0000-0000-0001",
        "works_count": 12,
        "cited_by_count": 34,
        "last_known_institutions": [
            {"id": "https://openalex.org/I1", "display_name": "Example Lab", "country_code": "TR"}
        ],
        "topics": [{"id": "https://openalex.org/T1", "display_name": "Genomics", "score": 0.9}],
    }
    normalized = _normalize_openalex_author(row)
    assert normalized["canonical_key"] == "openalex:author:A123"
    assert normalized["source_id"] == "openalex"
    assert normalized["institutions"][0]["id"] == "I1"
    assert normalized["topics"][0]["name"] == "Genomics"


def test_openalex_work_normalization_keeps_authorship_and_license():
    row = {
        "id": "https://openalex.org/W1",
        "display_name": "Genome paper",
        "doi": "https://doi.org/10.1/example",
        "publication_year": 2026,
        "cited_by_count": 7,
        "authorships": [
            {
                "author_position": "first",
                "is_corresponding": True,
                "author": {"id": "https://openalex.org/A1", "display_name": "Researcher"},
            }
        ],
        "primary_location": {"license": "cc-by"},
    }
    normalized = _normalize_openalex_work(row)
    assert normalized["canonical_key"] == "openalex:work:W1"
    assert normalized["authors"][0]["id"] == "A1"
    assert normalized["authors"][0]["corresponding"] is True
    assert normalized["primary_location_license"] == "cc-by"


def test_genome_normalizers_keep_stable_database_identifiers():
    gene = _normalize_ensembl_gene(
        {
            "id": "ENSG00000139618",
            "display_name": "BRCA2",
            "species": "homo_sapiens",
            "assembly_name": "GRCh38",
            "seq_region_name": "13",
            "start": 1,
            "end": 2,
        },
        "BRCA2",
    )
    assert gene["canonical_key"] == "ensembl:gene:ENSG00000139618"
    assert gene["assembly_name"] == "GRCh38"

    protein = _normalize_uniprot(
        {
            "primaryAccession": "P51587",
            "entryType": "UniProtKB reviewed (Swiss-Prot)",
            "proteinDescription": {"recommendedName": {"fullName": {"value": "BRCA2 protein"}}},
            "genes": [{"geneName": {"value": "BRCA2"}}],
            "sequence": {"length": 3418, "molWeight": 384202, "crc64": "ABC"},
        }
    )
    assert protein["canonical_key"] == "uniprot:protein:P51587"
    assert protein["reviewed"] is True
    assert protein["genes"] == ["BRCA2"]


def test_science_store_deduplicates_and_isolates_tenants(tmp_path):
    store = ScienceGraphStore(str(tmp_path / "science.sqlite3"))
    row = {
        "entity_type": "scientist",
        "canonical_key": "openalex:author:A1",
        "source_id": "openalex",
        "external_id": "A1",
        "name": "Researcher One",
    }
    assert store.upsert_entities("tenant-a", [row]) == 1
    assert store.upsert_entities("tenant-a", [row]) == 1
    assert len(store.list_entities("tenant-a")) == 1
    assert store.list_entities("tenant-b") == []
    assert store.counts("tenant-a") == {"scientist": 1}
