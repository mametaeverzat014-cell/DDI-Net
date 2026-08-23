"""Tests for negative sampling and dataset assembly."""
import numpy as np
import pytest

from ddinet.data import assemble, curated, split as split_mod


@pytest.fixture(scope="module")
def built():
    drugs, pairs = curated.load_drugs(), curated.load_pairs()
    keys = set(pairs["pair_key"])
    sp = split_mod.build_split(drugs, pairs, seed=42)
    return drugs, pairs, keys, sp


@pytest.mark.parametrize("strategy", ["uniform", "degree_matched"])
def test_no_sampled_negative_is_a_documented_interaction(built, strategy):
    """The most damaging silent bug this pipeline could have."""
    _, _, keys, sp = built
    cfg = assemble.AssemblyConfig(strategy=strategy, seed=3)
    ds = assemble.build_supervised_dataset(sp, keys, cfg)
    assemble.verify_no_negative_is_positive(ds, keys)


def test_negatives_respect_their_bucket_drug_scope(built):
    """A test_S2 negative must look exactly like a test_S2 positive.

    If negatives came from a different drug scope, the model could separate
    the classes by scope alone - a leak that is invisible in the metrics.
    """
    _, _, keys, sp = built
    ds = assemble.build_supervised_dataset(sp, keys, assemble.AssemblyConfig(seed=3))
    for row in ds.itertuples():
        sides = {sp.split_of(row.drug_a), sp.split_of(row.drug_b)}
        expected = {
            "train": {"train"},
            "val_S2": {"train", "val"},
            "val_S3": {"val"},
            "test_S2": {"train", "test"},
            "test_S3": {"test"},
        }[row.bucket]
        assert sides == expected, f"{row.bucket}: ({row.drug_a},{row.drug_b}) -> {sides}"


def test_no_self_pairs(built):
    _, _, keys, sp = built
    ds = assemble.build_supervised_dataset(sp, keys, assemble.AssemblyConfig(seed=3))
    assert (ds["drug_a"] != ds["drug_b"]).all()


def test_neg_ratio_controls_prevalence(built):
    _, _, keys, sp = built
    for ratio in (1.0, 3.0, 5.0):
        ds = assemble.build_supervised_dataset(
            sp, keys, assemble.AssemblyConfig(neg_ratio=ratio, seed=3)
        )
        train = ds[ds.bucket == "train"]
        observed = (train.label == 1).mean()
        assert abs(observed - 1 / (1 + ratio)) < 0.03


def test_degree_matching_closes_the_degree_gap(built):
    """Uniform negatives leave an exploitable degree shortcut; matched ones do not."""
    _, pairs, keys, sp = built
    degree = {}
    for a, b in keys:
        degree[a] = degree.get(a, 0) + 1
        degree[b] = degree.get(b, 0) + 1

    def gap(strategy):
        ds = assemble.build_supervised_dataset(
            sp, keys, assemble.AssemblyConfig(strategy=strategy, seed=3)
        )
        tr = ds[ds.bucket == "train"]
        means = {}
        for label in (0, 1):
            sub = tr[tr.label == label]
            means[label] = np.mean([degree.get(d, 0) for d in
                                    list(sub.drug_a) + list(sub.drug_b)])
        return means[1] - means[0]

    assert gap("degree_matched") < gap("uniform")


def test_dangerous_only_drops_rather_than_relabels(built):
    """Moderate interactions must never become negatives - they ARE interactions."""
    _, _, keys, sp = built
    ds = assemble.build_supervised_dataset(
        sp, keys, assemble.AssemblyConfig(dangerous_only=True, seed=3)
    )
    positives = ds[ds.label == 1]
    assert set(positives["severity"]) == {"major"}
    assert (ds[ds.label == 0]["severity"] == "").all()
