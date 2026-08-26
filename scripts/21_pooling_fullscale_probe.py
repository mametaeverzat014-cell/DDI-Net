#!/usr/bin/env python3
"""Full scale: does the pooling scheme matter once the step budget is adequate?

Two questions in one grid, because they share runs:

  (item 1) Confirm at 187k pairs that gradient steps, not the architecture,
           were the binding constraint.
  (item 2) sum / mean / attention x with and without normalisation. If mean
           closes the gap on its own, the diagnosis recorded in Addendum 9
           ("a missing normalisation") is wrong and becomes "the pooling
           encodes molecule size".

Everything runs at 600 full-batch steps, where the 5k probe saturated, so the
comparison is not confounded by the undertraining that produced the original
result. Validation only; test is dropped before training.
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import torch, torch.nn as nn
from ddinet.data import negatives as neg, split as split_mod, tdc_drugbank as tdc
from ddinet.eval.metrics import compute_binary_metrics
from ddinet.features.build import FeatureConfig, build_feature_bundle
from ddinet.features.molgraph import ATOM_FEATURE_DIM, BOND_FEATURE_DIM
from ddinet.models.ddinet import DDINet, DDINetConfig
from ddinet.models.train import TrainConfig, Trainer, set_seed

torch.set_num_threads(4)
STEPS = 600
drugs, pairs, _ = tdc.load_modelling_data()
names, keys = list(drugs["name"]), set(pairs["pair_key"])
sp = split_mod.build_any("drug", drugs, pairs, seed=0)
bundle = build_feature_bundle(drugs, sp, FeatureConfig())
ds, _ = neg.build_dataset(sp, names, keys,
        neg.NegativeSamplingConfig(strategy="degree_matched", ratio=1.0, seed=0))
ds = ds.loc[~ds["bucket"].str.startswith("test")].reset_index(drop=True)
print(f"full scale: {int(ds['bucket'].str.startswith('train').sum())} train pairs, "
      f"{STEPS} full-batch steps", flush=True)

def run(pooling, pool_norm, steps=STEPS):
    set_seed(0)
    m = DDINet(DDINetConfig(atom_dim=ATOM_FEATURE_DIM, bond_dim=BOND_FEATURE_DIM,
        node_feature_dim=bundle.node_features.shape[1], hidden_dim=64,
        mol_layers=3, graph_layers=2, dropout=0.1, pooling=pooling,
        use_graph_branch=False))
    if pool_norm:
        enc, ln = m.mol_encoder, nn.LayerNorm(64)
        fwd = enc.forward
        enc.forward = lambda *a, **k: (lambda p, at: (ln(p), at))(*fwd(*a, **k))
        m.add_module("_pool_norm", ln)
    t0 = time.time()
    tr = Trainer(m, bundle, ds, TrainConfig(epochs=steps, lr=1e-3,
        weight_decay=1e-4, batch_size=None, patience=steps, seed=0,
        selection_bucket="val", verbose=False))
    h = tr.fit()
    ytr, str_ = tr.predict_bucket("train"); yva, sva = tr.predict_bucket("val")
    a_tr = compute_binary_metrics(ytr, str_).auprc
    a_va = compute_binary_metrics(yva, sva).auprc
    tag = f"{pooling}{'+norm' if pool_norm else '':<5s} {steps}st"
    print(f"{tag:24s} TRAIN {a_tr:.4f}  VAL {a_va:.4f}  gap {a_tr-a_va:+.4f}  "
          f"loss->{min(h.train_loss):.4f}  ({time.time()-t0:.0f}s)", flush=True)

for pooling in ("sum", "mean", "attention"):
    for pool_norm in (False, True):
        run(pooling, pool_norm)
