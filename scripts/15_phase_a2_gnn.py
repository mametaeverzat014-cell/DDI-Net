#!/usr/bin/env python3
"""
Phase A-2: graph neural networks across split schemes and negative schemes.

    python scripts/15_phase_a2_gnn.py --stage tune       # validation only
    python scripts/15_phase_a2_gnn.py --stage grid       # the 60-run grid
    python scripts/15_phase_a2_gnn.py --stage ensemble   # 10 runs, fixed split

The protocol this script executes was pre-registered in
`docs/PHASE_A2_PROTOCOL.md` **before the first run**. Read it before changing
anything here; in particular section 3 (a GNN that loses to the random forest
is a result, not a reason to edit the architecture) and section 4 (test opens
once).

THE THREE STAGES ARE SEPARATE COMMANDS ON PURPOSE
--------------------------------------------------
`tune` never constructs a test batch at all - not "constructs it and declines
to look", literally never asks the dataset for a bucket named `test`. That is
the difference between a rule you follow and a rule the code enforces. `grid`
then reads the tuned hyperparameters from disk and refuses to run if they are
missing, so there is no path where test is scored under untuned settings and
the numbers get quietly kept.

WHY TWO ARCHITECTURES
---------------------
`gine` is the molecular branch alone. `dual` adds a GNN over the interaction
graph built from training edges only. Under a drug-level split a test drug has
zero training edges by construction, so the network branch degenerates to a
second view of that drug's own features (see the protocol, section 7). The 2x3
table of architecture x split scheme therefore measures how much of the network
level's advantage is an artefact of evaluating on drugs the graph has already
seen. That measurement is the point, not a side effect.

SEEDS: THREE ROLES, USUALLY ONE NUMBER
---------------------------------------
A seed here controls three independent things: which drugs land in which
bucket, which negatives are drawn, and how weights are initialised. In `grid`
they are deliberately tied together, so the five seeds sample the full
end-to-end variance. In `ensemble` the split seed is pinned to 0 and only the
other two vary - otherwise the five models would be evaluated on five different
test sets and averaging their predictions would be meaningless rather than an
ensemble (protocol, Addendum 1).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd
import torch

from ddinet.data import leakage, negatives as neg, split as split_mod, tdc_drugbank as tdc
from ddinet.eval.metrics import best_threshold, compute_binary_metrics
from ddinet.features.build import FeatureConfig, build_feature_bundle
from ddinet.features.molgraph import ATOM_FEATURE_DIM, BOND_FEATURE_DIM
from ddinet.models.ddinet import DDINet, DDINetConfig
from ddinet.models.train import TrainConfig, Trainer

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
PREDICTIONS = REPORTS / "phase_a2_predictions"

SCHEMES = ("random_pair", "drug", "scaffold")
NEGATIVE_STRATEGIES = ("uniform", "degree_matched")
ARCHITECTURES = ("gine", "dual")
METRICS = ("auc_roc", "auprc", "f1", "brier", "prevalence")

#: Fixed without tuning - protocol section 8. Tuning these too would multiply
#: the budget past the eight-hour ceiling agreed before launch.
FIXED = dict(hidden_dim=64, mol_layers=3, graph_layers=2, heads=4,
             weight_decay=1e-4, architecture_graph="gat", pooling="sum")

#: Tuned once per architecture on `drug + degree_matched`, validation AUPRC.
TUNING_GRID = [
    {"lr": lr, "dropout": dropout}
    for lr in (3e-4, 1e-3)
    for dropout in (0.1, 0.3)
]

#: The cell hyperparameters are tuned on, and the cell the ensemble is built
#: on. Both are the honest configuration, not the flattering one.
TUNING_CELL = ("drug", "degree_matched")


def pooled(dataset: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """Every bucket whose name starts with ``prefix``.

    Schemes name buckets differently (`test` vs `test_S2`/`test_S3`), so prefix
    matching is what keeps this runner scheme-agnostic. Exact matching would
    silently evaluate on an empty frame for two of the three schemes and report
    it as a completed configuration.
    """
    return dataset.loc[dataset["bucket"].str.startswith(prefix)].reset_index(drop=True)


def build_model(bundle, architecture: str, hp: dict) -> DDINet:
    """`gine` = molecular branch only; `dual` = molecular + interaction graph.

    The switch is `use_graph_branch`, and the fusion layer's width follows it,
    so the ablated model carries no dead parameters fed with zeros. A model that
    kept the parameters and zeroed their input would be a different model with
    the same name, and the ablation comparison would be unfair.
    """
    return DDINet(DDINetConfig(
        atom_dim=ATOM_FEATURE_DIM,
        bond_dim=BOND_FEATURE_DIM,
        node_feature_dim=bundle.node_features.shape[1],
        n_relations=int(bundle.graph.edge_type.max().item()) + 1 if len(bundle.graph.edge_type) else 1,
        hidden_dim=FIXED["hidden_dim"],
        mol_layers=FIXED["mol_layers"],
        graph_layers=FIXED["graph_layers"],
        heads=FIXED["heads"],
        dropout=hp["dropout"],
        architecture=FIXED["architecture_graph"],
        pooling=FIXED["pooling"],
        use_molecular_branch=True,
        use_graph_branch=(architecture == "dual"),
    ))


def make_bundle(scheme: str, split_seed: int, drugs, pairs):
    """Split, verify, then featurise - in that order, which is the only correct one.

    `build_feature_bundle` builds the message-passing graph from the training
    bucket alone and re-asserts that no evaluation edge reached it. Note the
    bundle depends on the split only, not on the negative scheme or the
    architecture, so it is built once per (scheme, seed) and reused across the
    four runs that share it. Rebuilding it per run would cost ~40 s x 4.
    """
    split = split_mod.build_any(scheme, drugs, pairs, seed=split_seed)
    leak = leakage.verify(split)          # aborts on strict schemes, reports on random_pair
    bundle = build_feature_bundle(drugs, split, FeatureConfig())
    return split, bundle, leak


def run_one(
    bundle,
    dataset: pd.DataFrame,
    architecture: str,
    hp: dict,
    *,
    init_seed: int,
    max_epochs: int,
    patience: int,
    score_test: bool,
    save_predictions: Path | None = None,
    curve_key: str | None = None,
) -> dict:
    """Train one model and score it. `score_test=False` never touches test.

    Returns a flat record plus, when asked, the raw validation and test
    predictions - needed later for the deep ensemble, which averages member
    probabilities and so cannot be assembled from summary metrics.

    When `curve_key` is given, the per-epoch validation curve is appended to
    `reports/phase_a2_curves.json`. That curve is the only way to tell a model
    that converged from one that ran out of budget. The stop reason alone
    cannot: the LR schedule is cosine annealing with T_max = max_epochs, so the
    learning rate reaches ~0 exactly at the cap and the best epoch lands near
    the end almost by construction. Reading "stopped by epoch limit" as
    "truncated while improving" would therefore overstate the limitation, and
    reading it as "converged" would understate it. The curve settles it.
    """
    model = build_model(bundle, architecture, hp)
    trainer = Trainer(model, bundle, dataset, TrainConfig(
        epochs=max_epochs,
        lr=hp["lr"],
        weight_decay=FIXED["weight_decay"],
        batch_size=None,               # full batch - protocol section 9
        patience=patience,
        seed=init_seed,
        selection_bucket="val",
        selection_metric="auprc",
        verbose=False,
    ))
    history = trainer.fit()

    y_val, s_val = trainer.predict_bucket("val")
    # Threshold on validation, applied unchanged to test. A fixed 0.5 is not
    # usable: a model can rank well while placing every probability on one side
    # of it, and the reported F1 would then describe the threshold, not the model.
    threshold = best_threshold(y_val, s_val, metric="f1") if len(y_val) else 0.5
    val_metrics = compute_binary_metrics(y_val, s_val, threshold=threshold)

    record = {
        "architecture": architecture,
        "lr": hp["lr"],
        "dropout": hp["dropout"],
        "init_seed": init_seed,
        "epochs_run": history.epochs_run,
        "best_epoch": history.best_epoch,
        "stopped_by": history.stopped_by,
        "wall_time_s": round(history.wall_time_s, 1),
        "threshold": threshold,
        "val_auprc": float(val_metrics.auprc),
        "val_auc_roc": float(val_metrics.auc_roc),
    }
    if curve_key is not None:
        _append_curve(curve_key, history)

    if not score_test:
        return record

    test_rows = []
    y_test, s_test = trainer.predict_bucket("test")
    for view, mask in _test_views(trainer.bucket_frame("test")):
        yv, sv = (y_test, s_test) if mask is None else (y_test[mask], s_test[mask])
        if len(yv) == 0 or len(np.unique(yv)) < 2:
            continue
        m = compute_binary_metrics(yv, sv, threshold=threshold)
        test_rows.append({**record, "test_view": view,
                          **{k: getattr(m, k) for k in METRICS},
                          "n": m.n, "n_positive": m.n_positive})

    if save_predictions is not None:
        save_predictions.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(save_predictions, y_val=y_val, s_val=s_val,
                            y_test=y_test, s_test=s_test, threshold=threshold)

    record["test_rows"] = test_rows
    return record


def _append_curve(key: str, history) -> None:
    """Store one run's validation curve, keyed by run identity.

    Written as a whole file each time rather than appended to, so an
    interrupted run leaves valid JSON instead of a truncated line.
    """
    path = REPORTS / "phase_a2_curves.json"
    curves = json.loads(path.read_text()) if path.exists() else {}
    curves[key] = {
        "val_auprc_by_epoch": [round(float(v), 6) for v in history.val_scores],
        "train_loss_by_epoch": [round(float(v), 6) for v in history.train_loss],
        "best_epoch": history.best_epoch,
        "stopped_by": history.stopped_by,
    }
    path.write_text(json.dumps(curves, indent=1))


def _test_views(frame: pd.DataFrame | None):
    """The pooled test set, then each S-setting inside it.

    ``frame`` must come from ``Trainer.bucket_frame`` and not from filtering the
    dataset here: only the trainer's own frame is guaranteed row-for-row aligned
    with its prediction vector. Masking predictions with an independently
    rebuilt frame is the kind of bug that produces plausible per-setting numbers
    that are simply wrong.
    """
    yield "pooled", None
    if frame is None or "setting" not in frame.columns:
        return
    for setting in sorted(frame["setting"].dropna().unique()):
        yield setting, (frame["setting"] == setting).to_numpy()


# ---------------------------------------------------------------- stages ----
def stage_tune(args, drugs, pairs, drug_names, positive_keys) -> int:
    """Four hyperparameter combinations per architecture, validation only.

    Selected once on `drug + degree_matched` and then frozen for every split
    scheme, negative scheme and seed. Tuning inside each of the six cells would
    triple the budget and would also let each cell choose the settings that
    flatter it - which is exactly the kind of per-configuration freedom that
    inflates published numbers, and this project is about measuring that.
    """
    scheme, strategy = TUNING_CELL
    out = REPORTS / f"{args.out_prefix}_tuning.json"
    log = json.loads(out.read_text()) if out.exists() and not args.fresh else []
    done = {(e["architecture"], e["lr"], e["dropout"]) for e in log}

    print(f"Tuning on {scheme} + {strategy}, seed {args.tune_seed}, validation AUPRC only.")
    _, bundle, _ = make_bundle(scheme, args.tune_seed, drugs, pairs)
    dataset, _ = neg.build_dataset(
        bundle.split, drug_names, positive_keys,
        neg.NegativeSamplingConfig(strategy=strategy, ratio=args.neg_ratio,
                                   seed=args.tune_seed))
    neg.verify_no_negative_is_positive(dataset, positive_keys)
    # Test is not pooled, not indexed, not passed anywhere in this stage.
    dataset = dataset.loc[~dataset["bucket"].str.startswith("test")].reset_index(drop=True)

    total = len(ARCHITECTURES) * len(TUNING_GRID)
    for i, (architecture, hp) in enumerate(product(ARCHITECTURES, TUNING_GRID), 1):
        if (architecture, hp["lr"], hp["dropout"]) in done:
            print(f"[{i}/{total}] {architecture} {hp} - already done")
            continue
        t0 = time.time()
        record = run_one(bundle, dataset, architecture, hp,
                         init_seed=args.tune_seed, max_epochs=args.max_epochs,
                         patience=args.patience, score_test=False,
                         curve_key=f"tune|{architecture}|lr{hp['lr']}|do{hp['dropout']}")
        log.append({"scheme": scheme, "negatives": strategy, **record})
        out.write_text(json.dumps(log, indent=2, default=str))
        print(f"[{i}/{total}] {architecture:5s} lr={hp['lr']:<7g} drop={hp['dropout']} "
              f"-> val AUPRC {record['val_auprc']:.4f}  "
              f"({record['epochs_run']} ep, {record['stopped_by']}, {time.time()-t0:.0f}s)")

    chosen = {}
    for architecture in ARCHITECTURES:
        entries = [e for e in log if e["architecture"] == architecture]
        best = max(entries, key=lambda e: e["val_auprc"])
        chosen[architecture] = {"lr": best["lr"], "dropout": best["dropout"],
                                "val_auprc": best["val_auprc"]}
        print(f"\nchosen {architecture}: lr={best['lr']}, dropout={best['dropout']} "
              f"(val AUPRC {best['val_auprc']:.4f})")
    (REPORTS / f"{args.out_prefix}_hyperparameters.json").write_text(
        json.dumps(chosen, indent=2))
    return 0


def load_hyperparameters(args) -> dict:
    path = REPORTS / f"{args.out_prefix}_hyperparameters.json"
    if not path.exists():
        raise SystemExit(
            f"{path} is missing. Run `--stage tune` first: scoring test under "
            "untuned settings and keeping the numbers is the exact failure the "
            "protocol forbids."
        )
    return json.loads(path.read_text())


def stage_grid(args, drugs, pairs, drug_names, positive_keys) -> int:
    """2 architectures x 3 schemes x 2 negative schemes x 5 seeds. Test opens here."""
    hyper = load_hyperparameters(args)
    results_path = REPORTS / f"{args.out_prefix}_results.csv"
    rows: list[dict] = []
    completed: set[tuple] = set()

    if results_path.exists() and not args.fresh:
        previous = pd.read_csv(results_path)
        rows = previous.to_dict("records")
        completed = set(map(tuple, previous[
            ["scheme", "seed", "negatives", "architecture"]].drop_duplicates().values))
        print(f"Resuming: {len(completed)} runs done ({len(rows)} rows). "
              "Pass --fresh to start over.\n")

    total = len(args.seeds) * len(SCHEMES) * len(NEGATIVE_STRATEGIES) * len(ARCHITECTURES)
    done = 0
    t_start = time.time()

    # Seed outermost so an interrupted run leaves a COMPLETE grid at fewer
    # seeds - every scheme and both architectures, comparable - rather than all
    # five seeds of one scheme and nothing for the others. The cross-scheme
    # comparison is the headline, so that axis is filled first.
    for seed, scheme in product(args.seeds, SCHEMES):
        cell = [(scheme, seed, st, a)
                for st, a in product(NEGATIVE_STRATEGIES, ARCHITECTURES)]
        if all(c in completed for c in cell):
            done += len(cell)
            print(f"[{done}/{total}] {scheme} seed={seed} - already done")
            continue

        t0 = time.time()
        _, bundle, leak = make_bundle(scheme, seed, drugs, pairs)
        print(f"\n{scheme} seed={seed}: bundle built in {time.time()-t0:.0f}s, "
              f"test S1 fraction {leak.test_s1_fraction:.4f}")

        for strategy in NEGATIVE_STRATEGIES:
            dataset, _ = neg.build_dataset(
                bundle.split, drug_names, positive_keys,
                neg.NegativeSamplingConfig(strategy=strategy, ratio=args.neg_ratio,
                                           seed=seed))
            neg.verify_no_negative_is_positive(dataset, positive_keys)

            for architecture in ARCHITECTURES:
                done += 1
                if (scheme, seed, strategy, architecture) in completed:
                    print(f"[{done}/{total}] {scheme} seed={seed} {strategy} "
                          f"{architecture} - already done")
                    continue
                t1 = time.time()
                record = run_one(bundle, dataset, architecture,
                                 hyper[architecture], init_seed=seed,
                                 max_epochs=args.max_epochs, patience=args.patience,
                                 score_test=True,
                                 curve_key=f"grid|{scheme}|{strategy}|{architecture}|{seed}")
                base = {"scheme": scheme, "seed": seed, "negatives": strategy,
                        "test_S1_fraction": leak.test_s1_fraction,
                        "n_train": int((dataset["bucket"].str.startswith("train")).sum())}
                for row in record.pop("test_rows"):
                    rows.append({**base, **row})
                pd.DataFrame(rows).to_csv(results_path, index=False)
                pooled_row = next(r for r in rows[::-1] if r["test_view"] == "pooled")
                print(f"[{done}/{total}] {scheme:11s} seed={seed} {strategy:14s} "
                      f"{architecture:5s} -> test AUPRC {pooled_row['auprc']:.4f} "
                      f"(val {record['val_auprc']:.4f}, {record['epochs_run']} ep, "
                      f"{record['stopped_by']}, {time.time()-t1:.0f}s)")

    print(f"\nTotal wall time: {(time.time()-t_start)/60:.1f} min -> {results_path}")
    return 0


def stage_ensemble(args, drugs, pairs, drug_names, positive_keys) -> int:
    """Deep ensemble: one fixed split, five models differing in init and negatives.

    The split seed is pinned (protocol, Addendum 1). Varying it would give each
    member a different test set, and averaging predictions across different test
    sets is not an ensemble - it is a mistake that happens to produce a number.

    What this ensemble therefore covers is the variance from initialisation and
    from which negatives were drawn. It does NOT cover the variance from which
    drugs landed in test, which Phase A found to be the dominant term. That
    limitation is stated up front because the ensemble's tighter spread would
    otherwise read as a robustness it does not have.
    """
    hyper = load_hyperparameters(args)
    scheme, strategy = TUNING_CELL
    results_path = REPORTS / f"{args.out_prefix}_ensemble.csv"
    rows: list[dict] = []
    completed: set[tuple] = set()
    if results_path.exists() and not args.fresh:
        previous = pd.read_csv(results_path)
        rows = previous.to_dict("records")
        completed = set(map(tuple, previous[
            ["architecture", "member_seed"]].drop_duplicates().values))
        print(f"Resuming: {len(completed)} members done.\n")

    _, bundle, leak = make_bundle(scheme, args.ensemble_split_seed, drugs, pairs)
    print(f"Ensemble on {scheme} + {strategy}, split seed "
          f"{args.ensemble_split_seed} held fixed; members vary init and negatives.")

    total = len(ARCHITECTURES) * len(args.seeds)
    done = 0
    for architecture, member_seed in product(ARCHITECTURES, args.seeds):
        done += 1
        if (architecture, member_seed) in completed:
            print(f"[{done}/{total}] {architecture} member {member_seed} - already done")
            continue
        dataset, _ = neg.build_dataset(
            bundle.split, drug_names, positive_keys,
            neg.NegativeSamplingConfig(strategy=strategy, ratio=args.neg_ratio,
                                       seed=member_seed))
        neg.verify_no_negative_is_positive(dataset, positive_keys)
        t1 = time.time()
        record = run_one(
            bundle, dataset, architecture, hyper[architecture],
            init_seed=member_seed, max_epochs=args.max_epochs,
            patience=args.patience, score_test=True,
            save_predictions=PREDICTIONS / f"{architecture}_member{member_seed}.npz",
            curve_key=f"ensemble|{architecture}|{member_seed}",
        )
        base = {"scheme": scheme, "negatives": strategy,
                "split_seed": args.ensemble_split_seed, "member_seed": member_seed,
                "test_S1_fraction": leak.test_s1_fraction}
        for row in record.pop("test_rows"):
            rows.append({**base, **row})
        pd.DataFrame(rows).to_csv(results_path, index=False)
        pooled_row = next(r for r in rows[::-1] if r["test_view"] == "pooled")
        print(f"[{done}/{total}] {architecture:5s} member {member_seed} -> "
              f"test AUPRC {pooled_row['auprc']:.4f} ({time.time()-t1:.0f}s)")

    print(f"\nWrote {results_path} and per-member predictions to {PREDICTIONS}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", choices=("tune", "grid", "ensemble"), required=True)
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2, 3, 4])
    ap.add_argument("--tune-seed", type=int, default=0)
    ap.add_argument("--ensemble-split-seed", type=int, default=0)
    ap.add_argument("--neg-ratio", type=float, default=1.0)
    #: 150, not the 200 of protocol section 8 - see Addendum 2. The fraction of
    #: runs that stop on the limit rather than on patience is reported with the
    #: results, because a run that was still improving is a lower bound.
    ap.add_argument("--max-epochs", type=int, default=150)
    ap.add_argument("--patience", type=int, default=20)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--out-prefix", default="phase_a2")
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()

    torch.set_num_threads(args.threads)
    REPORTS.mkdir(parents=True, exist_ok=True)

    drugs, pairs, drop_report = tdc.load_modelling_data()
    print(drop_report.summary())
    drug_names = list(drugs["name"])
    positive_keys = set(pairs["pair_key"])
    print(f"{len(drugs):,} drugs, {len(pairs):,} positive pairs\n")

    stages = {"tune": stage_tune, "grid": stage_grid, "ensemble": stage_ensemble}
    return stages[args.stage](args, drugs, pairs, drug_names, positive_keys)


if __name__ == "__main__":
    raise SystemExit(main())
