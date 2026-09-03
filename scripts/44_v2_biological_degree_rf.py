#!/usr/bin/env python3
"""
Frozen H-V2-4 control: biological-degree-only Random Forest.

Primary comparison:
    BIO-GINE M4 > biological-degree-only RF
    on drug-disjoint + degree-matched test pairs.

Important:
- split_seed = 0
- evaluation_negative_seed = 0
- training negative seed varies 0..4
- M4 true biology
- no protein/pathway identity is supplied to the RF
- RF hyperparameters are the preregistered defaults implemented in
  BiologicalDegreeRF
- no model selection is performed here
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ddinet.eval.calibration import expected_calibration_error
from ddinet.models.bio_baselines import BiologicalDegreeRF
from ddinet.models.classical import PairBatch
from ddinet.training.v2_trainer import (
    EvaluationMode,
    V2RunSpec,
    build_v2_dataset,
    resolve_biology,
)
from run_v2 import load_frozen_split, load_universe


OUT_DIR = ROOT / "reports" / "v2_bio_controls"
RESULTS = OUT_DIR / "biological_degree_rf_test.csv"
PREDICTIONS = OUT_DIR / "biological_degree_rf_pair_predictions.csv"
MANIFEST = OUT_DIR / "biological_degree_rf_manifest.json"

SEEDS = tuple(range(5))


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
        ).strip()
    except Exception:
        return "UNKNOWN"


def make_spec(seed: int) -> V2RunSpec:
    # Fields irrelevant to this RF are retained at the frozen selected M4
    # values so dataset identity is exactly aligned with the primary model.
    return V2RunSpec(
        scheme="drug",
        split_seed=0,
        negatives="degree_matched",
        eval_negative_seed=0,
        seed=seed,
        ablation="M4",
        biology_source="true",
        aggregation="mean",
        bio_dim=128,
        dropout_bio=0.1,
        dropout_pair=0.1,
        lr=0.001,
        batch_size=512,
        max_optimizer_steps=21960,
        validation_interval_steps=366,
        patience_checks=30,
    )


def pair_batch(frame: pd.DataFrame) -> PairBatch:
    return PairBatch(
        drug_a=frame["drug_a"].astype(str).tolist(),
        drug_b=frame["drug_b"].astype(str).tolist(),
        y=frame["label"].to_numpy(dtype=np.int64),
    )


def pooled(dataset: pd.DataFrame, prefix: str) -> pd.DataFrame:
    out = dataset.loc[
        dataset["bucket"].astype(str).str.startswith(prefix),
        ["drug_a", "drug_b", "label", "bucket"],
    ].copy()
    if out.empty:
        raise RuntimeError(
            f"No rows found for bucket prefix {prefix!r}; "
            f"available={sorted(dataset['bucket'].astype(str).unique())}"
        )
    return out.reset_index(drop=True)


def metrics(y: np.ndarray, p: np.ndarray) -> dict:
    return {
        "auprc": float(average_precision_score(y, p)),
        "auroc": float(roc_auc_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "ece": float(expected_calibration_error(y, p, n_bins=15)),
        "n": int(len(y)),
        "prevalence": float(np.mean(y)),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if RESULTS.exists() or PREDICTIONS.exists():
        raise RuntimeError(
            "Frozen H4 outputs already exist; refusing to overwrite them."
        )

    universe = load_universe()
    split = load_frozen_split(universe, "drug", 0)

    print("=== H-V2-4 FROZEN CONTROL ===")
    print("model       BiologicalDegreeRF")
    print("split       drug-disjoint, split_seed=0")
    print("negatives   degree_matched")
    print("eval seed   0")
    print("seeds       0,1,2,3,4")
    print("RF          500 trees, max_depth=20, min_samples_leaf=5")
    print("biology     M4 true; COUNTS ONLY, no protein/pathway identity")
    print(f"train drugs {len(split.train_drugs)}")

    if args.dry_run:
        # Build seed 0 dataset so the frozen split/sampler contract is checked,
        # but do not fit a model or score test predictions.
        spec = make_spec(0)
        dataset = build_v2_dataset(
            spec, universe, split, EvaluationMode.WITH_TEST
        )
        train = pooled(dataset, "train")
        test = pooled(dataset, "test")
        print(f"train pairs {len(train):,}")
        print(f"test pairs  {len(test):,}")
        print("buckets     " + ", ".join(sorted(dataset["bucket"].astype(str).unique())))
        print("DRY RUN COMPLETE — NO MODEL WAS FITTED")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    result_rows = []
    prediction_rows = []
    commit = git_commit()

    drug_ids = list(universe.drugs["drugbank_id"].astype(str))

    for seed in SEEDS:
        print(f"\n--- seed {seed} ---", flush=True)

        spec = make_spec(seed)
        dataset = build_v2_dataset(
            spec, universe, split, EvaluationMode.WITH_TEST
        )

        train = pooled(dataset, "train")
        test = pooled(dataset, "test")

        bundle, provenance = resolve_biology(spec, drug_ids)

        model = BiologicalDegreeRF.build(
            bundle,
            split.train_drugs,
            seed=seed,
            # Explicit preregistered defaults:
            n_estimators=500,
            max_depth=20,
            min_samples_leaf=5,
            n_jobs=-1,
            log_counts=True,
        )

        model.fit(pair_batch(train))

        test_batch = pair_batch(test)
        pred = model.predict_proba(test_batch)
        y = test["label"].to_numpy(dtype=np.int64)

        m = metrics(y, pred)

        print(
            f"test AUPRC {m['auprc']:.6f} | "
            f"AUROC {m['auroc']:.6f} | "
            f"Brier {m['brier']:.6f} | "
            f"ECE {m['ece']:.6f} | n={m['n']:,}",
            flush=True,
        )

        result_rows.append({
            "model": "biological_degree_rf",
            "seed": seed,
            "split": "drug",
            "split_seed": 0,
            "negatives": "degree_matched",
            "eval_negative_seed": 0,
            "biology_policy": "M4",
            "biology_source": "true",
            "test_auprc": m["auprc"],
            "test_auroc": m["auroc"],
            "test_brier": m["brier"],
            "test_ece": m["ece"],
            "test_n": m["n"],
            "test_prevalence": m["prevalence"],
            "git_commit_before_run": commit,
            "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        })

        pred_frame = test.copy()
        pred_frame.insert(0, "seed", seed)
        pred_frame.insert(0, "model", "biological_degree_rf")
        pred_frame["prediction"] = pred
        prediction_rows.append(pred_frame)

    results = pd.DataFrame(result_rows)
    predictions = pd.concat(prediction_rows, ignore_index=True)

    results.to_csv(RESULTS, index=False)
    predictions.to_csv(PREDICTIONS, index=False)

    vals = results["test_auprc"].to_numpy(dtype=float)

    manifest = {
        "hypothesis": "H-V2-4",
        "model": "biological_degree_rf",
        "split": "drug",
        "split_seed": 0,
        "negatives": "degree_matched",
        "eval_negative_seed": 0,
        "seeds": list(SEEDS),
        "n_estimators": 500,
        "max_depth": 20,
        "min_samples_leaf": 5,
        "max_features": "sqrt",
        "class_weight": "balanced_subsample",
        "log_counts": True,
        "protein_identity": False,
        "pathway_identity": False,
        "mean_test_auprc": float(vals.mean()),
        "std_test_auprc": float(vals.std(ddof=1)),
        "git_commit_before_run": commit,
        "biology_provenance_last_seed": provenance,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, default=str) + "\n")

    print("\n=== H-V2-4 CONTROL COMPLETE ===")
    print(
        f"Biological-degree RF test AUPRC = "
        f"{vals.mean():.6f} ± {vals.std(ddof=1):.6f}"
    )
    print(f"WROTE {RESULTS}")
    print(f"WROTE {PREDICTIONS}")
    print(f"WROTE {MANIFEST}")


if __name__ == "__main__":
    main()
