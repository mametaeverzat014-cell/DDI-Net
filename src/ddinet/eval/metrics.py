"""
Metrics for a strongly imbalanced binary problem.

WHY ACCURACY IS BANNED FROM THIS PROJECT
----------------------------------------
At a 1:10 negative ratio, "predict no interaction, always" scores 91% accuracy
and is completely useless. Every metric here is chosen because it survives
imbalance, and every one is reported with the base rate beside it.

WHY AUPRC MATTERS MORE THAN AUC-ROC HERE
-----------------------------------------
Both are threshold-free, but they answer different questions.

AUC-ROC is the probability a random positive is ranked above a random negative.
Its weakness under imbalance is that the false-positive rate has a huge
denominator: with 10,000 negatives, 500 false positives is an FPR of only 0.05,
which barely moves the ROC curve - yet those 500 alerts are what a pharmacist
actually experiences. ROC curves therefore look encouraging even when precision
is poor.

AUPRC (average precision) uses precision, whose denominator is the number of
*predicted* positives. It is directly sensitive to false alarms and is the
metric that tracks real usefulness. Its baseline is the positive prevalence,
not 0.5 - so an AUPRC of 0.4 is excellent at 5% prevalence and terrible at 50%.

**Always report AUPRC together with prevalence.** An AUPRC quoted alone is
uninterpretable, and a judge who knows this will ask.

THE THRESHOLD IS A CLINICAL DECISION, NOT A STATISTICAL ONE
------------------------------------------------------------
F1 weights precision and recall equally. That is the wrong trade-off here: a
missed dangerous interaction can kill a patient, while a false alarm costs a
pharmacist thirty seconds. We therefore also report F2 (recall weighted 4x) and
recall at fixed high-precision operating points, and we select thresholds on the
*validation* split only. Choosing a threshold on test data is a subtle but real
form of leakage.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    fbeta_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)


@dataclass
class BinaryMetrics:
    """Everything worth reporting for one binary evaluation."""

    n: int
    n_positive: int
    prevalence: float
    auc_roc: float
    auprc: float
    auprc_lift: float          # AUPRC / prevalence: >1 means better than chance
    precision: float
    recall: float
    f1: float
    f2: float
    balanced_accuracy: float
    specificity: float
    brier: float
    threshold: float
    tp: int
    fp: int
    tn: int
    fn: int

    def to_dict(self) -> dict:
        return asdict(self)

    def summary(self) -> str:
        return (
            f"n={self.n} (pos={self.n_positive}, prevalence={self.prevalence:.3f})\n"
            f"  AUC-ROC {self.auc_roc:.3f} | AUPRC {self.auprc:.3f} "
            f"(lift {self.auprc_lift:.2f}x over prevalence)\n"
            f"  @thr={self.threshold:.3f}: precision {self.precision:.3f} "
            f"recall {self.recall:.3f} F1 {self.f1:.3f} F2 {self.f2:.3f}\n"
            f"  balanced acc {self.balanced_accuracy:.3f} | "
            f"specificity {self.specificity:.3f} | Brier {self.brier:.3f}\n"
            f"  confusion: TP={self.tp} FP={self.fp} TN={self.tn} FN={self.fn}"
        )


def _safe_auc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    """AUC-ROC, or NaN when one class is absent.

    A single-class evaluation set is undefined for ROC, and scikit-learn raises.
    Returning NaN lets a small S3 bucket be reported honestly as "not estimable"
    instead of crashing the run or silently recording 0.5.
    """
    if len(np.unique(y_true)) < 2:
        return float("nan")
    return float(roc_auc_score(y_true, y_score))


def compute_binary_metrics(
    y_true: np.ndarray, y_score: np.ndarray, *, threshold: float = 0.5
) -> BinaryMetrics:
    y_true = np.asarray(y_true).astype(int)
    y_score = np.asarray(y_score, dtype=float)
    y_pred = (y_score >= threshold).astype(int)

    n = len(y_true)
    n_pos = int(y_true.sum())
    prevalence = n_pos / n if n else 0.0

    auprc = (
        float(average_precision_score(y_true, y_score))
        if len(np.unique(y_true)) > 1 else float("nan")
    )

    labels = [0, 1]
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    tn, fp, fn, tp = cm.ravel()
    specificity = tn / (tn + fp) if (tn + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0

    return BinaryMetrics(
        n=n,
        n_positive=n_pos,
        prevalence=prevalence,
        auc_roc=_safe_auc(y_true, y_score),
        auprc=auprc,
        auprc_lift=(auprc / prevalence) if prevalence > 0 and np.isfinite(auprc) else float("nan"),
        precision=float(precision_score(y_true, y_pred, zero_division=0)),
        recall=float(recall),
        f1=float(f1_score(y_true, y_pred, zero_division=0)),
        f2=float(fbeta_score(y_true, y_pred, beta=2, zero_division=0)),
        balanced_accuracy=float((recall + specificity) / 2),
        specificity=float(specificity),
        brier=float(brier_score_loss(y_true, np.clip(y_score, 0, 1))),
        threshold=float(threshold),
        tp=int(tp), fp=int(fp), tn=int(tn), fn=int(fn),
    )


def best_threshold(
    y_true: np.ndarray, y_score: np.ndarray, *, metric: str = "f2"
) -> float:
    """Threshold maximising a metric. **Fit on validation data only.**

    Default is F2, not F1: recall is weighted four times precision because a
    missed dangerous interaction is far more costly than a false alarm. Making
    that trade-off explicit - and defensible on clinical grounds - is better
    than silently accepting F1's implicit claim that the two errors are equal.
    """
    if len(np.unique(y_true)) < 2:
        return 0.5
    precisions, recalls, thresholds = precision_recall_curve(y_true, y_score)
    if len(thresholds) == 0:
        return 0.5
    p, r = precisions[:-1], recalls[:-1]
    beta2 = {"f1": 1.0, "f2": 4.0, "f0.5": 0.25}[metric]
    denom = beta2 * p + r
    scores = np.where(denom > 0, (1 + beta2) * p * r / np.maximum(denom, 1e-12), 0.0)
    return float(thresholds[int(np.argmax(scores))])


def recall_at_precision(
    y_true: np.ndarray, y_score: np.ndarray, min_precision: float = 0.9
) -> tuple[float, float]:
    """Best recall achievable at or above a precision floor.

    This is the deployment-relevant question: "if I will only tolerate one false
    alarm in ten, what fraction of real dangerous interactions do I catch?"
    A single AUPRC number cannot answer that; this can.

    Returns ``(recall, threshold)``; ``(0.0, 1.0)`` if the floor is unreachable.
    """
    if len(np.unique(y_true)) < 2:
        return 0.0, 1.0
    precisions, recalls, thresholds = precision_recall_curve(y_true, y_score)
    ok = precisions[:-1] >= min_precision
    if not ok.any():
        return 0.0, 1.0
    idx = int(np.argmax(np.where(ok, recalls[:-1], -1.0)))
    return float(recalls[idx]), float(thresholds[idx])


def bootstrap_ci(
    y_true: np.ndarray, y_score: np.ndarray, *,
    metric: str = "auprc", n_boot: int = 1000, seed: int = 0, alpha: float = 0.05,
) -> tuple[float, float, float]:
    """Percentile bootstrap CI for a ranking metric.

    Essential on the small S3 buckets, where a point estimate from 12 examples
    is close to meaningless. Reporting "AUPRC 0.71 (95% CI 0.42-0.93)" is honest;
    reporting "0.71" alone invites a judge to over-read it.

    Note this captures sampling variability of the *pairs* only. The dominant
    source of variance in DDI prediction is which *drugs* were held out, and
    that is what the drug-level cross-validation in Step 4 measures. Report both.
    """
    rng = np.random.default_rng(seed)
    y_true = np.asarray(y_true).astype(int)
    y_score = np.asarray(y_score, dtype=float)
    fn = {"auprc": average_precision_score, "auc_roc": roc_auc_score}[metric]

    point = fn(y_true, y_score) if len(np.unique(y_true)) > 1 else float("nan")
    stats = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(y_true), len(y_true))
        if len(np.unique(y_true[idx])) < 2:
            continue
        stats.append(fn(y_true[idx], y_score[idx]))
    if not stats:
        return float(point), float("nan"), float("nan")
    lo, hi = np.percentile(stats, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(point), float(lo), float(hi)


def severity_metrics(
    y_true_rank: np.ndarray, y_pred_probs: np.ndarray
) -> dict[str, float]:
    """Metrics for the ordered severity head, evaluated on positives only.

    Reports macro-F1 (so the rare 'minor' class is not ignored) and mean
    absolute rank error, which respects the ordering: predicting 'moderate' for
    a 'major' costs 1, predicting 'minor' costs 2. Plain accuracy would treat
    both mistakes as identical, which is exactly what ordinal data must not do.
    """
    if len(y_true_rank) == 0:
        return {"macro_f1": float("nan"), "mae_rank": float("nan"), "n": 0}
    pred_rank = np.asarray(y_pred_probs).argmax(axis=1)
    return {
        "macro_f1": float(f1_score(y_true_rank, pred_rank, average="macro",
                                   zero_division=0, labels=[0, 1, 2])),
        "mae_rank": float(np.mean(np.abs(pred_rank - y_true_rank))),
        "exact_match": float(np.mean(pred_rank == y_true_rank)),
        "n": int(len(y_true_rank)),
    }
