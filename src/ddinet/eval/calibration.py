"""
Calibration: does a predicted probability of 0.8 mean the event happens 80% of
the time?

WHY THIS MATTERS MORE THAN AUPRC FOR THE STATED USE CASE
---------------------------------------------------------
AUPRC and AUC-ROC are *ranking* metrics. They are invariant to any monotone
transformation of the scores, so a model that outputs 0.99 for every pair it
considers risky and 0.98 for every pair it does not scores identically to one
whose outputs are honest probabilities. For ranking a shortlist that is fine.

For the use this project claims - telling a clinician how likely a pair is to
interact - it is not. "There is a 15% chance" and "there is an 85% chance" lead
to different decisions, and a ranking metric cannot distinguish a model that
gets those right from one that merely orders them correctly. A well-ranked but
badly calibrated model is actively dangerous in that setting, because its
confidence is read as information when it carries none.

So calibration is not a supplementary metric here. It is the one that tests the
project's own claim about why the work is useful.

EXPECTED CALIBRATION ERROR, AND WHY THE BINNING SCHEME IS REPORTED
-------------------------------------------------------------------
ECE partitions predictions into bins and averages |accuracy - confidence| over
them, weighted by bin population. It is the standard summary, and it has a
known weakness: **the value depends on the binning**, and equal-width bins are
easy to game. With most predictions crowded into one or two bins, equal-width
binning leaves the rest nearly empty, and those sparse bins contribute almost
nothing to the weighted average - so a badly calibrated model can post a small
ECE.

Both schemes are therefore computed and reported side by side:

  ``uniform``   equal-width bins over [0, 1]. The conventional choice; comparable
                with published numbers.
  ``quantile``  equal-mass bins. Every bin holds the same number of predictions,
                so no region of the score range can hide.

A large gap between the two is itself diagnostic: it means the predictions are
concentrated, and the uniform number is flattering.

TEMPERATURE SCALING
-------------------
A single scalar T divides the logits before the sigmoid: p' = sigmoid(logit/T).
T > 1 softens over-confident predictions, T < 1 sharpens under-confident ones.

Two properties make it the right first thing to try. It is **monotone**, so it
cannot change the ranking at all - AUPRC, AUC-ROC and every threshold-free
metric are identical before and after. And it has **one parameter**, so it
cannot overfit a validation set of this size.

That also bounds what it can fix: temperature scaling corrects global
over- or under-confidence, not a model whose errors differ by region of the
score range. If ECE stays high after scaling, the miscalibration is structural
and needs isotonic regression or a different model, not a better T.

**T is fitted on validation and applied unchanged to test.** Fitting it on test
would be the same leak as tuning a threshold there.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy import optimize
from sklearn.metrics import brier_score_loss

EPSILON = 1e-12


def _to_logit(p: np.ndarray) -> np.ndarray:
    """Inverse sigmoid, clipped so that 0 and 1 do not become infinite.

    Random forests routinely output exact 0.0 and 1.0 when every tree agrees,
    which would otherwise make the temperature fit diverge.
    """
    p = np.clip(np.asarray(p, dtype=float), EPSILON, 1 - EPSILON)
    return np.log(p / (1 - p))


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -700, 700)))


@dataclass
class ReliabilityCurve:
    """Binned observed frequency against mean predicted probability."""

    bin_edges: list[float]
    mean_predicted: list[float]
    observed_frequency: list[float]
    counts: list[int]
    strategy: str

    def to_dict(self) -> dict:
        return asdict(self)


def reliability_curve(
    y_true: np.ndarray, y_prob: np.ndarray, *, n_bins: int = 15,
    strategy: str = "quantile",
) -> ReliabilityCurve:
    """Points for a reliability diagram.

    Empty bins are dropped rather than plotted at zero: an empty bin carries no
    observation, and drawing it at the origin invents a data point that would
    read as catastrophic miscalibration.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_prob = np.asarray(y_prob, dtype=float)

    if strategy == "uniform":
        edges = np.linspace(0.0, 1.0, n_bins + 1)
    elif strategy == "quantile":
        edges = np.unique(np.quantile(y_prob, np.linspace(0, 1, n_bins + 1)))
        if len(edges) < 2:
            edges = np.array([0.0, 1.0])
    else:
        raise ValueError(f"Unknown binning strategy {strategy!r}")

    idx = np.clip(np.digitize(y_prob, edges[1:-1], right=False), 0, len(edges) - 2)
    mean_pred, observed, counts = [], [], []
    for b in range(len(edges) - 1):
        mask = idx == b
        n = int(mask.sum())
        if n == 0:
            continue
        mean_pred.append(float(y_prob[mask].mean()))
        observed.append(float(y_true[mask].mean()))
        counts.append(n)

    return ReliabilityCurve([float(e) for e in edges], mean_pred, observed,
                            counts, strategy)


def expected_calibration_error(
    y_true: np.ndarray, y_prob: np.ndarray, *, n_bins: int = 15,
    strategy: str = "quantile",
) -> float:
    """Population-weighted mean |observed - predicted| across bins."""
    curve = reliability_curve(y_true, y_prob, n_bins=n_bins, strategy=strategy)
    if not curve.counts:
        return float("nan")
    counts = np.asarray(curve.counts, dtype=float)
    gaps = np.abs(np.asarray(curve.observed_frequency) - np.asarray(curve.mean_predicted))
    return float((counts * gaps).sum() / counts.sum())


def maximum_calibration_error(
    y_true: np.ndarray, y_prob: np.ndarray, *, n_bins: int = 15,
    strategy: str = "quantile", min_count: int = 30,
) -> float:
    """Worst per-bin gap, ignoring bins too small to estimate a frequency from.

    Without ``min_count`` this is dominated by whichever bin happens to hold
    three points, which says more about sampling noise than about the model.
    """
    curve = reliability_curve(y_true, y_prob, n_bins=n_bins, strategy=strategy)
    gaps = [
        abs(o - p) for o, p, c in
        zip(curve.observed_frequency, curve.mean_predicted, curve.counts)
        if c >= min_count
    ]
    return float(max(gaps)) if gaps else float("nan")


class TemperatureScaler:
    """Single-parameter recalibration: ``p' = sigmoid(logit(p) / T)``.

    Monotone, so it never changes the ranking - every threshold-free metric is
    unchanged by construction, and ``assert_ranking_preserved`` checks it.
    """

    def __init__(self) -> None:
        self.temperature: float = 1.0
        self.converged: bool = False

    def fit(self, y_true: np.ndarray, y_prob: np.ndarray) -> "TemperatureScaler":
        """Fit T by minimising negative log-likelihood on the given data.

        Call this with VALIDATION predictions only.
        """
        y = np.asarray(y_true, dtype=float)
        logits = _to_logit(y_prob)

        def nll(log_t: np.ndarray) -> float:
            # Optimise log(T) so T stays positive without a constrained solver.
            t = float(np.exp(log_t[0]))
            p = np.clip(_sigmoid(logits / t), EPSILON, 1 - EPSILON)
            return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())

        result = optimize.minimize(nll, x0=np.array([0.0]), method="Nelder-Mead",
                                   options={"xatol": 1e-4, "fatol": 1e-8})
        self.temperature = float(np.exp(result.x[0]))
        self.converged = bool(result.success)
        return self

    def transform(self, y_prob: np.ndarray) -> np.ndarray:
        return _sigmoid(_to_logit(y_prob) / self.temperature)

    def describe(self) -> str:
        direction = ("softening over-confident predictions" if self.temperature > 1
                     else "sharpening under-confident predictions"
                     if self.temperature < 1 else "no change")
        return f"T = {self.temperature:.3f} ({direction})"


def assert_ranking_preserved(before: np.ndarray, after: np.ndarray,
                             tolerance: float = 1e-9) -> None:
    """Verify a recalibration did not reorder anything.

    Temperature scaling is monotone in theory; this checks the implementation
    against floating-point surprises, because a recalibration that silently
    changed the ranking would invalidate every metric reported alongside it.
    """
    order_before = np.argsort(np.asarray(before, dtype=float), kind="stable")
    order_after = np.argsort(np.asarray(after, dtype=float), kind="stable")
    b = np.asarray(before, dtype=float)[order_before]
    a = np.asarray(after, dtype=float)[order_after]
    if not np.array_equal(order_before, order_after):
        # Ties can legitimately reorder under a stable sort; only flag a genuine
        # change in the sorted value sequence.
        if not (np.all(np.diff(b) >= -tolerance) and np.all(np.diff(a) >= -tolerance)):
            raise AssertionError("Recalibration changed the ranking")


@dataclass
class CalibrationReport:
    model: str
    n: int
    prevalence: float
    brier: float
    ece_uniform: float
    ece_quantile: float
    mce_quantile: float
    temperature: float
    brier_scaled: float
    ece_uniform_scaled: float
    ece_quantile_scaled: float
    mce_quantile_scaled: float

    def to_dict(self) -> dict:
        return asdict(self)

    def summary(self) -> str:
        return (
            f"{self.model:26s} n={self.n:6d}  "
            f"Brier {self.brier:.4f} -> {self.brier_scaled:.4f}   "
            f"ECE(q) {self.ece_quantile:.4f} -> {self.ece_quantile_scaled:.4f}   "
            f"ECE(u) {self.ece_uniform:.4f} -> {self.ece_uniform_scaled:.4f}   "
            f"MCE {self.mce_quantile:.4f} -> {self.mce_quantile_scaled:.4f}   "
            f"T={self.temperature:.3f}"
        )


def evaluate_calibration(
    model_name: str,
    y_val: np.ndarray, p_val: np.ndarray,
    y_test: np.ndarray, p_test: np.ndarray,
    *, n_bins: int = 15,
) -> tuple[CalibrationReport, np.ndarray, TemperatureScaler]:
    """Full calibration assessment: raw, then temperature-scaled.

    The scaler is fitted on validation and applied to test. Returns the report,
    the recalibrated test probabilities, and the fitted scaler.
    """
    scaler = TemperatureScaler().fit(y_val, p_val)
    p_test_scaled = scaler.transform(p_test)
    assert_ranking_preserved(p_test, p_test_scaled)

    report = CalibrationReport(
        model=model_name,
        n=int(len(y_test)),
        prevalence=float(np.mean(y_test)),
        brier=float(brier_score_loss(y_test, np.clip(p_test, 0, 1))),
        ece_uniform=expected_calibration_error(y_test, p_test, n_bins=n_bins,
                                               strategy="uniform"),
        ece_quantile=expected_calibration_error(y_test, p_test, n_bins=n_bins,
                                                strategy="quantile"),
        mce_quantile=maximum_calibration_error(y_test, p_test, n_bins=n_bins),
        temperature=scaler.temperature,
        brier_scaled=float(brier_score_loss(y_test, np.clip(p_test_scaled, 0, 1))),
        ece_uniform_scaled=expected_calibration_error(y_test, p_test_scaled,
                                                      n_bins=n_bins, strategy="uniform"),
        ece_quantile_scaled=expected_calibration_error(y_test, p_test_scaled,
                                                       n_bins=n_bins, strategy="quantile"),
        mce_quantile_scaled=maximum_calibration_error(y_test, p_test_scaled, n_bins=n_bins),
    )
    return report, p_test_scaled, scaler
