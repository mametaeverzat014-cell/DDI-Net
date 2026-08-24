"""Tests for the three-mode leakage verifier.

The project's claim is that published DDI metrics are inflated by leakage. That
claim is only credible if our own verifier demonstrably works - so these tests
check both that it PASSES clean splits and that it FAILS dirty ones. A verifier
that never fires is indistinguishable from no verifier at all.
"""
import pandas as pd
import pytest

from ddinet.data import leakage, split as split_mod, synthetic_fixture, tdc_drugbank as tdc


@pytest.fixture(scope="module")
def fixture_data():
    return synthetic_fixture.load_drugs(), synthetic_fixture.load_pairs()


# -- Strict schemes ---------------------------------------------------------

@pytest.mark.parametrize("scheme", ["drug", "scaffold"])
def test_strict_schemes_pass_and_have_zero_overlap(fixture_data, scheme):
    drugs, pairs = fixture_data
    sp = split_mod.build_any(scheme, drugs, pairs, seed=42)
    rep = leakage.verify(sp)
    assert rep.strict
    assert rep.passed
    assert rep.total_drug_overlap == 0
    assert rep.test_s1_fraction == 0.0


@pytest.mark.parametrize("scheme", ["drug", "scaffold"])
def test_strict_schemes_have_no_s1_test_pairs(fixture_data, scheme):
    """Under a drug-level split no test pair can have both endpoints trained on."""
    drugs, pairs = fixture_data
    rep = leakage.verify(split_mod.build_any(scheme, drugs, pairs, seed=7))
    assert rep.test_pair_settings["S1"] == 0


def test_verifier_raises_on_a_deliberately_dirty_split(fixture_data):
    """Prove the guard fires. A verifier that never fails proves nothing."""
    drugs, pairs = fixture_data
    sp = split_mod.build_split(drugs, pairs, seed=42, group_by="drug")
    # Contaminate: move one training drug into the test set as well.
    stolen = sorted(sp.train_drugs)[0]
    sp.test_drugs.add(stolen)
    with pytest.raises(leakage.LeakageError, match="strict"):
        leakage.verify(sp)


def test_dirty_split_report_names_the_offending_drug(fixture_data):
    drugs, pairs = fixture_data
    sp = split_mod.build_split(drugs, pairs, seed=42)
    stolen = sorted(sp.train_drugs)[0]
    sp.test_drugs.add(stolen)
    rep = leakage.verify(sp, strict=False)      # measure instead of raising
    assert not rep.passed or rep.overlap_train_test == 1
    assert stolen in rep.example_overlaps


def test_unknown_scheme_defaults_to_strict(fixture_data):
    """If we don't know a scheme may leak, assume it may not."""
    drugs, pairs = fixture_data
    sp = split_mod.build_split(drugs, pairs, seed=42)
    object.__setattr__(sp, "group_by", "some_new_scheme")
    assert leakage.verify(sp).strict


# -- Measured scheme --------------------------------------------------------

def test_random_pair_split_reports_instead_of_raising(fixture_data):
    """The leaky scheme must run: it is the object of measurement."""
    drugs, pairs = fixture_data
    sp = split_mod.build_random_pair_split(drugs, pairs, seed=0)
    rep = leakage.verify(sp)                    # must not raise
    assert not rep.strict
    assert rep.passed                           # "passed" is vacuous here
    assert rep.overlap_train_test > 0


def test_random_pair_split_leaks_almost_every_test_pair(fixture_data):
    """The quantity that matters: share of test pairs with both endpoints seen."""
    drugs, pairs = fixture_data
    rep = leakage.verify(split_mod.build_random_pair_split(drugs, pairs, seed=0))
    assert rep.test_s1_fraction > 0.8
    assert rep.test_drugs_seen_in_train_fraction > 0.8


def test_random_pair_split_discards_nothing(fixture_data):
    """Unlike the strict schemes, which throw away straddling pairs."""
    drugs, pairs = fixture_data
    sp = split_mod.build_random_pair_split(drugs, pairs, seed=0)
    assert len(sp.discarded) == 0
    total = sum(len(b) for b in sp.buckets.values())
    assert total == len(pairs)


def test_random_pair_split_is_deterministic(fixture_data):
    drugs, pairs = fixture_data
    a = split_mod.build_random_pair_split(drugs, pairs, seed=3)
    b = split_mod.build_random_pair_split(drugs, pairs, seed=3)
    assert list(a.buckets["test"]["pair_key"]) == list(b.buckets["test"]["pair_key"])


def test_different_seeds_give_different_random_pair_splits(fixture_data):
    drugs, pairs = fixture_data
    a = split_mod.build_random_pair_split(drugs, pairs, seed=1)
    b = split_mod.build_random_pair_split(drugs, pairs, seed=2)
    assert list(a.buckets["test"]["pair_key"]) != list(b.buckets["test"]["pair_key"])


# -- Bucket-name handling ---------------------------------------------------

def test_verifier_matches_buckets_by_prefix(fixture_data):
    """Schemes name buckets differently; matching by exact name would measure
    an empty test set and wrongly report a clean bill of health."""
    drugs, pairs = fixture_data
    drug_split = split_mod.build_split(drugs, pairs, seed=42)      # test_S2/test_S3
    pair_split = split_mod.build_random_pair_split(drugs, pairs, seed=0)  # test
    assert leakage.verify(drug_split).n_test_pairs > 0
    assert leakage.verify(pair_split).n_test_pairs > 0


def test_comparison_table_has_one_row_per_report(fixture_data):
    drugs, pairs = fixture_data
    reps = [leakage.verify(split_mod.build_any(s, drugs, pairs, seed=0))
            for s in ("random_pair", "drug", "scaffold")]
    table = leakage.compare_schemes(reps)
    assert len(table) == 3
    assert set(table["scheme"]) == {"random_pair", "drug", "scaffold"}
    assert table["test_S1_fraction"].between(0, 1).all()


# -- Real data --------------------------------------------------------------

@pytest.mark.skipif(not tdc.DEFAULT_PATH.exists(), reason="TDC export not present")
def test_real_data_random_pair_split_leaks_nearly_completely():
    """On the real graph the leak is near-total: mean degree is ~224, so a
    pair-level shuffle leaves both endpoints of almost every test pair in
    training. This is the number Phase A exists to report."""
    drugs, pairs = tdc.load_drugs(), tdc.load_pairs()
    rep = leakage.verify(split_mod.build_random_pair_split(drugs, pairs, seed=0))
    assert rep.test_s1_fraction > 0.99


@pytest.mark.skipif(not tdc.DEFAULT_PATH.exists(), reason="TDC export not present")
@pytest.mark.parametrize("scheme", ["drug", "scaffold"])
def test_real_data_strict_schemes_are_clean(scheme):
    drugs, pairs = tdc.load_drugs(), tdc.load_pairs()
    rep = leakage.verify(split_mod.build_any(scheme, drugs, pairs, seed=0))
    assert rep.total_drug_overlap == 0
    assert rep.test_pair_settings["S1"] == 0
    assert rep.n_discarded_pairs > 0     # straddling pairs are thrown away
