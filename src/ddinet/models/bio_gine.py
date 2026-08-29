"""
BIO-GINE: the V2 model. Molecular GINE + a DeepSets encoder over biology.

WHY THIS REPLACES THE DDI-NETWORK BRANCH
-----------------------------------------
Phase A-2 measured the dual model's DDI-network branch and found it to be a
liability on every honest split: dual - gine was +0.1026 and +0.0875 AUPRC on
the two leaky cells and -0.0331, -0.0234, -0.0169 on three drug- and
scaffold-disjoint cells. The probe (scripts/23) showed the branch's embedding
predicts training-graph degree at R^2 0.885-0.954, and the adversarial
suppression experiment failed to remove it (probe R^2 0.602 and 0.359 against a
preregistered 0.30 threshold). The branch encodes how well-studied a drug is.

That is structurally unfixable for an unseen drug: in the S3 setting a test drug
has zero DDI adjacency, so there is nothing for a network encoder to aggregate.
V2's premise is that biology - the proteins a drug is annotated against and the
pathways they sit in - is context that survives the split, because it comes from
the drug's own annotation rather than from its position in the label graph.

The premise is not assumed. It was measured before this model was written:
shared targets separate degree-matched positives from negatives at AUC 0.5613,
while Spearman(shared targets, min-degree) = +0.112 against
Spearman(min-degree, label) = +0.215. Biology carries signal that is not simply
degree in another coordinate system. Whether a *model* can use it is what
H-V2-1 through H-V2-4 test, and the honest possible answer is no.

WHY DEEPSETS RATHER THAN A HETEROGENEOUS GNN
---------------------------------------------
The full argument is docs/V2_ARCHITECTURE_PLAN.md section 3. The short version
is that a hetero-GNN over 10,357 nodes has to learn graph structure from 1,705
labelled drugs, and its standard SUM aggregation is neighbour counting - the
same degree shortcut this project spent Phase A-2 documenting, re-entered
through a new door. DeepSets with MEAN aggregation makes the shortcut an
explicit, testable choice rather than an architectural default: CONTROL C trains
the identical model with SUM, and if SUM wins, counting was the signal.

MEAN IS A DESIGN COMMITMENT, NOT A DEFAULT
-------------------------------------------
MEAN normalises by |P(d)|, so the representation of a drug with 4 targets and
one with 400 differ in content, not in magnitude. The count is not thereby
erased - it re-enters through which proteins are common enough to be annotated
often - but it is no longer the path of least resistance. Three controls sit
around this choice: CONTROL A (can eight scalar counts match the model?),
CONTROL C (does SUM beat MEAN?), CONTROL E (does the learned embedding still
linearly predict DDI degree?).

SYMMETRY
--------
f(A, B) = f(B, A) exactly, as in Phase A-2's model: every pair term is
commutative (sum, absolute difference, elementwise product) and the two mask
bits are combined as min/max rather than concatenated in argument order. A
concatenated [mask_A | mask_B] would break symmetry for exactly the pairs where
one drug has biology and the other does not - which is 3.9% of drugs and
disproportionately the interesting ones.

WHAT THIS FILE DOES NOT DO
--------------------------
It does not train, evaluate, select hyperparameters, or read a split. It defines
parameters and a forward pass. The preregistered protocol requires the grid to
run on drug-disjoint VALIDATION AUPRC only, with test touched exactly once at
the end (docs/V2_PREREGISTRATION.md section 10), and keeping the model free of
data-loading logic is what keeps that enforceable elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch
import torch.nn as nn

from ..data.biology import EVIDENCE_TYPES, RELATION_TYPES, BiologyBundle
from .encoders import MolecularEncoder


@dataclass
class BioGineConfig:
    """Every architectural number in one place; the grid varies a subset.

    The preregistered grid (configs/v2_preregistered.yaml, preregistration
    section 10.2) moves ``bio_dim``, ``dropout_bio``, ``dropout_pair``, and the
    optimiser's lr/batch size. Everything else is frozen at the Phase A-2 value
    so that a V2-minus-GINE difference is attributable to the biological branch.
    """

    # -- vocabulary sizes: come from the BiologyBundle, not from a guess ----
    n_protein_vocab: int
    n_pathway_vocab: int

    # -- molecular branch: frozen at the Phase A-2 GINE configuration -------
    #
    # DEVIATION FROM THE PLAN TEXT, STATED HERE BECAUSE IT IS LOAD-BEARING.
    # docs/V2_ARCHITECTURE_PLAN.md section 4.2 says "GINE (4-layer, d=128, same
    # as Phase A-2)". Those two numbers contradict the phrase they qualify:
    # scripts/15_phase_a2_gnn.py froze hidden_dim=64 and mol_layers=3, and the
    # tuned dropout for the `gine` cell was 0.1 (reports/phase_a2_hyperparameters
    # .json). The intent - "same as Phase A-2" - is what matters, because M0 in
    # the evidence ladder IS the frozen Phase A-2 GINE result, reused rather
    # than retrained. Following the literal 4/128 would change the molecular
    # branch at the same time as adding the biological one, and every M-minus-M0
    # difference would then confound the two. So these defaults follow the
    # measured Phase A-2 configuration. See docs/V2_IMPLEMENTATION_NOTES.md.
    atom_dim: int = 0
    bond_dim: int = 0
    mol_dim: int = 64
    mol_layers: int = 3
    mol_pooling: str = "sum"
    mol_pool_norm: bool = True
    dropout_mol: float = 0.1

    # -- biological branch --------------------------------------------------
    bio_dim: int = 64
    rel_dim: int = 16
    ev_dim: int = 16
    dropout_bio: float = 0.1
    #: MEAN or SUM. SUM is CONTROL C and exists to be *lost*: if it wins, the
    #: biological branch is a counter. Not a tuning knob - it is never selected
    #: on validation, it is reported as a control.
    aggregation: str = "mean"

    # -- fusion and decoder -------------------------------------------------
    hidden_dim: int = 128
    dropout_pair: float = 0.1

    # -- branch switches: the ablation ladder -------------------------------
    use_molecular_branch: bool = True
    use_protein_level: bool = True
    use_pathway_level: bool = True

    def __post_init__(self) -> None:
        if self.aggregation not in {"mean", "sum"}:
            raise ValueError(f"aggregation must be 'mean' or 'sum', got {self.aggregation!r}")
        if not (self.use_molecular_branch or self.use_protein_level or self.use_pathway_level):
            raise ValueError("At least one branch must be enabled")

    def ablation_name(self) -> str:
        parts = ["bio-gine"]
        if not self.use_molecular_branch:
            parts.append("no-mol")
        if not self.use_protein_level:
            parts.append("no-prot")
        if not self.use_pathway_level:
            parts.append("no-path")
        if self.aggregation != "mean":
            parts.append(self.aggregation)
        return "+".join(parts)


class BiologicalSets:
    """Drug biology flattened into the ragged layout ``scatter`` wants.

    A DeepSets aggregation over per-drug sets of different sizes is a segmented
    reduction: concatenate every drug's elements into one long tensor, carry an
    index saying which drug each element belongs to, and reduce by that index.
    That is one embedding lookup and one scatter for the whole batch, rather
    than 1,705 small ones.

    Built ONCE per run from a :class:`BiologyBundle` and then held constant:
    biology does not change during training. It is registered on the model as
    buffers so it moves with ``.to(device)`` - a CPU index tensor against a CUDA
    embedding table is a silent-wrong-device error at best.

    ``empty_*`` marks drugs whose set is empty. Those rows get a learned MISSING
    token rather than a zero vector, because zero is a point in embedding space
    that some real drug could occupy, and "no annotation" must not be
    representable as "annotated with nothing in particular".
    """

    def __init__(self, bundle: BiologyBundle) -> None:
        self.n_drugs = bundle.n_drugs
        self.n_protein_vocab = bundle.n_proteins
        self.n_pathway_vocab = bundle.n_pathways

        prot_rows, prot_owner = [], []
        for i, items in enumerate(bundle.protein_items):
            if len(items):
                prot_rows.append(items)
                prot_owner.append(np.full(len(items), i, dtype=np.int64))
        stacked = (
            np.concatenate(prot_rows, axis=0) if prot_rows
            else np.zeros((0, 3), dtype=np.int64)
        )
        self.protein_id = torch.as_tensor(stacked[:, 0], dtype=torch.long)
        self.protein_rel = torch.as_tensor(stacked[:, 1], dtype=torch.long)
        self.protein_ev = torch.as_tensor(stacked[:, 2], dtype=torch.long)
        self.protein_owner = torch.as_tensor(
            np.concatenate(prot_owner) if prot_owner else np.zeros(0, dtype=np.int64),
            dtype=torch.long,
        )

        path_rows, path_owner = [], []
        for i, items in enumerate(bundle.pathway_items):
            if len(items):
                path_rows.append(items)
                path_owner.append(np.full(len(items), i, dtype=np.int64))
        self.pathway_id = torch.as_tensor(
            np.concatenate(path_rows) if path_rows else np.zeros(0, dtype=np.int64),
            dtype=torch.long,
        )
        self.pathway_owner = torch.as_tensor(
            np.concatenate(path_owner) if path_owner else np.zeros(0, dtype=np.int64),
            dtype=torch.long,
        )

        self.protein_size = torch.as_tensor(
            [len(x) for x in bundle.protein_items], dtype=torch.float
        )
        self.pathway_size = torch.as_tensor(
            [len(x) for x in bundle.pathway_items], dtype=torch.float
        )
        self.empty_protein = self.protein_size == 0
        self.empty_pathway = self.pathway_size == 0

        # CSR-style offsets. The elements are already grouped by owner in drug
        # order, so drug i owns rows [offset[i], offset[i+1]). This is what makes
        # a minibatch affordable: the preregistered grid trains on 256- or
        # 512-pair batches, and encoding all 1,705 drugs on every one of ~700
        # steps per epoch would cost ~700x what Phase A-2 paid per epoch.
        # With offsets, the elements of a 512-drug subset are gathered with
        # arithmetic instead of a Python loop.
        self.protein_offsets = torch.cat([
            torch.zeros(1, dtype=torch.long),
            torch.cumsum(self.protein_size.long(), 0),
        ])
        self.pathway_offsets = torch.cat([
            torch.zeros(1, dtype=torch.long),
            torch.cumsum(self.pathway_size.long(), 0),
        ])

    def tensors(self) -> dict[str, torch.Tensor]:
        return {
            "protein_id": self.protein_id,
            "protein_rel": self.protein_rel,
            "protein_ev": self.protein_ev,
            "protein_owner": self.protein_owner,
            "pathway_id": self.pathway_id,
            "pathway_owner": self.pathway_owner,
            "protein_size": self.protein_size,
            "pathway_size": self.pathway_size,
            "empty_protein": self.empty_protein,
            "empty_pathway": self.empty_pathway,
            "protein_offsets": self.protein_offsets,
            "pathway_offsets": self.pathway_offsets,
        }


def _segment_reduce(
    values: torch.Tensor,
    owner: torch.Tensor,
    n_segments: int,
    *,
    aggregation: str,
    sizes: torch.Tensor,
) -> torch.Tensor:
    """Sum or mean ``values`` grouped by ``owner``, over ``n_segments`` groups.

    ``index_add_`` rather than ``torch_scatter``: it is in core PyTorch, so the
    environment stays reproducible from ``requirements.lock.txt`` without an
    extra compiled dependency pinned to a CUDA version.

    Empty segments come back as zero. That is deliberate and harmless here -
    the caller overwrites every empty row with the MISSING token before the
    value is used, and dividing by a clamped size keeps the zero finite rather
    than NaN. A NaN would propagate into the loss and be discovered as a failed
    run rather than as a handled case.
    """
    out = values.new_zeros((n_segments, values.shape[-1]))
    out.index_add_(0, owner, values)
    if aggregation == "mean":
        out = out / sizes.clamp(min=1.0).unsqueeze(-1)
    return out


def _gather_subset(
    offsets: torch.Tensor, node_idx: torch.Tensor
) -> tuple[torch.Tensor, torch.Tensor]:
    """Element positions and local owner ids for a subset of drugs.

    ``offsets`` is CSR: drug *i* owns element rows ``[offsets[i], offsets[i+1])``.
    Given ``node_idx``, return (a) the flat element positions belonging to those
    drugs, in ``node_idx`` order, and (b) for each of those elements, the
    POSITION of its owner within ``node_idx`` - not the global drug index, so
    the segmented reduction produces one row per selected drug.

    Vectorised because it runs on every training step. The trick is standard:
    build the destination offsets by cumulative sum of the selected sizes, then
    reconstruct each element's source index as
    ``start_of_its_drug + (its position within the drug)``.
    """
    sizes = offsets[node_idx + 1] - offsets[node_idx]
    total = int(sizes.sum())
    if total == 0:
        empty = torch.zeros(0, dtype=torch.long, device=offsets.device)
        return empty, empty
    owner = torch.repeat_interleave(
        torch.arange(len(node_idx), device=offsets.device), sizes
    )
    # Offset of each selected drug's block within the OUTPUT, so that
    # (running position) - (block start) is the position within the drug.
    out_starts = torch.cat([
        torch.zeros(1, dtype=torch.long, device=offsets.device),
        torch.cumsum(sizes, 0)[:-1],
    ])
    within = torch.arange(total, device=offsets.device) - out_starts[owner]
    positions = offsets[node_idx][owner] + within
    return positions, owner


class DeepSetsEncoder(nn.Module):
    """phi -> aggregate -> rho over a per-drug set, with a learned MISSING token.

    Follows docs/V2_ARCHITECTURE_PLAN.md section 4.3. ``phi`` runs per element,
    the aggregation is permutation-invariant, ``rho`` runs per drug. Dropout
    sits in ``rho`` only: dropping features of individual set elements before a
    mean is a second, uncontrolled source of set-size dependence (the variance
    of the mean of dropped-out elements scales with 1/|P(d)|), which would
    smuggle degree back in as noise.
    """

    def __init__(
        self,
        element_dim: int,
        hidden_dim: int,
        out_dim: int,
        *,
        dropout: float,
        aggregation: str,
    ) -> None:
        super().__init__()
        self.aggregation = aggregation
        self.phi = nn.Sequential(
            nn.Linear(element_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, out_dim),
            nn.ReLU(),
        )
        self.rho = nn.Sequential(
            nn.Linear(out_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, out_dim),
        )
        # One learned vector standing for "no annotation of this kind". A
        # parameter rather than a constant, so the model can place it wherever
        # in the space is least confusable with a real drug.
        self.missing = nn.Parameter(torch.zeros(out_dim))
        nn.init.normal_(self.missing, std=0.02)

    def forward(
        self,
        elements: torch.Tensor,
        owner: torch.Tensor,
        n_drugs: int,
        sizes: torch.Tensor,
        empty: torch.Tensor,
    ) -> torch.Tensor:
        if elements.numel() == 0:
            return self.missing.unsqueeze(0).expand(n_drugs, -1)
        pooled = _segment_reduce(
            self.phi(elements), owner, n_drugs,
            aggregation=self.aggregation, sizes=sizes,
        )
        out = self.rho(pooled)
        # torch.where, not indexed assignment: keeps the graph intact for
        # autograd and lets the MISSING token receive gradient from the drugs
        # that actually use it.
        return torch.where(empty.unsqueeze(-1), self.missing.unsqueeze(0), out)


@dataclass
class BioPairPrediction:
    interaction_logit: torch.Tensor

    def interaction_prob(self) -> torch.Tensor:
        return torch.sigmoid(self.interaction_logit)


class BioGine(nn.Module):
    """Molecular GINE + biological DeepSets, fused, with a symmetric decoder.

    Held-out drugs are encoded exactly like training drugs: their molecular
    graph and their biological annotation both exist without reference to the
    DDI label graph. There is no transductive step anywhere in the forward pass,
    which is the property the S3 setting requires and the property the Phase A-2
    network branch did not have.
    """

    def __init__(self, config: BioGineConfig) -> None:
        super().__init__()
        self.config = config
        h = config.hidden_dim

        self.mol_encoder = None
        if config.use_molecular_branch:
            if config.atom_dim <= 0 or config.bond_dim <= 0:
                raise ValueError(
                    "use_molecular_branch requires atom_dim and bond_dim from "
                    "the feature bundle; they have no sensible default"
                )
            self.mol_encoder = MolecularEncoder(
                atom_dim=config.atom_dim,
                bond_dim=config.bond_dim,
                hidden_dim=config.mol_dim,
                n_layers=config.mol_layers,
                dropout=config.dropout_mol,
                pooling=config.mol_pooling,
                pool_norm=config.mol_pool_norm,
            )

        b = config.bio_dim
        self.protein_embedding = None
        self.protein_encoder = None
        if config.use_protein_level:
            self.protein_embedding = nn.Embedding(config.n_protein_vocab, b)
            self.relation_embedding = nn.Embedding(len(RELATION_TYPES), config.rel_dim)
            self.evidence_embedding = nn.Embedding(len(EVIDENCE_TYPES), config.ev_dim)
            self.protein_encoder = DeepSetsEncoder(
                element_dim=b + config.rel_dim + config.ev_dim,
                hidden_dim=2 * b,
                out_dim=b,
                dropout=config.dropout_bio,
                aggregation=config.aggregation,
            )

        self.pathway_embedding = None
        self.pathway_encoder = None
        if config.use_pathway_level:
            self.pathway_embedding = nn.Embedding(config.n_pathway_vocab, b)
            self.pathway_encoder = DeepSetsEncoder(
                element_dim=b,
                hidden_dim=2 * b,
                out_dim=b,
                dropout=config.dropout_bio,
                aggregation=config.aggregation,
            )

        # Fusion width tracks the active branches. An ablated model must not
        # carry dead parameters fed with zeros - that inflates its parameter
        # count and makes the ablation comparison dishonest.
        fuse_in = 0
        if config.use_molecular_branch:
            fuse_in += config.mol_dim
        if config.use_protein_level:
            fuse_in += b
        if config.use_pathway_level:
            fuse_in += b
        self.fusion_input_dim = fuse_in
        self.fusion = nn.Linear(fuse_in, h)
        self.fusion_norm = nn.LayerNorm(h)

        # 3h from the three commutative pair terms, +4 from the mask: two
        # modality bits reduced two ways, elementwise min ("both drugs have
        # this modality") and max ("at least one does"). Both are commutative,
        # unlike the [mask_A | mask_B] concatenation of the plan text, which
        # would break f(A,B) = f(B,A) for exactly the pairs where one drug has
        # biology and the other does not. Same width, symmetry preserved.
        self.pair_input_dim = 3 * h + 4
        self.pair_mlp = nn.Sequential(
            nn.Linear(self.pair_input_dim, 2 * h),
            nn.ReLU(),
            nn.Dropout(config.dropout_pair),
            nn.Linear(2 * h, h),
            nn.ReLU(),
            nn.Dropout(config.dropout_pair),
            nn.Linear(h, 1),
        )

        # Biology, installed once via set_biology(). Buffers so they follow the
        # model onto the device and are not mistaken for trainable parameters.
        self._biology_installed = False
        for name, tensor in _EMPTY_BIOLOGY.items():
            self.register_buffer(name, tensor.clone(), persistent=False)

    # -- biology installation ---------------------------------------------
    def set_biology(self, sets: BiologicalSets) -> None:
        """Install the drug biology this model scores against.

        Required before any forward pass. Without it the buffers are empty and
        every drug would silently take the MISSING token - a model that trains,
        reports a number, and has seen no biology at all. That failure mode is
        the reason this raises rather than defaulting.
        """
        cfg = self.config
        if cfg.use_protein_level and sets.n_protein_vocab != cfg.n_protein_vocab:
            raise ValueError(
                f"protein vocabulary mismatch: model has {cfg.n_protein_vocab}, "
                f"biology has {sets.n_protein_vocab}"
            )
        if cfg.use_pathway_level and sets.n_pathway_vocab != cfg.n_pathway_vocab:
            raise ValueError(
                f"pathway vocabulary mismatch: model has {cfg.n_pathway_vocab}, "
                f"biology has {sets.n_pathway_vocab}"
            )
        device = self.fusion.weight.device
        for name, tensor in sets.tensors().items():
            self.register_buffer(name, tensor.to(device), persistent=False)
        self.n_drugs = sets.n_drugs
        self._biology_installed = True

    # -- encoding ----------------------------------------------------------
    def encode_biology(
        self, node_idx: torch.Tensor | None = None
    ) -> tuple[torch.Tensor | None, torch.Tensor | None, torch.Tensor]:
        """Encode drug biology. Returns ``(prot, path, mask)``.

        With ``node_idx=None`` every drug is encoded and row *i* is drug *i*.
        With ``node_idx`` given, only those drugs are encoded and row *i* is
        ``node_idx[i]`` - the LOCAL position, which is what a minibatch needs.

        The subset path exists for cost, not for semantics: DeepSets aggregation
        is per drug, so a drug's representation does not depend on which other
        drugs were encoded alongside it, and the subset result is exactly the
        corresponding rows of the full result. ``test_subset_encoding_equals_
        full_encoding`` asserts that rather than leaving it as a claim.

        Encoding the batch's drugs once, rather than once per pair, still
        matters: the embedding tables are shared, so per-pair encoding would
        recompute the same drug many times per step and, with dropout active,
        give one drug several different representations inside a single step.

        ``mask`` is ``[n, 2]`` float: has_protein, has_pathway. Passed to the
        decoder rather than used to gate the embeddings - gating would make
        "missing" and "present but uninformative" indistinguishable downstream.
        """
        if not self._biology_installed:
            raise RuntimeError(
                "set_biology() was never called; every drug would take the "
                "MISSING token and the model would score no biology at all"
            )
        full = node_idx is None
        n = self.n_drugs if full else len(node_idx)
        empty_prot = self.empty_protein if full else self.empty_protein[node_idx]
        empty_path = self.empty_pathway if full else self.empty_pathway[node_idx]

        prot = path = None
        if self.protein_encoder is not None:
            if full:
                pos, owner = None, self.protein_owner
                size = self.protein_size
            else:
                pos, owner = _gather_subset(self.protein_offsets, node_idx)
                size = self.protein_size[node_idx]
            ids = self.protein_id if full else self.protein_id[pos]
            rel = self.protein_rel if full else self.protein_rel[pos]
            ev = self.protein_ev if full else self.protein_ev[pos]
            elements = torch.cat(
                [
                    self.protein_embedding(ids),
                    self.relation_embedding(rel),
                    self.evidence_embedding(ev),
                ],
                dim=-1,
            )
            prot = self.protein_encoder(elements, owner, n, size, empty_prot)

        if self.pathway_encoder is not None:
            if full:
                pos, owner = None, self.pathway_owner
                size = self.pathway_size
            else:
                pos, owner = _gather_subset(self.pathway_offsets, node_idx)
                size = self.pathway_size[node_idx]
            ids = self.pathway_id if full else self.pathway_id[pos]
            path = self.pathway_encoder(
                self.pathway_embedding(ids), owner, n, size, empty_path
            )

        mask = torch.stack([(~empty_prot).float(), (~empty_path).float()], dim=-1)
        return prot, path, mask

    def encode(
        self, mol_batch=None, node_idx: torch.Tensor | None = None
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Fuse the branches into one vector per drug. Returns ``(h, mask)``.

        When ``node_idx`` is given, ``mol_batch`` must contain exactly those
        drugs' molecular graphs, in the same order. The caller owns that
        alignment; a mismatch is caught here by shape rather than producing a
        model that silently pairs one drug's chemistry with another's biology.
        """
        parts: list[torch.Tensor] = []
        prot, path, mask = self.encode_biology(node_idx)
        expected = mask.shape[0]
        if self.mol_encoder is not None:
            if mol_batch is None:
                raise ValueError("use_molecular_branch is on but mol_batch is None")
            pooled, _ = self.mol_encoder(
                mol_batch.x, mol_batch.edge_index, mol_batch.edge_attr, mol_batch.batch
            )
            if pooled.shape[0] != expected:
                raise ValueError(
                    f"mol_batch holds {pooled.shape[0]} molecules but "
                    f"{expected} drugs were selected; the molecular batch must "
                    f"match node_idx exactly, in order"
                )
            parts.append(pooled)
        if prot is not None:
            parts.append(prot)
        if path is not None:
            parts.append(path)
        h = self.fusion_norm(self.fusion(torch.cat(parts, dim=-1)))
        return h, mask

    # -- pair scoring ------------------------------------------------------
    def score_pairs(
        self,
        h: torch.Tensor,
        mask: torch.Tensor,
        idx_a: torch.Tensor,
        idx_b: torch.Tensor,
    ) -> BioPairPrediction:
        h_a, h_b = h[idx_a], h[idx_b]
        m_a, m_b = mask[idx_a], mask[idx_b]
        pair = torch.cat(
            [
                h_a + h_b,                     # commutative
                (h_a - h_b).abs(),             # commutative
                h_a * h_b,                     # commutative
                torch.minimum(m_a, m_b),       # "both have it"
                torch.maximum(m_a, m_b),       # "at least one has it"
            ],
            dim=-1,
        )
        return BioPairPrediction(self.pair_mlp(pair).squeeze(-1))

    def forward(self, mol_batch, idx_a, idx_b) -> BioPairPrediction:
        h, mask = self.encode(mol_batch)
        return self.score_pairs(h, mask, idx_a, idx_b)

    def n_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    def parameter_table(self) -> dict[str, int]:
        """Per-component parameter counts, for the budget table in the report."""
        table: dict[str, int] = {}
        for name, module in [
            ("molecular_encoder", self.mol_encoder),
            ("protein_embedding", self.protein_embedding),
            ("protein_encoder", self.protein_encoder),
            ("pathway_embedding", self.pathway_embedding),
            ("pathway_encoder", self.pathway_encoder),
            ("fusion", self.fusion),
            ("fusion_norm", self.fusion_norm),
            ("pair_mlp", self.pair_mlp),
        ]:
            if module is not None:
                table[name] = sum(p.numel() for p in module.parameters())
        if self.protein_embedding is not None:
            table["relation_embedding"] = sum(p.numel() for p in self.relation_embedding.parameters())
            table["evidence_embedding"] = sum(p.numel() for p in self.evidence_embedding.parameters())
        table["total"] = self.n_parameters()
        return table


#: Buffer skeleton so a model is a valid nn.Module before biology arrives.
#: Registering the names up front means ``load_state_dict`` on a checkpoint has
#: somewhere to put them and ``.to(device)`` does not skip half the model.
_EMPTY_BIOLOGY: dict[str, torch.Tensor] = {
    "protein_id": torch.zeros(0, dtype=torch.long),
    "protein_rel": torch.zeros(0, dtype=torch.long),
    "protein_ev": torch.zeros(0, dtype=torch.long),
    "protein_owner": torch.zeros(0, dtype=torch.long),
    "pathway_id": torch.zeros(0, dtype=torch.long),
    "pathway_owner": torch.zeros(0, dtype=torch.long),
    "protein_size": torch.zeros(0),
    "pathway_size": torch.zeros(0),
    "empty_protein": torch.zeros(0, dtype=torch.bool),
    "empty_pathway": torch.zeros(0, dtype=torch.bool),
    "protein_offsets": torch.zeros(1, dtype=torch.long),
    "pathway_offsets": torch.zeros(1, dtype=torch.long),
}
