from science_edges import ScienceEdgeStore, derive_edges
from science_world import ScienceGraphStore


def test_scientist_and_work_edges_preserve_source_keys():
    scientist = {
        "entity_type": "scientist",
        "canonical_key": "openalex:author:A1",
        "source_id": "openalex",
        "institutions": [{"id": "I1", "name": "Example University"}],
        "topics": [{"id": "T1", "name": "Genomics", "score": 0.9}],
    }
    edges = derive_edges(scientist)
    assert any(edge["relation"] == "affiliated_with" and edge["target_key"] == "openalex:institution:I1" for edge in edges)
    assert any(edge["relation"] == "about_topic" and edge["target_key"] == "openalex:topic:T1" for edge in edges)

    work = {
        "entity_type": "work",
        "canonical_key": "openalex:work:W1",
        "source_id": "openalex",
        "authors": [{"id": "A1", "name": "Researcher", "position": "first", "corresponding": True}],
    }
    authored = derive_edges(work)
    assert authored[0]["source_key"] == "openalex:author:A1"
    assert authored[0]["relation"] == "authored"
    assert authored[0]["target_key"] == "openalex:work:W1"


def test_gene_protein_and_variant_edges_do_not_fake_cross_source_identity():
    gene = {
        "entity_type": "gene",
        "canonical_key": "ensembl:gene:ENSG1",
        "source_id": "ensembl",
        "assembly_name": "GRCh38",
        "seq_region_name": "13",
        "start": 10,
        "end": 20,
        "strand": 1,
    }
    gene_edges = derive_edges(gene)
    assert gene_edges[0]["target_key"] == "genome:chromosome:GRCh38:13"

    protein = {
        "entity_type": "protein",
        "canonical_key": "uniprot:protein:P1",
        "source_id": "uniprot",
        "genes": ["BRCA2"],
        "organism": {"taxonId": 9606},
    }
    protein_edges = derive_edges(protein)
    assert protein_edges[0]["source_key"] == "gene-symbol:9606:BRCA2"
    assert protein_edges[0]["relation"] == "encodes"

    variant = {
        "entity_type": "variant",
        "canonical_key": "clinvar:variation:1",
        "source_id": "clinvar",
        "genes": [{"symbol": "BRCA2", "geneid": "675"}],
    }
    variant_edges = derive_edges(variant)
    assert variant_edges[0]["target_key"] == "ncbi:gene:675"
    assert variant_edges[0]["relation"] == "associated_with"


def test_edge_rebuild_is_tenant_scoped(tmp_path):
    db = str(tmp_path / "science.sqlite3")
    graph = ScienceGraphStore(db)
    edges = ScienceEdgeStore(db)
    graph.upsert_entities(
        "tenant-a",
        [
            {
                "entity_type": "work",
                "canonical_key": "openalex:work:W1",
                "source_id": "openalex",
                "external_id": "W1",
                "name": "Paper",
                "authors": [{"id": "A1", "name": "Researcher"}],
            }
        ],
    )
    result = edges.rebuild("tenant-a")
    assert result["edges_written"] == 1
    assert len(edges.edges("tenant-a")) == 1
    assert edges.edges("tenant-b") == []
