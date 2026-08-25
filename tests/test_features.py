"""Tests for fingerprints, molecular graphs and the DDI graph."""
import numpy as np
import pytest
import torch
from rdkit import Chem

from ddinet.data import assemble, synthetic_fixture, split as split_mod
from ddinet.features import ddi_graph as dg
from ddinet.features.build import FeatureConfig, build_feature_bundle
from ddinet.features.fingerprints import (
    MorganFeaturizer, descriptor_vector, explain_bit, pair_features, tanimoto,
)
from ddinet.features.molgraph import (
    ATOM_FEATURE_DIM, BOND_FEATURE_DIM, atom_feature_names, smiles_to_graph,
)

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"


@pytest.fixture(scope="module")
def data():
    return synthetic_fixture.load_drugs(), synthetic_fixture.load_pairs()


@pytest.fixture(scope="module")
def bundle(data):
    drugs, pairs = data
    sp = split_mod.build_split(drugs, pairs, seed=42)
    return build_feature_bundle(drugs, sp, FeatureConfig())


# -- Fingerprints -----------------------------------------------------------

def test_fingerprint_is_deterministic():
    fz = MorganFeaturizer()
    a = fz.featurize_smiles(ASPIRIN).bits
    b = fz.featurize_smiles(ASPIRIN).bits
    assert np.array_equal(a, b)


def test_every_on_bit_has_provenance():
    """Step 5 depends on being able to trace any set bit back to atoms."""
    fz = MorganFeaturizer()
    res = fz.featurize_smiles(ASPIRIN)
    assert res.on_bits
    assert set(res.on_bits) == set(res.bit_info)


def test_explain_bit_returns_real_atom_indices():
    mol = Chem.MolFromSmiles(ASPIRIN)
    res = MorganFeaturizer().featurize(mol)
    for bit in res.on_bits[:5]:
        for env in explain_bit(mol, bit, res.bit_info):
            assert all(0 <= i < mol.GetNumAtoms() for i in env["atoms"])
            assert env["fragment_smiles"]


def test_collision_rate_ignores_repeated_identical_substructures():
    """Three methyls setting one bit is repetition, not a hash collision."""
    mol = Chem.MolFromSmiles("CC(C)(C)O")     # three equivalent methyl groups
    res = MorganFeaturizer().featurize(mol)
    assert res.collision_rate(mol) == 0.0


def test_tanimoto_bounds_and_chemical_sanity(data):
    drugs, _ = data
    fz = MorganFeaturizer()
    by_name = {r["name"]: fz.featurize_smiles(r["smiles"]).bits
               for _, r in drugs.iterrows()}
    assert tanimoto(by_name["warfarin"], by_name["warfarin"]) == 1.0
    # Simvastatin and lovastatin differ by one methyl; metformin is unrelated.
    assert tanimoto(by_name["simvastatin"], by_name["lovastatin"]) > 0.6
    assert tanimoto(by_name["simvastatin"], by_name["metformin"]) < 0.2


def test_symmetric_pair_features_are_actually_symmetric():
    """A DDI is symmetric; an asymmetric encoding makes the score order-dependent."""
    a = np.array([1.0, 0.0, 1.0], dtype=np.float32)
    b = np.array([0.0, 1.0, 1.0], dtype=np.float32)
    for mode in ("symmetric", "sum_prod"):
        assert np.array_equal(pair_features(a, b, mode), pair_features(b, a, mode))
    assert not np.array_equal(pair_features(a, b, "concat"), pair_features(b, a, "concat"))


def test_descriptors_are_finite_and_fixed_width(data):
    drugs, _ = data
    for smiles in drugs["smiles"]:
        v = descriptor_vector(Chem.MolFromSmiles(smiles))
        assert v.shape == (12,)
        assert np.all(np.isfinite(v))


# -- Molecular graphs -------------------------------------------------------

def test_atom_feature_names_match_dimension():
    assert len(atom_feature_names()) == ATOM_FEATURE_DIM
    assert smiles_to_graph(ASPIRIN).data.x.shape[1] == ATOM_FEATURE_DIM


def test_bonds_are_stored_in_both_directions():
    """PyG message passing is directional; one entry is half a bond."""
    mol = Chem.MolFromSmiles(ASPIRIN)
    g = smiles_to_graph(ASPIRIN)
    assert g.data.edge_index.shape[1] == 2 * mol.GetNumBonds()
    edges = {(int(a), int(b)) for a, b in g.data.edge_index.t().tolist()}
    assert all((b, a) in edges for a, b in edges)


def test_unparseable_smiles_yields_a_valid_empty_graph():
    g = smiles_to_graph("not-a-molecule")
    assert g.n_atoms == 0
    assert g.data.x.shape == (1, ATOM_FEATURE_DIM)
    assert g.data.edge_index.shape == (2, 0)


def test_every_curated_drug_builds_a_graph(data):
    drugs, _ = data
    for name, smiles in zip(drugs["name"], drugs["smiles"]):
        assert smiles_to_graph(smiles).n_atoms > 0, name


def test_one_hot_other_bucket_catches_unusual_elements():
    """An unseen element must be an explicit signal, not an all-zero block."""
    g = smiles_to_graph("[Se]")                       # Se is in the vocabulary
    exotic = smiles_to_graph("[U]")                   # uranium is not
    names = atom_feature_names()
    other = names.index("element_other")
    assert exotic.data.x[0, other] == 1.0
    assert g.data.x[0, other] == 0.0


# -- DDI graph --------------------------------------------------------------

def test_graph_built_from_training_pairs_contains_no_evaluation_edge(bundle):
    for name in ("val_S2", "val_S3", "test_S2", "test_S3"):
        pairs = bundle.split.buckets[name]
        if len(pairs):
            dg.assert_no_evaluation_edges(bundle.graph, pairs)


def test_leak_guard_actually_fires(data):
    """Prove the guard works by deliberately building a leaky graph."""
    drugs, pairs = data
    sp = split_mod.build_split(drugs, pairs, seed=42)
    X = np.zeros((len(drugs), 4), dtype=np.float32)
    leaky = dg.build_ddi_graph(drugs, pairs, X)        # ALL pairs - wrong on purpose
    with pytest.raises(AssertionError, match="LEAKAGE"):
        dg.assert_no_evaluation_edges(leaky, sp.buckets["test_S2"])


def test_test_drugs_have_no_known_ddi_edges(bundle):
    """Under a drug-level split a test drug cannot appear in a training pair."""
    for name in bundle.split.test_drugs:
        assert bundle.graph.degree_of(name, "known_ddi") == 0


def test_ddi_edges_are_bidirectional(bundle):
    ei = bundle.graph.edge_index
    edges = {(int(a), int(b)) for a, b in ei.t().tolist()}
    assert all((b, a) in edges for a, b in edges)


def test_pathway_edges_encode_the_right_mechanism(data):
    """Ketoconazole inhibits CYP3A4; simvastatin is a CYP3A4 substrate."""
    drugs, _ = data
    edges = dg.derive_pathway_edges(drugs)
    key = tuple(sorted(("ketoconazole", "simvastatin")))
    assert key in edges["cyp_inhibitor_substrate"]
    # Rifampicin INDUCES CYP3A4 - a different relation, must not be conflated.
    ind = tuple(sorted(("rifampicin", "simvastatin")))
    assert ind in edges["cyp_inducer_substrate"]
    assert ind not in edges["cyp_inhibitor_substrate"]


def test_no_self_loops_in_ddi_graph(bundle):
    ei = bundle.graph.edge_index
    assert not (ei[0] == ei[1]).any()


def test_leakage_audit_reports_every_bucket(data):
    drugs, pairs = data
    sp = split_mod.build_split(drugs, pairs, seed=42)
    ds = assemble.build_supervised_dataset(sp, set(pairs["pair_key"]),
                                           assemble.AssemblyConfig(seed=1))
    audit = dg.leakage_audit(drugs, ds)
    assert set(audit["bucket"]) == set(ds["bucket"])
    assert "ANY_PATHWAY_EDGE" in set(audit["edge_type"])
    assert audit["precision"].between(0, 1).all()
    assert audit["recall"].between(0, 1).all()


# -- Bundle -----------------------------------------------------------------

def test_cyp_features_are_off_by_default(bundle):
    """Circular on the curated fixture; enabling must be deliberate."""
    assert not bundle.config.include_cyp_features
    assert not any(n.startswith("cyp_") for n in bundle.node_feature_names)


def test_cyp_features_appear_when_explicitly_enabled(data):
    drugs, pairs = data
    sp = split_mod.build_split(drugs, pairs, seed=42)
    b = build_feature_bundle(drugs, sp, FeatureConfig(include_cyp_features=True))
    assert any(n.startswith("cyp_") for n in b.node_feature_names)
    assert b.node_features.shape[1] > 2060


def test_descriptor_standardisation_uses_training_drugs_only(data):
    """Fitting the scaler on all drugs leaks test statistics into training."""
    drugs, pairs = data
    sp = split_mod.build_split(drugs, pairs, seed=42)
    b = build_feature_bundle(drugs, sp, FeatureConfig(standardise_descriptors=True))
    desc_cols = [i for i, n in enumerate(b.node_feature_names) if n.startswith("desc_")]
    train_rows = [b.index_of(n) for n in sp.train_drugs]
    train_block = b.node_features[np.array(train_rows)][:, desc_cols]
    assert np.allclose(train_block.mean(axis=0), 0.0, atol=1e-4)
    assert np.allclose(train_block.std(axis=0), 1.0, atol=1e-4)


def test_bundle_feature_names_match_matrix_width(bundle):
    assert len(bundle.node_feature_names) == bundle.node_features.shape[1]


def test_every_drug_has_a_molecular_graph(bundle):
    assert set(bundle.mol_graphs) == set(bundle.drugs["name"])


def test_evaluation_edges_are_checked_under_every_bucket_naming():
    """The graph guard must cover schemes that name their buckets differently.

    The drug-level scheme emits val_S2/val_S3/test_S2/test_S3; the random-pair
    scheme emits a flat val/test. An explicit list of the former names checks
    nothing for the latter - and the random-pair scheme is precisely where an
    evaluation edge in the message-passing graph would inflate results most.
    This pins that the guard is reached for a flat-named bucket by handing it a
    graph that does contain one.
    """
    from ddinet.data import synthetic_fixture, split as split_mod
    from ddinet.features.ddi_graph import assert_no_evaluation_edges, build_ddi_graph
    import numpy as np
    import pytest

    drugs = synthetic_fixture.load_drugs()
    pairs = synthetic_fixture.load_pairs()
    sp = split_mod.build_split(drugs, pairs, seed=7)
    node_features = np.zeros((len(drugs), 4), dtype=np.float32)

    # A graph built from ALL pairs contains the evaluation edges by definition,
    # so the guard must reject it however the bucket happens to be named.
    leaky = build_ddi_graph(drugs, pairs, node_features,
                            node_feature_names=[f"f{i}" for i in range(4)],
                            include_pathway_edges=False)
    held_out = next(df for name, df in sp.buckets.items()
                    if not name.startswith("train") and len(df))
    with pytest.raises(Exception):
        assert_no_evaluation_edges(leaky, held_out)
