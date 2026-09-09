"""What two drugs have in common in the body — documented facts, not a prediction.

WHY THIS IS DIFFERENT FROM THE MODEL SCORE. Nothing here is predicted. It is a
lookup of curated annotations: which proteins both drugs are recorded against.
It needs no validation because it forecasts nothing, and it is computable for
ANY pair with annotations — including the ~86.8% of the pair space that has no
documented interaction record at all, which is exactly where a conventional
interaction checker goes silent.

ONLY DRUGBANK, DELIBERATELY. The edge table also carries ChEMBL bioactivity
rows, and those must NOT be used here. ChEMBL screens compounds against shared
assay panels, so two arbitrary drugs "share targets" merely by having been
tested on the same plate: metformin and warfarin share 95 ChEMBL targets and
zero DrugBank ones. Metformin is renally cleared and shares no metabolic route
with warfarin — the DrugBank answer is the true one. Counting panel overlap as
biology would reproduce, in a new guise, the popularity artifact this whole
project exists to expose.

The four relation types are kept apart because they mean different things to a
reader: an enzyme in common is a metabolic route in common, a transporter in
common is a membrane route in common. The plain-language rendering of each
lives in the frontend; this module returns facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]

#: Fixed order; the artifact stores relation as an index into this tuple.
RELATIONS: tuple[str, ...] = ("target", "enzyme", "transporter", "carrier")

#: The only evidence source admitted here. See the module docstring.
SOURCE = "DrugBank_v5.1"


@dataclass(frozen=True)
class SharedProtein:
    uniprot: str
    gene: str
    name: str


class SharedBiologyIndex:
    """Drug -> protein annotations, and the intersection of two drugs' sets."""

    def __init__(
        self,
        uniprot: list[str],
        gene: list[str],
        name: list[str],
        edge_drug: np.ndarray,
        edge_protein: np.ndarray,
        edge_relation: np.ndarray,
        n_drugs: int,
    ) -> None:
        self.uniprot, self.gene, self.name = uniprot, gene, name
        self.edge_drug = edge_drug
        self.edge_protein = edge_protein
        self.edge_relation = edge_relation
        # Per (drug, relation) protein sets, built once. A request is then two
        # set lookups and an intersection.
        self._sets: list[list[set[int]]] = [
            [set() for _ in RELATIONS] for _ in range(n_drugs)
        ]
        for d, p, r in zip(edge_drug, edge_protein, edge_relation):
            self._sets[int(d)][int(r)].add(int(p))

    # -- queries ----------------------------------------------------------
    def shared(self, a_idx: int, b_idx: int) -> dict[str, list[SharedProtein]]:
        """Proteins both drugs are annotated against, grouped by relation.

        Relations with no overlap are omitted, so an empty dict means "no
        shared annotation recorded" — which is not the same as "no interaction"
        and must never be rendered as reassurance.
        """
        out: dict[str, list[SharedProtein]] = {}
        for r, relation in enumerate(RELATIONS):
            common = self._sets[a_idx][r] & self._sets[b_idx][r]
            if common:
                out[relation] = [
                    SharedProtein(self.uniprot[p], self.gene[p], self.name[p])
                    for p in sorted(common, key=lambda i: self.gene[i])
                ]
        return out

    def counts(self, drug_idx: int) -> dict[str, int]:
        return {
            relation: len(self._sets[drug_idx][r])
            for r, relation in enumerate(RELATIONS)
        }

    # -- construction -----------------------------------------------------
    @classmethod
    def from_parquet(cls, drug_ids: list[str]) -> "SharedBiologyIndex":
        """Build from data/mechanism_v1. Used by precompute and the full engine."""
        import pandas as pd

        edges = pd.read_parquet(ROOT / "data" / "mechanism_v1" / "drug_protein_edges.parquet")
        edges = edges[edges.evidence_source == SOURCE].drop_duplicates(
            ["drugbank_id", "uniprot_id", "relation_type"]
        )
        proteins = pd.read_parquet(ROOT / "data" / "mechanism_v1" / "proteins.parquet")

        drug_index = {d: i for i, d in enumerate(drug_ids)}
        edges = edges[edges.drugbank_id.isin(drug_index)]

        keep = proteins[proteins.uniprot_accession.isin(set(edges.uniprot_id))]
        uni = list(keep.uniprot_accession)
        pidx = {u: i for i, u in enumerate(uni)}
        # Fall back to the accession when a gene symbol is absent: an empty
        # label would render as a blank chip with no way to look it up.
        gene = [g if isinstance(g, str) and g else u
                for g, u in zip(keep.gene_name, uni)]
        name = [n if isinstance(n, str) and n else u
                for n, u in zip(keep.protein_name, uni)]

        edges = edges[edges.uniprot_id.isin(pidx)]
        rel_index = {r: i for i, r in enumerate(RELATIONS)}
        return cls(
            uniprot=uni, gene=gene, name=name,
            edge_drug=np.array([drug_index[d] for d in edges.drugbank_id], dtype=np.int16),
            edge_protein=np.array([pidx[u] for u in edges.uniprot_id], dtype=np.int16),
            edge_relation=np.array([rel_index[r] for r in edges.relation_type], dtype=np.int8),
            n_drugs=len(drug_ids),
        )

    @classmethod
    def from_arrays(cls, z, n_drugs: int) -> "SharedBiologyIndex":
        """Build from the precomputed .npz. Used by the lean server."""
        return cls(
            uniprot=[str(x) for x in z["bio_uniprot"]],
            gene=[str(x) for x in z["bio_gene"]],
            name=[str(x) for x in z["bio_name"]],
            edge_drug=z["bio_edge_drug"],
            edge_protein=z["bio_edge_protein"],
            edge_relation=z["bio_edge_relation"],
            n_drugs=n_drugs,
        )

    def to_arrays(self) -> dict:
        return {
            "bio_uniprot": np.array(self.uniprot, dtype=object),
            "bio_gene": np.array(self.gene, dtype=object),
            "bio_name": np.array(self.name, dtype=object),
            "bio_edge_drug": self.edge_drug,
            "bio_edge_protein": self.edge_protein,
            "bio_edge_relation": self.edge_relation,
        }
