"""Parity: does this inference pipeline reproduce the frozen seed-0 predictions?

WHY THIS EXISTS
---------------
The Analyze page shows a number that claims to come from the frozen research
model. That claim is only true if this pipeline reproduces what the frozen run
produced. This module measures that against
reports/v2_final/v2_final_pair_predictions.csv, read straight from the tag so it
cannot be cherry-picked or quietly regenerated.

WHAT WAS MEASURED, AND THE TOLERANCE IT JUSTIFIES
-------------------------------------------------
Over all 92,448 frozen seed-0 rows, scored on CPU:

    probability space   max |Δ| 8.37e-06     mean |Δ| 1.05e-07
    logit space         max |Δ| 8.17e-02     mean |Δ| 4.93e-04

The logit figure is far above float32 round-off, so it was chased down rather
than waved through. Running the identical weights in float64 on CPU moves the
disagreement with the stored values by nothing at all (mean 4.922e-04 vs
4.930e-04, same maximum), while float32-CPU and float64-CPU differ from each
other by only 2.7e-06. A discrepancy that float64 does not shrink is not this
pipeline's round-off: it lives on the side that produced the stored numbers,
i.e. the frozen run's GPU arithmetic. Reduced-precision matmul (TF32 carries a
10-bit mantissa, ~5e-4 relative) accounts for the magnitude.

Four further facts say this is arithmetic and not a preprocessing or
architecture mismatch, which would bias the scores rather than scatter them:

  * the signed logit error is centred — mean +5.9e-05 against SD 3.3e-03;
  * Brier reproduces to 1.7e-10 and ECE15 to 1.3e-09;
  * the parameter count is exactly 1,122,804, the published figure;
  * two independent batching paths in this repo (cached full encode, and a
    replica of V2Trainer._batch_forward with its 4096 chunking) agree with each
    other to 8.8e-08 while both sit 8.4e-06 from the stored values.

So the tolerance below is stated in PROBABILITY space, which is the quantity the
API returns and the site displays: 1e-05, roughly one part in 10^5 of a score
shown to three decimals.

WHAT PARITY DOES *NOT* CLAIM
----------------------------
It does not claim bit-exact reproduction, and it does not claim the frozen
AUPRC recomputes exactly. It does not: 5.83% of the frozen seed-0 pooled
predictions are exactly 1.0 in float32 — a single saturated tie block of 4,936
rows (4,564 positive, 372 negative) sitting at the top of the ranking, where
average precision is most sensitive. Any perturbation splits that block. Jitter
of ±1e-09, far below the observed difference, already moves AUPRC by ±3.2e-04
(SD over 12 draws). Recomputing on CPU gives 0.821497 against the recorded
0.823534, a gap of 2.0e-03.

That gap is a numerical property of a saturated ranking metric, not a
correction to the published result: the published number stands on its own
frozen predictions, and 2.0e-03 is 0.22x the across-seed SD of 9.1e-03 that the
hypothesis tests were computed against. It is recorded here and in LIMITATIONS
rather than hidden.
"""

from __future__ import annotations

import io
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

FROZEN_TAG = "v2-final-github-safe-2026-09-03"
FROZEN_PREDICTIONS = "reports/v2_final/v2_final_pair_predictions.csv"
FROZEN_RUN_ID = "bd45f84e3c1b2c33"

#: Defined in serving/constants.py, which imports nothing — the request path
#: needs this value and must not pull pandas in to get it.
from .constants import IDEAL_TOLERANCE, PROB_TOLERANCE  # noqa: F401,E402


@dataclass(frozen=True)
class ParityResult:
    n_pairs: int
    max_abs_diff: float
    mean_abs_diff: float
    n_exceeding_tolerance: int
    tolerance: float

    @property
    def passed(self) -> bool:
        return self.n_exceeding_tolerance == 0

    def summary(self) -> str:
        return (
            f"n={self.n_pairs}  max|Δ|={self.max_abs_diff:.3e}  "
            f"mean|Δ|={self.mean_abs_diff:.3e}  "
            f"exceeding {self.tolerance:.0e}: {self.n_exceeding_tolerance}"
        )


def load_frozen_predictions(seed: int = 0) -> pd.DataFrame:
    """Read the frozen predictions from the TAG, never from the working tree.

    The working branch is not a descendant of the frozen commit, so reports/ is
    absent here; reading through git also means the test cannot be satisfied by
    a regenerated local file.
    """
    blob = subprocess.check_output(
        ["git", "show", f"{FROZEN_TAG}:{FROZEN_PREDICTIONS}"], cwd=ROOT
    )
    df = pd.read_csv(io.BytesIO(blob))
    df = df[df["seed"] == seed].reset_index(drop=True)
    run_ids = set(df["run_id"].unique())
    if seed == 0 and run_ids != {FROZEN_RUN_ID}:
        raise RuntimeError(f"seed-0 rows carry unexpected run_ids: {run_ids}")
    return df


def stratified_sample(df: pd.DataFrame, engine, per_stratum: int = 15) -> pd.DataFrame:
    """A deterministic sample spanning the strata that could hide a mismatch.

    Deterministic by construction: strata are defined by columns, and rows are
    taken with ``head()`` from a frame in the frozen file's own order. No RNG,
    so the same rows are checked on every run and a regression cannot hide
    behind a reseed.

    Covered: S2 and S3; documented positives and sampled-unlabelled negatives;
    drugs with full biology and drugs with missing protein or pathway
    annotation — the last because the MISSING token is a separate code path and
    is exactly where an encoding mistake would surface.
    """
    s3_pairs = {
        tuple(sorted(p)) for p in
        zip(df[df.test_view == "S3"].drug_a, df[df.test_view == "S3"].drug_b)
    }
    pooled = df[df.test_view == "pooled"].copy()
    pooled["view"] = [
        "S3" if tuple(sorted((a, b))) in s3_pairs else "S2"
        for a, b in zip(pooled.drug_a, pooled.drug_b)
    ]
    pooled["bio"] = [
        "full" if (engine.has_protein[engine.index[a]] and engine.has_pathway[engine.index[a]]
                   and engine.has_protein[engine.index[b]] and engine.has_pathway[engine.index[b]])
        else "partial"
        for a, b in zip(pooled.drug_a, pooled.drug_b)
    ]
    parts = [
        g.head(per_stratum)
        for _, g in pooled.groupby(["view", "label", "bio"], sort=True)
    ]
    return pd.concat(parts, ignore_index=True)


def check(engine, frame: pd.DataFrame, tolerance: float = PROB_TOLERANCE) -> ParityResult:
    scores = engine.score_many(list(zip(frame.drug_a, frame.drug_b)))
    new = np.array([s.raw_model_score for s in scores])
    old = frame["prediction"].to_numpy()
    diff = np.abs(new - old)
    return ParityResult(
        n_pairs=len(frame),
        max_abs_diff=float(diff.max()),
        mean_abs_diff=float(diff.mean()),
        n_exceeding_tolerance=int((diff > tolerance).sum()),
        tolerance=tolerance,
    )
