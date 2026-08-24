#!/usr/bin/env python3
"""
Unbounded random forest on the two configurations the headline claim rests on.

    python scripts/13_full_random_forest.py

The Phase A grid capped tree depth at 30 for tractability, which makes every
reported random-forest number a LOWER bound. The headline claim - that
chemistry adds little under the published protocol - therefore leans on a
handicapped forest, and that is exactly the point an examiner should press.

This script removes the handicap where it matters:

  random_pair + uniform    the published protocol. If the unbounded forest
                           beats 0.873 here, the gap over degree-only widens
                           and the headline weakens.
  drug + degree_matched    the honest protocol. Confirms the +0.189 gap is not
                           an artefact of the depth cap either.

Only the symmetric encoding and only these two cells: the question is whether
the cap changed a conclusion, not to re-run the grid unbounded.

Results are appended to reports/phase_a_full_rf.csv and compared against the
capped run.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd

from ddinet.data import leakage, negatives as neg, split as split_mod, tdc_drugbank as tdc
from ddinet.eval.metrics import best_threshold, compute_binary_metrics
from ddinet.eval.paired_stats import paired_compare
from ddinet.features.pair_encoding import build_fingerprint_matrix, encode_dataset
from ddinet.models.classical import PairBatch, RandomForestECFP, training_degree

REPORTS = Path(__file__).resolve().parents[1] / "reports"
SEEDS = [0, 1, 2, 3, 4]
CONFIGS = [("random_pair", "uniform"), ("drug", "degree_matched")]
METRICS = ("auc_roc", "auprc", "f1", "brier", "prevalence")


def pooled(dataset: pd.DataFrame, prefix: str) -> pd.DataFrame:
    return dataset.loc[dataset["bucket"].str.startswith(prefix)].reset_index(drop=True)


def main() -> int:
    out_path = REPORTS / "phase_a_full_rf.csv"
    rows: list[dict] = []
    completed: set[tuple] = set()
    if out_path.exists():
        previous = pd.read_csv(out_path)
        rows = previous.to_dict("records")
        completed = set(map(tuple, previous[["scheme", "negatives", "seed"]]
                            .drop_duplicates().values))
        print(f"Resuming: {len(completed)} runs already done")

    drugs, pairs, drop_report = tdc.load_modelling_data()
    print(drop_report.summary())
    drug_names = list(drugs["name"])
    positive_keys = set(pairs["pair_key"])
    fingerprints = build_fingerprint_matrix(drug_names, list(drugs["smiles"]))

    total = len(CONFIGS) * len(SEEDS)
    done = 0
    for scheme, strategy in CONFIGS:
        for seed in SEEDS:
            done += 1
            if (scheme, strategy, seed) in completed:
                print(f"[{done}/{total}] {scheme}/{strategy} seed={seed} - done")
                continue
            print(f"[{done}/{total}] {scheme}/{strategy} seed={seed}", flush=True)

            split = split_mod.build_any(scheme, drugs, pairs, seed=seed)
            leakage.verify(split)
            dataset, _ = neg.build_dataset(
                split, drug_names, positive_keys,
                neg.NegativeSamplingConfig(strategy=strategy, ratio=1.0, seed=seed),
            )
            neg.verify_no_negative_is_positive(dataset, positive_keys)

            train_df, val_df, test_df = (pooled(dataset, p) for p in ("train", "val", "test"))
            enc = dict(encoding="symmetric", seed=seed)
            train_b = PairBatch.from_frame(train_df, encode_dataset(fingerprints, train_df, **enc))
            val_b = PairBatch.from_frame(val_df, encode_dataset(fingerprints, val_df, **enc))
            Xte = encode_dataset(fingerprints, test_df, **enc)

            t0 = time.time()
            # max_depth=None: the handicap this script exists to remove.
            model = RandomForestECFP(n_estimators=100, max_depth=None,
                                     min_samples_leaf=5, seed=seed).fit(train_b)
            elapsed = time.time() - t0
            threshold = best_threshold(val_b.y, model.predict_proba(val_b), metric="f1")

            batch = PairBatch.from_frame(test_df, Xte)
            m = compute_binary_metrics(batch.y, model.predict_proba(batch),
                                       threshold=threshold)
            rows.append({
                "scheme": scheme, "negatives": strategy, "seed": seed,
                "model": "random_forest_full", "encoding": "symmetric",
                "max_depth": "None", "test_view": "pooled",
                **{k: getattr(m, k) for k in METRICS},
                "n": m.n, "threshold": threshold, "fit_seconds": round(elapsed, 1),
            })
            pd.DataFrame(rows).to_csv(out_path, index=False)
            print(f"      AUPRC {m.auprc:.4f}  AUC {m.auc_roc:.4f}  ({elapsed:.0f}s fit)",
                  flush=True)

    full = pd.DataFrame(rows)
    capped = pd.read_csv(REPORTS / "phase_a_results.csv")
    capped = capped[(capped.test_view == "pooled") & (capped.model == "random_forest")
                    & (capped.encoding == "symmetric")]

    lines = ["# Unbounded random forest on the two critical configurations\n",
             "Generated by `scripts/13_full_random_forest.py`. `max_depth=None`, "
             "symmetric encoding, 5 seeds.\n",
             "The Phase A grid capped depth at 30 for tractability, making its "
             "random-forest numbers a lower bound. This checks whether the cap "
             "changed a conclusion.\n",
             "| Configuration | capped (depth 30) | unbounded | difference | paired t p |",
             "|---|---|---|---|---|"]
    comparisons = []
    for scheme, strategy in CONFIGS:
        f = full[(full.scheme == scheme) & (full.negatives == strategy)].set_index("seed")["auprc"]
        c = capped[(capped.scheme == scheme) & (capped.negatives == strategy)].set_index("seed")["auprc"]
        seeds = sorted(set(f.index) & set(c.index))
        if len(seeds) < 2:
            continue
        cmp = paired_compare(f.loc[seeds].to_numpy(), c.loc[seeds].to_numpy(),
                             name_a=f"unbounded @ {scheme}/{strategy}",
                             name_b=f"depth-30 @ {scheme}/{strategy}")
        comparisons.append(cmp)
        lines.append(f"| {scheme} + {strategy} | {cmp.mean_b:.4f} | {cmp.mean_a:.4f} | "
                     f"{cmp.mean_difference:+.4f} | {cmp.t_p_value:.4f} |")
        print("\n" + cmp.summary())
    lines.append("")
    lines.append(f"Mean fit time: {full['fit_seconds'].mean():.0f}s per forest "
                 f"(against ~20-130s at depth 30).\n")
    (REPORTS / "phase_a_full_rf.md").write_text("\n".join(lines))
    (REPORTS / "phase_a_full_rf.json").write_text(
        json.dumps([c.to_dict() for c in comparisons], indent=2, default=float))
    print(f"\nWrote {out_path} and {REPORTS/'phase_a_full_rf.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
