#!/usr/bin/env python3
"""Does removing the scale explosion remove the underfitting? Validation only.

Nothing in the repository changes: the variants are built by wrapping the
encoder locally, so this measures the hypothesis without committing to a fix.
Baseline is the shipped architecture; the question is whether train AUPRC moves.
"""
import sys, json, time
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
hyper = json.load(open(Path(__file__).resolve().parents[1] / "reports/phase_a2_hyperparameters.json"))
drugs, pairs, _ = tdc.load_modelling_data()
names, keys = list(drugs["name"]), set(pairs["pair_key"])
sp = split_mod.build_any("drug", drugs, pairs, seed=0)
bundle = build_feature_bundle(drugs, sp, FeatureConfig())
ds, _ = neg.build_dataset(sp, names, keys,
        neg.NegativeSamplingConfig(strategy="degree_matched", ratio=1.0, seed=0))
ds = ds.loc[~ds["bucket"].str.startswith("test")].reset_index(drop=True)

def make(variant, hp):
    set_seed(0)
    m = DDINet(DDINetConfig(
        atom_dim=ATOM_FEATURE_DIM, bond_dim=BOND_FEATURE_DIM,
        node_feature_dim=bundle.node_features.shape[1], hidden_dim=64,
        mol_layers=3, graph_layers=2, dropout=hp["dropout"],
        pooling=("mean" if variant == "B_mean_pool" else "sum"),
        use_graph_branch=False))
    if variant == "A_norm_after_pool":
        # LayerNorm between pooling and the multiplicative decoder.
        enc, h = m.mol_encoder, 64
        norm = nn.LayerNorm(h)
        fwd = enc.forward
        enc.forward = lambda *a, **k: (lambda p, at: (norm(p), at))(*fwd(*a, **k))
        m.add_module("_pool_norm", norm)
    elif variant == "C_norm_fusion_input":
        m.fusion = nn.Sequential(nn.LayerNorm(m.fusion_dim), *m.fusion)
    return m

for variant in ("baseline", "A_norm_after_pool", "B_mean_pool", "C_norm_fusion_input"):
    hp = hyper["gine"]
    t0 = time.time()
    tr = Trainer(make(variant, hp), bundle, ds, TrainConfig(
        epochs=150, lr=hp["lr"], weight_decay=1e-4, batch_size=None,
        patience=150, seed=0, selection_bucket="val", verbose=False))
    h = tr.fit()
    y_tr, s_tr = tr.predict_bucket("train"); y_va, s_va = tr.predict_bucket("val")
    a_tr = compute_binary_metrics(y_tr, s_tr).auprc
    a_va = compute_binary_metrics(y_va, s_va).auprc
    print(f"{variant:22s} train AUPRC {a_tr:.4f}  val AUPRC {a_va:.4f}  "
          f"train_loss {h.train_loss[0]:.4f}->{min(h.train_loss):.4f}  "
          f"({time.time()-t0:.0f}s)", flush=True)
