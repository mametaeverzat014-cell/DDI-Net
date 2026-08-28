"""Tests for the debiasing analysis.

The point of this script is that the verdict is READ OFF a rule fixed before
the experiment ran. So the thing to test is that each branch of that rule fires
on the input it is supposed to fire on - especially the two branches that
REFUSE to report a result (collapse, and adversary-failed). A bug there would
turn a failed experiment into a reported finding.

The frames below are synthetic and exist only to exercise the decision logic.
They are never a substitute for measurements: the script reads real results
from reports/debias_results.csv.
"""
import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "debias_analysis", ROOT / "scripts" / "27_debias_analysis.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["debias_analysis"] = module
    spec.loader.exec_module(module)
    return module


A = _load()


def frame(*, r2_adv1=0.05, var_adv1=1.0, auprc_adv1=0.70,
          r2_base=0.92, var_base=1.0, auprc_base=0.70,
          auprc_adv0=None, seeds=(0, 1, 2, 3, 4), views=("pooled", "S2")):
    """One cell, five seeds, three conditions. Defaults = clean suppression."""
    auprc_adv0 = auprc_base if auprc_adv0 is None else auprc_adv0
    rows = []
    for seed in seeds:
        for view in views:
            for cond, r2, var, auprc in (
                ("base", r2_base, var_base, auprc_base),
                ("adv0", r2_base, var_base, auprc_adv0),
                ("adv1", r2_adv1, var_adv1, auprc_adv1),
            ):
                rows.append({
                    "scheme": "random_pair", "negatives": "uniform",
                    "condition": cond, "seed": seed, "test_view": view,
                    # tiny per-seed jitter so paired tests are not degenerate
                    "auprc": auprc + 0.001 * seed,
                    "r2_probe": r2, "embedding_var": var,
                })
    return pd.DataFrame(rows)


def _verdict(df):
    out = []
    collapsed = A.collapse_check(df, out)
    suppressed = A.suppression_check(df, out)
    effects = A.cost_table(df, out)
    A.verdicts(collapsed, suppressed, effects, out)
    return "\n".join(out)


# --------------------------------------------------------------------------
# The two branches that must REFUSE to report
# --------------------------------------------------------------------------

def test_collapse_is_detected_and_refuses_to_report_auprc():
    """A collapsed encoder also defeats the degree probe. Reporting its AUPRC
    as 'after debiasing' would be the single most misleading thing this script
    could do."""
    df = frame(var_adv1=0.05, var_base=1.0)      # 5% of base, below the 10% floor
    text = _verdict(df)
    assert "КОЛЛАПС" in text
    assert "НЕ сообщается" in text


def test_variance_just_above_the_floor_is_not_called_collapse():
    """The threshold is pre-registered at 10%; it must be applied as written."""
    df = frame(var_adv1=0.15, var_base=1.0)
    text = _verdict(df)
    assert "КОЛЛАПС" not in text


def test_adversary_that_did_not_suppress_is_reported_as_a_failure():
    """R^2 that stays high means the method did not work. The AUPRC must not be
    presented as if debiasing had happened."""
    df = frame(r2_adv1=0.80)
    text = _verdict(df)
    assert "не сработал" in text
    assert "неудача метода" in text


def test_collapse_takes_precedence_over_suppression():
    """If both fire, collapse is the more damaging finding and must win."""
    df = frame(r2_adv1=0.02, var_adv1=0.01)
    text = _verdict(df)
    assert "КОЛЛАПС" in text
    assert "не сработал" not in text


# --------------------------------------------------------------------------
# The two branches that report a result
# --------------------------------------------------------------------------

def test_quality_held_reads_as_the_model_not_relying_on_degree():
    df = frame(r2_adv1=0.05, auprc_adv1=0.70, auprc_adv0=0.70)
    text = _verdict(df)
    assert "не опиралась на степень" in text


def test_quality_lost_reads_as_the_model_having_relied_on_degree():
    df = frame(r2_adv1=0.05, auprc_adv1=0.55, auprc_adv0=0.70)
    text = _verdict(df)
    assert "опиралась на степень" in text
    assert "не опиралась" not in text


def test_ambiguous_effect_claims_neither_direction():
    """An effect too small to call significant but too large to call equivalent
    must be reported as underpowered, not rounded to either verdict.

    Built explicitly rather than through `frame`: the ambiguous branch needs
    real spread across seeds. With a constant offset the paired t-test has zero
    variance and ANY difference comes out significant, which is a property of
    the fixture, not of the analysis.
    """
    # adv1 - adv0 per seed: -0.05, +0.03, -0.06, +0.04, -0.01
    # mean -0.030 (beyond the 0.02 margin), but the spread makes p > 0.05.
    deltas = [-0.05, +0.03, -0.06, +0.04, -0.01]
    rows = []
    for seed, delta in enumerate(deltas):
        for view in ("pooled",):
            for cond, auprc in (("base", 0.70), ("adv0", 0.70),
                                ("adv1", 0.70 + delta)):
                rows.append({
                    "scheme": "random_pair", "negatives": "uniform",
                    "condition": cond, "seed": seed, "test_view": view,
                    "auprc": auprc,
                    "r2_probe": 0.05 if cond == "adv1" else 0.92,
                    "embedding_var": 1.0,
                })
    text = _verdict(pd.DataFrame(rows))
    assert "мощности не хватает" in text
    assert "опиралась на степень" not in text


# --------------------------------------------------------------------------
# Contract
# --------------------------------------------------------------------------

def test_thresholds_match_the_pre_registration():
    """These live in docs/DEBIAS_PROTOCOL.md section 4. If the code and the
    document drift apart, the 'pre-registered' claim is void."""
    protocol = (ROOT / "docs" / "DEBIAS_PROTOCOL.md").read_text()
    assert A.R2_SUPPRESSED == 0.30 and "0.3" in protocol
    assert A.COLLAPSE_FRACTION == 0.10 and "10 %" in protocol
    assert A.EQUIVALENCE_MARGIN == 0.02


def test_duplicate_seeds_raise_rather_than_being_averaged():
    """A resumed run that double-wrote a row would otherwise be silently
    averaged into the comparison."""
    df = pd.concat([frame(seeds=(0,)), frame(seeds=(0,))])
    with pytest.raises(ValueError, match="Duplicate seeds"):
        A.series(df, "random_pair", "uniform", "adv1", "auprc")


def test_per_bucket_reporting_covers_every_view_present():
    """pooled is 91% S2; a summary that reported only pooled would hide S3."""
    df = frame(views=("pooled", "S2", "S3"))
    out = []
    A.cost_table(df, out)
    text = "\n".join(out)
    for view in ("pooled", "S2", "S3"):
        assert f"| {view} |" in text
