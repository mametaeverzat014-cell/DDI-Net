#!/usr/bin/env python3
"""Isolate the factor separating 0.93 on 5k pairs from 0.68 on 187k.

Full-batch training runs ONE optimiser step per epoch, so "150 epochs" means
150 gradient updates. The 5k probe used 300 epochs = 300 updates. This varies
one factor at a time on the same 5k subset, cheapest first, then confirms at
full scale.
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pandas as pd, torch, torch.nn as nn
from ddinet.data import negatives as neg, split as split_mod, tdc_drugbank as tdc
from ddinet.eval.metrics import compute_binary_metrics
from ddinet.features.build import FeatureConfig, build_feature_bundle
from ddinet.features.molgraph import ATOM_FEATURE_DIM, BOND_FEATURE_DIM
from ddinet.models.ddinet import DDINet, DDINetConfig
from ddinet.models.train import TrainConfig, Trainer, set_seed

torch.set_num_threads(4)
drugs, pairs, _ = tdc.load_modelling_data()
names, keys = list(drugs["name"]), set(pairs["pair_key"])
sp = split_mod.build_any("drug", drugs, pairs, seed=0)
bundle = build_feature_bundle(drugs, sp, FeatureConfig())
ds, _ = neg.build_dataset(sp, names, keys,
        neg.NegativeSamplingConfig(strategy="degree_matched", ratio=1.0, seed=0))
full_train = ds[ds["bucket"].str.startswith("train")]

def subset(n):
    s = full_train.sample(n=n, random_state=0).copy()
    v = s.copy(); v["bucket"] = "val"
    return pd.concat([s, v], ignore_index=True)

def run(tag, data, epochs, dropout, pool_norm, batch_size=None):
    set_seed(0)
    m = DDINet(DDINetConfig(atom_dim=ATOM_FEATURE_DIM, bond_dim=BOND_FEATURE_DIM,
        node_feature_dim=bundle.node_features.shape[1], hidden_dim=64,
        mol_layers=3, graph_layers=2, dropout=dropout, pooling="sum",
        use_graph_branch=False))
    if pool_norm:
        enc, ln = m.mol_encoder, nn.LayerNorm(64)
        fwd = enc.forward
        enc.forward = lambda *a, **k: (lambda p, at: (ln(p), at))(*fwd(*a, **k))
        m.add_module("_pool_norm", ln)
    t0 = time.time()
    tr = Trainer(m, bundle, data, TrainConfig(epochs=epochs, lr=1e-3,
        weight_decay=0.0, batch_size=batch_size, patience=epochs, seed=0,
        selection_bucket="val", verbose=False))
    h = tr.fit()
    y, s = tr.predict_bucket("train")
    n_train = int(data["bucket"].str.startswith("train").sum())
    steps = epochs * max(1, -(-n_train // (batch_size or n_train)))
    print(f"{tag:44s} TRAIN AUPRC {compute_binary_metrics(y, s).auprc:.4f}  "
          f"loss->{min(h.train_loss):.4f}  steps {steps:5d}  ({time.time()-t0:.0f}s)",
          flush=True)

sub5k = subset(5000)
print("--- 5k subset, one factor at a time (all with pool norm) ---", flush=True)
run("5k  300ep dropout0.0   [reference]", sub5k, 300, 0.0, True)
run("5k  150ep dropout0.0   [halve steps]", sub5k, 150, 0.0, True)
run("5k  300ep dropout0.1   [add dropout]", sub5k, 300, 0.1, True)
run("5k  600ep dropout0.0   [double steps]", sub5k, 600, 0.0, True)
