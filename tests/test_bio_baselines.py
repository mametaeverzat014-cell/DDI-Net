"""Tests for CONTROL A (biological-degree RF) and BIO-RF.

The leakage tests are the load-bearing ones. A biological baseline whose SVD saw
the held-out drugs would beat BIO-GINE for a reason that has nothing to do with
biology, and the failure leaves no trace in any metric.
"""
import numpy as np
import pytest
from scipy import sparse

from ddinet.data.biology import COUNT_FEATURES, EVIDENCE_POLICIES, BiologyBundle
from ddinet.models.bio_baselines import (
    BiologicalDegreeRF,
    BiologicalFeaturizer,
    BioRF,
    _multi_hot,
    _pair_terms,
)
from ddinet.models.classical import PairBatch


@pytest.fixture
def bundle() -> BiologyBundle:
    rng = np.random.default_rng(0)
    n, n_prot, n_path = 40, 12, 9
    protein_items, pathway_items = [], []
    for i in range(n):
        k = int(rng.integers(0, 5))
        ids = rng.choice(n_prot, size=k, replace=False)
        protein_items.append(
            np.stack([ids, np.zeros(k, int), np.zeros(k, int)], axis=1).astype(np.int64)
            if k else np.zeros((0, 3), dtype=np.int64)
        )
        j = int(rng.integers(0, 4))
        pathway_items.append(
            np.sort(rng.choice(n_path, size=j, replace=False)).astype(np.int64)
            if j else np.zeros(0, dtype=np.int64)
        )
    counts = np.zeros((n, len(COUNT_FEATURES)))
    counts[:, COUNT_FEATURES.index("n_proteins")] = [len(x) for x in protein_items]
    counts[:, COUNT_FEATURES.index("n_pathways")] = [len(x) for x in pathway_items]
    return BiologyBundle(
        drug_ids=[f"D{i}" for i in range(n)],
        protein_vocab=[f"P{i}" for i in range(n_prot)],
        pathway_vocab=[f"Q{i}" for i in range(n_path)],
        protein_items=protein_items,
        pathway_items=pathway_items,
        counts=counts,
        policy=EVIDENCE_POLICIES["M4"],
    )


@pytest.fixture
def batch(bundle):
    rng = np.random.default_rng(1)
    train = bundle.drug_ids[:30]
    a = rng.choice(train, 200)
    b = rng.choice(train, 200)
    y = rng.integers(0, 2, 200)
    return PairBatch(drug_a=a, drug_b=b, y=y), train


# -- pair terms -----------------------------------------------------------
def test_pair_terms_are_commutative():
    a, b = np.random.default_rng(0).normal(size=(2, 5, 3))
    assert np.allclose(_pair_terms(a, b), _pair_terms(b, a))


def test_pair_terms_width_is_three_times_the_drug_block():
    a = np.zeros((4, 7))
    assert _pair_terms(a, a).shape == (4, 21)


# -- multi-hot ------------------------------------------------------------
def test_multi_hot_is_binary_not_a_count(bundle):
    dup = list(bundle.protein_items)
    dup[0] = np.array([[0, 0, 0], [0, 1, 1], [0, 2, 2]], dtype=np.int64)
    b2 = BiologyBundle(bundle.drug_ids, bundle.protein_vocab, bundle.pathway_vocab,
                       dup, bundle.pathway_items, bundle.counts, bundle.policy)
    m = _multi_hot(b2, "protein")
    assert m[0, 0] == 1.0
    assert set(np.unique(m.toarray())) <= {0.0, 1.0}


def test_multi_hot_shape_follows_the_vocabulary(bundle):
    assert _multi_hot(bundle, "protein").shape == (bundle.n_drugs, bundle.n_proteins)
    assert _multi_hot(bundle, "pathway").shape == (bundle.n_drugs, bundle.n_pathways)


def test_multi_hot_rejects_unknown_kind(bundle):
    with pytest.raises(ValueError, match="protein.*pathway"):
        _multi_hot(bundle, "adverse_event")


# -- leakage boundary -----------------------------------------------------
def test_svd_is_fitted_on_training_drugs_only(bundle):
    """The held-out block must not change the basis. Change a held-out drug's
    annotation and every training drug's coordinates must be unchanged."""
    train = bundle.drug_ids[:30]
    base = BiologicalFeaturizer(bundle, protein_components=4, pathway_components=3,
                                seed=0).fit(train)

    altered_items = list(bundle.protein_items)
    altered_items[35] = np.array([[i, 0, 0] for i in range(bundle.n_proteins)],
                                 dtype=np.int64)
    altered = BiologyBundle(bundle.drug_ids, bundle.protein_vocab, bundle.pathway_vocab,
                            altered_items, bundle.pathway_items, bundle.counts,
                            bundle.policy)
    changed = BiologicalFeaturizer(altered, protein_components=4, pathway_components=3,
                                   seed=0).fit(train)

    n_count = len(COUNT_FEATURES)
    assert np.allclose(base.features.matrix[:30, n_count:n_count + 4],
                       changed.features.matrix[:30, n_count:n_count + 4])


def test_featurizer_records_how_many_drugs_it_was_fitted_on(bundle):
    train = bundle.drug_ids[:30]
    f = BiologicalFeaturizer(bundle, protein_components=4, pathway_components=3).fit(train)
    assert f.features.fitted_on == 30
    assert f.features.notes["n_train_drugs"] == 30


def test_transform_before_fit_raises(bundle):
    f = BiologicalFeaturizer(bundle, protein_components=4, pathway_components=3)
    with pytest.raises(RuntimeError, match="fit\\(\\) was never called"):
        f.transform_pairs(["D0"], ["D1"])


def test_training_drug_absent_from_the_bundle_raises(bundle):
    f = BiologicalFeaturizer(bundle, protein_components=2, pathway_components=2)
    with pytest.raises(KeyError, match="absent from the"):
        f.fit(["D0", "NOT_A_DRUG"])


def test_unknown_drug_at_transform_time_raises(bundle):
    f = BiologicalFeaturizer(bundle, protein_components=2, pathway_components=2)
    f.fit(bundle.drug_ids[:30])
    with pytest.raises(KeyError, match="no biological features"):
        f.transform_pairs(["GHOST"], ["D1"])


# -- CONTROL A ------------------------------------------------------------
def test_control_a_uses_counts_only(bundle, batch):
    b, train = batch
    m = BiologicalDegreeRF.build(bundle, train, n_estimators=5, n_jobs=1).fit(b)
    d = m.describe()
    assert d["n_drug_features"] == len(COUNT_FEATURES)
    assert d["n_pair_features"] == 3 * len(COUNT_FEATURES)
    assert m.featurizer._svd == {}          # no identity information at all


def test_control_a_ignores_protein_identity(bundle, batch):
    """Permuting which proteins a drug has, at fixed counts, must not move it."""
    b, train = batch
    m = BiologicalDegreeRF.build(bundle, train, n_estimators=5, n_jobs=1).fit(b)
    before = m.predict_proba(b)

    rng = np.random.default_rng(3)
    shuffled = []
    for items in bundle.protein_items:
        k = len(items)
        ids = rng.choice(bundle.n_proteins, size=k, replace=False) if k else []
        shuffled.append(
            np.stack([np.asarray(ids), np.zeros(k, int), np.zeros(k, int)], 1).astype(np.int64)
            if k else np.zeros((0, 3), dtype=np.int64)
        )
    b2 = BiologyBundle(bundle.drug_ids, bundle.protein_vocab, bundle.pathway_vocab,
                       shuffled, bundle.pathway_items, bundle.counts, bundle.policy)
    m2 = BiologicalDegreeRF.build(b2, train, n_estimators=5, n_jobs=1).fit(b)
    assert np.allclose(before, m2.predict_proba(b))


def test_log_counts_flag_changes_the_features(bundle, batch):
    _, train = batch
    raw = BiologicalDegreeRF.build(bundle, train, log_counts=False)
    logged = BiologicalDegreeRF.build(bundle, train, log_counts=True)
    raw.featurizer.fit(train)
    logged.featurizer.fit(train)
    assert not np.allclose(raw.featurizer.features.matrix,
                           logged.featurizer.features.matrix)
    assert logged.featurizer.features.names[0].startswith("log1p_")


# -- BIO-RF ---------------------------------------------------------------
def test_bio_rf_adds_identity_to_counts(bundle, batch):
    b, train = batch
    m = BioRF.build(bundle, train, protein_components=4, pathway_components=3,
                    n_estimators=5, n_jobs=1).fit(b)
    d = m.describe()
    assert d["n_drug_features"] == len(COUNT_FEATURES) + 4 + 3
    assert d["use_fingerprints"] is False
    assert set(m.featurizer._svd) == {"protein", "pathway"}


def test_bio_rf_predictions_are_symmetric(bundle, batch):
    b, train = batch
    m = BioRF.build(bundle, train, protein_components=4, pathway_components=3,
                    n_estimators=5, n_jobs=1).fit(b)
    flipped = PairBatch(drug_a=b.drug_b, drug_b=b.drug_a, y=b.y)
    assert np.allclose(m.predict_proba(b), m.predict_proba(flipped))


def test_component_clamping_is_recorded_not_silent(bundle, batch):
    """A tiny vocabulary must not quietly change the model's width."""
    b, train = batch
    m = BioRF.build(bundle, train, protein_components=999, pathway_components=3,
                    n_estimators=5, n_jobs=1).fit(b)
    note = m.describe()["protein_components_clamped"]
    assert note["requested"] == 999 and note["used"] == bundle.n_proteins - 1


def test_predict_before_fit_raises(bundle, batch):
    b, train = batch
    m = BioRF.build(bundle, train, protein_components=4, pathway_components=3)
    with pytest.raises(RuntimeError, match="fit\\(\\) must be called"):
        m.predict_proba(b)


def test_memory_estimate_is_reported_before_allocation(bundle, batch):
    _, train = batch
    f = BiologicalFeaturizer(bundle, protein_components=4, pathway_components=3).fit(train)
    est = f.estimate_memory(1000)
    assert est["dense_columns"] == 3 * f.features.matrix.shape[1]
    assert est["dense_bytes"] == 1000 * est["dense_columns"] * 8
    assert f.estimate_memory(1000, fingerprint_bits=4096)["total_gib"] > est["total_gib"]


def test_fingerprint_block_makes_the_design_sparse(bundle, batch):
    pytest.importorskip("rdkit")
    from ddinet.features.pair_encoding import build_fingerprint_matrix

    b, train = batch
    smiles = ["CCO"] * bundle.n_drugs
    fps = build_fingerprint_matrix(bundle.drug_ids, smiles, n_bits=64)
    m = BioRF.build(bundle, train, protein_components=4, pathway_components=3,
                    fingerprints=fps, n_estimators=5, n_jobs=1)
    m.featurizer.fit(train)
    design = m._design(b)
    assert sparse.issparse(design)
    assert design.shape[1] == 3 * m.featurizer.features.matrix.shape[1] + 2 * 64
    assert m.describe()["use_fingerprints"] is True


def test_bundle_provenance_is_carried_into_describe(bundle, batch):
    b, train = batch
    m = BiologicalDegreeRF.build(bundle, train, n_estimators=5, n_jobs=1).fit(b)
    assert m.describe()["policy"] == "M4"
    assert m.describe()["biology_source"] == "true"
