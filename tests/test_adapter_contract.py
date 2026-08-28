"""Tests for the adapter contract and the data quality audit.

The contract's whole point is the difference between "this source contributed
nothing" and "this source is not here". An adapter that returns an empty store
for an absent source destroys that distinction, so most of these tests are
about REFUSING correctly.
"""
import pytest

from ddinet.adapters import Adapter, SourceUnavailable
from ddinet.adapters.chembl_adapter import ChemblAdapter
from ddinet.adapters.drugcentral_adapter import DrugCentralAdapter
from ddinet.adapters.faers_adapter import FaersAdapter
from ddinet.adapters.reactome_adapter import ReactomeFIAdapter, ReactomeUniProtAdapter
from ddinet.adapters.sider_adapter import JoinUnavailable, SiderAdapter
from ddinet.adapters.uniprot_adapter import UniProtAdapter
from ddinet.integration.quality import (
    audit_compounds, audit_identifier_map, audit_store,
)
from ddinet.integration.identifiers import build_compound_map
from ddinet.integration.schema import (
    Entity, EntityType, Evidence, EvidenceType, KnowledgeStore, Provenance,
    Relation, RelationType,
)

ALL_ADAPTERS = [DrugCentralAdapter, ChemblAdapter, ReactomeFIAdapter,
                ReactomeUniProtAdapter, SiderAdapter, UniProtAdapter,
                FaersAdapter]
PLACEHOLDERS = [UniProtAdapter, FaersAdapter]


# --------------------------------------------------------------------------
# The contract
# --------------------------------------------------------------------------

@pytest.mark.parametrize("cls", ALL_ADAPTERS)
def test_every_adapter_satisfies_the_protocol(cls):
    assert isinstance(cls(), Adapter)


@pytest.mark.parametrize("cls", ALL_ADAPTERS)
def test_every_adapter_declares_licence_and_required_files(cls):
    """A source whose licence is not recorded cannot be redistributed or even
    safely cited. Stated before it runs, not after."""
    desc = cls().describe()
    assert desc.name and desc.licence
    assert desc.required_files, "an adapter must say what files it needs"


@pytest.mark.parametrize("cls", ALL_ADAPTERS)
def test_declared_relations_are_real_relation_types(cls):
    known = {r.value for r in RelationType}
    assert set(cls().describe().provides) <= known


@pytest.mark.parametrize("cls", PLACEHOLDERS)
def test_a_placeholder_refuses_instead_of_returning_an_empty_store(cls):
    """An adapter that silently yields nothing is indistinguishable from a
    source with no data - the one confusion this project cannot afford."""
    adapter = cls()
    assert adapter.describe().is_placeholder
    assert not adapter.is_available()
    with pytest.raises(SourceUnavailable, match="interface only"):
        adapter.extract(KnowledgeStore())


@pytest.mark.parametrize("cls", PLACEHOLDERS)
def test_a_placeholder_says_where_to_get_the_data(cls):
    desc = cls().describe()
    assert desc.download_url or desc.notes


def test_sider_refuses_without_a_cid_bridge_even_though_its_files_exist():
    """Files present, join impossible. The adapter must not fall back to
    anything weaker: the corpus has no drug names to match on."""
    with pytest.raises(JoinUnavailable, match="STITCH CID"):
        SiderAdapter().extract(KnowledgeStore())


def test_chembl_availability_means_the_extracts_not_the_database(tmp_path):
    """Pointing the adapter at the 5 GB database would work and would be wrong:
    extraction happens once, training consumes compact artifacts."""
    adapter = ChemblAdapter(processed_dir=tmp_path)
    assert not adapter.is_available()
    with pytest.raises(SourceUnavailable, match="extract_chembl"):
        adapter.extract(KnowledgeStore())


def test_missing_files_are_named_individually(tmp_path):
    adapter = DrugCentralAdapter(directory=tmp_path)
    assert not adapter.is_available()
    missing = adapter.missing_files()
    assert len(missing) == 2
    with pytest.raises(SourceUnavailable, match="drugcentral.org"):
        adapter.extract(KnowledgeStore(), drugs=None)


# --------------------------------------------------------------------------
# Quality audit
# --------------------------------------------------------------------------

def _store_with(*assertions):
    store = KnowledgeStore()
    for cid, kind in (("CMP:BSYNRYMUTXBXSQ-UHFFFAOYSA-N", EntityType.DRUG),
                      ("PRO:P23219", EntityType.PROTEIN),
                      ("PRO:P35354", EntityType.PROTEIN)):
        store.add_entity(Entity(cid, kind))
    for subject, predicate, obj, source, sid in assertions:
        store.add_assertion(Relation(subject, predicate, obj),
                            Evidence(EvidenceType.CURATED,
                                     Provenance(source, "1", None, sid)))
    return store


def test_the_same_row_twice_is_a_duplicate_but_two_sources_are_not():
    drug = "CMP:BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
    rel = (drug, RelationType.DRUG_TARGETS_PROTEIN, "PRO:P23219")
    duplicated = _store_with((*rel, "chembl", "r1"), (*rel, "chembl", "r1"))
    agreeing = _store_with((*rel, "chembl", "r1"), (*rel, "drugcentral", "r9"))
    assert audit_store(duplicated)["duplicate_assertions"]["count"] == 1
    assert audit_store(agreeing)["duplicate_assertions"]["count"] == 0


def test_self_interactions_are_counted_not_dropped():
    """Reactome genuinely contains 7 812 homodimers. Counting them is the
    point; silently dropping them would change 7 812 nodes' degrees."""
    store = _store_with(("PRO:P23219",
                         RelationType.PROTEIN_INTERACTS_WITH_PROTEIN,
                         "PRO:P23219", "reactome", "r1"))
    assert audit_store(store)["self_interactions"]["count"] == 1


def test_orphan_edges_and_orphan_nodes_are_reported_separately():
    store = _store_with(("CMP:BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
                         RelationType.DRUG_TARGETS_PROTEIN, "PRO:GHOST",
                         "x", "r1"))
    report = audit_store(store)
    assert report["orphan_edges"]["count"] == 1
    # P35354 was registered but nothing refers to it
    assert report["orphan_nodes"]["count"] >= 1


def test_conflicting_signs_between_sources_are_surfaced():
    """One source saying inhibit and another activate is a finding, not
    something to average away."""
    drug = "CMP:BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
    store = _store_with(
        (drug, RelationType.DRUG_INHIBITS_PROTEIN, "PRO:P23219", "a", "1"),
        (drug, RelationType.DRUG_ACTIVATES_PROTEIN, "PRO:P23219", "b", "2"))
    assert audit_store(store)["conflicting_signs"]["count"] == 1


def test_an_id_minted_in_the_wrong_canonical_space_is_caught():
    store = KnowledgeStore()
    store.add_entity(Entity("PRO:P23219", EntityType.DRUG))
    assert audit_store(store)["identifier_wrong_space"]["count"] == 1


def test_a_malformed_identifier_inside_a_canonical_id_is_caught():
    store = KnowledgeStore()
    store.add_entity(Entity("PRO:not-an-accession", EntityType.PROTEIN))
    assert audit_store(store)["malformed_identifiers"]["count"] == 1


def test_compound_audit_finds_duplicates_and_invalid_structures():
    report = audit_compounds([
        ("DB1", "CC(=O)Oc1ccccc1C(=O)O", "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"),
        ("DB2", "CC(=O)Oc1ccccc1C(=O)O", "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"),
        ("DB3", "this is not smiles", "AAAAAAAAAAAAAA-BBBBBBBBBB-C"),
        ("DB4", "CCO", "malformed-key"),
        ("DB5", "", ""),
    ])
    assert report["duplicate_structures"]["count"] == 1
    assert report["malformed_inchikey"]["count"] == 1
    assert report["missing_inchikey"]["count"] == 1
    assert report["missing_smiles"]["count"] == 1
    if report["invalid_smiles"]["checked"]:
        assert report["invalid_smiles"]["count"] == 1


def test_identifier_map_audit_reports_conflicts_and_collisions():
    imap = build_compound_map([
        ("drugbank", "DB1", "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"),
        ("drugbank", "DB2", "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"),
    ])
    report = audit_identifier_map(imap)
    assert report["within_space_collisions"]["count"] == 1
    assert report["summary"]["n_uncertain"] == 0
