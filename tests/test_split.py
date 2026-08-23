"""Tests for the leakage-free drug-level split.

The whole scientific claim of this project rests on the split being correct,
so these tests assert the invariants directly rather than trusting the report.
"""
import pytest

from ddinet.data import synthetic_fixture, split as split_mod


@pytest.fixture(scope="module")
def data():
    return synthetic_fixture.load_drugs(), synthetic_fixture.load_pairs()


@pytest.mark.parametrize("group_by", ["drug", "scaffold"])
@pytest.mark.parametrize("seed", [0, 1, 42])
def test_drug_partitions_are_disjoint(data, group_by, seed):
    drugs, pairs = data
    s = split_mod.build_split(drugs, pairs, seed=seed, group_by=group_by)
    assert not (s.train_drugs & s.val_drugs)
    assert not (s.train_drugs & s.test_drugs)
    assert not (s.val_drugs & s.test_drugs)


@pytest.mark.parametrize("group_by", ["drug", "scaffold"])
def test_training_pairs_only_reference_training_drugs(data, group_by):
    """This is THE leakage test. If it fails, every reported metric is invalid."""
    drugs, pairs = data
    s = split_mod.build_split(drugs, pairs, seed=42, group_by=group_by)
    train = s.buckets["train"]
    used = set(train["drug_a"]) | set(train["drug_b"])
    assert used <= s.train_drugs


def test_s2_pairs_have_exactly_one_unseen_drug(data):
    drugs, pairs = data
    s = split_mod.build_split(drugs, pairs, seed=42)
    for bucket in ("val_S2", "test_S2"):
        for a, b in zip(s.buckets[bucket]["drug_a"], s.buckets[bucket]["drug_b"]):
            n_unseen = (a not in s.train_drugs) + (b not in s.train_drugs)
            assert n_unseen == 1, f"{bucket}: ({a},{b}) has {n_unseen} unseen drugs"


def test_s3_pairs_have_two_unseen_drugs(data):
    drugs, pairs = data
    s = split_mod.build_split(drugs, pairs, seed=42)
    for bucket in ("val_S3", "test_S3"):
        for a, b in zip(s.buckets[bucket]["drug_a"], s.buckets[bucket]["drug_b"]):
            assert a not in s.train_drugs and b not in s.train_drugs


def test_no_val_test_straddling_pair_survives(data):
    """A pair with one val drug and one test drug must be discarded, not used."""
    drugs, pairs = data
    s = split_mod.build_split(drugs, pairs, seed=42)
    for bucket, df in s.buckets.items():
        for a, b in zip(df["drug_a"], df["drug_b"]):
            sides = {s.split_of(a), s.split_of(b)}
            assert sides != {"val", "test"}


def test_split_is_deterministic(data):
    drugs, pairs = data
    a = split_mod.build_split(drugs, pairs, seed=7)
    b = split_mod.build_split(drugs, pairs, seed=7)
    assert a.train_drugs == b.train_drugs
    assert a.test_drugs == b.test_drugs


def test_different_seeds_give_different_splits(data):
    drugs, pairs = data
    a = split_mod.build_split(drugs, pairs, seed=1)
    b = split_mod.build_split(drugs, pairs, seed=2)
    assert a.test_drugs != b.test_drugs


def test_scaffold_split_keeps_analogues_together(data):
    """Simvastatin and lovastatin differ by one methyl; they must not span splits."""
    drugs, pairs = data
    groups = split_mod.assign_groups(drugs, "scaffold")
    assert groups["simvastatin"] == groups["lovastatin"]
    s = split_mod.build_split(drugs, pairs, seed=42, group_by="scaffold")
    assert s.split_of("simvastatin") == s.split_of("lovastatin")


def test_kfold_folds_are_mutually_disjoint(data):
    drugs, pairs = data
    folds = split_mod.drug_level_kfold(drugs, pairs, n_folds=5, seed=0)
    assert len(folds) == 5
    test_sets = [f.test_drugs for f in folds]
    for i in range(len(test_sets)):
        for j in range(i + 1, len(test_sets)):
            assert not (test_sets[i] & test_sets[j]), "CV folds overlap"


def test_kfold_covers_every_drug_exactly_once(data):
    drugs, pairs = data
    folds = split_mod.drug_level_kfold(drugs, pairs, n_folds=5, seed=0)
    covered = set().union(*(f.test_drugs for f in folds))
    assert covered == set(drugs["name"])
