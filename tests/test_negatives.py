"""Tests for negative sampling.

The dataset has no negatives at all, so every one is invented here. That makes
this module the place where a silent methodological error would do the most
damage, and it is why the scope invariant gets a dedicated test.
"""
import numpy as np
import pandas as pd
import pytest

from ddinet.data import (
    negatives as neg, split as split_mod, synthetic_fixture, tdc_drugbank as tdc,
)


@pytest.fixture(scope="module")
def fixture_env():
    drugs = synthetic_fixture.load_drugs()
    pairs = synthetic_fixture.load_pairs()
    return drugs, pairs, list(drugs["name"]), set(pairs["pair_key"])


@pytest.mark.parametrize("scheme", ["random_pair", "drug", "scaffold"])
@pytest.mark.parametrize("strategy", ["uniform", "degree_matched"])
def test_no_sampled_negative_is_a_documented_interaction(fixture_env, scheme, strategy):
    """The most damaging silent bug available: a straightforward label error."""
    drugs, pairs, names, keys = fixture_env
    sp = split_mod.build_any(scheme, drugs, pairs, seed=0)
    ds, _ = neg.build_dataset(sp, names, keys,
                              neg.NegativeSamplingConfig(strategy=strategy, seed=1))
    neg.verify_no_negative_is_positive(ds, keys)


@pytest.mark.parametrize("scheme", ["random_pair", "drug", "scaffold"])
@pytest.mark.parametrize("strategy", ["uniform", "degree_matched"])
def test_negatives_preserve_the_membership_profile(fixture_env, scheme, strategy):
    """THE SCOPE INVARIANT.

    Within each bucket, negatives must show the same distribution of
    (split membership of A, split membership of B) as the positives. If they did
    not, a model could separate the classes by split membership alone - a leak
    that no metric would reveal.
    """
    drugs, pairs, names, keys = fixture_env
    sp = split_mod.build_any(scheme, drugs, pairs, seed=0)
    ds, _ = neg.build_dataset(sp, names, keys,
                              neg.NegativeSamplingConfig(strategy=strategy, seed=1))

    for bucket, grp in ds.groupby("bucket"):
        def profile(frame):
            return neg.membership_profile(sp, frame)

        pos_profile = profile(grp[grp.label == 1])
        neg_profile = profile(grp[grp.label == 0])
        assert set(neg_profile) <= set(pos_profile), (
            f"{bucket}: negatives use membership combinations absent from "
            f"positives: {set(neg_profile) - set(pos_profile)}"
        )
        total_pos = sum(pos_profile.values())
        total_neg = sum(neg_profile.values())
        if total_neg == 0:
            continue
        for combo, count in pos_profile.items():
            expected = count / total_pos
            observed = neg_profile.get(combo, 0) / total_neg
            assert abs(expected - observed) < 0.02, (
                f"{bucket}/{combo}: positives {expected:.3f} vs "
                f"negatives {observed:.3f}"
            )


def test_negatives_never_pair_a_drug_with_itself(fixture_env):
    drugs, pairs, names, keys = fixture_env
    sp = split_mod.build_any("drug", drugs, pairs, seed=0)
    ds, _ = neg.build_dataset(sp, names, keys, neg.NegativeSamplingConfig(seed=1))
    assert (ds["drug_a"] != ds["drug_b"]).all()


def test_ratio_controls_prevalence(fixture_env):
    drugs, pairs, names, keys = fixture_env
    sp = split_mod.build_any("drug", drugs, pairs, seed=0)
    for ratio in (1.0, 3.0):
        ds, _ = neg.build_dataset(
            sp, names, keys, neg.NegativeSamplingConfig(ratio=ratio, seed=1))
        train = ds[ds.bucket.str.startswith("train")]
        assert abs((train.label == 1).mean() - 1 / (1 + ratio)) < 0.03


def test_degree_matched_shifts_negative_degrees_upward(fixture_env):
    """Degree matching should move negative endpoints toward the positive
    degree distribution; uniform leaves a gap the model can exploit."""
    drugs, pairs, names, keys = fixture_env
    sp = split_mod.build_any("random_pair", drugs, pairs, seed=0)
    degree = {}
    for a, b in keys:
        degree[a] = degree.get(a, 0) + 1
        degree[b] = degree.get(b, 0) + 1

    def gap(strategy):
        ds, _ = neg.build_dataset(
            sp, names, keys, neg.NegativeSamplingConfig(strategy=strategy, seed=1))
        tr = ds[ds.bucket.str.startswith("train")]
        means = {}
        for label in (0, 1):
            sub = tr[tr.label == label]
            means[label] = np.mean([degree.get(d, 0)
                                    for d in list(sub.drug_a) + list(sub.drug_b)])
        return means[1] - means[0]

    assert gap("degree_matched") < gap("uniform")


def test_degree_weights_come_from_training_pairs_only(fixture_env):
    """Weighting by full-graph degree would leak test connectivity into the
    training distribution. The config records the source explicitly."""
    drugs, pairs, names, keys = fixture_env
    sp = split_mod.build_split(drugs, pairs, seed=0)
    train = sp.buckets["train"]
    degree = neg._training_degree(train, names)
    index = {n: i for i, n in enumerate(names)}
    for drug in sp.test_drugs:
        assert degree[index[drug]] == 0, (
            f"{drug} is a test drug but has nonzero training degree"
        )
    assert neg.NegativeSamplingConfig().degree_source == "train"


def test_sampling_is_deterministic(fixture_env):
    drugs, pairs, names, keys = fixture_env
    sp = split_mod.build_split(drugs, pairs, seed=0)
    cfg = neg.NegativeSamplingConfig(seed=5)
    a, _ = neg.build_dataset(sp, names, keys, cfg)
    b, _ = neg.build_dataset(sp, names, keys, cfg)
    pd.testing.assert_frame_equal(a, b)


def test_different_seeds_give_different_negatives(fixture_env):
    drugs, pairs, names, keys = fixture_env
    sp = split_mod.build_split(drugs, pairs, seed=0)
    a, _ = neg.build_dataset(sp, names, keys, neg.NegativeSamplingConfig(seed=1))
    b, _ = neg.build_dataset(sp, names, keys, neg.NegativeSamplingConfig(seed=2))
    neg_a = set(zip(a[a.label == 0].drug_a, a[a.label == 0].drug_b))
    neg_b = set(zip(b[b.label == 0].drug_a, b[b.label == 0].drug_b))
    assert neg_a != neg_b


def test_positives_are_never_altered(fixture_env):
    """Sampling must add rows, not touch the documented interactions."""
    drugs, pairs, names, keys = fixture_env
    sp = split_mod.build_split(drugs, pairs, seed=0)
    ds, _ = neg.build_dataset(sp, names, keys, neg.NegativeSamplingConfig(seed=1))
    got = set(zip(ds[ds.label == 1].drug_a, ds[ds.label == 1].drug_b))
    expected = {
        (a, b) for bucket, df in sp.buckets.items()
        for a, b in zip(df["drug_a"], df["drug_b"])
    }
    assert got == expected


def test_reports_flag_a_shortfall(fixture_env):
    """A bucket that cannot supply enough negatives must say so, not silently
    return fewer."""
    drugs, pairs, names, keys = fixture_env
    sp = split_mod.build_split(drugs, pairs, seed=0)
    _, reports = neg.build_dataset(
        sp, names, keys, neg.NegativeSamplingConfig(ratio=500.0, seed=1))
    assert any(r.exhausted for r in reports)
    assert any(r.n_negative_drawn < r.n_negative_requested for r in reports)


@pytest.mark.skipif(not tdc.DEFAULT_PATH.exists(), reason="TDC export not present")
def test_scope_invariant_holds_on_the_real_data():
    """Same invariant, on 1,705 drugs and 191,392 pairs."""
    drugs, pairs, _ = tdc.load_modelling_data()
    names, keys = list(drugs["name"]), set(pairs["pair_key"])
    sp = split_mod.build_split(drugs, pairs, seed=0)
    ds, _ = neg.build_dataset(sp, names, keys, neg.NegativeSamplingConfig(seed=0))
    neg.verify_no_negative_is_positive(ds, keys)
    for bucket, grp in ds.groupby("bucket"):
        pos = neg.membership_profile(sp, grp[grp.label == 1])
        negp = neg.membership_profile(sp, grp[grp.label == 0])
        assert set(negp) <= set(pos), bucket
