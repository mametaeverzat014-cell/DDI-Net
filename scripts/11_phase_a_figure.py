#!/usr/bin/env python3
"""
The Phase A headline figure: how metrics fall as the split is tightened.

    python scripts/11_phase_a_figure.py

Writes reports/figures/phase_a_degradation.png and .svg.

DESIGN NOTES
------------
*Form.* The data's job is change across an ORDERED axis - split schemes ranked
by how much leakage they permit - so a slope chart is the right form: the
degradation is the slope, read directly rather than inferred by comparing bar
heights.

*Encoding.* Colour carries the model (three hues, fixed order, never cycled) and
line style carries the pair encoding (solid = symmetric, dashed = concat). Two
channels for two dimensions, so no dimension is left to the reader's memory.
degree-only has no encoding and appears once, solid.

*One y-axis, shared across panels.* Both panels are AUPRC on the same scale, so
the panels are directly comparable. A second axis would make the two negative
schemes look equivalent when the whole point is that they are not.

*Error bars.* 95% Student-t interval over seeds. At five seeds the normal
approximation is ~30% too narrow.

*Relief rule.* The aqua slot sits below 3:1 contrast on the light surface, so the
palette validator requires visible labels or a table view. Both are present:
lines are directly labelled at their right end, and `phase_a_summary.md` carries
the full table.

*The prevalence line.* AUPRC has no fixed baseline - a random classifier scores
the positive prevalence, 0.5 here. Drawn as a recessive reference so no value can
be read as "good" without it.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ddinet.eval.metrics import mean_ci

REPORTS = Path(__file__).resolve().parents[1] / "reports"
FIGURES = REPORTS / "figures"

# Validated categorical slots 1-3 (light surface). Assigned in fixed order and
# never cycled; a fourth model would fold into "other" or get its own facet.
COLOURS = {"degree_only": "#2a78d6", "logreg": "#eb6834", "random_forest": "#1baf7a"}
LABELS = {"degree_only": "degree-only", "logreg": "logistic regression",
          "random_forest": "random forest"}
STYLES = {"none": "-", "symmetric": "-", "concat": "--"}

SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e3e2df"

#: Ordered by how much leakage the scheme permits - the x-axis is a severity
#: ordering, not a nominal list, which is what makes the slope meaningful.
SCHEME_ORDER = ["random_pair", "drug", "scaffold"]
SCHEME_LABELS = {"random_pair": "random pair\n(as published)",
                 "drug": "drug-level", "scaffold": "scaffold"}
PANEL_TITLES = {"uniform": "Uniform negatives",
                "degree_matched": "Degree-matched negatives"}


def main() -> int:
    results_path = REPORTS / "phase_a_results.csv"
    if not results_path.exists():
        raise SystemExit(f"No results at {results_path}; run 10_phase_a_baselines.py")

    df = pd.read_csv(results_path)
    pooled = df[df["test_view"] == "pooled"]
    n_seeds = pooled["seed"].nunique()
    schemes = [s for s in SCHEME_ORDER if s in set(pooled["scheme"])]
    strategies = [s for s in ("uniform", "degree_matched")
                  if s in set(pooled["negatives"])]

    fig, axes = plt.subplots(
        1, len(strategies), figsize=(4.6 * len(strategies), 5.0),
        sharey=True, facecolor=SURFACE,
    )
    axes = np.atleast_1d(axes)

    prevalence = float(pooled["prevalence"].mean())

    for ax, strategy in zip(axes, strategies):
        ax.set_facecolor(SURFACE)
        sub = pooled[pooled["negatives"] == strategy]
        end_labels: list[tuple[float, float, str, str]] = []

        ax.axhline(prevalence, color=TEXT_SECONDARY, lw=1, ls=":", alpha=0.55, zorder=1)
        if strategy == strategies[-1]:
            # Once only, on the last panel. Drawn on every panel it collided
            # with the neighbouring axes and was clipped.
            ax.text(-0.2, prevalence + 0.008,
                    f"random classifier = {prevalence:.2f}", va="bottom", ha="left",
                    fontsize=8, color=TEXT_SECONDARY)

        for model in ("degree_only", "logreg", "random_forest"):
            for encoding in sorted(sub[sub["model"] == model]["encoding"].unique()):
                xs, ys, errs = [], [], []
                for i, scheme in enumerate(schemes):
                    vals = sub[(sub["model"] == model) &
                               (sub["encoding"] == encoding) &
                               (sub["scheme"] == scheme)]["auprc"]
                    if not len(vals):
                        continue
                    mean, _, _, half = mean_ci(vals)
                    xs.append(i)
                    ys.append(mean)
                    errs.append(0.0 if not np.isfinite(half) else half)
                if not xs:
                    continue
                ax.errorbar(
                    xs, ys, yerr=errs,
                    color=COLOURS[model], linestyle=STYLES.get(encoding, "-"),
                    lw=2, marker="o", markersize=8,
                    markeredgecolor=SURFACE, markeredgewidth=2,
                    capsize=3, elinewidth=1.2, zorder=3,
                )
                # Direct label at the right end - the relief the validator
                # requires, and it removes a legend lookup for the reader.
                # Positions are collected and de-collided after the loop.
                if strategy == strategies[-1]:
                    suffix = "" if encoding == "none" else f" · {encoding}"
                    end_labels.append(
                        (ys[-1], xs[-1], f"{LABELS[model]}{suffix}", COLOURS[model])
                    )

        # Push overlapping end labels apart. Two lines that finish within a
        # hair of each other would otherwise print on top of one another, which
        # is exactly the case the relief rule is meant to prevent.
        if end_labels:
            span = max(ax.get_ylim()) - min(ax.get_ylim())
            min_gap = span * 0.045
            end_labels.sort()
            placed: list[float] = []
            for y, _, _, _ in end_labels:
                target = y
                while placed and target - placed[-1] < min_gap:
                    target = placed[-1] + min_gap
                placed.append(target)
            for (y, x, text, colour), y_text in zip(end_labels, placed):
                ax.annotate(
                    text, xy=(x, y), xytext=(8, 0),
                    textcoords="offset points",
                    xycoords="data", va="center", ha="left",
                    fontsize=8.5, color=TEXT_SECONDARY, annotation_clip=False,
                )
                if abs(y_text - y) > 1e-9:
                    ax.annotate(
                        "", xy=(x, y), xytext=(x + 0.06, y_text),
                        arrowprops=dict(arrowstyle="-", color=colour, lw=0.8,
                                        alpha=0.5), annotation_clip=False,
                    )

        ax.set_title(PANEL_TITLES[strategy], fontsize=11, color=TEXT_PRIMARY, pad=12)
        ax.set_xticks(range(len(schemes)))
        ax.set_xticklabels([SCHEME_LABELS[s] for s in schemes], fontsize=9,
                           color=TEXT_SECONDARY)
        ax.set_xlim(-0.25, len(schemes) - 1 + 0.25)
        ax.grid(axis="y", color=GRID, lw=0.8, zorder=0)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(GRID)
        ax.tick_params(colors=TEXT_SECONDARY, length=0)

    axes[0].set_ylabel("AUPRC on held-out test pairs", fontsize=10,
                       color=TEXT_PRIMARY)

    handles = [
        # Marker only, no line: colour is one encoding channel and line style
        # is another, so a swatch that shows both reads as if the model itself
        # were dashed.
        plt.Line2D([], [], color=COLOURS[m], ls="none", marker="o", markersize=9,
                   markeredgecolor=SURFACE, markeredgewidth=2, label=LABELS[m])
        for m in ("degree_only", "logreg", "random_forest")
    ] + [
        plt.Line2D([], [], color=TEXT_SECONDARY, lw=2, ls="-", label="symmetric pair encoding"),
        plt.Line2D([], [], color=TEXT_SECONDARY, lw=2, ls="--", label="concatenated pair encoding"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=5, frameon=False,
               fontsize=8.5, labelcolor=TEXT_SECONDARY, bbox_to_anchor=(0.5, -0.02))

    fig.suptitle(
        "Baseline performance falls as the evaluation split is tightened",
        fontsize=13, color=TEXT_PRIMARY, y=0.99,
    )
    fig.text(
        0.5, 0.925,
        f"TDC DrugBank, 1,705 drugs, 191,392 interactions · mean ± 95% CI over "
        f"{n_seeds} seed{'s' if n_seeds != 1 else ''} · 1:1 negatives",
        ha="center", fontsize=9, color=TEXT_SECONDARY,
    )
    fig.subplots_adjust(left=0.09, right=0.74, top=0.84, bottom=0.14, wspace=0.08)

    FIGURES.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "svg"):
        fig.savefig(FIGURES / f"phase_a_degradation.{ext}", dpi=200,
                    facecolor=SURFACE, bbox_inches="tight")
    print(f"Wrote {FIGURES/'phase_a_degradation.png'} and .svg")
    print(f"  seeds: {n_seeds}  schemes: {schemes}  strategies: {strategies}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
