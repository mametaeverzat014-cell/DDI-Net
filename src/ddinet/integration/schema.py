"""
Canonical, source-independent schema for the biomedical layer.

THE ONE RULE THIS FILE EXISTS TO ENFORCE
-----------------------------------------
Provenance is never collapsed. If DrugCentral and ChEMBL both say that
warfarin acts on VKORC1, that is TWO assertions about one relation, not one
fact. The distinction matters because:

  * agreement between independent sources is evidence, and it is only
    measurable if the sources are still distinguishable;
  * a relation asserted by one source with a bioactivity measurement and by
    another as a computational inference are not interchangeable, and a single
    averaged "confidence" number would hide exactly that;
  * when a source is later found to be wrong, its assertions must be
    removable without taking the others with them.

So the store below keeps ``Assertion`` objects - (relation, evidence) - and a
relation's support is a LIST of assertions. ``agreement()`` reports how many
distinct sources back each relation; nothing in this module ever merges two
sources into one number.

WHAT IS DELIBERATELY NOT HERE
------------------------------
No mechanism inference, no ranking of sources, no default confidence. A source
that does not report a confidence gets ``None``, not 1.0: inventing a number
because the field is required is how fabricated data enters a pipeline.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Iterable, Iterator


class EntityType(str, Enum):
    """Node kinds. Deliberately finer than the model will need at first.

    ENZYME and TRANSPORTER are subtypes of PROTEIN and share its key space
    (a UniProt accession). They are separate types because they participate in
    different mechanisms - an enzyme metabolises, a transporter moves - and
    collapsing them would make PK mechanism statements unexpressible.
    """

    DRUG = "Drug"
    COMPOUND = "Compound"
    PROTEIN = "Protein"
    GENE = "Gene"
    ENZYME = "Enzyme"
    TRANSPORTER = "Transporter"
    TARGET = "Target"
    PATHWAY = "Pathway"
    METABOLITE = "Metabolite"
    INTERACTION = "Interaction"
    MECHANISM = "Mechanism"
    EVIDENCE = "Evidence"


#: Compound-like types share the InChIKey key space.
COMPOUND_LIKE = frozenset({
    EntityType.DRUG, EntityType.COMPOUND, EntityType.METABOLITE,
})

#: Families whose members are specialisations of one general type. Different
#: sources know different amounts about the same node - DrugCentral records
#: that Q9UBN7 is an enzyme, Reactome only that it is a protein - and neither
#: is wrong. Registering the same id under two members of one family is
#: therefore a refinement, not a conflict.
_TYPE_FAMILIES = ((PROTEIN_LIKE := frozenset({
    EntityType.PROTEIN, EntityType.ENZYME,
    EntityType.TRANSPORTER, EntityType.TARGET,
}), EntityType.PROTEIN),
    (COMPOUND_LIKE, EntityType.COMPOUND))


def reconcile_types(existing: EntityType, incoming: EntityType) -> EntityType | None:
    """The type to keep, or None when the two are genuinely incompatible.

    Within a family the more specific type wins over the general one. Two
    DIFFERENT specific types (an id recorded as both Enzyme and Transporter)
    fall back to the general type rather than picking one: the sources
    disagree, and choosing arbitrarily would make the result depend on adapter
    order - the property `add_entity` exists to guarantee against.
    """
    if existing is incoming:
        return existing
    for family, general in _TYPE_FAMILIES:
        if existing in family and incoming in family:
            if existing is general:
                return incoming
            if incoming is general:
                return existing
            return general
    return None


class RelationType(str, Enum):
    """Edge kinds.

    Named after what the SOURCE asserts, not after what it would mean
    mechanistically. `DRUG_TARGETS_PROTEIN` says a database recorded an
    interaction between a compound and a protein; it does not say the protein
    mediates any drug-drug interaction. Keeping the names at the level of the
    assertion is what stops a ChEMBL activity from silently becoming a DDI
    mechanism downstream.
    """

    DRUG_TARGETS_PROTEIN = "drug_targets_protein"
    DRUG_INHIBITS_PROTEIN = "drug_inhibits_protein"
    DRUG_ACTIVATES_PROTEIN = "drug_activates_protein"
    DRUG_SUBSTRATE_OF_ENZYME = "drug_substrate_of_enzyme"
    DRUG_INDUCES_ENZYME = "drug_induces_enzyme"
    DRUG_TRANSPORTED_BY = "drug_transported_by"
    DRUG_METABOLISED_TO = "drug_metabolised_to"
    DRUG_INTERACTS_WITH_DRUG = "drug_interacts_with_drug"
    DRUG_CAUSES_EFFECT = "drug_causes_effect"
    PROTEIN_INTERACTS_WITH_PROTEIN = "protein_interacts_with_protein"
    PROTEIN_ACTIVATES_PROTEIN = "protein_activates_protein"
    PROTEIN_INHIBITS_PROTEIN = "protein_inhibits_protein"
    PROTEIN_IN_PATHWAY = "protein_in_pathway"
    GENE_ENCODES_PROTEIN = "gene_encodes_protein"
    COMPOUND_SAME_AS = "compound_same_as"


#: Which (subject type, object type) pairs each relation may connect.
#: Used by the quality audit to reject impossible edges - a Pathway that
#: "targets" a Drug is a bug in an adapter, not a finding.
#: A gene symbol is a COARSER identity for the same gene product. Some sources
#: give only the symbol (Reactome FI is gene-level throughout; DrugCentral rows
#: without an accession have nothing else), so a relation whose object is a
#: protein must also accept a Gene node. These are upgradeable: once a UniProt
#: accession <-> symbol table exists, such nodes can be re-keyed. Until then,
#: refusing them would discard real data on a technicality.
PROTEIN_OR_GENE = PROTEIN_LIKE | frozenset({EntityType.GENE})

RELATION_DOMAIN: dict[RelationType, tuple[frozenset, frozenset]] = {
    RelationType.DRUG_TARGETS_PROTEIN: (COMPOUND_LIKE, PROTEIN_OR_GENE),
    RelationType.DRUG_INHIBITS_PROTEIN: (COMPOUND_LIKE, PROTEIN_OR_GENE),
    RelationType.DRUG_ACTIVATES_PROTEIN: (COMPOUND_LIKE, PROTEIN_OR_GENE),
    RelationType.DRUG_SUBSTRATE_OF_ENZYME: (COMPOUND_LIKE, PROTEIN_OR_GENE),
    RelationType.DRUG_INDUCES_ENZYME: (COMPOUND_LIKE, PROTEIN_OR_GENE),
    RelationType.DRUG_TRANSPORTED_BY: (COMPOUND_LIKE, PROTEIN_OR_GENE),
    RelationType.DRUG_METABOLISED_TO: (COMPOUND_LIKE, COMPOUND_LIKE),
    RelationType.DRUG_INTERACTS_WITH_DRUG: (COMPOUND_LIKE, COMPOUND_LIKE),
    RelationType.DRUG_CAUSES_EFFECT: (COMPOUND_LIKE, frozenset({EntityType.MECHANISM})),
    RelationType.PROTEIN_INTERACTS_WITH_PROTEIN: (PROTEIN_OR_GENE, PROTEIN_OR_GENE),
    RelationType.PROTEIN_ACTIVATES_PROTEIN: (PROTEIN_OR_GENE, PROTEIN_OR_GENE),
    RelationType.PROTEIN_INHIBITS_PROTEIN: (PROTEIN_OR_GENE, PROTEIN_OR_GENE),
    RelationType.PROTEIN_IN_PATHWAY: (PROTEIN_OR_GENE, frozenset({EntityType.PATHWAY})),
    RelationType.GENE_ENCODES_PROTEIN: (frozenset({EntityType.GENE}), PROTEIN_LIKE),
    RelationType.COMPOUND_SAME_AS: (COMPOUND_LIKE, COMPOUND_LIKE),
}

#: Relations that are symmetric. Stored once in a canonical orientation; a
#: store that kept both directions would double every degree and quietly
#: change every degree-based measurement in this project.
SYMMETRIC = frozenset({
    RelationType.PROTEIN_INTERACTS_WITH_PROTEIN,
    RelationType.DRUG_INTERACTS_WITH_DRUG,
    RelationType.COMPOUND_SAME_AS,
})


class EvidenceType(str, Enum):
    """What KIND of thing the source did to arrive at the assertion.

    Ordered from most direct to least, but the order is NOT a ranking of
    truth - it is a statement about which errors are likely. EXPERIMENTAL has
    a low false-positive rate and a high incompleteness rate; INFERRED has the
    opposite; CURATED carries class-effect generalisation; CLINICAL carries
    reporting bias. Averaging them into one number destroys exactly this.
    """

    EXPERIMENTAL = "experimental"
    BIOACTIVITY = "bioactivity"
    CURATED = "curated"
    CLINICAL = "clinical"
    COMPUTATIONAL = "computational"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Provenance:
    """Where an assertion came from, precisely enough to be re-fetched."""

    source: str                       # "chembl", "drugcentral", "reactome_fi"
    source_version: str = ""          # "36", "2021_09_01", "04142025"
    retrieval_date: date | None = None
    source_id: str = ""               # the row/record id inside that source

    def key(self) -> tuple[str, str]:
        return (self.source, self.source_version)


@dataclass(frozen=True)
class Evidence:
    """One source's grounds for one assertion.

    ``confidence`` is Optional and stays None when the source reports none.
    A default of 1.0 would be a number this project invented, and it would
    propagate into every downstream aggregate looking like a measurement.
    """

    evidence_type: EvidenceType
    provenance: Provenance
    reference: str = ""               # PubMed id, DOI, assay id
    confidence: float | None = None
    #: Source-specific numbers kept verbatim (pchembl_value, standard_value,
    #: Reactome score...). Never interpreted here.
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"confidence must be in [0, 1] or None, got {self.confidence}. "
                "A source's own score on a different scale belongs in metadata."
            )


@dataclass(frozen=True)
class Entity:
    """A node. ``canonical_id`` is assigned by the identifier layer."""

    canonical_id: str
    entity_type: EntityType
    name: str = ""
    synonyms: tuple[str, ...] = ()
    provenance: Provenance | None = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.canonical_id:
            raise ValueError("canonical_id must not be empty")


@dataclass(frozen=True)
class Relation:
    """The claim itself, without any source attached.

    Hashable and used as a dict key, which is what lets several assertions
    about the same claim be grouped without merging them.
    """

    subject: str                      # canonical_id
    predicate: RelationType
    object: str                       # canonical_id

    def canonical(self) -> "Relation":
        """Orient symmetric relations deterministically."""
        if self.predicate in SYMMETRIC and self.subject > self.object:
            return Relation(self.object, self.predicate, self.subject)
        return self


@dataclass(frozen=True)
class Assertion:
    """One source saying one thing. The unit this store actually holds."""

    relation: Relation
    evidence: Evidence


class KnowledgeStore:
    """Entities plus assertions, with sources kept apart.

    Not a graph: it has no adjacency and no traversal. Turning it into a graph
    is a separate, filtered step (``integration/biograph.py``), because that
    step is where split-awareness and leakage control belong.
    """

    def __init__(self) -> None:
        self._entities: dict[str, Entity] = {}
        self._assertions: list[Assertion] = []
        self._by_relation: dict[Relation, list[Assertion]] = defaultdict(list)

    # -- entities ----------------------------------------------------------
    def add_entity(self, entity: Entity) -> Entity:
        """Register a node. A second registration of the same id MERGES
        synonyms and metadata rather than overwriting.

        Overwriting would make the result depend on adapter execution order,
        which is the kind of bug that shows up as an unreproducible count.
        """
        existing = self._entities.get(entity.canonical_id)
        if existing is None:
            self._entities[entity.canonical_id] = entity
            return entity
        resolved = reconcile_types(existing.entity_type, entity.entity_type)
        if resolved is None:
            raise ValueError(
                f"{entity.canonical_id} is already registered as "
                f"{existing.entity_type.value}, cannot re-register as "
                f"{entity.entity_type.value}"
            )
        merged = Entity(
            canonical_id=existing.canonical_id,
            entity_type=resolved,
            name=existing.name or entity.name,
            synonyms=tuple(sorted(set(existing.synonyms) | set(entity.synonyms))),
            provenance=existing.provenance or entity.provenance,
            metadata={**entity.metadata, **existing.metadata},
        )
        self._entities[entity.canonical_id] = merged
        return merged

    def entity(self, canonical_id: str) -> Entity | None:
        return self._entities.get(canonical_id)

    @property
    def entities(self) -> list[Entity]:
        return list(self._entities.values())

    def entities_of(self, entity_type: EntityType) -> list[Entity]:
        return [e for e in self._entities.values() if e.entity_type == entity_type]

    # -- assertions --------------------------------------------------------
    def add_assertion(self, relation: Relation, evidence: Evidence) -> Assertion:
        """Record that ONE source asserts ONE relation.

        Adding the same relation from a second source appends; it does not
        deduplicate. That is the whole point of this store.
        """
        rel = relation.canonical()
        assertion = Assertion(rel, evidence)
        self._assertions.append(assertion)
        self._by_relation[rel].append(assertion)
        return assertion

    @property
    def assertions(self) -> list[Assertion]:
        return list(self._assertions)

    @property
    def relations(self) -> list[Relation]:
        """Distinct claims, regardless of how many sources back each one."""
        return list(self._by_relation)

    def support(self, relation: Relation) -> list[Assertion]:
        return list(self._by_relation.get(relation.canonical(), []))

    def sources_for(self, relation: Relation) -> set[str]:
        return {a.evidence.provenance.source for a in self.support(relation)}

    def agreement(self) -> dict[Relation, int]:
        """Relation -> number of DISTINCT sources asserting it.

        The measurement that keeping provenance apart is for. A relation backed
        by three independent sources is a different object from one backed by
        the same source three times, and this is where that shows.
        """
        return {rel: len({a.evidence.provenance.source for a in assertions})
                for rel, assertions in self._by_relation.items()}

    def filter(self, *, sources: Iterable[str] | None = None,
               evidence_types: Iterable[EvidenceType] | None = None,
               predicates: Iterable[RelationType] | None = None) -> "KnowledgeStore":
        """A new store containing only the assertions that match.

        Used for the required ablations: "with and without computationally
        inferred edges", "curated sources only". Entities are carried over
        whole - a filtered store with dangling ids would fail the quality
        audit's orphan check for the wrong reason.
        """
        src = set(sources) if sources is not None else None
        ev = set(evidence_types) if evidence_types is not None else None
        pred = set(predicates) if predicates is not None else None

        out = KnowledgeStore()
        for entity in self._entities.values():
            out.add_entity(entity)
        for a in self._assertions:
            if src is not None and a.evidence.provenance.source not in src:
                continue
            if ev is not None and a.evidence.evidence_type not in ev:
                continue
            if pred is not None and a.relation.predicate not in pred:
                continue
            out.add_assertion(a.relation, a.evidence)
        return out

    def __iter__(self) -> Iterator[Assertion]:
        return iter(self._assertions)

    def __len__(self) -> int:
        return len(self._assertions)

    def summary(self) -> dict:
        by_source: dict[str, int] = defaultdict(int)
        by_evidence: dict[str, int] = defaultdict(int)
        by_predicate: dict[str, int] = defaultdict(int)
        by_type: dict[str, int] = defaultdict(int)
        for a in self._assertions:
            by_source[a.evidence.provenance.source] += 1
            by_evidence[a.evidence.evidence_type.value] += 1
            by_predicate[a.relation.predicate.value] += 1
        for e in self._entities.values():
            by_type[e.entity_type.value] += 1
        agreement = self.agreement()
        multi = sum(1 for n in agreement.values() if n > 1)
        return {
            "n_entities": len(self._entities),
            "n_assertions": len(self._assertions),
            "n_distinct_relations": len(self._by_relation),
            "n_relations_with_multiple_sources": multi,
            "entities_by_type": dict(by_type),
            "assertions_by_source": dict(by_source),
            "assertions_by_evidence_type": dict(by_evidence),
            "assertions_by_predicate": dict(by_predicate),
        }
