#!/usr/bin/env python3
import argparse
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
    compute_binary_metrics,
    expected_calibration_error,
    resolve_biology,
)

ABLATION_DIR = ROOT / "reports" / "v2_ablations"
VALIDATION_CSV = ABLATION_DIR / "validation.csv"
CHECKPOINTS = ABLATION_DIR / "checkpoints"

TEST_CSV = ABLATION_DIR / "test_frozen.csv"
PRED_CSV = ABLATION_DIR / "pair_predictions.csv"

EXPECTED_VARIANTS = {
    ("M1", "true", "mean"),
    ("M2", "true", "mean"),
    ("M3", "true", "mean"),
    ("M4", "true", "sum"),
    ("M4", "shuffled", "mean"),
}
EXPECTED_SEEDS = {0, 1, 2, 3, 4}


def load_specs():
    path = ROOT / "scripts" / "41_v2_ablation_runner.py"
    spec = importlib.util.spec_from_file_location("v2_ablation_runner", path)
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


def verify_frozen_inputs(specs, validation):
    if len(specs) != 25:
        raise RuntimeError(f"Expected 25 frozen specs, got {len(specs)}")

    variants = {
        (s.ablation, s.biology_source, s.aggregation)
        for s in specs
    }
    if variants != EXPECTED_VARIANTS:
        raise RuntimeError(
            f"Frozen variant mismatch.\nExpected={sorted(EXPECTED_VARIANTS)}"
            f"\nGot={sorted(variants)}"
        )

    for variant in EXPECTED_VARIANTS:
        seeds = {
            s.seed
            for s in specs
            if (s.ablation, s.biology_source, s.aggregation) == variant
        }
        if seeds != EXPECTED_SEEDS:
            raise RuntimeError(
                f"Variant {variant} seeds mismatch: {sorted(seeds)}"
            )

    if len({s.run_id() for s in specs}) != 25:
        raise RuntimeError("Expected 25 unique frozen run_ids")

    if len({s.config_id() for s in specs}) != 5:
        raise RuntimeError("Expected exactly 5 unique frozen config_ids")

    if len(validation) != 25:
        raise RuntimeError(
            f"Expected exactly 25 validation rows, got {len(validation)}"
        )

    if "status" not in validation.columns:
        raise RuntimeError("validation.csv has no status column")

    bad_status = validation.loc[validation["status"] != "completed"]
    if len(bad_status):
        raise RuntimeError(
            f"Found {len(bad_status)} non-completed validation rows"
        )

    validation_ids = set(validation["run_id"].astype(str))
    spec_ids = {s.run_id() for s in specs}

    if validation_ids != spec_ids:
        raise RuntimeError(
            "Validation/spec run_id set mismatch: "
            f"missing={sorted(spec_ids - validation_ids)}, "
            f"extra={sorted(validation_ids - spec_ids)}"
        )

    for s in specs:
        run_id = s.run_id()
        ckpt = CHECKPOINTS / f"{run_id}.pt"
        manifest = CHECKPOINTS / f"{run_id}.manifest.json"

        if not ckpt.exists():
            raise RuntimeError(f"Missing checkpoint: {ckpt}")
        if not manifest.exists():
            raise RuntimeError(f"Missing manifest: {manifest}")

    pt_files = list(CHECKPOINTS.glob("*.pt"))
    manifest_files = list(CHECKPOINTS.glob("*.manifest.json"))

    if len(pt_files) != 25 or len(manifest_files) != 25:
        raise RuntimeError(
            "Expected exactly 25 .pt + 25 manifests, got "
            f"{len(pt_files)} .pt + {len(manifest_files)} manifests"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify frozen specs/validation/checkpoints only. Never opens test.",
    )
    args = parser.parse_args()

    specs = load_specs()

    validation = pd.read_csv(
        VALIDATION_CSV,
        dtype={
            "run_id": str,
            "config_id": str,
            "ablation": str,
            "biology_source": str,
            "aggregation": str,
            "status": str,
        },
    )

    verify_frozen_inputs(specs, validation)

    print("FROZEN INPUT CHECK PASS")
    print("specs: 25")
    print("validation rows: 25 completed")
    print("checkpoints: 25 .pt + 25 manifests")
    print("variants:")
    for variant in sorted(EXPECTED_VARIANTS):
        print(" ", variant)

    if args.dry_run:
        print("\nDRY RUN COMPLETE — TEST WAS NOT OPENED")
        return

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable")

    if TEST_CSV.exists() or PRED_CSV.exists():
        raise RuntimeError(
            "Frozen test outputs already exist. Refusing to overwrite:\n"
            f"{TEST_CSV}\n{PRED_CSV}"
        )

    validation_by_id = {
        str(r["run_id"]): r
        for _, r in validation.iterrows()
    }

    universe = load_universe()
    assert_no_ddi_features(universe.drugs, "drugs.parquet")

    # All 25 specs are required to use the exact same frozen split.
    split_keys = {
        (s.scheme, s.split_seed, s.negatives, s.eval_negative_seed)
        for s in specs
    }
    if len(split_keys) != 1:
        raise RuntimeError(f"Expected one frozen split definition: {split_keys}")

    first = specs[0]
    split = load_frozen_split(
        universe,
        first.scheme,
        first.split_seed,
    )

    drug_ids = list(universe.drugs["drugbank_id"])

    mol_graphs = build_mol_graphs(
        list(universe.drugs["name"]),
        list(universe.drugs["smiles"]),
    )

    summary_rows = []
    prediction_frames = []

    for i, s in enumerate(specs, start=1):
        run_id = s.run_id()
        variant = (
            s.ablation,
            s.biology_source,
            s.aggregation,
        )

        print(
            f"\n[{i:02d}/25] "
            f"{s.ablation} biology={s.biology_source} "
            f"aggregation={s.aggregation} seed={s.seed} "
            f"run={run_id}"
        )

        ckpt = CHECKPOINTS / f"{run_id}.pt"

        # IMPORTANT: resolve biology separately for every frozen spec.
        # This prevents shuffled M4 from accidentally receiving true biology.
        bundle, _ = resolve_biology(s, drug_ids)

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
            raise RuntimeError(
                f"Checkpoint run_id mismatch: "
                f"{blob.get('run_id')} != {run_id}"
            )

        trainer.model.load_state_dict(blob["model_state"])

        # Reproduce validation before accepting this frozen checkpoint.
        vm = trainer.validation_metrics()
        recorded_val = float(
            validation_by_id[run_id]["val_auprc"]
        )

        if abs(vm["val_auprc"] - recorded_val) > 1e-9:
            raise RuntimeError(
                f"Validation mismatch for {variant}, seed={s.seed}: "
                f"{vm['val_auprc']} vs {recorded_val}"
            )

        if "test_S3" not in trainer.buckets:
            raise RuntimeError(
                f"test_S3 bucket missing for {variant}, seed={s.seed}; "
                f"available={sorted(trainer.buckets)}"
            )

        pooled = trainer._pooled("test")
        y_all, p_all = trainer._predict(pooled)

        s3 = trainer.buckets["test_S3"]
        y_s3, p_s3 = trainer._predict(s3)

        row = {
            "ablation": s.ablation,
            "biology_source": s.biology_source,
            "aggregation": s.aggregation,
            "seed": s.seed,
            "run_id": run_id,
            "config_id": s.config_id(),
            "checkpoint_sha256": sha256(ckpt),
            "val_auprc_recheck": float(vm["val_auprc"]),
            **metrics("test", y_all, p_all),
            **metrics("s3", y_s3, p_s3),
        }
        summary_rows.append(row)

        # Keep pair-level frozen predictions for bootstrap/subgroup analyses.
        for view, data, y, scores in (
            ("pooled", pooled, y_all, p_all),
            ("S3", s3, y_s3, p_s3),
        ):
            frame = data["frame"].copy().reset_index(drop=True)

            if len(frame) != len(scores):
                raise RuntimeError(
                    f"Frame/prediction mismatch "
                    f"{variant}, seed={s.seed}, view={view}: "
                    f"{len(frame)} != {len(scores)}"
                )

            frame["ablation"] = s.ablation
            frame["biology_source"] = s.biology_source
            frame["aggregation"] = s.aggregation
            frame["seed"] = s.seed
            frame["run_id"] = run_id
            frame["config_id"] = s.config_id()
            frame["test_view"] = view
            frame["label"] = y
            frame["prediction"] = scores

            keep = [
                c for c in [
                    "ablation",
                    "biology_source",
                    "aggregation",
                    "seed",
                    "run_id",
                    "config_id",
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
            f"  val={row['val_auprc_recheck']:.6f} "
            f"pooled={row['test_auprc']:.6f} "
            f"S3={row['s3_auprc']:.6f} "
            f"n_S3={row['s3_n']}"
        )

        del trainer, bundle, blob
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    git_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()

    evaluated_at = datetime.now(timezone.utc).isoformat()

    summary = pd.DataFrame(summary_rows).sort_values(
        ["ablation", "biology_source", "aggregation", "seed"]
    )
    summary["git_commit_evaluator"] = git_commit
    summary["evaluated_at_utc"] = evaluated_at

    predictions = pd.concat(
        prediction_frames,
        ignore_index=True,
    )

    # Write only after all 25 frozen evaluations have succeeded.
    summary.to_csv(TEST_CSV, index=False)
    predictions.to_csv(PRED_CSV, index=False)

    print("\nFROZEN ABLATION TEST EVALUATION COMPLETE")
    print("25/25 checkpoints evaluated; no training/model selection performed.")

    print("\n=== TEST AUPRC SUMMARY ===")
    print(
        summary.groupby(
            ["ablation", "biology_source", "aggregation"]
        )["test_auprc"]
        .agg(["count", "mean", "std", "min", "max"])
        .sort_values("mean", ascending=False)
        .to_string()
    )

    print("\n=== S3 AUPRC SUMMARY ===")
    print(
        summary.groupby(
            ["ablation", "biology_source", "aggregation"]
        )["s3_auprc"]
        .agg(["count", "mean", "std", "min", "max"])
        .sort_values("mean", ascending=False)
        .to_string()
    )

    print(f"\nwrote {TEST_CSV}")
    print(f"wrote {PRED_CSV}")
    print("No training or model selection was performed.")


if __name__ == "__main__":
    main()
