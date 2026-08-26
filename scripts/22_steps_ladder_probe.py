#!/usr/bin/env python3
"""Where does validation actually peak once the model trains? Cost follows.

The grid's cost is set by where early stopping fires, not by max_steps. In the
undertrained regime patience fired spuriously early (39 of 60 runs). With an
adequate budget the model learns for longer but also starts overfitting, so val
peaks and patience fires for a real reason. This measures where.

Validation only. Saves the curve so the peak is visible, not inferred.
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
MAX_STEPS, PATIENCE = 800, 60
drugs, pairs, _ = tdc.load_modelling_data()
names, keys = list(drugs["name"]), set(pairs["pair_key"])
sp = split_mod.build_any("drug", drugs, pairs, seed=0)
bundle = build_feature_bundle(drugs, sp, FeatureConfig())
ds, _ = neg.build_dataset(sp, names, keys,
        neg.NegativeSamplingConfig(strategy="degree_matched", ratio=1.0, seed=0))
ds = ds.loc[~ds["bucket"].str.startswith("test")].reset_index(drop=True)

curves = {}
for arch in ("gine", "dual"):
    set_seed(0)
    m = DDINet(DDINetConfig(atom_dim=ATOM_FEATURE_DIM, bond_dim=BOND_FEATURE_DIM,
        node_feature_dim=bundle.node_features.shape[1], hidden_dim=64,
        mol_layers=3, graph_layers=2, dropout=0.1, pooling="sum",
        use_graph_branch=(arch == "dual")))
    enc, ln = m.mol_encoder, nn.LayerNorm(64)
    fwd = enc.forward
    enc.forward = lambda *a, _f=fwd, _n=ln, **k: (lambda p, at: (_n(p), at))(*_f(*a, **k))
    m.add_module("_pool_norm", ln)
    t0 = time.time()
    tr = Trainer(m, bundle, ds, TrainConfig(epochs=MAX_STEPS, lr=1e-3,
        weight_decay=1e-4, batch_size=None, patience=PATIENCE, seed=0,
        selection_bucket="val", verbose=False))
    h = tr.fit()
    v = np.array(h.val_scores)
    curves[arch] = {"val": [round(float(x), 5) for x in v],
                    "best_epoch": h.best_epoch, "stopped_by": h.stopped_by}
    marks = {k: round(float(v[:k].max()), 4) for k in (100, 200, 300, 400, 600, 800)
             if k <= len(v)}
    print(f"{arch:5s} ran {h.epochs_run} steps, stopped by {h.stopped_by}, "
          f"best step {h.best_epoch}, best val {h.best_score:.4f} "
          f"({time.time()-t0:.0f}s)", flush=True)
    print(f"      best-so-far by step: {marks}", flush=True)
Path(__file__).resolve().parents[1] / "reports/steps_ladder_curves.json".write_text(json.dumps(curves, indent=1))
print("wrote reports/steps_ladder_curves.json")
