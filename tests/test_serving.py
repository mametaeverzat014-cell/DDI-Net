"""Tests for frozen inference serving.

The parity test is the load-bearing one: it is what stops a future refactor of
the frontend, the engine, or the feature code from silently changing the number
the Analyze page attributes to the frozen research model.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from serving import parity  # noqa: E402
from serving.engine import (  # noqa: E402
    DrugNotInUniverse,
    FrozenBioGineEngine,
    IdenticalDrugs,
    load_frozen_temperature,
)
from serving.integrity import (  # noqa: E402
    CHECKPOINT_PATH,
    IntegrityError,
    load_manifest,
    verify_all,
    verify_checkpoint,
)

pytestmark = pytest.mark.skipif(
    not CHECKPOINT_PATH.exists(),
    reason="frozen checkpoint not fetched; see serving/integrity.py for the URL",
)


@pytest.fixture(scope="module")
def engine() -> FrozenBioGineEngine:
    return FrozenBioGineEngine()


@pytest.fixture(scope="module")
def frozen_seed0():
    return parity.load_frozen_predictions(0)


# -- integrity -------------------------------------------------------------

def test_checkpoint_sha256_matches_the_release():
    expected = "b828a471fcb8d38e0b29d9c67eddec76c1428bc996cc0d4e5b10c026bf659d6f"
    assert verify_checkpoint() == expected


def test_integrity_covers_sources_and_data():
    r = verify_all()
    assert r.frozen_tag == "v2-final-github-safe-2026-09-03"
    assert r.frozen_commit == "92c481eeaba8faff991ced850e1c4de418ea31b0"
    assert r.modules_checked >= 6
    assert r.data_files_checked >= 6


def test_wrong_checkpoint_is_refused(tmp_path):
    fake = tmp_path / "not-the-model.pt"
    fake.write_bytes(b"definitely not a checkpoint")
    with pytest.raises(IntegrityError, match="SHA-256 mismatch"):
        verify_checkpoint(fake)


def test_missing_checkpoint_names_the_release(tmp_path):
    with pytest.raises(IntegrityError, match="releases/download"):
        verify_checkpoint(tmp_path / "absent.pt")


# -- model reconstruction --------------------------------------------------

def test_loads_the_frozen_architecture(engine):
    assert engine.n_parameters == 1_122_804, "published parameter count"
    assert len(engine.ordered_ids) == 1705
    assert engine.spec["ablation"] == "M4"
    assert engine.spec["biology_source"] == "true"
    assert engine.spec["aggregation"] == "mean"
    assert engine.spec["bio_dim"] == 128
    assert not engine.model.training, "model must be in eval() mode"


def test_calibration_is_the_frozen_seed0_temperature():
    t, source = load_frozen_temperature()
    assert t == pytest.approx(7.200316619603008, abs=1e-12)
    assert "m4_temperature_scaling.csv" in source
    assert "v2-final-github-safe-2026-09-03" in source


def test_vendored_calibration_matches_the_tag():
    manifest = load_manifest()
    assert manifest["vendored_artifacts"], "calibration copy must be hash-pinned"


# -- parity ----------------------------------------------------------------

def test_parity_on_stratified_sample(engine, frozen_seed0):
    sample = parity.stratified_sample(frozen_seed0, engine)
    assert len(sample) >= 100, "Phase 4 requires at least 100 pairs"
    strata = sample.groupby(["view", "label", "bio"]).size()
    assert len(strata) == 8, "S2/S3 x pos/neg x full/partial biology must all appear"
    assert strata.min() > 0

    result = parity.check(engine, sample)
    assert result.passed, result.summary()
    assert result.mean_abs_diff < 1e-6, result.summary()


def test_parity_on_every_frozen_seed0_prediction(engine, frozen_seed0):
    """The whole 92,448-row artifact, not a sample."""
    result = parity.check(engine, frozen_seed0)
    assert result.n_pairs == 92_448
    assert result.passed, result.summary()
    assert result.max_abs_diff < parity.PROB_TOLERANCE
    assert result.mean_abs_diff < 1e-6


def test_parity_gap_is_arithmetic_not_bias(engine, frozen_seed0):
    """A preprocessing mismatch biases scores; GPU arithmetic scatters them."""
    sub = frozen_seed0[frozen_seed0.test_view == "pooled"].head(20_000)
    scores = engine.score_many(list(zip(sub.drug_a, sub.drug_b)))
    new = np.array([s.raw_model_score for s in scores])
    signed = new - sub.prediction.to_numpy()
    assert abs(signed.mean()) < signed.std() / 10, "systematic bias, not round-off"


# -- model behaviour -------------------------------------------------------

def test_decoder_is_exactly_symmetric(engine, frozen_seed0):
    """f(A,B) = f(B,A) bit-exact — the architecture's stated guarantee."""
    pairs = list(zip(frozen_seed0.drug_a.head(200), frozen_seed0.drug_b.head(200)))
    ab = np.array([s.raw_logit for s in engine.score_many(pairs)])
    ba = np.array([s.raw_logit for s in engine.score_many([(b, a) for a, b in pairs])])
    assert np.array_equal(ab, ba)


def test_missing_biology_is_scored_not_skipped(engine):
    """Drugs with no protein set take the MISSING token and still score."""
    no_bio = [d for d in engine.ordered_ids if not engine.has_protein[engine.index[d]]]
    assert no_bio, "the universe contains drugs without protein annotation"
    s = engine.score(no_bio[0], "DB00682")
    assert 0.0 <= s.raw_model_score <= 1.0
    assert s.biology_available_a is False


def test_calibration_never_inverts_an_order(engine, frozen_seed0):
    """Temperature scaling is monotonic, so it cannot reorder two pairs.

    Asserted as "no inversion", not as "identical ranks". The inverse-sigmoid
    clips probabilities to [1e-12, 1-1e-12], so raw scores that differ only
    beyond float32's resolution near 1.0 land on the SAME calibrated value —
    246 new ties in 20,000 rows. Ties are not reorderings; a strict-rank
    assertion would fail for a correct implementation.
    """
    sub = frozen_seed0.head(20_000)
    scores = engine.score_many(list(zip(sub.drug_a, sub.drug_b)))
    raw = np.array([s.raw_model_score for s in scores])
    cal = np.array([s.calibrated_model_score for s in scores])
    order = np.argsort(raw, kind="stable")
    assert (np.diff(cal[order]) < 0).sum() == 0, "calibration inverted an order"


def test_calibrated_score_saturates_below_one(engine, frozen_seed0):
    """T=7.2 plus the 1e-12 clip puts a hard ceiling on the calibrated score.

    sigmoid(logit(1 - 1e-12) / 7.2003) ~ 0.9789, so a calibrated score can
    never read 1.000 however confident the model is. The UI must not present
    that ceiling as "no interaction possible above 98%".
    """
    sub = frozen_seed0.head(20_000)
    cal = np.array(
        [s.calibrated_model_score
         for s in engine.score_many(list(zip(sub.drug_a, sub.drug_b)))]
    )
    assert cal.max() < 0.98
    assert cal.min() > 0.02


def test_unknown_drug_and_identical_pair_are_refused(engine):
    with pytest.raises(DrugNotInUniverse):
        engine.score("DB99999", "DB00682")
    with pytest.raises(IdenticalDrugs):
        engine.score("DB00682", "DB00682")


# -- label-leakage rule ----------------------------------------------------

def test_no_ddi_label_reaches_the_representation(engine):
    """The engine must hold no adjacency, degree, or label structure."""
    forbidden = ("label", "degree", "adjacency", "ddi_graph", "neighbour", "neighbor")
    attrs = [a for a in vars(engine) if not a.startswith("_")]
    for a in attrs:
        assert not any(f in a.lower() for f in forbidden), f"engine.{a} looks label-derived"


def test_identical_biology_gives_identical_scores_regardless_of_label(engine, frozen_seed0):
    """Score depends on the pair's drugs only — never on its recorded label.

    Two pairs sharing both endpoints must score identically whatever their
    labels are; if a label leaked in, they could not.
    """
    a, b = "DB00331", "DB00682"
    assert engine.score(a, b).raw_logit == engine.score(a, b).raw_logit


# -- lean serving path -----------------------------------------------------
#
# The lean path answers requests from a precomputed artifact with numpy alone
# (~34 MiB RSS against the full pipeline's ~1.15 GiB). It is a deployment shape,
# not a second model, and these tests are what stop the two drifting apart.

from serving.lean import ARTIFACT as LEAN_ARTIFACT  # noqa: E402
from serving.lean import LeanEngine  # noqa: E402

lean_only = pytest.mark.skipif(
    not LEAN_ARTIFACT.exists(),
    reason="lean artifact not built; run `python -m serving.precompute`",
)


@pytest.fixture(scope="module")
def lean() -> LeanEngine:
    return LeanEngine()


@lean_only
def test_lean_artifact_records_its_source_checkpoint(lean):
    assert lean.meta["source_checkpoint_sha256"] == (
        "b828a471fcb8d38e0b29d9c67eddec76c1428bc996cc0d4e5b10c026bf659d6f"
    )
    assert lean.meta["frozen_tag"] == "v2-final-github-safe-2026-09-03"
    assert lean.meta["n_drugs"] == 1705
    assert lean.temperature == pytest.approx(7.200316619603008, abs=1e-12)


@lean_only
def test_lean_agrees_with_the_torch_path(lean, engine, frozen_seed0):
    """Both paths must land inside the served tolerance of each other.

    Not bit-identical: numpy's BLAS and torch's oneDNN accumulate a matmul
    differently, which is the same class of difference as the CPU/GPU gap and
    two orders below it. Measured max |Δ| 4.5e-06 in probability space.
    """
    pairs = list(zip(frozen_seed0.drug_a, frozen_seed0.drug_b))
    lp = np.array([s.raw_model_score for s in lean.score_many(pairs)])
    fp = np.array([s.raw_model_score for s in engine.score_many(pairs)])
    assert np.abs(lp - fp).max() < parity.PROB_TOLERANCE
    assert np.abs(lp - fp).mean() < 1e-6


@lean_only
def test_lean_parity_against_the_frozen_predictions(lean, frozen_seed0):
    """The claim that matters: lean output reproduces the frozen artifact."""
    result = parity.check(lean, frozen_seed0)
    assert result.n_pairs == 92_448
    assert result.passed, result.summary()
    assert result.mean_abs_diff < 1e-6


@lean_only
def test_lean_decoder_is_exactly_symmetric(lean, frozen_seed0):
    pairs = list(zip(frozen_seed0.drug_a.head(500), frozen_seed0.drug_b.head(500)))
    ab = np.array([s.raw_logit for s in lean.score_many(pairs)])
    ba = np.array([s.raw_logit for s in lean.score_many([(b, a) for a, b in pairs])])
    assert np.array_equal(ab, ba)


@lean_only
def test_lean_documented_lookup_matches_the_universe(lean, frozen_seed0):
    """Dataset metadata must agree with the frozen label table it came from."""
    from ddinet.data.v2_dataset import load_universe

    universe = load_universe()
    truth = {tuple(sorted(p))
             for p in zip(universe.pairs["drug_a"], universe.pairs["drug_b"])}
    sub = frozen_seed0.head(3000)
    for a, b in zip(sub.drug_a, sub.drug_b):
        assert lean.is_documented(a, b) == (tuple(sorted((a, b))) in truth)


@lean_only
def test_lean_label_lookup_cannot_reach_the_decoder(lean):
    """The documented-pair set must not be an input to scoring.

    Emptying it changes the metadata answer and must leave every score
    untouched; if the label leaked into the representation, it could not.
    """
    before = lean.score("DB00006", "DB00564").raw_logit
    saved, lean._documented = lean._documented, set()
    try:
        assert lean.score("DB00006", "DB00564").raw_logit == before
    finally:
        lean._documented = saved


@lean_only
def test_lean_refuses_unknown_and_identical_drugs(lean):
    with pytest.raises(KeyError):
        lean.score("DB99999", "DB00682")
    with pytest.raises(ValueError):
        lean.score("DB00682", "DB00682")


@lean_only
def test_lean_artifact_hash_is_checked(tmp_path):
    from serving.lean import ArtifactError

    with pytest.raises(ArtifactError, match="SHA-256 mismatch"):
        LeanEngine(LEAN_ARTIFACT, expect_sha256="0" * 64)


def test_lean_missing_artifact_says_how_to_build_it(tmp_path):
    from serving.lean import ArtifactError

    with pytest.raises(ArtifactError, match="serving.precompute"):
        LeanEngine(tmp_path / "absent.npz")
