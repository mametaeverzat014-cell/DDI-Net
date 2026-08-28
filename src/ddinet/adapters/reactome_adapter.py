"""
Reactome -> canonical assertions.

Wraps ``ddinet.data.reactome``; does not re-parse the files.

TWO FILES, TWO EVIDENCE TYPES
------------------------------
The UniProt-keyed file is curated and every row carries a PubMed reference:
EvidenceType.CURATED, and the reference is kept.

The FI file is wider and carries the sign of the interaction, but 29.2% of its
edges are the output of Reactome's own predictor. Those are
EvidenceType.COMPUTATIONAL and are EXCLUDED by default (``include_predicted``),
because training on them without separating them means training partly on
another model's output - a circular-label risk no downstream metric reveals.

SCALE, AND WHY restrict_to EXISTS
----------------------------------
The FI network is 193 058 edges over 9 968 genes after dropping predicted ones.
Materialising all of it as assertion objects is possible but pointless: only
the neighbourhood of drugs' target proteins can ever reach a drug pair. Passing
``restrict_to`` keeps the store to that neighbourhood, which is a performance
choice with no effect on any feature that is actually computable.

WHAT AN EDGE MEANS
------------------
`complex` and `input` annotations arise from CO-MEMBERSHIP: two proteins in one
complex, or two inputs to one reaction. They mean "occur together", not "one
acts on the other". They are emitted as the neutral
PROTEIN_INTERACTS_WITH_PROTEIN. Only `activate`/`inhibit` annotations become
the directed, signed relations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from ..data import reactome as rx
from ..integration.identifiers import canonical_gene_id, canonical_protein_id, normalise
from ..integration.schema import (
    Entity, EntityType, Evidence, EvidenceType, KnowledgeStore, Provenance,
    Relation, RelationType,
)
from . import BaseAdapter, SourceDescription


@dataclass
class ReactomeFIAdapter(BaseAdapter):
    """Gene-level functional interactions, signed where the source says so."""

    def describe(self) -> SourceDescription:
        return SourceDescription(
            name="reactome_fi",
            version="04142025",
            licence="CC0 1.0",
            provides=("protein_interacts_with_protein",
                      "protein_activates_protein", "protein_inhibits_protein"),
            required_files=(f"reactome_fi/{rx.FI_FILE}",),
            download_url="https://reactome.org/download-data",
            retrieval_date=date(2026, 8, 27),
            notes=("29.2% of edges are annotated `predicted` - Reactome's own "
                   "ML output, EvidenceType.COMPUTATIONAL, excluded by default."),
        )

    def _extract(self, store: KnowledgeStore, *,
                 include_predicted: bool = False,
                 restrict_to: Iterable[str] | None = None,
                 min_score: float = 0.0) -> KnowledgeStore:
        desc = self.describe()
        net = rx.load_fi_network(include_predicted=include_predicted,
                                 min_score=min_score)
        keep = {normalise("gene", g) for g in restrict_to} if restrict_to else None

        for row_index, row in enumerate(net.edges.itertuples(index=False)):
            a, b = normalise("gene", row.gene_a), normalise("gene", row.gene_b)
            if a is None or b is None or a == b:
                continue                     # self-loops: see pathway_adjacency
            if keep is not None and not (a in keep or b in keep):
                continue

            ann = (row.annotation or "").lower()
            if "inhibit" in ann:
                predicate = RelationType.PROTEIN_INHIBITS_PROTEIN
            elif "activate" in ann:
                predicate = RelationType.PROTEIN_ACTIVATES_PROTEIN
            else:
                # complex / input / catalyse: co-occurrence, not action.
                predicate = RelationType.PROTEIN_INTERACTS_WITH_PROTEIN

            for gene in (a, b):
                store.add_entity(Entity(canonical_gene_id(gene), EntityType.GENE,
                                        name=gene))
            store.add_assertion(
                Relation(canonical_gene_id(a), predicate, canonical_gene_id(b)),
                Evidence(
                    (EvidenceType.COMPUTATIONAL if row.is_predicted
                     else EvidenceType.CURATED),
                    # The row index distinguishes two edges between the same
                    # pair under different annotations; without it they would
                    # be counted as one source repeating itself.
                    Provenance(desc.name, desc.version, desc.retrieval_date,
                               str(row_index)),
                    # Score is Reactome's internal confidence, NOT P(true), so
                    # it is metadata rather than `confidence`.
                    metadata={"annotation": row.annotation,
                              "direction": row.direction,
                              "reactome_score": float(row.score)},
                ))
        return store


@dataclass
class ReactomeUniProtAdapter(BaseAdapter):
    """The conservative, fully literature-referenced protein network."""

    def describe(self) -> SourceDescription:
        return SourceDescription(
            name="reactome_uniprot",
            version="homo_sapiens",
            licence="CC0 1.0",
            provides=("protein_interacts_with_protein", "protein_in_pathway"),
            required_files=(f"reactome/{rx.UNIPROT_FILE}",),
            download_url="https://reactome.org/download-data",
            retrieval_date=date(2026, 8, 27),
            notes="100% of rows carry a PubMed reference; 6.3% are homodimers.",
        )

    def _extract(self, store: KnowledgeStore, *,
                 restrict_to: Iterable[str] | None = None,
                 include_self: bool = False) -> KnowledgeStore:
        desc = self.describe()
        table = rx.load_uniprot_interactions()
        keep = {normalise("uniprot", a) for a in restrict_to} if restrict_to else None

        for row in table.itertuples(index=False):
            a = normalise("uniprot", row.uniprot_a)
            b = normalise("uniprot", row.uniprot_b)
            if a is None or b is None:
                continue
            if a == b and not include_self:
                continue
            if keep is not None and not (a in keep or b in keep):
                continue
            for acc in (a, b):
                store.add_entity(Entity(canonical_protein_id(acc),
                                        EntityType.PROTEIN, name=acc))
            store.add_assertion(
                Relation(canonical_protein_id(a),
                         RelationType.PROTEIN_INTERACTS_WITH_PROTEIN,
                         canonical_protein_id(b)),
                Evidence(
                    EvidenceType.CURATED,
                    Provenance(desc.name, desc.version, desc.retrieval_date,
                               str(row.context)),
                    reference=str(row.pubmed),
                    metadata={"interaction_type": row.interaction_type,
                              "context": row.context},
                ))
        return store
