"""Tests for metrics, baselines, cross-validation and FAERS statistics."""
import numpy as np
import pandas as pd
import pytest

from ddinet.data import assemble, curated, split as split_mod
from ddinet.eval.baselines import (
    BaselineContext, DegreeBaseline, LogisticRegressionBaseline, PrevalenceBaseline,
    RandomForestBaseline, RulesBaseline, SimilarityBaseline, default_baselines,
)
from ddinet.eval.crossval import CVResult, run_cross_validation
from ddinet.eval.faers import (
    EFFECT_TO_MEDDRA, FAERSClient, disproportionality, signal_enrichment,
)
from ddinet.eval.metrics import (
    best_threshold, bootstrap_ci, compute_binary_metrics, recall_at_precision,
    severity_metrics,
)
from ddinet.features.build import FeatureConfig, build_feature_bundle


@pytest.fixture(scope="module")
def env():
    drugs, pairs = curated.load_drugs(), curated.load_pairs()
    sp = split_mod.build_split(drugs, pairs, seed=42)
    bundle = build_feature_bundle(drugs, sp, FeatureConfig())
    dataset = assemble.build_supervised_dataset(
        sp, set(pairs["pair_key"]), assemble.AssemblyConfig(neg_ratio=3.0, seed=42)
    )
    fps = {n: bundle.fingerprints[n].bits for n in drugs["name"]}
    ctx = BaselineContext(drugs, fps, sp.buckets["train"])
    return drugs, pairs, sp, bundle, dataset, ctx


# -- Metrics ----------------------------------------------------------------

def test_perfect_and_random_classifiers_score_as_expected():
    y = np.array([0, 0, 1, 1])
    assert compute_binary_metrics(y, np.array([0.1, 0.2, 0.8, 0.9])).auc_roc == 1.0
    assert compute_binary_metrics(y, np.array([0.9, 0.8, 0.2, 0.1])).auc_roc == 0.0


def test_auprc_baseline_equals_prevalence():
    """A constant predictor's AUPRC is the prevalence - the number to beat."""
    rng = np.random.default_rng(0)
    y = (rng.random(4000) < 0.2).astype(int)
    m = compute_binary_metrics(y, np.full(4000, 0.5))
    assert m.auprc == pytest.approx(m.prevalence, abs=0.02)


def test_single_class_returns_nan_not_a_fake_score():
    """A one-class bucket must be 'not estimable', never a silent 0.5."""
    m = compute_binary_metrics(np.zeros(10, int), np.random.rand(10))
    assert np.isnan(m.auc_roc)
    assert np.isnan(m.auprc)


def test_f2_threshold_favours_recall_over_f1():
    """F2 weights recall 4x, so it should select a more permissive threshold."""
    rng = np.random.default_rng(1)
    y = (rng.random(2000) < 0.15).astype(int)
    s = np.clip(0.35 * y + rng.random(2000) * 0.65, 0, 1)
    assert best_threshold(y, s, metric="f2") <= best_threshold(y, s, metric="f1")


def test_recall_at_precision_is_monotone_in_the_floor():
    rng = np.random.default_rng(2)
    y = (rng.random(2000) < 0.2).astype(int)
    s = np.clip(0.4 * y + rng.random(2000) * 0.6, 0, 1)
    r50, _ = recall_at_precision(y, s, 0.5)
    r90, _ = recall_at_precision(y, s, 0.9)
    assert r50 >= r90


def test_bootstrap_ci_brackets_the_point_estimate():
    rng = np.random.default_rng(3)
    y = (rng.random(500) < 0.3).astype(int)
    s = np.clip(0.4 * y + rng.random(500) * 0.6, 0, 1)
    point, lo, hi = bootstrap_ci(y, s, n_boot=300, seed=0)
    assert lo <= point <= hi


def test_severity_mae_respects_ordering():
    """Predicting 'minor' for a major must cost more than predicting 'moderate'."""
    truth = np.array([2, 2, 2])
    near = np.array([[0.1, 0.6, 0.3]] * 3)     # predicts moderate (rank 1)
    far = np.array([[0.7, 0.2, 0.1]] * 3)      # predicts minor (rank 0)
    assert severity_metrics(truth, near)["mae_rank"] < severity_metrics(truth, far)["mae_rank"]


# -- Baselines --------------------------------------------------------------

def test_prevalence_baseline_predicts_the_training_rate(env):
    *_, dataset, ctx = env
    train = dataset[dataset.bucket == "train"]
    bl = PrevalenceBaseline().fit(train, ctx)
    preds = bl.predict_proba(dataset[dataset.bucket == "test_S2"], ctx)
    assert np.allclose(preds, train["label"].mean())


def test_degree_baseline_is_structurally_degenerate_in_s2(env):
    """In S2 every pair contains a drug with TRAINING degree 0.

    So the degree baseline assigns every S2 pair the same score and lands on
    exactly 0.5 - regardless of how negatives were sampled. That is a property
    of the drug-level split, NOT evidence that degree-matched sampling worked.
    Conflating the two would be a real misreading of the results table.
    """
    drugs, pairs, sp, bundle, dataset, ctx = env
    for drug in sp.test_drugs:
        assert ctx.degree.get(drug, 0) == 0
    bl = DegreeBaseline().fit(dataset[dataset.bucket == "train"], ctx)
    sub = dataset[dataset.bucket == "test_S2"]
    scores = bl.predict_proba(sub, ctx)
    assert len(np.unique(scores)) == 1
    assert compute_binary_metrics(sub["label"].to_numpy(), scores).auc_roc == 0.5


def test_degree_matched_sampling_shrinks_the_shortcut_in_s1(env):
    """The degree shortcut lives in S1, where both drugs have a training degree.

    Measured on the curated fixture: a degree-only classifier reaches AUC ~0.78
    with uniform negatives and ~0.64 with degree-matched negatives. The shortcut
    is substantially REDUCED but not eliminated - so the honest claim is
    "reduced", and S1 numbers still deserve suspicion.
    """
    drugs, pairs, sp, bundle, _, _ = env
    fps = {n: bundle.fingerprints[n].bits for n in drugs["name"]}
    ctx = BaselineContext(drugs, fps, sp.buckets["train"])

    def degree_auc(strategy: str) -> float:
        ds = assemble.build_supervised_dataset(
            sp, set(pairs["pair_key"]),
            assemble.AssemblyConfig(neg_ratio=3.0, strategy=strategy, seed=42),
        )
        train = ds[ds.bucket == "train"]
        bl = DegreeBaseline().fit(train, ctx)
        return compute_binary_metrics(
            train["label"].to_numpy(), bl.predict_proba(train, ctx)
        ).auc_roc

    uniform_auc = degree_auc("uniform")
    matched_auc = degree_auc("degree_matched")
    assert uniform_auc > 0.70, "expected a large shortcut with uniform negatives"
    assert matched_auc < uniform_auc - 0.05, "degree matching should shrink it"


def test_similarity_baseline_only_uses_training_edges(env):
    """A baseline that peeked at test edges would make the comparison a lie."""
    drugs, pairs, sp, bundle, dataset, ctx = env
    for drug, partners in ctx.neighbours.items():
        assert drug in sp.train_drugs
        assert partners <= sp.train_drugs


def test_similarity_baseline_is_degenerate_in_s3(env):
    """Both drugs unseen means no training partners, so no signal is available.

    This is not a bug - it is the honest structural limit of a neighbourhood
    method in the fully-inductive setting, and it is worth reporting.
    """
    *_, dataset, ctx = env
    train = dataset[dataset.bucket == "train"]
    bl = SimilarityBaseline().fit(train, ctx)
    s3 = dataset[dataset.bucket == "test_S3"]
    if len(s3):
        assert np.allclose(bl.predict_proba(s3, ctx), 0.0)


def test_rules_baseline_learns_positive_weight_for_cyp_inhibition(env):
    """The strongest mechanism should get a positive learned weight."""
    *_, dataset, ctx = env
    bl = RulesBaseline().fit(dataset[dataset.bucket == "train"], ctx)
    weights = bl.rule_weights()
    assert weights["cyp_inhibitor_substrate"] > 0


@pytest.mark.parametrize("factory", [LogisticRegressionBaseline, RandomForestBaseline])
def test_ml_baselines_produce_valid_probabilities(env, factory):
    *_, dataset, ctx = env
    bl = factory().fit(dataset[dataset.bucket == "train"], ctx)
    p = bl.predict_proba(dataset[dataset.bucket == "test_S2"], ctx)
    assert p.shape == (len(dataset[dataset.bucket == "test_S2"]),)
    assert np.all((p >= 0) & (p <= 1))


def test_all_baselines_use_symmetric_pair_features(env):
    """No baseline may exploit argument order; a DDI is symmetric."""
    *_, dataset, ctx = env
    train = dataset[dataset.bucket == "train"]
    test = dataset[dataset.bucket == "test_S2"].head(30)
    swapped = test.rename(columns={"drug_a": "drug_b", "drug_b": "drug_a"})
    for bl in default_baselines(seed=0):
        bl.fit(train, ctx)
        assert np.allclose(
            bl.predict_proba(test, ctx), bl.predict_proba(swapped, ctx), atol=1e-8
        ), f"{bl.name} is order-dependent"


# -- Cross-validation -------------------------------------------------------

def test_cv_evaluates_every_model_on_every_fold(env):
    drugs, pairs, *_ = env
    res = run_cross_validation(drugs, pairs, n_folds=3, seed=0,
                               baselines=default_baselines(0), verbose=False)
    s2 = res.rows[res.rows.bucket == "test_S2"]
    for model, grp in s2.groupby("model"):
        assert len(grp) == 3, f"{model} missing folds"


def test_cv_folds_are_drug_disjoint(env):
    drugs, pairs, *_ = env
    res = run_cross_validation(drugs, pairs, n_folds=3, seed=0,
                               baselines=[PrevalenceBaseline()], verbose=False)
    tests = [s.test_drugs for s in res.splits]
    for i in range(len(tests)):
        for j in range(i + 1, len(tests)):
            assert not (tests[i] & tests[j])


def test_paired_comparison_counts_wins_correctly():
    rows = pd.DataFrame([
        {"fold": f, "model": m, "bucket": "test_S2", "auprc": v,
         "auc_roc": v, "auprc_lift": v, "balanced_accuracy": v,
         "f1": v, "f2": v, "precision": v, "recall": v}
        for f, (a, b) in enumerate([(0.6, 0.5), (0.7, 0.4), (0.3, 0.5)])
        for m, v in (("A", a), ("B", b))
    ])
    c = CVResult(rows).paired_comparison("A", "B")
    assert c["n_folds"] == 3
    assert c["folds_a_wins"] == 2
    assert c["folds_b_wins"] == 1
    assert c["mean_difference"] == pytest.approx((0.1 + 0.3 - 0.2) / 3)


# -- FAERS ------------------------------------------------------------------

def test_disproportionality_matches_hand_computed_values():
    d = disproportionality(50, 950, 1000, 998000)
    assert d.prr == pytest.approx((50 / 1000) / (1000 / 999000), rel=1e-6)
    assert d.ror == pytest.approx((50 * 998000) / (950 * 1000), rel=1e-6)
    assert d.ror_ci_low < d.ror < d.ror_ci_high


def test_sparse_counts_are_not_called_a_signal():
    """a=2 is below the min_reports floor however extreme the ratio."""
    assert not disproportionality(2, 10, 1000, 998000).is_signal


def test_zero_cell_gets_haldane_correction_not_infinity():
    d = disproportionality(0, 100, 1000, 998000)
    assert np.isfinite(d.ror)
    assert not d.is_signal


def test_null_association_gives_ror_near_one():
    d = disproportionality(100, 900, 10000, 90000)
    assert d.ror == pytest.approx(1.0, abs=0.05)


def test_offline_client_returns_none_not_zero():
    """'Unanswerable' must never be silently converted into 'no signal'."""
    client = FAERSClient(offline=True)
    assert client.count_reports('patient.drug.medicinalproduct:"nonexistentdrug"') is None
    assert client.analyse_pair("a", "b", "headache") is None


def test_signal_enrichment_computes_the_rate_ratio():
    flagged = pd.DataFrame({"queried": [True] * 10, "is_signal": [True] * 4 + [False] * 6})
    control = pd.DataFrame({"queried": [True] * 10, "is_signal": [True] * 1 + [False] * 9})
    e = signal_enrichment(flagged, control)
    assert e["flagged_rate"] == pytest.approx(0.4)
    assert e["control_rate"] == pytest.approx(0.1)
    assert e["rate_ratio"] == pytest.approx(4.0)


def test_meddra_mapping_covers_the_curated_effects():
    """Every clinical effect we predict should map to a queryable MedDRA term."""
    effects = set(curated.load_pairs()["clinical_effect"]) - {""}
    mapped = effects & set(EFFECT_TO_MEDDRA)
    assert len(mapped) / len(effects) > 0.4, (
        f"only {len(mapped)}/{len(effects)} effects mapped: "
        f"{sorted(effects - set(EFFECT_TO_MEDDRA))[:10]}"
    )
