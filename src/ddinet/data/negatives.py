"""
Negative sampling for a positive-only dataset.

WHY THIS IS A SEPARATE MODULE WITH ITS OWN TESTS
-------------------------------------------------
The TDC DrugBank export contains 191,392 documented interactions and **no
non-interactions at all**. Every binary experiment therefore rests on
negatives we invent, which makes the sampling scheme a first-class
methodological choice rather than a preprocessing detail. Two different schemes
produce two different tasks, and the gap between them is a reportable result -
see ``LIMITATIONS.md`` section 7.

TWO SCHEMES, ONE IMPLEMENTATION
-------------------------------
``uniform``
    Endpoints drawn with equal probability. This is what most of the DDI
    literature does. It leaves a **degree shortcut**: hub drugs (degree up to
    913 here) are over-represented among positives but appear in negatives only
    in proportion to their share of the drug list. A model can then score pairs
    well above chance by answering "are both of these drugs promiscuous?"
    without looking at chemistry at all.

``degree_matched``
    Endpoints drawn in proportion to interaction degree, so the marginal degree
    distribution of negatives matches that of positives and the shortcut
    carries little information. Makes the task harder and the numbers lower -
    which is the point.

The difference between the two, measured with the same model on the same
splits, is a direct estimate of how much apparent skill was degree
memorisation. That is why both are computed and why the strategy is a
parameter rather than two forked code paths that would drift apart.

*** DEGREE IS COMPUTED FROM TRAINING PAIRS ONLY ***

A subtle but real leak: weighting by each drug's degree in the *full* graph
would let the sampler consult test edges, and information about which drugs are
promiscuous in the test set would flow into the training distribution. Degree
here always comes from the training bucket. ``degree_source`` records this so
the choice is visible rather than implicit.

THE SCOPE INVARIANT
-------------------
Negatives for a bucket must be drawn from the **same drug scope as that
bucket's positives**. Under a drug-level split, a ``test_S2`` positive has one
training drug and one test drug; a ``test_S2`` negative must too. If negatives
came from a different scope, a model could separate the classes by split
membership alone - a leak invisible in every metric.

We enforce this generically rather than with a hardcoded table: for each bucket
we count the observed combinations of (split membership of A, split membership
of B) among its positives, then draw negatives reproducing that same
distribution. This works unchanged for the drug-level, scaffold and random-pair
schemes, whose bucket structures differ, and is covered by
``test_negatives.py::test_negatives_preserve_the_membership_profile``.
"""

from __future__ import annotations

import zlib
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Literal

import numpy as np
import pandas as pd

Strategy = Literal["uniform", "degree_matched"]


@dataclass(frozen=True)
class NegativeSamplingConfig:
    """Every knob that changes the produced negatives. Recorded in run logs."""

    strategy: Strategy = "degree_matched"
    ratio: float = 1.0
    seed: int = 0
    #: Where endpoint weights come from. "train" is the only leak-free option;
    #: exposed so that the choice is explicit in the config rather than buried.
    degree_source: Literal["train"] = "train"
    #: Separate seed for the EVALUATION buckets (anything not starting with
    #: "train"). None keeps the original single-stream behaviour bit for bit.
    #:
    #: WHY THIS EXISTS - IT FIXED A DEFECT THAT PRODUCED A NUMBER
    #: ---------------------------------------------------------
    #: A deep ensemble averages member probabilities row by row, which is only
    #: meaningful if row *i* is the same drug pair for every member. The Phase
    #: A-2 ensemble varied `seed` per member "to vary init and negatives", and
    #: that varied the TEST negatives too: members shared their 42,345 test
    #: positives exactly and overlapped on only 23.8% of their test negatives,
    #: with 0% of negative rows landing on the same pair at the same index.
    #:
    #: The label vector was nevertheless byte-identical across members - the
    #: sampler emits positives then negatives, in fixed counts and order - so
    #: the analysis script's `array_equal(y_test)` guard passed and the average
    #: was computed anyway. It inflated AUPRC from 0.7490 to 0.8628 for `gine`
    #: and 0.7034 to 0.8233 for `dual`, because averaging five INDEPENDENT
    #: negative-score draws shrinks the negative score distribution by 1/sqrt(5)
    #: (measured 0.448 against a theoretical 0.447) while the positives, being
    #: the same pairs, shrink only to 0.90. Measured mean pairwise correlation
    #: between members: 0.765 on positives, 0.001 on negatives.
    #:
    #: Setting `eval_seed` pins the evaluation negatives across members while
    #: `seed` still varies the training negatives, which is the only
    #: arrangement in which "members differ in their negatives" and "member
    #: predictions may be averaged" are both true.
    #:
    #: DEFAULT-OFF ON PURPOSE. When None the sampler follows the original code
    #: path exactly, because turning it on changes which negatives are drawn and
    #: the Phase A-2 grid must stay reproducible from its recorded config.
    eval_seed: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SamplingReport:
    """What the sampler actually produced, per bucket."""

    bucket: str
    n_positive: int
    n_negative_requested: int
    n_negative_drawn: int
    n_attempts: int
    membership_profile: dict[str, int]
    exhausted: bool

    def summary(self) -> str:
        shortfall = self.n_negative_requested - self.n_negative_drawn
        note = f"  SHORTFALL {shortfall}" if shortfall else ""
        return (
            f"  {self.bucket:10s} pos={self.n_positive:6d} "
            f"neg={self.n_negative_drawn:6d}/{self.n_negative_requested:6d} "
            f"attempts={self.n_attempts:8d}{note}"
        )


# --------------------------------------------------------------------------
# Scope handling
# --------------------------------------------------------------------------

def membership_profile(split, bucket_pairs: pd.DataFrame) -> Counter:
    """Count (membership of A, membership of B) combinations among positives.

    Memberships are sorted so that ('train', 'test') and ('test', 'train') are
    the same combination - the pair itself is unordered, so the profile must be
    too.
    """
    profile: Counter = Counter()
    for a, b in zip(bucket_pairs["drug_a"], bucket_pairs["drug_b"]):
        combo = tuple(sorted((split.split_of(a), split.split_of(b))))
        profile[combo] += 1
    return profile


def _membership_pools(split, drug_names: list[str]) -> dict[str, np.ndarray]:
    """Drug indices grouped by which split they belong to."""
    pools: dict[str, list[int]] = {}
    for i, name in enumerate(drug_names):
        pools.setdefault(split.split_of(name), []).append(i)
    return {k: np.asarray(v, dtype=np.int64) for k, v in pools.items()}


def _training_degree(train_pairs: pd.DataFrame, drug_names: list[str]) -> np.ndarray:
    """Interaction degree from TRAINING pairs only. See module docstring."""
    index = {name: i for i, name in enumerate(drug_names)}
    degree = np.zeros(len(drug_names), dtype=np.float64)
    for a, b in zip(train_pairs["drug_a"], train_pairs["drug_b"]):
        ia, ib = index.get(a), index.get(b)
        if ia is not None:
            degree[ia] += 1
        if ib is not None:
            degree[ib] += 1
    return degree


def _weights_for(pool: np.ndarray, degree: np.ndarray, strategy: Strategy) -> np.ndarray | None:
    """Sampling weights over a pool, or ``None`` for uniform.

    Degree gets +1 smoothing so a drug with no training interactions can still
    be sampled. Without it such drugs would never appear as negatives and the
    model would never see them - which matters most in exactly the S2/S3
    settings where test drugs have zero training degree.
    """
    if strategy == "uniform":
        return None
    if strategy != "degree_matched":
        raise ValueError(f"Unknown strategy {strategy!r}")
    w = degree[pool] + 1.0
    return w / w.sum()


def _draw(rng: np.random.Generator, pool: np.ndarray,
          cumulative: np.ndarray | None, size: int) -> np.ndarray:
    """Draw ``size`` pool entries, weighted or uniform.

    Weighted draws use a precomputed cumulative distribution plus
    ``searchsorted`` rather than ``rng.choice(p=...)``, which re-normalises the
    weight vector on every call. At ~100k draws per bucket that difference is
    the gap between seconds and minutes.
    """
    if cumulative is None:
        return pool[rng.integers(0, len(pool), size)]
    return pool[np.searchsorted(cumulative, rng.random(size))]


# --------------------------------------------------------------------------
# Sampling
# --------------------------------------------------------------------------

def sample_negatives(
    split,
    drug_names: list[str],
    forbidden: set[tuple[str, str]],
    bucket: str,
    bucket_pairs: pd.DataFrame,
    train_pairs: pd.DataFrame,
    config: NegativeSamplingConfig,
    rng: np.random.Generator,
) -> tuple[list[tuple[str, str]], SamplingReport]:
    """Draw negatives for one bucket, preserving its membership profile.

    ``forbidden`` must contain **every known positive in the whole dataset**,
    not just this bucket's. A pair that is a documented interaction elsewhere
    must never be drawn as a negative here - that would be a straightforward
    label error.

    Rejection sampling in batches rather than enumerating all non-edges: the
    complete non-edge set is ~1.26M pairs here and would be far larger on any
    bigger graph, so materialising it is the wrong shape of solution.
    """
    profile = membership_profile(split, bucket_pairs)
    pools = _membership_pools(split, drug_names)
    degree = _training_degree(train_pairs, drug_names)

    collected: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    attempts = 0
    exhausted = False

    for combo, count in sorted(profile.items()):
        want = int(round(count * config.ratio))
        if want <= 0:
            continue
        m_a, m_b = combo
        pool_a, pool_b = pools.get(m_a), pools.get(m_b)
        if pool_a is None or pool_b is None or not len(pool_a) or not len(pool_b):
            continue

        w_a = _weights_for(pool_a, degree, config.strategy)
        w_b = _weights_for(pool_b, degree, config.strategy)
        cum_a = np.cumsum(w_a) if w_a is not None else None
        cum_b = np.cumsum(w_b) if w_b is not None else None

        got = 0
        # Generous but bounded: a bucket whose pools are nearly saturated with
        # positives can legitimately fail to supply enough negatives, and we
        # report that rather than spinning forever.
        max_attempts = max(20 * want, 100_000)
        batch = max(4096, min(want * 2, 200_000))

        while got < want and attempts < max_attempts:
            take = min(batch, (want - got) * 3)
            ia = _draw(rng, pool_a, cum_a, take)
            ib = _draw(rng, pool_b, cum_b, take)
            attempts += take
            for x, y in zip(ia, ib):
                if x == y:
                    continue
                a, b = drug_names[x], drug_names[y]
                key = (a, b) if a < b else (b, a)
                if key in forbidden or key in seen:
                    continue
                seen.add(key)
                collected.append(key)
                got += 1
                if got >= want:
                    break
        if got < want:
            exhausted = True

    return collected, SamplingReport(
        bucket=bucket,
        n_positive=len(bucket_pairs),
        n_negative_requested=int(round(len(bucket_pairs) * config.ratio)),
        n_negative_drawn=len(collected),
        n_attempts=attempts,
        membership_profile={"+".join(k): v for k, v in sorted(profile.items())},
        exhausted=exhausted,
    )


def build_dataset(
    split,
    drug_names: list[str],
    all_positive_keys: set[tuple[str, str]],
    config: NegativeSamplingConfig | None = None,
) -> tuple[pd.DataFrame, list[SamplingReport]]:
    """Assemble a labelled dataset for every bucket of any split scheme.

    Works unchanged for drug-level, scaffold and random-pair splits: bucket
    names are read from the split rather than assumed, and each bucket's
    negative scope is inferred from its own positives.

    Returns ``(dataset, reports)``. The dataset has columns ``drug_a``,
    ``drug_b``, ``label``, ``bucket``, ``setting``.
    """
    cfg = config or NegativeSamplingConfig()

    # One shared stream when eval_seed is None - the original behaviour, kept
    # bit-identical so every recorded Phase A-2 config still reproduces. With
    # eval_seed set, each bucket gets its own stream keyed by the bucket name,
    # so the evaluation buckets are independent of how many negatives the
    # training bucket happened to draw first. crc32 rather than hash(): Python's
    # hash is salted per process and would make the draw irreproducible.
    shared_rng = np.random.default_rng(cfg.seed) if cfg.eval_seed is None else None

    def rng_for(bucket: str) -> np.random.Generator:
        if shared_rng is not None:
            return shared_rng
        base = cfg.seed if bucket.startswith("train") else cfg.eval_seed
        return np.random.default_rng([base, zlib.crc32(bucket.encode("utf-8"))])

    train_pairs = pd.concat(
        [df for name, df in split.buckets.items() if name.startswith("train")],
        ignore_index=True,
    ) if any(n.startswith("train") for n in split.buckets) else pd.DataFrame(
        columns=["drug_a", "drug_b"]
    )

    frames: list[pd.DataFrame] = []
    reports: list[SamplingReport] = []

    for bucket in sorted(split.buckets):
        positives = split.buckets[bucket]
        if positives is None or len(positives) == 0:
            continue

        negatives, report = sample_negatives(
            split, drug_names, all_positive_keys, bucket, positives,
            train_pairs, cfg, rng_for(bucket),
        )
        reports.append(report)

        pos = pd.DataFrame(
            {"drug_a": positives["drug_a"].to_numpy(),
             "drug_b": positives["drug_b"].to_numpy(), "label": 1}
        )
        neg = pd.DataFrame(
            {"drug_a": [k[0] for k in negatives],
             "drug_b": [k[1] for k in negatives], "label": 0}
        )
        combined = pd.concat([pos, neg], ignore_index=True)
        combined["bucket"] = bucket
        combined["setting"] = [
            split.setting_of(a, b)
            for a, b in zip(combined["drug_a"], combined["drug_b"])
        ]
        frames.append(combined)

    if not frames:
        return pd.DataFrame(columns=["drug_a", "drug_b", "label", "bucket", "setting"]), []
    dataset = pd.concat(frames, ignore_index=True)
    dataset.attrs["negative_sampling"] = cfg.to_dict()
    return dataset, reports


def verify_no_negative_is_positive(
    dataset: pd.DataFrame, all_positive_keys: set[tuple[str, str]]
) -> None:
    """Assert no sampled negative is a documented interaction. Run every time.

    This catches the most damaging silent bug available here: a label error
    that either flatters the model or, if it lands in training, actively
    teaches it the wrong thing.
    """
    negs = dataset.loc[dataset["label"] == 0]
    offenders = [
        (a, b) for a, b in zip(negs["drug_a"], negs["drug_b"])
        if ((a, b) if a < b else (b, a)) in all_positive_keys
    ]
    if offenders:
        raise AssertionError(
            f"{len(offenders)} sampled negatives are documented interactions, "
            f"e.g. {offenders[:5]}"
        )


def dataset_summary(dataset: pd.DataFrame) -> str:
    lines = ["Assembled dataset", f"  total examples: {len(dataset):,}"]
    for bucket, grp in dataset.groupby("bucket", sort=True):
        n_pos = int((grp["label"] == 1).sum())
        prevalence = n_pos / len(grp) if len(grp) else 0.0
        settings = dict(Counter(grp["setting"]))
        lines.append(
            f"  {bucket:10s} n={len(grp):7,d} pos={n_pos:6,d} "
            f"prevalence={prevalence:.3f} settings={settings}"
        )
    lines.append("  (prevalence = AUPRC of a random classifier - always quote it)")
    return "\n".join(lines)
