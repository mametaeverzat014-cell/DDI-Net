"""
The two encoders: one over atoms inside a molecule, one over drugs inside the
interaction network.

WHY TWO LEVELS
--------------
A drug-drug interaction is caused by chemistry (what the molecules are) and is
observed in a network (what else each drug is known to interact with). Those are
different graphs at different scales, and collapsing them into one loses
information:

  * The **molecular** graph explains *why* an interaction happens - this
    imidazole nitrogen coordinates the CYP3A4 haem iron.
  * The **interaction** graph explains *what else is like this* - this drug sits
    in a neighbourhood of CYP3A4 inhibitors.

Critically, the two degrade differently. In the S3 setting a test drug has NO
edges in the interaction network, so the network encoder contributes almost
nothing and the molecular encoder must carry the prediction alone. Keeping them
as separate branches lets Step 4 ablate them and *show* that, rather than
asserting it.

WHICH ARCHITECTURE FOR WHICH LEVEL - AND WHY
--------------------------------------------
**Molecular level: GINE.**
Graph Isomorphism Networks (Xu et al. 2019) are provably as powerful as the
1-Weisfeiler-Lehman test, which is the theoretical maximum for a message-passing
GNN that does not use extra structural features. For molecules this matters:
distinguishing ortho- from para-substitution is a WL-hard problem and is exactly
the kind of distinction that changes metabolism. GINE is the edge-feature
variant, so bond order and aromaticity participate. GCN's symmetric
normalisation actively *discards* degree information, and atom degree is
chemically meaningful (a quaternary carbon is not a methyl).

**Interaction-network level: GAT (default), with SAGE and GCN available.**
Three reasons GAT wins here:

  1. *Interpretability.* Attention coefficients say which neighbouring drugs
     influenced this drug's representation. That is a directly reportable
     explanation, and interpretability is the project's stated goal.
  2. *Heterogeneous neighbourhoods.* Our graph has seven relation types.
     A CYP3A4-inhibitor edge should not be weighted like a same-ATC-class edge.
     GCN would average them uniformly. We feed the relation type in as an edge
     feature so attention can learn per-relation weighting.
  3. *Inductive by construction.* Attention is computed from node features, so a
     drug never seen in training still gets a sensible representation - which is
     the entire S2/S3 requirement.

GraphSAGE is the honest competitor: it was designed for inductive settings and
its sampling-based aggregation is more robust on high-degree nodes. We implement
all three behind one interface and let Step 4 decide empirically, because
"which architecture is best" is a question to answer with an experiment, not an
opinion.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import (
    GATv2Conv,
    GCNConv,
    GINEConv,
    SAGEConv,
)
from torch_geometric.nn import global_add_pool, global_mean_pool
from torch_geometric.nn.aggr import AttentionalAggregation
from torch_geometric.utils import to_dense_batch


# --------------------------------------------------------------------------
# Molecular encoder
# --------------------------------------------------------------------------

class MolecularEncoder(nn.Module):
    """Encode a molecule from its atom graph.

    Returns **both** a pooled molecule vector and the per-atom embeddings.
    The per-atom embeddings are not an implementation detail - they are what the
    co-attention decoder consumes and what Step 5 paints onto the structure. An
    encoder that returned only the pooled vector would make the project's
    interpretability claim impossible.

    POOLING: SUM BY DEFAULT
    -----------------------
    Sum pooling is the standard readout for GIN-family encoders and is what the
    original paper uses, for a specific reason: it is the only one of the three
    common readouts that is *injective* over multisets of node features. Mean and
    max both discard multiplicity - a molecule with two carboxyl groups and one
    with three pool to the same mean - so they throw away exactly the size and
    composition information that distinguishes a small fragment from a large one.

    The cost is that sum scales with molecule size, so a 60-atom drug produces a
    larger-norm embedding than a 15-atom one. The LayerNorm in the fusion head
    absorbs that.

    ``pooling="attention"`` is retained because it emits a scalar weight per
    atom, which is a per-molecule saliency map for free. It is not the Phase A-2
    default: the protocol calls for a standard architecture with no invented
    components, and attention pooling is the thin end of the interpretability
    work that belongs to Phase B.
    """

    def __init__(
        self,
        atom_dim: int,
        bond_dim: int,
        hidden_dim: int = 128,
        n_layers: int = 3,
        dropout: float = 0.2,
        pooling: str = "sum",
        pool_norm: bool = True,
    ) -> None:
        super().__init__()
        self.hidden_dim = hidden_dim
        self.n_layers = n_layers

        self.atom_embed = nn.Linear(atom_dim, hidden_dim)
        # GINEConv requires edge features to match node dimensionality.
        self.bond_embed = nn.Linear(bond_dim, hidden_dim)

        self.convs = nn.ModuleList()
        self.norms = nn.ModuleList()
        for _ in range(n_layers):
            mlp = nn.Sequential(
                nn.Linear(hidden_dim, 2 * hidden_dim),
                nn.ReLU(),
                nn.Linear(2 * hidden_dim, hidden_dim),
            )
            self.convs.append(GINEConv(mlp, train_eps=True))
            # LayerNorm, not BatchNorm: batches of molecules vary wildly in size
            # and composition, so batch statistics are noisy and make evaluation
            # depend on how molecules happen to be grouped.
            self.norms.append(nn.LayerNorm(hidden_dim))

        self.dropout = nn.Dropout(dropout)
        self.pooling = pooling

        # Normalise the pooled vector before it leaves the encoder.
        #
        # Sum pooling makes the embedding's MAGNITUDE a near-perfect proxy for
        # molecule size - measured correlation with atom count is 0.9999, and
        # norms span 12.7 to 5800 across DrugBank. The pair decoder multiplies
        # two of these elementwise, so the fusion MLP saw inputs spanning five
        # orders of magnitude that encoded size rather than chemistry, and
        # gradients were dominated by a handful of large-molecule pairs. The
        # first Phase A-2 grid trained under exactly that and could not fit its
        # own training data (docs/PHASE_A2_PROTOCOL.md, Addenda 9-10).
        #
        # On by default because the failure it prevents is silent: the run
        # completes, the curves look smooth, and the numbers are meaningless.
        self.pool_norm = nn.LayerNorm(hidden_dim) if pool_norm else nn.Identity()
        if pooling == "attention":
            self.pool = AttentionalAggregation(
                gate_nn=nn.Sequential(
                    nn.Linear(hidden_dim, hidden_dim // 2),
                    nn.ReLU(),
                    nn.Linear(hidden_dim // 2, 1),
                )
            )
        elif pooling in ("sum", "mean"):
            self.pool = None
        else:
            raise ValueError(f"Unknown pooling {pooling!r}")

    def forward(
        self, x: torch.Tensor, edge_index: torch.Tensor,
        edge_attr: torch.Tensor, batch: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Returns ``(pooled [B, H], atom_embeddings [n_atoms, H])``."""
        h = self.atom_embed(x)
        e = self.bond_embed(edge_attr)

        for conv, norm in zip(self.convs, self.norms):
            h_new = conv(h, edge_index, e)
            h_new = norm(h_new)
            h_new = F.relu(h_new)
            h_new = self.dropout(h_new)
            # Residual connection: keeps early-layer (local, atom-identity)
            # information reachable at the output. Without it, deeper stacks
            # over-smooth and every atom in a molecule converges to the same
            # vector - which destroys per-atom attribution.
            h = h + h_new

        if self.pooling == "sum":
            pooled = global_add_pool(h, batch)
        elif self.pooling == "mean":
            pooled = global_mean_pool(h, batch)
        else:
            pooled = self.pool(h, batch)
        return self.pool_norm(pooled), h

    def atom_importance(
        self, atom_embeddings: torch.Tensor, batch: torch.Tensor
    ) -> torch.Tensor:
        """Per-atom pooling-gate weights, softmax-normalised within a molecule.

        Only meaningful with ``pooling="attention"``; sum pooling has no gate to
        read, so this raises rather than returning a uniform vector that would
        look like a saliency map while carrying no information.
        """
        if self.pooling != "attention":
            raise ValueError(
                f"atom_importance requires pooling='attention', not {self.pooling!r}. "
                f"Sum pooling has no per-atom gate; a uniform vector would be "
                f"mistaken for a saliency map."
            )
        logits = self.pool.gate_nn(atom_embeddings).squeeze(-1)
        dense, mask = to_dense_batch(logits.unsqueeze(-1), batch, fill_value=-1e9)
        weights = torch.softmax(dense.squeeze(-1), dim=1)
        return weights * mask


# --------------------------------------------------------------------------
# Interaction-network encoder
# --------------------------------------------------------------------------

class DDIGraphEncoder(nn.Module):
    """Encode a drug from its position in the interaction network.

    ``architecture`` selects GAT / SAGE / GCN so Step 4 can compare them under
    identical conditions. Only GAT consumes the relation type, because only GAT
    has a mechanism for weighting neighbours differently - which is precisely
    the argument for preferring it on a multi-relational graph.
    """

    def __init__(
        self,
        in_dim: int,
        hidden_dim: int = 128,
        n_layers: int = 2,
        n_relations: int = 7,
        heads: int = 4,
        dropout: float = 0.2,
        architecture: str = "gat",
    ) -> None:
        super().__init__()
        if architecture not in ("gat", "sage", "gcn"):
            raise ValueError(f"Unknown architecture: {architecture!r}")
        self.architecture = architecture
        self.hidden_dim = hidden_dim
        self.n_layers = n_layers

        self.input_proj = nn.Sequential(
            nn.Linear(in_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
        )
        # Relation embeddings let attention learn that a CYP-inhibitor edge
        # carries more information than a same-ATC-class edge.
        self.relation_embed = nn.Embedding(n_relations, hidden_dim // 2)

        self.convs = nn.ModuleList()
        self.norms = nn.ModuleList()
        for _ in range(n_layers):
            if architecture == "gat":
                # GATv2 rather than GAT: the original's attention is "static"
                # (the ranking of neighbours is the same for every query node),
                # which GATv2 fixes. Free improvement, same interface.
                conv = GATv2Conv(
                    hidden_dim, hidden_dim // heads, heads=heads,
                    edge_dim=hidden_dim // 2, dropout=dropout, add_self_loops=True,
                )
            elif architecture == "sage":
                conv = SAGEConv(hidden_dim, hidden_dim)
            else:
                conv = GCNConv(hidden_dim, hidden_dim, add_self_loops=True)
            self.convs.append(conv)
            self.norms.append(nn.LayerNorm(hidden_dim))

        self.dropout = nn.Dropout(dropout)

    def forward(
        self,
        x: torch.Tensor,
        edge_index: torch.Tensor,
        edge_type: torch.Tensor,
        *,
        return_attention: bool = False,
    ):
        """Returns node embeddings ``[N, H]`` (and attention if requested)."""
        h = self.input_proj(x)
        attentions: list[tuple[torch.Tensor, torch.Tensor]] = []
        edge_feat = self.relation_embed(edge_type) if edge_index.numel() else None

        for conv, norm in zip(self.convs, self.norms):
            if self.architecture == "gat":
                if return_attention:
                    h_new, (att_idx, att_w) = conv(
                        h, edge_index, edge_attr=edge_feat,
                        return_attention_weights=True,
                    )
                    attentions.append((att_idx.detach(), att_w.detach()))
                else:
                    h_new = conv(h, edge_index, edge_attr=edge_feat)
            else:
                h_new = conv(h, edge_index)
            h_new = norm(h_new)
            h_new = F.relu(h_new)
            h_new = self.dropout(h_new)
            h = h + h_new                       # residual, as in the mol encoder

        return (h, attentions) if return_attention else h


@dataclass
class EncoderConfig:
    """Hyperparameters, kept in one place so runs are reproducible."""

    hidden_dim: int = 128
    mol_layers: int = 3
    graph_layers: int = 2
    heads: int = 4
    dropout: float = 0.2
    architecture: str = "gat"
