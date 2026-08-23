"""Tests for the DDI-Net architecture.

The symmetry tests are the important ones: a DDI is symmetric, and a model that
scores (A,B) differently from (B,A) is broken in a way a judge can demonstrate
at your poster in ten seconds.
"""
import numpy as np
import pytest
import torch
from torch_geometric.loader import DataLoader

from ddinet.data import assemble, curated, split as split_mod
from ddinet.features.build import FeatureConfig, build_feature_bundle
from ddinet.features.molgraph import ATOM_FEATURE_DIM, BOND_FEATURE_DIM
from ddinet.models.ddinet import (
    DDINet, DDINetConfig, LossWeights, SubstructureCoAttention, compute_loss,
    ordinal_severity_loss,
)
from ddinet.models.train import Trainer, TrainConfig


@pytest.fixture(scope="module")
def setup():
    drugs, pairs = curated.load_drugs(), curated.load_pairs()
    sp = split_mod.build_split(drugs, pairs, seed=42)
    bundle = build_feature_bundle(drugs, sp, FeatureConfig())
    names = list(drugs["name"])
    loader = DataLoader([bundle.mol_graphs[n].data for n in names],
                        batch_size=len(names), shuffle=False)
    mol_batch = next(iter(loader))
    dataset = assemble.build_supervised_dataset(
        sp, set(pairs["pair_key"]), assemble.AssemblyConfig(neg_ratio=2.0, seed=42)
    )
    return bundle, mol_batch, dataset


def make_model(bundle, **overrides):
    cfg = DDINetConfig(
        atom_dim=ATOM_FEATURE_DIM,
        bond_dim=BOND_FEATURE_DIM,
        node_feature_dim=bundle.node_features.shape[1],
        hidden_dim=64, mol_layers=2, graph_layers=2, dropout=0.0,
        **overrides,
    )
    return DDINet(cfg)


# -- Symmetry ---------------------------------------------------------------

def test_bilinear_form_is_symmetric():
    """W = M + M^T is symmetric for any M, at any point in training."""
    ca = SubstructureCoAttention(16)
    assert torch.allclose(ca.W, ca.W.t())
    with torch.no_grad():
        ca.M.add_(torch.randn(16, 16))      # simulate an arbitrary update
    assert torch.allclose(ca.W, ca.W.t())


@pytest.mark.parametrize("architecture", ["gat", "sage", "gcn"])
def test_prediction_is_symmetric(setup, architecture):
    """f(A,B) must equal f(B,A) exactly, not approximately."""
    bundle, mol_batch, _ = setup
    torch.manual_seed(0)
    model = make_model(bundle, architecture=architecture).eval()
    g = bundle.graph
    ia = torch.tensor([0, 3, 7, 11, 20])
    ib = torch.tensor([5, 9, 2, 40, 33])
    with torch.no_grad():
        fwd = model(mol_batch, g.node_features, g.edge_index, g.edge_type, ia, ib)
        rev = model(mol_batch, g.node_features, g.edge_index, g.edge_type, ib, ia)
    assert torch.allclose(fwd.interaction_logit, rev.interaction_logit, atol=1e-5)
    assert torch.allclose(fwd.severity_logits, rev.severity_logits, atol=1e-5)


def test_symmetry_survives_training(setup):
    """A trained model must still be symmetric - it is architectural, not learned."""
    bundle, mol_batch, dataset = setup
    torch.manual_seed(0)
    model = make_model(bundle)
    trainer = Trainer(model, bundle, dataset,
                      TrainConfig(epochs=3, patience=3, verbose=False))
    trainer.fit()
    g = bundle.graph
    ia, ib = torch.tensor([1, 4, 9]), torch.tensor([12, 30, 44])
    model.eval()
    with torch.no_grad():
        f = model(mol_batch, g.node_features, g.edge_index, g.edge_type, ia, ib)
        r = model(mol_batch, g.node_features, g.edge_index, g.edge_type, ib, ia)
    assert torch.allclose(f.interaction_logit, r.interaction_logit, atol=1e-5)


# -- Ordinal severity head --------------------------------------------------

def test_cumulative_severity_is_monotone(setup):
    """P(>=major) can never exceed P(>=moderate) - enforced by construction."""
    bundle, mol_batch, _ = setup
    torch.manual_seed(1)
    model = make_model(bundle).eval()
    g = bundle.graph
    ia, ib = torch.arange(0, 30), torch.arange(30, 60)
    with torch.no_grad():
        pred = model(mol_batch, g.node_features, g.edge_index, g.edge_type, ia, ib)
    cum = torch.sigmoid(pred.severity_logits)
    assert (cum[:, 0] >= cum[:, 1] - 1e-6).all()


def test_severity_probabilities_are_valid_distribution(setup):
    bundle, mol_batch, _ = setup
    torch.manual_seed(1)
    model = make_model(bundle).eval()
    g = bundle.graph
    with torch.no_grad():
        pred = model(mol_batch, g.node_features, g.edge_index, g.edge_type,
                     torch.arange(0, 20), torch.arange(20, 40))
    probs = pred.severity_prob()
    assert probs.shape == (20, 3)
    assert (probs >= 0).all()
    assert torch.allclose(probs.sum(dim=1), torch.ones(20), atol=1e-5)


def test_ordinal_loss_penalises_bigger_rank_errors_more():
    """Confusing minor with major must cost more than minor with moderate."""
    rank_major = torch.tensor([2])
    mask = torch.tensor([True])
    # Confidently 'major' -> low loss for a major target.
    good = ordinal_severity_loss(torch.tensor([[6.0, 6.0]]), rank_major, mask)
    # Confidently 'moderate' -> wrong on the second threshold only.
    mid = ordinal_severity_loss(torch.tensor([[6.0, -6.0]]), rank_major, mask)
    # Confidently 'minor' -> wrong on both thresholds.
    bad = ordinal_severity_loss(torch.tensor([[-6.0, -6.0]]), rank_major, mask)
    assert good < mid < bad


def test_ordinal_loss_ignores_negative_pairs():
    """A negative pair has no severity; supervising on it would be meaningless."""
    logits = torch.randn(4, 2, requires_grad=True)
    loss = ordinal_severity_loss(logits, torch.tensor([-1, -1, -1, -1]),
                                 torch.tensor([False] * 4))
    assert float(loss.detach()) == 0.0
    loss.backward()          # must still be differentiable


# -- Ablations --------------------------------------------------------------

@pytest.mark.parametrize(
    "flags,expected_blocks",
    [
        ({}, 6),                                              # mol + coattn + graph
        ({"use_coattention": False}, 4),
        ({"use_graph_branch": False}, 4),
        ({"use_molecular_branch": False}, 2),                 # graph only
    ],
)
def test_ablation_fusion_width_matches_active_branches(setup, flags, expected_blocks):
    """Disabled branches must shrink the fusion layer, not feed it zeros.

    Feeding zeros would leave dead parameters and make the ablation comparison
    unfair - the ablated model would carry capacity it cannot use.
    """
    bundle, _, _ = setup
    model = make_model(bundle, **flags)
    assert model.fusion_dim == expected_blocks * 64


def test_graph_only_model_still_runs(setup):
    bundle, mol_batch, _ = setup
    model = make_model(bundle, use_molecular_branch=False).eval()
    g = bundle.graph
    with torch.no_grad():
        pred = model(mol_batch, g.node_features, g.edge_index, g.edge_type,
                     torch.tensor([0, 1]), torch.tensor([2, 3]))
    assert pred.interaction_logit.shape == (2,)


def test_disabling_every_branch_is_rejected(setup):
    bundle, _, _ = setup
    with pytest.raises(ValueError, match="At least one branch"):
        make_model(bundle, use_molecular_branch=False, use_graph_branch=False)


# -- Loss and gradients -----------------------------------------------------

def test_pos_weight_increases_the_cost_of_missing_a_positive(setup):
    bundle, mol_batch, _ = setup
    torch.manual_seed(0)
    model = make_model(bundle).eval()
    g = bundle.graph
    with torch.no_grad():
        pred = model(mol_batch, g.node_features, g.edge_index, g.edge_type,
                     torch.arange(0, 10), torch.arange(10, 20))
    labels = torch.ones(10, dtype=torch.long)
    sev = torch.full((10,), 2, dtype=torch.long)
    mech = torch.zeros(10, dtype=torch.long)
    plain, _ = compute_loss(pred, labels, sev, mech)
    weighted, _ = compute_loss(pred, labels, sev, mech,
                               pos_weight=torch.tensor(5.0))
    assert float(weighted) > float(plain)


def test_gradients_reach_every_branch(setup):
    """A branch with no gradient is silently doing nothing."""
    bundle, mol_batch, _ = setup
    model = make_model(bundle)
    g = bundle.graph
    pred = model(mol_batch, g.node_features, g.edge_index, g.edge_type,
                 torch.arange(0, 8), torch.arange(8, 16))
    loss, _ = compute_loss(
        pred, torch.tensor([1, 0, 1, 0, 1, 0, 1, 0]),
        torch.tensor([2, -1, 1, -1, 2, -1, 0, -1]),
        torch.tensor([0, -1, 1, -1, 0, -1, 1, -1]),
    )
    loss.backward()
    for branch in ("mol_encoder", "graph_encoder", "coattention", "fusion"):
        module = getattr(model, branch)
        grads = [p.grad for p in module.parameters() if p.grad is not None]
        assert grads, f"{branch} received no gradient"
        assert any(float(gr.abs().sum()) > 0 for gr in grads), f"{branch} gradient is all zero"


def test_loss_reports_every_active_task(setup):
    bundle, mol_batch, _ = setup
    model = make_model(bundle).eval()
    g = bundle.graph
    with torch.no_grad():
        pred = model(mol_batch, g.node_features, g.edge_index, g.edge_type,
                     torch.arange(0, 6), torch.arange(6, 12))
    _, parts = compute_loss(
        pred, torch.tensor([1, 1, 0, 1, 0, 1]),
        torch.tensor([2, 1, -1, 0, -1, 2]),
        torch.tensor([0, 1, -1, 0, -1, 1]),
        weights=LossWeights(1.0, 0.5, 0.25),
    )
    assert {"interaction", "severity", "mechanism", "total"} <= set(parts)
    assert all(np.isfinite(v) for v in parts.values())


# -- Co-attention -----------------------------------------------------------

def test_coattention_ignores_padded_atoms():
    """Padding must receive zero attention mass, or short molecules are corrupted."""
    torch.manual_seed(0)
    ca = SubstructureCoAttention(8)
    h_a, h_b = torch.randn(2, 5, 8), torch.randn(2, 5, 8)
    mask_a = torch.tensor([[1, 1, 1, 0, 0], [1, 1, 0, 0, 0]], dtype=torch.bool)
    mask_b = torch.tensor([[1, 1, 0, 0, 0], [1, 1, 1, 1, 0]], dtype=torch.bool)
    u, v, scores = ca(h_a, mask_a, h_b, mask_b)
    valid = mask_a.unsqueeze(2) & mask_b.unsqueeze(1)
    assert float(scores[~valid].abs().sum()) == 0.0
    assert torch.isfinite(u).all() and torch.isfinite(v).all()


def test_coattention_swap_exchanges_u_and_v():
    """The mechanism underlying whole-model symmetry."""
    torch.manual_seed(0)
    ca = SubstructureCoAttention(8)
    h_a, h_b = torch.randn(1, 4, 8), torch.randn(1, 6, 8)
    mask_a, mask_b = torch.ones(1, 4, dtype=torch.bool), torch.ones(1, 6, dtype=torch.bool)
    u, v, _ = ca(h_a, mask_a, h_b, mask_b)
    u2, v2, _ = ca(h_b, mask_b, h_a, mask_a)
    assert torch.allclose(u, v2, atol=1e-5)
    assert torch.allclose(v, u2, atol=1e-5)


# -- Training ---------------------------------------------------------------

def test_training_reduces_loss(setup):
    bundle, _, dataset = setup
    torch.manual_seed(0)
    model = make_model(bundle)
    trainer = Trainer(model, bundle, dataset,
                      TrainConfig(epochs=15, patience=15, verbose=False, seed=0))
    history = trainer.fit()
    assert history.train_loss[-1] < history.train_loss[0]


def test_trainer_restores_the_best_checkpoint(setup):
    bundle, _, dataset = setup
    torch.manual_seed(0)
    model = make_model(bundle)
    trainer = Trainer(model, bundle, dataset,
                      TrainConfig(epochs=12, patience=12, verbose=False, seed=0))
    history = trainer.fit()
    y, s, _ = trainer.predict_bucket(history.selection_bucket)
    from ddinet.eval.metrics import compute_binary_metrics
    assert compute_binary_metrics(y, s).auprc == pytest.approx(history.best_score, abs=1e-4)


def test_pos_weight_is_capped(setup):
    """Uncapped weighting on a 1:50 split makes the model predict all-positive."""
    bundle, _, _ = setup
    drugs, pairs = curated.load_drugs(), curated.load_pairs()
    sp = split_mod.build_split(drugs, pairs, seed=42)
    skewed = assemble.build_supervised_dataset(
        sp, set(pairs["pair_key"]), assemble.AssemblyConfig(neg_ratio=50.0, seed=1)
    )
    trainer = Trainer(make_model(bundle), bundle, skewed,
                      TrainConfig(max_pos_weight=10.0, verbose=False))
    assert float(trainer.pos_weight) == 10.0


def test_training_is_deterministic_under_a_fixed_seed(setup):
    bundle, _, dataset = setup
    scores = []
    for _ in range(2):
        torch.manual_seed(0)
        model = make_model(bundle)
        trainer = Trainer(model, bundle, dataset,
                          TrainConfig(epochs=5, patience=5, verbose=False, seed=0))
        trainer.fit()
        _, s, _ = trainer.predict_bucket("val_S2")
        scores.append(s)
    assert np.allclose(scores[0], scores[1], atol=1e-5)
