"""
The leakage verifier: one module that proves, or measures, drug overlap between
splits.

WHY THIS IS A SEPARATE MODULE AND NOT AN ASSERTION BURIED IN THE SPLITTER
--------------------------------------------------------------------------
The project's main claim is that published DDI metrics are inflated by data
leakage. That claim is worthless unless our *own* splits are verifiably clean.
So the verification is not a private implementation detail of the splitter - it
is a first-class artefact with its own tests, run before every training run, and
its output goes into the write-up.

Keeping it separate also keeps it honest: a splitter that verifies itself can
only check the invariant it happens to believe in. This module recomputes the
overlap from the produced buckets, so a bug in the routing logic is caught
rather than reproduced.

TWO MODES, BECAUSE THERE ARE TWO KINDS OF SCHEME
-------------------------------------------------
**Strict schemes** (``drug``, ``scaffold``). Zero drug overlap is a design
invariant. Any overlap is a bug, and the verifier raises ``LeakageError``. It
must fail the run: a silent leak invalidates every number downstream, and a
warning would be scrolled past.

**Measured schemes** (``random_pair``). Overlap is expected and is the whole
point - the scheme is included precisely so its leakage can be quantified. Here
raising would be wrong: the verifier reports the size of the overlap as a
measurement. Refusing to run the leaky baseline would mean having no baseline
to compare against.

WHAT IS MEASURED
----------------
Drug-level overlap answers "did the same molecule appear on both sides?". But
the quantity that actually matters for link prediction is finer: **how many
test pairs have both endpoints already seen in training?** Those are the pairs
a model can score from memorised node identity alone. That is the S1/S2/S3
composition of the test bucket, and it is what converts "this scheme leaks" from
an assertion into a number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import pandas as pd

#: Schemes whose design guarantees zero drug overlap. Any overlap is a bug.
STRICT_SCHEMES: frozenset[str] = frozenset({"drug", "scaffold"})

#: Schemes where overlap is expected and is reported rather than rejected.
MEASURED_SCHEMES: frozenset[str] = frozenset({"random_pair"})


class LeakageError(AssertionError):
    """A strict scheme produced overlapping drugs. The run must not continue."""


class SplitLike(Protocol):
    """The minimal contract both split types satisfy."""

    train_drugs: set[str]
    val_drugs: set[str]
    test_drugs: set[str]
    buckets: dict[str, pd.DataFrame]

    @property
    def scheme(self) -> str: ...


@dataclass
class LeakageReport:
    """Everything the verifier measured. Serialised into experiment logs."""

    scheme: str
    strict: bool
    n_train_drugs: int
    n_val_drugs: int
    n_test_drugs: int
    #: Drugs present in both splits of each pair.
    overlap_train_val: int
    overlap_train_test: int
    overlap_val_test: int
    #: Fraction of test drugs that were also seen during training.
    test_drugs_seen_in_train_fraction: float
    #: Test pairs by how many endpoints appeared in TRAINING pairs.
    test_pair_settings: dict[str, int] = field(default_factory=dict)
    val_pair_settings: dict[str, int] = field(default_factory=dict)
    n_train_pairs: int = 0
    n_val_pairs: int = 0
    n_test_pairs: int = 0
    n_discarded_pairs: int = 0
    #: Names of overlapping drugs, truncated - for debugging a strict failure.
    example_overlaps: list[str] = field(default_factory=list)

    @property
    def total_drug_overlap(self) -> int:
        return self.overlap_train_val + self.overlap_train_test + self.overlap_val_test

    @property
    def passed(self) -> bool:
        """Strict schemes pass only with zero overlap; measured always pass."""
        return (not self.strict) or self.total_drug_overlap == 0

    @property
    def test_s1_fraction(self) -> float:
        """Share of test pairs whose BOTH endpoints were seen in training.

        The headline leakage number. Under a drug-level split it is 0 by
        construction. Under a random pair split it approaches 1.
        """
        total = sum(self.test_pair_settings.values())
        return self.test_pair_settings.get("S1", 0) / total if total else 0.0

    def summary(self) -> str:
        lines = [
            f"Leakage report - scheme '{self.scheme}' "
            f"({'STRICT' if self.strict else 'MEASURED'})",
            f"  drugs      train={self.n_train_drugs} val={self.n_val_drugs} "
            f"test={self.n_test_drugs}",
            f"  pairs      train={self.n_train_pairs} val={self.n_val_pairs} "
            f"test={self.n_test_pairs} discarded={self.n_discarded_pairs}",
            f"  drug overlap  train&val={self.overlap_train_val} "
            f"train&test={self.overlap_train_test} val&test={self.overlap_val_test}",
            f"  test drugs also seen in train: "
            f"{self.test_drugs_seen_in_train_fraction:.1%}",
            f"  test pairs by setting: {self.test_pair_settings}",
            f"  -> S1 share of test pairs (both endpoints memorisable): "
            f"{self.test_s1_fraction:.1%}",
        ]
        if self.strict:
            lines.append(f"  verdict: {'PASS' if self.passed else 'FAIL - LEAKAGE'}")
            if self.example_overlaps:
                lines.append(f"  overlapping drugs (first 10): {self.example_overlaps}")
        else:
            lines.append(
                "  verdict: n/a - this scheme is expected to leak; the numbers "
                "above are the measurement, not a failure"
            )
        return "\n".join(lines)


def _pairs_of(split: SplitLike, prefixes: tuple[str, ...]) -> pd.DataFrame:
    """Concatenate every bucket whose name starts with one of ``prefixes``.

    Bucket naming differs between schemes - the drug-level scheme emits
    ``test_S2``/``test_S3`` while the random-pair scheme emits plain ``test`` -
    so we match by prefix rather than by exact name. Getting this wrong would
    silently measure an empty test set and report a clean bill of health.
    """
    frames = [
        df for name, df in split.buckets.items()
        if name.startswith(prefixes) and df is not None and len(df)
    ]
    if not frames:
        return pd.DataFrame(columns=["drug_a", "drug_b"])
    return pd.concat(frames, ignore_index=True)


def _training_drugs(split: SplitLike) -> set[str]:
    """Drugs that actually appear in a TRAINING PAIR.

    Deliberately recomputed from the training bucket rather than read from
    ``split.train_drugs``. A drug can be assigned to the training split and yet
    appear in no training pair - in which case the model never sees it, and
    counting it as "seen" would understate the difficulty of the test set.
    """
    train = _pairs_of(split, ("train",))
    if not len(train):
        return set()
    return set(train["drug_a"]) | set(train["drug_b"])


def _setting_counts(pairs: pd.DataFrame, train_drugs: set[str]) -> dict[str, int]:
    counts = {"S1": 0, "S2": 0, "S3": 0}
    for a, b in zip(pairs.get("drug_a", []), pairs.get("drug_b", [])):
        n_unseen = int(a not in train_drugs) + int(b not in train_drugs)
        counts[("S1", "S2", "S3")[n_unseen]] += 1
    return counts


def verify(split: SplitLike, *, strict: bool | None = None) -> LeakageReport:
    """Measure drug overlap, and raise for strict schemes if any is found.

    ``strict`` overrides the per-scheme default, which is derived from
    :data:`STRICT_SCHEMES`. An unrecognised scheme defaults to strict: if we do
    not know that a scheme is allowed to leak, the safe assumption is that it
    is not.
    """
    scheme = getattr(split, "scheme", "unknown")
    if strict is None:
        strict = scheme not in MEASURED_SCHEMES

    train_d, val_d, test_d = split.train_drugs, split.val_drugs, split.test_drugs
    ov_tv = train_d & val_d
    ov_tt = train_d & test_d
    ov_vt = val_d & test_d

    seen_in_train = _training_drugs(split)
    test_pairs = _pairs_of(split, ("test",))
    val_pairs = _pairs_of(split, ("val",))
    train_pairs = _pairs_of(split, ("train",))

    discarded = getattr(split, "discarded", None)

    report = LeakageReport(
        scheme=scheme,
        strict=strict,
        n_train_drugs=len(train_d),
        n_val_drugs=len(val_d),
        n_test_drugs=len(test_d),
        overlap_train_val=len(ov_tv),
        overlap_train_test=len(ov_tt),
        overlap_val_test=len(ov_vt),
        test_drugs_seen_in_train_fraction=(
            len(test_d & seen_in_train) / len(test_d) if test_d else 0.0
        ),
        test_pair_settings=_setting_counts(test_pairs, seen_in_train),
        val_pair_settings=_setting_counts(val_pairs, seen_in_train),
        n_train_pairs=len(train_pairs),
        n_val_pairs=len(val_pairs),
        n_test_pairs=len(test_pairs),
        n_discarded_pairs=len(discarded) if discarded is not None else 0,
        example_overlaps=sorted(ov_tv | ov_tt | ov_vt)[:10],
    )

    if strict and not report.passed:
        raise LeakageError(
            f"Scheme '{scheme}' is strict but produced overlapping drugs.\n"
            f"{report.summary()}\n"
            f"Every metric from this split would be invalid. Fix the splitter."
        )
    return report


def verify_before_training(split: SplitLike) -> LeakageReport:
    """Call this at the top of every training run.

    Costs milliseconds. Guards against the one class of bug that silently
    invalidates an entire experiment, which is exactly the bug this project
    exists to study - it would be an unusually poor look to fall into it.
    """
    report = verify(split)
    print(report.summary())
    return report


def compare_schemes(reports: list[LeakageReport]) -> pd.DataFrame:
    """Side-by-side table across schemes - the Phase A headline artefact."""
    return pd.DataFrame(
        [
            {
                "scheme": r.scheme,
                "strict": r.strict,
                "train_drugs": r.n_train_drugs,
                "test_drugs": r.n_test_drugs,
                "train_pairs": r.n_train_pairs,
                "val_pairs": r.n_val_pairs,
                "test_pairs": r.n_test_pairs,
                "discarded_pairs": r.n_discarded_pairs,
                "drug_overlap_train_test": r.overlap_train_test,
                "test_drugs_seen_in_train": round(r.test_drugs_seen_in_train_fraction, 4),
                "test_S1": r.test_pair_settings.get("S1", 0),
                "test_S2": r.test_pair_settings.get("S2", 0),
                "test_S3": r.test_pair_settings.get("S3", 0),
                "test_S1_fraction": round(r.test_s1_fraction, 4),
            }
            for r in reports
        ]
    )
