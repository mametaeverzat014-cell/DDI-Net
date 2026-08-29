"""
Per-drug biological context assembled from the frozen DDI_MECH_1705_V1 dataset.

WHAT THIS MODULE IS FOR
-----------------------
Phase A-2 answered the project's first question and answered it negatively: the
DDI-network branch helps on the leaky ``random_pair`` split and *hurts* on every
honest split (dual - gine = +0.10 leaky, -0.02..-0.03 drug- and
scaffold-disjoint). The branch that carried that signal was topology over the
DDI graph itself, and a drug the model has never seen has no such topology.

V2 replaces it with context that exists for an unseen drug: which proteins it is
annotated against, and which Reactome pathways those proteins sit in. This
module is the loader for that context. It does not train anything and it never
touches a DDI label.

WHY A SEPARATE MODULE FROM ``integration/``
-------------------------------------------
``ddinet.integration`` is the provenance-preserving knowledge store: assertions
kept apart by source, never merged, with match quality attached. It is the right
structure for auditing what we know and where it came from, and the wrong
structure for a training loop that needs contiguous integer index arrays.

This module is the compilation step between the two. It reads the frozen
Parquet snapshot, applies one evidence policy, and emits index arrays. The
provenance question has already been answered upstream; here the question is
only "which integers does drug d carry".

THE UNIT OF BIOLOGY IS A TRIPLE, NOT A PROTEIN
-----------------------------------------------
``docs/V2_ARCHITECTURE_PLAN.md`` section 4.3 gives each element of P(d) three
embeddings: the protein, the relation type (target/enzyme/transporter/carrier)
and the evidence type (documented / curated MoA / experimental bioactivity).
So the set element is the triple ``(protein, relation, evidence)``, and a drug
that both inhibits CYP3A4 (DrugBank ``enzyme``) and has ChEMBL bioactivity
against it contributes two elements.

Duplicates BELOW that granularity are collapsed. The raw table carries 146,743
rows but only 94,088 distinct triples: the difference is ChEMBL assay rows, one
per measurement. Keeping them would weight a protein by how many times it was
assayed, which is literature attention, not biology - precisely the popularity
confound this phase exists to control. Collapsing is also what makes the
CONTROL F comparison exact: the shuffle preserves distinct-pair degree, and it
was verified here that row, pair and triple degree are all identical between
``drug_protein_edges.parquet`` and its shuffled twin, so true and shuffled
models see set sizes that match element for element.

COUNTS ARE DERIVED HERE, NOT READ FROM ``drugs.parquet``
---------------------------------------------------------
``drugs.parquet`` carries ``n_targets``/``n_proteins``/``n_pathways`` columns.
They are **DrugBank-only** counts: ``n_pathways`` reproduces exactly (1.000)
when the derivation is restricted to ``evidence_source == DrugBank_v5.1`` and
not at all (0.229) over the full edge set. Two reasons not to use them:

  1. an evidence ablation (M1 -> M4) changes which sources are active, so the
     counts must move with the policy;
  2. CONTROL F reshuffles proteins, and pathways are *derived* from proteins, so
     the shuffled graph's pathway counts are genuinely different numbers.

Reading the frozen column in either case would feed the model a count that does
not describe the biology it is being shown. ``count_discrepancy_report`` records
the mismatch against ``drugs.parquet`` rather than hiding it.

MISSING IS NOT ZERO
-------------------
67 of 1,705 drugs have no protein annotation from any source and 91 have no
pathway. That is absence of evidence. The loader reports them as empty sets and
flags them in ``has_protein`` / ``has_pathway``; what the model does with an
empty set (a learned MISSING token, plus the mask handed to the decoder) is the
model's business, not the loader's. Nothing is imputed here.

LEAKAGE POSITION
----------------
Drug-level biological annotation is legitimately available for a held-out drug
- that is the whole inductive premise of V2, and ``integration/biograph.py``
states the same rule with ``allow_holdout_biology=True``. What is NOT available
is anything derived from DDI labels. This module never opens
``ddi_positive_labels.parquet`` and never reads a split assignment; the split is
applied downstream, by whoever fits a transform. See
``docs/BIOLOGICAL_GRAPH_LEAKAGE.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

#: Frozen dataset root. The V2 preregistration names this path and freezes it;
#: an override exists only so the CONTROL F variant can be pointed at its own
#: directory and so tests can build a miniature copy.
MECHANISM_V1 = Path("data/mechanism_v1")

#: Relation types in ``drug_protein_edges.parquet``, in a FIXED order. The order
#: is the embedding row index, so it must not be derived from the data - a
#: dataset that happened to contain no carriers would otherwise renumber every
#: other relation and silently invalidate a saved checkpoint.
RELATION_TYPES: tuple[str, ...] = ("target", "enzyme", "transporter", "carrier")

#: Evidence types, same fixed-order rule.
EVIDENCE_TYPES: tuple[str, ...] = (
    "DOCUMENTED_DATABASE_RELATION",   # DrugBank v5.1 curated drug-protein
    "CURATED_MOA",                    # ChEMBL 36 drug_mechanism
    "EXPERIMENTAL_BIOACTIVITY",       # ChEMBL 36 activities, assay confidence >= 8
)

_RELATION_INDEX = {r: i for i, r in enumerate(RELATION_TYPES)}
_EVIDENCE_INDEX = {e: i for i, e in enumerate(EVIDENCE_TYPES)}


@dataclass(frozen=True)
class EvidencePolicy:
    """Which biological evidence is allowed into a drug's representation.

    The evidence ablation of ``docs/V2_ARCHITECTURE_PLAN.md`` section 8 changes
    *only* this object. Architecture, hyperparameters, splits and negative
    sampling are held fixed, so the M-to-M difference is attributable to the
    evidence source and to nothing else.

    :param evidence_types: allowed values of the ``evidence_type`` column.
        Empty means the protein level is switched off entirely (M0, the
        molecular-only Phase A-2 baseline, which is reused rather than
        retrained - it is here only so the ladder is expressible).
    :param use_pathways: whether the pathway level runs at all. Pathways are
        derived from whatever proteins survive ``evidence_types``, so M4 - M3
        isolates Reactome given a fixed protein set.
    """

    name: str
    evidence_types: frozenset[str]
    use_pathways: bool

    def __post_init__(self) -> None:
        unknown = set(self.evidence_types) - set(EVIDENCE_TYPES)
        if unknown:
            raise ValueError(f"Unknown evidence types: {sorted(unknown)}")


#: The preregistered evidence ladder. M0 is listed for completeness; it is the
#: Phase A-2 GINE result and is NOT retrained (preregistration section 11).
EVIDENCE_POLICIES: dict[str, EvidencePolicy] = {
    "M0": EvidencePolicy("M0", frozenset(), use_pathways=False),
    "M1": EvidencePolicy("M1", frozenset({"DOCUMENTED_DATABASE_RELATION"}), False),
    "M2": EvidencePolicy(
        "M2", frozenset({"DOCUMENTED_DATABASE_RELATION", "CURATED_MOA"}), False
    ),
    "M3": EvidencePolicy("M3", frozenset(EVIDENCE_TYPES), use_pathways=False),
    "M4": EvidencePolicy("M4", frozenset(EVIDENCE_TYPES), use_pathways=True),
}

#: Scalar count features, in a FIXED order. This is CONTROL A's entire feature
#: set (preregistration section 8, H-V2-4) - the null model for "biological
#: popularity". If BIO-GINE cannot beat a random forest on these eight numbers,
#: then protein *identity* contributes nothing and the biological encoder is a
#: more expensive way to count annotations.
COUNT_FEATURES: tuple[str, ...] = (
    "n_targets",
    "n_enzymes",
    "n_transporters",
    "n_carriers",
    "n_proteins",
    "n_pathways",
    "n_adverse_events",
    "n_chembl_proteins",
)


@dataclass
class BiologyBundle:
    """Compiled per-drug biology, indexed for a training loop.

    Every array is aligned to ``drug_ids``: position *i* everywhere refers to
    the same drug. That ordering is the contract with the model, which indexes
    pairs by integer.

    :param protein_items: for drug *i*, an ``(n_i, 3)`` int array whose columns
        are ``(protein_index, relation_index, evidence_index)``. Rows are the
        elements of P(d). ``n_i`` may be 0.
    :param pathway_items: for drug *i*, a 1-D int array of pathway indices,
        the elements of Q(d). May be empty.
    :param counts: ``(N, 8)`` float array in ``COUNT_FEATURES`` order.
    """

    drug_ids: list[str]
    protein_vocab: list[str]
    pathway_vocab: list[str]
    protein_items: list[np.ndarray]
    pathway_items: list[np.ndarray]
    counts: np.ndarray
    policy: EvidencePolicy
    source: str = "true"
    provenance: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        n = len(self.drug_ids)
        if not (len(self.protein_items) == len(self.pathway_items) == n):
            raise ValueError("per-drug arrays must align with drug_ids")
        if self.counts.shape != (n, len(COUNT_FEATURES)):
            raise ValueError(
                f"counts must be ({n}, {len(COUNT_FEATURES)}), "
                f"got {self.counts.shape}"
            )
        self.index = {d: i for i, d in enumerate(self.drug_ids)}

    # -- sizes ------------------------------------------------------------
    @property
    def n_drugs(self) -> int:
        return len(self.drug_ids)

    @property
    def n_proteins(self) -> int:
        """Vocabulary size, not the count for any one drug.

        Taken from the vocabulary rather than from the observed maximum: an
        evidence policy that excludes a source shrinks the observed set but must
        NOT shrink the embedding table, or M1 and M4 checkpoints would have
        incompatible shapes and could not be compared parameter-for-parameter.
        """
        return len(self.protein_vocab)

    @property
    def n_pathways(self) -> int:
        return len(self.pathway_vocab)

    # -- masks ------------------------------------------------------------
    def has_protein(self) -> np.ndarray:
        """Per-drug boolean: is P(d) non-empty?

        Handed to the pair decoder as an auxiliary feature so it can score a
        no-biology drug differently rather than being told, via a zero vector,
        that the drug has no targets.
        """
        return np.array([len(x) > 0 for x in self.protein_items], dtype=bool)

    def has_pathway(self) -> np.ndarray:
        return np.array([len(x) > 0 for x in self.pathway_items], dtype=bool)

    def count_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.counts, index=self.drug_ids, columns=COUNT_FEATURES)

    def describe(self) -> dict:
        """Everything a report needs to state what this bundle contained."""
        hp, hq = self.has_protein(), self.has_pathway()
        sizes = np.array([len(x) for x in self.protein_items])
        qsizes = np.array([len(x) for x in self.pathway_items])
        return {
            "policy": self.policy.name,
            "source": self.source,
            "n_drugs": self.n_drugs,
            "protein_vocab": self.n_proteins,
            "pathway_vocab": self.n_pathways,
            "drugs_with_protein": int(hp.sum()),
            "drugs_without_protein": int((~hp).sum()),
            "drugs_with_pathway": int(hq.sum()),
            "drugs_without_pathway": int((~hq).sum()),
            "protein_items_total": int(sizes.sum()),
            "protein_items_median": float(np.median(sizes)),
            "pathway_items_total": int(qsizes.sum()),
            "pathway_items_median": float(np.median(qsizes)),
            **self.provenance,
        }


def _distinct_triples(edges: pd.DataFrame) -> pd.DataFrame:
    """Collapse assay-level duplicates to distinct (drug, protein, rel, ev)."""
    return edges[
        ["drugbank_id", "uniprot_id", "relation_type", "evidence_type"]
    ].drop_duplicates()


def load_biology(
    root: Path | str = MECHANISM_V1,
    *,
    policy: EvidencePolicy | str = "M4",
    drug_protein_path: Path | str | None = None,
    drug_ids: list[str] | None = None,
) -> BiologyBundle:
    """Compile the frozen biology snapshot under one evidence policy.

    :param root: dataset directory. Everything except the drug-protein edge
        table is read from here.
    :param policy: an :class:`EvidencePolicy` or a key of ``EVIDENCE_POLICIES``.
    :param drug_protein_path: override for the drug-protein edge table. This is
        how CONTROL F is run: point it at
        ``data/mechanism_v1_controls/.../drug_protein_edges_shuffled.parquet``
        and leave every other input alone, so proteins are randomised while
        pathway membership, the pathway vocabulary and the split are untouched.
        The shuffled file must not be produced here - it is frozen once, before
        training, and regenerating it would break the preregistration.
    :param drug_ids: explicit drug ordering. Defaults to ``drugs.parquet`` order,
        which is the ordering the rest of the pipeline uses.

    The vocabularies are built from the FULL edge table, before the evidence
    filter, so that every policy in the ladder yields the same embedding shapes.
    """
    root = Path(root)
    if isinstance(policy, str):
        if policy not in EVIDENCE_POLICIES:
            raise ValueError(
                f"Unknown policy {policy!r}; expected one of "
                f"{sorted(EVIDENCE_POLICIES)}"
            )
        policy = EVIDENCE_POLICIES[policy]

    drugs = pd.read_parquet(root / "drugs.parquet")
    if drug_ids is None:
        drug_ids = list(drugs["drugbank_id"])

    dp_path = Path(drug_protein_path) if drug_protein_path else root / "drug_protein_edges.parquet"
    edges = pd.read_parquet(dp_path)
    pathway_edges = pd.read_parquet(root / "protein_pathway_edges.parquet")

    # Vocabularies: union of the edge table and the node tables, sorted. Sorting
    # rather than first-appearance order makes the integer assignment a pure
    # function of the ID set, so a checkpoint stays valid across a re-run and a
    # test can assert an exact index.
    protein_vocab = sorted(
        set(edges["uniprot_id"].dropna())
        | set(pd.read_parquet(root / "proteins.parquet")["uniprot_accession"].dropna())
    )
    pathway_vocab = sorted(
        set(pathway_edges["reactome_pathway_id"].dropna())
        | set(pd.read_parquet(root / "pathways.parquet")["pathway_id"].dropna())
    )
    protein_index = {p: i for i, p in enumerate(protein_vocab)}
    pathway_index = {q: i for i, q in enumerate(pathway_vocab)}

    triples = _distinct_triples(edges)
    active = triples[triples["evidence_type"].isin(policy.evidence_types)]

    # Protein -> pathway lookup, built once. Restricted to proteins that carry
    # at least one pathway edge; a protein absent from Reactome contributes
    # nothing to Q(d) rather than contributing a placeholder.
    prot_to_path: dict[str, np.ndarray] = {}
    if policy.use_pathways:
        pp = pathway_edges[["uniprot_accession", "reactome_pathway_id"]].drop_duplicates()
        for prot, group in pp.groupby("uniprot_accession", sort=False):
            ids = [pathway_index[q] for q in group["reactome_pathway_id"] if q in pathway_index]
            if ids:
                prot_to_path[prot] = np.asarray(sorted(set(ids)), dtype=np.int64)

    by_drug = {d: g for d, g in active.groupby("drugbank_id", sort=False)}

    protein_items: list[np.ndarray] = []
    pathway_items: list[np.ndarray] = []
    for drug in drug_ids:
        group = by_drug.get(drug)
        if group is None or group.empty:
            protein_items.append(np.zeros((0, 3), dtype=np.int64))
            pathway_items.append(np.zeros(0, dtype=np.int64))
            continue
        rows = np.array(
            [
                (
                    protein_index[p],
                    _RELATION_INDEX[r],
                    _EVIDENCE_INDEX[e],
                )
                for p, r, e in zip(
                    group["uniprot_id"], group["relation_type"], group["evidence_type"]
                )
                if p in protein_index and r in _RELATION_INDEX
            ],
            dtype=np.int64,
        ).reshape(-1, 3)
        # Sort so the element order is a function of the content only. MEAN
        # aggregation is permutation-invariant, so this changes no number - but
        # it makes leave-one-protein-out attributions and test assertions stable.
        rows = rows[np.lexsort((rows[:, 2], rows[:, 1], rows[:, 0]))]
        protein_items.append(rows)

        if policy.use_pathways:
            paths: set[int] = set()
            for p in group["uniprot_id"].unique():
                hit = prot_to_path.get(p)
                if hit is not None:
                    paths.update(hit.tolist())
            pathway_items.append(np.asarray(sorted(paths), dtype=np.int64))
        else:
            pathway_items.append(np.zeros(0, dtype=np.int64))

    counts = _count_matrix(
        drug_ids,
        active=active,
        pathway_items=pathway_items,
        adverse_path=root / "drug_adverse_event_edges.parquet",
    )

    return BiologyBundle(
        drug_ids=list(drug_ids),
        protein_vocab=protein_vocab,
        pathway_vocab=pathway_vocab,
        protein_items=protein_items,
        pathway_items=pathway_items,
        counts=counts,
        policy=policy,
        source="shuffled" if drug_protein_path else "true",
        provenance={
            "root": str(root),
            "drug_protein_path": str(dp_path),
            "n_edge_rows": int(len(edges)),
            "n_distinct_triples": int(len(triples)),
            "n_active_triples": int(len(active)),
        },
    )


def _count_matrix(
    drug_ids: list[str],
    *,
    active: pd.DataFrame,
    pathway_items: list[np.ndarray],
    adverse_path: Path,
) -> np.ndarray:
    """The eight CONTROL A scalars, derived from the same filtered edges.

    Derived, not read from ``drugs.parquet``: see the module docstring. The
    pathway count comes from the already-materialised ``pathway_items`` so that
    the number CONTROL A sees is exactly the size of the set BIO-GINE sees, for
    both true and shuffled biology.
    """
    n = len(drug_ids)
    row_of = {d: i for i, d in enumerate(drug_ids)}
    counts = np.zeros((n, len(COUNT_FEATURES)), dtype=np.float64)
    col = {name: i for i, name in enumerate(COUNT_FEATURES)}

    pairs = active[["drugbank_id", "uniprot_id", "relation_type", "evidence_type"]]

    for rel in RELATION_TYPES:
        sub = pairs[pairs["relation_type"] == rel]
        for drug, k in sub.groupby("drugbank_id")["uniprot_id"].nunique().items():
            if drug in row_of:
                counts[row_of[drug], col[f"n_{rel}s"]] = k

    for drug, k in pairs.groupby("drugbank_id")["uniprot_id"].nunique().items():
        if drug in row_of:
            counts[row_of[drug], col["n_proteins"]] = k

    chembl = pairs[pairs["evidence_type"].isin({"CURATED_MOA", "EXPERIMENTAL_BIOACTIVITY"})]
    for drug, k in chembl.groupby("drugbank_id")["uniprot_id"].nunique().items():
        if drug in row_of:
            counts[row_of[drug], col["n_chembl_proteins"]] = k

    for i, items in enumerate(pathway_items):
        counts[i, col["n_pathways"]] = len(items)

    if adverse_path.exists():
        ae = pd.read_parquet(adverse_path)[["drugbank_id", "adverse_event_id"]]
        for drug, k in ae.groupby("drugbank_id")["adverse_event_id"].nunique().items():
            if drug in row_of:
                counts[row_of[drug], col["n_adverse_events"]] = k

    return counts


def count_discrepancy_report(
    bundle: BiologyBundle, root: Path | str = MECHANISM_V1
) -> pd.DataFrame:
    """Compare derived counts against the frozen ``drugs.parquet`` columns.

    Not a validation gate - the two are expected to differ, because the frozen
    columns are DrugBank-only while the derived ones follow the evidence policy.
    It exists so the difference is a recorded number in the report rather than a
    surprise a judge finds first.

    ``n_chembl_proteins`` has no counterpart in ``drugs.parquet`` and is skipped.
    """
    frozen = pd.read_parquet(Path(root) / "drugs.parquet").set_index("drugbank_id")
    derived = bundle.count_frame()
    rows = []
    for name in COUNT_FEATURES:
        if name not in frozen.columns:
            continue
        exp = frozen[name].reindex(derived.index).fillna(0).to_numpy(dtype=float)
        got = derived[name].to_numpy(dtype=float)
        rows.append(
            {
                "feature": name,
                "frozen_sum": float(exp.sum()),
                "derived_sum": float(got.sum()),
                "exact_match_fraction": float((exp == got).mean()),
            }
        )
    return pd.DataFrame(rows)
