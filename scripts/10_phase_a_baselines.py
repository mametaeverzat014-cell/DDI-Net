#!/usr/bin/env python3
"""
Phase A: classical baselines across split schemes, negative schemes and pair
encodings.

    python scripts/10_phase_a_baselines.py                    # full grid
    python scripts/10_phase_a_baselines.py --seeds 0 1 2      # shorter
    python scripts/10_phase_a_baselines.py --quick            # smoke test

Grid: 3 split schemes x 2 negative-sampling schemes x 2 pair encodings x
{logreg, random_forest}, plus degree-only (which uses no encoding), over N
seeds. Metrics: AUC-ROC, AUPRC (primary), F1, Brier.

PROTOCOL
--------
1. Hyperparameters are selected on VALIDATION only, at the first seed, once per
   (scheme, negatives, encoding, model). The test buckets are not read at all
   during this stage.
2. The selected hyperparameters are then held fixed across every seed, and test
   is scored once per configuration.

That ordering is the whole point of the "do not tune on test" rule, so it is
enforced by the structure of the script rather than by discipline: the tuning
function is only ever handed validation batches.

WHAT TO LOOK AT FIRST
---------------------
`degree_only`. It uses two numbers per pair - the training degree of each drug -
and no chemistry at all. Whatever it scores is the floor a fingerprint model
must clear before its chemistry can be said to be contributing anything. If it
lands close to random forest, that is the finding, and it needs thinking about
before any GNN is written.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning

from ddinet.data import leakage, negatives as neg, split as split_mod, tdc_drugbank as tdc
from ddinet.eval.metrics import best_threshold, compute_binary_metrics, format_ci
from ddinet.features.pair_encoding import build_fingerprint_matrix, encode_dataset
from ddinet.models.classical import (
    HYPERPARAMETER_GRIDS, PairBatch, build_model, training_degree,
)

REPORTS = Path(__file__).resolve().parents[1] / "reports"

SCHEMES = ("random_pair", "drug", "scaffold")
NEGATIVE_STRATEGIES = ("uniform", "degree_matched")
ENCODINGS = ("concat", "symmetric")
FEATURE_MODELS = ("logreg", "random_forest")
METRICS = ("auc_roc", "auprc", "f1", "brier", "prevalence")


def pooled(dataset: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """All buckets whose name starts with ``prefix``.

    Bucket naming differs between schemes (``test`` vs ``test_S2``/``test_S3``),
    so matching by prefix keeps the runner scheme-agnostic. Matching by exact
    name would silently evaluate on an empty frame for two of the three schemes.
    """
    return dataset.loc[dataset["bucket"].str.startswith(prefix)].reset_index(drop=True)


def choose_threshold(model, val: PairBatch) -> float:
    """Decision threshold that maximises F1 on VALIDATION.

    A fixed 0.5 is not usable here. A model can rank well while placing every
    probability on one side of 0.5 - the degree-only baseline does exactly that,
    scoring AUPRC 0.71 and F1 0.00 at threshold 0.5. Reporting that F1 would say
    the model is useless when in fact only its threshold is wrong.

    Selecting on validation and applying unchanged to test keeps the rule that
    nothing is fitted on test, threshold included.
    """
    return best_threshold(val.y, model.predict_proba(val), metric="f1")


def evaluate(model, batch: PairBatch, threshold: float) -> dict:
    scores = model.predict_proba(batch)
    m = compute_binary_metrics(batch.y, scores, threshold=threshold)
    return ({k: getattr(m, k) for k in METRICS}
            | {"n": m.n, "n_positive": m.n_positive, "threshold": threshold})


def tune(model_name: str, train: PairBatch, val: PairBatch, seed: int) -> tuple[dict, list]:
    """Pick hyperparameters by validation AUPRC. Never sees test."""
    trace = []
    best_params, best_score = None, -np.inf
    for params in HYPERPARAMETER_GRIDS[model_name]:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ConvergenceWarning)
            model = build_model(model_name, params, seed=seed).fit(train)
        score = compute_binary_metrics(val.y, model.predict_proba(val)).auprc
        trace.append({"params": params, "val_auprc": float(score)})
        if np.isfinite(score) and score > best_score:
            best_params, best_score = params, score
    return best_params or HYPERPARAMETER_GRIDS[model_name][0], trace


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2, 3, 4])
    ap.add_argument("--neg-ratio", type=float, default=1.0)
    ap.add_argument("--quick", action="store_true",
                    help="one seed, one encoding - smoke test only")
    ap.add_argument("--out-prefix", default="phase_a")
    ap.add_argument("--fresh", action="store_true",
                    help="ignore any partial results and start over")
    args = ap.parse_args()

    seeds = [0] if args.quick else args.seeds
    encodings = ("symmetric",) if args.quick else ENCODINGS
    schemes = SCHEMES

    pd.set_option("display.width", 240)
    REPORTS.mkdir(parents=True, exist_ok=True)
    t_start = time.time()

    # ---- Data ---------------------------------------------------------
    drugs, pairs, drop_report = tdc.load_modelling_data()
    print(drop_report.summary())
    drug_names = list(drugs["name"])
    positive_keys = set(pairs["pair_key"])
    print(f"\n{len(drugs):,} drugs, {len(pairs):,} positive pairs")

    print("Building ECFP4 fingerprints ...")
    fingerprints = build_fingerprint_matrix(drug_names, list(drugs["smiles"]))
    print(f"  {fingerprints.matrix.shape}, "
          f"{fingerprints.matrix.nnz / fingerprints.matrix.shape[0]:.1f} bits/drug\n")

    # Results are appended after every configuration rather than written once
    # at the end. A grid this size runs for hours; losing all of it to an
    # interruption at hour four is an avoidable engineering failure, and being
    # able to resume means a crash costs one configuration, not the whole run.
    results_path = REPORTS / f"{args.out_prefix}_results.csv"
    tuning_path = REPORTS / f"{args.out_prefix}_tuning.json"

    rows: list[dict] = []
    tuning_log: list[dict] = []
    chosen: dict[tuple, dict] = {}
    completed: set[tuple] = set()

    if results_path.exists() and not args.fresh:
        previous = pd.read_csv(results_path)
        rows = previous.to_dict("records")
        completed = set(
            map(tuple, previous[["scheme", "seed", "negatives"]].drop_duplicates().values)
        )
        if tuning_path.exists():
            tuning_log = json.loads(tuning_path.read_text())
            for entry in tuning_log:
                chosen[(entry["scheme"], entry["negatives"], entry["encoding"],
                        entry["model"])] = entry["chosen"]
        print(f"Resuming: {len(completed)} configurations already done "
              f"({len(rows)} rows). Pass --fresh to start over.\n")

    def checkpoint() -> None:
        pd.DataFrame(rows).to_csv(results_path, index=False)
        tuning_path.write_text(json.dumps(tuning_log, indent=2, default=str))

    total = len(schemes) * len(seeds) * len(NEGATIVE_STRATEGIES)
    done = 0

    for scheme, seed in product(schemes, seeds):
        if all((scheme, seed, st) in completed for st in NEGATIVE_STRATEGIES):
            done += len(NEGATIVE_STRATEGIES)
            print(f"[{done}/{total}] scheme={scheme} seed={seed} - already done")
            continue
        split = split_mod.build_any(scheme, drugs, pairs, seed=seed)
        # Strict schemes abort here if they leak; the leaky one reports.
        leak = leakage.verify(split)
        train_positives = pooled(
            pd.concat([df.assign(bucket=name) for name, df in split.buckets.items()],
                      ignore_index=True),
            "train",
        )
        degree = training_degree(train_positives)

        for strategy in NEGATIVE_STRATEGIES:
            done += 1
            if (scheme, seed, strategy) in completed:
                print(f"[{done}/{total}] scheme={scheme} seed={seed} "
                      f"negatives={strategy} - already done, skipping")
                continue
            print(f"[{done}/{total}] scheme={scheme} seed={seed} negatives={strategy}")
            dataset, sampling = neg.build_dataset(
                split, drug_names, positive_keys,
                neg.NegativeSamplingConfig(strategy=strategy, ratio=args.neg_ratio,
                                           seed=seed),
            )
            neg.verify_no_negative_is_positive(dataset, positive_keys)

            train_df = pooled(dataset, "train")
            val_df = pooled(dataset, "val")
            test_df = pooled(dataset, "test")

            base = {
                "scheme": scheme, "seed": seed, "negatives": strategy,
                "test_S1_fraction": leak.test_s1_fraction,
                "n_train": len(train_df), "n_test": len(test_df),
            }

            # ---- degree-only: no encoding, no tuning grid ---------------
            model = build_model("degree_only", {}, degree=degree, seed=seed)
            model.fit(PairBatch.from_frame(train_df))
            thr = choose_threshold(model, PairBatch.from_frame(val_df))
            for setting_name, frame in _test_views(test_df):
                rows.append({**base, "model": "degree_only", "encoding": "none",
                             "test_view": setting_name,
                             **evaluate(model, PairBatch.from_frame(frame), thr)})

            # ---- feature-based models ----------------------------------
            for encoding in encodings:
                enc_kwargs = dict(encoding=encoding, seed=seed)
                Xtr = encode_dataset(fingerprints, train_df, **enc_kwargs)
                Xva = encode_dataset(fingerprints, val_df, **enc_kwargs)
                Xte = encode_dataset(fingerprints, test_df, **enc_kwargs)
                train_b = PairBatch.from_frame(train_df, Xtr)
                val_b = PairBatch.from_frame(val_df, Xva)

                for model_name in FEATURE_MODELS:
                    key = (scheme, strategy, encoding, model_name)
                    if key not in chosen:
                        t0 = time.time()
                        params, trace = tune(model_name, train_b, val_b, seed)
                        chosen[key] = params
                        tuning_log.append({
                            "scheme": scheme, "negatives": strategy,
                            "encoding": encoding, "model": model_name,
                            "tuned_at_seed": seed, "chosen": params, "trace": trace,
                            "seconds": round(time.time() - t0, 1),
                        })
                        print(f"      tuned {model_name:14s} {encoding:9s} -> "
                              f"{params}  ({time.time() - t0:.0f}s)")

                    t0 = time.time()
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", ConvergenceWarning)
                        model = build_model(model_name, chosen[key], seed=seed).fit(train_b)
                    thr = choose_threshold(model, val_b)
                    for setting_name, frame in _test_views(test_df):
                        idx = frame.index.to_numpy()
                        batch = PairBatch.from_frame(frame, Xte[idx])
                        rows.append({**base, "model": model_name,
                                     "encoding": encoding, "test_view": setting_name,
                                     **evaluate(model, batch, thr)})
                    print(f"      fit   {model_name:14s} {encoding:9s} "
                          f"({time.time() - t0:.0f}s)")

            checkpoint()

    results = pd.DataFrame(rows)
    checkpoint()

    _write_summary(results, args, seeds, encodings, REPORTS / f"{args.out_prefix}_summary.md")
    print(f"\nTotal wall time: {(time.time() - t_start) / 60:.1f} min")
    print(f"Wrote {REPORTS / f'{args.out_prefix}_results.csv'}")
    print(f"      {REPORTS / f'{args.out_prefix}_summary.md'}")
    return 0


def _test_views(test_df: pd.DataFrame):
    """The pooled test set, then each S-setting present in it, keeping the
    original index so encoded rows can be gathered without re-encoding."""
    yield "pooled", test_df
    if "setting" in test_df.columns:
        for setting in sorted(test_df["setting"].unique()):
            sub = test_df.loc[test_df["setting"] == setting]
            if len(sub) and sub["label"].nunique() > 1:
                yield setting, sub


def _write_summary(results: pd.DataFrame, args, seeds, encodings, path: Path) -> None:
    lines: list[str] = []
    w = lines.append
    w("# Phase A - classical baselines\n")
    w(f"Generated by `scripts/10_phase_a_baselines.py`. Seeds: {list(seeds)}. "
      f"Negative ratio 1:{args.neg_ratio:g}. Encodings: {list(encodings)}.\n")
    w("Hyperparameters were selected on validation at the first seed and then "
      "held fixed; test was scored once per configuration.\n")
    w("All figures are **mean +/- 95% CI (Student-t) over seeds**. The interval "
      "covers seed-to-seed variability - split assignment, negative sample and "
      "fit stochasticity - not uncertainty from the finite test set.\n")

    pooled_rows = results[results["test_view"] == "pooled"]

    w("## Main table: AUPRC on the pooled test set\n")
    w("AUPRC is the primary metric. Its random-classifier baseline equals the "
      "positive prevalence, shown in the last column, so a value is only "
      "interpretable next to it.\n")
    for strategy, grp in pooled_rows.groupby("negatives"):
        w(f"### Negatives: `{strategy}`\n")
        w("| Model | Encoding | " + " | ".join(f"`{s}`" for s in SCHEMES) + " | Prevalence |")
        w("|---|---|" + "---|" * (len(SCHEMES) + 1))
        for model_name in ("degree_only", "logreg", "random_forest"):
            sub = grp[grp["model"] == model_name]
            for encoding in sorted(sub["encoding"].unique()):
                cells = []
                for scheme in SCHEMES:
                    vals = sub[(sub["encoding"] == encoding) &
                               (sub["scheme"] == scheme)]["auprc"]
                    cells.append(format_ci(vals) if len(vals) else "n/a")
                prev = sub["prevalence"].mean()
                w(f"| {model_name} | {encoding} | " + " | ".join(cells) +
                  f" | {prev:.3f} |")
        w("")

    w("## Degradation when the split is tightened\n")
    w("Change in pooled-test AUPRC relative to the `random_pair` split, which is "
      "the leaky scheme most of the literature uses.\n")
    w("| Model | Encoding | Negatives | random_pair | drug | scaffold | drop drug | drop scaffold |")
    w("|---|---|---|---|---|---|---|---|")
    for (model_name, encoding, strategy), grp in pooled_rows.groupby(
            ["model", "encoding", "negatives"]):
        means = {s: grp[grp["scheme"] == s]["auprc"].mean() for s in SCHEMES}
        if not np.isfinite(means.get("random_pair", np.nan)):
            continue
        ref = means["random_pair"]
        d_drug = means["drug"] - ref
        d_scaf = means["scaffold"] - ref
        w(f"| {model_name} | {encoding} | {strategy} | {ref:.3f} | "
          f"{means['drug']:.3f} | {means['scaffold']:.3f} | "
          f"{d_drug:+.3f} | {d_scaf:+.3f} |")
    w("")

    w("## Effect of the negative-sampling scheme\n")
    w("Difference in pooled-test AUPRC, `uniform` minus `degree_matched`. A "
      "positive value means uniform negatives flatter the model - an estimate of "
      "how much apparent skill was degree memorisation rather than chemistry.\n")
    w("| Model | Encoding | Scheme | uniform | degree_matched | difference |")
    w("|---|---|---|---|---|---|")
    for (model_name, encoding, scheme), grp in pooled_rows.groupby(
            ["model", "encoding", "scheme"]):
        u = grp[grp["negatives"] == "uniform"]["auprc"].mean()
        d = grp[grp["negatives"] == "degree_matched"]["auprc"].mean()
        if np.isfinite(u) and np.isfinite(d):
            w(f"| {model_name} | {encoding} | {scheme} | {u:.3f} | {d:.3f} | {u - d:+.3f} |")
    w("")

    w("## Breakdown by setting\n")
    w("S1 = both drugs seen in training, S2 = one unseen, S3 = both unseen.\n")
    for view in ("S1", "S2", "S3"):
        sub = results[results["test_view"] == view]
        if not len(sub):
            continue
        w(f"### {view}\n")
        w("| Model | Encoding | Negatives | Scheme | AUPRC | AUC-ROC | n |")
        w("|---|---|---|---|---|---|---|")
        for (m_, e_, n_, s_), grp in sub.groupby(
                ["model", "encoding", "negatives", "scheme"]):
            w(f"| {m_} | {e_} | {n_} | {s_} | {format_ci(grp['auprc'])} | "
              f"{format_ci(grp['auc_roc'])} | {int(grp['n'].mean()):,} |")
        w("")

    w("## All metrics, pooled test\n")
    w("| Model | Encoding | Negatives | Scheme | AUPRC | AUC-ROC | F1 | Brier |")
    w("|---|---|---|---|---|---|---|---|")
    for (m_, e_, n_, s_), grp in pooled_rows.groupby(
            ["model", "encoding", "negatives", "scheme"]):
        w(f"| {m_} | {e_} | {n_} | {s_} | {format_ci(grp['auprc'])} | "
          f"{format_ci(grp['auc_roc'])} | {format_ci(grp['f1'])} | "
          f"{format_ci(grp['brier'])} |")
    w("")
    path.write_text("\n".join(lines))


if __name__ == "__main__":
    raise SystemExit(main())
