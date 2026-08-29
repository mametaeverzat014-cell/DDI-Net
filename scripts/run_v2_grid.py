#!/usr/bin/env python3
"""
Enumerate the preregistered V2 validation grid. Does NOT run it without --execute.

    python scripts/run_v2_grid.py                 # enumerate and stop
    python scripts/run_v2_grid.py --show 5        # ... and print five rows
    python scripts/run_v2_grid.py --execute       # only with explicit approval

WHY ENUMERATION IS A SEPARATE STEP
-----------------------------------
The grid is 32 configurations x 3 seeds = 96 runs. Two things have to be true
before any of them starts, and both are cheap to check and expensive to
discover afterwards:

  1. the enumeration must match the preregistration exactly. The grid is read
     from ``configs/v2_preregistered.yaml``, never hard-coded here, and the
     counts are checked against the ``n_configurations`` the config itself
     declares. A mismatch stops the script rather than being reconciled by
     quietly editing one of them;
  2. every run must be identified by what it is. ``run_id`` hashes the
     configuration, so an interrupted grid resumes precisely - this project has
     already lost two long runs to container restarts, and a grid keyed by row
     position would have restarted from zero.

THE GRID SELECTS ON VALIDATION AND NOTHING ELSE
-------------------------------------------------
Every run is launched in ``validation_only`` mode, in which the test buckets are
removed before negatives are sampled. The results table has no ``test_*``
column, and ``tests/test_v2_runner.py`` asserts that. Test is touched exactly
once, after the winning configuration is frozen (docs/V2_PREREGISTRATION.md
section 10.3).
"""

from __future__ import annotations

import argparse
import itertools
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from ddinet.training.v2_trainer import V2RunSpec  # noqa: E402

CONFIG = ROOT / "configs" / "v2_preregistered.yaml"
RESULTS = ROOT / "reports" / "v2_grid" / "v2_validation_grid.csv"

#: Grid axis -> V2RunSpec field. Explicit so a renamed config key fails loudly
#: instead of silently dropping an axis and running a smaller grid.
AXIS_TO_FIELD: dict[str, str] = {
    "bio_dim": "bio_dim",
    "dropout_bio": "dropout_bio",
    "dropout_pair": "dropout_pair",
    "lr": "lr",
    "batch_size": "batch_size",
}


def load_grid(config_path: Path = CONFIG) -> dict:
    cfg = yaml.safe_load(config_path.read_text())
    search = cfg["hparam_search"]
    grid = search["grid"]
    unknown = sorted(set(grid) - set(AXIS_TO_FIELD))
    if unknown:
        raise ValueError(
            f"{config_path} declares grid axes this runner cannot set: {unknown}. "
            f"Add them to AXIS_TO_FIELD and to V2RunSpec rather than ignoring them."
        )
    return {
        "grid": grid,
        "declared_n_configurations": search.get("n_configurations"),
        "selection_seeds": list(search["selection_seeds"]),
        "final_seeds": list(search.get("final_seeds", [])),
        "fixed": search.get("fixed", {}),
        "selection_metric": search.get("selection_metric"),
        "primary_ablation": cfg["model"]["primary_ablation"],
        "primary_scheme": cfg["splits"]["hyperparameter_selection"]["scheme"],
        "primary_negatives": cfg["negative_sampling"]["primary"],
    }


def enumerate_configurations(spec_of: dict) -> list[dict]:
    """Full factorial over the declared axes, in a deterministic order.

    ``sorted(grid)`` so the enumeration order is a function of the axis names
    rather than of YAML ordering - it makes a partially completed grid's
    remaining work reproducible.
    """
    axes = sorted(spec_of["grid"])
    values = [spec_of["grid"][a] for a in axes]
    return [dict(zip(axes, combo)) for combo in itertools.product(*values)]


def build_specs(spec_of: dict, seeds: list[int] | None = None) -> list[V2RunSpec]:
    """One V2RunSpec per (configuration, seed)."""
    seeds = seeds if seeds is not None else spec_of["selection_seeds"]
    fixed = spec_of["fixed"]
    # The budget comes from the FROZEN amendment, not from hparam_search.fixed:
    # configs/v2_preregistered.yaml still records the superseded 400 epochs, and
    # it is deliberately left unedited so the original preregistration reads as
    # written. configs/v2_budget_frozen.yaml is what applies.
    budget = yaml.safe_load(
        (ROOT / "configs" / "v2_budget_frozen.yaml").read_text())["budget"]
    if budget["unit"] != "optimizer_steps":
        raise ValueError(f"frozen budget unit is {budget['unit']!r}, expected "
                         f"'optimizer_steps'")
    base = V2RunSpec(
        ablation=spec_of["primary_ablation"],
        scheme=spec_of["primary_scheme"],
        negatives=spec_of["primary_negatives"],
        max_optimizer_steps=int(budget["max_optimizer_steps"]),
        validation_interval_steps=int(budget["validation_interval_steps"]),
        patience_checks=int(budget["early_stopping_patience_checks"]),
        weight_decay=float(fixed.get("weight_decay", 1e-4)),
    )
    specs: list[V2RunSpec] = []
    for config in enumerate_configurations(spec_of):
        overrides = {AXIS_TO_FIELD[k]: v for k, v in config.items()}
        for seed in seeds:
            specs.append(replace(base, seed=seed, **overrides))
    return specs


def completed_run_ids(results: Path = RESULTS) -> set[str]:
    """Run ids already present with status 'completed'.

    Read from the results table rather than from checkpoint filenames: a
    checkpoint can exist for a run that crashed before writing its row, and
    resuming that one is exactly what should happen.
    """
    if not Path(results).exists():
        return set()
    frame = pd.read_csv(results)
    if "run_id" not in frame.columns:
        return set()
    if "status" in frame.columns:
        frame = frame[frame["status"] == "completed"]
    return set(frame["run_id"].astype(str))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(CONFIG))
    ap.add_argument("--results", default=str(RESULTS))
    ap.add_argument("--show", type=int, default=0,
                    help="print this many enumerated runs")
    ap.add_argument("--execute", action="store_true",
                    help="actually run the grid. Requires explicit approval.")
    args = ap.parse_args()

    spec_of = load_grid(Path(args.config))
    configs = enumerate_configurations(spec_of)
    seeds = spec_of["selection_seeds"]
    specs = build_specs(spec_of, seeds)

    print("=== V2 PREREGISTERED VALIDATION GRID ===")
    print(f"config file            {args.config}")
    print(f"axes                   " + ", ".join(
        f"{a}={spec_of['grid'][a]}" for a in sorted(spec_of["grid"])))
    print(f"number of configurations  {len(configs)}")
    print(f"number of seeds           {len(seeds)}  {seeds}")
    print(f"total expected runs       {len(specs)}")
    print(f"selection metric          {spec_of['selection_metric']}")
    print(f"primary ablation          {spec_of['primary_ablation']}")
    print(f"split / negatives         {spec_of['primary_scheme']} / "
          f"{spec_of['primary_negatives']}")
    print(f"evaluation mode           validation_only (test is not touched)")
    b = yaml.safe_load((ROOT / "configs" / "v2_budget_frozen.yaml").read_text())["budget"]
    print(f"budget (FROZEN)           {b['max_optimizer_steps']:,} optimiser steps, "
          f"validate every {b['validation_interval_steps']}, patience "
          f"{b['early_stopping_patience_checks']} checks")

    declared = spec_of["declared_n_configurations"]
    if declared is not None and declared != len(configs):
        print(f"\nSTOP: the config declares n_configurations={declared} but the "
              f"declared axes enumerate {len(configs)}.")
        print("Do not edit the config to make these agree. Report the "
              "discrepancy and stop.")
        return 1

    unique_ids = {s.run_id() for s in specs}
    if len(unique_ids) != len(specs):
        print(f"\nSTOP: {len(specs)} runs collapse to {len(unique_ids)} run ids. "
              f"Some axis is not part of the run identity.")
        return 1
    print(f"distinct run ids          {len(unique_ids)}  (no collisions)")

    done = completed_run_ids(Path(args.results))
    remaining = [s for s in specs if s.run_id() not in done]
    print(f"already completed         {len(specs) - len(remaining)}")
    print(f"remaining                 {len(remaining)}")

    if args.show:
        print("\nfirst runs:")
        for s in specs[: args.show]:
            print(f"  {s.run_id()}  bio_dim={s.bio_dim:3d} db={s.dropout_bio} "
                  f"dp={s.dropout_pair} lr={s.lr:g} bs={s.batch_size} seed={s.seed}")

    if not args.execute:
        print("\nEnumeration only. Pass --execute to run, and not before the "
              "runner report has been reviewed.")
        return 0

    print("\n--execute given: running the grid is not implemented in this "
          "phase. The runner is scripts/run_v2.py; wire it here only after "
          "explicit approval to start the grid.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
