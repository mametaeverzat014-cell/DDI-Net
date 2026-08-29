"""
The V2 runner: trains BIO-GINE without any DDI-graph input, and keeps test sealed.

WHY A SECOND TRAINER RATHER THAN A FLAG ON THE FIRST
------------------------------------------------------
``models/train.py`` is built around a ``FeatureBundle``, and a FeatureBundle
contains the message-passing DDI graph: node features, edge index, edge types.
Its ``_encode`` passes all three into the model on every step. That is correct
for Phase A-2, whose question was what the DDI-network branch contributes.

V2's question is what happens when that branch is *gone*. Adding a "skip the
graph" flag to the Phase A-2 trainer would leave the graph constructed, moved
to the device and threaded through the call signature, and the guarantee "V2
never sees DDI topology" would rest on a boolean. Here the guarantee is
structural: this module does not import ``FeatureBundle``, never builds a DDI
graph, and has nowhere to put one.

THE THREE THINGS THIS FILE IS CAREFUL ABOUT
--------------------------------------------
**1. The test set stays sealed.** ``EvaluationMode.VALIDATION_ONLY`` is not a
flag checked before printing. The test buckets are dropped from the split
*before* negatives are sampled, so no test negative is ever drawn, no test
label ever enters a tensor, and ``predict_test`` raises. Dropping them is free
of side effects only because the negative sampler now keys each bucket's RNG on
the bucket name (Addendum 17's ``eval_seed``): validation negatives are
identical whether or not test was sampled, which is asserted by a test.

**2. Minibatching without re-encoding the world.** The preregistered grid uses
256- and 512-pair batches. Encoding all 1,705 drugs on each of ~700 steps per
epoch would cost roughly 700x a Phase A-2 epoch. Instead each step encodes only
the drugs its pairs mention (at most 2x batch size), which is exact rather than
approximate: DeepSets aggregates per drug, so a drug's representation does not
depend on which others were encoded with it.

**3. A run is identified by what it is, not by where it sat.** ``run_id`` is a
hash of the identity fields. Resume compares run ids, so an interrupted grid
picks up exactly the configurations it has not finished, and a row cannot be
duplicated by re-running with the arguments in a different order.

WHAT IS DELIBERATELY NOT HERE
------------------------------
Hyperparameter selection, test evaluation, calibration fitting, and the grid
itself. Selection reads validation only (preregistration section 10) and test is
touched exactly once at the end of the whole programme; keeping those in
separate modules is what makes that auditable.
"""

from __future__ import annotations

import hashlib
import json
import random
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F

from ..data import negatives as neg
from ..data.biology import EVIDENCE_POLICIES, BiologyBundle, load_biology
from ..data.split import BUCKET_NAMES, DrugLevelSplit
from ..data.v2_dataset import DATASET_VERSION, V2Universe
from ..eval.calibration import expected_calibration_error
from ..eval.metrics import compute_binary_metrics
from ..models.bio_gine import BiologicalSets, BioGine, BioGineConfig

#: Frozen CONTROL F artefact. A directory, not a file, because the manifest that
#: proves what the shuffle did lives beside the Parquet and both are recorded.
CONTROL_F_DIR = Path(
    "data/mechanism_v1_controls/shuffled_biology_seed20260829"
)
CONTROL_F_EDGES = CONTROL_F_DIR / "drug_protein_edges_shuffled.parquet"
CONTROL_F_MANIFEST = CONTROL_F_DIR / "SHUFFLE_MANIFEST.json"


class TestSetSealed(RuntimeError):
    """Raised when something tries to reach the test set in validation-only mode.

    A distinct exception type so a test can assert the refusal happened for this
    reason and not because of an unrelated ``RuntimeError`` elsewhere.
    """

    #: pytest collects any class named Test*; this is an exception, not a suite.
    __test__ = False


class EvaluationMode(str, Enum):
    #: Development mode. Test buckets never enter the pipeline at all.
    VALIDATION_ONLY = "validation_only"
    #: Final evaluation. Used exactly once, at the end, after the configuration
    #: is frozen. Not used anywhere in V2 phase 2.
    WITH_TEST = "with_test"


@dataclass(frozen=True)
class V2RunSpec:
    """Everything that makes one run *that* run.

    ``run_id`` hashes these fields, so two invocations with the same values are
    the same run and a resume can recognise it. ``evaluation_mode`` is
    deliberately NOT part of the identity: whether test is scored afterwards
    does not change what was trained, and excluding it means a validation-only
    checkpoint stays resumable when the final evaluation eventually runs.
    """

    # -- what is being trained --------------------------------------------
    model: str = "bio_gine"
    ablation: str = "M4"
    biology_source: str = "true"        # "true" | "shuffled"
    aggregation: str = "mean"           # "sum" is CONTROL C

    # -- data --------------------------------------------------------------
    scheme: str = "drug"
    split_seed: int = 0
    negatives: str = "degree_matched"
    neg_ratio: float = 1.0
    #: Fixed seed for the VALIDATION negatives, shared by every run. Validation
    #: is the selection surface for the whole grid, so every configuration must
    #: be scored on the same validation pairs or the comparison is between
    #: samples rather than between models (Addendum 17).
    eval_negative_seed: int = 0

    # -- hyperparameters (the preregistered grid moves these five) ---------
    bio_dim: int = 64
    dropout_bio: float = 0.1
    dropout_pair: float = 0.1
    lr: float = 1.0e-3
    batch_size: int = 256

    # -- fixed by the preregistration --------------------------------------
    max_epochs: int = 400
    patience: int = 30
    weight_decay: float = 1.0e-4
    hidden_dim: int = 128

    # -- molecular branch: the measured Phase A-2 configuration ------------
    # NOT the plan text's "4-layer, d=128". Phase A-2 froze hidden_dim=64,
    # mol_layers=3, dropout=0.1, sum pooling. M0 in the evidence ladder IS the
    # frozen Phase A-2 GINE result, so a different molecular branch would make
    # every M-minus-M0 difference confound "added biology" with "changed the
    # chemistry encoder". See docs/V2_IMPLEMENTATION_NOTES.md section 1.
    mol_dim: int = 64
    mol_layers: int = 3
    dropout_mol: float = 0.1
    mol_pooling: str = "sum"

    # -- run seed ----------------------------------------------------------
    seed: int = 0

    #: Identity fields, in a fixed order. Anything absent from this tuple can
    #: change without making it a different run.
    IDENTITY: tuple[str, ...] = field(
        default=(
            "model", "ablation", "biology_source", "aggregation",
            "scheme", "split_seed", "negatives", "neg_ratio", "eval_negative_seed",
            "bio_dim", "dropout_bio", "dropout_pair", "lr", "batch_size",
            "max_epochs", "patience", "weight_decay", "hidden_dim",
            "mol_dim", "mol_layers", "dropout_mol", "mol_pooling", "seed",
        ),
        repr=False,
        compare=False,
    )

    def identity(self) -> dict:
        return {k: getattr(self, k) for k in self.IDENTITY}

    def run_id(self) -> str:
        """Deterministic 16-hex-character id derived from the identity fields.

        ``sort_keys`` so the id does not depend on field declaration order, and
        a hash rather than a joined string so the id stays a fixed length as
        fields are added - a filename built from every hyperparameter grows
        past path limits and changes shape whenever the grid does.
        """
        blob = json.dumps(self.identity(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    def config_id(self) -> str:
        """Id of the hyperparameter configuration, ignoring the seed.

        The grid reports one row per (config, seed); ``config_id`` is what
        groups the three seeds of a configuration together for selection.
        """
        blob = json.dumps(
            {k: v for k, v in self.identity().items() if k != "seed"},
            sort_keys=True, separators=(",", ":"),
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("IDENTITY", None)
        return d


@dataclass
class V2History:
    """What happened during training. No test field exists on purpose."""

    epochs_run: int = 0
    best_epoch: int = 0
    best_val_auprc: float = -np.inf
    stopped_by: str = "epoch_limit"
    wall_time_s: float = 0.0
    train_loss: list[float] = field(default_factory=list)
    val_auprc: list[float] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"{self.epochs_run} epochs in {self.wall_time_s:.1f}s | "
            f"best val AUPRC {self.best_val_auprc:.4f} @ epoch {self.best_epoch} "
            f"({self.stopped_by})"
        )


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def git_commit() -> str:
    """Current commit, or ``"unknown"``. Recorded in every manifest.

    Never raises: a manifest that fails to write because git is unavailable is
    worse than a manifest that says the commit is unknown.
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------
# Biology selection
# --------------------------------------------------------------------------

def resolve_biology(
    spec: V2RunSpec, drug_ids: list[str]
) -> tuple[BiologyBundle, dict]:
    """Load true or frozen-shuffled biology, and the provenance to record.

    ``shuffled`` points at the frozen CONTROL F artefact and nothing else. The
    shuffle is never produced here: it was frozen once, before any training, and
    regenerating it inside a training run would silently make every run's
    control a different control. If the file is absent this raises rather than
    falling back to true biology, because a CONTROL F run that quietly used real
    biology would report the exact opposite of what it measured.
    """
    if spec.biology_source not in ("true", "shuffled"):
        raise ValueError(
            f"biology_source must be 'true' or 'shuffled', got {spec.biology_source!r}"
        )
    if spec.ablation not in EVIDENCE_POLICIES:
        raise ValueError(
            f"Unknown ablation {spec.ablation!r}; expected one of "
            f"{sorted(EVIDENCE_POLICIES)}"
        )

    provenance: dict = {"biology_source": spec.biology_source,
                        "ablation": spec.ablation}
    edges_path = None
    if spec.biology_source == "shuffled":
        if not CONTROL_F_EDGES.exists():
            raise FileNotFoundError(
                f"CONTROL F artefact not found at {CONTROL_F_EDGES}. It is "
                f"frozen, not generated: a shuffled run cannot proceed without "
                f"it, and must never fall back to true biology."
            )
        edges_path = CONTROL_F_EDGES
        manifest = json.loads(CONTROL_F_MANIFEST.read_text())
        provenance.update({
            "control_f_seed": manifest.get("shuffle_seed"),
            "control_f_manifest_sha256": _sha256(CONTROL_F_MANIFEST),
            "control_f_edges_sha256": _sha256(CONTROL_F_EDGES),
            "control_f_swaps_per_edge": manifest.get("swaps_per_edge"),
        })

    bundle = load_biology(
        policy=spec.ablation, drug_protein_path=edges_path, drug_ids=drug_ids
    )
    provenance.update(bundle.describe())
    return bundle, provenance


# --------------------------------------------------------------------------
# Dataset assembly
# --------------------------------------------------------------------------

def build_v2_dataset(
    spec: V2RunSpec,
    universe: V2Universe,
    split: DrugLevelSplit,
    mode: EvaluationMode,
) -> pd.DataFrame:
    """Sample negatives and assemble the labelled pair table.

    Reuses the Phase A/A-2 sampler unchanged - not a reimplementation with the
    same name. ``seed`` varies the TRAINING negatives with the run seed;
    ``eval_seed`` pins the validation negatives so every configuration in the
    grid is selected on the same validation pairs.

    In ``VALIDATION_ONLY`` the test buckets are removed from the split before
    sampling, so the sampler never draws a test negative and no test label is
    produced. That is possible without disturbing validation only because the
    sampler keys each bucket's RNG on the bucket name; ``eval_seed`` is what
    switches that on.
    """
    if mode is EvaluationMode.VALIDATION_ONLY:
        kept = {
            name: frame for name, frame in split.buckets.items()
            if not name.startswith("test")
        }
        split = DrugLevelSplit(
            train_drugs=split.train_drugs,
            val_drugs=split.val_drugs,
            test_drugs=split.test_drugs,
            buckets=kept,
            discarded=split.discarded,
            group_by=split.group_by,
            seed=split.seed,
        )

    dataset, _ = neg.build_dataset(
        split,
        universe.drug_names,
        universe.positive_keys,
        neg.NegativeSamplingConfig(
            strategy=spec.negatives,
            ratio=spec.neg_ratio,
            seed=spec.seed,
            eval_seed=spec.eval_negative_seed,
        ),
    )
    neg.verify_no_negative_is_positive(dataset, universe.positive_keys)

    if mode is EvaluationMode.VALIDATION_ONLY:
        leaked = sorted({b for b in dataset["bucket"].unique() if b.startswith("test")})
        if leaked:
            raise TestSetSealed(
                f"validation_only produced test buckets {leaked}; the seal is broken"
            )
    return dataset


# --------------------------------------------------------------------------
# Trainer
# --------------------------------------------------------------------------

class V2Trainer:
    """Trains a :class:`BioGine` on molecular + biological features only.

    Holds no DDI graph, no adjacency, no node degree. The only thing derived
    from the DDI labels is the label itself.
    """

    def __init__(
        self,
        spec: V2RunSpec,
        universe: V2Universe,
        split: DrugLevelSplit,
        bundle: BiologyBundle,
        mol_graphs: dict,
        *,
        mode: EvaluationMode = EvaluationMode.VALIDATION_ONLY,
        device: str = "cpu",
        dataset: pd.DataFrame | None = None,
    ) -> None:
        self.spec = spec
        self.mode = EvaluationMode(mode)
        self.device = torch.device(device)
        self.universe = universe
        self.split = split
        self.bundle = bundle

        # Seed BEFORE the model is constructed. Phase A-2 learned this the hard
        # way: Trainer.__init__ seeding after construction made a run's weights
        # depend on its position in the grid rather than on its seed
        # (LIMITATIONS.md section 6b).
        set_seed(spec.seed)

        self.drug_index = {d: i for i, d in enumerate(bundle.drug_ids)}
        self.mol_data = [mol_graphs[d].data for d in bundle.drug_ids]

        self.model = BioGine(self._model_config()).to(self.device)
        self.model.set_biology(BiologicalSets(bundle))

        self.dataset = dataset if dataset is not None else build_v2_dataset(
            spec, universe, split, self.mode
        )
        self.buckets = {
            name: self._prepare(group)
            for name, group in self.dataset.groupby("bucket", sort=True)
        }
        train = self._pooled("train")
        if train is None:
            raise ValueError("dataset has no training bucket")
        val = self._pooled("val")
        if val is None:
            raise ValueError("dataset has no validation bucket")
        self._train, self._val = train, val

        n_pos = int(train["labels"].sum())
        n_neg = len(train["labels"]) - n_pos
        self.pos_weight = torch.tensor(
            min(n_neg / max(n_pos, 1), 10.0), dtype=torch.float, device=self.device
        )

        self.optimizer = torch.optim.AdamW(
            self.model.parameters(), lr=spec.lr, weight_decay=spec.weight_decay
        )
        self.scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            self.optimizer, T_max=spec.max_epochs
        )
        self.history = V2History()
        self._best_state: dict | None = None
        self._start_epoch = 0

    # -- configuration -----------------------------------------------------
    def _model_config(self) -> BioGineConfig:
        from ..features.molgraph import ATOM_FEATURE_DIM, BOND_FEATURE_DIM

        policy = EVIDENCE_POLICIES[self.spec.ablation]
        return BioGineConfig(
            n_protein_vocab=self.bundle.n_proteins,
            n_pathway_vocab=self.bundle.n_pathways,
            atom_dim=ATOM_FEATURE_DIM,
            bond_dim=BOND_FEATURE_DIM,
            mol_dim=self.spec.mol_dim,
            mol_layers=self.spec.mol_layers,
            mol_pooling=self.spec.mol_pooling,
            dropout_mol=self.spec.dropout_mol,
            bio_dim=self.spec.bio_dim,
            dropout_bio=self.spec.dropout_bio,
            aggregation=self.spec.aggregation,
            hidden_dim=self.spec.hidden_dim,
            dropout_pair=self.spec.dropout_pair,
            use_molecular_branch=True,
            # M0 is the frozen Phase A-2 GINE result and is not retrained here;
            # the switches still exist so the ladder is expressible and so a
            # molecular-only control can be run deliberately if ever wanted.
            use_protein_level=bool(policy.evidence_types),
            use_pathway_level=policy.use_pathways,
        )

    def _prepare(self, group: pd.DataFrame) -> dict:
        idx = self.drug_index
        keep = [
            i for i, (a, b) in enumerate(zip(group["drug_a"], group["drug_b"]))
            if a in idx and b in idx
        ]
        group = group.iloc[keep]
        return {
            "idx_a": torch.tensor([idx[a] for a in group["drug_a"]], dtype=torch.long),
            "idx_b": torch.tensor([idx[b] for b in group["drug_b"]], dtype=torch.long),
            "labels": torch.tensor(group["label"].to_numpy(), dtype=torch.long),
            "frame": group.reset_index(drop=True),
        }

    def _pooled(self, prefix: str) -> dict | None:
        """Concatenate buckets by name prefix.

        Prefix matching, not exact: the drug-disjoint scheme names its buckets
        ``val_S2``/``val_S3`` while other schemes emit a flat ``val``. Exact
        matching would silently select on an empty set.
        """
        parts = [d for name, d in self.buckets.items()
                 if name.startswith(prefix) and len(d["labels"])]
        if not parts:
            return None
        if len(parts) == 1:
            return parts[0]
        return {
            "idx_a": torch.cat([d["idx_a"] for d in parts]),
            "idx_b": torch.cat([d["idx_b"] for d in parts]),
            "labels": torch.cat([d["labels"] for d in parts]),
            "frame": pd.concat([d["frame"] for d in parts], ignore_index=True),
        }

    # -- the sealed test set ----------------------------------------------
    def predict_test(self):
        """Refuses in validation-only mode. There is nothing to fall back to.

        In ``VALIDATION_ONLY`` the test buckets were dropped before negatives
        were sampled, so this cannot be satisfied even in principle - the labels
        do not exist in this process. The explicit refusal is so the failure is
        a clear message rather than an empty array that a caller might average.
        """
        if self.mode is EvaluationMode.VALIDATION_ONLY:
            raise TestSetSealed(
                "predict_test() called in validation_only mode. The test "
                "buckets were removed before negative sampling; no test label "
                "exists in this process. Re-run with "
                "evaluation_mode=with_test only after the configuration is "
                "frozen (docs/V2_PREREGISTRATION.md section 10.3)."
            )
        return self._predict(self._pooled("test"))

    # -- forward -----------------------------------------------------------
    def _batch_forward(self, idx_a: torch.Tensor, idx_b: torch.Tensor):
        """Encode only the drugs this batch mentions, then score its pairs.

        ``torch.unique`` gives the subset and, with ``return_inverse``, the
        local positions in one pass - so the mapping from global drug index to
        row of ``h`` is produced by the same call that defines the subset and
        cannot drift from it.
        """
        from torch_geometric.data import Batch

        pair_nodes = torch.cat([idx_a, idx_b])
        node_idx, inverse = torch.unique(pair_nodes, return_inverse=True)
        local_a, local_b = inverse[: len(idx_a)], inverse[len(idx_a):]

        mol_batch = Batch.from_data_list(
            [self.mol_data[i] for i in node_idx.tolist()]
        ).to(self.device)
        h, mask = self.model.encode(mol_batch, node_idx.to(self.device))
        return self.model.score_pairs(h, mask, local_a.to(self.device),
                                      local_b.to(self.device))

    def _train_epoch(self) -> float:
        self.model.train()
        n = len(self._train["labels"])
        batch_size = self.spec.batch_size or n
        perm = torch.randperm(n)
        total, steps = 0.0, 0
        for start in range(0, n, batch_size):
            sel = perm[start: start + batch_size]
            self.optimizer.zero_grad()
            pred = self._batch_forward(self._train["idx_a"][sel],
                                       self._train["idx_b"][sel])
            loss = F.binary_cross_entropy_with_logits(
                pred.interaction_logit,
                self._train["labels"][sel].float().to(self.device),
                pos_weight=self.pos_weight,
            )
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
            self.optimizer.step()
            total += float(loss.detach())
            steps += 1
        return total / max(steps, 1)

    @torch.no_grad()
    def _predict(self, data: dict | None, chunk: int = 4096):
        if data is None or not len(data["labels"]):
            return np.array([]), np.array([])
        self.model.eval()
        scores = []
        n = len(data["labels"])
        for start in range(0, n, chunk):
            sl = slice(start, start + chunk)
            pred = self._batch_forward(data["idx_a"][sl], data["idx_b"][sl])
            scores.append(pred.interaction_prob().cpu().numpy())
        return data["labels"].numpy(), np.concatenate(scores)

    def predict_validation(self):
        return self._predict(self._val)

    def validation_metrics(self, threshold: float = 0.5) -> dict:
        """AUPRC, AUROC, Brier and ECE on validation. Never on test."""
        y, s = self.predict_validation()
        if not len(y):
            return {}
        m = compute_binary_metrics(y, s, threshold=threshold)
        return {
            "val_auprc": float(m.auprc),
            "val_auroc": float(m.auc_roc),
            "val_brier": float(m.brier),
            "val_ece": float(expected_calibration_error(y, s, n_bins=15)),
            "val_n": int(m.n),
            "val_prevalence": float(m.prevalence),
        }

    # -- training loop -----------------------------------------------------
    def fit(self, max_epochs: int | None = None, verbose: bool = False) -> V2History:
        """Train with early stopping on VALIDATION AUPRC. Never on test.

        Selection on validation AUPRC is the preregistered rule
        (docs/V2_PREREGISTRATION.md section 10.1). Not loss - its scale moves
        with the class weighting - and not accuracy, which is uninformative at
        this prevalence.
        """
        budget = max_epochs if max_epochs is not None else self.spec.max_epochs
        started = time.time()
        bad = 0
        for epoch in range(self._start_epoch, budget):
            loss = self._train_epoch()
            self.scheduler.step()
            score = self.validation_metrics().get("val_auprc", float("nan"))
            self.history.train_loss.append(loss)
            self.history.val_auprc.append(score)
            self.history.epochs_run = epoch + 1

            if score > self.history.best_val_auprc:
                self.history.best_val_auprc = score
                self.history.best_epoch = epoch + 1
                self._best_state = {
                    k: v.detach().cpu().clone()
                    for k, v in self.model.state_dict().items()
                }
                bad = 0
            else:
                bad += 1
            if verbose:
                print(f"  epoch {epoch+1:4d} loss {loss:.4f} val_auprc {score:.4f}")
            if bad >= self.spec.patience:
                self.history.stopped_by = "patience"
                break
        else:
            self.history.stopped_by = "epoch_limit"

        self.history.wall_time_s += time.time() - started
        if self._best_state is not None:
            self.model.load_state_dict(self._best_state)
        return self.history

    # -- checkpointing -----------------------------------------------------
    def save_checkpoint(self, path: Path) -> str:
        """Write the best-validation weights plus enough state to resume.

        Returns the checkpoint's sha256, which goes into the manifest: a
        manifest that names a checkpoint it cannot identify is a manifest that
        cannot detect the checkpoint being replaced.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "run_id": self.spec.run_id(),
                "spec": self.spec.to_dict(),
                "model_state": self._best_state or self.model.state_dict(),
                "optimizer_state": self.optimizer.state_dict(),
                "scheduler_state": self.scheduler.state_dict(),
                "history": asdict(self.history),
                "epochs_run": self.history.epochs_run,
            },
            path,
        )
        return _sha256(path)

    def load_checkpoint(self, path: Path) -> None:
        """Restore weights and optimiser state, refusing a foreign checkpoint.

        The run id is checked because a checkpoint from a different
        configuration would load cleanly - the shapes usually match across the
        grid - and produce a run whose reported hyperparameters are not the ones
        that trained it.
        """
        blob = torch.load(Path(path), map_location=self.device, weights_only=False)
        if blob.get("run_id") != self.spec.run_id():
            raise ValueError(
                f"checkpoint belongs to run {blob.get('run_id')}, not "
                f"{self.spec.run_id()}; refusing to resume a different configuration"
            )
        self.model.load_state_dict(blob["model_state"])
        self.optimizer.load_state_dict(blob["optimizer_state"])
        self.scheduler.load_state_dict(blob["scheduler_state"])
        self._best_state = {k: v.clone() for k, v in blob["model_state"].items()}
        stored = blob.get("history", {})
        self.history = V2History(**stored) if stored else V2History()
        self._start_epoch = int(blob.get("epochs_run", 0))

    # -- manifest ----------------------------------------------------------
    def manifest(self, *, checkpoint_hash: str = "", extra: dict | None = None) -> dict:
        """Everything needed to say what this run was, without reading its code."""
        out = {
            "run_id": self.spec.run_id(),
            "config_id": self.spec.config_id(),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "git_commit": git_commit(),
            "dataset_version": DATASET_VERSION,
            "dataset_manifest_sha256": self.universe.manifest_hash,
            "n_drugs": len(self.universe.drugs),
            "n_positive_pairs": len(self.universe.pairs),
            "split_scheme": self.spec.scheme,
            "split_seed": self.spec.split_seed,
            "split_sizes": {
                "train_drugs": len(self.split.train_drugs),
                "val_drugs": len(self.split.val_drugs),
                "test_drugs": len(self.split.test_drugs),
            },
            "negative_sampling": {
                "strategy": self.spec.negatives,
                "ratio": self.spec.neg_ratio,
                "train_seed": self.spec.seed,
                "eval_seed": self.spec.eval_negative_seed,
            },
            "evaluation_mode": self.mode.value,
            "model_variant": self.spec.model,
            "ablation": self.spec.ablation,
            "hyperparameters": self.spec.to_dict(),
            "seed": self.spec.seed,
            "n_parameters": self.model.n_parameters(),
            "parameter_table": self.model.parameter_table(),
            "best_epoch": self.history.best_epoch,
            "best_val_auprc": self.history.best_val_auprc,
            "epochs_run": self.history.epochs_run,
            "stopped_by": self.history.stopped_by,
            "wall_time_s": round(self.history.wall_time_s, 1),
            "checkpoint_sha256": checkpoint_hash,
            "test_evaluated": self.mode is EvaluationMode.WITH_TEST,
        }
        if extra:
            out.update(extra)
        return out
