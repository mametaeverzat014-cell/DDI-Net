"""
The drug-drug interaction graph: nodes are drugs, edges are relations between
them.

*** THE MOST DANGEROUS BUG IN LINK PREDICTION LIVES IN THIS FILE ***
--------------------------------------------------------------------
When you predict edges in a graph, the graph itself is an *input feature*. So if
you build the message-passing graph from **all** known interactions and then
evaluate on a held-out subset of those same interactions, the model can read the
answer directly off its own input. A 2-layer GNN does not even need to be clever
about it: the test edge is literally in the adjacency it aggregates over.

This produces near-perfect metrics and is completely invalid. It is also
extremely easy to write by accident, because "build the graph, then split the
edges" is the natural order to think in.

DDI-Net enforces the correct order:

    1. Split DRUGS  (Step 1)
    2. Route pairs into buckets by drug membership  (Step 1)
    3. Build the message-passing graph from **training-bucket edges only**
    4. Predict validation/test edges against that graph

``build_ddi_graph`` takes ``train_pairs`` as a *required, explicitly named*
argument - never the full pair table - and ``assert_no_evaluation_edges``
verifies the invariant. Call it before every training run.

Note the interaction with the drug-level split: because a test drug is not in
any training pair, a test drug has **no** ``known_ddi`` edges at all. Its
representation must come from chemistry and from pathway edges. That is exactly
the intended difficulty of the S2/S3 settings, and it is why a model that leans
entirely on graph topology collapses there.

WHY A GRAPH BEATS A TABLE FOR THIS PROBLEM
------------------------------------------
The honest version of this argument has four parts.

1. **The label is a property of a pair, not of a drug.** In a tabular setup you
   must flatten the pair into one row, which forces an arbitrary choice
   (concatenate? subtract?) and discards the relational structure. A graph
   represents the relation natively.

2. **Higher-order structure carries real pharmacology.** If ketoconazole
   inhibits CYP3A4, and simvastatin, midazolam and colchicine are CYP3A4
   substrates, then knowing ketoconazole-simvastatin interacts is evidence
   about ketoconazole-midazolam. Message passing propagates exactly this;
   independent rows cannot represent it at all. This is the single strongest
   argument and it is mechanistically grounded, not hand-waving.

3. **Sparsity.** Documented interactions cover a few percent of possible pairs.
   A graph's inductive bias - "represent a node by its neighbourhood" - is
   well matched to sparse relational data, where a flat model has to learn the
   relational structure from scratch.

4. **Symmetry comes for free.** Interaction is symmetric. Undirected edges plus
   a symmetric decoder enforce f(A,B) = f(B,A) architecturally, rather than
   hoping the model learns it from data augmentation.

The counter-argument you should also state: for S1 warm-start prediction, a
well-tuned gradient-boosted model on concatenated fingerprints is a genuinely
strong baseline and sometimes wins. The graph's advantage should show up most
in S2/S3. Step 4 tests this rather than assuming it.

PATHWAY EDGES AND THE CIRCULARITY CAVEAT
-----------------------------------------
Beyond known interactions we add *mechanistic* edges derived from CYP450 and
transporter annotations - notably ``cyp_inhibitor_substrate``, which encodes
"drug A inhibits an enzyme that drug B is metabolised by". That is the single
most common pharmacokinetic interaction mechanism in existence.

These edges are derived from drug annotations, not from interaction labels, so
in general they are legitimate features rather than leakage. **But on the
curated seed fixture the labels were themselves curated from these mechanisms**,
so there the relationship is circular. ``leakage_audit`` measures the effect
directly: it scores pairs using pathway edges alone and reports the AUC. Expect
a very high number on the fixture and a much lower - but real - number on
DrugBank. Run it, report both, and you have turned a hidden trap into a result.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import torch

#: Relation types, in a fixed order so edge-type indices are stable across runs.
EDGE_TYPES: tuple[str, ...] = (
    "known_ddi",                        # observed interaction (TRAIN ONLY)
    "cyp_inhibitor_substrate",          # A inhibits CYP_x; B is a CYP_x substrate
    "cyp_inducer_substrate",            # A induces  CYP_x; B is a CYP_x substrate
    "cyp_shared_substrate",             # both compete for CYP_x
    "transporter_inhibitor_substrate",  # e.g. P-gp inhibition (digoxin toxicity)
    "transporter_shared_substrate",
    "same_atc_class",                   # same therapeutic class (level-3 ATC)
)
EDGE_TYPE_INDEX = {name: i for i, name in enumerate(EDGE_TYPES)}

#: Pathway relations only - the ones usable when a drug has no known DDIs.
PATHWAY_EDGE_TYPES = EDGE_TYPES[1:]


@dataclass
class DDIGraph:
    """A multi-relational drug graph ready for message passing."""

    drug_names: list[str]
    name_to_idx: dict[str, int]
    edge_index: torch.Tensor          # [2, E] long
    edge_type: torch.Tensor           # [E]   long, index into EDGE_TYPES
    node_features: torch.Tensor       # [N, F] float
    node_feature_names: list[str] = field(default_factory=list)
    #: Which pairs were used to build ``known_ddi`` edges. Kept for auditing.
    training_edge_keys: set[tuple[str, str]] = field(default_factory=set)

    @property
    def n_nodes(self) -> int:
        return len(self.drug_names)

    @property
    def n_edges(self) -> int:
        return int(self.edge_index.shape[1])

    def edge_counts(self) -> dict[str, int]:
        """Edges per relation type (counting each undirected edge once)."""
        counts = {name: 0 for name in EDGE_TYPES}
        for t in self.edge_type.tolist():
            counts[EDGE_TYPES[t]] += 1
        return {k: v // 2 for k, v in counts.items()}   # stored bidirectionally

    def degree_of(self, name: str, edge_type: str | None = None) -> int:
        idx = self.name_to_idx.get(name)
        if idx is None:
            return 0
        mask = self.edge_index[0] == idx
        if edge_type is not None:
            mask &= self.edge_type == EDGE_TYPE_INDEX[edge_type]
        return int(mask.sum())

    def report(self) -> str:
        lines = [
            f"DDI graph: {self.n_nodes} drugs, {self.n_edges // 2} undirected edges",
            f"  node features: {self.node_features.shape[1]}",
            "  edges by relation:",
        ]
        for name, count in self.edge_counts().items():
            if count:
                lines.append(f"    {name:34s} {count:6d}")
        isolated = sum(
            1 for n in self.drug_names
            if self.degree_of(n) == 0
        )
        lines.append(f"  isolated nodes (no edges at all): {isolated}")
        return "\n".join(lines)


# --------------------------------------------------------------------------
# Pathway edge derivation
# --------------------------------------------------------------------------

def _annotation_index(drugs: pd.DataFrame, column: str) -> dict[str, set[str]]:
    """``{'CYP3A4': {'ketoconazole', ...}}`` from a ``|``-separated column."""
    index: dict[str, set[str]] = defaultdict(set)
    list_col = column + "_list"
    if list_col not in drugs.columns:
        return {}
    for name, values in zip(drugs["name"], drugs[list_col]):
        for value in values:
            index[value].add(name)
    return dict(index)


def derive_pathway_edges(drugs: pd.DataFrame) -> dict[str, set[tuple[str, str]]]:
    """Build mechanistic drug-drug edges from enzyme/transporter annotations.

    Returns ``{edge_type: {(drug_a, drug_b), ...}}`` with canonically ordered
    keys.

    Note that ``cyp_inhibitor_substrate`` is mechanistically *directional* -
    the inhibitor affects the substrate, not vice versa - but we store it
    undirected. Rationale: the *clinical* consequence is a property of the
    combination, and the pair-level prediction target is symmetric. Making the
    relation directed would require an asymmetric decoder for a target that is
    symmetric by definition. The direction is recorded in the explanation layer
    (Step 5) where it actually matters for the narrative.
    """
    edges: dict[str, set[tuple[str, str]]] = {t: set() for t in PATHWAY_EDGE_TYPES}

    cyp_sub = _annotation_index(drugs, "cyp_substrate")
    cyp_inh = _annotation_index(drugs, "cyp_inhibitor")
    cyp_ind = _annotation_index(drugs, "cyp_inducer")
    tr_sub = _annotation_index(drugs, "transporter_substrate")
    tr_inh = _annotation_index(drugs, "transporter_inhibitor")

    def _cross(a_set: set[str], b_set: set[str], edge_type: str) -> None:
        for a in a_set:
            for b in b_set:
                if a != b:
                    edges[edge_type].add((a, b) if a < b else (b, a))

    def _within(members: set[str], edge_type: str) -> None:
        ordered = sorted(members)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1:]:
                edges[edge_type].add((a, b))

    for enzyme, substrates in cyp_sub.items():
        _cross(cyp_inh.get(enzyme, set()), substrates, "cyp_inhibitor_substrate")
        _cross(cyp_ind.get(enzyme, set()), substrates, "cyp_inducer_substrate")
        _within(substrates, "cyp_shared_substrate")

    for transporter, substrates in tr_sub.items():
        _cross(tr_inh.get(transporter, set()), substrates,
               "transporter_inhibitor_substrate")
        _within(substrates, "transporter_shared_substrate")

    if "atc_code" in drugs.columns:
        by_class: dict[str, set[str]] = defaultdict(set)
        for name, code in zip(drugs["name"], drugs["atc_code"]):
            code = str(code or "")
            if len(code) >= 3:
                by_class[code[:3]].add(name)     # ATC level 3 = pharmacological subgroup
        for members in by_class.values():
            if 1 < len(members) <= 25:           # skip huge, uninformative classes
                _within(members, "same_atc_class")

    return edges


# --------------------------------------------------------------------------
# Graph construction
# --------------------------------------------------------------------------

def build_ddi_graph(
    drugs: pd.DataFrame,
    train_pairs: pd.DataFrame,
    node_features: np.ndarray,
    *,
    node_feature_names: list[str] | None = None,
    include_pathway_edges: bool = True,
    pathway_edge_types: tuple[str, ...] | None = None,
) -> DDIGraph:
    """Assemble the message-passing graph.

    ``train_pairs`` MUST be the training bucket only. Passing the full pair
    table silently leaks every evaluation label into the model's input. The
    argument is keyword-positional and named ``train_pairs`` precisely so that a
    reader of the call site can see whether it is correct.

    Every edge is stored in both directions, because PyG message passing is
    directional and a chemical/clinical relation between two drugs is not.
    """
    names = list(drugs["name"])
    name_to_idx = {n: i for i, n in enumerate(names)}

    src: list[int] = []
    dst: list[int] = []
    etype: list[int] = []

    def add(a: str, b: str, type_name: str) -> None:
        ia, ib = name_to_idx.get(a), name_to_idx.get(b)
        if ia is None or ib is None or ia == ib:
            return
        t = EDGE_TYPE_INDEX[type_name]
        src.extend([ia, ib])
        dst.extend([ib, ia])
        etype.extend([t, t])

    training_keys: set[tuple[str, str]] = set()
    for a, b in zip(train_pairs["drug_a"], train_pairs["drug_b"]):
        key = (a, b) if a < b else (b, a)
        if key in training_keys:
            continue
        training_keys.add(key)
        add(a, b, "known_ddi")

    if include_pathway_edges:
        allowed = pathway_edge_types or PATHWAY_EDGE_TYPES
        derived = derive_pathway_edges(drugs)
        for type_name in allowed:
            for a, b in sorted(derived.get(type_name, ())):
                add(a, b, type_name)

    edge_index = (
        torch.tensor([src, dst], dtype=torch.long)
        if src else torch.zeros((2, 0), dtype=torch.long)
    )
    edge_type = torch.tensor(etype, dtype=torch.long) if etype else torch.zeros(0, dtype=torch.long)

    return DDIGraph(
        drug_names=names,
        name_to_idx=name_to_idx,
        edge_index=edge_index,
        edge_type=edge_type,
        node_features=torch.tensor(node_features, dtype=torch.float),
        node_feature_names=node_feature_names or [],
        training_edge_keys=training_keys,
    )


def assert_no_evaluation_edges(
    graph: DDIGraph, evaluation_pairs: pd.DataFrame
) -> None:
    """Fail loudly if any evaluation pair is present as a ``known_ddi`` edge.

    Run this before every training run. It is the guard against the single most
    invalidating bug in link prediction, it costs milliseconds, and a silent
    failure here would make every number in your write-up wrong.
    """
    offenders = []
    for a, b in zip(evaluation_pairs["drug_a"], evaluation_pairs["drug_b"]):
        key = (a, b) if a < b else (b, a)
        if key in graph.training_edge_keys:
            offenders.append(key)
    if offenders:
        raise AssertionError(
            f"LEAKAGE: {len(offenders)} evaluation pairs are present as known_ddi "
            f"edges in the message-passing graph, e.g. {offenders[:5]}. "
            f"Build the graph from the TRAINING bucket only."
        )


# --------------------------------------------------------------------------
# Leakage audit
# --------------------------------------------------------------------------

def leakage_audit(
    drugs: pd.DataFrame,
    dataset: pd.DataFrame,
    *,
    edge_types: tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """How much of the label can be predicted from pathway edges alone?

    For each pathway relation, we treat "this edge exists" as a one-bit
    classifier for "this pair interacts" and report its precision, recall and
    balanced accuracy on every bucket.

    Why this matters: if ``cyp_inhibitor_substrate`` alone recovers most of the
    positives, then a GNN given that edge type is largely re-deriving a rule
    rather than learning chemistry - and you need to say so before a judge asks.
    On the curated fixture this is expected to be very high (the labels were
    curated from these mechanisms). On DrugBank it should be substantially
    lower, and whatever remains is genuine mechanistic signal.

    Report both numbers side by side. It converts a hidden circularity into an
    explicit, quantified caveat, which is a much stronger position.
    """
    derived = derive_pathway_edges(drugs)
    types = edge_types or PATHWAY_EDGE_TYPES

    rows = []
    for bucket, group in dataset.groupby("bucket", sort=True):
        y = group["label"].to_numpy()
        keys = [
            (a, b) if a < b else (b, a)
            for a, b in zip(group["drug_a"], group["drug_b"])
        ]
        for type_name in types:
            edge_set = derived.get(type_name, set())
            pred = np.array([1 if k in edge_set else 0 for k in keys])
            tp = int(((pred == 1) & (y == 1)).sum())
            fp = int(((pred == 1) & (y == 0)).sum())
            fn = int(((pred == 0) & (y == 1)).sum())
            tn = int(((pred == 0) & (y == 0)).sum())
            precision = tp / (tp + fp) if (tp + fp) else 0.0
            recall = tp / (tp + fn) if (tp + fn) else 0.0
            specificity = tn / (tn + fp) if (tn + fp) else 0.0
            rows.append(
                {
                    "bucket": bucket,
                    "edge_type": type_name,
                    "n_pairs_with_edge": int(pred.sum()),
                    "precision": round(precision, 3),
                    "recall": round(recall, 3),
                    "balanced_accuracy": round((recall + specificity) / 2, 3),
                }
            )

    # The union of all pathway edges - the strongest possible rule-only model.
    for bucket, group in dataset.groupby("bucket", sort=True):
        y = group["label"].to_numpy()
        union: set[tuple[str, str]] = set()
        for type_name in types:
            union |= derived.get(type_name, set())
        keys = [
            (a, b) if a < b else (b, a)
            for a, b in zip(group["drug_a"], group["drug_b"])
        ]
        pred = np.array([1 if k in union else 0 for k in keys])
        tp = int(((pred == 1) & (y == 1)).sum())
        fp = int(((pred == 1) & (y == 0)).sum())
        fn = int(((pred == 0) & (y == 1)).sum())
        tn = int(((pred == 0) & (y == 0)).sum())
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        specificity = tn / (tn + fp) if (tn + fp) else 0.0
        rows.append(
            {
                "bucket": bucket,
                "edge_type": "ANY_PATHWAY_EDGE",
                "n_pairs_with_edge": int(pred.sum()),
                "precision": round(tp / (tp + fp), 3) if (tp + fp) else 0.0,
                "recall": round(recall, 3),
                "balanced_accuracy": round((recall + specificity) / 2, 3),
            }
        )

    return pd.DataFrame(rows)
