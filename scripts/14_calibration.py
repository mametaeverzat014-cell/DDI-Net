#!/usr/bin/env python3
"""
Calibration of every baseline on the honest configuration (drug + degree_matched).

    python scripts/14_calibration.py

Writes reports/calibration.csv, reports/calibration.md and
reports/figures/calibration_reliability.png.

WHY THIS IS NOT A SUPPLEMENTARY METRIC
---------------------------------------
AUPRC and AUC-ROC are invariant to any monotone transformation of the scores, so
they cannot distinguish a model whose probabilities mean something from one that
merely orders pairs correctly. This project's stated justification is that a
clinician needs a trustworthy probability, not a ranking - so calibration is the
metric that tests the project's own claim about why the work is useful.

The configuration is drug + degree_matched: the split and negative scheme that
survived Phase A as the honest ones. Calibrating on the leaky configuration
would measure how well a model expresses confidence about a task it is partly
memorising.

Hyperparameters are read from the Phase A tuning log, so the models here are the
same ones the headline table reports - not refits with different settings.
Temperature is fitted on validation and applied unchanged to test.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ddinet.data import leakage, negatives as neg, split as split_mod, tdc_drugbank as tdc
from ddinet.eval.calibration import evaluate_calibration, reliability_curve
from ddinet.eval.metrics import format_ci
from ddinet.features.pair_encoding import build_fingerprint_matrix, encode_dataset
from ddinet.models.classical import PairBatch, build_model, training_degree

REPORTS = Path(__file__).resolve().parents[1] / "reports"
FIGURES = REPORTS / "figures"

SCHEME, STRATEGY = "drug", "degree_matched"
SEEDS = [0, 1, 2, 3, 4]
MODELS = [
    ("degree_only", "none"),
    ("logreg", "concat"), ("logreg", "symmetric"),
    ("random_forest", "concat"), ("random_forest", "symmetric"),
]

COLOURS = {"degree_only": "#2a78d6", "logreg": "#eb6834", "random_forest": "#1baf7a"}
LABELS = {"degree_only": "degree-only", "logreg": "logistic regression",
          "random_forest": "random forest"}
SURFACE, TEXT_PRIMARY, TEXT_SECONDARY, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e3e2df"


def pooled(dataset: pd.DataFrame, prefix: str) -> pd.DataFrame:
    return dataset.loc[dataset["bucket"].str.startswith(prefix)].reset_index(drop=True)


def load_tuned() -> dict[tuple, dict]:
    path = REPORTS / "phase_a_tuning.json"
    if not path.exists():
        return {}
    return {
        (e["scheme"], e["negatives"], e["encoding"], e["model"]): e["chosen"]
        for e in json.loads(path.read_text())
    }


def main() -> int:
    tuned = load_tuned()
    drugs, pairs, drop_report = tdc.load_modelling_data()
    print(drop_report.summary())
    drug_names = list(drugs["name"])
    positive_keys = set(pairs["pair_key"])
    fingerprints = build_fingerprint_matrix(drug_names, list(drugs["smiles"]))

    rows: list[dict] = []
    curves: dict[tuple[str, str], list] = {}

    for seed in SEEDS:
        print(f"\n--- seed {seed} ---", flush=True)
        split = split_mod.build_any(SCHEME, drugs, pairs, seed=seed)
        leakage.verify(split)
        dataset, _ = neg.build_dataset(
            split, drug_names, positive_keys,
            neg.NegativeSamplingConfig(strategy=STRATEGY, ratio=1.0, seed=seed),
        )
        neg.verify_no_negative_is_positive(dataset, positive_keys)
        train_df, val_df, test_df = (pooled(dataset, p) for p in ("train", "val", "test"))

        all_train = pd.concat(
            [df for name, df in split.buckets.items() if name.startswith("train")],
            ignore_index=True)
        degree = training_degree(all_train)

        encoded: dict[str, tuple] = {}
        for encoding in ("concat", "symmetric"):
            enc = dict(encoding=encoding, seed=seed)
            encoded[encoding] = (
                encode_dataset(fingerprints, train_df, **enc),
                encode_dataset(fingerprints, val_df, **enc),
                encode_dataset(fingerprints, test_df, **enc),
            )

        for model_name, encoding in MODELS:
            params = tuned.get((SCHEME, STRATEGY, encoding, model_name), {})
            if encoding == "none":
                train_b = PairBatch.from_frame(train_df)
                val_b = PairBatch.from_frame(val_df)
                test_b = PairBatch.from_frame(test_df)
            else:
                Xtr, Xva, Xte = encoded[encoding]
                train_b = PairBatch.from_frame(train_df, Xtr)
                val_b = PairBatch.from_frame(val_df, Xva)
                test_b = PairBatch.from_frame(test_df, Xte)

            t0 = time.time()
            model = build_model(model_name, params, degree=degree, seed=seed).fit(train_b)
            p_val, p_test = model.predict_proba(val_b), model.predict_proba(test_b)
            label = model_name + ("" if encoding == "none" else f"[{encoding}]")
            report, p_scaled, scaler = evaluate_calibration(
                label, val_b.y, p_val, test_b.y, p_test)
            rows.append({"seed": seed, "model": model_name, "encoding": encoding,
                         **report.to_dict(), "fit_seconds": round(time.time() - t0, 1)})
            print("  " + report.summary(), flush=True)

            if seed == SEEDS[0] and encoding in ("none", "symmetric"):
                curves[(model_name, "raw")] = reliability_curve(
                    test_b.y, p_test, n_bins=12, strategy="quantile")
                curves[(model_name, "scaled")] = reliability_curve(
                    test_b.y, p_scaled, n_bins=12, strategy="quantile")

        pd.DataFrame(rows).to_csv(REPORTS / "calibration.csv", index=False)

    results = pd.DataFrame(rows)
    _write_report(results)
    _plot(curves, results)
    return 0


def _write_report(results: pd.DataFrame) -> None:
    lines: list[str] = []
    w = lines.append
    w("# Calibration - drug-level split, degree-matched negatives\n")
    w("Generated by `scripts/14_calibration.py`. Five seeds, mean +/- 95% CI.\n")
    w("AUPRC and AUC-ROC are invariant to any monotone transformation of the "
      "scores, so they cannot tell a model whose probabilities mean something "
      "from one that merely ranks correctly. This project claims a clinician "
      "needs a trustworthy probability, so calibration is what tests that "
      "claim.\n")
    w("Temperature scaling is monotone and has one parameter: it cannot change "
      "any ranking metric and cannot overfit. It corrects global over- or "
      "under-confidence only. **If ECE stays high after scaling, the "
      "miscalibration is structural** and needs isotonic regression or a "
      "different model, not a better T.\n")
    w("Two binning schemes are reported because ECE depends on the binning. "
      "Equal-width bins flatter a model whose predictions are concentrated, "
      "since the sparse bins barely enter the weighted average; equal-mass "
      "(quantile) bins give every region of the score range the same weight. "
      "A gap between the two is itself diagnostic.\n")

    w("## Expected calibration error, quantile bins\n")
    w("| Model | Encoding | ECE raw | ECE after scaling | Temperature | Brier raw | Brier scaled |")
    w("|---|---|---|---|---|---|---|")
    for (model, encoding), grp in results.groupby(["model", "encoding"]):
        w(f"| {model} | {encoding} | {format_ci(grp['ece_quantile'], 4)} | "
          f"{format_ci(grp['ece_quantile_scaled'], 4)} | "
          f"{format_ci(grp['temperature'], 3)} | {format_ci(grp['brier'], 4)} | "
          f"{format_ci(grp['brier_scaled'], 4)} |")
    w("")
    w("## Equal-width bins, for comparison with published numbers\n")
    w("| Model | Encoding | ECE(uniform) raw | ECE(uniform) scaled | gap vs quantile |")
    w("|---|---|---|---|---|")
    for (model, encoding), grp in results.groupby(["model", "encoding"]):
        gap = grp["ece_quantile"].mean() - grp["ece_uniform"].mean()
        w(f"| {model} | {encoding} | {format_ci(grp['ece_uniform'], 4)} | "
          f"{format_ci(grp['ece_uniform_scaled'], 4)} | {gap:+.4f} |")
    w("")
    w("## Worst-bin error (MCE, quantile bins, bins of >= 30 predictions)\n")
    w("| Model | Encoding | MCE raw | MCE scaled |")
    w("|---|---|---|---|")
    for (model, encoding), grp in results.groupby(["model", "encoding"]):
        w(f"| {model} | {encoding} | {format_ci(grp['mce_quantile'], 4)} | "
          f"{format_ci(grp['mce_quantile_scaled'], 4)} |")
    w("")
    (REPORTS / "calibration.md").write_text("\n".join(lines))
    print(f"\nWrote {REPORTS/'calibration.md'}")


def _plot(curves: dict, results: pd.DataFrame) -> None:
    if not curves:
        return
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 5.2), sharex=True, sharey=True,
                             facecolor=SURFACE)
    for ax, state, title in zip(axes, ("raw", "scaled"),
                                ("Raw probabilities", "After temperature scaling")):
        ax.set_facecolor(SURFACE)
        # The diagonal is perfect calibration; every deviation from it is the
        # quantity being measured, so it is drawn first and recessive.
        ax.plot([0, 1], [0, 1], color=TEXT_SECONDARY, lw=1, ls=":", alpha=0.6, zorder=1)
        for model in ("degree_only", "logreg", "random_forest"):
            curve = curves.get((model, state))
            if curve is None:
                continue
            ax.plot(curve.mean_predicted, curve.observed_frequency,
                    color=COLOURS[model], lw=2, marker="o", markersize=8,
                    markeredgecolor=SURFACE, markeredgewidth=2, zorder=3)
        ax.set_title(title, fontsize=11, color=TEXT_PRIMARY, pad=10)
        ax.set_xlabel("Mean predicted probability", fontsize=10, color=TEXT_SECONDARY)
        ax.grid(color=GRID, lw=0.8, zorder=0)
        ax.set_axisbelow(True)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(GRID)
        ax.tick_params(colors=TEXT_SECONDARY, length=0)
    axes[0].set_ylabel("Observed frequency", fontsize=10, color=TEXT_PRIMARY)
    axes[0].text(0.04, 0.93, "above the line =\nunder-confident", fontsize=8,
                 color=TEXT_SECONDARY, va="top")
    axes[0].text(0.55, 0.10, "below the line =\nover-confident", fontsize=8,
                 color=TEXT_SECONDARY, va="bottom")

    handles = [plt.Line2D([], [], color=COLOURS[m], ls="none", marker="o",
                          markersize=9, markeredgecolor=SURFACE, markeredgewidth=2,
                          label=LABELS[m])
               for m in ("degree_only", "logreg", "random_forest")]
    handles.append(plt.Line2D([], [], color=TEXT_SECONDARY, lw=1, ls=":",
                              label="perfect calibration"))
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False,
               fontsize=9, labelcolor=TEXT_SECONDARY, bbox_to_anchor=(0.5, -0.01))
    fig.suptitle("Reliability on the honest configuration (drug split, degree-matched negatives)",
                 fontsize=12.5, color=TEXT_PRIMARY, y=0.99)
    fig.text(0.5, 0.915, "12 equal-mass bins, seed 0, symmetric pair encoding",
             ha="center", fontsize=9, color=TEXT_SECONDARY)
    fig.subplots_adjust(left=0.08, right=0.97, top=0.83, bottom=0.17, wspace=0.06)

    FIGURES.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "svg"):
        fig.savefig(FIGURES / f"calibration_reliability.{ext}", dpi=200,
                    facecolor=SURFACE, bbox_inches="tight")
    print(f"Wrote {FIGURES/'calibration_reliability.png'}")


if __name__ == "__main__":
    raise SystemExit(main())
