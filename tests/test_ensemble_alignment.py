"""Tests for the ensemble alignment defect of Addendum 17 and its fix.

The defect was not that a check failed. It was that the check compared LABEL
vectors, and label equality is compatible with the members having been scored
on entirely different drug pairs. Every test here pins one step of that:
the sampler behaviour that made the labels match, the eval_seed that pins the
evaluation pairs, and the guard that now refuses to average without proof.
"""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ddinet.data import split as split_mod
from ddinet.data.negatives import NegativeSamplingConfig, build_dataset

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def analysis():
    return _load("phase_a2_analysis", ROOT / "scripts" / "16_phase_a2_analysis.py")


# -- the config contract --------------------------------------------------
def test_eval_seed_defaults_to_none_so_the_old_path_is_untouched():
    """The Phase A-2 grid must stay reproducible from its recorded config."""
    cfg = NegativeSamplingConfig()
    assert cfg.eval_seed is None
    assert cfg.to_dict()["eval_seed"] is None


def test_eval_seed_is_recorded_in_the_config_dict():
    assert NegativeSamplingConfig(eval_seed=7).to_dict()["eval_seed"] == 7


# -- sampler behaviour on the synthetic fixture ---------------------------
@pytest.fixture(scope="module")
def env():
    """The curated synthetic fixture, not real data: this is a test of the
    sampler's RNG plumbing, and the fixture is what it exists for."""
    from ddinet.data import synthetic_fixture

    drugs = synthetic_fixture.load_drugs()
    pairs = synthetic_fixture.load_pairs()
    split = split_mod.build_any("drug", drugs, pairs, seed=0)
    return split, list(drugs["name"]), set(pairs["pair_key"])


def _bucket(dataset, prefix):
    return dataset[dataset["bucket"].str.startswith(prefix)].reset_index(drop=True)


def _build(env, **kwargs):
    split, names, keys = env
    cfg = NegativeSamplingConfig(strategy="uniform", ratio=1.0, **kwargs)
    return build_dataset(split, names, keys, cfg)[0]


def test_labels_match_even_when_the_negatives_are_different(env):
    """The exact hole Addendum 17 fell through, reproduced on the fixture."""
    a, b = _build(env, seed=0), _build(env, seed=1)
    ta, tb = _bucket(a, "test"), _bucket(b, "test")
    assert np.array_equal(ta["label"].to_numpy(), tb["label"].to_numpy())
    pa = list(zip(ta["drug_a"], ta["drug_b"]))
    pb = list(zip(tb["drug_a"], tb["drug_b"]))
    assert pa != pb, "fixture failed to reproduce the defect"


def test_eval_seed_pins_the_evaluation_pairs_across_member_seeds(env):
    frames = [_build(env, seed=s, eval_seed=0) for s in range(5)]
    cols = ["drug_a", "drug_b", "label"]
    for prefix in ("test", "val"):
        reference = _bucket(frames[0], prefix)[cols]
        assert len(reference) > 0
        for f in frames[1:]:
            assert _bucket(f, prefix)[cols].equals(reference)


def test_eval_seed_still_lets_the_training_negatives_vary(env):
    """Otherwise the ensemble would cover initialisation only."""
    def train_negs(seed):
        t = _bucket(_build(env, seed=seed, eval_seed=0), "train")
        return set(map(tuple, t[t["label"] == 0][["drug_a", "drug_b"]].to_numpy()))
    assert train_negs(0) != train_negs(1)


def test_default_path_is_deterministic(env):
    assert _build(env, seed=3).equals(_build(env, seed=3))


def test_eval_seed_path_is_deterministic(env):
    assert _build(env, seed=3, eval_seed=1).equals(_build(env, seed=3, eval_seed=1))


def test_eval_seed_changes_which_evaluation_negatives_are_drawn(env):
    """The pin is a pin, not a constant: a different eval_seed is a different
    evaluation set, which is what makes it a recorded parameter."""
    cols = ["drug_a", "drug_b"]
    a = _bucket(_build(env, seed=0, eval_seed=0), "test")[cols]
    b = _bucket(_build(env, seed=0, eval_seed=1), "test")[cols]
    assert not a.equals(b)


# -- the guard ------------------------------------------------------------
def _member(tmp_path, name, pairs, y, s):
    path = tmp_path / f"{name}.npz"
    np.savez_compressed(path, y_val=y, s_val=s, y_test=y, s_test=s,
                        threshold=0.5, val_pairs=pairs, test_pairs=pairs)
    return path


def test_guard_accepts_members_scored_on_the_same_pairs(analysis, tmp_path):
    pairs = np.array(["A|B", "A|C", "B|C"])
    y = np.array([1, 0, 1])
    files = [_member(tmp_path, f"m{i}", pairs, y, np.array([0.1, 0.2, 0.3]))
             for i in range(3)]
    members = [np.load(f) for f in files]
    assert analysis._ensemble_alignment_problem(files, members, y) is None


def test_guard_rejects_members_scored_on_different_pairs(analysis, tmp_path):
    y = np.array([1, 0, 1])
    files = [
        _member(tmp_path, "m0", np.array(["A|B", "A|C", "B|C"]), y, np.zeros(3)),
        _member(tmp_path, "m1", np.array(["A|B", "A|D", "B|C"]), y, np.zeros(3)),
    ]
    members = [np.load(f) for f in files]
    problem = analysis._ensemble_alignment_problem(files, members, y)
    assert problem is not None and "ДРУГИХ парах" in problem


def test_guard_rejects_files_written_before_the_fix(analysis, tmp_path):
    """Unverifiable is not the same as correct."""
    y = np.array([1, 0])
    path = tmp_path / "old.npz"
    np.savez_compressed(path, y_val=y, s_val=np.zeros(2), y_test=y,
                        s_test=np.zeros(2), threshold=0.5)
    members = [np.load(path)]
    problem = analysis._ensemble_alignment_problem([path], members, y)
    assert problem is not None and "идентификаторов пар" in problem


def test_guard_rejects_different_lengths(analysis, tmp_path):
    files = [
        _member(tmp_path, "m0", np.array(["A|B", "A|C"]), np.array([1, 0]), np.zeros(2)),
        _member(tmp_path, "m1", np.array(["A|B"]), np.array([1]), np.zeros(1)),
    ]
    members = [np.load(f) for f in files]
    problem = analysis._ensemble_alignment_problem(files, members, np.array([1, 0]))
    assert problem is not None and "против" in problem


def test_pair_key_is_order_independent():
    runner = _load("phase_a2_gnn", ROOT / "scripts" / "15_phase_a2_gnn.py")
    forward = pd.DataFrame({"drug_a": ["A", "C"], "drug_b": ["B", "A"]})
    reversed_ = pd.DataFrame({"drug_a": ["B", "A"], "drug_b": ["A", "C"]})
    assert np.array_equal(runner._pair_keys(forward), runner._pair_keys(reversed_))
    assert runner._pair_keys(forward).tolist() == ["A|B", "A|C"]
