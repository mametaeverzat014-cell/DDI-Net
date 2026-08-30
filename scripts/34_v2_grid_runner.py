#!/usr/bin/env python3
"""
Execute the frozen 32x3 V2 validation grid, survivably.

    python scripts/34_v2_grid_runner.py --execute

WHAT MAKES THIS SURVIVABLE
---------------------------
The grid is ~6.4 days on a container that has already restarted three times
mid-run. Everything here exists because of that:

  * a run is identified by a hash of its configuration, not by row position, so
    a restart resumes exactly the configurations it has not finished;
  * results are appended after EVERY run, never batched to the end;
  * a completed run is skipped; an incomplete one resumes from its latest
    checkpoint; a corrupt one is marked FAILED rather than counted as done;
  * progress is written to disk after every run so an outside observer can see
    the state without reading logs.

WHAT IT REFUSES TO DO
----------------------
Touch the test set. Every run is launched in validation_only mode, where the
test buckets are removed before negatives are sampled - there is no test label
in the process. The results table has no test column and
``verify_run`` fails a run that somehow produced one.

Select a configuration. Selection happens after all 96 runs, in a separate
script, on the preregistered metric. Nothing here reads the metric to decide
what to do next.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import pandas as pd  # noqa: E402

from ddinet.training.v2_trainer import V2RunSpec  # noqa: E402

GRID_DIR = ROOT / "reports" / "v2_grid"
RESULTS = GRID_DIR / "v2_validation_grid.csv"
CURVES = GRID_DIR / "v2_validation_curves.csv"
PROGRESS_JSON = GRID_DIR / "progress.json"
PROGRESS_MD = GRID_DIR / "GRID_PROGRESS.md"
CHECKPOINTS = ROOT / "reports" / "v2_checkpoints"

#: Every run in this grid must report these. A run that disagrees is not part
#: of the preregistered experiment and must not be counted as one.
REQUIRED_INVARIANTS = {
    "ablation": "M4",
    "biology_source": "true",
    "aggregation": "mean",
    "split": "drug",
    "model": "bio_gine",
}


def load_specs() -> list[V2RunSpec]:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_v2_grid", ROOT / "scripts" / "run_v2_grid.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_v2_grid"] = module
    spec.loader.exec_module(module)
    return module.build_specs(module.load_grid())


def verify_run(row: pd.Series, spec: V2RunSpec) -> tuple[bool, str]:
    """Integrity check for one completed run. Returns (ok, reason).

    Checked after the run rather than trusted, because a corrupt run that is
    silently counted as complete is worse than one that fails: it removes a
    configuration from the grid without removing it from the count.
    """
    if str(row.get("run_id")) != spec.run_id():
        return False, f"run_id {row.get('run_id')} != {spec.run_id()}"
    for column, expected in REQUIRED_INVARIANTS.items():
        actual = row.get(column)
        if str(actual) != expected:
            return False, f"{column}={actual!r}, expected {expected!r}"
    if int(row.get("seed", -1)) != spec.seed:
        return False, f"seed {row.get('seed')} != {spec.seed}"
    for column in row.index:
        if str(column).startswith("test_"):
            return False, f"result carries a test column: {column}"
    for metric in ("val_auprc", "val_auroc", "val_brier", "val_ece"):
        value = row.get(metric)
        if value is None or not pd.notna(value) or not float(value) == float(value):
            return False, f"{metric} is not finite: {value!r}"
        if not (0.0 <= float(value) <= 1.0):
            return False, f"{metric} out of range: {value}"
    if int(row.get("optimizer_steps", 0)) <= 0:
        return False, "no optimiser steps recorded"
    checkpoint = CHECKPOINTS / f"{spec.run_id()}.pt"
    if not checkpoint.exists():
        return False, "checkpoint missing"
    return True, ""


#: Columns compared as strings by verify_run(). They must be read back as
#: strings, not re-typed by pandas' inference. This is not cosmetic: every run
#: in this grid writes biology_source="true", so the whole column is the literal
#: "true" and read_csv infers it as bool. The value then compares as np.True_
#: against the expected "true" and every completed run is rejected as corrupt --
#: after paying its full training cost. Identifier columns are pinned for the
#: same reason: an all-digit run_id would be read back as an integer and a
#: leading zero would be lost.
STRING_COLUMNS = tuple(REQUIRED_INVARIANTS) + (
    "run_id", "config_id", "status", "stopped_by", "tag",
)


def completed_rows() -> pd.DataFrame:
    if not RESULTS.exists():
        return pd.DataFrame()
    # dtype is pinned only for the string columns. Numeric columns keep normal
    # inference, so a blank metric still arrives as NaN and is rejected by the
    # finiteness check rather than raising on float("").
    return pd.read_csv(RESULTS, dtype={c: str for c in STRING_COLUMNS})


def run_one(spec: V2RunSpec, verbose: bool) -> int:
    cmd = [
        sys.executable, "-u", str(ROOT / "scripts" / "run_v2.py"),
        "--ablation", spec.ablation,
        "--biology", spec.biology_source,
        "--aggregation", spec.aggregation,
        "--scheme", spec.scheme,
        "--split-seed", str(spec.split_seed),
        "--negatives", spec.negatives,
        "--eval-negative-seed", str(spec.eval_negative_seed),
        "--bio-dim", str(spec.bio_dim),
        "--dropout-bio", str(spec.dropout_bio),
        "--dropout-pair", str(spec.dropout_pair),
        "--lr", repr(spec.lr),
        "--batch-size", str(spec.batch_size),
        "--max-optimizer-steps", str(spec.max_optimizer_steps),
        "--validation-interval-steps", str(spec.validation_interval_steps),
        "--patience-checks", str(spec.patience_checks),
        "--seed", str(spec.seed),
        "--evaluation-mode", "validation_only",
        "--results", str(RESULTS),
        "--curves", str(CURVES),
        "--checkpoint-every", "5",
        "--threads", "2",
        "--resume",
        "--tag", "V2_GRID",
    ]
    if verbose:
        cmd.append("--verbose")
    return subprocess.run(cmd, cwd=ROOT).returncode


def write_progress(specs: list[V2RunSpec], done: set[str], failed: dict,
                   running: str | None, started: float) -> None:
    elapsed = time.time() - started
    n_done, n_total = len(done), len(specs)
    rate = elapsed / n_done if n_done else 0.0
    remaining = rate * (n_total - n_done) if n_done else 0.0
    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "completed": n_done,
        "total": n_total,
        "failed": len(failed),
        "failed_runs": failed,
        "currently_running": running,
        "elapsed_hours": round(elapsed / 3600, 2),
        "estimated_remaining_hours": round(remaining / 3600, 2),
        "mean_hours_per_run": round(rate / 3600, 3),
        "test_evaluated": False,
    }
    PROGRESS_JSON.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_JSON.write_text(json.dumps(payload, indent=2))

    bar_width = 40
    filled = int(bar_width * n_done / n_total) if n_total else 0
    PROGRESS_MD.write_text(f"""# V2 validation grid — progress

**Updated:** {payload['timestamp_utc']}

`[{'#' * filled}{'.' * (bar_width - filled)}]` **{n_done} / {n_total}**

| | |
|---|---|
| Completed | {n_done} |
| Failed | {len(failed)} |
| Currently running | {running or '—'} |
| Elapsed | {payload['elapsed_hours']:.2f} h |
| Estimated remaining | {payload['estimated_remaining_hours']:.2f} h |
| Mean per run | {payload['mean_hours_per_run']:.3f} h |

**Test set:** sealed. Every run is `validation_only`; the test buckets are
removed before negatives are sampled, so no test label exists in any run's
process. No test metric has been computed.

**No scientific interpretation while the grid is incomplete.** Intermediate
validation metrics are recorded but must not be used to modify the search
(docs/V2_PREREGISTRATION.md section 10.4).

{"## Failed runs" + chr(10) + chr(10) + chr(10).join(f"- `{k}`: {v}" for k, v in failed.items()) if failed else ""}
""")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--execute", action="store_true",
                    help="actually run; without it the grid is only enumerated")
    ap.add_argument("--limit", type=int, default=0,
                    help="stop after this many runs (0 = all)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    specs = load_specs()
    if len(specs) != 96:
        print(f"STOP: expected 96 runs, enumerated {len(specs)}.")
        return 1
    if len({s.run_id() for s in specs}) != 96:
        print("STOP: run_id collisions in the enumeration.")
        return 1
    if len({s.config_id() for s in specs}) != 32:
        print(f"STOP: expected 32 configs, got "
              f"{len({s.config_id() for s in specs})}.")
        return 1
    print(f"grid: 32 configs x 3 seeds = {len(specs)} runs, no collisions")

    if not args.execute:
        print("Enumeration only. Pass --execute to run.")
        return 0

    started = time.time()
    done: set[str] = set()
    failed: dict[str, str] = {}

    rows = completed_rows()
    if len(rows) and "run_id" in rows.columns:
        by_id = {str(r["run_id"]): r for _, r in rows.iterrows()}
        for spec in specs:
            row = by_id.get(spec.run_id())
            if row is None:
                continue
            ok, reason = verify_run(row, spec)
            if ok and str(row.get("status")) == "completed":
                done.add(spec.run_id())
            elif not ok:
                failed[spec.run_id()] = f"pre-existing row rejected: {reason}"
        print(f"resuming: {len(done)} already valid, {len(failed)} rejected")

    write_progress(specs, done, failed, None, started)

    ran = 0
    for spec in specs:
        if spec.run_id() in done:
            continue
        if args.limit and ran >= args.limit:
            break
        label = (f"{spec.run_id()} bio{spec.bio_dim} db{spec.dropout_bio} "
                 f"dp{spec.dropout_pair} lr{spec.lr:g} bs{spec.batch_size} "
                 f"seed{spec.seed}")
        print(f"\n[{len(done)+1}/{len(specs)}] {label}", flush=True)
        write_progress(specs, done, failed, label, started)

        code = run_one(spec, args.verbose)
        ran += 1
        rows = completed_rows()
        row = None
        if len(rows) and "run_id" in rows.columns:
            match = rows[rows["run_id"].astype(str) == spec.run_id()]
            row = match.iloc[-1] if len(match) else None

        if code != 0 or row is None:
            failed[spec.run_id()] = f"exit {code}, row {'absent' if row is None else 'present'}"
            print(f"  FAILED: {failed[spec.run_id()]}", flush=True)
        else:
            ok, reason = verify_run(row, spec)
            if ok:
                done.add(spec.run_id())
                print(f"  ok  val_auprc {float(row['val_auprc']):.4f}  "
                      f"steps {int(row['optimizer_steps']):,}  "
                      f"{float(row['runtime_s'])/3600:.2f} h", flush=True)
            else:
                failed[spec.run_id()] = reason
                print(f"  FAILED integrity: {reason}", flush=True)
        write_progress(specs, done, failed, None, started)

    print(f"\ngrid stopped: {len(done)}/{len(specs)} complete, "
          f"{len(failed)} failed, {(time.time()-started)/3600:.2f} h elapsed")
    return 0 if len(done) == len(specs) else 2


if __name__ == "__main__":
    raise SystemExit(main())
