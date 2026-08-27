"""Tests for adversarial degree-debiasing.

The tests that matter here are not "does it run" but "does it do the thing, and
does it tell us when it has not". An adversarial component that silently fails
is worse than none: it produces a debiased-looking number that was never
debiased.
"""
import numpy as np
import pytest
import torch
from torch import nn

from ddinet.models.adversarial import (
    AdversaryOutput,
    DegreeAdversary,
    dann_lambda,
    gradient_reversal,
)


# --------------------------------------------------------------------------
# The reversal itself
# --------------------------------------------------------------------------

def test_gradient_reversal_is_identity_in_the_forward_pass():
    x = torch.randn(6, 4)
    assert torch.equal(gradient_reversal(x, 3.0), x)


def test_gradient_reversal_negates_and_scales_the_backward_pass():
    """The entire mechanism is this sign flip; if it is wrong, the encoder is
    being trained to *help* the adversary and the experiment measures the
    opposite of what it claims."""
    x = torch.randn(5, 3, requires_grad=True)
    gradient_reversal(x, 2.5).sum().backward()
    assert torch.allclose(x.grad, torch.full((5, 3), -2.5))


def test_zero_lambda_stops_the_adversary_influencing_the_encoder():
    """lambda=0 must be a true no-op, because that is what the ramp starts at
    and what an ablation run sets."""
    x = torch.randn(5, 3, requires_grad=True)
    gradient_reversal(x, 0.0).sum().backward()
    assert torch.allclose(x.grad, torch.zeros(5, 3))


# --------------------------------------------------------------------------
# The schedule
# --------------------------------------------------------------------------

def test_ramp_starts_at_zero_and_increases_monotonically():
    vals = [dann_lambda(p) for p in np.linspace(0.0, 1.0, 11)]
    assert vals[0] == pytest.approx(0.0, abs=1e-9)
    assert all(b >= a for a, b in zip(vals, vals[1:]))
    assert vals[-1] == pytest.approx(1.0, abs=1e-3)


def test_ramp_clamps_progress_outside_the_unit_interval():
    """epochs_run can exceed the budget when a run is resumed from checkpoint;
    the schedule must not blow up or go negative there."""
    assert dann_lambda(-0.5) == pytest.approx(0.0, abs=1e-9)
    assert dann_lambda(3.0) == pytest.approx(dann_lambda(1.0), abs=1e-9)


def test_ramp_respects_max_lambda():
    assert dann_lambda(1.0, max_lambda=0.3) == pytest.approx(0.3, abs=1e-3)


# --------------------------------------------------------------------------
# Input contract
# --------------------------------------------------------------------------

def test_misaligned_rows_raise_rather_than_broadcast():
    """Silent broadcasting here would pair each drug with another drug's degree
    and train the adversary on nonsense, which looks like successful debiasing."""
    adv = DegreeAdversary(4)
    with pytest.raises(ValueError, match="row-aligned"):
        adv(torch.randn(7, 4), torch.rand(5), 0.5)


def test_wrong_dimensionality_raises():
    adv = DegreeAdversary(4)
    with pytest.raises(ValueError, match="2-D"):
        adv(torch.randn(7), torch.rand(7), 0.5)
    with pytest.raises(ValueError, match="1-D"):
        adv(torch.randn(7, 4), torch.rand(7, 1), 0.5)


# --------------------------------------------------------------------------
# The behaviour the whole module exists for
# --------------------------------------------------------------------------

def _fit(embedding: torch.Tensor, target: torch.Tensor) -> float:
    """R^2 of an independently fitted linear probe.

    Deliberately NOT the adversary's own head: that head is being sabotaged, so
    its loss is not a measurement of anything. This mirrors what
    scripts/23_degree_shortcut_probe.py does on the real model.
    """
    x = embedding.detach().numpy()
    y = target.detach().numpy()
    x = np.hstack([x, np.ones((len(x), 1))])
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    resid = y - x @ beta
    ss_res = float((resid ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return 1.0 - ss_res / ss_tot


def test_adversary_reduces_degree_predictability_of_the_embedding():
    """End-to-end: an encoder whose input carries degree learns to hide it.

    Setup: node features literally contain log-degree in one column, so an
    un-pressured encoder passes it straight through and the probe recovers it
    almost perfectly. Under reversal the encoder must destroy it.
    """
    torch.manual_seed(0)
    n, dim = 400, 8
    log_deg = torch.log1p(torch.randint(0, 300, (n,)).float())
    # Feature 0 is the degree; the rest is unrelated signal.
    feats = torch.randn(n, dim)
    feats[:, 0] = log_deg

    def run(lambd: float) -> tuple[float, float]:
        torch.manual_seed(1)
        encoder = nn.Sequential(nn.Linear(dim, dim), nn.ReLU(), nn.Linear(dim, dim))
        adv = DegreeAdversary(dim)
        opt = torch.optim.Adam(
            list(encoder.parameters()) + list(adv.parameters()), lr=1e-2
        )
        for _ in range(300):
            opt.zero_grad()
            emb = encoder(feats)
            adv(emb, log_deg, lambd).loss.backward()
            opt.step()
        emb = encoder(feats)
        return _fit(emb, log_deg), float(emb.var(dim=0).mean().detach())

    r2_off, var_off = run(0.0)  # adversary trains, encoder unaffected
    r2_on, var_on = run(1.0)    # adversary trains, encoder pushed against it

    # The control is not ~1.0: with lambda=0 the encoder receives no gradient at
    # all, so it stays at its random initialisation, and the ReLU there discards
    # part of the degree signal on its own. Measured: 0.609. What the control
    # has to establish is only that degree IS substantially recoverable when the
    # encoder is not being pressured.
    assert r2_off > 0.5, f"control failed: probe should recover degree, got {r2_off}"
    assert r2_on < 0.15, f"reversal left degree recoverable: R^2 = {r2_on}"
    assert r2_on < r2_off / 3, f"drop too small: {r2_on} vs {r2_off}"

    # And it must not have won by collapsing. Measured on this fixture the
    # variance rises (0.056 -> 14.5): the encoder spreads out while hiding
    # degree, rather than shrinking towards a constant.
    assert var_on > var_off / 10, (
        f"embedding collapsed instead of debiasing: var {var_off} -> {var_on}"
    )


def test_embedding_variance_is_reported_so_collapse_is_visible():
    """A collapsed encoder also defeats the adversary. Without this number we
    could not tell 'degree removed' from 'everything removed', and would report
    a debiasing that never happened."""
    adv = DegreeAdversary(4)
    alive = adv(torch.randn(50, 4), torch.rand(50), 0.5)
    collapsed = adv(torch.full((50, 4), 0.7), torch.rand(50), 0.5)
    assert alive.embedding_variance > 0.1
    assert collapsed.embedding_variance == pytest.approx(0.0, abs=1e-9)


def test_diagnostics_carry_no_gradient():
    """Logging values must never be part of the graph - a stray gradient path
    through a diagnostic would silently change training."""
    adv = DegreeAdversary(4)
    out = adv(torch.randn(9, 4, requires_grad=True), torch.rand(9), 0.5)
    assert isinstance(out, AdversaryOutput)
    assert isinstance(out.embedding_variance, float)
    assert isinstance(out.degree_mse, float)
    assert out.loss.requires_grad


# --------------------------------------------------------------------------
# Integration with DDINet
# --------------------------------------------------------------------------

def _cfg(**kw):
    from ddinet.models.ddinet import DDINetConfig
    base = dict(atom_dim=8, bond_dim=4, node_feature_dim=6, hidden_dim=16,
                architecture="gat")
    base.update(kw)
    return DDINetConfig(**base)


def test_flag_off_constructs_no_adversary_at_all():
    """Not merely unused - absent. An unused module still holds parameters that
    an optimiser would step and a checkpoint would carry."""
    from ddinet.models.ddinet import DDINet
    assert DDINet(_cfg()).degree_adversary is None
    assert DDINet(_cfg(adversarial_degree=True)).degree_adversary is not None


def test_enabling_the_adversary_does_not_perturb_any_other_weight():
    """THE safety property, and the reason the adversary is constructed last
    and conditionally.

    If building the adversary drew from the ambient RNG before the encoders,
    every other weight in the model would shift. A run with the flag off would
    then differ from a run made before the flag existed - which would silently
    invalidate resuming the Phase A-2 grid from its checkpoint, mixing two code
    versions inside one pre-registered experiment.
    """
    from ddinet.models.ddinet import DDINet
    from ddinet.models.train import set_seed

    set_seed(0); off = DDINet(_cfg())
    set_seed(0); on = DDINet(_cfg(adversarial_degree=True))

    shared = [k for k in off.state_dict() if not k.startswith("degree_adversary")]
    assert len(shared) > 10, "sanity: expected a non-trivial number of shared tensors"
    for key in shared:
        assert torch.equal(off.state_dict()[key], on.state_dict()[key]), (
            f"enabling the adversary changed {key}"
        )


def test_adversary_without_a_network_branch_is_refused():
    """Debiasing the network embedding is meaningless when there is none.
    Failing loudly beats reporting a debiasing that could not have happened."""
    from ddinet.models.ddinet import DDINet
    with pytest.raises(ValueError, match="nothing to debias"):
        DDINet(_cfg(adversarial_degree=True, use_graph_branch=False))


def test_adversarial_loss_refuses_when_degrees_were_never_installed():
    """The zero-default buffer would otherwise make the adversary regress onto
    a constant and 'succeed' without measuring anything."""
    from ddinet.models.ddinet import DDINet, DrugEncodings
    model = DDINet(_cfg(adversarial_degree=True))
    enc = DrugEncodings(
        torch.randn(5, 16), torch.randn(5, 3, 16),
        torch.ones(5, 3, dtype=torch.bool), torch.randn(5, 16), [],
    )
    with pytest.raises(RuntimeError, match="set_node_degree"):
        model.adversarial_loss(enc, torch.arange(5), progress=0.5)


def test_adversarial_loss_refuses_when_the_flag_is_off():
    from ddinet.models.ddinet import DDINet, DrugEncodings
    model = DDINet(_cfg())
    model.set_node_degree(torch.arange(5).float())
    enc = DrugEncodings(
        torch.randn(5, 16), torch.randn(5, 3, 16),
        torch.ones(5, 3, dtype=torch.bool), torch.randn(5, 16), [],
    )
    with pytest.raises(RuntimeError, match="never constructed"):
        model.adversarial_loss(enc, torch.arange(5), progress=0.5)


def test_ablation_name_records_the_adversary_and_its_strength():
    """Result rows are keyed by this string; a run whose name does not say it
    was debiased is a run that will be compared against the wrong baseline."""
    assert _cfg().ablation_name() == "gat"
    assert _cfg(adversarial_degree=True).ablation_name() == "gat+adv1"
    assert _cfg(adversarial_degree=True, adv_lambda_max=0.0).ablation_name() == "gat+adv0"


# --------------------------------------------------------------------------
# End-to-end through the Trainer
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def trainer_setup():
    from ddinet.data import assemble, synthetic_fixture, split as split_mod
    from ddinet.features.build import FeatureConfig, build_feature_bundle

    drugs = synthetic_fixture.load_drugs()
    pairs = synthetic_fixture.load_pairs()
    sp = split_mod.build_split(drugs, pairs, seed=42)
    bundle = build_feature_bundle(drugs, sp, FeatureConfig())
    dataset = assemble.build_supervised_dataset(
        sp, set(pairs["pair_key"]), assemble.AssemblyConfig(neg_ratio=2.0, seed=42)
    )
    return bundle, dataset


def _model(bundle, **overrides):
    from ddinet.features.molgraph import ATOM_FEATURE_DIM, BOND_FEATURE_DIM
    from ddinet.models.ddinet import DDINet, DDINetConfig
    return DDINet(DDINetConfig(
        atom_dim=ATOM_FEATURE_DIM, bond_dim=BOND_FEATURE_DIM,
        node_feature_dim=bundle.node_features.shape[1],
        hidden_dim=32, mol_layers=2, graph_layers=2, dropout=0.0, **overrides,
    ))


def _degrees(bundle, dataset):
    """Training-graph degree per node, ordered like the graph's nodes."""
    train = dataset[dataset["bucket"].str.startswith("train")]
    train = train[train["label"] == 1]
    counts = {}
    for a, b in zip(train["drug_a"], train["drug_b"]):
        counts[a] = counts.get(a, 0) + 1
        counts[b] = counts.get(b, 0) + 1
    order = list(bundle.drugs["name"])
    return torch.tensor([float(counts.get(n, 0)) for n in order])


def test_trainer_runs_with_the_adversary_and_records_its_diagnostics(trainer_setup):
    """The three numbers a debiased run must report have to actually reach the
    history object - a run that cannot report embedding variance cannot be
    distinguished from a collapsed one."""
    from ddinet.models.train import TrainConfig, Trainer, set_seed

    bundle, dataset = trainer_setup
    set_seed(0)
    model = _model(bundle, adversarial_degree=True, adv_lambda_max=1.0)
    model.set_node_degree(_degrees(bundle, dataset))
    hist = Trainer(model, bundle, dataset, TrainConfig(epochs=5, patience=5)).fit()

    assert len(hist.adv_lambda) == hist.epochs_run
    assert len(hist.adv_degree_mse) == hist.epochs_run
    assert len(hist.adv_embedding_variance) == hist.epochs_run
    # The ramp must actually move across the run, not sit at its start value.
    assert hist.adv_lambda[0] < hist.adv_lambda[-1]
    assert all(v > 0 for v in hist.adv_embedding_variance)


def test_trainer_without_an_adversary_records_nothing(trainer_setup):
    """Absence must be visible as empty lists, not as zeros that would be
    mistaken for measurements."""
    from ddinet.models.train import TrainConfig, Trainer, set_seed

    bundle, dataset = trainer_setup
    set_seed(0)
    hist = Trainer(
        _model(bundle), bundle, dataset, TrainConfig(epochs=3, patience=3)
    ).fit()
    assert hist.adv_lambda == []
    assert hist.adv_degree_mse == []
    assert hist.adv_embedding_variance == []


def test_adversary_off_gives_the_same_training_trajectory_as_before_the_feature(
    trainer_setup,
):
    """The safety property at the training level, not just at construction.

    A model with the flag off must follow exactly the trajectory it would have
    followed before this feature existed. If it does not, the Phase A-2 grid
    cannot be resumed from checkpoint across this commit.
    """
    from ddinet.models.train import TrainConfig, Trainer, set_seed

    bundle, dataset = trainer_setup
    losses = []
    for _ in range(2):
        set_seed(0)
        hist = Trainer(
            _model(bundle), bundle, dataset, TrainConfig(epochs=4, patience=4)
        ).fit()
        losses.append(hist.train_loss)
    assert losses[0] == losses[1], "training is not deterministic under a fixed seed"


def test_lambda_zero_builds_the_head_but_applies_no_pressure(trainer_setup):
    """The `adv0` control of DEBIAS_PROTOCOL.md: same parameters, same optimiser
    state, no adversarial gradient. Without it, base-vs-adv1 would confound
    debiasing with the extra capacity and the extra loss term."""
    from ddinet.models.train import TrainConfig, Trainer, set_seed

    bundle, dataset = trainer_setup
    set_seed(0)
    model = _model(bundle, adversarial_degree=True, adv_lambda_max=0.0)
    model.set_node_degree(_degrees(bundle, dataset))
    hist = Trainer(model, bundle, dataset, TrainConfig(epochs=4, patience=4)).fit()

    assert model.degree_adversary is not None, "the head must still exist"
    assert all(l == 0.0 for l in hist.adv_lambda), "lambda must stay at zero"
    # The head still learns - it is only the reversal into the encoder that is off.
    assert len(hist.adv_degree_mse) == hist.epochs_run
