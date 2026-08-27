#!/usr/bin/env python3
"""Is 600 steps enough for dual at its CHOSEN dropout (0.3)?

The ladder measured dual at dropout 0.1, where it peaks around step 158.
Tuning selected dropout 0.3, which regularises harder and pushed the peak to
step 300 of a 400 cap - 75% of the budget, close enough to the edge that the
cap may be binding. If dual at 0.3 is still climbing at 600, a 600-cap grid
would bias the architecture comparison the other way.

Run at cap 800 with T_max 800 so the schedule is not compressed. Validation
only.
"""
import sys, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import numpy as np, torch
from ddinet.data import negatives as neg, split as split_mod, tdc_drugbank as tdc
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
ds = ds.loc[~ds["bucket"].str.startswith("test")].reset_index(drop=True)

out = {}
for arch, do in (("dual", 0.3), ("gine", 0.1)):
    set_seed(0)
    m = DDINet(DDINetConfig(atom_dim=ATOM_FEATURE_DIM, bond_dim=BOND_FEATURE_DIM,
        node_feature_dim=bundle.node_features.shape[1], hidden_dim=64,
        mol_layers=3, graph_layers=2, dropout=do, pooling="sum",
        use_graph_branch=(arch == "dual")))
    t0 = time.time()
    tr = Trainer(m, bundle, ds, TrainConfig(epochs=800, lr=1e-3, weight_decay=1e-4,
        batch_size=None, patience=80, seed=0, selection_bucket="val", verbose=False))
    h = tr.fit()
    v = np.array(h.val_scores)
    out[f"{arch}_do{do}"] = {"val": [round(float(x),5) for x in v],
                             "best_epoch": h.best_epoch, "stopped_by": h.stopped_by}
    marks = {k: round(float(v[:k].max()),4) for k in (100,200,300,400,500,600,700,800) if k <= len(v)}
    print(f"{arch} do={do}: ran {h.epochs_run}, stopped {h.stopped_by}, "
          f"peak {h.best_score:.4f} at step {h.best_epoch} ({time.time()-t0:.0f}s)", flush=True)
    print(f"   best-so-far: {marks}", flush=True)
Path(__file__).resolve().parents[1] / "reports/cap600_adequacy_curves.json".write_text(json.dumps(out, indent=1))
print("wrote reports/cap600_adequacy_curves.json")
