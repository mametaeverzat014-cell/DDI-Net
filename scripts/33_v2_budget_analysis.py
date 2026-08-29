#!/usr/bin/env python3
"""
Read the budget-adequacy curves and apply the criteria fixed in the amendment.

    python scripts/33_v2_budget_analysis.py

WHAT THIS DOES AND DOES NOT DECIDE
------------------------------------
It applies criteria A, B and C exactly as written in
`docs/V2_PREREGISTRATION_AMENDMENT_BUDGET.md` section 4, which was committed
BEFORE any convergence curve existed (commit 92363b4). The thresholds are
constants here, not arguments: a threshold that can be passed on the command
line is a threshold that can be chosen after seeing the answer.

The script does not pick a budget. It reports whether a candidate cap satisfies
the rule, and the descriptive diagnostics the amendment asks for. Choosing the
budget is a written decision in the amendment, made on adequacy and fair compute
allocation - explicitly NOT on which option gives a better validation AUPRC.

It never reads a test metric. There is none to read: the pilot ran in
validation_only mode, where the test buckets are removed before negatives are
sampled.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

REPORTS = ROOT / "reports" / "v2_budget_adequacy"
CURVES = REPORTS / "budget_adequacy_curves.csv"
SUMMARY = REPORTS / "budget_adequacy_summary.json"
PLOT = REPORTS / "budget_adequacy_plot.png"

# -- the preregistered rule, as constants ---------------------------------
#: A: the best checkpoint must fall before the final 20% of the budget.
CRITERION_A_FRACTION = 0.80
#: B: absolute validation AUPRC improvement over the final 5 epochs.
CRITERION_B_WINDOW = 5
CRITERION_B_MAX_IMPROVEMENT = 0.005
#: C: OLS slope of validation AUPRC over the final 5 epochs, per epoch.
CRITERION_C_WINDOW = 5
CRITERION_C_MAX_SLOPE = 0.001
#: The extension ladder. 80 is a hard stop.
EXTENSION_LADDER: tuple[int, ...] = (40, 60, 80)


def improvement_over_last(curve: np.ndarray, window: int) -> float:
    """How much better the final ``window`` epochs got than where they started.

    ``max`` of the window rather than its last value: a curve that peaked
    mid-window and dipped back has still improved within it, and treating that
    as "no improvement" would call a still-moving run converged.
    """
    if len(curve) < window + 1:
        return float("nan")
    return float(np.max(curve[-window:]) - curve[-(window + 1)])


def trailing_slope(curve: np.ndarray, window: int) -> float:
    """OLS slope per epoch over the final ``window`` points."""
    if len(curve) < window:
        return float("nan")
    y = curve[-window:]
    x = np.arange(len(y), dtype=float)
    return float(np.polyfit(x, y, 1)[0])


def epoch_reaching_fraction(curve: np.ndarray, fraction: float) -> int:
    """First 1-based epoch whose value reaches ``fraction`` of the run's best."""
    target = fraction * float(np.max(curve))
    hits = np.nonzero(curve >= target)[0]
    return int(hits[0]) + 1 if len(hits) else -1


def analyse_seed(frame: pd.DataFrame, cap: int) -> dict:
    frame = frame.sort_values("epoch")
    curve = frame["val_auprc"].to_numpy(dtype=float)
    best_row = frame.loc[frame["val_auprc"].idxmax()]
    best_epoch = int(best_row["epoch"])

    out = {
        "seed": int(frame["seed"].iloc[0]),
        "run_id": str(frame["run_id"].iloc[0]),
        "epochs_run": int(frame["epoch"].max()),
        "cap": cap,
        "batch_size": int(frame["batch_size"].iloc[0]),
        "optimizer_steps_per_epoch": int(frame["optimizer_steps_this_epoch"].iloc[0]),
        "total_optimizer_steps": int(frame["cumulative_optimizer_steps"].max()),
        "best_epoch": best_epoch,
        "best_optimizer_step": int(best_row["cumulative_optimizer_steps"]),
        "best_val_auprc": float(best_row["val_auprc"]),
        "final_val_auprc": float(curve[-1]),
        "best_val_auroc": float(best_row["val_auroc"]),
        "best_val_brier": float(best_row["val_brier"]),
        "best_val_ece": float(best_row["val_ece"]),
        "improvement_last_3": improvement_over_last(curve, 3),
        "improvement_last_5": improvement_over_last(curve, 5),
        "improvement_last_10": improvement_over_last(curve, 10),
        "trailing_slope_last_5": trailing_slope(curve, CRITERION_C_WINDOW),
        "epoch_95pct_of_best": epoch_reaching_fraction(curve, 0.95),
        "epoch_99pct_of_best": epoch_reaching_fraction(curve, 0.99),
        "mean_epoch_runtime_s": float(frame["epoch_runtime_s"].mean()),
        "total_runtime_s": float(frame["epoch_runtime_s"].sum()),
    }
    out["criterion_A"] = bool(best_epoch <= CRITERION_A_FRACTION * cap)
    out["criterion_B"] = bool(out["improvement_last_5"] < CRITERION_B_MAX_IMPROVEMENT)
    out["criterion_C"] = bool(out["trailing_slope_last_5"] < CRITERION_C_MAX_SLOPE)
    return out


def next_cap(cap: int) -> int | None:
    for candidate in EXTENSION_LADDER:
        if candidate > cap:
            return candidate
    return None


def make_plot(curves: pd.DataFrame, per_seed: list[dict], path: Path) -> None:
    """Validation AUPRC against epoch and against optimiser step.

    Two panels because the whole point of the study is that the two axes are
    not interchangeable when batch size is a searched hyperparameter.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), constrained_layout=True)
    colours = {0: "#2166ac", 1: "#b2182b", 2: "#1a9850"}
    for seed, group in curves.groupby("seed"):
        group = group.sort_values("epoch")
        c = colours.get(int(seed), "#555555")
        axes[0].plot(group["epoch"], group["val_auprc"], marker="o", ms=3,
                     color=c, label=f"seed {seed}")
        axes[1].plot(group["cumulative_optimizer_steps"], group["val_auprc"],
                     marker="o", ms=3, color=c, label=f"seed {seed}")
    for record in per_seed:
        c = colours.get(record["seed"], "#555555")
        axes[0].axvline(record["best_epoch"], color=c, ls=":", lw=1, alpha=0.7)
    cap = per_seed[0]["cap"]
    axes[0].axvspan(CRITERION_A_FRACTION * cap, cap, color="#cccccc", alpha=0.35,
                    label="final 20% (criterion A)")
    axes[0].set_xlabel("epoch")
    axes[1].set_xlabel("cumulative optimiser steps")
    for ax in axes:
        ax.set_ylabel("validation AUPRC")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    fig.suptitle("BIO-GINE M4 budget adequacy - VALIDATION ONLY, slow grid corner "
                 "(lr 3e-4, bs 512, dropout 0.3/0.2)", fontsize=10)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> int:
    if not CURVES.exists():
        print(f"No curves at {CURVES}; run the pilot first.")
        return 1
    curves = pd.read_csv(CURVES)
    forbidden = [c for c in curves.columns if c.startswith("test_")]
    if forbidden:
        print(f"STOP: the curve file carries test columns {forbidden}.")
        return 1

    cap = int(curves["epoch"].max())
    per_seed = [analyse_seed(g, cap) for _, g in curves.groupby("seed")]

    print("=== V2 BUDGET ADEQUACY ===")
    print(f"cap under test           {cap} epochs")
    print(f"seeds                    {[r['seed'] for r in per_seed]}")
    print(f"optimiser steps / epoch  "
          f"{per_seed[0]['optimizer_steps_per_epoch']} (batch "
          f"{per_seed[0]['batch_size']})\n")

    for r in per_seed:
        print(f"-- seed {r['seed']} ({r['run_id']}) --")
        print(f"   best epoch                 {r['best_epoch']}  "
              f"(step {r['best_optimizer_step']:,})")
        print(f"   best val AUPRC             {r['best_val_auprc']:.4f}   "
              f"final {r['final_val_auprc']:.4f}")
        print(f"   val AUROC / Brier / ECE    {r['best_val_auroc']:.4f} / "
              f"{r['best_val_brier']:.4f} / {r['best_val_ece']:.4f}")
        print(f"   improvement last 3/5/10    {r['improvement_last_3']:+.4f} / "
              f"{r['improvement_last_5']:+.4f} / {r['improvement_last_10']:+.4f}")
        print(f"   trailing slope (last 5)    {r['trailing_slope_last_5']:+.5f} /epoch")
        print(f"   95% / 99% of best at epoch {r['epoch_95pct_of_best']} / "
              f"{r['epoch_99pct_of_best']}")
        print(f"   mean epoch runtime         {r['mean_epoch_runtime_s']:.1f} s")
        print(f"   A {'PASS' if r['criterion_A'] else 'FAIL'}   "
              f"B {'PASS' if r['criterion_B'] else 'FAIL'}   "
              f"C {'PASS' if r['criterion_C'] else 'FAIL'}\n")

    verdict = {
        "A": all(r["criterion_A"] for r in per_seed),
        "B": all(r["criterion_B"] for r in per_seed),
        "C": all(r["criterion_C"] for r in per_seed),
    }
    adequate = all(verdict.values())
    print("criterion A (best before final 20%)      "
          f"{'PASS' if verdict['A'] else 'FAIL'}")
    print(f"criterion B (last-5 improvement < {CRITERION_B_MAX_IMPROVEMENT})  "
          f"{'PASS' if verdict['B'] else 'FAIL'}")
    print(f"criterion C (last-5 slope < {CRITERION_C_MAX_SLOPE})        "
          f"{'PASS' if verdict['C'] else 'FAIL'}")
    print(f"\nBUDGET {cap} EPOCHS: {'ADEQUATE' if adequate else 'NOT ADEQUATE'}")

    extension = None
    if not adequate:
        extension = next_cap(cap)
        if extension is None:
            print("Cap is already at the hard stop of 80 epochs. Do not extend "
                  "further; report and hand the decision back.")
        else:
            print(f"Rule says: extend the SAME runs by resume to {extension} "
                  f"epochs. Do not invent a budget from the curve.")

    summary = {
        "cap_tested": cap,
        "adequate": adequate,
        "criteria": verdict,
        "thresholds": {
            "A_fraction": CRITERION_A_FRACTION,
            "B_window": CRITERION_B_WINDOW,
            "B_max_improvement": CRITERION_B_MAX_IMPROVEMENT,
            "C_window": CRITERION_C_WINDOW,
            "C_max_slope": CRITERION_C_MAX_SLOPE,
        },
        "extension_required": extension,
        "per_seed": per_seed,
        "test_metrics_present": False,
    }
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(summary, indent=2))
    try:
        make_plot(curves, per_seed, PLOT)
        print(f"\nwrote {SUMMARY}\n      {PLOT}")
    except Exception as exc:                       # matplotlib is optional
        print(f"\nwrote {SUMMARY}  (plot skipped: {exc})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
