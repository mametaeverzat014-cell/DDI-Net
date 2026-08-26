#!/usr/bin/env python3
"""Can this architecture memorise a small training set at all?

The standard first debugging check, run late: take a few thousand training
pairs, remove regularisation, and see whether the model can drive training
AUPRC towards 1.0. A model that cannot overfit 5k pairs has an architecture or
optimisation limit that no amount of data or epochs will fix, and its test
numbers say nothing about the task.

Validation is not consulted; this is purely about capacity to fit.
"""
import sys, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import numpy as np, torch, torch.nn as nn
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

train = ds[ds["bucket"].str.startswith("train")]
small = train.sample(n=5000, random_state=0).copy()
# The trainer needs a validation bucket to exist; give it a copy of the same
# rows. We are asking about fit, not generalisation, so this is deliberate.
val = small.copy(); val["bucket"] = "val"
sub = __import__("pandas").concat([small, val], ignore_index=True)
print(f"subset: {len(small)} train pairs, prevalence {small['label'].mean():.3f}")

for tag, hidden, layers, lr, norm_pool in (
    ("as-shipped h64",        64, 3, 1e-3, False),
    ("h64 + pool norm",       64, 3, 1e-3, True),
    ("h256 + pool norm",     256, 3, 1e-3, True),
    ("h256 + pool norm lr3e-3", 256, 3, 3e-3, True),
):
    set_seed(0)
    m = DDINet(DDINetConfig(atom_dim=ATOM_FEATURE_DIM, bond_dim=BOND_FEATURE_DIM,
                            node_feature_dim=bundle.node_features.shape[1],
                            hidden_dim=hidden, mol_layers=layers, graph_layers=2,
                            dropout=0.0, pooling="sum", use_graph_branch=False))
    if norm_pool:
        enc, ln = m.mol_encoder, nn.LayerNorm(hidden)
        fwd = enc.forward
        enc.forward = lambda *a, **k: (lambda p, at: (ln(p), at))(*fwd(*a, **k))
        m.add_module("_pool_norm", ln)
    t0 = time.time()
    tr = Trainer(m, bundle, sub, TrainConfig(epochs=300, lr=lr, weight_decay=0.0,
        batch_size=None, patience=300, seed=0, selection_bucket="val", verbose=False))
    h = tr.fit()
    y, s = tr.predict_bucket("train")
    print(f"{tag:26s} TRAIN AUPRC {compute_binary_metrics(y, s).auprc:.4f}  "
          f"loss {h.train_loss[0]:.4f}->{min(h.train_loss):.4f}  "
          f"params {m.n_parameters()/1e6:.2f}M  ({time.time()-t0:.0f}s)", flush=True)
