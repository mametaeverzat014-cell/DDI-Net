"""
Paired tests across seeds, and equivalence testing.

WHY PAIRED, NOT TWO INDEPENDENT SAMPLES
----------------------------------------
Every model in this study is evaluated on the *same* five seeds, and a seed
fixes the split assignment, the negative sample and the fit stochasticity all at
once. Seeds therefore differ from each other far more than models differ within
a seed. Comparing two independent means throws that shared variation into the
error term and buries the effect; comparing per-seed *differences* removes it.

WHY THE PAIRED t-TEST AND NOT WILCOXON, AT n = 5
-------------------------------------------------
The Wilcoxon signed-rank test on 5 pairs has 2^5 = 32 equally likely sign
assignments under the null, so its smallest attainable two-sided p-value is
2/32 = 0.0625. **It cannot return p < 0.05 no matter how large the effect.**
Using it as the primary test would guarantee a non-significant result and then
invite that result to be read as evidence of no difference, which would be
circular.

The paired t-test assumes the differences are approximately normal. With n = 5
that assumption cannot be checked, and we say so rather than pretending
otherwise. It is nonetheless the appropriate primary test here: the measurements
are continuous, the pairing is exact, and it is the only one of the two with any
power at this sample size. Wilcoxon is reported alongside as a distribution-free
cross-check - if the two disagree in direction, the t-test result should be
distrusted.

*** A NON-SIGNIFICANT p DOES NOT MEAN THE TWO ARE EQUAL ***
-----------------------------------------------------------
This is the point on which the project's headline claim turns, so it is worth
being exact. "We failed to reject the null" and "the null is true" are different
statements. A large p-value is produced just as readily by a small sample as by
a genuine absence of effect, and at n = 5 the study has little power.

To claim *equivalence* - to write "equal" rather than "not distinguishable" -
requires an equivalence test against a margin fixed in advance. ``tost``
implements the standard two one-sided tests procedure: it rejects the null of
"the true difference is at least as large as the margin" from both sides. Only
if BOTH one-sided tests reject can equivalence be asserted, and then only
equivalence *within the stated margin*.

The margin is a scientific judgement, not a statistical one, and must be stated
with the result. It has to be chosen before looking at the p-value; choosing it
afterwards to obtain the desired conclusion is the equivalence-testing version
of p-hacking.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy import stats


@dataclass
class PairedComparison:
    """Result of comparing two models across the seeds they share."""

    name_a: str
    name_b: str
    metric: str
    n_pairs: int
    mean_a: float
    mean_b: float
    mean_difference: float
    ci_low: float
    ci_high: float
    t_statistic: float
    t_p_value: float
    wilcoxon_p_value: float | None
    wilcoxon_min_attainable_p: float
    per_seed_differences: list[float]
    #: Equivalence testing, present when a margin was supplied.
    equivalence_margin: float | None = None
    tost_p_value: float | None = None
    equivalent: bool | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    def verdict(self, alpha: float = 0.05) -> str:
        """The sentence that may honestly be written about this comparison.

        Significance and equivalence are independent questions, so there are
        four outcomes rather than two. The case that matters most here is
        significant AND equivalent: a difference that is reliably detectable
        yet too small to matter. Reporting only the significance would overstate
        it; reporting only the equivalence would hide that it is real. Both
        belong in the sentence.
        """
        significant = self.t_p_value < alpha
        equivalent = bool(self.equivalent)
        direction = "higher" if self.mean_difference > 0 else "lower"
        size = (
            f"{abs(self.mean_difference):.4f} "
            f"(95% CI [{self.ci_low:+.4f}, {self.ci_high:+.4f}], "
            f"paired t p = {self.t_p_value:.4f})"
        )

        if significant and equivalent:
            return (
                f"{self.name_a} is {direction} than {self.name_b} by {size}, "
                f"but the difference is EQUIVALENT TO ZERO within "
                f"+/-{self.equivalence_margin:g} (TOST p = {self.tost_p_value:.4f}): "
                f"detectable but negligible"
            )
        if significant:
            return f"{self.name_a} is {direction} than {self.name_b} by {size}"
        if equivalent:
            return (
                f"{self.name_a} and {self.name_b} are EQUIVALENT within "
                f"+/-{self.equivalence_margin:g} (TOST p = {self.tost_p_value:.4f}); "
                f"difference {self.mean_difference:+.4f}, "
                f"95% CI [{self.ci_low:+.4f}, {self.ci_high:+.4f}]"
            )
        return (
            f"{self.name_a} vs {self.name_b}: not significant "
            f"(p = {self.t_p_value:.4f}) AND equivalence not established - "
            f"inconclusive, not evidence of equality"
        )

    def summary(self) -> str:
        lines = [
            f"{self.name_a}  vs  {self.name_b}   [{self.metric}]",
            f"  means            {self.mean_a:.4f} vs {self.mean_b:.4f}",
            f"  paired diff      {self.mean_difference:+.4f}  "
            f"95% CI [{self.ci_low:+.4f}, {self.ci_high:+.4f}]  (n = {self.n_pairs})",
            f"  per-seed diffs   {[round(d, 4) for d in self.per_seed_differences]}",
            f"  paired t-test    t = {self.t_statistic:+.3f}, p = {self.t_p_value:.4f}",
        ]
        if self.wilcoxon_p_value is not None:
            lines.append(
                f"  Wilcoxon         p = {self.wilcoxon_p_value:.4f}  "
                f"(min attainable at n={self.n_pairs}: "
                f"{self.wilcoxon_min_attainable_p:.4f} - underpowered by construction)"
            )
        if self.equivalence_margin is not None:
            lines.append(
                f"  TOST +/-{self.equivalence_margin:g}   p = {self.tost_p_value:.4f} -> "
                f"{'EQUIVALENT' if self.equivalent else 'equivalence NOT established'}"
            )
        lines.append(f"  verdict: {self.verdict()}")
        return "\n".join(lines)


def wilcoxon_min_p(n: int) -> float:
    """Smallest two-sided p the signed-rank test can return at this n.

    Under the null every sign assignment is equally likely, so with n pairs
    there are 2^n outcomes and the most extreme two-sided result carries
    2 / 2^n. At n = 5 that is 0.0625, above the conventional 0.05 threshold.
    """
    return 2.0 / (2 ** n) if n > 0 else float("nan")


def paired_compare(
    values_a: np.ndarray,
    values_b: np.ndarray,
    *,
    name_a: str = "A",
    name_b: str = "B",
    metric: str = "auprc",
    equivalence_margin: float | None = None,
    alpha: float = 0.05,
) -> PairedComparison:
    """Compare two paired series. ``values_a[i]`` and ``values_b[i]`` share a seed."""
    a = np.asarray(values_a, dtype=float)
    b = np.asarray(values_b, dtype=float)
    if a.shape != b.shape:
        raise ValueError(f"Unpaired inputs: {a.shape} vs {b.shape}")
    ok = np.isfinite(a) & np.isfinite(b)
    a, b = a[ok], b[ok]
    diff = a - b
    n = len(diff)
    if n < 2:
        raise ValueError(f"Need at least 2 pairs, got {n}")

    mean_diff = float(diff.mean())
    sem = float(diff.std(ddof=1) / np.sqrt(n))
    t_crit = float(stats.t.ppf(1 - alpha / 2, df=n - 1))
    ci_low, ci_high = mean_diff - t_crit * sem, mean_diff + t_crit * sem

    if np.allclose(diff, diff[0]):
        # Zero variance: the t-statistic is undefined. Happens when every seed
        # gives exactly the same difference, which at this precision means the
        # two models are byte-identical, not that the effect is infinite.
        t_stat = float("inf") if mean_diff != 0 else 0.0
        t_p = 0.0 if mean_diff != 0 else 1.0
    else:
        t_res = stats.ttest_rel(a, b)
        t_stat, t_p = float(t_res.statistic), float(t_res.pvalue)

    try:
        w_p = float(stats.wilcoxon(diff).pvalue) if np.any(diff != 0) else 1.0
    except ValueError:
        w_p = None

    result = PairedComparison(
        name_a=name_a, name_b=name_b, metric=metric, n_pairs=n,
        mean_a=float(a.mean()), mean_b=float(b.mean()),
        mean_difference=mean_diff, ci_low=ci_low, ci_high=ci_high,
        t_statistic=t_stat, t_p_value=t_p,
        wilcoxon_p_value=w_p, wilcoxon_min_attainable_p=wilcoxon_min_p(n),
        per_seed_differences=[float(d) for d in diff],
    )

    if equivalence_margin is not None:
        p_tost, equivalent = tost(diff, equivalence_margin, alpha=alpha)
        result.equivalence_margin = float(equivalence_margin)
        result.tost_p_value = float(p_tost)
        result.equivalent = bool(equivalent)
    return result


def tost(
    differences: np.ndarray, margin: float, *, alpha: float = 0.05
) -> tuple[float, bool]:
    """Two one-sided tests for equivalence within ``+/- margin``.

    Null hypotheses: the true difference is <= -margin, and >= +margin. Both
    must be rejected for equivalence to be claimed, so the overall p-value is
    the LARGER of the two one-sided p-values - the harder of the two hurdles.

    Returns ``(p_value, equivalent_at_alpha)``.

    Note this is a statement about the *margin*, never about zero. "Equivalent
    within 0.01 AUPRC" is a claim that can be supported; "identical" is not.
    """
    d = np.asarray(differences, dtype=float)
    n = len(d)
    mean = d.mean()
    sem = d.std(ddof=1) / np.sqrt(n)
    if sem == 0:
        equivalent = abs(mean) < margin
        return (0.0 if equivalent else 1.0), equivalent
    df = n - 1
    t_lower = (mean - (-margin)) / sem      # H0: diff <= -margin
    t_upper = (mean - margin) / sem         # H0: diff >= +margin
    p_lower = float(stats.t.sf(t_lower, df))
    p_upper = float(stats.t.cdf(t_upper, df))
    p = max(p_lower, p_upper)
    return p, p < alpha


def extract_paired(
    results: pd.DataFrame,
    selector_a: dict,
    selector_b: dict,
    *,
    metric: str = "auprc",
) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """Pull two seed-aligned series out of the results table.

    Seeds present for only one of the two selectors are dropped, so the pairing
    is exact rather than approximate.
    """
    def pick(sel: dict) -> pd.Series:
        sub = results
        for key, value in sel.items():
            sub = sub[sub[key] == value]
        if sub["seed"].duplicated().any():
            raise ValueError(f"Selector {sel} matches multiple rows per seed")
        return sub.set_index("seed")[metric]

    sa, sb = pick(selector_a), pick(selector_b)
    seeds = sorted(set(sa.index) & set(sb.index))
    return sa.loc[seeds].to_numpy(), sb.loc[seeds].to_numpy(), seeds
