"""Tests that must pass before CONTROL F is frozen.

A shuffled control is worthless if it differs from the true graph in any
statistic the model can see other than identity. Every test here pins one such
statistic. They are not smoke tests: each corresponds to a way the control
could silently stop being a control.

Two of them exist because earlier versions of this shuffle FAILED them, and the
failure was visible only in the numbers:

  * per-stratum independent shuffling raised distinct-protein count for 63.6%
    of drugs (median +2, max +29), because 4,381 pairs live in more than one
    stratum and collapse in the true graph but not in the shuffled one;
  * pair-level shuffling with a per-class duplicate set then LOWERED it, because
    a drug with pairs in two profile classes could receive the same protein
    twice.

Both are fixed, and both are pinned below.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "mechanism_v1"
SEED = 20260829
CONTROL = ROOT / "data" / "mechanism_v1_controls" / f"shuffled_biology_seed{SEED}"

pytestmark = pytest.mark.skipif(
    not (CONTROL / "drug_protein_edges_shuffled.parquet").exists(),
    reason="CONTROL F not built in this checkout",
)


@pytest.fixture(scope="module")
def data():
    true = pd.read_parquet(SOURCE / "drug_protein_edges.parquet")
    shuf = pd.read_parquet(CONTROL / "drug_protein_edges_shuffled.parquet")
    manifest = json.loads((CONTROL / "SHUFFLE_MANIFEST.json").read_text())
    return true, shuf, manifest


def _pairs(frame):
    return frame.drop_duplicates(["drugbank_id", "uniprot_id"])


# 1 -----------------------------------------------------------------------
def test_same_drug_universe(data):
    true, shuf, _ = data
    drugs = pd.read_parquet(SOURCE / "drugs.parquet", columns=["drugbank_id"])
    assert len(drugs) == 1705
    assert set(shuf["drugbank_id"]) == set(true["drugbank_id"])
    assert set(shuf["drugbank_id"]) <= set(drugs["drugbank_id"])


# 2 -----------------------------------------------------------------------
def test_no_drug_drug_edges_of_any_kind(data):
    """A drug-drug edge is the label. None may exist in a biological control."""
    _, shuf, _ = data
    assert "INTERACTS_WITH" not in set(shuf["relation_type"].astype(str))
    assert set(shuf["relation_type"]) <= {"target", "enzyme", "transporter", "carrier"}
    bio = pd.read_parquet(CONTROL / "biological_edges_shuffled.parquet")
    drug_drug = bio[(bio["source_type"] == "DRUG") & (bio["target_type"] == "DRUG")]
    assert len(drug_drug) == 0


# 3, 4, 5 -----------------------------------------------------------------
def test_the_generator_never_reads_ddi_labels_or_mechanisms():
    """Checked against the source, not just behaviour: a future edit that
    imports the label table would pass a behavioural test on today's output.

    The check is on READS, not on mentions. An earlier version grepped for the
    bare string and failed on the manifest's own note that the label table is
    never opened - a test that fires on its subject being discussed is a test
    that will be silenced rather than fixed.
    """
    source = (ROOT / "scripts" / "31_freeze_control_f.py").read_text()
    forbidden = ("ddi_positive_labels", "drug_adverse_event_edges",
                 "load_pairs", "y_types")
    reads = [line for line in source.splitlines()
             if "read_parquet" in line or "read_csv" in line]
    for line in reads:
        for name in forbidden:
            assert name not in line, f"generator reads {name!r}: {line.strip()}"
    # and no import of the DDI data modules at all
    imports = [l for l in source.splitlines() if l.startswith(("import ", "from "))]
    assert not any("tdc_drugbank" in l or "negatives" in l for l in imports)


def test_output_carries_no_ddi_or_adverse_event_information(data):
    _, shuf, _ = data
    forbidden = {"label", "y", "y_types", "ddi", "mechanism", "adverse_event_term",
                 "drug_a", "drug_b", "pair_key"}
    assert not (set(shuf.columns) & forbidden)
    # exactly one drug column: no pair information can be encoded
    assert [c for c in shuf.columns if c.startswith("drug")] == ["drugbank_id"]


def test_manifest_records_that_no_labels_were_read(data):
    _, _, manifest = data
    assert "none" in manifest["labels_read"].lower()


# 6 -----------------------------------------------------------------------
def test_same_number_of_edges_and_assertion_rows(data):
    true, shuf, _ = data
    assert len(shuf) == len(true)
    assert len(_pairs(shuf)) == len(_pairs(true))


# 7 -----------------------------------------------------------------------
def test_per_drug_distinct_protein_degree_is_exactly_preserved(data):
    """The statistic the control exists to hold constant. Not 'close' - equal.

    Regression: independent per-stratum shuffling broke this for 63.6% of drugs.
    """
    true, shuf, _ = data
    a = _pairs(true).groupby("drugbank_id")["uniprot_id"].nunique()
    b = _pairs(shuf).groupby("drugbank_id")["uniprot_id"].nunique()
    assert a.equals(b.reindex(a.index))


def test_per_drug_assertion_density_is_exactly_preserved(data):
    """Annotation density - how much is known about a drug - is the nuisance
    variable most likely to be confused with real biology."""
    true, shuf, _ = data
    assert true.groupby("drugbank_id").size().equals(
        shuf.groupby("drugbank_id").size())


@pytest.mark.parametrize("relation", ["target", "enzyme", "transporter", "carrier"])
def test_per_drug_degree_preserved_within_each_relation_type(data, relation):
    true, shuf, _ = data
    a = _pairs(true[true.relation_type == relation]).groupby("drugbank_id").size()
    b = _pairs(shuf[shuf.relation_type == relation]).groupby("drugbank_id").size()
    assert a.equals(b.reindex(a.index))


@pytest.mark.parametrize("source", ["DrugBank_v5.1", "ChEMBL_36_drug_mechanism",
                                    "ChEMBL_36_activities"])
def test_per_drug_edge_count_preserved_within_each_evidence_source(data, source):
    true, shuf, _ = data
    a = true[true.evidence_source == source].groupby("drugbank_id").size()
    b = shuf[shuf.evidence_source == source].groupby("drugbank_id").size()
    assert a.equals(b.reindex(a.index))


# 8 -----------------------------------------------------------------------
def test_per_protein_distinct_drug_degree_is_exactly_preserved(data):
    """Regression: a per-class duplicate set let a drug receive one protein
    twice, which changed protein degree too. The fix is a global set."""
    true, shuf, _ = data
    a = _pairs(true).groupby("uniprot_id")["drugbank_id"].nunique()
    b = _pairs(shuf).groupby("uniprot_id")["drugbank_id"].nunique()
    assert a.equals(b.reindex(a.index))


# 9 -----------------------------------------------------------------------
@pytest.mark.parametrize("column", ["relation_type", "evidence_source",
                                    "evidence_type"])
def test_stratum_composition_is_identical(data, column):
    """A DrugBank TARGET edge must never become a ChEMBL BIOACTIVITY edge."""
    true, shuf, _ = data
    assert (true[column].value_counts(dropna=False).sort_index().equals(
        shuf[column].value_counts(dropna=False).sort_index()))


def test_each_edges_own_stratum_is_unchanged(data):
    """Not just the totals: every row keeps its own semantics."""
    true, shuf, _ = data
    for col in ("relation_type", "evidence_source", "evidence_type"):
        assert (true[col].to_numpy() == shuf[col].to_numpy()).all() or \
               true[col].isna().equals(shuf[col].isna())


# 10 ----------------------------------------------------------------------
def test_no_duplicate_edges_were_created(data):
    true, shuf, _ = data
    assert not _pairs(shuf).duplicated(["drugbank_id", "uniprot_id"]).any()
    assert len(_pairs(shuf)) == len(_pairs(true))


def test_no_self_referential_or_empty_endpoints(data):
    _, shuf, _ = data
    assert shuf["drugbank_id"].notna().all()
    assert shuf["uniprot_id"].notna().all()


# 11 ----------------------------------------------------------------------
def test_every_shuffled_protein_exists_in_the_true_protein_pool(data):
    """Foreign-key integrity: the shuffle may only reassign proteins that were
    already in the graph, never invent one."""
    true, shuf, _ = data
    assert set(shuf["uniprot_id"]) <= set(true["uniprot_id"])
    assert set(shuf["uniprot_id"]) == set(true["uniprot_id"]), (
        "the protein pool must be used in full, or protein degree changed")


# 12 ----------------------------------------------------------------------
def test_shuffle_is_deterministic_under_the_frozen_seed():
    """Re-running the algorithm with the recorded seed must reproduce it
    exactly, or the manifest's hashes describe something unreproducible."""
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from ddinet.integration.shuffle import shuffle_bipartite

    left = np.repeat(np.arange(40), 5)
    rng = np.random.default_rng(7)
    right = np.concatenate([rng.choice(60, 5, replace=False) for _ in range(40)])
    strata = np.array(["a"] * 100 + ["b"] * 100)

    first, r1 = shuffle_bipartite(left, right, strata, seed=SEED)
    second, r2 = shuffle_bipartite(left, right, strata, seed=SEED)
    assert (first == second).all()
    assert r1.successful == r2.successful

    other, _ = shuffle_bipartite(left, right, strata, seed=SEED + 1)
    assert not (first == other).all(), "different seeds gave the same result"


def test_manifest_records_the_frozen_seed(data):
    _, _, manifest = data
    assert manifest["shuffle_seed"] == SEED


# 13 ----------------------------------------------------------------------
def test_slot_level_retention_is_low(data):
    """Nearly every edge slot points at a different protein than it did."""
    _, _, manifest = data
    assert manifest["swap_report"]["retained_fraction"] < 0.05


def test_pair_set_overlap_matches_the_manifest(data):
    """The honest measure of surviving identity, recomputed from the files."""
    true, shuf, manifest = data
    merged = _pairs(true).merge(_pairs(shuf), on=["drugbank_id", "uniprot_id"],
                                how="inner")
    overlap = len(merged) / len(_pairs(true))
    assert abs(overlap - manifest["pair_set_overlap"]) < 0.005


def test_the_chain_is_converged_not_merely_stopped(data):
    """THE test that decides what this control can claim.

    Slot retention (2.5%) and pair-set overlap (57.4%) disagree by a factor of
    twenty, because a protein can leave one slot of a drug and return to
    another. So "is 57% under-mixing or the floor?" cannot be answered by
    running longer and hoping - it is answered by the shape of the curve.

    A flat tail means further swapping destroys nothing more, and the residual
    overlap is forced by the degree sequence itself. That is a property of the
    graph, and it caps the power of CONTROL F rather than indicating a bug.
    """
    _, _, manifest = data
    curve = manifest["mixing_curve"]
    assert len(curve) >= 3, "need at least three budgets to judge convergence"
    overlaps = [c["pair_set_overlap"] for c in curve]

    # it must actually move at first...
    assert overlaps[0] - overlaps[-1] > 0.10, "the shuffle barely randomises"
    # ...and then stop moving
    tail = overlaps[-3:]
    assert max(tail) - min(tail) < 0.01, (
        f"tail still moving: {tail} - the chain is not converged and the "
        f"frozen graph is under-mixed")


def test_the_limited_power_of_this_control_is_recorded(data):
    """A control that removes only part of the signal must say so, or a null
    result will be read as evidence of absence."""
    _, _, manifest = data
    assert "pair_set_overlap" in manifest
    assert manifest["pair_set_overlap"] > 0
    assert "stationary" in manifest["mixing_curve_note"]


def test_the_preregistration_deviation_is_recorded(data):
    """The implemented method is stricter than the preregistered text. A
    deviation that is not written down is indistinguishable from a mistake."""
    _, _, manifest = data
    dev = manifest["preregistration_deviation"]
    assert "stricter" in dev["direction"]
    assert dev["preregistered"] and dev["implemented"] and dev["reason"]
