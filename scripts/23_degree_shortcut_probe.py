#!/usr/bin/env python3
"""
Does the network branch encode topology, or does it encode DEGREE?

    python scripts/23_degree_shortcut_probe.py

Phase A measured that a two-number degree baseline scores 0.868 AUPRC under the
published protocol. So "topological signal" in this dataset is, to first order,
degree. That makes an alternative reading of the dual architecture's fast
convergence available: it peaks around step 158 while the molecular branch needs
529, and the explanation may not be "it learned a good representation quickly"
but "it found degree quickly and then had nothing left to learn".

This measures it directly on a trained model:

  * Spearman correlation between the node embedding's norm and the drug's degree
    in the TRAINING graph;
  * R^2 of a linear regression predicting degree from the full embedding vector,
    which catches degree encoded in any direction, not just in magnitude.

Both are computed against an UNTRAINED control. Without it, a high correlation
cannot distinguish "training discovered degree" from "this architecture encodes
degree at initialisation".

On a drug-level split every validation drug has training degree zero by
construction, so the validation figure is degenerate there and is reported as
such; the meaningful validation measurement is made on the random-pair split,
where held-out drugs do have training edges.

If the correlation is high, two-level DDI architectures exploit the degree
shortcut rather than integrating topology in the sense their authors claim -
which is a result about the field, not just about this model. If it is low, the
fast-convergence explanation stands as stated and this file records that.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd
import torch
from scipy import stats
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import cross_val_score

from ddinet.data import negatives as neg, split as split_mod, tdc_drugbank as tdc
from ddinet.features.build import FeatureConfig, build_feature_bundle
from ddinet.features.molgraph import ATOM_FEATURE_DIM, BOND_FEATURE_DIM
from ddinet.models.ddinet import DDINet, DDINetConfig
from ddinet.models.train import TrainConfig, Trainer, set_seed

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"

#: Both cells matter. drug + degree_matched is where the fast convergence was
#: observed and where negatives were built to REMOVE the degree shortcut from
#: the labels - degree surviving in the representation there is the stronger
#: finding. random_pair + uniform is the published protocol, where degree-only
#: reaches 0.868 and held-out drugs still have training edges.
CASES = [("drug", "degree_matched", 400), ("random_pair", "uniform", 400)]


def training_degree(split, drug_names: list[str]) -> np.ndarray:
    """Degree of each drug among TRAINING pairs only."""
    train = pd.concat(
        [df for name, df in split.buckets.items() if name.startswith("train")],
        ignore_index=True)
    counts = pd.concat([train["drug_a"], train["drug_b"]]).value_counts()
    return np.array([float(counts.get(n, 0)) for n in drug_names])


def degree_alignment(z: np.ndarray, degree: np.ndarray, label: str) -> dict:
    """How much of `degree` is recoverable from the embedding `z`?

    Two views. The Spearman correlation against the embedding NORM asks whether
    degree shows up as sheer magnitude - the crude form of the shortcut. The
    cross-validated R^2 of a linear map from the whole vector asks whether it is
    encoded anywhere at all, which is the question that matters: a model can
    hide degree in a direction while keeping norms uniform.

    R^2 is cross-validated because the embedding is 64-dimensional and a few
    hundred drugs would let an unregularised fit memorise degree outright.
    """
    ok = np.isfinite(degree)
    z, degree = z[ok], degree[ok]
    if len(degree) < 20 or np.allclose(degree, degree[0]):
        return {"view": label, "n": int(len(degree)), "degenerate": True,
                "note": "degree is constant (or too few drugs) - correlation undefined"}
    rho = float(stats.spearmanr(np.linalg.norm(z, axis=1), degree).statistic)
    r2 = float(np.mean(cross_val_score(LinearRegression(), z, degree,
                                       cv=5, scoring="r2")))
    return {"view": label, "n": int(len(degree)), "degenerate": False,
            "spearman_norm_vs_degree": round(rho, 4),
            "r2_embedding_to_degree_cv": round(r2, 4),
            "degree_mean": round(float(degree.mean()), 1),
            "degree_max": int(degree.max())}


def network_embedding(model: DDINet, bundle, trainer: Trainer) -> np.ndarray:
    """The node vectors the fusion layer actually receives from the graph branch."""
    model.eval()
    with torch.no_grad():
        enc = model.encode(trainer.mol_batch, trainer.node_features,
                           trainer.edge_index, trainer.edge_type)
    return enc.network.cpu().numpy()


def main() -> int:
    torch.set_num_threads(4)
    hyper = json.loads((REPORTS / "phase_a2_hyperparameters.json").read_text())
    hp = hyper["dual"]
    drugs, pairs, _ = tdc.load_modelling_data()
    names, keys = list(drugs["name"]), set(pairs["pair_key"])
    results = []

    for scheme, strategy, steps in CASES:
        sp = split_mod.build_any(scheme, drugs, pairs, seed=0)
        bundle = build_feature_bundle(drugs, sp, FeatureConfig())
        dataset, _ = neg.build_dataset(sp, names, keys,
            neg.NegativeSamplingConfig(strategy=strategy, ratio=1.0, seed=0))
        dataset = dataset.loc[
            ~dataset["bucket"].str.startswith("test")].reset_index(drop=True)

        degree = training_degree(sp, names)
        train_mask = np.array([n in sp.train_drugs for n in names])
        held_mask = ~train_mask

        set_seed(0)
        model = DDINet(DDINetConfig(
            atom_dim=ATOM_FEATURE_DIM, bond_dim=BOND_FEATURE_DIM,
            node_feature_dim=bundle.node_features.shape[1], hidden_dim=64,
            mol_layers=3, graph_layers=2, dropout=hp["dropout"], pooling="sum",
            use_graph_branch=True))
        trainer = Trainer(model, bundle, dataset, TrainConfig(
            epochs=steps, lr=hp["lr"], weight_decay=1e-4, batch_size=None,
            patience=steps, seed=0, selection_bucket="val", verbose=False))

        # Control FIRST: the same measurement before a single gradient step.
        z0 = network_embedding(model, bundle, trainer)
        trainer.fit()
        z1 = network_embedding(model, bundle, trainer)

        for state, z in (("untrained", z0), ("trained", z1)):
            for who, mask in (("train drugs", train_mask), ("held-out drugs", held_mask)):
                row = degree_alignment(z[mask], degree[mask], who)
                row |= {"scheme": scheme, "negatives": strategy, "state": state}
                results.append(row)
                if row["degenerate"]:
                    print(f"{scheme:12s} {state:9s} {who:15s} n={row['n']:4d}  "
                          f"DEGENERATE: {row['note']}", flush=True)
                else:
                    print(f"{scheme:12s} {state:9s} {who:15s} n={row['n']:4d}  "
                          f"Spearman(|z|, degree) {row['spearman_norm_vs_degree']:+.4f}  "
                          f"R2(z -> degree, cv) {row['r2_embedding_to_degree_cv']:+.4f}",
                          flush=True)
        print(flush=True)

    pd.DataFrame(results).to_csv(REPORTS / "degree_shortcut_probe.csv", index=False)
    print(f"Wrote {REPORTS / 'degree_shortcut_probe.csv'}")
    print("\nHow to read: compare trained against untrained. A high R^2 that is "
          "already high\nbefore training says the architecture encodes degree; a "
          "rise from low to high says\ntraining sought it out. Either way, degree "
          "recoverable from the embedding means\nthe network branch is carrying "
          "the shortcut Phase A measured at 0.868 AUPRC.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
