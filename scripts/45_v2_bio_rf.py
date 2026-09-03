#!/usr/bin/env python3
"""
Preregistered BIO-RF strong control.

Features:
  - biological annotation counts
  - protein membership, train-only TruncatedSVD(128)
  - pathway membership, train-only TruncatedSVD(64)
  - ECFP4 / Morgan radius=2, 2048 bits

Evaluation alignment:
  split              drug-disjoint
  split_seed         0
  negatives          degree_matched
  eval_negative_seed 0
  seeds              0..4

Validation is run first and frozen before test access.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    roc_auc_score,
    brier_score_loss,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ddinet.eval.calibration import expected_calibration_error
from ddinet.features.pair_encoding import build_fingerprint_matrix
from ddinet.models.bio_baselines import BioRF
from ddinet.models.classical import PairBatch
from ddinet.training.v2_trainer import (
    EvaluationMode,
    V2RunSpec,
    build_v2_dataset,
    resolve_biology,
)
from run_v2 import load_frozen_split, load_universe


OUT = ROOT / "reports" / "v2_bio_controls"
VAL_FILE = OUT / "bio_rf_validation.csv"
TEST_FILE = OUT / "bio_rf_test.csv"
TEST_PRED = OUT / "bio_rf_pair_predictions.csv"
MANIFEST = OUT / "bio_rf_manifest.json"

SEEDS = tuple(range(5))


def git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
        ).strip()
    except Exception:
        return "UNKNOWN"


def make_spec(seed):
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


def batch(frame):
    return PairBatch(
        drug_a=frame["drug_a"].astype(str).tolist(),
        drug_b=frame["drug_b"].astype(str).tolist(),
        y=frame["label"].to_numpy(dtype=np.int64),
    )


def bucket(dataset, prefix):
    x = dataset.loc[
        dataset["bucket"].astype(str).str.startswith(prefix),
        ["drug_a", "drug_b", "label", "bucket"],
    ].copy()

    if x.empty:
        raise RuntimeError(
            f"No rows for prefix={prefix}; "
            f"buckets={sorted(dataset['bucket'].unique())}"
        )

    return x.reset_index(drop=True)


def score(y, p):
    return {
        "auprc": float(average_precision_score(y, p)),
        "auroc": float(roc_auc_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "ece": float(expected_calibration_error(y, p, n_bins=15)),
        "n": int(len(y)),
    }


def find_smiles_column(df):
    candidates = [
        "smiles",
        "canonical_smiles",
        "canonical_isomeric_smiles",
        "isomeric_smiles",
    ]
    for c in candidates:
        if c in df.columns:
            return c

    raise RuntimeError(
        "Cannot locate SMILES column. Available columns: "
        + ", ".join(map(str, df.columns))
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["validation", "test"],
        default="validation",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)

    if args.mode == "validation" and VAL_FILE.exists():
        raise RuntimeError(f"{VAL_FILE} already exists; refusing overwrite")

    if args.mode == "test":
        if not VAL_FILE.exists():
            raise RuntimeError(
                "BIO-RF validation results must be frozen before test access"
            )
        if TEST_FILE.exists() or TEST_PRED.exists():
            raise RuntimeError("BIO-RF test outputs already exist")

    universe = load_universe()
    split = load_frozen_split(universe, "drug", 0)

    drugs = universe.drugs.copy()
    smiles_col = find_smiles_column(drugs)

    ids = drugs["drugbank_id"].astype(str).tolist()
    smiles = drugs[smiles_col].astype(str).tolist()

    print("=== BIO-RF STRONG CONTROL ===")
    print("split       drug-disjoint / split_seed=0")
    print("negatives   degree_matched / eval_seed=0")
    print("seeds       0,1,2,3,4")
    print("biology     M4 true")
    print("protein SVD 128, train drugs only")
    print("pathway SVD 64, train drugs only")
    print("ECFP4       radius=2, bits=2048")
    print(f"SMILES col  {smiles_col}")
    print(f"drugs       {len(ids)}")
    print(f"train drugs {len(split.train_drugs)}")

    print("Building ECFP4 matrix...", flush=True)
    fingerprints = build_fingerprint_matrix(
        ids,
        smiles,
        radius=2,
        n_bits=2048,
    )
    print(
        f"ECFP4 ready: {fingerprints.matrix.shape[0]} x "
        f"{fingerprints.matrix.shape[1]}",
        flush=True,
    )

    mode = (
        EvaluationMode.VALIDATION_ONLY
        if args.mode == "validation"
        else EvaluationMode.WITH_TEST
    )

    # Dry-run verifies construction/sampling but never fits the RF.
    if args.dry_run:
        spec = make_spec(0)
        ds = build_v2_dataset(spec, universe, split, mode)

        train = bucket(ds, "train")
        target = bucket(ds, "val" if args.mode == "validation" else "test")

        print(f"train pairs  {len(train):,}")
        print(f"target pairs {len(target):,}")
        print("buckets      " + ", ".join(sorted(ds["bucket"].unique())))
        print("DRY RUN COMPLETE — NO MODEL WAS FITTED")
        return

    rows = []
    pred_rows = []
    commit = git_commit()

    for seed in SEEDS:
        print(f"\n--- seed {seed} ---", flush=True)

        spec = make_spec(seed)
        ds = build_v2_dataset(spec, universe, split, mode)

        train = bucket(ds, "train")
        target_prefix = "val" if args.mode == "validation" else "test"
        target = bucket(ds, target_prefix)

        bundle, provenance = resolve_biology(spec, ids)

        model = BioRF.build(
            bundle,
            split.train_drugs,
            protein_components=128,
            pathway_components=64,
            log_counts=True,
            fingerprints=fingerprints,
            seed=seed,
            n_estimators=500,
            max_depth=20,
            min_samples_leaf=5,
            n_jobs=-1,
        )

        model.fit(batch(train))

        y = target["label"].to_numpy(dtype=np.int64)
        p = model.predict_proba(batch(target))
        m = score(y, p)

        print(
            f"{target_prefix} AUPRC {m['auprc']:.6f} | "
            f"AUROC {m['auroc']:.6f} | "
            f"Brier {m['brier']:.6f} | "
            f"ECE {m['ece']:.6f} | n={m['n']:,}",
            flush=True,
        )

        rows.append({
            "model": "bio_rf",
            "seed": seed,
            "view": target_prefix,
            "split": "drug",
            "split_seed": 0,
            "negatives": "degree_matched",
            "eval_negative_seed": 0,
            "biology_policy": "M4",
            "biology_source": "true",
            "protein_components": 128,
            "pathway_components": 64,
            "ecfp_radius": 2,
            "ecfp_bits": 2048,
            "auprc": m["auprc"],
            "auroc": m["auroc"],
            "brier": m["brier"],
            "ece": m["ece"],
            "n": m["n"],
            "git_commit_before_run": commit,
            "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        })

        if args.mode == "test":
            q = target.copy()
            q.insert(0, "seed", seed)
            q.insert(0, "model", "bio_rf")
            q["prediction"] = p
            pred_rows.append(q)

    result = pd.DataFrame(rows)
    vals = result["auprc"].to_numpy(float)

    if args.mode == "validation":
        result.to_csv(VAL_FILE, index=False)
        print("\n=== BIO-RF VALIDATION COMPLETE ===")
        print(
            f"AUPRC = {vals.mean():.6f} ± "
            f"{vals.std(ddof=1):.6f}"
        )
        print(f"WROTE {VAL_FILE}")

    else:
        result.to_csv(TEST_FILE, index=False)
        pd.concat(pred_rows, ignore_index=True).to_csv(
            TEST_PRED,
            index=False,
        )

        manifest = {
            "model": "bio_rf",
            "biology": "M4 true",
            "counts": True,
            "protein_components": 128,
            "pathway_components": 64,
            "ecfp": {
                "radius": 2,
                "bits": 2048,
            },
            "svd_fit_scope": "training drugs only",
            "split": "drug",
            "split_seed": 0,
            "negatives": "degree_matched",
            "eval_negative_seed": 0,
            "seeds": list(SEEDS),
            "mean_test_auprc": float(vals.mean()),
            "std_test_auprc": float(vals.std(ddof=1)),
            "git_commit_before_run": commit,
            "biology_provenance_last_seed": provenance,
        }

        MANIFEST.write_text(
            json.dumps(manifest, indent=2, default=str) + "\n"
        )

        print("\n=== BIO-RF TEST COMPLETE ===")
        print(
            f"AUPRC = {vals.mean():.6f} ± "
            f"{vals.std(ddof=1):.6f}"
        )
        print(f"WROTE {TEST_FILE}")
        print(f"WROTE {TEST_PRED}")
        print(f"WROTE {MANIFEST}")


if __name__ == "__main__":
    main()
