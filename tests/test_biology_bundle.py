"""Tests for the V2 biological feature layer.

Two groups. The first builds a miniature dataset in ``tmp_path`` and pins the
loader's contract exactly. The second runs against the frozen real snapshot and
is skipped where it is absent; those tests exist because three of the loader's
decisions (triple-level deduplication, derived rather than frozen counts, the
vocabulary being policy-independent) are only wrong at real scale.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ddinet.data.biology import (
    COUNT_FEATURES,
    EVIDENCE_POLICIES,
    EVIDENCE_TYPES,
    RELATION_TYPES,
    BiologyBundle,
    EvidencePolicy,
    count_discrepancy_report,
    load_biology,
)

ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / "data" / "mechanism_v1"
SHUFFLED = (
    ROOT / "data" / "mechanism_v1_controls" / "shuffled_biology_seed20260829"
    / "drug_protein_edges_shuffled.parquet"
)

real_only = pytest.mark.skipif(
    not (REAL / "drug_protein_edges.parquet").exists(),
    reason="frozen mechanism_v1 snapshot not present in this checkout",
)


# -- miniature dataset -----------------------------------------------------
@pytest.fixture
def mini(tmp_path: Path) -> Path:
    """Four drugs, three proteins, two pathways, one deliberate duplicate row."""
    root = tmp_path / "mini"
    root.mkdir()
    pd.DataFrame({"drugbank_id": ["D0", "D1", "D2", "D3"],
                  "n_targets": [1, 1, 0, 1], "n_enzymes": [1, 0, 0, 0],
                  "n_transporters": [0, 0, 0, 0], "n_carriers": [0, 0, 0, 0],
                  "n_proteins": [2, 1, 0, 1], "n_pathways": [2, 1, 0, 0],
                  "n_adverse_events": [0, 0, 0, 0]}).to_parquet(root / "drugs.parquet")
    edges = pd.DataFrame({
        "drugbank_id": ["D0", "D0", "D1", "D3", "D1"],
        "uniprot_id":  ["P1", "P2", "P3", "P1", "P3"],
        "relation_type": ["target", "enzyme", "target", "target", "target"],
        "evidence_type": ["DOCUMENTED_DATABASE_RELATION",
                          "DOCUMENTED_DATABASE_RELATION",
                          "EXPERIMENTAL_BIOACTIVITY",
                          "CURATED_MOA",
                          "EXPERIMENTAL_BIOACTIVITY"],   # duplicate of row 2
        "evidence_source": ["DrugBank_v5.1", "DrugBank_v5.1",
                            "ChEMBL_36_activities", "ChEMBL_36_drug_mechanism",
                            "ChEMBL_36_activities"],
    })
    edges.to_parquet(root / "drug_protein_edges.parquet")
    pd.DataFrame({"uniprot_accession": ["P1", "P1", "P2"],
                  "reactome_pathway_id": ["R-1", "R-2", "R-1"],
                  "pathway_name": ["a", "b", "a"], "evidence_code": ["TAS"] * 3,
                  "organism": ["Homo sapiens"] * 3, "source": ["x"] * 3,
                  }).to_parquet(root / "protein_pathway_edges.parquet")
    pd.DataFrame({"uniprot_accession": ["P1", "P2", "P3"], "protein_name": list("abc"),
                  "gene_name": list("abc"), "organism": ["Homo sapiens"] * 3,
                  "taxonomy_id": ["9606"] * 3, "ec_numbers": [""] * 3,
                  }).to_parquet(root / "proteins.parquet")
    pd.DataFrame({"pathway_id": ["R-1", "R-2"], "pathway_name": ["a", "b"],
                  "organism": ["Homo sapiens"] * 2, "source": ["x"] * 2,
                  }).to_parquet(root / "pathways.parquet")
    pd.DataFrame({"drugbank_id": ["D0", "D0"], "adverse_event_id": ["C1", "C1"],
                  }).to_parquet(root / "drug_adverse_event_edges.parquet")
    return root


def test_duplicate_rows_collapse_to_one_triple(mini):
    """An assay-level duplicate must not weight its protein twice under MEAN."""
    b = load_biology(mini, policy="M4")
    d1 = b.protein_items[b.index["D1"]]
    assert len(d1) == 1
    assert b.provenance["n_edge_rows"] == 5
    assert b.provenance["n_distinct_triples"] == 4


def test_element_columns_are_protein_relation_evidence(mini):
    b = load_biology(mini, policy="M4")
    rows = b.protein_items[b.index["D0"]]
    got = {
        (b.protein_vocab[p], RELATION_TYPES[r], EVIDENCE_TYPES[e])
        for p, r, e in rows
    }
    assert got == {
        ("P1", "target", "DOCUMENTED_DATABASE_RELATION"),
        ("P2", "enzyme", "DOCUMENTED_DATABASE_RELATION"),
    }


def test_element_order_is_deterministic(mini):
    a = load_biology(mini, policy="M4")
    b = load_biology(mini, policy="M4")
    for x, y in zip(a.protein_items, b.protein_items):
        assert np.array_equal(x, y)


def test_pathways_derive_from_the_active_protein_set(mini):
    b = load_biology(mini, policy="M4")
    # D0 hits P1 (R-1, R-2) and P2 (R-1) -> union {R-1, R-2}
    assert sorted(b.pathway_vocab[q] for q in b.pathway_items[b.index["D0"]]) == ["R-1", "R-2"]
    # D1 hits only P3, which has no Reactome edge -> empty, not imputed
    assert len(b.pathway_items[b.index["D1"]]) == 0


def test_evidence_filter_changes_the_active_set(mini):
    m1 = load_biology(mini, policy="M1")     # DrugBank only
    m3 = load_biology(mini, policy="M3")     # + both ChEMBL sources
    assert len(m1.protein_items[m1.index["D1"]]) == 0
    assert len(m3.protein_items[m3.index["D1"]]) == 1
    assert len(m1.protein_items[m1.index["D3"]]) == 0   # D3 is CURATED_MOA only
    assert len(m3.protein_items[m3.index["D3"]]) == 1


def test_m3_switches_pathways_off_entirely(mini):
    m3, m4 = load_biology(mini, policy="M3"), load_biology(mini, policy="M4")
    assert all(len(x) == 0 for x in m3.pathway_items)
    assert any(len(x) > 0 for x in m4.pathway_items)


def test_vocabulary_is_independent_of_the_policy(mini):
    """Otherwise M1 and M4 checkpoints would have incompatible embedding shapes."""
    sizes = {
        k: (load_biology(mini, policy=k).n_proteins, load_biology(mini, policy=k).n_pathways)
        for k in EVIDENCE_POLICIES
    }
    assert len(set(sizes.values())) == 1


def test_vocabulary_index_is_a_pure_function_of_the_id_set(mini):
    b = load_biology(mini, policy="M4")
    assert b.protein_vocab == sorted(b.protein_vocab)
    assert b.pathway_vocab == sorted(b.pathway_vocab)


def test_missing_biology_is_empty_not_imputed(mini):
    b = load_biology(mini, policy="M4")
    assert len(b.protein_items[b.index["D2"]]) == 0
    assert not b.has_protein()[b.index["D2"]]
    assert b.counts[b.index["D2"]].sum() == 0


def test_counts_follow_the_policy(mini):
    m1, m3 = load_biology(mini, policy="M1"), load_biology(mini, policy="M3")
    col = COUNT_FEATURES.index("n_proteins")
    assert m1.counts[m1.index["D1"], col] == 0
    assert m3.counts[m3.index["D1"], col] == 1
    chembl = COUNT_FEATURES.index("n_chembl_proteins")
    assert m1.counts[:, chembl].sum() == 0
    assert m3.counts[m3.index["D1"], chembl] == 1


def test_pathway_count_equals_the_materialised_set_size(mini):
    """CONTROL A must see exactly the set size BIO-GINE sees, true or shuffled."""
    b = load_biology(mini, policy="M4")
    col = COUNT_FEATURES.index("n_pathways")
    for i, items in enumerate(b.pathway_items):
        assert b.counts[i, col] == len(items)


def test_adverse_events_are_deduplicated(mini):
    b = load_biology(mini, policy="M4")
    col = COUNT_FEATURES.index("n_adverse_events")
    assert b.counts[b.index["D0"], col] == 1     # two rows, one event


def test_unknown_policy_name_raises(mini):
    with pytest.raises(ValueError, match="Unknown policy"):
        load_biology(mini, policy="M9")


def test_unknown_evidence_type_raises():
    with pytest.raises(ValueError, match="Unknown evidence types"):
        EvidencePolicy("bad", frozenset({"MADE_UP"}), use_pathways=False)


def test_bundle_rejects_misaligned_arrays():
    with pytest.raises(ValueError, match="align with drug_ids"):
        BiologyBundle(["A", "B"], ["P"], ["Q"], [np.zeros((0, 3), dtype=np.int64)],
                      [np.zeros(0, dtype=np.int64)], np.zeros((2, len(COUNT_FEATURES))),
                      EVIDENCE_POLICIES["M4"])


def test_bundle_rejects_wrong_count_width():
    with pytest.raises(ValueError, match="counts must be"):
        BiologyBundle(["A"], ["P"], ["Q"], [np.zeros((0, 3), dtype=np.int64)],
                      [np.zeros(0, dtype=np.int64)], np.zeros((1, 3)),
                      EVIDENCE_POLICIES["M4"])


def test_drug_ids_override_controls_the_ordering(mini):
    b = load_biology(mini, policy="M4", drug_ids=["D3", "D0"])
    assert b.drug_ids == ["D3", "D0"]
    assert b.n_drugs == 2


# -- against the frozen snapshot ------------------------------------------
@real_only
def test_real_snapshot_shapes():
    b = load_biology(REAL, policy="M4")
    d = b.describe()
    assert d["n_drugs"] == 1705
    assert d["protein_vocab"] == 2893 and d["pathway_vocab"] == 1969
    assert d["drugs_without_protein"] == 67
    assert d["n_edge_rows"] == 146743 and d["n_distinct_triples"] == 94088


@real_only
def test_real_evidence_ladder_is_monotone():
    """M1 subset of M2 subset of M3, drug by drug. A non-monotone ladder would
    make the marginal contribution of a source uninterpretable."""
    bundles = {k: load_biology(REAL, policy=k) for k in ("M1", "M2", "M3")}
    for i in range(bundles["M1"].n_drugs):
        s1 = {tuple(r) for r in bundles["M1"].protein_items[i]}
        s2 = {tuple(r) for r in bundles["M2"].protein_items[i]}
        s3 = {tuple(r) for r in bundles["M3"].protein_items[i]}
        assert s1 <= s2 <= s3


@real_only
def test_frozen_drugs_parquet_counts_are_drugbank_only():
    """Pins the discrepancy that made the loader derive counts instead of
    reading them: n_pathways matches the frozen column exactly under a
    DrugBank-only derivation and not at all under the full evidence set."""
    report = count_discrepancy_report(load_biology(REAL, policy="M4")).set_index("feature")
    assert report.loc["n_pathways", "exact_match_fraction"] < 0.3
    assert report.loc["n_adverse_events", "exact_match_fraction"] == 1.0

    edges = pd.read_parquet(REAL / "drug_protein_edges.parquet")
    db = edges[edges["evidence_source"] == "DrugBank_v5.1"]
    pp = pd.read_parquet(REAL / "protein_pathway_edges.parquet")
    merged = (
        db[["drugbank_id", "uniprot_id"]].drop_duplicates()
        .merge(pp[["uniprot_accession", "reactome_pathway_id"]].drop_duplicates(),
               left_on="uniprot_id", right_on="uniprot_accession")
    )
    derived = merged.groupby("drugbank_id")["reactome_pathway_id"].nunique()
    frozen = pd.read_parquet(REAL / "drugs.parquet").set_index("drugbank_id")["n_pathways"]
    joined = frozen.to_frame("frozen").join(derived.rename("derived")).fillna(0)
    assert (joined["frozen"] == joined["derived"]).all()


@pytest.mark.skipif(not SHUFFLED.exists(), reason="CONTROL F not built")
def test_control_f_preserves_every_protein_level_count():
    true = load_biology(REAL, policy="M4")
    shuf = load_biology(REAL, policy="M4", drug_protein_path=SHUFFLED)
    protein_side = [c for c in COUNT_FEATURES if c != "n_pathways"]
    t, s = true.count_frame(), shuf.count_frame()
    for c in protein_side:
        assert np.array_equal(t[c].to_numpy(), s[c].to_numpy()), c
    assert [len(x) for x in true.protein_items] == [len(x) for x in shuf.protein_items]
    assert true.protein_vocab == shuf.protein_vocab
    assert true.source == "true" and shuf.source == "shuffled"


@pytest.mark.skipif(not SHUFFLED.exists(), reason="CONTROL F not built")
def test_control_f_does_not_preserve_pathway_count_and_inflates_it():
    """A documented asymmetry, pinned so it cannot be forgotten.

    Pathways are DERIVED from proteins, so shuffling proteins reshapes Q(d).
    Real target sets are pathway-coherent - a drug's targets cluster in the same
    pathways - so a random set of the same size spreads over more of them:
    median 52 -> 87, larger for 68% of drugs. The direction is conservative for
    H-V2-3 (the control is not starved of pathway signal, it has more of it) but
    it means the true/shuffled contrast at the pathway level confounds identity
    with set size, and the M3 contrast, where protein degree is exact, is the
    clean one. See docs/V2_CONTROL_F_PATHWAY_ASYMMETRY.md.
    """
    true = load_biology(REAL, policy="M4")
    shuf = load_biology(REAL, policy="M4", drug_protein_path=SHUFFLED)
    a = np.array([len(x) for x in true.pathway_items])
    b = np.array([len(x) for x in shuf.pathway_items])
    assert not np.array_equal(a, b)
    assert np.median(b) > np.median(a)
    assert (b > a).mean() > 0.5
