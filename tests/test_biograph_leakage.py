"""Tests for split-aware biological graph construction.

The leakage rule here is NOT the DDI graph's rule, and the tests are written
around exactly that difference: a drug-protein edge for a held-out drug is
admissible, a drug-drug edge for one is not. Getting this backwards in either
direction produces a number rather than an error - too high in one case, too
low in the other - so it is tested from both sides.
"""
import pytest

from ddinet.integration.biograph import (
    LeakageViolation, assert_relation_domains, build_biograph,
)
from ddinet.integration.quality import audit_graph
from ddinet.integration.schema import (
    Entity, EntityType, Evidence, EvidenceType, KnowledgeStore, Provenance,
    Relation, RelationType,
)

TRAIN, TEST, VAL = "CMP:TRAIN", "CMP:TEST", "CMP:VAL"
P1, P2 = "PRO:P00001", "PRO:P00002"


def _store():
    store = KnowledgeStore()
    for cid in (TRAIN, TEST, VAL):
        store.add_entity(Entity(cid, EntityType.DRUG))
    for cid in (P1, P2):
        store.add_entity(Entity(cid, EntityType.PROTEIN))
    return store


def _add(store, subject, predicate, obj, source="drugcentral",
         evidence=EvidenceType.CURATED):
    store.add_assertion(Relation(subject, predicate, obj),
                        Evidence(evidence, Provenance(source, "1")))


# --------------------------------------------------------------------------
# The difference from the DDI graph rule
# --------------------------------------------------------------------------

def test_a_held_out_drugs_own_target_annotation_is_ADMISSIBLE():
    """A drug-protein edge is a measurement, not the label. It exists for a new
    drug on the day it is approved, so withholding it would simulate a
    deployment nobody would build and UNDERSTATE what an honest system does."""
    store = _store()
    _add(store, TEST, RelationType.DRUG_TARGETS_PROTEIN, P1)
    graph = build_biograph(store, train_drugs={TRAIN}, test_drugs={TEST})
    assert len(graph.edges) == 1
    assert P1 in graph.neighbours(TEST)


def test_a_drug_drug_edge_touching_a_held_out_drug_RAISES():
    """A DDI edge is the label. It is a hard failure rather than a filter:
    an adapter that produced it has a bug, and dropping it would hide that."""
    store = _store()
    _add(store, TRAIN, RelationType.DRUG_INTERACTS_WITH_DRUG, TEST)
    with pytest.raises(LeakageViolation, match="label-bearing"):
        build_biograph(store, train_drugs={TRAIN}, test_drugs={TEST})


def test_the_rule_applies_to_the_edge_not_to_the_database_it_came_from():
    """A DDI edge imported from a biological database is still a DDI edge.
    This is the easiest way to leak: the adapter looks harmless."""
    store = _store()
    _add(store, TRAIN, RelationType.DRUG_INTERACTS_WITH_DRUG, VAL,
         source="drugcentral")
    with pytest.raises(LeakageViolation):
        build_biograph(store, train_drugs={TRAIN}, validation_drugs={VAL})


def test_a_drug_drug_edge_between_two_training_drugs_is_kept():
    store = _store()
    store.add_entity(Entity("CMP:TRAIN2", EntityType.DRUG))
    _add(store, TRAIN, RelationType.DRUG_INTERACTS_WITH_DRUG, "CMP:TRAIN2")
    graph = build_biograph(store, train_drugs={TRAIN, "CMP:TRAIN2"},
                           test_drugs={TEST})
    assert len(graph.edges) == 1


def test_protein_protein_edges_are_unaffected_by_the_split():
    """A protein is not held out by a drug-level split."""
    store = _store()
    _add(store, P1, RelationType.PROTEIN_INTERACTS_WITH_PROTEIN, P2)
    graph = build_biograph(store, train_drugs={TRAIN}, test_drugs={TEST})
    assert len(graph.edges) == 1


# --------------------------------------------------------------------------
# Rule 2: what may be FITTED
# --------------------------------------------------------------------------

def test_held_out_drugs_are_excluded_from_the_fittable_set():
    """The graph may span all drugs; anything learned from it may not. This is
    the transductive leak the DDI rule does not cover."""
    store = _store()
    _add(store, TEST, RelationType.DRUG_TARGETS_PROTEIN, P1)
    _add(store, TRAIN, RelationType.DRUG_TARGETS_PROTEIN, P2)
    graph = build_biograph(store, train_drugs={TRAIN}, test_drugs={TEST})
    assert TRAIN in graph.fittable_nodes
    assert TEST not in graph.fittable_nodes
    # proteins stay fittable - they are not held out by a drug-level split
    assert P1 in graph.fittable_nodes and P2 in graph.fittable_nodes


def test_a_drug_in_both_train_and_test_is_refused_outright():
    store = _store()
    _add(store, TRAIN, RelationType.DRUG_TARGETS_PROTEIN, P1)
    with pytest.raises(LeakageViolation, match="both train and held-out"):
        build_biograph(store, train_drugs={TRAIN}, test_drugs={TRAIN})


# --------------------------------------------------------------------------
# The ablation switch
# --------------------------------------------------------------------------

def test_allow_holdout_biology_false_strips_held_out_annotations():
    """Not a safe mode - a separate question: does the advantage come from the
    held-out drug's own annotations or from the training drugs' ones?"""
    store = _store()
    _add(store, TEST, RelationType.DRUG_TARGETS_PROTEIN, P1)
    _add(store, TRAIN, RelationType.DRUG_TARGETS_PROTEIN, P2)
    strict = build_biograph(store, train_drugs={TRAIN}, test_drugs={TEST},
                            allow_holdout_biology=False)
    assert len(strict.edges) == 1
    assert strict.excluded["holdout_biology_excluded"] == 1


def test_nothing_is_dropped_silently():
    """Every exclusion lands in a counter, and the counters land in summary()."""
    store = _store()
    _add(store, TEST, RelationType.DRUG_TARGETS_PROTEIN, P1)
    graph = build_biograph(store, train_drugs={TRAIN}, test_drugs={TEST},
                           allow_holdout_biology=False)
    assert sum(graph.excluded.values()) == 1
    assert graph.summary()["excluded"] == graph.excluded


# --------------------------------------------------------------------------
# Filtering
# --------------------------------------------------------------------------

def test_computational_evidence_can_be_excluded_for_the_required_ablation():
    """29.2% of Reactome FI edges are its own predictor's output. Running with
    and without them is a required ablation, so the switch must work."""
    store = _store()
    _add(store, P1, RelationType.PROTEIN_INTERACTS_WITH_PROTEIN, P2,
         evidence=EvidenceType.COMPUTATIONAL)
    _add(store, TRAIN, RelationType.DRUG_TARGETS_PROTEIN, P1,
         evidence=EvidenceType.CURATED)
    curated_only = build_biograph(store, train_drugs={TRAIN},
                                  include_evidence_types={"curated"})
    assert len(curated_only.edges) == 1
    assert curated_only.excluded["evidence_type_excluded"] == 1


def test_a_source_can_be_excluded_wholesale():
    store = _store()
    _add(store, TRAIN, RelationType.DRUG_TARGETS_PROTEIN, P1, source="chembl")
    _add(store, TRAIN, RelationType.DRUG_TARGETS_PROTEIN, P2, source="drugcentral")
    graph = build_biograph(store, train_drugs={TRAIN}, exclude_sources={"chembl"})
    assert len(graph.edges) == 1
    assert graph.edges[0].provenance_source == "drugcentral"


def test_an_edge_with_an_unregistered_endpoint_is_counted_not_crashed():
    store = _store()
    store.add_assertion(
        Relation(TRAIN, RelationType.DRUG_TARGETS_PROTEIN, "PRO:GHOST"),
        Evidence(EvidenceType.CURATED, Provenance("x", "1")))
    graph = build_biograph(store, train_drugs={TRAIN})
    assert graph.excluded["edge_with_unknown_endpoint"] == 1
    assert len(graph.edges) == 0


# --------------------------------------------------------------------------
# Domain validation
# --------------------------------------------------------------------------

def test_impossible_relation_types_are_reported():
    """A pathway that 'targets' a drug is an adapter bug, not a finding."""
    store = _store()
    store.add_entity(Entity("PWY:R-HSA-1", EntityType.PATHWAY))
    _add(store, "PWY:R-HSA-1", RelationType.DRUG_TARGETS_PROTEIN, P1)
    problems = assert_relation_domains(store)
    assert len(problems) == 1
    assert "subject" in problems[0]


def test_a_valid_store_reports_no_domain_problems():
    store = _store()
    _add(store, TRAIN, RelationType.DRUG_TARGETS_PROTEIN, P1)
    _add(store, P1, RelationType.PROTEIN_INTERACTS_WITH_PROTEIN, P2)
    assert assert_relation_domains(store) == []


# --------------------------------------------------------------------------
# Graph-level quality
# --------------------------------------------------------------------------

def test_audit_reports_duplicate_edges_and_the_build_policy():
    store = _store()
    _add(store, TRAIN, RelationType.DRUG_TARGETS_PROTEIN, P1)
    _add(store, TRAIN, RelationType.DRUG_TARGETS_PROTEIN, P1)
    graph = build_biograph(store, train_drugs={TRAIN}, test_drugs={TEST})
    report = audit_graph(graph)
    assert report["duplicate_edges"]["count"] == 1
    assert report["policy"]["n_train_drugs"] == 1
    assert report["policy"]["allow_holdout_biology"] is True
