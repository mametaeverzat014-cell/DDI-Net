#!/usr/bin/env python3
"""
Is the Phase A-2 GNN result a property of the task, or of our optimisation?

    python scripts/17_underfitting_diagnostic.py

Phase A-2 reported GNN AUPRC around 0.59 on the honest configuration against
0.763 for an unbounded random forest. Before that can be called a finding about
graph networks, one alternative has to be ruled out: that our model is simply
undertrained.

The decisive measurement is TRAIN AUPRC. A model that generalises poorly still
fits its training set; a model that cannot fit its own training data has an
optimisation problem, and its test number says nothing about the task. This
script trains the tuned configurations and reports train alongside validation,
per epoch.

Test is never touched here - the buckets are dropped before training, as in the
tuning stage.

Read with `reports/phase_a2_curves.json`, which already showed the training
LOSS barely moving off chance (0.693) for gine: 0.633-0.667 after 150 epochs.
This script converts that into the same metric the headline uses.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd
import torch

from ddinet.data import negatives as neg, split as split_mod, tdc_drugbank as tdc
from ddinet.eval.metrics import compute_binary_metrics
from ddinet.features.build import FeatureConfig, build_feature_bundle
from ddinet.features.molgraph import ATOM_FEATURE_DIM, BOND_FEATURE_DIM
from ddinet.models.ddinet import DDINet, DDINetConfig
from ddinet.models.train import TrainConfig, Trainer, set_seed

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"

#: The two configurations that decide the question. `random_pair + uniform` is
#: the sanity check: it is the regime that most favours memorisation, where the
#: random forest reaches 0.915. A model that cannot fit training data THERE is
#: not being held back by an honest protocol.
CASES = [("random_pair", "uniform"), ("drug", "degree_matched")]


def build(bundle, architecture: str, hp: dict, seed: int) -> DDINet:
    set_seed(seed)
    return DDINet(DDINetConfig(
        atom_dim=ATOM_FEATURE_DIM, bond_dim=BOND_FEATURE_DIM,
        node_feature_dim=bundle.node_features.shape[1],
        hidden_dim=64, mol_layers=3, graph_layers=2, heads=4,
        dropout=hp["dropout"], architecture="gat", pooling="sum",
        use_molecular_branch=True, use_graph_branch=(architecture == "dual"),
    ))


def main() -> int:
    hyper = json.loads((REPORTS / "phase_a2_hyperparameters.json").read_text())
    torch.set_num_threads(4)
    drugs, pairs, _ = tdc.load_modelling_data()
    names, keys = list(drugs["name"]), set(pairs["pair_key"])
    rows = []

    for scheme, strategy in CASES:
        sp = split_mod.build_any(scheme, drugs, pairs, seed=0)
        bundle = build_feature_bundle(drugs, sp, FeatureConfig())
        dataset, _ = neg.build_dataset(
            sp, names, keys,
            neg.NegativeSamplingConfig(strategy=strategy, ratio=1.0, seed=0))
        dataset = dataset.loc[
            ~dataset["bucket"].str.startswith("test")].reset_index(drop=True)

        for architecture in ("gine", "dual"):
            hp = hyper[architecture]
            t0 = time.time()
            model = build(bundle, architecture, hp, seed=0)
            trainer = Trainer(model, bundle, dataset, TrainConfig(
                epochs=150, lr=hp["lr"], weight_decay=1e-4, batch_size=None,
                patience=150,            # no early stop: we want the fit itself
                seed=0, selection_bucket="val", selection_metric="auprc",
                verbose=False))
            trainer.fit()

            y_tr, s_tr = trainer.predict_bucket("train")
            y_va, s_va = trainer.predict_bucket("val")
            tr = compute_binary_metrics(y_tr, s_tr)
            va = compute_binary_metrics(y_va, s_va)
            rows.append({
                "scheme": scheme, "negatives": strategy,
                "architecture": architecture,
                "train_auprc": tr.auprc, "train_auc": tr.auc_roc,
                "val_auprc": va.auprc, "val_auc": va.auc_roc,
                "gap": tr.auprc - va.auprc, "seconds": round(time.time() - t0, 1),
            })
            print(f"{scheme:12s} {strategy:15s} {architecture:5s}  "
                  f"TRAIN auprc {tr.auprc:.4f} auc {tr.auc_roc:.4f}  |  "
                  f"VAL auprc {va.auprc:.4f} auc {va.auc_roc:.4f}  "
                  f"({time.time()-t0:.0f}s)", flush=True)

    out = pd.DataFrame(rows)
    out.to_csv(REPORTS / "underfitting_diagnostic.csv", index=False)
    print(f"\nWrote {REPORTS / 'underfitting_diagnostic.csv'}")
    print("\nHow to read: a model that generalises badly still fits training "
          "data.\nTrain AUPRC near 0.5 means the optimisation failed, and the "
          "test number\nreported for that model describes our training, not the task.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
