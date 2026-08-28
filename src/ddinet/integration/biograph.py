"""
Typed biological graph, built from a KnowledgeStore under an explicit
leakage policy.

WHY A SEPARATE BUILD STEP AND NOT A GRAPH IN THE STORE
--------------------------------------------------------
``KnowledgeStore`` holds what sources said. This module decides what a MODEL is
allowed to see, and that decision depends on the split. Keeping them apart is
what makes it impossible to accidentally hand the store straight to a model.

THE LEAKAGE RULE IS PER RELATION TYPE, NOT PER DRUG
-----------------------------------------------------
This is the part that differs from the DDI graph and the part most likely to
be got wrong, so it is stated here as well as in
docs/BIOLOGICAL_GRAPH_LEAKAGE.md.

The existing rule for the drug-drug graph is "training edges only", because a
drug-drug edge IS the label: an edge between two test drugs would hand the
model the answer.

A drug-protein edge is not the label. It is an independent measurement that
exists for a newly approved drug on the day it is approved. Withholding a test
drug's own target annotations would not prevent leakage - it would simulate an
unrealistically ignorant deployment and understate what an honest system can
do. So biological annotations of held-out drugs ARE admissible.

What is NOT admissible, and what this module enforces:

  1. Any relation whose subject and object are both drugs. Those are labels,
     whatever database they came from, and they are train-only. A DDI edge
     imported from DrugCentral is still a DDI edge.
  2. Any statistic FITTED over the graph - normalisation constants, node
     embeddings, frequency weights - must be fitted on training drugs only.
     The graph structure may span all drugs; anything learned from it may not.
  3. Any edge derived from the DDI labels themselves. No adapter may create a
     biological edge by reading the interaction table.

Rule 1 is enforced mechanically below. Rule 2 belongs to whatever consumes the
graph and is carried as ``BioGraph.fittable_nodes``. Rule 3 cannot be enforced
by code and is a review obligation, recorded as such.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

from .schema import (
    Assertion, COMPOUND_LIKE, EntityType, KnowledgeStore, RelationType,
    RELATION_DOMAIN,
)


class LeakageViolation(AssertionError):
    """A relation that would put evaluation information into the graph."""


#: Relations whose two endpoints are both compounds. These encode the
#: prediction target and are therefore restricted to training drugs, no matter
#: which database supplied them.
LABEL_BEARING = frozenset({
    RelationType.DRUG_INTERACTS_WITH_DRUG,
})

#: Relations that connect a drug to biology measured independently of the DDI
#: labels. Admissible for held-out drugs - see the module docstring.
DRUG_BIOLOGY = frozenset({
    RelationType.DRUG_TARGETS_PROTEIN,
    RelationType.DRUG_INHIBITS_PROTEIN,
    RelationType.DRUG_ACTIVATES_PROTEIN,
    RelationType.DRUG_SUBSTRATE_OF_ENZYME,
    RelationType.DRUG_INDUCES_ENZYME,
    RelationType.DRUG_TRANSPORTED_BY,
    RelationType.DRUG_METABOLISED_TO,
})

#: Relations with no drug endpoint at all. Independent of the split entirely.
DRUG_FREE = frozenset({
    RelationType.PROTEIN_INTERACTS_WITH_PROTEIN,
    RelationType.PROTEIN_ACTIVATES_PROTEIN,
    RelationType.PROTEIN_INHIBITS_PROTEIN,
    RelationType.PROTEIN_IN_PATHWAY,
    RelationType.GENE_ENCODES_PROTEIN,
})


@dataclass(frozen=True)
class BioNode:
    id: str
    type: EntityType
    source: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class BioEdge:
    source_id: str
    relation: RelationType
    target_id: str
    evidence_type: str
    confidence: float | None
    provenance_source: str
    provenance_version: str = ""
    reference: str = ""


@dataclass
class BioGraph:
    """Typed nodes and typed edges, plus the record of how it was restricted."""

    nodes: dict[str, BioNode]
    edges: list[BioEdge]
    #: Drugs whose data may be used to FIT anything (rule 2 above).
    fittable_nodes: frozenset[str]
    #: How the build was parameterised, so a graph can be audited after the fact.
    policy: dict
    #: Assertions dropped, by reason. Never silently discarded.
    excluded: dict[str, int] = field(default_factory=dict)

    def neighbours(self, node_id: str,
                   relations: Iterable[RelationType] | None = None) -> set[str]:
        """Undirected neighbourhood. Direction is kept on the edge, but
        "is A connected to B" is a symmetric question and answering it
        directionally is a common off-by-one in this kind of feature."""
        wanted = set(relations) if relations is not None else None
        out: set[str] = set()
        for e in self.edges:
            if wanted is not None and e.relation not in wanted:
                continue
            if e.source_id == node_id:
                out.add(e.target_id)
            elif e.target_id == node_id:
                out.add(e.source_id)
        return out

    def degree(self, node_id: str) -> int:
        return len(self.neighbours(node_id))

    def edges_of(self, relation: RelationType) -> list[BioEdge]:
        return [e for e in self.edges if e.relation == relation]

    def summary(self) -> dict:
        by_type: dict[str, int] = defaultdict(int)
        by_rel: dict[str, int] = defaultdict(int)
        by_src: dict[str, int] = defaultdict(int)
        for n in self.nodes.values():
            by_type[n.type.value] += 1
        for e in self.edges:
            by_rel[e.relation.value] += 1
            by_src[e.provenance_source] += 1
        return {
            "n_nodes": len(self.nodes),
            "n_edges": len(self.edges),
            "n_fittable_nodes": len(self.fittable_nodes),
            "nodes_by_type": dict(by_type),
            "edges_by_relation": dict(by_rel),
            "edges_by_source": dict(by_src),
            "excluded": dict(self.excluded),
            "policy": self.policy,
        }


def build_biograph(
    store: KnowledgeStore,
    *,
    train_drugs: Iterable[str],
    validation_drugs: Iterable[str] = (),
    test_drugs: Iterable[str] = (),
    include_evidence_types: Iterable[str] | None = None,
    exclude_sources: Iterable[str] = (),
    allow_holdout_biology: bool = True,
) -> BioGraph:
    """Turn a store into a split-aware graph.

    :param train_drugs: canonical ids of drugs the model may learn from.
    :param validation_drugs, test_drugs: held out. Their *biological*
        annotations are included by default (see the module docstring); their
        drug-drug edges never are.
    :param allow_holdout_biology: set False to also strip held-out drugs'
        target/enzyme annotations. Not the default, because doing so measures
        a deployment nobody would build - but available as an ablation, since
        "does the biological branch help because of the held-out drug's own
        annotations, or because of the training drugs' ones?" is a real
        question.

    Raises :class:`LeakageViolation` if a label-bearing relation would touch a
    non-training drug. That is a hard failure, not a filter: an adapter
    producing such an edge has a bug, and quietly dropping it would hide it.
    """
    train = set(train_drugs)
    val = set(validation_drugs)
    test = set(test_drugs)
    holdout = val | test
    overlap = train & holdout
    if overlap:
        raise LeakageViolation(
            f"{len(overlap)} drugs are in both train and held-out sets: "
            f"{sorted(overlap)[:5]}"
        )

    keep_evidence = set(include_evidence_types) if include_evidence_types else None
    drop_sources = set(exclude_sources)

    nodes: dict[str, BioNode] = {}
    edges: list[BioEdge] = []
    excluded: dict[str, int] = defaultdict(int)

    def entity_type(cid: str) -> EntityType | None:
        e = store.entity(cid)
        return e.entity_type if e else None

    for assertion in store.assertions:
        rel = assertion.relation
        ev = assertion.evidence
        src = ev.provenance.source

        if src in drop_sources:
            excluded["source_excluded"] += 1
            continue
        if keep_evidence is not None and ev.evidence_type.value not in keep_evidence:
            excluded["evidence_type_excluded"] += 1
            continue

        subject_is_drug = entity_type(rel.subject) in COMPOUND_LIKE
        object_is_drug = entity_type(rel.object) in COMPOUND_LIKE

        # Rule 1, enforced. A drug-drug edge touching a held-out drug is the
        # label, and its presence means an adapter built the graph wrong.
        if rel.predicate in LABEL_BEARING:
            if rel.subject in holdout or rel.object in holdout:
                raise LeakageViolation(
                    f"label-bearing relation {rel.predicate.value} touches a "
                    f"held-out drug: {rel.subject} -> {rel.object}. Drug-drug "
                    f"edges must be built from training pairs only, whatever "
                    f"database they came from."
                )
            if rel.subject not in train or rel.object not in train:
                excluded["label_edge_outside_train"] += 1
                continue

        # A drug-drug edge under a non-label predicate is still both-endpoints-
        # drugs and still carries pair information; treat it the same way.
        elif subject_is_drug and object_is_drug:
            if (rel.subject in holdout) or (rel.object in holdout):
                excluded["drug_drug_edge_touching_holdout"] += 1
                continue

        elif not allow_holdout_biology:
            touching = {rel.subject, rel.object} & holdout
            if touching:
                excluded["holdout_biology_excluded"] += 1
                continue

        for cid in (rel.subject, rel.object):
            if cid in nodes:
                continue
            entity = store.entity(cid)
            if entity is None:
                excluded["edge_with_unknown_endpoint"] += 1
                break
            nodes[cid] = BioNode(cid, entity.entity_type,
                                 entity.provenance.source if entity.provenance else "",
                                 dict(entity.metadata))
        else:
            edges.append(BioEdge(
                source_id=rel.subject,
                relation=rel.predicate,
                target_id=rel.object,
                evidence_type=ev.evidence_type.value,
                confidence=ev.confidence,
                provenance_source=src,
                provenance_version=ev.provenance.source_version,
                reference=ev.reference,
            ))

    return BioGraph(
        nodes=nodes,
        edges=edges,
        # Rule 2: only training drugs may be used to fit anything. Non-drug
        # nodes are fittable - a protein is not held out by a drug-level split.
        fittable_nodes=frozenset(
            {n for n in nodes if n in train}
            | {n for n, node in nodes.items() if node.type not in COMPOUND_LIKE}
        ),
        policy={
            "n_train_drugs": len(train),
            "n_validation_drugs": len(val),
            "n_test_drugs": len(test),
            "allow_holdout_biology": allow_holdout_biology,
            "include_evidence_types": sorted(keep_evidence) if keep_evidence else None,
            "exclude_sources": sorted(drop_sources),
        },
        excluded=dict(excluded),
    )


def assert_relation_domains(store: KnowledgeStore) -> list[str]:
    """Every assertion's endpoints must have types the relation permits.

    Returns the list of violations rather than raising: the caller (the quality
    audit) reports all of them at once, which is more useful than the first.
    """
    problems: list[str] = []
    for a in store.assertions:
        rel = a.relation
        domain = RELATION_DOMAIN.get(rel.predicate)
        if domain is None:
            problems.append(f"unknown relation type {rel.predicate}")
            continue
        subject_types, object_types = domain
        s, o = store.entity(rel.subject), store.entity(rel.object)
        if s is None or o is None:
            continue                       # orphan check reports these
        if s.entity_type not in subject_types:
            problems.append(
                f"{rel.predicate.value}: subject {rel.subject} is "
                f"{s.entity_type.value}, expected one of "
                f"{sorted(t.value for t in subject_types)}")
        if o.entity_type not in object_types:
            problems.append(
                f"{rel.predicate.value}: object {rel.object} is "
                f"{o.entity_type.value}, expected one of "
                f"{sorted(t.value for t in object_types)}")
    return problems
