#!/usr/bin/env python3
"""
Train DDI-Net and report metrics across all three settings.

    python scripts/04_train.py
    python scripts/04_train.py --architecture sage --group-by scaffold
    python scripts/04_train.py --dangerous-only --neg-ratio 5

Reports S1 (train), S2 and S3 separately. The S1 -> S2 -> S3 degradation is the
headline scientific result, not an embarrassment: it quantifies how much of an
S1 score is node memorisation rather than chemistry.

The decision threshold is selected on the VALIDATION split and then applied
unchanged to test. Tuning a threshold on test data is a real, if subtle, leak.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import torch

from ddinet.data import assemble, curated, split as split_mod
from ddinet.eval.metrics import (
    best_threshold, bootstrap_ci, compute_binary_metrics, recall_at_precision,
    severity_metrics,
)
from ddinet.features.build import FeatureConfig, build_feature_bundle
from ddinet.features.ddi_graph import leakage_audit
from ddinet.features.molgraph import ATOM_FEATURE_DIM, BOND_FEATURE_DIM
from ddinet.models.ddinet import DDINet, DDINetConfig
from ddinet.models.train import Trainer, TrainConfig

REPORTS = Path(__file__).resolve().parents[1] / "reports"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--architecture", choices=("gat", "sage", "gcn"), default="gat")
    ap.add_argument("--group-by", choices=("drug", "scaffold"), default="drug")
    ap.add_argument("--neg-ratio", type=float, default=3.0)
    ap.add_argument("--dangerous-only", action="store_true")
    ap.add_argument("--epochs", type=int, default=300)
    ap.add_argument("--patience", type=int, default=50)
    ap.add_argument("--hidden-dim", type=int, default=128)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--dropout", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--no-coattention", action="store_true")
    ap.add_argument("--no-molecular", action="store_true")
    ap.add_argument("--no-graph", action="store_true")
    ap.add_argument("--out", type=Path, default=REPORTS / "train_results.json")
    args = ap.parse_args()

    drugs, pairs = curated.load_drugs(), curated.load_pairs()
    sp = split_mod.build_split(drugs, pairs, seed=args.seed, group_by=args.group_by)
    print(sp.report())

    bundle = build_feature_bundle(drugs, sp, FeatureConfig())
    dataset = assemble.build_supervised_dataset(
        sp, set(pairs["pair_key"]),
        assemble.AssemblyConfig(neg_ratio=args.neg_ratio, seed=args.seed,
                                dangerous_only=args.dangerous_only),
    )
    print()
    print(assemble.dataset_summary(dataset))

    model_cfg = DDINetConfig(
        atom_dim=ATOM_FEATURE_DIM,
        bond_dim=BOND_FEATURE_DIM,
        node_feature_dim=bundle.node_features.shape[1],
        hidden_dim=args.hidden_dim,
        dropout=args.dropout,
        architecture=args.architecture,
        use_coattention=not args.no_coattention,
        use_molecular_branch=not args.no_molecular,
        use_graph_branch=not args.no_graph,
    )
    model = DDINet(model_cfg)
    print(f"\nModel: {model_cfg.ablation_name()} | "
          f"{model.n_parameters():,} parameters | fusion dim {model.fusion_dim}")

    trainer = Trainer(
        model, bundle, dataset,
        TrainConfig(epochs=args.epochs, patience=args.patience, lr=args.lr,
                    seed=args.seed, verbose=True),
    )
    print(f"pos_weight = {float(trainer.pos_weight):.2f}\n")
    history = trainer.fit()
    print("\n" + history.summary())

    # ---- Threshold selected on VALIDATION only ---------------------------
    y_val, s_val, _ = trainer.predict_bucket("val_S2")
    threshold = best_threshold(y_val, s_val, metric="f2") if len(y_val) else 0.5
    print(f"\nDecision threshold chosen on val_S2 (max F2): {threshold:.3f}")
    print("  F2 weights recall 4x precision: a missed dangerous interaction is")
    print("  far more costly than a false alarm.")

    results = {
        "config": {
            "architecture": args.architecture,
            "ablation": model_cfg.ablation_name(),
            "group_by": args.group_by,
            "neg_ratio": args.neg_ratio,
            "dangerous_only": args.dangerous_only,
            "seed": args.seed,
            "n_parameters": model.n_parameters(),
        },
        "history": {"best_epoch": history.best_epoch, "best_score": history.best_score,
                    "epochs_run": history.epochs_run},
        "threshold": threshold,
        "buckets": {},
    }

    print("\n" + "=" * 78)
    print("RESULTS BY SETTING")
    print("=" * 78)
    for bucket in ("train", "val_S2", "val_S3", "test_S2", "test_S3"):
        y, s, sev = trainer.predict_bucket(bucket)
        if len(y) == 0 or len(np.unique(y)) < 2:
            print(f"\n[{bucket}] not estimable (fewer than two classes present)")
            continue
        m = compute_binary_metrics(y, s, threshold=threshold)
        point, lo, hi = bootstrap_ci(y, s, metric="auprc", n_boot=500, seed=args.seed)
        rec90, _ = recall_at_precision(y, s, 0.9)
        rec75, _ = recall_at_precision(y, s, 0.75)

        setting = "S1" if bucket == "train" else bucket.split("_")[1]
        print(f"\n[{bucket}]  setting={setting}")
        print("  " + m.summary().replace("\n", "\n  "))
        print(f"  AUPRC 95% CI: [{lo:.3f}, {hi:.3f}]")
        print(f"  recall @ precision>=0.90: {rec90:.3f} | >=0.75: {rec75:.3f}")

        entry = m.to_dict()
        entry.update({"auprc_ci_low": lo, "auprc_ci_high": hi,
                      "recall_at_p90": rec90, "recall_at_p75": rec75})

        if sev is not None:
            pos = y == 1
            frame = trainer.buckets[bucket]["frame"]
            ranks = frame["severity_rank"].to_numpy()[pos]
            valid = ranks >= 0
            if valid.any():
                sm = severity_metrics(ranks[valid], sev[pos][valid])
                print(f"  severity head (positives only): macro-F1 {sm['macro_f1']:.3f}, "
                      f"mean |rank error| {sm['mae_rank']:.3f}, n={sm['n']}")
                entry["severity"] = sm
        results["buckets"][bucket] = entry

    # ---- The comparison that matters -------------------------------------
    audit = leakage_audit(drugs, dataset)
    row = audit[(audit.edge_type == "ANY_PATHWAY_EDGE") & (audit.bucket == "test_S2")]
    if len(row) and "test_S2" in results["buckets"]:
        rules_ba = float(row.iloc[0]["balanced_accuracy"])
        model_ba = results["buckets"]["test_S2"]["balanced_accuracy"]
        results["rules_baseline_balanced_accuracy_test_S2"] = rules_ba
        print("\n" + "=" * 78)
        print("THE COMPARISON THAT MATTERS (test_S2, balanced accuracy)")
        print("=" * 78)
        print(f"  mechanistic rules only : {rules_ba:.3f}")
        print(f"  DDI-Net                : {model_ba:.3f}")
        verdict = ("BEATS the rules baseline" if model_ba > rules_ba
                   else "DOES NOT beat the rules baseline")
        print(f"  -> the model {verdict}.")
        if model_ba <= rules_ba:
            print("     Report this honestly. On a 104-drug fixture the graph has very")
            print("     little to learn from; the meaningful comparison is on DrugBank.")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2, default=float))
    print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
