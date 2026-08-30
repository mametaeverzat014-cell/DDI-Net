#!/usr/bin/env python3
"""
Run ONE V2 BIO-GINE configuration. Validation only unless told otherwise.

    python scripts/run_v2.py --ablation M4 --biology true --seed 0 \
        --max-epochs 3 --tag SMOKE_ONLY

WHAT THIS SCRIPT WILL NOT DO
-----------------------------
It will not touch the test set unless ``--evaluation-mode with_test`` is passed
explicitly, and that mode is reserved for the single final evaluation after the
configuration is frozen (docs/V2_PREREGISTRATION.md section 10.3). In the
default ``validation_only`` mode the test buckets are removed before negatives
are sampled: no test negative is drawn, no test label enters a tensor, and
``predict_test`` raises :class:`TestSetSealed`.

It will not select hyperparameters. It runs the configuration it is given and
writes validation metrics. Selection is the grid runner's job and reads
validation only.

RESUME
------
The run id is a hash of the configuration, not a row number. If a checkpoint for
this run id exists and ``--resume`` is passed, training continues from it and
the results file is updated in place rather than gaining a second row for the
same run. That matters because this project has already lost two long runs to
container restarts.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402
import torch  # noqa: E402

from ddinet.data.v2_dataset import (  # noqa: E402
    assert_no_ddi_features, load_frozen_split, load_universe,
)
from ddinet.features.molgraph import build_mol_graphs  # noqa: E402
from ddinet.training.v2_trainer import (  # noqa: E402
    EvaluationMode, V2RunSpec, V2Trainer, resolve_biology,
)

REPORTS = ROOT / "reports" / "v2_grid"
CHECKPOINTS = ROOT / "reports" / "v2_checkpoints"

#: The validation-grid schema. No ``test_*`` column exists, and
#: ``test_result_columns_are_absent`` asserts it - a schema is only a guarantee
#: if something checks it.
RESULT_COLUMNS: tuple[str, ...] = (
    "run_id", "config_id", "seed", "split", "split_seed", "model", "ablation",
    "biology_source", "aggregation", "bio_dim", "dropout_bio", "dropout_pair",
    "lr", "batch_size", "n_parameters", "best_check", "best_optimizer_step",
    "optimizer_steps", "effective_epochs", "steps_per_epoch", "checks_run",
    "stopped_by",
    "val_auprc", "val_auroc", "val_brier", "val_ece", "val_n", "val_prevalence",
    "runtime_s", "status", "tag",
)


def describe_sibling_checkpoints(spec, checkpoint_dir: Path) -> list[str]:
    """Checkpoints whose spec differs from this one in only a field or two.

    Exists so that "--resume found nothing" comes with the reason. Comparing
    identity dictionaries rather than guessing from filenames: the filename is a
    hash and carries no information about what changed.
    """
    notes: list[str] = []
    if not checkpoint_dir.exists():
        return notes
    mine = spec.identity()
    for manifest_path in sorted(checkpoint_dir.glob("*.manifest.json")):
        try:
            other = json.loads(manifest_path.read_text()).get("hyperparameters", {})
        except (OSError, json.JSONDecodeError):
            continue
        differing = {
            k: (other.get(k), v) for k, v in mine.items()
            if k in other and other[k] != v
        }
        if differing and len(differing) <= 2:
            shown = ", ".join(f"{k}: {was!r} -> {now!r}"
                              for k, (was, now) in sorted(differing.items()))
            notes.append(
                f"{manifest_path.stem.replace('.manifest', '')} is the same run "
                f"except {shown}"
            )
    return notes


def build_spec(args) -> V2RunSpec:
    return V2RunSpec(
        ablation=args.ablation,
        biology_source=args.biology,
        aggregation=args.aggregation,
        scheme=args.scheme,
        split_seed=args.split_seed,
        negatives=args.negatives,
        eval_negative_seed=args.eval_negative_seed,
        bio_dim=args.bio_dim,
        dropout_bio=args.dropout_bio,
        dropout_pair=args.dropout_pair,
        lr=args.lr,
        batch_size=args.batch_size,
        max_optimizer_steps=args.max_optimizer_steps,
        validation_interval_steps=args.validation_interval_steps,
        patience_checks=args.patience_checks,
        seed=args.seed,
    )


def result_row(spec: V2RunSpec, trainer: V2Trainer, metrics: dict,
               status: str, tag: str) -> dict:
    return {
        "run_id": spec.run_id(),
        "config_id": spec.config_id(),
        "seed": spec.seed,
        "split": spec.scheme,
        "split_seed": spec.split_seed,
        "model": spec.model,
        "ablation": spec.ablation,
        "biology_source": spec.biology_source,
        "aggregation": spec.aggregation,
        "bio_dim": spec.bio_dim,
        "dropout_bio": spec.dropout_bio,
        "dropout_pair": spec.dropout_pair,
        "lr": spec.lr,
        "batch_size": spec.batch_size,
        "n_parameters": trainer.model.n_parameters(),
        "best_check": trainer.history.best_check,
        "best_optimizer_step": trainer._best_optimizer_step,
        "optimizer_steps": trainer.history.optimizer_steps,
        "effective_epochs": round(trainer.history.effective_epochs, 3),
        "steps_per_epoch": trainer.history.steps_per_epoch,
        "checks_run": trainer.history.checks_run,
        "stopped_by": trainer.history.stopped_by,
        "val_auprc": metrics.get("val_auprc"),
        "val_auroc": metrics.get("val_auroc"),
        "val_brier": metrics.get("val_brier"),
        "val_ece": metrics.get("val_ece"),
        "val_n": metrics.get("val_n"),
        "val_prevalence": metrics.get("val_prevalence"),
        "runtime_s": round(trainer.history.wall_time_s, 1),
        "status": status,
        "tag": tag,
    }


def upsert_row(path: Path, row: dict) -> pd.DataFrame:
    """Write one row, replacing any existing row with the same run id.

    Replace rather than append: a resumed run is the same run, and a second row
    for it would be counted twice by any aggregation. The run id is what makes
    "the same run" decidable without comparing every column.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=RESULT_COLUMNS)
    frame = frame[frame["run_id"] != row["run_id"]] if len(frame) else frame
    frame = pd.concat([frame, pd.DataFrame([row])], ignore_index=True)
    frame = frame[list(RESULT_COLUMNS)]
    frame.to_csv(path, index=False)
    return frame


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ablation", default="M4", choices=["M0", "M1", "M2", "M3", "M4"])
    ap.add_argument("--biology", default="true", choices=["true", "shuffled"],
                    help="'shuffled' uses the FROZEN CONTROL F artefact")
    ap.add_argument("--aggregation", default="mean", choices=["mean", "sum"],
                    help="'sum' is CONTROL C; never selected on validation")
    ap.add_argument("--scheme", default="drug", choices=["drug", "scaffold"])
    ap.add_argument("--split-seed", type=int, default=0)
    ap.add_argument("--negatives", default="degree_matched",
                    choices=["degree_matched", "uniform"])
    ap.add_argument("--eval-negative-seed", type=int, default=0)
    ap.add_argument("--bio-dim", type=int, default=64)
    ap.add_argument("--dropout-bio", type=float, default=0.1)
    ap.add_argument("--dropout-pair", type=float, default=0.1)
    ap.add_argument("--lr", type=float, default=1.0e-3)
    ap.add_argument("--batch-size", type=int, default=256)
    # FROZEN budget, configs/v2_budget_frozen.yaml. Denominated in optimiser
    # steps so batch size cannot buy extra optimisation, and validated on a step
    # interval so it cannot buy extra checkpoint-selection opportunities either.
    ap.add_argument("--max-optimizer-steps", type=int, default=21960)
    ap.add_argument("--validation-interval-steps", type=int, default=366)
    ap.add_argument("--patience-checks", type=int, default=30)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--evaluation-mode", default="validation_only",
                    choices=["validation_only", "with_test"],
                    help="with_test is for the single final evaluation only")
    ap.add_argument("--results", default=str(REPORTS / "v2_validation_grid.csv"))
    ap.add_argument("--checkpoint-dir", default=str(CHECKPOINTS))
    ap.add_argument("--checkpoint-every", type=int, default=5,
                    help="validation checks between periodic checkpoints; a run "
                         "killed mid-training must not start over")
    ap.add_argument("--resume", action="store_true",
                    help="continue from this run id's checkpoint if it exists")
    ap.add_argument("--curves", default="",
                    help="CSV to append the per-epoch convergence curve to")
    ap.add_argument("--tag", default="",
                    help="free-text label, e.g. SMOKE_ONLY")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    torch.set_num_threads(args.threads)
    spec = build_spec(args)
    mode = EvaluationMode(args.evaluation_mode)

    universe = load_universe()
    assert_no_ddi_features(universe.drugs, "drugs.parquet")
    split = load_frozen_split(universe, spec.scheme, spec.split_seed)
    bundle, bio_provenance = resolve_biology(spec, list(universe.drugs["drugbank_id"]))
    mol_graphs = build_mol_graphs(
        list(universe.drugs["name"]), list(universe.drugs["smiles"])
    )

    print(f"run_id   {spec.run_id()}   config_id {spec.config_id()}")
    print(f"model    BIO-GINE {spec.ablation}, biology={spec.biology_source}, "
          f"agg={spec.aggregation}")
    print(f"split    {spec.scheme} seed {spec.split_seed} | negatives "
          f"{spec.negatives} (train seed {spec.seed}, eval seed "
          f"{spec.eval_negative_seed})")
    print(f"mode     {mode.value}")
    if args.tag:
        print(f"tag      {args.tag}")

    trainer = V2Trainer(spec, universe, split, bundle, mol_graphs,
                        mode=mode, dataset=None)
    print(f"params   {trainer.model.n_parameters():,}")
    print(f"pairs    train {len(trainer._train['labels']):,} | "
          f"val {len(trainer._val['labels']):,}")
    print(f"budget   {spec.max_optimizer_steps:,} steps = "
          f"{spec.max_optimizer_steps/trainer._steps_per_epoch:.0f} epochs at "
          f"batch {spec.batch_size} ({trainer._steps_per_epoch} steps/epoch), "
          f"{trainer._total_checks} validation checks")

    ckpt_path = Path(args.checkpoint_dir) / f"{spec.run_id()}.pt"
    if args.resume:
        if ckpt_path.exists():
            trainer.load_checkpoint(ckpt_path)
            # Report the position in optimizer steps: that is the unit the
            # budget is denominated in, and the attribute that used to be
            # printed here (_start_epoch) stopped existing when training became
            # step-native. Resume is what protects a multi-day grid against an
            # interruption, so a crash on this line costs far more than the line.
            print(f"resumed  at step {trainer.history.optimizer_steps:,}/"
                  f"{spec.max_optimizer_steps:,} "
                  f"(pass {trainer._start_pass}, "
                  f"check {trainer.history.checks_run}/{trainer._total_checks}, "
                  f"best val AUPRC {trainer.history.best_val_auprc:.4f})")
        else:
            # Never resume silently-not-resuming. --resume was asked for, so a
            # fresh start is a surprise and has to say so. The common cause is
            # a changed identity field: max_optimizer_steps in particular looks
            # like a budget knob but sets T_max of the cosine schedule, so a run
            # with a different cap follows a different learning-rate trajectory
            # and is genuinely a different run, not a longer one.
            print(f"resume   NO checkpoint for run_id {spec.run_id()} - "
                  f"starting from scratch")
            for sibling in describe_sibling_checkpoints(spec, Path(args.checkpoint_dir)):
                print(f"         note: {sibling}")

    history = trainer.fit(verbose=args.verbose, checkpoint_path=ckpt_path,
                          checkpoint_every_checks=args.checkpoint_every)
    print(f"trained  {history.summary()}")

    metrics = trainer.validation_metrics()
    checkpoint_hash = trainer.save_checkpoint(ckpt_path)

    manifest = trainer.manifest(checkpoint_hash=checkpoint_hash,
                                extra={"biology": bio_provenance, "tag": args.tag})
    manifest_path = Path(args.checkpoint_dir) / f"{spec.run_id()}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str))

    # The raw per-epoch curve, one row per validation check. Written separately
    # from the results row because a single best-epoch number cannot show
    # whether a run was still improving when its budget ran out - which is the
    # only question a budget study can answer.
    if args.curves:
        curve = pd.DataFrame(trainer.history.epoch_records)
        curve.insert(0, "run_id", spec.run_id())
        curve.insert(1, "seed", spec.seed)
        curve.insert(2, "batch_size", spec.batch_size)
        curve.insert(3, "lr", spec.lr)
        curve.insert(4, "config_id", spec.config_id())
        curve_path = Path(args.curves)
        curve_path.parent.mkdir(parents=True, exist_ok=True)
        if curve_path.exists():
            existing = pd.read_csv(curve_path)
            existing = existing[existing["run_id"] != spec.run_id()]
            curve = pd.concat([existing, curve], ignore_index=True)
        curve.to_csv(curve_path, index=False)
        print(f"         {curve_path}")

    row = result_row(spec, trainer, metrics, status="completed", tag=args.tag)
    upsert_row(Path(args.results), row)

    print("validation " + " ".join(
        f"{k.replace('val_', '')}={v:.4f}" if isinstance(v, float) else f"{k}={v}"
        for k, v in metrics.items()))
    print(f"wrote    {args.results}\n         {manifest_path}")
    if args.tag == "SMOKE_ONLY":
        print("\nSMOKE_ONLY: these numbers are a pipeline check, not a result. "
              "Do not compare them to any model.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
