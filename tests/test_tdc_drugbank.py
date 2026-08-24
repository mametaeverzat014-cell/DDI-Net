"""Tests for the TDC DrugBank loader.

These read the real 4.5 MB export committed at data/raw/drugbank.tab.gz. They
skip rather than fail if it is absent, so a checkout without the data file still
has a green suite - but the skip is loud, because silently passing would hide
that the data-facing code was never exercised.
"""
import numpy as np
import pandas as pd
import pytest

from ddinet.data import tdc_drugbank as tdc

pytestmark = pytest.mark.skipif(
    not tdc.DEFAULT_PATH.exists(),
    reason=f"TDC export not present at {tdc.DEFAULT_PATH}",
)


@pytest.fixture(scope="module")
def report():
    return tdc.build_report()


def test_counts_match_the_stated_figures(report):
    """Reconcile against the counts stated when the file was committed."""
    assert report.n_rows == 191_808
    assert report.n_drugs == 1_706
    assert report.n_types == 86


def test_rows_exceed_unordered_pairs_because_of_multi_type_pairs(report):
    """406 pairs carry two mechanisms each; there are no exact duplicates.

    This is the discrepancy between the stated 191,808 and the 191,402 pairs the
    binary task actually has. Pinning it stops it being rediscovered as a bug.
    """
    assert report.n_rows - report.n_pairs == 406
    assert report.n_multitype_pairs == 406


def test_no_self_interactions(report):
    assert report.n_self_loops == 0


def test_pairs_are_canonically_ordered():
    pairs = tdc.load_pairs()
    assert (pairs["drug_a"] < pairs["drug_b"]).all()


def test_pair_keys_are_unique():
    pairs = tdc.load_pairs()
    assert pairs["pair_key"].nunique() == len(pairs)


def test_multi_type_pairs_keep_every_type():
    """Collapsing to unordered pairs must not silently drop a mechanism."""
    pairs = tdc.load_pairs()
    multi = pairs[pairs["n_types"] > 1]
    assert len(multi) == 406
    assert (multi["y_types"].map(len) >= 2).all()
    raw = tdc.load_raw()
    assert sum(pairs["n_types"]) == len(raw)


def test_y_primary_is_one_of_the_pairs_types():
    pairs = tdc.load_pairs()
    assert all(r.y_primary in r.y_types for r in pairs.head(2000).itertuples())


def test_original_orientation_is_preserved():
    """`Map` is directional, so the ID1/ID2 order must survive canonicalisation."""
    pairs = tdc.load_pairs()
    for r in pairs.head(500).itertuples():
        for id1, id2, y in r.orientations:
            assert {id1, id2} == {r.drug_a, r.drug_b}
            assert y in r.y_types


def test_smiles_are_consistent_across_rows(report):
    """One DrugBank ID must denote one structure everywhere in the export."""
    assert report.inconsistent_smiles_ids == []


def test_smiles_validity_is_reported_not_assumed(report):
    """Exactly one structure fails to parse; it is kept and flagged, not dropped."""
    assert report.n_valid_smiles == 1_705
    assert report.invalid_smiles_ids == ["DB11630"]
    drugs = tdc.load_drugs()
    row = drugs.loc[drugs.drugbank_id == "DB11630"].iloc[0]
    assert row["valid"] is False or row["valid"] == False  # noqa: E712
    assert row["canonical_smiles"] == ""


def test_invalid_drug_is_still_present_in_the_drug_table():
    """Dropping it is a modelling decision, not the loader's to make."""
    drugs = tdc.load_drugs()
    assert "DB11630" in set(drugs["drugbank_id"])


def test_no_two_drugs_share_a_structure(report):
    assert report.duplicate_structures == {}


def test_drug_table_exposes_a_name_column():
    """The split and feature modules key on `name`; this is the contract."""
    drugs = tdc.load_drugs()
    assert "name" in drugs.columns
    assert (drugs["name"] == drugs["drugbank_id"]).all()


def test_type_vocabulary_covers_every_class():
    vocab = tdc.type_vocabulary()
    assert len(vocab) == 86
    assert vocab["n_rows"].sum() == len(tdc.load_raw())
    assert vocab["description"].str.len().min() > 0


def test_dataset_has_no_negative_examples():
    """The central fact about this file: Y is a type, never a binary label."""
    raw = tdc.load_raw()
    assert raw["Y"].min() == 1        # no zero class
    assert set(tdc.load_pairs()["label"]) == {1}


def test_missing_file_raises_with_instructions(tmp_path):
    with pytest.raises(FileNotFoundError, match="PyTDC"):
        tdc._read_raw(tmp_path / "absent.tab.gz")


def test_wrong_columns_are_rejected(tmp_path):
    path = tmp_path / "bad.tab.gz"
    pd.DataFrame({"a": [1], "b": [2]}).to_csv(path, sep="\t", index=False,
                                              compression="gzip")
    with pytest.raises(tdc.TDCDataError, match="Missing columns"):
        tdc._read_raw(path)
