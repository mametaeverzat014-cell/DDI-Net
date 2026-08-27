"""
DDI-Net, Phase A model: a standard dual-branch GNN for pair classification.

SCOPE OF THIS FILE - READ BEFORE ADDING ANYTHING
------------------------------------------------
Phase A of this project asks one question: *how much of the reported
performance of DDI models is an artefact of data leakage, and does a GNN retain
an advantage over simple baselines under an honest split?*

To answer that, **the split scheme must be the only variable that changes.**
A custom architecture would confound the comparison: a drop from random-pair to
drug-level splitting could then be attributed either to the split or to the
architecture, and the experiment would answer neither question.

So this model is deliberately unremarkable: a standard GINE encoder over atom
graphs, a standard GNN encoder over the interaction graph, commutative fusion,
one binary head. No invented components.

The following were REMOVED from this file and preserved on the branch
``feature/coattention-phase-b``:

  * ``SubstructureCoAttention`` - atom-level co-attention between the two
    molecules. Belongs to Phase B, which tests whether attention weights
    correspond to known CYP450 pharmacophores.
  * the ordinal (cumulative-link) severity head;
  * the pharmacokinetic/pharmacodynamic mechanism head.

Do not reintroduce them here. Phase B branches from this file.

THE SYMMETRY CONSTRAINT
-----------------------
A drug interaction is symmetric: f(A, B) must equal f(B, A). Many published
models concatenate the two drug vectors, which permits an asymmetric function -
so the same pair receives two different scores depending on argument order. For
a clinical tool that is a defect, and it is demonstrable in ten seconds.

Every fusion term here uses ``*`` or ``|.|``, both commutative, so symmetry
holds exactly rather than approximately. ``test_prediction_is_symmetric``
asserts it.

Note this is a deliberate departure from the concatenation used in most
published work. Phase A quantifies the difference: ``eval.baselines`` supports
both encodings through its ``mode`` parameter, and the gap between them is
itself a result bearing on the project's main question.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.utils import to_dense_batch

from .adversarial import AdversaryOutput, DegreeAdversary, dann_lambda
from .encoders import DDIGraphEncoder, MolecularEncoder


@dataclass
class DDINetConfig:
    atom_dim: int
    bond_dim: int
    node_feature_dim: int
    n_relations: int = 7
    hidden_dim: int = 128
    mol_layers: int = 3
    graph_layers: int = 2
    heads: int = 4
    dropout: float = 0.2
    architecture: str = "gat"
    #: Molecular readout. Sum is the GIN-family standard and the Phase A-2
    #: default; see MolecularEncoder for why injectivity over multisets matters.
    pooling: str = "sum"
    #: Normalise the pooled molecular vector. See MolecularEncoder for why the
    #: default is True and what happens without it.
    pool_norm: bool = True
    #: Append the two drugs' TRAINING-graph degrees to the pair representation,
    #: as log1p(min) and log1p(max) - the same two numbers Phase A's degree-only
    #: baseline uses, and commutative like every other fusion term.
    #:
    #: This exists as a control, not as a proposed model. The network branch's
    #: embedding was measured to encode degree at R^2 0.885-0.954
    #: (scripts/23_degree_shortcut_probe.py), so the question is whether the
    #: whole contribution of that branch is reproducible by two scalars. If
    #: `gine` + these two numbers matches `dual`, the branch is a degree
    #: detector rather than an integrator of topology.
    use_degree_feature: bool = False
    use_molecular_branch: bool = True
    use_graph_branch: bool = True

    #: Adversarially suppress the training-graph degree in the network branch's
    #: embedding. This is the project's own architectural proposal, not a
    #: baseline - see models/adversarial.py for the full rationale and for the
    #: failure mode (encoder collapse) that must be reported alongside it.
    #:
    #: OFF BY DEFAULT AND CONSTRUCTED ONLY WHEN ON. The adversary's parameters
    #: are created inside `if config.adversarial_degree:` rather than
    #: unconditionally, because constructing an unused module would still draw
    #: from the ambient RNG and shift every other weight in the model. A run
    #: with this flag off must be bit-identical to one from before the flag
    #: existed - otherwise the Phase A-2 grid could not be resumed from its
    #: checkpoint without silently mixing two code versions.
    adversarial_degree: bool = False
    #: Asymptotic reversal strength. 0 disables the pressure while still
    #: building the head, which is the honest ablation control: same parameter
    #: count, same optimiser state, no adversarial gradient.
    adv_lambda_max: float = 1.0
    #: Steepness of the DANN ramp.
    adv_gamma: float = 10.0

    def ablation_name(self) -> str:
        parts = [self.architecture]
        if self.use_degree_feature:
            parts.append("degree")
        if not self.use_molecular_branch:
            parts.append("no-mol")
        if not self.use_graph_branch:
            parts.append("no-graph")
        if self.adversarial_degree:
            parts.append(f"adv{self.adv_lambda_max:g}")
        return "+".join(parts)


@dataclass
class DrugEncodings:
    """All drugs encoded once; pair scoring then just indexes into these."""

    pooled: torch.Tensor          # [N, H] molecule-level
    atoms: torch.Tensor           # [N, max_atoms, H] padded, kept for Phase B
    atom_mask: torch.Tensor       # [N, max_atoms] bool
    network: torch.Tensor         # [N, H] interaction-network level
    graph_attention: list = field(default_factory=list)


@dataclass
class PairPrediction:
    interaction_logit: torch.Tensor            # [P]

    def interaction_prob(self) -> torch.Tensor:
        return torch.sigmoid(self.interaction_logit)


class DDINet(nn.Module):
    """Standard dual-branch GNN for symmetric pair classification."""

    def __init__(self, config: DDINetConfig) -> None:
        super().__init__()
        self.config = config
        h = config.hidden_dim

        self.mol_encoder = MolecularEncoder(
            atom_dim=config.atom_dim,
            bond_dim=config.bond_dim,
            hidden_dim=h,
            n_layers=config.mol_layers,
            dropout=config.dropout,
            pooling=config.pooling,
            pool_norm=config.pool_norm,
        )
        self.graph_encoder = DDIGraphEncoder(
            in_dim=config.node_feature_dim,
            hidden_dim=h,
            n_layers=config.graph_layers,
            n_relations=config.n_relations,
            heads=config.heads,
            dropout=config.dropout,
            architecture=config.architecture,
        )

        # Fusion width tracks the active branches, so an ablated model does not
        # carry dead parameters fed with zeros - that would make the ablation
        # comparison unfair.
        fusion_dim = 0
        if config.use_molecular_branch:
            fusion_dim += 2 * h                       # g_A*g_B, |g_A-g_B|
        if config.use_graph_branch:
            fusion_dim += 2 * h                       # z_A*z_B, |z_A-z_B|
        if config.use_degree_feature:
            fusion_dim += 2                           # log1p(min d), log1p(max d)
        if fusion_dim == 0:
            raise ValueError("At least one branch must be enabled")
        self.fusion_dim = fusion_dim

        self.fusion = nn.Sequential(
            nn.Linear(fusion_dim, h),
            nn.LayerNorm(h),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(h, h // 2),
            nn.LayerNorm(h // 2),
            nn.ReLU(),
            nn.Dropout(config.dropout),
        )
        self.interaction_head = nn.Linear(h // 2, 1)

        # Degrees live on the model as a buffer so they move with .to(device)
        # and are saved with the state dict. They MUST be computed from
        # training pairs only - a degree counted over the full graph would leak
        # the evaluation edges this project exists to keep out.
        self.register_buffer("node_degree", torch.zeros(1), persistent=False)

        # Constructed ONLY when enabled - see DDINetConfig.adversarial_degree
        # for why an unconditional construction would change every other run.
        self.degree_adversary: DegreeAdversary | None = None
        if config.adversarial_degree:
            if not config.use_graph_branch:
                raise ValueError(
                    "adversarial_degree targets the network branch's embedding, "
                    "but use_graph_branch is False - there is nothing to debias"
                )
            self.degree_adversary = DegreeAdversary(h)

    def set_node_degree(self, degree: torch.Tensor) -> None:
        """Install per-drug TRAINING degrees, ordered like the graph's nodes.

        Required before a forward pass when ``use_degree_feature`` is on; the
        zero default would otherwise silently feed a constant, which looks like
        a working model and measures nothing.
        """
        if degree.dim() != 1:
            raise ValueError(f"degree must be 1-D, got shape {tuple(degree.shape)}")
        self.node_degree = degree.to(dtype=torch.float, device=self.node_degree.device)

    # -- encoding ----------------------------------------------------------
    def encode(
        self, mol_batch, node_features: torch.Tensor,
        edge_index: torch.Tensor, edge_type: torch.Tensor,
        *, return_attention: bool = False,
    ) -> DrugEncodings:
        """Encode every drug once per forward pass.

        Encoding all drugs together rather than per pair is both faster and
        more correct: a drug's network embedding depends on the whole graph, so
        it must be computed from the full adjacency, not a per-pair subgraph.
        """
        pooled, atom_h = self.mol_encoder(
            mol_batch.x, mol_batch.edge_index, mol_batch.edge_attr, mol_batch.batch
        )
        atoms, mask = to_dense_batch(atom_h, mol_batch.batch)

        if return_attention and self.config.architecture == "gat":
            network, attention = self.graph_encoder(
                node_features, edge_index, edge_type, return_attention=True
            )
        else:
            network = self.graph_encoder(node_features, edge_index, edge_type)
            attention = []

        return DrugEncodings(pooled, atoms, mask, network, attention)

    # -- pair scoring ------------------------------------------------------
    def score_pairs(
        self, enc: DrugEncodings, idx_a: torch.Tensor, idx_b: torch.Tensor
    ) -> PairPrediction:
        cfg = self.config
        parts: list[torch.Tensor] = []

        if cfg.use_molecular_branch:
            g_a, g_b = enc.pooled[idx_a], enc.pooled[idx_b]
            parts += [g_a * g_b, (g_a - g_b).abs()]          # both commutative

        if cfg.use_graph_branch:
            z_a, z_b = enc.network[idx_a], enc.network[idx_b]
            parts += [z_a * z_b, (z_a - z_b).abs()]          # both commutative

        if cfg.use_degree_feature:
            if self.node_degree.numel() <= 1:
                raise RuntimeError(
                    "use_degree_feature is on but node degrees were never set; "
                    "call set_node_degree() with training-graph degrees first."
                )
            d_a, d_b = self.node_degree[idx_a], self.node_degree[idx_b]
            lo = torch.log1p(torch.minimum(d_a, d_b)).unsqueeze(-1)
            hi = torch.log1p(torch.maximum(d_a, d_b)).unsqueeze(-1)
            parts += [lo, hi]                                # min/max: commutative

        fused = self.fusion(torch.cat(parts, dim=-1))
        return PairPrediction(self.interaction_head(fused).squeeze(-1))

    # -- adversarial debiasing --------------------------------------------
    def adversarial_loss(
        self,
        enc: DrugEncodings,
        node_idx: torch.Tensor,
        progress: float,
    ) -> AdversaryOutput:
        """Degree-adversary loss on the network embedding of ``node_idx``.

        :param node_idx: indices of TRAINING drugs only. Held-out drugs have a
            training-graph degree of zero by construction of the split, so
            including them would teach the adversary an artefact of the split
            rather than a property of the drug - and would make the debiasing
            look stronger than it is.
        :param progress: fraction of the step budget consumed, for the ramp.
            Training is full-batch, so this is steps taken over steps budgeted.

        The returned loss is ADDED to the interaction loss by the caller. The
        sign flip lives in the reversal layer, not here, so the total is a
        plain sum and the optimiser needs no special handling.
        """
        if self.degree_adversary is None:
            raise RuntimeError(
                "adversarial_loss() called but adversarial_degree is off; "
                "the adversary was never constructed"
            )
        if self.node_degree.numel() <= 1:
            raise RuntimeError(
                "adversarial debiasing needs training-graph degrees; "
                "call set_node_degree() first"
            )
        lambd = dann_lambda(
            progress, gamma=self.config.adv_gamma, max_lambda=self.config.adv_lambda_max
        )
        log_degree = torch.log1p(self.node_degree[node_idx])
        return self.degree_adversary(enc.network[node_idx], log_degree, lambd)

    def forward(
        self, mol_batch, node_features, edge_index, edge_type, idx_a, idx_b
    ) -> PairPrediction:
        enc = self.encode(mol_batch, node_features, edge_index, edge_type)
        return self.score_pairs(enc, idx_a, idx_b)

    def n_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


def compute_loss(
    pred: PairPrediction,
    labels: torch.Tensor,
    *,
    pos_weight: torch.Tensor | None = None,
) -> tuple[torch.Tensor, dict[str, float]]:
    """Binary cross-entropy with optional positive-class weighting.

    ``pos_weight`` rescales the positive class. With a 1:10 negative ratio an
    unweighted model reaches 91% accuracy by predicting "no interaction" for
    everything - a useless model with an impressive number. Weighting makes a
    missed interaction cost proportionally more, which also matches the clinical
    asymmetry: a missed dangerous interaction is worse than a false alarm.
    """
    loss = F.binary_cross_entropy_with_logits(
        pred.interaction_logit, labels.float(), pos_weight=pos_weight
    )
    return loss, {"interaction": float(loss.detach()), "total": float(loss.detach())}
