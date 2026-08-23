"""Tests for the Phase A model.

Scope note: co-attention, the ordinal severity head and the mechanism head were
removed from this branch (see src/ddinet/models/ddinet.py) and preserved on
``feature/coattention-phase-b``. Their tests moved with them.

The symmetry tests are the important ones here: a DDI is symmetric, and a model
that scores (A,B) differently from (B,A) is broken in a way a judge can
demonstrate at a poster in ten seconds.
"""
import numpy as np
import pytest
import torch
from torch_geometric.loader import DataLoader

from ddinet.data import assemble, synthetic_fixture, split as split_mod
from ddinet.features.build import FeatureConfig, build_feature_bundle
from ddinet.features.molgraph import ATOM_FEATURE_DIM, BOND_FEATURE_DIM
from ddinet.models.ddinet import DDINet, DDINetConfig, compute_loss
from ddinet.models.train import Trainer, TrainConfig


@pytest.fixture(scope="module")
def setup():
    drugs = synthetic_fixture.load_drugs()
    pairs = synthetic_fixture.load_pairs()
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


def test_symmetry_survives_training(setup):
    """Symmetry is architectural, not learned - it must hold after fitting."""
    bundle, mol_batch, dataset = setup
    torch.manual_seed(0)
    model = make_model(bundle)
    Trainer(model, bundle, dataset,
            TrainConfig(epochs=3, patience=3, verbose=False)).fit()
    g = bundle.graph
    ia, ib = torch.tensor([1, 4, 9]), torch.tensor([12, 30, 44])
    model.eval()
    with torch.no_grad():
        f = model(mol_batch, g.node_features, g.edge_index, g.edge_type, ia, ib)
        r = model(mol_batch, g.node_features, g.edge_index, g.edge_type, ib, ia)
    assert torch.allclose(f.interaction_logit, r.interaction_logit, atol=1e-5)


# -- Phase A scope guard ----------------------------------------------------

def test_phase_b_components_are_absent():
    """Phase A must vary only the split scheme, so the architecture is fixed.

    If someone reintroduces co-attention or the auxiliary heads on this branch,
    the leakage experiment silently becomes confounded - two variables changing
    at once. This test makes that regression loud.
    """
    import ddinet.models.ddinet as m

    for removed in ("SubstructureCoAttention", "ordinal_severity_loss", "LossWeights"):
        assert not hasattr(m, removed), (
            f"{removed} belongs to Phase B (branch feature/coattention-phase-b), "
            f"not to the Phase A leakage benchmark"
        )
    cfg = DDINetConfig(atom_dim=1, bond_dim=1, node_feature_dim=1)
    for removed in ("use_coattention", "predict_severity", "predict_mechanism"):
        assert not hasattr(cfg, removed)


# -- Ablations --------------------------------------------------------------

@pytest.mark.parametrize(
    "flags,expected_blocks",
    [
        ({}, 4),                                    # molecular + graph
        ({"use_graph_branch": False}, 2),
        ({"use_molecular_branch": False}, 2),
    ],
)
def test_ablation_fusion_width_matches_active_branches(setup, flags, expected_blocks):
    """Disabled branches must shrink the fusion layer, not feed it zeros.

    Feeding zeros would leave dead parameters and make the ablation unfair - the
    ablated model would carry capacity it cannot use.
    """
    bundle, _, _ = setup
    assert make_model(bundle, **flags).fusion_dim == expected_blocks * 64


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
    plain, _ = compute_loss(pred, labels)
    weighted, _ = compute_loss(pred, labels, pos_weight=torch.tensor(5.0))
    assert float(weighted) > float(plain)


def test_gradients_reach_every_branch(setup):
    """A branch receiving no gradient is silently doing nothing."""
    bundle, mol_batch, _ = setup
    model = make_model(bundle)
    g = bundle.graph
    pred = model(mol_batch, g.node_features, g.edge_index, g.edge_type,
                 torch.arange(0, 8), torch.arange(8, 16))
    loss, _ = compute_loss(pred, torch.tensor([1, 0, 1, 0, 1, 0, 1, 0]))
    loss.backward()
    for branch in ("mol_encoder", "graph_encoder", "fusion"):
        grads = [p.grad for p in getattr(model, branch).parameters() if p.grad is not None]
        assert grads, f"{branch} received no gradient"
        assert any(float(gr.abs().sum()) > 0 for gr in grads), f"{branch} gradient all zero"


# -- Training ---------------------------------------------------------------

def test_training_reduces_loss(setup):
    bundle, _, dataset = setup
    torch.manual_seed(0)
    history = Trainer(make_model(bundle), bundle, dataset,
                      TrainConfig(epochs=15, patience=15, verbose=False, seed=0)).fit()
    assert history.train_loss[-1] < history.train_loss[0]


def test_trainer_restores_the_best_checkpoint(setup):
    bundle, _, dataset = setup
    torch.manual_seed(0)
    trainer = Trainer(make_model(bundle), bundle, dataset,
                      TrainConfig(epochs=12, patience=12, verbose=False, seed=0))
    history = trainer.fit()
    y, s = trainer.predict_bucket(history.selection_bucket)
    from ddinet.eval.metrics import compute_binary_metrics
    assert compute_binary_metrics(y, s).auprc == pytest.approx(history.best_score, abs=1e-4)


def test_pos_weight_is_capped(setup):
    """Uncapped weighting on a 1:50 split makes the model predict all-positive."""
    bundle, _, _ = setup
    drugs = synthetic_fixture.load_drugs()
    pairs = synthetic_fixture.load_pairs()
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
        trainer = Trainer(make_model(bundle), bundle, dataset,
                          TrainConfig(epochs=5, patience=5, verbose=False, seed=0))
        trainer.fit()
        _, s = trainer.predict_bucket("val_S2")
        scores.append(s)
    assert np.allclose(scores[0], scores[1], atol=1e-5)
