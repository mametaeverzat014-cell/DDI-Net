"""
DDI-Net: the full dual-level model with a symmetric co-attention decoder.

ARCHITECTURE
------------
    SMILES A --> MolecularEncoder --> atom embeddings H_A, pooled g_A
    SMILES B --> MolecularEncoder --> atom embeddings H_B, pooled g_B
    DDI graph --> DDIGraphEncoder --> network embeddings z_A, z_B

    H_A, H_B --> SubstructureCoAttention --> u, v  and the attention map S

    fuse([g_A*g_B, |g_A-g_B|, z_A*z_B, |z_A-z_B|, u+v, u*v]) --> MLP
        |--> interaction logit          (does this pair interact?)
        |--> ordinal severity logits    (minor / moderate / major)
        `--> mechanism logits           (pharmacokinetic vs pharmacodynamic)

THE SYMMETRY CONSTRAINT - AND WHY WE ENFORCE IT ARCHITECTURALLY
---------------------------------------------------------------
A drug interaction is symmetric: f(A, B) must equal f(B, A). Most published DDI
models concatenate the two drug vectors, which lets the network learn an
asymmetric function. In practice that means the same pair receives two different
risk scores depending on which drug you typed first. For a clinical decision
tool that is not a rounding error, it is a defect - and it is one a judge can
demonstrate live at your poster in ten seconds.

Two common fixes are unsatisfying: averaging f(A,B) and f(B,A) at inference
doubles the compute and still trains on an inconsistent objective, while random
order-swapping during training only *encourages* symmetry without guaranteeing
it.

We make it exact instead:

  * All drug-level fusion terms use ``*`` and ``|.|``, both commutative.
  * The co-attention bilinear form is parameterised as ``W = M + M^T``, which is
    symmetric **by construction** for any M. Then S(B,A) = S(A,B)^T exactly, the
    two attention directions swap, and the pooled terms ``u+v`` and ``u*v`` are
    invariant.

The result holds to floating-point precision at initialisation, after any amount
of training, and for every input - there is no way to train it away.
``test_prediction_is_symmetric`` asserts it.

WHY CO-ATTENTION RATHER THAN JUST CONCATENATING TWO MOLECULE VECTORS
--------------------------------------------------------------------
An interaction is not a property of two molecules considered separately; it is a
property of how a *part* of one relates to a *part* of the other. Ketoconazole's
imidazole coordinates CYP3A4's haem iron, which blocks the site where
simvastatin's ester would have been hydrolysed. That is a statement about two
specific substructures.

Co-attention represents exactly this: it computes a compatibility score between
every atom of A and every atom of B, so the model can learn "this fragment
matters *when paired with* that fragment". Two independently pooled vectors
cannot express a pairwise substructure relationship at all.

It also hands Step 5 its central object for free: the attention matrix S is a
map over atom pairs, so "which part of drug A interacted with which part of drug
B" is read directly off the model rather than reconstructed post hoc by a
separate explainer. An explanation the model actually computed is worth more
than one inferred afterwards.

ORDINAL SEVERITY, NOT PLAIN MULTI-CLASS
----------------------------------------
Severity is ordered: minor < moderate < major. Standard cross-entropy treats the
three as unrelated labels, so predicting "minor" for a major interaction is
penalised exactly as much as predicting "moderate" - which is wrong, because one
of those errors is far more dangerous.

We use a cumulative-link (CORAL-style) formulation: two sigmoid outputs
predicting P(severity >= moderate) and P(severity >= major). This encodes the
ordering in the loss, and it makes the head monotone by construction, so the
model cannot output the incoherent "probably major but probably not moderate".
"""

from __future__ import annotations

from dataclasses import dataclass, field

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.utils import to_dense_batch

from .encoders import DDIGraphEncoder, EncoderConfig, MolecularEncoder


# --------------------------------------------------------------------------
# Co-attention
# --------------------------------------------------------------------------

class SubstructureCoAttention(nn.Module):
    """Symmetric bilinear co-attention between two molecules' atom sets.

    The bilinear form is ``W = M + M^T``. Symmetry of W is what makes the whole
    model order-invariant, so it is enforced in the parameterisation rather than
    added as a regulariser or a post-hoc average.
    """

    def __init__(self, dim: int, temperature: float = 1.0) -> None:
        super().__init__()
        self.dim = dim
        self.temperature = temperature
        # Scaled init: a raw N(0,1) bilinear form produces enormous logits and
        # a saturated softmax that yields no gradient in the first epochs.
        self.M = nn.Parameter(torch.randn(dim, dim) / (dim ** 0.5))

    @property
    def W(self) -> torch.Tensor:
        return self.M + self.M.t()

    def forward(
        self,
        h_a: torch.Tensor, mask_a: torch.Tensor,
        h_b: torch.Tensor, mask_b: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Parameters
        ----------
        h_a, h_b: ``[B, n_atoms, D]`` padded atom embeddings.
        mask_a, mask_b: ``[B, n_atoms]`` boolean, True for real atoms.

        Returns ``(u, v, S)`` where ``u``/``v`` are ``[B, D]`` interaction-aware
        summaries of A and B, and ``S`` is the ``[B, n_a, n_b]`` atom-pair
        compatibility map used for explanation.
        """
        scores = torch.einsum("bid,de,bje->bij", h_a, self.W, h_b)
        scores = scores / (self.temperature * (self.dim ** 0.5))

        # Padding must not receive attention mass. -inf before softmax is the
        # only correct way; zeroing afterwards would leave the distribution
        # unnormalised.
        pad = torch.finfo(scores.dtype).min
        valid = mask_a.unsqueeze(2) & mask_b.unsqueeze(1)
        scores_masked = scores.masked_fill(~valid, pad)

        alpha = torch.softmax(scores_masked, dim=-1)   # A attends over B
        beta = torch.softmax(scores_masked, dim=-2)    # B attends over A
        alpha = alpha * valid
        beta = beta * valid

        context_a = torch.bmm(alpha, h_b)                      # [B, n_a, D]
        context_b = torch.bmm(beta.transpose(1, 2), h_a)       # [B, n_b, D]

        u = _masked_mean(context_a * h_a, mask_a)
        v = _masked_mean(context_b * h_b, mask_b)

        # Return the *masked, unnormalised* scores so Step 5 can rank atom pairs
        # without the softmax's row-wise normalisation obscuring magnitudes.
        return u, v, scores.masked_fill(~valid, 0.0)


def _masked_mean(x: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    """Mean over the atom axis, ignoring padding. Clamped to avoid 0/0."""
    m = mask.unsqueeze(-1).to(x.dtype)
    return (x * m).sum(dim=1) / m.sum(dim=1).clamp(min=1.0)


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

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
    use_coattention: bool = True
    predict_severity: bool = True
    predict_mechanism: bool = True
    n_mechanism_classes: int = 2       # pharmacokinetic vs pharmacodynamic

    def ablation_name(self) -> str:
        parts = [self.architecture]
        if not self.use_molecular_branch:
            parts.append("no-mol")
        if not self.use_graph_branch:
            parts.append("no-graph")
        if not self.use_coattention:
            parts.append("no-coattn")
        return "+".join(parts)


@dataclass
class DrugEncodings:
    """All drugs encoded once; pair scoring then just indexes into these."""

    pooled: torch.Tensor          # [N, H] molecule-level
    atoms: torch.Tensor           # [N, max_atoms, H] padded
    atom_mask: torch.Tensor       # [N, max_atoms] bool
    network: torch.Tensor         # [N, H] interaction-network level
    graph_attention: list = field(default_factory=list)


@dataclass
class PairPrediction:
    interaction_logit: torch.Tensor            # [P]
    severity_logits: torch.Tensor | None       # [P, 2] cumulative
    mechanism_logits: torch.Tensor | None      # [P, C]
    coattention: torch.Tensor | None           # [P, n_a, n_b]

    def interaction_prob(self) -> torch.Tensor:
        return torch.sigmoid(self.interaction_logit)

    def severity_prob(self) -> torch.Tensor | None:
        """``[P, 3]`` probabilities for (minor, moderate, major).

        Derived from the cumulative link outputs P(>=moderate), P(>=major).
        Clamped so numerical noise cannot produce a small negative probability.
        """
        if self.severity_logits is None:
            return None
        cum = torch.sigmoid(self.severity_logits)
        p_ge_mod, p_ge_maj = cum[:, 0], cum[:, 1]
        p_minor = (1 - p_ge_mod).clamp(min=0)
        p_moderate = (p_ge_mod - p_ge_maj).clamp(min=0)
        p_major = p_ge_maj.clamp(min=0)
        probs = torch.stack([p_minor, p_moderate, p_major], dim=1)
        return probs / probs.sum(dim=1, keepdim=True).clamp(min=1e-8)


# --------------------------------------------------------------------------
# The model
# --------------------------------------------------------------------------

class DDINet(nn.Module):
    """The complete model."""

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
        self.coattention = SubstructureCoAttention(h)

        # Fusion width depends on which branches are active, so ablations do not
        # silently feed zeros into a fixed-width layer (which would leave dead
        # parameters and make the comparison unfair).
        fusion_dim = 0
        if config.use_molecular_branch:
            fusion_dim += 2 * h                       # g_A*g_B, |g_A-g_B|
        if config.use_graph_branch:
            fusion_dim += 2 * h                       # z_A*z_B, |z_A-z_B|
        if config.use_coattention and config.use_molecular_branch:
            fusion_dim += 2 * h                       # u+v, u*v
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
        self.severity_head = nn.Linear(h // 2, 2) if config.predict_severity else None
        self.mechanism_head = (
            nn.Linear(h // 2, config.n_mechanism_classes)
            if config.predict_mechanism else None
        )

    # -- encoding ----------------------------------------------------------
    def encode(
        self, mol_batch, node_features: torch.Tensor,
        edge_index: torch.Tensor, edge_type: torch.Tensor,
        *, return_attention: bool = False,
    ) -> DrugEncodings:
        """Encode every drug once per forward pass.

        Encoding all drugs together rather than per pair is both faster and
        *more correct*: a drug's network embedding depends on the whole graph,
        so it must be computed from the full adjacency, not from a per-pair
        subgraph.
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
        self, enc: DrugEncodings, idx_a: torch.Tensor, idx_b: torch.Tensor,
        *, return_coattention: bool = False,
    ) -> PairPrediction:
        cfg = self.config
        parts: list[torch.Tensor] = []
        coattn = None

        if cfg.use_molecular_branch:
            g_a, g_b = enc.pooled[idx_a], enc.pooled[idx_b]
            parts += [g_a * g_b, (g_a - g_b).abs()]          # both commutative

            if cfg.use_coattention:
                u, v, scores = self.coattention(
                    enc.atoms[idx_a], enc.atom_mask[idx_a],
                    enc.atoms[idx_b], enc.atom_mask[idx_b],
                )
                parts += [u + v, u * v]                      # both commutative
                if return_coattention:
                    coattn = scores

        if cfg.use_graph_branch:
            z_a, z_b = enc.network[idx_a], enc.network[idx_b]
            parts += [z_a * z_b, (z_a - z_b).abs()]          # both commutative

        fused = self.fusion(torch.cat(parts, dim=-1))

        severity = self.severity_head(fused) if self.severity_head is not None else None
        if severity is not None:
            # Enforce monotonicity of the cumulative link: P(>=major) can never
            # exceed P(>=moderate). Parameterising the second threshold as the
            # first minus a non-negative offset makes an incoherent prediction
            # unrepresentable rather than merely unlikely.
            base = severity[:, 0]
            offset = F.softplus(severity[:, 1])
            severity = torch.stack([base, base - offset], dim=1)

        return PairPrediction(
            interaction_logit=self.interaction_head(fused).squeeze(-1),
            severity_logits=severity,
            mechanism_logits=(
                self.mechanism_head(fused) if self.mechanism_head is not None else None
            ),
            coattention=coattn,
        )

    def forward(
        self, mol_batch, node_features, edge_index, edge_type,
        idx_a, idx_b, *, return_coattention: bool = False,
    ) -> PairPrediction:
        enc = self.encode(mol_batch, node_features, edge_index, edge_type)
        return self.score_pairs(enc, idx_a, idx_b, return_coattention=return_coattention)

    def n_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


# --------------------------------------------------------------------------
# Losses
# --------------------------------------------------------------------------

def ordinal_severity_loss(
    logits: torch.Tensor, severity_rank: torch.Tensor, mask: torch.Tensor
) -> torch.Tensor:
    """Cumulative-link loss for ordered severity.

    ``severity_rank``: 0 = minor, 1 = moderate, 2 = major; ``mask`` selects the
    positive pairs (a negative pair has no severity, so including it would be
    meaningless supervision).

    Each of the two outputs is a binary problem - "is it at least moderate?",
    "is it at least major?" - and the ordering is encoded in the targets. This
    is what makes confusing minor with major cost more than confusing minor with
    moderate.
    """
    if mask.sum() == 0:
        return logits.sum() * 0.0            # keeps the graph connected
    sel_logits = logits[mask]
    sel_rank = severity_rank[mask]
    targets = torch.stack([(sel_rank >= 1).float(), (sel_rank >= 2).float()], dim=1)
    return F.binary_cross_entropy_with_logits(sel_logits, targets)


@dataclass
class LossWeights:
    interaction: float = 1.0
    severity: float = 0.5
    mechanism: float = 0.25


def compute_loss(
    pred: PairPrediction,
    labels: torch.Tensor,
    severity_rank: torch.Tensor,
    mechanism: torch.Tensor,
    *,
    pos_weight: torch.Tensor | None = None,
    weights: LossWeights | None = None,
) -> tuple[torch.Tensor, dict[str, float]]:
    """Multi-task loss. Returns ``(total, per_task_values)``.

    ``pos_weight`` rescales the positive class in the interaction loss. With a
    1:10 negative ratio, an unweighted model can reach 91% accuracy by
    predicting "no interaction" for everything - a useless model with an
    impressive-looking number. Weighting makes missing a real interaction cost
    proportionally more, which also matches the clinical asymmetry: a missed
    dangerous interaction is far worse than a false alarm.
    """
    w = weights or LossWeights()
    parts: dict[str, float] = {}

    interaction = F.binary_cross_entropy_with_logits(
        pred.interaction_logit, labels.float(), pos_weight=pos_weight
    )
    parts["interaction"] = float(interaction.detach())
    total = w.interaction * interaction

    positives = labels == 1
    if pred.severity_logits is not None and w.severity > 0:
        sev = ordinal_severity_loss(pred.severity_logits, severity_rank, positives)
        parts["severity"] = float(sev.detach())
        total = total + w.severity * sev

    if pred.mechanism_logits is not None and w.mechanism > 0:
        valid = positives & (mechanism >= 0)
        if valid.any():
            mech = F.cross_entropy(pred.mechanism_logits[valid], mechanism[valid])
        else:
            mech = pred.mechanism_logits.sum() * 0.0
        parts["mechanism"] = float(mech.detach())
        total = total + w.mechanism * mech

    parts["total"] = float(total.detach())
    return total, parts
