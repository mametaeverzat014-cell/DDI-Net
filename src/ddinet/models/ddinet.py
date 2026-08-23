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
    use_molecular_branch: bool = True
    use_graph_branch: bool = True

    def ablation_name(self) -> str:
        parts = [self.architecture]
        if not self.use_molecular_branch:
            parts.append("no-mol")
        if not self.use_graph_branch:
            parts.append("no-graph")
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

        fused = self.fusion(torch.cat(parts, dim=-1))
        return PairPrediction(self.interaction_head(fused).squeeze(-1))

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
