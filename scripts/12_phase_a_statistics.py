#!/usr/bin/env python3
"""
Paired significance and equivalence tests on the Phase A results.

    python scripts/12_phase_a_statistics.py

Writes reports/phase_a_statistics.md and .json.

THE CLAIM UNDER TEST
--------------------
Under the protocol most of the DDI literature uses - pairs shuffled at random,
negatives drawn uniformly - the random forest on ECFP4 scores 0.873 and a
classifier using only each drug's interaction degree, with no molecular
information at all, scores 0.868. The project's headline claim is that the
chemistry contributes nothing there.

A difference of +0.005 with per-seed CIs of +/-0.002 and +/-0.003 *looks*
negligible, but "looks negligible" is not a result. Two things are needed:

  1. a paired test, to ask whether the difference is distinguishable from zero;
  2. an EQUIVALENCE test, because a non-significant p-value on its own is not
     evidence of equality - it is equally consistent with a small sample. Only
     a rejected equivalence null licenses writing "equal" instead of "not
     distinguishable".

THE EQUIVALENCE MARGIN
----------------------
Set to 0.01 AUPRC, and this number is a scientific judgement that has to be
declared, not derived from the data:

  * The seed-to-seed 95% CI half-widths in this study are 0.002-0.003, so 0.01
    is three to five times the measurement noise - a margin below that would be
    testing the precision of the experiment rather than the size of the effect.
  * No conclusion anywhere in this project changes if two models differ by 0.01
    AUPRC. The differences that matter here are an order of magnitude larger:
    tightening the split costs 0.08-0.15, and fixing the negatives costs
    0.03-0.23.

*** Declared honestly: the margin was chosen after the results were seen. ***
It was not pre-registered. It is defensible on the grounds above, but a reader
is entitled to know that, and choosing a margin to obtain a desired conclusion
would be the equivalence-testing form of p-hacking.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from ddinet.eval.paired_stats import PairedComparison, extract_paired, paired_compare

REPORTS = Path(__file__).resolve().parents[1] / "reports"

EQUIVALENCE_MARGIN = 0.01

RF = {"model": "random_forest", "encoding": "symmetric"}
RF_FULL = {"model": "random_forest_full", "encoding": "symmetric"}
LR = {"model": "logreg", "encoding": "symmetric"}
DEG = {"model": "degree_only", "encoding": "none"}


def at(scheme: str, negatives: str, base: dict) -> dict:
    return {**base, "scheme": scheme, "negatives": negatives,
            "test_view": "pooled"}


#: (label, selector_a, selector_b, use_equivalence_test)
COMPARISONS = [
    ("HEADLINE (unbounded forest) - random_pair + uniform: full random forest vs degree-only",
     at("random_pair", "uniform", RF_FULL), at("random_pair", "uniform", DEG), True),
    ("HEADLINE (unbounded forest) - drug + degree_matched: full random forest vs degree-only",
     at("drug", "degree_matched", RF_FULL), at("drug", "degree_matched", DEG), True),
    ("DEPTH CAP COST - random_pair + uniform: unbounded vs depth-30 forest",
     at("random_pair", "uniform", RF_FULL), at("random_pair", "uniform", RF), True),
    ("DEPTH CAP COST - drug + degree_matched: unbounded vs depth-30 forest",
     at("drug", "degree_matched", RF_FULL), at("drug", "degree_matched", RF), True),
    ("HEADLINE (depth-capped forest) - random_pair + uniform: random forest vs degree-only",
     at("random_pair", "uniform", RF), at("random_pair", "uniform", DEG), True),
    ("random_pair + uniform: logistic regression vs degree-only",
     at("random_pair", "uniform", LR), at("random_pair", "uniform", DEG), True),
    ("CONTRAST - drug + degree_matched: random forest vs degree-only",
     at("drug", "degree_matched", RF), at("drug", "degree_matched", DEG), True),
    ("drug + uniform: random forest vs degree-only",
     at("drug", "uniform", RF), at("drug", "uniform", DEG), True),
    ("random_pair + degree_matched: random forest vs degree-only",
     at("random_pair", "degree_matched", RF),
     at("random_pair", "degree_matched", DEG), True),
    ("scaffold + degree_matched: random forest vs degree-only",
     at("scaffold", "degree_matched", RF),
     at("scaffold", "degree_matched", DEG), True),
    ("SPLIT EFFECT - random forest, uniform: random_pair vs drug",
     at("random_pair", "uniform", RF), at("drug", "uniform", RF), False),
    ("SPLIT EFFECT - degree-only, uniform: random_pair vs drug",
     at("random_pair", "uniform", DEG), at("drug", "uniform", DEG), False),
    ("NEGATIVES EFFECT - random forest, random_pair: uniform vs degree_matched",
     at("random_pair", "uniform", RF),
     at("random_pair", "degree_matched", RF), False),
    ("NEGATIVES EFFECT - degree-only, random_pair: uniform vs degree_matched",
     at("random_pair", "uniform", DEG),
     at("random_pair", "degree_matched", DEG), False),
    ("ENCODING - random forest, drug + degree_matched: symmetric vs concat",
     at("drug", "degree_matched", RF),
     at("drug", "degree_matched", {"model": "random_forest", "encoding": "concat"}),
     True),
    ("ENCODING - logistic regression, drug + degree_matched: symmetric vs concat",
     at("drug", "degree_matched", LR),
     at("drug", "degree_matched", {"model": "logreg", "encoding": "concat"}),
     True),
]


def label_of(sel: dict) -> str:
    enc = "" if sel["encoding"] == "none" else f"[{sel['encoding']}]"
    return f"{sel['model']}{enc} @ {sel['scheme']}/{sel['negatives']}"


def main() -> int:
    results_path = REPORTS / "phase_a_results.csv"
    if not results_path.exists():
        raise SystemExit(f"No results at {results_path}")
    results = pd.read_csv(results_path)

    # Fold in the unbounded-forest runs so the headline can be re-tested against
    # a forest that is not handicapped by the depth cap. Without this the
    # comparison rests on a model we deliberately weakened for tractability,
    # which is the first thing an examiner would push on.
    full_rf_path = REPORTS / "phase_a_full_rf.csv"
    if full_rf_path.exists():
        full_rf = pd.read_csv(full_rf_path)
        full_rf["model"] = "random_forest_full"
        results = pd.concat([results, full_rf], ignore_index=True)
        print(f"Loaded {len(full_rf)} unbounded random-forest runs\n")

    comparisons: list[tuple[str, PairedComparison]] = []
    for label, sel_a, sel_b, use_tost in COMPARISONS:
        try:
            a, b, seeds = extract_paired(results, sel_a, sel_b)
        except Exception as exc:
            print(f"[skip] {label}: {exc}")
            continue
        comparison = paired_compare(
            a, b, name_a=label_of(sel_a), name_b=label_of(sel_b),
            equivalence_margin=EQUIVALENCE_MARGIN if use_tost else None,
        )
        comparisons.append((label, comparison))
        print(f"\n### {label}")
        print(comparison.summary())

    # ---- Report ------------------------------------------------------
    lines: list[str] = []
    w = lines.append
    w("# Phase A - paired significance and equivalence tests\n")
    w("Generated by `scripts/12_phase_a_statistics.py`. Metric: AUPRC on the "
      "pooled test set. Five seeds, paired by seed.\n")

    w("## Why the paired t-test is primary and Wilcoxon is not\n")
    w("Wilcoxon signed-rank on 5 pairs has 2^5 = 32 equally likely sign "
      "assignments under the null, so its smallest attainable two-sided "
      "p-value is 2/32 = **0.0625**. It cannot return p < 0.05 at this sample "
      "size regardless of effect size. Using it as the primary test would "
      "guarantee non-significance and then invite that to be read as evidence "
      "of no difference.\n")
    w("The paired t-test assumes approximately normal differences, which n = 5 "
      "cannot verify - stated plainly rather than glossed. It is still the "
      "right primary test: continuous measurements, exact pairing, and the "
      "only one of the two with power here. Wilcoxon is reported alongside as "
      "a distribution-free cross-check.\n")

    w("## Why a non-significant p-value is not enough\n")
    w("\"We failed to reject\" and \"there is no difference\" are different "
      "statements; a large p-value is produced just as readily by a small "
      "sample as by an absent effect. Writing **equal** requires an "
      "equivalence test (TOST) against a margin declared in advance of the "
      "conclusion.\n")
    w(f"**Margin: +/-{EQUIVALENCE_MARGIN} AUPRC.** Three to five times the "
      "seed-level CI half-widths (0.002-0.003), and an order of magnitude "
      "below the differences this project actually turns on (0.08-0.15 for the "
      "split, 0.03-0.23 for the negatives). **Declared honestly: chosen after "
      "seeing the results, not pre-registered.**\n")

    w("## Results\n")
    w("| Comparison | Difference | 95% CI | paired t p | Wilcoxon p | TOST p | Verdict |")
    w("|---|---|---|---|---|---|---|")
    for label, c in comparisons:
        tost_cell = (f"{c.tost_p_value:.4f}" if c.tost_p_value is not None else "-")
        wil = f"{c.wilcoxon_p_value:.4f}" if c.wilcoxon_p_value is not None else "-"
        significant = c.t_p_value < 0.05
        if significant and c.equivalent:
            verdict = "**detectable but negligible**"
        elif significant:
            verdict = "**different**"
        elif c.equivalent:
            verdict = f"**equivalent within {EQUIVALENCE_MARGIN}**"
        else:
            verdict = "inconclusive"
        w(f"| {label} | {c.mean_difference:+.4f} | "
          f"[{c.ci_low:+.4f}, {c.ci_high:+.4f}] | {c.t_p_value:.4f} | {wil} | "
          f"{tost_cell} | {verdict} |")
    w("")

    w("## What may be written in the paper\n")
    for label, c in comparisons:
        w(f"**{label}**  \n{c.verdict()}\n")

    (REPORTS / "phase_a_statistics.md").write_text("\n".join(lines))
    (REPORTS / "phase_a_statistics.json").write_text(json.dumps(
        {"equivalence_margin": EQUIVALENCE_MARGIN,
         "margin_declared_post_hoc": True,
         "comparisons": [{"label": lbl, **c.to_dict()} for lbl, c in comparisons]},
        indent=2, default=float))
    print(f"\nWrote {REPORTS/'phase_a_statistics.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
