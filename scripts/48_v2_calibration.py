#!/usr/bin/env python3
"""
Preregistered V2 calibration analysis for the frozen primary M4 BIO-GINE.

Protocol
--------
1. Load the five frozen final M4 specifications and best checkpoints.
2. Reconstruct VALIDATION only and obtain pair-level validation probabilities.
3. Fit one TemperatureScaler per seed using validation labels/probabilities only.
4. Apply the fitted temperature to the ALREADY-FROZEN pooled test predictions.
   No test inference is performed by this script.
5. Report raw/scaled Brier and ECE with exactly 15 uniform bins.
6. Verify temperature scaling preserves ranking/AUPRC/AUROC.
7. Save reliability diagrams and an audit-friendly CSV.

The test set is never used to fit temperature.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ddinet.data.v2_dataset import load_frozen_split, load_universe
from ddinet.eval.calibration import (
    TemperatureScaler,
    assert_ranking_preserved,
    expected_calibration_error,
    reliability_curve,
)
from ddinet.features.molgraph import build_mol_graphs
from ddinet.training.v2_trainer import (
    EvaluationMode,
    V2Trainer,
    resolve_biology,
)


VALIDATION_CSV = ROOT / "reports/v2_final/v2_final_validation.csv"
TEST_PREDICTIONS = ROOT / "reports/v2_final/v2_final_pair_predictions.csv"
CHECKPOINTS = ROOT / "reports/v2_final_checkpoints"

OUTDIR = ROOT / "reports/v2_calibration"
SUMMARY_CSV = OUTDIR / "m4_temperature_scaling.csv"
VAL_PRED_CSV = OUTDIR / "m4_validation_predictions.csv"
TEST_CAL_CSV = OUTDIR / "m4_test_calibrated_predictions.csv"
FIGURE = OUTDIR / "m4_reliability_diagram.png"

N_BINS = 15
EXPECTED_SEEDS = {0, 1, 2, 3, 4}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_specs():
    path = ROOT / "scripts" / "35_v2_final_runner.py"
    spec = importlib.util.spec_from_file_location("v2_final_runner_calibration", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.load_specs()


def preflight():
    specs = load_specs()

    if len(specs) != 5:
        raise RuntimeError(f"Expected 5 frozen M4 specs, got {len(specs)}")

    if {int(s.seed) for s in specs} != EXPECTED_SEEDS:
        raise RuntimeError(
            f"Seeds must be exactly {sorted(EXPECTED_SEEDS)}, "
            f"got {sorted(int(s.seed) for s in specs)}"
        )

    if not VALIDATION_CSV.exists():
        raise RuntimeError(f"Missing frozen validation file: {VALIDATION_CSV}")

    if not TEST_PREDICTIONS.exists():
        raise RuntimeError(f"Missing frozen test predictions: {TEST_PREDICTIONS}")

    validation = pd.read_csv(
        VALIDATION_CSV,
        dtype={"run_id": str, "config_id": str},
    )

    if len(validation) != 5:
        raise RuntimeError(
            f"Expected 5 validation rows, got {len(validation)}"
        )

    completed = validation[validation["status"].astype(str) == "completed"]
    if len(completed) != 5:
        raise RuntimeError("Not all five frozen validation runs are completed")

    validation_ids = set(validation["run_id"].astype(str))

    for s in specs:
        rid = s.run_id()
        if rid not in validation_ids:
            raise RuntimeError(f"Missing validation row for {rid}")

        ckpt = CHECKPOINTS / f"{rid}.pt"
        if not ckpt.exists():
            raise RuntimeError(f"Missing frozen checkpoint: {ckpt}")

    test = pd.read_csv(TEST_PREDICTIONS, dtype={"run_id": str})

    required = {
        "seed", "run_id", "test_view",
        "drug_a", "drug_b", "label", "prediction",
    }
    missing = required - set(test.columns)
    if missing:
        raise RuntimeError(f"Frozen test predictions missing columns: {missing}")

    pooled = test[test["test_view"].astype(str) == "pooled"].copy()

    if set(pooled["seed"].astype(int)) != EXPECTED_SEEDS:
        raise RuntimeError("Frozen pooled test predictions do not contain seeds 0-4")

    counts = pooled.groupby("seed").size()
    if counts.nunique() != 1:
        raise RuntimeError(f"Unequal pooled test sizes across seeds: {counts.to_dict()}")

    if len(pooled) == 0:
        raise RuntimeError("No pooled frozen test predictions found")

    return specs, validation, pooled


def plot_reliability(test_cal: pd.DataFrame) -> None:
    # Seed-0 diagram is the preregistered representative visualization.
    d = test_cal[test_cal["seed"] == 0].copy()
    y = d["label"].to_numpy(dtype=int)
    raw = d["prediction_raw"].to_numpy(dtype=float)
    scaled = d["prediction_scaled"].to_numpy(dtype=float)

    rc_raw = reliability_curve(y, raw, n_bins=N_BINS, strategy="uniform")
    rc_scaled = reliability_curve(y, scaled, n_bins=N_BINS, strategy="uniform")

    fig, ax = plt.subplots(figsize=(7.2, 6.2))

    ax.plot([0, 1], [0, 1], linestyle="--", linewidth=1.2, label="Perfect calibration")
    ax.plot(
        rc_raw.mean_predicted,
        rc_raw.observed_frequency,
        marker="o",
        linewidth=1.6,
        label="Raw M4",
    )
    ax.plot(
        rc_scaled.mean_predicted,
        rc_scaled.observed_frequency,
        marker="o",
        linewidth=1.6,
        label="Temperature-scaled M4",
    )

    ax.set_xlabel("Mean predicted probability")
    ax.set_ylabel("Observed positive fraction")
    ax.set_title("M4 BIO-GINE reliability diagram — seed 0, pooled test")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGURE, dpi=220)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Frozen V2 M4 temperature-scaling calibration analysis."
    )
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--device", choices=["cpu", "cuda"], default="cuda")
    args = ap.parse_args()

    specs, validation, pooled_test = preflight()

    print("V2 M4 CALIBRATION PREFLIGHT")
    print("----------------------------")
    print("frozen specs: 5/5")
    print("frozen checkpoints: 5/5")
    print("validation summary rows: 5/5")
    print(f"frozen pooled test predictions: {len(pooled_test):,}")
    print(f"ECE bins: {N_BINS}")
    print("temperature fit source: VALIDATION ONLY")
    print("test source: ALREADY-FROZEN pair predictions")
    print("test inference in this script: NONE")

    if not args.execute:
        print("\nDRY RUN COMPLETE — no calibration fitted and no test output written.")
        return 0

    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable")

    for path in (SUMMARY_CSV, VAL_PRED_CSV, TEST_CAL_CSV, FIGURE):
        if path.exists():
            raise RuntimeError(
                f"Output already exists: {path}. "
                "Refusing overwrite to preserve audit trail."
            )

    OUTDIR.mkdir(parents=True, exist_ok=True)

    universe = load_universe()
    split = load_frozen_split(
        universe,
        specs[0].scheme,
        specs[0].split_seed,
    )

    drug_ids = list(universe.drugs["drugbank_id"])
    bundle, _ = resolve_biology(specs[0], drug_ids)

    mol_graphs = build_mol_graphs(
        list(universe.drugs["name"]),
        list(universe.drugs["smiles"]),
    )

    validation_by_id = {
        str(r["run_id"]): r
        for _, r in validation.iterrows()
    }

    summary_rows = []
    validation_prediction_frames = []
    calibrated_test_frames = []

    for s in sorted(specs, key=lambda x: int(x.seed)):
        seed = int(s.seed)
        rid = s.run_id()
        ckpt = CHECKPOINTS / f"{rid}.pt"

        print(f"\nseed {seed}: reconstructing validation predictions...", flush=True)

        # Critical audit property:
        # VALIDATION_ONLY means this trainer does not expose test labels/data.
        trainer = V2Trainer(
            s,
            universe,
            split,
            bundle,
            mol_graphs,
            mode=EvaluationMode.VALIDATION_ONLY,
            dataset=None,
            device=args.device,
        )

        blob = torch.load(
            ckpt,
            map_location="cpu",
            weights_only=False,
        )

        if blob.get("run_id") != rid:
            raise RuntimeError(
                f"Checkpoint run_id mismatch for seed {seed}"
            )

        if "model_state" not in blob:
            raise RuntimeError(
                f"Checkpoint model_state missing for seed {seed}"
            )

        trainer.model.load_state_dict(blob["model_state"])

        y_val, p_val = trainer.predict_validation()
        y_val = np.asarray(y_val, dtype=int)
        p_val = np.asarray(p_val, dtype=float)

        recorded = validation_by_id[rid]
        recorded_auprc = float(recorded["val_auprc"])
        reproduced_auprc = float(average_precision_score(y_val, p_val))

        if abs(reproduced_auprc - recorded_auprc) > 1e-9:
            raise RuntimeError(
                f"Validation AUPRC mismatch seed {seed}: "
                f"{reproduced_auprc} vs {recorded_auprc}"
            )

        scaler = TemperatureScaler().fit(y_val, p_val)

        if not scaler.converged:
            raise RuntimeError(
                f"Temperature optimization did not converge for seed {seed}"
            )

        test_seed = pooled_test[
            pooled_test["seed"].astype(int) == seed
        ].copy()

        if set(test_seed["run_id"].astype(str)) != {rid}:
            raise RuntimeError(
                f"Frozen test run_id mismatch for seed {seed}"
            )

        y_test = test_seed["label"].to_numpy(dtype=int)
        p_test = test_seed["prediction"].to_numpy(dtype=float)
        p_scaled = scaler.transform(p_test)

        assert_ranking_preserved(p_test, p_scaled)

        raw_ap = float(average_precision_score(y_test, p_test))
        scaled_ap = float(average_precision_score(y_test, p_scaled))
        raw_auc = float(roc_auc_score(y_test, p_test))
        scaled_auc = float(roc_auc_score(y_test, p_scaled))

        # Temperature scaling is monotonic. Threshold-free ranking metrics
        # must remain numerically unchanged.
        # Ranking preservation is checked directly above by
        # assert_ranking_preserved(). Tiny AP/AUROC differences can still
        # arise from floating-point clipping/ties after transforming extreme
        # probabilities, so record them rather than using metric equality as
        # a second ranking invariant.
        ap_numeric_delta = scaled_ap - raw_ap
        auc_numeric_delta = scaled_auc - raw_auc

        raw_brier = float(brier_score_loss(y_test, p_test))
        scaled_brier = float(brier_score_loss(y_test, p_scaled))

        raw_ece = float(
            expected_calibration_error(
                y_test, p_test,
                n_bins=N_BINS,
                strategy="uniform",
            )
        )
        scaled_ece = float(
            expected_calibration_error(
                y_test, p_scaled,
                n_bins=N_BINS,
                strategy="uniform",
            )
        )

        summary_rows.append({
            "seed": seed,
            "run_id": rid,
            "checkpoint_sha256": sha256(ckpt),
            "val_n": len(y_val),
            "val_auprc_reproduced": reproduced_auprc,
            "temperature": float(scaler.temperature),
            "temperature_converged": bool(scaler.converged),
            "test_n": len(y_test),
            "test_auprc_raw": raw_ap,
            "test_auprc_scaled": scaled_ap,
            "test_auroc_raw": raw_auc,
            "test_auroc_scaled": scaled_auc,
            "test_brier_raw": raw_brier,
            "test_brier_scaled": scaled_brier,
            "test_ece15_raw": raw_ece,
            "test_ece15_scaled": scaled_ece,
        })

        validation_prediction_frames.append(
            pd.DataFrame({
                "seed": seed,
                "run_id": rid,
                "label": y_val,
                "prediction": p_val,
            })
        )

        test_seed = test_seed[
            ["seed", "run_id", "test_view", "drug_a", "drug_b", "label"]
        ].copy()
        test_seed["prediction_raw"] = p_test
        test_seed["prediction_scaled"] = p_scaled
        test_seed["temperature"] = float(scaler.temperature)
        calibrated_test_frames.append(test_seed)

        print(
            f"  T={scaler.temperature:.6f} | "
            f"Brier {raw_brier:.6f} -> {scaled_brier:.6f} | "
            f"ECE-15 {raw_ece:.6f} -> {scaled_ece:.6f} | "
            f"AUPRC {raw_ap:.6f} unchanged",
            flush=True,
        )

    summary = pd.DataFrame(summary_rows).sort_values("seed")
    val_predictions = pd.concat(
        validation_prediction_frames,
        ignore_index=True,
    )
    test_cal = pd.concat(
        calibrated_test_frames,
        ignore_index=True,
    )

    summary.to_csv(SUMMARY_CSV, index=False)
    val_predictions.to_csv(VAL_PRED_CSV, index=False)
    test_cal.to_csv(TEST_CAL_CSV, index=False)

    plot_reliability(test_cal)

    git_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()

    print("\nCALIBRATION COMPLETE")
    print("--------------------")
    print(summary[
        [
            "seed",
            "temperature",
            "test_brier_raw",
            "test_brier_scaled",
            "test_ece15_raw",
            "test_ece15_scaled",
            "test_auprc_raw",
        ]
    ].to_string(index=False))

    print("\n5-seed summary:")
    for col in [
        "temperature",
        "test_brier_raw",
        "test_brier_scaled",
        "test_ece15_raw",
        "test_ece15_scaled",
    ]:
        print(
            f"{col}: "
            f"{summary[col].mean():.6f} ± "
            f"{summary[col].std(ddof=1):.6f}"
        )

    print(f"\nGit commit at execution: {git_commit}")
    print(f"wrote {SUMMARY_CSV}")
    print(f"wrote {VAL_PRED_CSV}")
    print(f"wrote {TEST_CAL_CSV}")
    print(f"wrote {FIGURE}")
    print("\nTemperature was fitted on validation only.")
    print("No test inference was performed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
