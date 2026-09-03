#!/usr/bin/env python3
import hashlib
import importlib.util
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ddinet.data.v2_dataset import (
    assert_no_ddi_features,
    load_frozen_split,
    load_universe,
)
from ddinet.features.molgraph import build_mol_graphs
from ddinet.training.v2_trainer import (
    EvaluationMode,
    V2Trainer,
    resolve_biology,
    compute_binary_metrics,
    expected_calibration_error,
)

FINAL_DIR = ROOT / "reports" / "v2_final"
VALIDATION_CSV = FINAL_DIR / "v2_final_validation.csv"
CHECKPOINTS = ROOT / "reports" / "v2_final_checkpoints"

S3_CSV = FINAL_DIR / "v2_final_s3_posthoc.csv"
PRED_CSV = FINAL_DIR / "v2_final_pair_predictions.csv"

EXPECTED_CONFIG_ID = "e8ece7c41ae09e5f"


def load_specs():
    path = ROOT / "scripts" / "35_v2_final_runner.py"
    spec = importlib.util.spec_from_file_location("v2_final_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_specs()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def metrics(prefix, y, scores):
    m = compute_binary_metrics(y, scores, threshold=0.5)
    return {
        f"{prefix}_auprc": float(m.auprc),
        f"{prefix}_auroc": float(m.auc_roc),
        f"{prefix}_brier": float(m.brier),
        f"{prefix}_ece": float(
            expected_calibration_error(y, scores, n_bins=15)
        ),
        f"{prefix}_n": int(m.n),
        f"{prefix}_prevalence": float(m.prevalence),
    }


def main():
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable")

    specs = load_specs()

    if len(specs) != 5 or {s.seed for s in specs} != {0, 1, 2, 3, 4}:
        raise RuntimeError("Expected exactly frozen seeds 0..4")

    if {s.config_id() for s in specs} != {EXPECTED_CONFIG_ID}:
        raise RuntimeError("Frozen config_id mismatch")

    validation = pd.read_csv(
        VALIDATION_CSV,
        dtype={"run_id": str, "config_id": str},
    )
    validation_by_id = {
        str(r["run_id"]): r for _, r in validation.iterrows()
    }

    universe = load_universe()
    assert_no_ddi_features(universe.drugs, "drugs.parquet")

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

    summary_rows = []
    prediction_frames = []

    for s in specs:
        run_id = s.run_id()

        if run_id not in validation_by_id:
            raise RuntimeError(f"Missing validation row for {run_id}")

        ckpt = CHECKPOINTS / f"{run_id}.pt"
        if not ckpt.exists():
            raise RuntimeError(f"Missing checkpoint {ckpt}")

        trainer = V2Trainer(
            s,
            universe,
            split,
            bundle,
            mol_graphs,
            mode=EvaluationMode.WITH_TEST,
            dataset=None,
            device="cuda",
        )

        blob = torch.load(
            ckpt,
            map_location="cpu",
            weights_only=False,
        )

        if blob.get("run_id") != run_id:
            raise RuntimeError(f"Checkpoint run_id mismatch: {run_id}")

        trainer.model.load_state_dict(blob["model_state"])

        # Frozen validation recheck: no training, no model selection.
        vm = trainer.validation_metrics()
        recorded_val = float(
            validation_by_id[run_id]["val_auprc"]
        )
        if abs(vm["val_auprc"] - recorded_val) > 1e-9:
            raise RuntimeError(
                f"Validation mismatch seed {s.seed}: "
                f"{vm['val_auprc']} vs {recorded_val}"
            )

        if "test_S3" not in trainer.buckets:
            raise RuntimeError(
                f"test_S3 bucket missing for seed {s.seed}; "
                f"available={sorted(trainer.buckets)}"
            )

        # Pooled test predictions.
        pooled = trainer._pooled("test")
        y_all, p_all = trainer._predict(pooled)

        # Fully inductive S3 predictions.
        s3 = trainer.buckets["test_S3"]
        y_s3, p_s3 = trainer._predict(s3)

        row = {
            "run_id": run_id,
            "config_id": s.config_id(),
            "seed": s.seed,
            "checkpoint_sha256": sha256(ckpt),
            "val_auprc_recheck": vm["val_auprc"],
            **metrics("test", y_all, p_all),
            **metrics("s3", y_s3, p_s3),
        }
        summary_rows.append(row)

        # Pair-level predictions for bootstrap/subgroup analyses.
        for view, data, y, scores in [
            ("pooled", pooled, y_all, p_all),
            ("S3", s3, y_s3, p_s3),
        ]:
            frame = data["frame"].copy().reset_index(drop=True)

            if len(frame) != len(scores):
                raise RuntimeError(
                    f"Frame/prediction mismatch seed={s.seed} view={view}"
                )

            frame["seed"] = s.seed
            frame["run_id"] = run_id
            frame["test_view"] = view
            frame["label"] = y
            frame["prediction"] = scores

            keep = [
                c for c in [
                    "seed",
                    "run_id",
                    "test_view",
                    "drug_a",
                    "drug_b",
                    "label",
                    "prediction",
                ]
                if c in frame.columns
            ]
            prediction_frames.append(frame[keep])

        print(
            f"seed {s.seed}: "
            f"pooled={row['test_auprc']:.6f} "
            f"S3={row['s3_auprc']:.6f} "
            f"n_S3={row['s3_n']}"
        )

    git_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()

    evaluated_at = datetime.now(timezone.utc).isoformat()

    summary = pd.DataFrame(summary_rows).sort_values("seed")
    summary["git_commit_posthoc"] = git_commit
    summary["evaluated_at_utc"] = evaluated_at

    predictions = pd.concat(
        prediction_frames,
        ignore_index=True,
    )

    summary.to_csv(S3_CSV, index=False)
    predictions.to_csv(PRED_CSV, index=False)

    print("\nPOST-HOC FROZEN EVALUATION COMPLETE")
    print(
        summary[
            ["seed", "s3_auprc", "s3_auroc", "s3_brier", "s3_ece", "s3_n"]
        ].to_string(index=False)
    )

    print(
        f"\nS3 AUPRC mean={summary['s3_auprc'].mean():.6f} "
        f"std={summary['s3_auprc'].std(ddof=1):.6f}"
    )
    print(f"wrote {S3_CSV}")
    print(f"wrote {PRED_CSV}")
    print("No training or model selection was performed.")


if __name__ == "__main__":
    main()
