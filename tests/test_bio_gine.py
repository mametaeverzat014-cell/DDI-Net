"""Tests for BIO-GINE.

The properties pinned here are the ones the preregistered hypotheses depend on.
If symmetry breaks, every pair is scored twice; if the MEAN aggregation quietly
becomes size-dependent, CONTROL C compares two models that both count; if the
MISSING token stops being reachable, 67 drugs are represented by whatever the
zero vector happens to mean.
"""
import numpy as np
import pytest
import torch

from ddinet.data.biology import EVIDENCE_POLICIES, BiologyBundle
from ddinet.models.bio_gine import (
    BiologicalSets,
    BioGine,
    BioGineConfig,
    DeepSetsEncoder,
)


def make_bundle(
    protein_items=None, pathway_items=None, n_prot=4, n_path=3
) -> BiologyBundle:
    protein_items = protein_items if protein_items is not None else [
        np.array([[0, 0, 0], [1, 1, 1]], dtype=np.int64),
        np.array([[2, 0, 2]], dtype=np.int64),
        np.zeros((0, 3), dtype=np.int64),
        np.array([[3, 3, 0]], dtype=np.int64),
    ]
    pathway_items = pathway_items if pathway_items is not None else [
        np.array([0], dtype=np.int64),
        np.array([0, 1], dtype=np.int64),
        np.zeros(0, dtype=np.int64),
        np.zeros(0, dtype=np.int64),
    ]
    n = len(protein_items)
    return BiologyBundle(
        drug_ids=[f"D{i}" for i in range(n)],
        protein_vocab=[f"P{i}" for i in range(n_prot)],
        pathway_vocab=[f"Q{i}" for i in range(n_path)],
        protein_items=protein_items,
        pathway_items=pathway_items,
        counts=np.zeros((n, 8)),
        policy=EVIDENCE_POLICIES["M4"],
    )


def make_model(bundle, **kwargs) -> BioGine:
    cfg = BioGineConfig(
        n_protein_vocab=bundle.n_proteins,
        n_pathway_vocab=bundle.n_pathways,
        use_molecular_branch=False,
        bio_dim=8,
        hidden_dim=16,
        **kwargs,
    )
    model = BioGine(cfg)
    model.set_biology(BiologicalSets(bundle))
    model.eval()
    return model


# -- symmetry -------------------------------------------------------------
def test_prediction_is_exactly_symmetric():
    m = make_model(make_bundle())
    h, mask = m.encode()
    a, b = torch.tensor([0, 1, 2, 3]), torch.tensor([3, 2, 1, 0])
    p1 = m.score_pairs(h, mask, a, b).interaction_logit
    p2 = m.score_pairs(h, mask, b, a).interaction_logit
    assert torch.equal(p1, p2)


def test_symmetry_holds_when_only_one_drug_has_biology():
    """The case a [mask_A | mask_B] concatenation would break."""
    m = make_model(make_bundle())
    h, mask = m.encode()
    a, b = torch.tensor([0]), torch.tensor([2])       # D2 has no biology at all
    assert torch.equal(
        m.score_pairs(h, mask, a, b).interaction_logit,
        m.score_pairs(h, mask, b, a).interaction_logit,
    )


# -- aggregation ----------------------------------------------------------
def test_mean_aggregation_is_invariant_to_duplicating_the_set():
    """MEAN must not see set size. A duplicated set has the same mean."""
    enc = DeepSetsEncoder(4, 8, 4, dropout=0.0, aggregation="mean").eval()
    x = torch.randn(3, 4)
    one = enc(x, torch.zeros(3, dtype=torch.long), 1,
              torch.tensor([3.0]), torch.tensor([False]))
    two = enc(torch.cat([x, x]), torch.zeros(6, dtype=torch.long), 1,
              torch.tensor([6.0]), torch.tensor([False]))
    assert torch.allclose(one, two, atol=1e-6)


def test_sum_aggregation_does_see_set_size():
    """CONTROL C only means anything if SUM and MEAN actually differ."""
    enc = DeepSetsEncoder(4, 8, 4, dropout=0.0, aggregation="sum").eval()
    x = torch.randn(3, 4)
    one = enc(x, torch.zeros(3, dtype=torch.long), 1,
              torch.tensor([3.0]), torch.tensor([False]))
    two = enc(torch.cat([x, x]), torch.zeros(6, dtype=torch.long), 1,
              torch.tensor([6.0]), torch.tensor([False]))
    assert not torch.allclose(one, two, atol=1e-4)


def test_aggregation_is_permutation_invariant():
    enc = DeepSetsEncoder(4, 8, 4, dropout=0.0, aggregation="mean").eval()
    x = torch.randn(5, 4)
    owner = torch.zeros(5, dtype=torch.long)
    a = enc(x, owner, 1, torch.tensor([5.0]), torch.tensor([False]))
    b = enc(x[torch.randperm(5)], owner, 1, torch.tensor([5.0]), torch.tensor([False]))
    assert torch.allclose(a, b, atol=1e-6)


def test_unknown_aggregation_rejected():
    with pytest.raises(ValueError, match="aggregation must be"):
        BioGineConfig(n_protein_vocab=1, n_pathway_vocab=1, aggregation="max")


# -- missing biology ------------------------------------------------------
def test_empty_set_takes_the_missing_token_not_zero():
    b = make_bundle()
    m = make_model(b)
    prot, _, _ = m.encode_biology()
    assert torch.allclose(prot[2], m.protein_encoder.missing)
    assert not torch.allclose(prot[0], m.protein_encoder.missing)


def test_missing_token_is_not_the_zero_vector():
    m = make_model(make_bundle())
    assert m.protein_encoder.missing.abs().sum() > 0


def test_missing_token_receives_gradient():
    m = make_model(make_bundle())
    m.train()
    h, mask = m.encode()
    loss = m.score_pairs(h, mask, torch.tensor([2]), torch.tensor([0])).interaction_logit.sum()
    loss.backward()
    assert m.protein_encoder.missing.grad is not None
    assert float(m.protein_encoder.missing.grad.norm()) > 0


def test_mask_reports_missing_modalities():
    m = make_model(make_bundle())
    _, _, mask = m.encode_biology()
    assert mask[0].tolist() == [1.0, 1.0]
    assert mask[2].tolist() == [0.0, 0.0]      # no proteins, no pathways
    assert mask[3].tolist() == [1.0, 0.0]      # proteins but no pathway


def test_all_empty_biology_still_forwards():
    """A policy that switches the protein level off must not produce NaN."""
    n = 3
    b = make_bundle(
        protein_items=[np.zeros((0, 3), dtype=np.int64)] * n,
        pathway_items=[np.zeros(0, dtype=np.int64)] * n,
    )
    m = make_model(b)
    h, mask = m.encode()
    assert torch.isfinite(h).all()
    assert mask.sum() == 0


# -- installation contract ------------------------------------------------
def test_forward_without_biology_raises():
    cfg = BioGineConfig(n_protein_vocab=4, n_pathway_vocab=3,
                        use_molecular_branch=False, bio_dim=8, hidden_dim=16)
    with pytest.raises(RuntimeError, match="set_biology"):
        BioGine(cfg).encode()


def test_vocabulary_mismatch_is_rejected():
    b = make_bundle()
    cfg = BioGineConfig(n_protein_vocab=99, n_pathway_vocab=b.n_pathways,
                        use_molecular_branch=False, bio_dim=8, hidden_dim=16)
    with pytest.raises(ValueError, match="protein vocabulary mismatch"):
        BioGine(cfg).set_biology(BiologicalSets(b))


def test_molecular_branch_without_dims_is_rejected():
    with pytest.raises(ValueError, match="atom_dim and bond_dim"):
        BioGine(BioGineConfig(n_protein_vocab=4, n_pathway_vocab=3))


def test_no_branches_is_rejected():
    with pytest.raises(ValueError, match="At least one branch"):
        BioGineConfig(n_protein_vocab=4, n_pathway_vocab=3,
                      use_molecular_branch=False, use_protein_level=False,
                      use_pathway_level=False)


# -- ablation bookkeeping -------------------------------------------------
def test_ablated_model_has_no_dead_parameters():
    b = make_bundle()
    full = make_model(b)
    no_path = make_model(b, use_pathway_level=False)
    assert no_path.pathway_embedding is None
    assert no_path.n_parameters() < full.n_parameters()
    assert no_path.fusion_input_dim == full.fusion_input_dim - full.config.bio_dim


def test_ablation_names_are_distinct():
    names = {
        BioGineConfig(n_protein_vocab=4, n_pathway_vocab=3, use_molecular_branch=False,
                      **kw).ablation_name()
        for kw in (
            {},
            {"use_pathway_level": False},
            {"use_protein_level": False},
            {"aggregation": "sum"},
        )
    }
    assert len(names) == 4


def test_parameter_table_sums_to_total():
    m = make_model(make_bundle())
    table = m.parameter_table()
    assert sum(v for k, v in table.items() if k != "total") == table["total"]


# -- ragged layout --------------------------------------------------------
def test_segment_layout_matches_the_bundle():
    b = make_bundle()
    s = BiologicalSets(b)
    assert s.protein_owner.tolist() == [0, 0, 1, 3]
    assert s.protein_size.tolist() == [2.0, 1.0, 0.0, 1.0]
    assert s.empty_protein.tolist() == [False, False, True, False]
    assert s.pathway_owner.tolist() == [0, 1, 1]


def test_biology_buffers_are_not_trainable_parameters():
    m = make_model(make_bundle())
    names = {n for n, _ in m.named_parameters()}
    assert "protein_id" not in names and "protein_owner" not in names


def test_encoding_is_deterministic_in_eval_mode():
    m = make_model(make_bundle())
    a, _ = m.encode()
    b, _ = m.encode()
    assert torch.equal(a, b)


# -- with the molecular branch -------------------------------------------
def test_full_model_is_symmetric_with_molecules():
    pytest.importorskip("rdkit")
    from torch_geometric.loader import DataLoader

    from ddinet.features.molgraph import (
        atom_feature_names,
        bond_feature_names,
        smiles_to_graph,
    )

    smiles = ["CCO", "c1ccccc1O", "CC(=O)Oc1ccccc1C(=O)O", "CN1C=NC2=C1C(=O)N(C)C(=O)N2C"]
    batch = next(iter(DataLoader([smiles_to_graph(s).data for s in smiles],
                                 batch_size=4, shuffle=False)))
    b = make_bundle()
    cfg = BioGineConfig(
        n_protein_vocab=b.n_proteins, n_pathway_vocab=b.n_pathways,
        atom_dim=len(atom_feature_names()), bond_dim=len(bond_feature_names()),
        bio_dim=8, hidden_dim=16, mol_dim=16,
    )
    m = BioGine(cfg)
    m.set_biology(BiologicalSets(b))
    m.eval()
    a, c = torch.tensor([0, 1, 2]), torch.tensor([3, 2, 0])
    assert torch.equal(
        m(batch, a, c).interaction_logit, m(batch, c, a).interaction_logit
    )
