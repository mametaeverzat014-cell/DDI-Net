"""Tests for the canonical schema and identifier layer.

The theme: every test here guards a property whose violation would show up as
a plausible NUMBER rather than as an error. Provenance quietly collapsing, a
fuzzy match quietly counted as exact, a type quietly depending on adapter
order - none of those raise anything on their own.
"""
from datetime import date

import pytest

from ddinet.integration.identifiers import (
    IdentifierMap, Mapping, MatchQuality, build_compound_map,
    canonical_compound_id, canonical_gene_id, canonical_protein_id,
    inchikey_skeleton, is_valid, normalise,
)
from ddinet.integration.schema import (
    Assertion, Entity, EntityType, Evidence, EvidenceType, KnowledgeStore,
    Provenance, Relation, RelationType, reconcile_types,
)

ASPIRIN = "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"


def _prov(source="chembl", version="36", sid="1"):
    return Provenance(source, version, date(2026, 8, 28), sid)


# --------------------------------------------------------------------------
# Provenance must never collapse
# --------------------------------------------------------------------------

def test_two_sources_asserting_one_relation_stay_two_assertions():
    """The single property this whole schema exists for. If these merged,
    'how many independent sources back this edge' would be unanswerable."""
    store = KnowledgeStore()
    store.add_entity(Entity("CMP:X", EntityType.DRUG))
    store.add_entity(Entity("PRO:P23219", EntityType.PROTEIN))
    rel = Relation("CMP:X", RelationType.DRUG_INHIBITS_PROTEIN, "PRO:P23219")
    store.add_assertion(rel, Evidence(EvidenceType.BIOACTIVITY, _prov("chembl")))
    store.add_assertion(rel, Evidence(EvidenceType.CURATED, _prov("drugcentral")))

    assert len(store) == 2
    assert len(store.relations) == 1
    assert store.sources_for(rel) == {"chembl", "drugcentral"}
    assert store.agreement()[rel] == 2


def test_the_same_source_twice_is_not_agreement():
    """Three rows from one database are one source's opinion, not three."""
    store = KnowledgeStore()
    store.add_entity(Entity("CMP:X", EntityType.DRUG))
    store.add_entity(Entity("PRO:P23219", EntityType.PROTEIN))
    rel = Relation("CMP:X", RelationType.DRUG_TARGETS_PROTEIN, "PRO:P23219")
    for i in range(3):
        store.add_assertion(rel, Evidence(EvidenceType.BIOACTIVITY,
                                          _prov("chembl", sid=str(i))))
    assert len(store) == 3
    assert store.agreement()[rel] == 1


def test_filtering_by_source_keeps_the_others_intact():
    store = KnowledgeStore()
    store.add_entity(Entity("CMP:X", EntityType.DRUG))
    store.add_entity(Entity("PRO:P23219", EntityType.PROTEIN))
    rel = Relation("CMP:X", RelationType.DRUG_TARGETS_PROTEIN, "PRO:P23219")
    store.add_assertion(rel, Evidence(EvidenceType.CURATED, _prov("a")))
    store.add_assertion(rel, Evidence(EvidenceType.COMPUTATIONAL, _prov("b")))

    curated = store.filter(evidence_types=[EvidenceType.CURATED])
    assert len(curated) == 1
    assert curated.sources_for(rel) == {"a"}
    # entities survive: a filtered store with dangling ids would fail the
    # orphan check for the wrong reason
    assert curated.entity("PRO:P23219") is not None


def test_confidence_is_none_when_a_source_reports_none():
    """A default of 1.0 would be a number this project invented."""
    ev = Evidence(EvidenceType.CURATED, _prov())
    assert ev.confidence is None


def test_confidence_outside_the_unit_interval_is_refused():
    """ChEMBL's pchembl and Reactome's score are not probabilities; putting
    them in `confidence` would make them look like one."""
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        Evidence(EvidenceType.BIOACTIVITY, _prov(), confidence=7.5)


def test_symmetric_relations_are_stored_in_one_orientation():
    """Storing both directions would double every degree - and degree is a
    quantity this project measures rather than assumes."""
    store = KnowledgeStore()
    for cid in ("PRO:A00000", "PRO:B00000"):
        store.add_entity(Entity(cid, EntityType.PROTEIN))
    ab = Relation("PRO:B00000", RelationType.PROTEIN_INTERACTS_WITH_PROTEIN,
                  "PRO:A00000")
    ba = Relation("PRO:A00000", RelationType.PROTEIN_INTERACTS_WITH_PROTEIN,
                  "PRO:B00000")
    store.add_assertion(ab, Evidence(EvidenceType.CURATED, _prov()))
    store.add_assertion(ba, Evidence(EvidenceType.CURATED, _prov("other")))
    assert len(store.relations) == 1
    assert store.agreement()[ab.canonical()] == 2


# --------------------------------------------------------------------------
# Entity typing must not depend on adapter order
# --------------------------------------------------------------------------

def test_a_specific_type_wins_over_the_general_one_either_way_round():
    """DrugCentral knows Q9UBN7 is an enzyme; Reactome only that it is a
    protein. Neither is wrong, and which adapter ran first must not matter."""
    assert reconcile_types(EntityType.PROTEIN, EntityType.ENZYME) is EntityType.ENZYME
    assert reconcile_types(EntityType.ENZYME, EntityType.PROTEIN) is EntityType.ENZYME


def test_two_conflicting_specific_types_fall_back_to_the_general_one():
    """Enzyme vs Transporter is a real disagreement. Picking one arbitrarily
    would make the result depend on row order."""
    assert reconcile_types(EntityType.ENZYME,
                           EntityType.TRANSPORTER) is EntityType.PROTEIN


def test_types_from_different_families_are_still_refused():
    assert reconcile_types(EntityType.DRUG, EntityType.PROTEIN) is None
    store = KnowledgeStore()
    store.add_entity(Entity("X", EntityType.DRUG))
    with pytest.raises(ValueError, match="already registered"):
        store.add_entity(Entity("X", EntityType.PATHWAY))


def test_re_registering_merges_synonyms_rather_than_overwriting():
    store = KnowledgeStore()
    store.add_entity(Entity("PRO:P23219", EntityType.PROTEIN, synonyms=("PTGS1",)))
    store.add_entity(Entity("PRO:P23219", EntityType.ENZYME, synonyms=("COX1",)))
    entity = store.entity("PRO:P23219")
    assert set(entity.synonyms) == {"PTGS1", "COX1"}
    assert entity.entity_type is EntityType.ENZYME


# --------------------------------------------------------------------------
# Identifier normalisation
# --------------------------------------------------------------------------

@pytest.mark.parametrize("kind,value", [
    ("inchikey", ASPIRIN), ("uniprot", "P23219"), ("uniprot", "A0A024R161"),
    ("drugbank", "DB00945"), ("chembl", "CHEMBL25"), ("gene", "PTGS1"),
    ("pubchem", "2244"),
])
def test_well_formed_identifiers_validate(kind, value):
    assert is_valid(kind, value)


@pytest.mark.parametrize("kind,value", [
    ("inchikey", "BSYNRYMUTXBXSQ"), ("inchikey", "not-a-key"),
    ("uniprot", "P2"), ("drugbank", "DB1"), ("chembl", "CHEMBL"),
    ("pubchem", "0"), ("gene", ""),
])
def test_malformed_identifiers_are_rejected(kind, value):
    assert not is_valid(kind, value)


def test_unknown_identifier_kind_raises_rather_than_passing_everything():
    with pytest.raises(ValueError, match="unknown identifier kind"):
        is_valid("smiles", "CCO")


def test_reactome_style_uniprot_prefix_and_isoform_are_stripped():
    """Reactome writes uniprotkb:P37840; isoform suffixes denote the same gene
    product for our purposes. The loss is deliberate and documented."""
    assert normalise("uniprot", "uniprotkb:P37840") == "P37840"
    assert normalise("uniprot", "P37840-2") == "P37840"


def test_normalise_returns_none_for_garbage_instead_of_raising():
    """Adapters read whole files; one malformed row must not abort an
    extraction. The quality audit counts them instead."""
    assert normalise("inchikey", "garbage") is None
    assert normalise("uniprot", "") is None
    assert normalise("gene", None) is None


def test_canonical_ids_are_prefixed_and_cannot_collide_across_spaces():
    assert canonical_compound_id(ASPIRIN).startswith("CMP:")
    assert canonical_protein_id("P23219") == "PRO:P23219"
    assert canonical_gene_id("ptgs1") == "GEN:PTGS1"
    ids = {canonical_compound_id(ASPIRIN), canonical_protein_id("P23219"),
           canonical_gene_id("PTGS1")}
    assert len(ids) == 3


def test_canonical_id_refuses_a_malformed_input():
    with pytest.raises(ValueError, match="InChIKey"):
        canonical_compound_id("nonsense")


def test_skeleton_is_the_first_block_only():
    assert inchikey_skeleton(ASPIRIN) == "BSYNRYMUTXBXSQ"


# --------------------------------------------------------------------------
# The mapping table
# --------------------------------------------------------------------------

def test_uncertain_bases_are_flagged_and_excluded_by_default():
    """Skeleton and name matches are decisions, not identities. A caller must
    not pick one up without having asked."""
    assert MatchQuality.INCHIKEY_SKELETON.is_uncertain
    assert MatchQuality.FUZZY_NAME.is_uncertain
    assert not MatchQuality.INCHIKEY_FULL.is_uncertain
    assert not MatchQuality.EXACT_ID.is_uncertain

    imap = IdentifierMap()
    imap.add(Mapping("drugbank", "DB1", "CMP:SKEL", MatchQuality.INCHIKEY_SKELETON))
    assert imap.resolve("drugbank", "DB1") is None
    assert imap.resolve("drugbank", "DB1", allow_uncertain=True) == "CMP:SKEL"


def test_a_tie_between_two_canonical_ids_refuses_rather_than_choosing():
    imap = IdentifierMap()
    imap.add(Mapping("drugbank", "DB1", "CMP:A", MatchQuality.INCHIKEY_FULL))
    imap.add(Mapping("drugbank", "DB1", "CMP:B", MatchQuality.INCHIKEY_FULL))
    assert imap.resolve("drugbank", "DB1") is None
    assert ("drugbank", "DB1") in imap.conflicts()


def test_higher_quality_wins_over_lower():
    imap = IdentifierMap()
    imap.add(Mapping("drugbank", "DB1", "CMP:SKEL", MatchQuality.INCHIKEY_SKELETON))
    imap.add(Mapping("drugbank", "DB1", "CMP:FULL", MatchQuality.INCHIKEY_FULL))
    assert imap.resolve("drugbank", "DB1", allow_uncertain=True) == "CMP:FULL"


def test_two_drugbank_ids_on_one_structure_are_reported_as_a_collision():
    """Legitimate across identifier spaces, suspicious within one: it means the
    corpus holds the same structure twice."""
    imap = build_compound_map([("drugbank", "DB1", ASPIRIN),
                               ("drugbank", "DB2", ASPIRIN)])
    assert len(imap.collisions()) == 1
    assert imap.summary()["n_canonical_ids"] == 1


def test_skeleton_mappings_are_only_emitted_when_asked_for():
    plain = build_compound_map([("drugbank", "DB1", ASPIRIN)])
    widened = build_compound_map([("drugbank", "DB1", ASPIRIN)],
                                 allow_skeleton=True)
    assert plain.summary()["n_uncertain"] == 0
    assert widened.summary()["n_uncertain"] == 1


def test_records_with_no_inchikey_are_skipped_not_guessed():
    imap = build_compound_map([("drugbank", "DB1", ""),
                               ("drugbank", "DB2", None)])
    assert len(imap) == 0
