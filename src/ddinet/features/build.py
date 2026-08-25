"""
Assemble everything Step 3 needs into one bundle, with the leakage guards
wired in so they cannot be forgotten.

The point of this module is that there is exactly ONE correct order of
operations, and calling it wrong is both easy and invalidating:

    split drugs  ->  route pairs  ->  build graph from TRAIN pairs only
                                  ->  featurise  ->  train

``build_feature_bundle`` performs that sequence and asserts the invariants at
each stage. If you find yourself constructing a ``DDIGraph`` by hand somewhere
else, that is a smell - route it through here.

ON WHICH NODE FEATURES ARE ENABLED BY DEFAULT
----------------------------------------------
``include_cyp_features`` defaults to **False**. The CYP annotation columns are
the same information the curated fixture's labels were derived from, so
enabling them on that fixture makes the task circular (see
``ddi_graph.leakage_audit``). They are legitimate on DrugBank, where labels are
curated independently - but the default should be the safe one, and turning
them on should be a visible, deliberate act in a config file rather than a
silent default nobody notices.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import torch

from ..data.synthetic_fixture import cyp_vocabulary, transporter_vocabulary
from ..data.split import DrugLevelSplit
from .ddi_graph import DDIGraph, assert_no_evaluation_edges, build_ddi_graph
from .fingerprints import (
    DESCRIPTOR_NAMES,
    FingerprintResult,
    MorganFeaturizer,
    descriptor_vector,
    _cached_mol,
)
from .molgraph import MolGraph, build_mol_graphs


@dataclass
class FeatureConfig:
    """Every switch that changes the representation. Serialised into run logs."""

    fingerprint_radius: int = 2
    fingerprint_bits: int = 2048
    use_counts: bool = False
    use_chirality: bool = True
    include_descriptors: bool = True
    #: OFF by default - see module docstring. Circular on the curated fixture.
    include_cyp_features: bool = False
    include_pathway_edges: bool = True
    #: Standardise descriptor columns using TRAIN-ONLY statistics.
    standardise_descriptors: bool = True


@dataclass
class FeatureBundle:
    """Everything the model needs, with provenance kept for explanation."""

    drugs: pd.DataFrame
    split: DrugLevelSplit
    graph: DDIGraph
    mol_graphs: dict[str, MolGraph]
    fingerprints: dict[str, FingerprintResult]
    node_features: np.ndarray
    node_feature_names: list[str]
    config: FeatureConfig
    name_to_idx: dict[str, int] = field(default_factory=dict)

    def index_of(self, drug: str) -> int:
        return self.name_to_idx[drug]

    def report(self) -> str:
        lines = [
            "Feature bundle",
            f"  drugs                : {len(self.drugs)}",
            f"  node feature dim     : {self.node_features.shape[1]}",
            f"  molecular graphs     : {len(self.mol_graphs)} "
            f"({sum(g.n_atoms for g in self.mol_graphs.values())} atoms total)",
            f"  CYP features enabled : {self.config.include_cyp_features}",
            f"  pathway edges        : {self.config.include_pathway_edges}",
        ]
        lines.append("  " + self.graph.report().replace("\n", "\n  "))
        return "\n".join(lines)


def _cyp_indicator_matrix(drugs: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    """Binary indicators for CYP/transporter roles.

    Layout: for each enzyme, three columns (substrate, inhibitor, inducer).
    Keeping the roles separate rather than collapsing to "involved with CYP3A4"
    is essential - the entire mechanism is that an *inhibitor* raises a
    *substrate*'s exposure. Two substrates of the same enzyme merely compete,
    which is a much weaker effect.
    """
    cyps = cyp_vocabulary()
    transporters = transporter_vocabulary()
    names: list[str] = []
    columns: list[np.ndarray] = []

    for enzyme in cyps:
        for role, col in (
            ("substrate", "cyp_substrate_list"),
            ("inhibitor", "cyp_inhibitor_list"),
            ("inducer", "cyp_inducer_list"),
        ):
            names.append(f"{enzyme}_{role}")
            columns.append(
                np.array([1.0 if enzyme in vals else 0.0 for vals in drugs[col]],
                         dtype=np.float32)
            )
    for transporter in transporters:
        for role, col in (
            ("substrate", "transporter_substrate_list"),
            ("inhibitor", "transporter_inhibitor_list"),
        ):
            names.append(f"{transporter}_{role}")
            columns.append(
                np.array([1.0 if transporter in vals else 0.0 for vals in drugs[col]],
                         dtype=np.float32)
            )

    if not columns:
        return np.zeros((len(drugs), 0), dtype=np.float32), []
    return np.column_stack(columns).astype(np.float32), names


def build_feature_bundle(
    drugs: pd.DataFrame,
    split: DrugLevelSplit,
    config: FeatureConfig | None = None,
) -> FeatureBundle:
    """Build node features, molecular graphs and the leakage-safe DDI graph.

    Descriptor standardisation uses **training-drug statistics only**. Fitting
    a scaler on the whole dataset is a textbook leak: the mean and standard
    deviation carry information about the test molecules into training. The
    effect is usually small, but it is free to avoid and impossible to defend
    if a judge spots it.
    """
    cfg = config or FeatureConfig()
    names = list(drugs["name"])
    name_to_idx = {n: i for i, n in enumerate(names)}

    featurizer = MorganFeaturizer(
        radius=cfg.fingerprint_radius,
        n_bits=cfg.fingerprint_bits,
        use_counts=cfg.use_counts,
        use_chirality=cfg.use_chirality,
    )

    fingerprints: dict[str, FingerprintResult] = {}
    fp_rows: list[np.ndarray] = []
    desc_rows: list[np.ndarray] = []
    for name, smiles in zip(names, drugs["smiles"]):
        mol = _cached_mol(smiles)
        result = featurizer.featurize(mol)
        fingerprints[name] = result
        fp_rows.append(result.bits)
        desc_rows.append(descriptor_vector(mol))

    fp_matrix = np.vstack(fp_rows).astype(np.float32)
    feature_names = [f"ecfp_{i}" for i in range(fp_matrix.shape[1])]
    blocks = [fp_matrix]

    if cfg.include_descriptors:
        desc_matrix = np.vstack(desc_rows).astype(np.float32)
        if cfg.standardise_descriptors:
            train_rows = [name_to_idx[n] for n in names if n in split.train_drugs]
            if train_rows:
                mu = desc_matrix[train_rows].mean(axis=0)
                sigma = desc_matrix[train_rows].std(axis=0)
                sigma[sigma < 1e-8] = 1.0     # constant column -> leave centred
                desc_matrix = (desc_matrix - mu) / sigma
        blocks.append(desc_matrix)
        feature_names += [f"desc_{n}" for n in DESCRIPTOR_NAMES]

    if cfg.include_cyp_features:
        cyp_matrix, cyp_names = _cyp_indicator_matrix(drugs)
        if cyp_matrix.shape[1]:
            blocks.append(cyp_matrix)
            feature_names += [f"cyp_{n}" for n in cyp_names]

    node_features = np.hstack(blocks).astype(np.float32)

    graph = build_ddi_graph(
        drugs,
        split.buckets["train"],                # TRAIN ONLY - the critical guard
        node_features,
        node_feature_names=feature_names,
        include_pathway_edges=cfg.include_pathway_edges,
    )

    # Verify the invariant rather than trusting the call above.
    #
    # Matched by PREFIX, not by an explicit list of names. The list used to be
    # ("val_S2", "val_S3", "test_S2", "test_S3"), which is the drug-level
    # scheme's naming; the random-pair scheme names its buckets "val" and
    # "test", so the check silently did nothing for exactly the scheme where a
    # graph leak would inflate results most - the one this project exists to
    # measure. A verification that quietly covers two of three schemes is worse
    # than none, because it reads like coverage.
    for name, pairs in split.buckets.items():
        if name.startswith("train") or pairs is None or not len(pairs):
            continue
        assert_no_evaluation_edges(graph, pairs)

    mol_graphs = build_mol_graphs(names, list(drugs["smiles"]))

    return FeatureBundle(
        drugs=drugs,
        split=split,
        graph=graph,
        mol_graphs=mol_graphs,
        fingerprints=fingerprints,
        node_features=node_features,
        node_feature_names=feature_names,
        config=cfg,
        name_to_idx=name_to_idx,
    )
