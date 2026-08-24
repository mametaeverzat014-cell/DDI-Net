"""Tests for sparse pair encoding and the classical baselines."""
import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from ddinet.data import synthetic_fixture
from ddinet.features.pair_encoding import (
    ENCODINGS, build_fingerprint_matrix, encode_dataset, encode_pairs,
)
from ddinet.models.classical import (
    DegreeOnlyModel, LogisticRegressionECFP, PairBatch, RandomForestECFP,
    build_model, training_degree,
)


@pytest.fixture(scope="module")
def fingerprints():
    drugs = synthetic_fixture.load_drugs()
    return build_fingerprint_matrix(list(drugs["name"]), list(drugs["smiles"]))


@pytest.fixture(scope="module")
def some_pairs():
    pairs = synthetic_fixture.load_pairs().head(200)
    return pairs["drug_a"].to_numpy(), pairs["drug_b"].to_numpy()


# -- Encoding ---------------------------------------------------------------

def test_output_is_sparse_and_correctly_shaped(fingerprints, some_pairs):
    """A dense pair matrix at real scale is ~3 GB and ~98% zeros."""
    a, b = some_pairs
    for encoding in ENCODINGS:
        X = encode_pairs(fingerprints, a, b, encoding=encoding)
        assert sparse.issparse(X)
        assert X.shape == (len(a), 2 * fingerprints.n_bits)


def test_symmetric_encoding_is_order_invariant(fingerprints, some_pairs):
    """A DDI is symmetric; the features must be too."""
    a, b = some_pairs
    forward = encode_pairs(fingerprints, a, b, encoding="symmetric")
    reverse = encode_pairs(fingerprints, b, a, encoding="symmetric")
    assert (forward != reverse).nnz == 0


def test_concat_encoding_is_order_dependent(fingerprints, some_pairs):
    """Documented, not fixed: quantifying what this costs is the experiment."""
    a, b = some_pairs
    forward = encode_pairs(fingerprints, a, b, encoding="concat",
                           randomise_concat_order=False)
    reverse = encode_pairs(fingerprints, b, a, encoding="concat",
                           randomise_concat_order=False)
    assert (forward != reverse).nnz > 0


def test_symmetric_blocks_match_their_definitions(fingerprints, some_pairs):
    """|a-b| and a*b, computed directly, must equal the vectorised result."""
    a, b = some_pairs
    X = encode_pairs(fingerprints, a[:20], b[:20], encoding="symmetric").toarray()
    n = fingerprints.n_bits
    for row, (da, db) in enumerate(zip(a[:20], b[:20])):
        fa = fingerprints.matrix[fingerprints.index[da]].toarray().ravel()
        fb = fingerprints.matrix[fingerprints.index[db]].toarray().ravel()
        assert np.allclose(X[row, :n], np.abs(fa - fb))
        assert np.allclose(X[row, n:], fa * fb)


def test_concat_blocks_are_the_two_fingerprints(fingerprints, some_pairs):
    a, b = some_pairs
    X = encode_pairs(fingerprints, a[:20], b[:20], encoding="concat",
                     randomise_concat_order=False).toarray()
    n = fingerprints.n_bits
    for row, (da, db) in enumerate(zip(a[:20], b[:20])):
        fa = fingerprints.matrix[fingerprints.index[da]].toarray().ravel()
        fb = fingerprints.matrix[fingerprints.index[db]].toarray().ravel()
        assert np.allclose(X[row, :n], fa)
        assert np.allclose(X[row, n:], fb)


def test_concat_order_randomisation_is_deterministic(fingerprints, some_pairs):
    a, b = some_pairs
    first = encode_pairs(fingerprints, a, b, encoding="concat", seed=7)
    again = encode_pairs(fingerprints, a, b, encoding="concat", seed=7)
    assert (first != again).nnz == 0


def test_concat_order_randomisation_changes_the_matrix(fingerprints, some_pairs):
    """Otherwise argument order encodes our alphabetical storage convention."""
    a, b = some_pairs
    fixed = encode_pairs(fingerprints, a, b, encoding="concat",
                         randomise_concat_order=False)
    shuffled = encode_pairs(fingerprints, a, b, encoding="concat",
                            randomise_concat_order=True, seed=0)
    assert (fixed != shuffled).nnz > 0


def test_unknown_drug_raises_rather_than_returning_zeros(fingerprints):
    """A silent zero row is indistinguishable from a real all-zero fingerprint."""
    with pytest.raises(KeyError, match="no fingerprint"):
        encode_pairs(fingerprints, np.array(["not_a_drug"]), np.array(["warfarin"]))


def test_unknown_encoding_is_rejected(fingerprints, some_pairs):
    a, b = some_pairs
    with pytest.raises(ValueError, match="Unknown encoding"):
        encode_pairs(fingerprints, a, b, encoding="bogus")


# -- Classical models -------------------------------------------------------

@pytest.fixture(scope="module")
def small_dataset(fingerprints):
    pairs = synthetic_fixture.load_pairs()
    rng = np.random.default_rng(0)
    names = list(synthetic_fixture.load_drugs()["name"])
    known = set(pairs["pair_key"])
    negatives = []
    while len(negatives) < len(pairs):
        x, y = rng.choice(names, 2, replace=False)
        key = (x, y) if x < y else (y, x)
        if key not in known:
            negatives.append(key)
    frame = pd.concat([
        pd.DataFrame({"drug_a": pairs["drug_a"], "drug_b": pairs["drug_b"], "label": 1}),
        pd.DataFrame({"drug_a": [k[0] for k in negatives],
                      "drug_b": [k[1] for k in negatives], "label": 0}),
    ], ignore_index=True)
    X = encode_dataset(fingerprints, frame, encoding="symmetric")
    return frame, PairBatch.from_frame(frame, X)


def test_degree_only_uses_no_chemistry(small_dataset):
    """Its whole point: whatever it scores is achievable without molecules."""
    frame, _ = small_dataset
    degree = training_degree(frame[frame.label == 1])
    model = DegreeOnlyModel(degree).fit(PairBatch.from_frame(frame))
    probs = model.predict_proba(PairBatch.from_frame(frame))
    assert probs.shape == (len(frame),)
    assert np.all((probs >= 0) & (probs <= 1))


def test_degree_only_is_symmetric(small_dataset):
    """(min, max) of the two degrees, so argument order cannot matter."""
    frame, _ = small_dataset
    degree = training_degree(frame[frame.label == 1])
    model = DegreeOnlyModel(degree).fit(PairBatch.from_frame(frame))
    swapped = frame.rename(columns={"drug_a": "drug_b", "drug_b": "drug_a"})
    assert np.allclose(model.predict_proba(PairBatch.from_frame(frame)),
                       model.predict_proba(PairBatch.from_frame(swapped)))


def test_degree_only_beats_chance_when_degree_is_informative(small_dataset):
    from ddinet.eval.metrics import compute_binary_metrics
    frame, _ = small_dataset
    degree = training_degree(frame[frame.label == 1])
    model = DegreeOnlyModel(degree).fit(PairBatch.from_frame(frame))
    batch = PairBatch.from_frame(frame)
    auc = compute_binary_metrics(batch.y, model.predict_proba(batch)).auc_roc
    assert auc > 0.6


def test_training_degree_counts_positives_only(small_dataset):
    """Counting sampled negatives would make 'degree' depend on the negative
    scheme rather than on the interaction graph."""
    frame, _ = small_dataset
    degree_pos = training_degree(frame[frame.label == 1])
    degree_all = training_degree(frame)
    assert sum(degree_pos.values()) < sum(degree_all.values())


@pytest.mark.parametrize("factory", [LogisticRegressionECFP, RandomForestECFP])
def test_feature_models_accept_sparse_input(small_dataset, factory):
    _, batch = small_dataset
    model = factory().fit(batch)
    probs = model.predict_proba(batch)
    assert probs.shape == (len(batch),)
    assert np.all((probs >= 0) & (probs <= 1))


def test_feature_models_reject_missing_features(small_dataset):
    frame, _ = small_dataset
    with pytest.raises(ValueError, match="requires encoded features"):
        LogisticRegressionECFP().fit(PairBatch.from_frame(frame))


def test_build_model_dispatches_by_name(small_dataset):
    frame, _ = small_dataset
    degree = training_degree(frame[frame.label == 1])
    assert build_model("degree_only", {}, degree=degree).name == "degree_only"
    assert build_model("logreg", {"C": 0.1}).C == 0.1
    assert build_model("random_forest", {"max_depth": 5}, seed=3).max_depth == 5
    with pytest.raises(ValueError, match="Unknown model"):
        build_model("nope", {})


def test_degree_only_requires_a_degree_mapping():
    with pytest.raises(ValueError, match="requires a training-degree mapping"):
        build_model("degree_only", {})
