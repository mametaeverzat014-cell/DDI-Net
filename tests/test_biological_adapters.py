"""Tests for the DrugCentral and Reactome adapters.

These adapters are the only place where the corpus is joined to biology, so a
silent defect here would not surface as an error - it would surface as a
biological branch that quietly sees fewer drugs, or the wrong ones, and a
performance number nobody could explain.

The files themselves are not in git (size and licence), so tests that need them
skip rather than fail. The logic tests below use small in-memory frames and run
everywhere.
"""
import pandas as pd
import pytest

from ddinet.data import drugcentral as dc
from ddinet.data import reactome as rx

REAL_DATA = (dc.DEFAULT_DIR / dc.STRUCTURES).exists()
REAL_FI = (rx.FI_DIR / rx.FI_FILE).exists()


# --------------------------------------------------------------------------
# Join logic - no files needed
# --------------------------------------------------------------------------

def test_shared_targets_is_zero_when_a_drug_is_unannotated():
    """Absence of annotation must produce 0 overlap, never a missing value that
    a downstream model would silently impute."""
    edges = pd.DataFrame({"drug_id": ["A", "A", "B"], "gene": ["X", "Y", "X"]})
    pairs = pd.DataFrame({"drug_a": ["A", "A"], "drug_b": ["B", "C"]})
    out = dc.shared_target_counts(edges, pairs)
    assert list(out["n_shared_targets"]) == [1, 0]


def test_both_covered_flags_the_only_rows_a_biology_comparison_may_use():
    """LIMITATIONS.md 6d: a with-biology vs without-biology comparison run on
    different drug sets measures selection, not biology. This flag is how a
    caller restricts to the same set, so it must be exact."""
    edges = pd.DataFrame({"drug_id": ["A", "B"], "gene": ["X", "Y"]})
    pairs = pd.DataFrame({"drug_a": ["A", "A", "C"], "drug_b": ["B", "C", "D"]})
    out = dc.shared_target_counts(edges, pairs)
    assert list(out["both_covered"]) == [True, False, False]


def test_jaccard_of_two_unannotated_drugs_is_zero_not_one():
    """0/0 must be 0. Defining it as 1.0 would make the pairs nobody has studied
    look like the most similar pairs in the dataset."""
    edges = pd.DataFrame({"drug_id": ["A"], "gene": ["X"]})
    pairs = pd.DataFrame({"drug_a": ["C"], "drug_b": ["D"]})
    out = dc.shared_target_counts(edges, pairs)
    assert out["target_jaccard"].iloc[0] == 0.0
    assert out["n_union_targets"].iloc[0] == 0


def test_match_mode_is_validated():
    drugs = pd.DataFrame({"drugbank_id": ["DB1"], "inchikey": ["AAAA-BBBB-C"]})
    with pytest.raises(ValueError, match="exact.*skeleton"):
        dc.build_drug_target_table(drugs, match="fuzzy")


def test_missing_columns_are_named_in_the_error():
    with pytest.raises(ValueError, match="inchikey"):
        dc.build_drug_target_table(pd.DataFrame({"drugbank_id": ["DB1"]}))


def test_pathway_adjacency_drops_self_loops_but_keeps_both_directions():
    """Homodimers are real and stay in the raw table, but they say nothing about
    whether two DIFFERENT drugs' targets are connected."""
    net = rx.FINetwork(
        edges=pd.DataFrame({
            "gene_a": ["X", "Y", "Z"], "gene_b": ["Y", "Y", "X"],
            "annotation": ["", "", ""], "direction": ["-", "-", "-"],
            "score": [1.0, 1.0, 1.0], "is_predicted": [False] * 3,
            "is_signed": [False] * 3,
        }),
        n_total=3, n_predicted_dropped=0, include_predicted=False,
    )
    adj = rx.pathway_adjacency(net)
    assert adj["X"] == {"Y", "Z"}
    assert adj["Y"] == {"X"}          # the Y-Y self loop is gone
    assert "Y" not in adj["Y"]


def test_target_proximity_is_zero_when_either_side_has_no_targets():
    adj = {"X": {"Y"}}
    targets = {"A": {"X"}}
    pairs = pd.DataFrame({"drug_a": ["A"], "drug_b": ["B"]})
    out = rx.target_network_proximity(targets, adj, pairs)
    assert out["n_target_adjacent"].iloc[0] == 0


def test_target_proximity_finds_a_one_hop_link():
    adj = {"X": {"Y"}, "Y": {"X"}}
    targets = {"A": {"X"}, "B": {"Y"}}
    pairs = pd.DataFrame({"drug_a": ["A"], "drug_b": ["B"]})
    out = rx.target_network_proximity(targets, adj, pairs)
    assert out["n_target_adjacent"].iloc[0] == 1


def test_missing_file_error_says_what_to_download():
    """A bare FileNotFoundError would send the next person hunting. These files
    cannot be committed, so the error has to carry the instructions."""
    from pathlib import Path
    with pytest.raises(FileNotFoundError, match="drugcentral.org"):
        dc.load_structures(Path("/nonexistent"))
    with pytest.raises(FileNotFoundError, match="reactome.org"):
        rx.load_fi_network(Path("/nonexistent/x.txt"))


# --------------------------------------------------------------------------
# Against the real files - skipped when they are absent
# --------------------------------------------------------------------------

@pytest.mark.skipif(not REAL_FI, reason="Reactome FI file not present")
def test_predicted_edges_are_excluded_by_default():
    """29.2% of FI edges are a machine-learning output (E5_INFERRED). Training
    on them unflagged risks a circular label that no metric would reveal."""
    default = rx.load_fi_network()
    everything = rx.load_fi_network(include_predicted=True)
    assert not default.edges["is_predicted"].any()
    assert len(default.edges) < len(everything.edges)
    assert default.n_predicted_dropped > 0
    # Dropping them narrows the gene set too - the cost must stay visible.
    assert len(default.genes) < len(everything.genes)


@pytest.mark.skipif(not REAL_DATA, reason="DrugCentral files not present")
def test_skeleton_matching_covers_at_least_as_much_as_exact():
    """First-block matching merges salt forms, so it can only add drugs. If it
    ever covered fewer, the key handling would be wrong."""
    from ddinet.data.tdc_drugbank import load_drugs
    drugs = load_drugs()
    drugs = drugs[drugs["valid"]]
    exact = dc.build_drug_target_table(drugs, match="exact")
    skel = dc.build_drug_target_table(drugs, match="skeleton")
    assert skel.n_matched >= exact.n_matched
    assert exact.covered <= skel.covered


@pytest.mark.skipif(not REAL_DATA, reason="DrugCentral files not present")
def test_only_human_targets_by_default():
    """Rat and mouse rows exist. Mixing species would put non-human proteins
    into a human pathway graph without anything flagging it."""
    edges = dc.load_target_interactions()
    assert set(edges["organism"]) == {dc.HUMAN}
    assert len(dc.load_target_interactions(organism=None)) > len(edges)


# --------------------------------------------------------------------------
# Schema parity between match modes (regression)
# --------------------------------------------------------------------------

def test_both_match_modes_produce_the_same_columns():
    """Regression for a real defect found 2026-08-28.

    In "exact" mode both the corpus frame and the DrugCentral frame carried a
    column named `inchikey`, so the merge suffixed them to inchikey_x/_y and
    the column filter silently dropped both. The output schema therefore
    DIFFERED between match modes: code reading `inchikey` worked on skeleton
    and raised AttributeError on exact - the worse way round, because exact is
    the default and the failure surfaced only in a downstream consumer.
    """
    drugs = pd.DataFrame({
        "drugbank_id": ["DB00001"],
        "inchikey": ["BSYNRYMUTXBXSQ-UHFFFAOYSA-N"],
    })
    structures = pd.DataFrame({
        "struct_id": ["1"], "inchikey": ["BSYNRYMUTXBXSQ-UHFFFAOYSA-N"],
        "inn": ["aspirin"], "cas_rn": ["50-78-2"],
        "inchikey_skeleton": ["BSYNRYMUTXBXSQ"],
    })
    targets = pd.DataFrame({
        "assertion_id": [0], "struct_id": ["1"], "drug_name": ["aspirin"],
        "gene": ["PTGS1"], "uniprot_id": ["P23219"], "target_name": ["COX-1"],
        "target_class": ["Enzyme"], "action_type": ["INHIBITOR"],
        "is_moa": [True], "organism": [dc.HUMAN],
    })

    import unittest.mock as mock
    with mock.patch.object(dc, "load_structures", return_value=structures), \
         mock.patch.object(dc, "load_target_interactions", return_value=targets):
        exact = dc.build_drug_target_table(drugs, match="exact")
        skeleton = dc.build_drug_target_table(drugs, match="skeleton")

    assert list(exact.edges.columns) == list(skeleton.edges.columns)
    assert "drug_inchikey" in exact.edges.columns, (
        "the corpus InChIKey must survive the merge under a stable name"
    )
    assert exact.edges["drug_inchikey"].iloc[0] == "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
