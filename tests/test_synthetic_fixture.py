"""Integrity tests for the hand-curated seed dataset.

These are the tests that make the fixture trustworthy. If any of them fail,
every downstream number is suspect - so they run first and they are strict.
"""
import pytest
from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

from ddinet.data import synthetic_fixture


def test_validation_passes():
    report = synthetic_fixture.validate()
    assert report.ok, report.summary()


def test_every_smiles_parses_and_matches_its_stated_formula():
    """The core guard: a typo in a SMILES changes the molecule silently.

    Cross-checking against an independently written molecular formula makes a
    structural error impossible to miss.
    """
    drugs = synthetic_fixture.load_drugs()
    for _, row in drugs.iterrows():
        mol = Chem.MolFromSmiles(row["smiles"])
        assert mol is not None, f"{row['name']}: unparseable SMILES"
        formula = rdMolDescriptors.CalcMolFormula(mol)
        assert formula == row["formula_expected"], (
            f"{row['name']}: formula {formula} != stated {row['formula_expected']}"
        )


def test_no_two_drugs_share_a_structure():
    drugs = synthetic_fixture.load_drugs()
    assert drugs["inchikey"].nunique() == len(drugs)


def test_pair_keys_are_canonically_ordered():
    pairs = synthetic_fixture.load_pairs()
    for a, b in zip(pairs["drug_a"], pairs["drug_b"]):
        assert a < b, f"({a}, {b}) is not canonically ordered"


def test_no_duplicate_or_self_interactions():
    pairs = synthetic_fixture.load_pairs()
    keys = list(pairs["pair_key"])
    assert len(keys) == len(set(keys))
    assert not any(a == b for a, b in keys)


def test_every_pair_references_a_known_drug():
    drugs = set(synthetic_fixture.load_drugs()["name"])
    pairs = synthetic_fixture.load_pairs()
    used = set(pairs["drug_a"]) | set(pairs["drug_b"])
    assert used <= drugs, f"unknown drugs in pair table: {sorted(used - drugs)}"


def test_severity_values_are_from_the_controlled_vocabulary():
    pairs = synthetic_fixture.load_pairs()
    assert set(pairs["severity"]) <= set(synthetic_fixture.SEVERITY_ORDER)


def test_dangerous_flag_matches_major_severity():
    pairs = synthetic_fixture.load_pairs()
    assert (pairs["is_dangerous"] == (pairs["severity"] == "major")).all()
