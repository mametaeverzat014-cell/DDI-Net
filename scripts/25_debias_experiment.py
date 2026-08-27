#!/usr/bin/env python3
"""
Adversarial degree-debiasing: the experiment pre-registered in
docs/DEBIAS_PROTOCOL.md.

WHAT THIS RUNS
--------------
Three conditions x two cells x five seeds = 30 runs.

    base   adversarial_degree=False    the current model, no adversary head
    adv0   adversarial_degree=True,    head built and trained, lambda = 0
           adv_lambda_max=0.0          -> the CONTROL
    adv1   adversarial_degree=True,    head built, reversal at full strength
           adv_lambda_max=1.0

`adv0` is not optional. Without it, base-vs-adv1 confounds "degree was
suppressed" with "the model gained parameters and an extra loss term". With it,
adv0-vs-adv1 isolates the reversal alone, since the two differ in exactly one
float.

WHY THE BASE ARCHITECTURE IS `dual` AND NOT `gine`
---------------------------------------------------
The adversary acts on the NETWORK branch's embedding, because that is where the
degree shortcut was measured (R^2 0.885-0.954, scripts/23). `gine` has no
network branch, so there would be nothing to debias. All three conditions
therefore use the dual-branch model, and the comparison is within one
architecture.

THE THREE NUMBERS THAT MUST BE REPORTED TOGETHER
--------------------------------------------------
An encoder can defeat a degree head cheaply by collapsing towards a constant.
Degree becomes unpredictable, but so does everything else. So every row carries:

  r2_probe        cross-validated R^2 of an INDEPENDENT linear probe. Not the
                  adversary's own MSE - that head is being sabotaged on purpose,
                  so its loss measures nothing.
  auprc           per test view (pooled, S1, S2, S3), never pooled alone.
  embedding_var   mean per-dimension variance. A number heading for zero is
                  collapse, and a collapsed run's AUPRC must NOT be reported as
                  "after debiasing".

Pre-registered thresholds (DEBIAS_PROTOCOL.md section 4):
    collapse      embedding_var < 10% of the same seed's `base`
    R^2 fell      r2_probe < 0.3, against 0.885-0.954 originally

RESOURCE GUARD
--------------
Refuses to start while the Phase A-2 grid is still running. Two full-batch
trainings on four cores distort each other's wall time and slow both; the
protocol requires this experiment to start only after the grid completes.
Override with --force only if you know the grid is finished.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ddinet.data import negatives as neg, split as split_mod, tdc_drugbank as tdc  # noqa: E402
from ddinet.eval.metrics import best_threshold, compute_binary_metrics  # noqa: E402
from ddinet.features.build import FeatureConfig, build_feature_bundle  # noqa: E402
from ddinet.features.molgraph import ATOM_FEATURE_DIM, BOND_FEATURE_DIM  # noqa: E402
from ddinet.models.ddinet import DDINet, DDINetConfig  # noqa: E402
from ddinet.models.train import TrainConfig, Trainer, set_seed  # noqa: E402


def _load_script(name: str):
    """Import a numbered script by path.

    The grid and the probe are not importable by name (a module cannot start
    with a digit), but duplicating their helpers would let the two drift apart -
    and `training_degrees` in particular must stay bit-identical to the grid's,
    or the two experiments would be measuring different degrees.
    """
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GRID = _load_script("15_phase_a2_gnn")
PROBE = _load_script("23_degree_shortcut_probe")

REPORTS = ROOT / "reports"
RESULTS = REPORTS / "debias_results.csv"

#: (split scheme, negative strategy). The leaky cell where degree is maximally
#: informative, and the strictest honest cell.
CELLS = (("random_pair", "uniform"), ("scaffold", "degree_matched"))

#: name -> (adversarial_degree, adv_lambda_max)
CONDITIONS = {
    "base": (False, 0.0),
    "adv0": (True, 0.0),
    "adv1": (True, 1.0),
}

SEEDS = (0, 1, 2, 3, 4)


def grid_is_running() -> str | None:
    """Return the offending command line if the Phase A-2 grid is still alive."""
    try:
        out = subprocess.run(
            ["ps", "-eo", "args"], capture_output=True, text=True, timeout=20
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for line in out.splitlines():
        if "15_phase_a2_gnn.py" in line and "--stage" in line:
            return line.strip()
    return None


def build_model(bundle, condition: str, dropout: float) -> DDINet:
    """Dual-branch model, differing between conditions in two fields only."""
    adversarial, lambda_max = CONDITIONS[condition]
    return DDINet(DDINetConfig(
        atom_dim=ATOM_FEATURE_DIM,
        bond_dim=BOND_FEATURE_DIM,
        node_feature_dim=bundle.node_features.shape[1],
        n_relations=(int(bundle.graph.edge_type.max().item()) + 1
                     if len(bundle.graph.edge_type) else 1),
        hidden_dim=GRID.FIXED["hidden_dim"],
        mol_layers=GRID.FIXED["mol_layers"],
        graph_layers=GRID.FIXED["graph_layers"],
        heads=GRID.FIXED["heads"],
        dropout=dropout,
        architecture=GRID.FIXED["architecture_graph"],
        pooling=GRID.FIXED["pooling"],
        use_molecular_branch=True,
        use_graph_branch=True,          # required: the adversary acts on it
        adversarial_degree=adversarial,
        adv_lambda_max=lambda_max,
    ))


def run_one(bundle, dataset, condition: str, seed: int, *,
            max_epochs: int, patience: int, lr: float, dropout: float) -> list[dict]:
    """Train one condition and return one row per test view."""
    # Seed BEFORE construction - see LIMITATIONS.md 6b for why this order is
    # not cosmetic.
    set_seed(seed)
    model = build_model(bundle, condition, dropout)
    degrees = GRID.training_degrees(bundle.split, list(bundle.drugs["name"]))
    model.set_node_degree(degrees)

    trainer = Trainer(model, bundle, dataset, TrainConfig(
        epochs=max_epochs, lr=lr, weight_decay=GRID.FIXED["weight_decay"],
        batch_size=None, patience=patience, seed=seed,
        selection_bucket="val", selection_metric="auprc", verbose=False,
    ))
    history = trainer.fit()

    # --- the three numbers -------------------------------------------------
    z = PROBE.network_embedding(model, bundle, trainer)
    train_mask = np.array([
        n in bundle.split.train_drugs for n in bundle.drugs["name"]
    ])
    deg = degrees.numpy()
    # Probe on TRAINING drugs: held-out drugs have degree 0 by construction, and
    # regressing onto that would measure the split rather than the encoder.
    probe = PROBE.degree_alignment(z[train_mask], deg[train_mask], "train")
    embedding_var = float(np.mean(np.var(z, axis=0)))

    y_val, s_val = trainer.predict_bucket("val")
    threshold = best_threshold(y_val, s_val, metric="f1") if len(y_val) else 0.5

    base = {
        "condition": condition,
        "seed": seed,
        "adversarial": CONDITIONS[condition][0],
        "lambda_max": CONDITIONS[condition][1],
        # The lambda actually REACHED, not the one configured: early stopping
        # can cut the ramp short (DEBIAS_PROTOCOL.md 6.3).
        "lambda_reached": (history.adv_lambda[-1] if history.adv_lambda else 0.0),
        "epochs_run": history.epochs_run,
        "best_epoch": history.best_epoch,
        "stopped_by": history.stopped_by,
        "r2_probe": probe.get("r2_embedding_to_degree_cv", float("nan")),
        "spearman_norm_degree": probe.get("spearman_norm_vs_degree", float("nan")),
        "probe_degenerate": probe.get("degenerate", False),
        "embedding_var": round(embedding_var, 6),
        "adv_var_last": (history.adv_embedding_variance[-1]
                         if history.adv_embedding_variance else float("nan")),
        "threshold": threshold,
        "val_auprc": float(compute_binary_metrics(y_val, s_val, threshold=threshold).auprc),
    }

    rows = []
    y_test, s_test = trainer.predict_bucket("test")
    for view, mask in GRID._test_views(trainer.bucket_frame("test")):
        yv, sv = (y_test, s_test) if mask is None else (y_test[mask], s_test[mask])
        if len(yv) == 0 or len(np.unique(yv)) < 2:
            continue
        m = compute_binary_metrics(yv, sv, threshold=threshold)
        rows.append({**base, "test_view": view,
                     **{k: getattr(m, k) for k in GRID.METRICS},
                     "n": m.n, "n_positive": m.n_positive})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-epochs", type=int, default=800)
    ap.add_argument("--patience", type=int, default=80)
    ap.add_argument("--lr", type=float, default=None,
                    help="override the tuned lr; by default reads the value "
                         "chosen on validation in Phase A-2 for `dual`")
    ap.add_argument("--dropout", type=float, default=None,
                    help="override the tuned dropout; see --lr")
    ap.add_argument("--seeds", type=int, nargs="+", default=list(SEEDS))
    ap.add_argument("--conditions", nargs="+", default=list(CONDITIONS))
    ap.add_argument("--neg-ratio", type=float, default=1.0)
    ap.add_argument("--force", action="store_true",
                    help="run even if the Phase A-2 grid is still alive")
    ap.add_argument("--smoke", action="store_true",
                    help="two epochs, one seed, one cell - checks the plumbing only")
    args = ap.parse_args()

    busy = grid_is_running()
    if busy and not args.force:
        print("REFUSING TO START: the Phase A-2 grid is still running.\n"
              f"  {busy}\n"
              "Two full-batch trainings on this machine distort each other's\n"
              "wall time and slow both. Wait for it, or pass --force.")
        return 2

    # Hyperparameters are NOT re-tuned here. They were selected on validation
    # in Phase A-2 for the `dual` architecture and are reused unchanged, so the
    # debiasing comparison cannot be credited to a fresh hyperparameter search
    # (hard rule 5: never tune on test, and never quietly re-tune between arms).
    lr, dropout = args.lr, args.dropout
    if lr is None or dropout is None:
        path = REPORTS / "phase_a2_hyperparameters.json"
        if not path.exists():
            print(f"{path} is missing - run the Phase A-2 tuning stage first, "
                  "or pass --lr and --dropout explicitly.")
            return 2
        tuned = json.loads(path.read_text())["dual"]
        lr = tuned["lr"] if lr is None else lr
        dropout = tuned["dropout"] if dropout is None else dropout
        print(f"Hyperparameters from Phase A-2 validation tuning (`dual`): "
              f"lr={lr}, dropout={dropout}")

    cells = CELLS[:1] if args.smoke else CELLS
    seeds = args.seeds[:1] if args.smoke else args.seeds
    max_epochs = 2 if args.smoke else args.max_epochs

    REPORTS.mkdir(exist_ok=True)
    done: set[tuple] = set()
    if RESULTS.exists() and not args.smoke:
        prev = pd.read_csv(RESULTS)
        done = set(zip(prev["scheme"], prev["negatives"],
                       prev["condition"], prev["seed"]))
        print(f"Resuming: {len(done)} (cell, condition, seed) already done.")

    drugs = tdc.load_drugs()
    drugs = drugs[drugs["valid"]].reset_index(drop=True)
    pairs = tdc.load_pairs()
    drug_names = list(drugs["drugbank_id"])
    positive_keys = set(pairs["pair_key"])

    total = len(cells) * len(seeds) * len(args.conditions)
    n = 0
    for scheme, strategy in cells:
        for seed in seeds:
            split = split_mod.build_any(scheme, drugs, pairs, seed=seed)
            bundle = build_feature_bundle(drugs, split, FeatureConfig())
            dataset, _ = neg.build_dataset(
                split, drug_names, positive_keys,
                neg.NegativeSamplingConfig(strategy=strategy,
                                           ratio=args.neg_ratio, seed=seed))
            neg.verify_no_negative_is_positive(dataset, positive_keys)

            for condition in args.conditions:
                n += 1
                if (scheme, strategy, condition, seed) in done:
                    print(f"[{n}/{total}] {scheme} {strategy} {condition} "
                          f"seed={seed} -> already done, skipped")
                    continue
                t0 = time.time()
                rows = run_one(bundle, dataset, condition, seed,
                               max_epochs=max_epochs, patience=args.patience,
                               lr=lr, dropout=dropout)
                for r in rows:
                    r.update(scheme=scheme, negatives=strategy,
                             wall_time_s=round(time.time() - t0, 1))
                pooled = next((r for r in rows if r["test_view"] == "pooled"), rows[0])
                print(f"[{n}/{total}] {scheme:11s} {strategy:14s} {condition} "
                      f"seed={seed} -> AUPRC {pooled['auprc']:.4f}  "
                      f"R2(probe) {pooled['r2_probe']:+.4f}  "
                      f"var {pooled['embedding_var']:.4f}  "
                      f"lambda {pooled['lambda_reached']:.3f}  "
                      f"({pooled['epochs_run']} ep, {pooled['stopped_by']})",
                      flush=True)
                if not args.smoke:
                    frame = pd.DataFrame(rows)
                    frame.to_csv(RESULTS, mode="a", index=False,
                                 header=not RESULTS.exists())

    if args.smoke:
        print("\nSmoke run finished. Plumbing works; no results were written.")
    else:
        print(f"\nDone. Results in {RESULTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
