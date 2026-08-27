"""
Adversarial degree-debiasing - the project's own architectural contribution.

WHAT THIS IS FOR
----------------
Phase A measured that a degree-only baseline reaches AUPRC 0.868 on
``random_pair`` + uniform negatives. Phase A-2 measured that the network
branch's embedding encodes the training-graph degree at R^2 0.885-0.954
(``scripts/23_degree_shortcut_probe.py``). Together those say: a large part of
what the "graph neural network" contributes is a count of how many
interactions a drug already has documented.

That count is not pharmacology. It is a measure of how much attention the drug
has received from researchers. A model built on it will look excellent on a
benchmark and fail on exactly the drugs a clinician cares about - the new ones,
which have no documented interactions by definition.

DrugCentral coverage makes this worse, not better. Drugs with target
annotations have median training-graph degree 252; drugs without have 64
(Mann-Whitney p = 2.4e-56, Cohen d = 0.803; DATA_PROVENANCE.md). So the
biological branch, if added naively, is fed preferentially by the very drugs
where the degree shortcut already works.

THE IDEA
--------
Train the encoder so that its embedding is *predictively useless for degree*
while remaining useful for interaction prediction. A small head tries to read
the degree off the embedding; the gradient flowing back from that head into the
encoder is **reversed**, so the encoder is pushed to destroy exactly the
information the head is trying to use. This is the domain-adversarial trick of
Ganin & Lempitsky (2015), applied to a nuisance variable instead of a domain
label.

WHY THIS IS A REAL EXPERIMENT AND NOT A TRICK
----------------------------------------------
The result is informative whichever way it goes, which is the property a good
experiment needs:

  * degree R^2 collapses AND AUPRC holds
        -> the model was not relying on degree for its predictions; the
           shortcut was present in the embedding but not load-bearing.
  * degree R^2 collapses AND AUPRC collapses with it
        -> the model *was* relying on degree, and we have measured how much of
           its reported performance that dependence was worth.
  * degree R^2 does not move
        -> the adversary failed. Report the failure, do not report the AUPRC as
           if debiasing had happened.

THE FAILURE MODE THIS CODE MUST NOT HIDE
-----------------------------------------
An encoder can defeat a degree head cheaply by shrinking its output towards a
constant. Degree becomes unpredictable, but so does everything else, and the
interaction loss quietly compensates elsewhere. A drop in degree R^2 is
therefore **not on its own** evidence of successful debiasing. Any run using
this module must report, together:

    (1) degree R^2 from an independently fitted probe (not the adversary's own
        head - it has been sabotaged and its loss means nothing),
    (2) interaction AUPRC,
    (3) the embedding's variance, so collapse is visible rather than inferred.

``DegreeAdversary.diagnostics`` returns (3); (1) comes from the standalone
probe in ``scripts/23_degree_shortcut_probe.py``, re-run on the debiased model.

WHY log1p(degree) AND NOT RAW COUNT OR A CLASS LABEL
-----------------------------------------------------
Degree is heavy-tailed: median 252 among covered drugs, maximum in the
thousands. Raw-count regression would be dominated by a handful of hubs. The
existing degree-only baseline, the ``use_degree_feature`` control, and the
shortcut probe all use ``log1p``, so using it here keeps every degree number in
the project on one scale and makes the adversary's target identical to the
quantity the probe measures.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import nn
from torch.autograd import Function


class _GradientReversal(Function):
    """Identity forward, negated-and-scaled gradient backward.

    The whole adversarial mechanism is this one sign flip. Forward, the
    embedding passes through untouched, so the degree head sees exactly what
    the encoder produced. Backward, the head's gradient arrives at the encoder
    multiplied by ``-lambda``, so the encoder moves to make the head *worse*
    while the head itself still moves to get better.
    """

    @staticmethod
    def forward(ctx, x: torch.Tensor, lambd: float) -> torch.Tensor:
        ctx.lambd = lambd
        # view_as() rather than returning x: autograd needs a distinct output
        # node, otherwise the custom backward can be bypassed entirely.
        return x.view_as(x)

    @staticmethod
    def backward(ctx, grad_output: torch.Tensor):
        # None: `lambd` is a plain float, not a differentiable input.
        return grad_output.neg() * ctx.lambd, None


def gradient_reversal(x: torch.Tensor, lambd: float) -> torch.Tensor:
    """Public wrapper so callers never touch the Function subclass directly."""
    return _GradientReversal.apply(x, lambd)


def dann_lambda(progress: float, gamma: float = 10.0, max_lambda: float = 1.0) -> float:
    """Ganin & Lempitsky's ramp: 2/(1+exp(-gamma*p)) - 1, scaled.

    WHY A RAMP AND NOT A CONSTANT
    -----------------------------
    At the start of training the encoder is random, so the degree head has
    nothing meaningful to read and its gradient is noise. Reversing noise and
    feeding it to the encoder at full strength destabilises the early epochs
    and, in the worst case, prevents the model from ever fitting - the exact
    failure this project already made once (FAILURE_CASE.md section 6a). The
    ramp starts the adversarial pressure at zero and reaches ``max_lambda``
    asymptotically.

    This matters more here than in the original paper: training is FULL-BATCH,
    so one epoch is one optimiser step. ``progress`` must therefore be measured
    in steps taken over steps budgeted, not in samples seen.

    :param progress: fraction of training completed, clamped to [0, 1].
    """
    p = min(max(progress, 0.0), 1.0)
    return max_lambda * (2.0 / (1.0 + torch.exp(torch.tensor(-gamma * p))).item() - 1.0)


@dataclass
class AdversaryOutput:
    """What one adversarial step produced, for logging and for the loss."""

    loss: torch.Tensor
    #: Current reversal strength, so the schedule is visible in the log.
    lambd: float
    #: Mean per-dimension variance of the embedding the adversary saw. A
    #: collapsing encoder shows up here as a number heading for zero, which is
    #: the difference between "degree was removed" and "everything was removed".
    embedding_variance: float
    #: The adversary's own MSE on log1p(degree). Diagnostic ONLY - this head is
    #: being actively sabotaged, so a high value is not evidence of debiasing.
    degree_mse: float


class DegreeAdversary(nn.Module):
    """A small head that reads degree off an embedding, trained against it.

    Deliberately small (one hidden layer). A high-capacity adversary would win
    outright and drive the encoder to collapse; a linear one would be too weak
    to notice anything but the crudest encoding. One hidden layer matches the
    capacity of the linear probe used to *measure* the shortcut (R^2 of a linear
    map), plus a little slack so the encoder cannot escape by making the
    relationship merely non-linear.
    """

    def __init__(self, embedding_dim: int, hidden_dim: int | None = None) -> None:
        super().__init__()
        hidden = hidden_dim if hidden_dim is not None else max(embedding_dim // 2, 8)
        self.net = nn.Sequential(
            nn.Linear(embedding_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, 1),
        )

    def forward(
        self,
        embedding: torch.Tensor,
        log_degree: torch.Tensor,
        lambd: float,
    ) -> AdversaryOutput:
        """Score ``embedding`` against ``log_degree`` through a reversal layer.

        :param embedding: (n_nodes, dim). Should be the embedding of the branch
            under test, restricted to nodes whose degree is meaningful - i.e.
            TRAINING drugs. Passing held-out drugs would ask the adversary to
            predict a degree of zero that is an artefact of the split, not a
            property of the drug.
        :param log_degree: (n_nodes,) ``log1p`` of training-graph degree.
        :param lambd: reversal strength for this step (see ``dann_lambda``).
        """
        if embedding.dim() != 2:
            raise ValueError(
                f"embedding must be 2-D (n_nodes, dim), got {tuple(embedding.shape)}"
            )
        if log_degree.dim() != 1:
            raise ValueError(
                f"log_degree must be 1-D, got {tuple(log_degree.shape)}"
            )
        if embedding.shape[0] != log_degree.shape[0]:
            raise ValueError(
                f"embedding has {embedding.shape[0]} rows but log_degree has "
                f"{log_degree.shape[0]} - they must be row-aligned over the same nodes"
            )

        reversed_emb = gradient_reversal(embedding, lambd)
        pred = self.net(reversed_emb).squeeze(-1)
        loss = nn.functional.mse_loss(pred, log_degree)

        # Detached: these are for the log, and must never contribute gradient.
        with torch.no_grad():
            var = embedding.var(dim=0, unbiased=False).mean().item()

        return AdversaryOutput(
            loss=loss,
            lambd=lambd,
            embedding_variance=var,
            degree_mse=float(loss.detach()),
        )
