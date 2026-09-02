#!/usr/bin/env python3
import argparse
import hashlib
import importlib.util
import os
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
)

FINAL_DIR = ROOT / "reports" / "v2_final"
VALIDATION_CSV = FINAL_DIR / "v2_final_validation.csv"
TEST_CSV = FINAL_DIR / "v2_final_test.csv"
CHECKPOINTS = ROOT / "reports" / "v2_final_checkpoints"
EXPECTED_CONFIG_ID = "e8ece7c41ae09e5f"


def load_specs():
    path = ROOT / "scripts" / "35_v2_final_runner.py"
    spec = importlib.util.spec_from_file_location("v2_final_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_specs()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def preflight(specs):
    if len(specs) != 5:
        raise RuntimeError(f"Expected 5 frozen specs, got {len(specs)}")

    if {s.seed for s in specs} != {0, 1, 2, 3, 4}:
        raise RuntimeError("Seeds must be exactly {0,1,2,3,4}")

    config_ids = {s.config_id() for s in specs}
    if config_ids != {EXPECTED_CONFIG_ID}:
        raise RuntimeError(f"Wrong frozen config_id(s): {config_ids}")

    if not VALIDATION_CSV.exists():
        raise RuntimeError(f"Missing {VALIDATION_CSV}")

    val = pd.read_csv(VALIDATION_CSV, dtype={"run_id": str, "config_id": str})
    if len(val) != 5:
        raise RuntimeError(f"Validation CSV must contain 5 rows, got {len(val)}")

    by_id = {str(r["run_id"]): r for _, r in val.iterrows()}

    for s in specs:
        run_id = s.run_id()
        if run_id not in by_id:
            raise RuntimeError(f"Missing validation row for {run_id}")

        row = by_id[run_id]
        if str(row["status"]) != "completed":
            raise RuntimeError(f"{run_id} validation status is not completed")
        if str(row["config_id"]) != EXPECTED_CONFIG_ID:
            raise RuntimeError(f"{run_id} has wrong config_id")

        ckpt = CHECKPOINTS / f"{run_id}.pt"
        if not ckpt.exists():
            raise RuntimeError(f"Missing checkpoint {ckpt}")

    if TEST_CSV.exists():
        raise RuntimeError(
            f"{TEST_CSV} already exists. Refusing to evaluate test again."
        )

    return val


def main():
    ap = argparse.ArgumentParser(
        description="One-shot final V2 test evaluation of the frozen 5-seed model."
    )
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--device", choices=["cpu", "cuda"], default="cuda")
    args = ap.parse_args()

    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable")

    specs = load_specs()
    validation = preflight(specs)

    print("FINAL TEST PREFLIGHT PASS")
    print(f"config_id: {EXPECTED_CONFIG_ID}")
    print("seeds: 0,1,2,3,4")
    print("checkpoints: 5/5")
    print("validation rows: 5/5 completed")
    print("test output: absent")

    if not args.execute:
        print("DRY RUN ONLY. Test set remains sealed.")
        print("Pass --execute only for the single final test evaluation.")
        return 0

    universe = load_universe()
    assert_no_ddi_features(universe.drugs, "drugs.parquet")

    split = load_frozen_split(universe, specs[0].scheme, specs[0].split_seed)
    drug_ids = list(universe.drugs["drugbank_id"])
    bundle, _ = resolve_biology(specs[0], drug_ids)
    mol_graphs = build_mol_graphs(
        list(universe.drugs["name"]),
        list(universe.drugs["smiles"]),
    )

    validation_by_id = {
        str(r["run_id"]): r for _, r in validation.iterrows()
    }

    results = []

    for s in specs:
        trainer = V2Trainer(
            s,
            universe,
            split,
            bundle,
            mol_graphs,
            mode=EvaluationMode.WITH_TEST,
            dataset=None,
            device=args.device,
        )

        ckpt = CHECKPOINTS / f"{s.run_id()}.pt"
        blob = torch.load(ckpt, map_location="cpu", weights_only=False)

        if blob.get("run_id") != s.run_id():
            raise RuntimeError(f"Checkpoint run_id mismatch for seed {s.seed}")

        if "model_state" not in blob:
            raise RuntimeError(f"Best model_state missing for seed {s.seed}")

        trainer.model.load_state_dict(blob["model_state"])

        # Recheck validation from the frozen best checkpoint before reading test.
        vm = trainer.validation_metrics()
        recorded_val = float(validation_by_id[s.run_id()]["val_auprc"])
        if abs(vm["val_auprc"] - recorded_val) > 1e-9:
            raise RuntimeError(
                f"Validation mismatch seed {s.seed}: "
                f"{vm['val_auprc']} vs {recorded_val}"
            )

        tm = trainer.test_metrics()

        results.append({
            "run_id": s.run_id(),
            "config_id": s.config_id(),
            "seed": s.seed,
            "checkpoint_sha256": sha256(ckpt),
            "val_auprc_recheck": vm["val_auprc"],
            **tm,
        })

    git_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()

    evaluated_at = datetime.now(timezone.utc).isoformat()

    for row in results:
        row["git_commit_before_test"] = git_commit
        row["evaluated_at_utc"] = evaluated_at

    out = pd.DataFrame(results).sort_values("seed")

    tmp = TEST_CSV.with_suffix(".csv.tmp")
    out.to_csv(tmp, index=False)
    os.replace(tmp, TEST_CSV)

    print("\nFINAL TEST COMPLETE — 5/5 seeds")
    print(out[
        ["seed", "test_auprc", "test_auroc", "test_brier", "test_ece"]
    ].to_string(index=False))

    print(
        f"\nAUPRC mean={out['test_auprc'].mean():.6f} "
        f"std={out['test_auprc'].std(ddof=1):.6f}"
    )
    print(f"wrote {TEST_CSV}")
    print("Frozen configuration must not be changed based on these results.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
