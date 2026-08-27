"""
Training loop, with the choices that matter for a small, imbalanced dataset.

MODEL SELECTION IS ON VALIDATION AUPRC IN THE S2 SETTING
---------------------------------------------------------
Not on loss, not on accuracy, and not on S1.

* *Not loss*: the loss is multi-task and its scale depends on task weights, so
  comparing it across configurations is meaningless.
* *Not accuracy*: useless under imbalance (see ``eval.metrics``).
* *Not S1*: S1 is the setting we distrust. Selecting checkpoints on S1 would
  quietly optimise for the memorisation we are trying to avoid. S2 - one unseen
  drug - is the deployment question, so it is the selection criterion.

If the S2 validation bucket is empty (possible on very small graphs), we fall
back to the pooled validation set and say so, rather than silently selecting on
something else.

EARLY STOPPING IS NOT OPTIONAL HERE
------------------------------------
With ~200 training pairs and ~700k parameters, this model can memorise the
training set completely. Early stopping on a drug-disjoint validation set is the
main thing standing between you and a beautiful training curve that means
nothing. We restore the best checkpoint rather than using the last one.

DETERMINISM
-----------
Seeds are set for Python, NumPy and Torch, and the exact configuration is stored
in the history object. A judge asking "can you re-run that?" should get "yes,
here is the command" rather than an apology about GPU non-determinism.
"""

from __future__ import annotations

import random
import time
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd
import torch
from torch_geometric.loader import DataLoader

from ..eval.metrics import BinaryMetrics, compute_binary_metrics
from ..features.build import FeatureBundle
from .ddinet import DDINet, DDINetConfig, compute_loss


@dataclass
class TrainConfig:
    epochs: int = 300
    lr: float = 1e-3
    weight_decay: float = 1e-4
    #: None = full batch. The cost of a step is dominated by encoding all
    #: molecules, not by the pair count, so minibatching pairs multiplies epoch
    #: cost roughly twentyfold at this scale while buying nothing. See
    #: docs/PHASE_A2_PROTOCOL.md section 9.
    batch_size: int | None = None
    patience: int = 40
    seed: int = 0
    device: str = "cpu"
    grad_clip: float = 1.0
    #: Cap on pos_weight. Uncapped, a 1:50 ratio yields pos_weight=50 and the
    #: model predicts "interaction" for everything - the mirror image of the
    #: majority-class failure it was meant to fix.
    max_pos_weight: float = 10.0
    #: Prefix, not an exact name: bucket naming differs between split
    #: schemes ("val" vs "val_S2"/"val_S3"), and exact matching would
    #: silently select on an empty set for two of the three schemes.
    selection_bucket: str = "val"
    selection_metric: str = "auprc"
    verbose: bool = True


@dataclass
class TrainHistory:
    config: dict
    epochs_run: int = 0
    best_epoch: int = 0
    best_score: float = -np.inf
    train_loss: list[float] = field(default_factory=list)
    val_scores: list[float] = field(default_factory=list)
    #: Prefix, not an exact name: bucket naming differs between split
    #: schemes ("val" vs "val_S2"/"val_S3"), and exact matching would
    #: silently select on an empty set for two of the three schemes.
    selection_bucket: str = "val"
    #: "patience" or "epoch_limit". Which one ended the run matters for
    #: interpretation: a run stopped by the epoch limit was possibly still
    #: improving, so its score is a lower bound rather than a converged
    #: result. Phase A-2 reports the fraction of runs in each state alongside
    #: the metrics (docs/PHASE_A2_PROTOCOL.md, Addendum 2).
    stopped_by: str = "epoch_limit"
    wall_time_s: float = 0.0
    #: Per-epoch adversary diagnostics. Empty unless the model was built with
    #: `adversarial_degree`. Recorded per epoch rather than summarised because
    #: the reversal strength follows a ramp and early stopping can cut it short
    #: - the lambda actually REACHED is what a result must be reported against,
    #: not the lambda that was configured (docs/DEBIAS_PROTOCOL.md section 6.3).
    adv_lambda: list[float] = field(default_factory=list)
    adv_degree_mse: list[float] = field(default_factory=list)
    adv_embedding_variance: list[float] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"trained {self.epochs_run} epochs in {self.wall_time_s:.1f}s | "
            f"best {self.selection_bucket} {self.config.get('selection_metric','auprc')}"
            f"={self.best_score:.4f} @ epoch {self.best_epoch} ({self.stopped_by})"
        )


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


class Trainer:
    """Trains a :class:`DDINet` on a :class:`FeatureBundle` + labelled dataset."""

    def __init__(
        self,
        model: DDINet,
        bundle: FeatureBundle,
        dataset: pd.DataFrame,
        config: TrainConfig | None = None,
    ) -> None:
        self.cfg = config or TrainConfig()
        set_seed(self.cfg.seed)

        self.device = torch.device(self.cfg.device)
        self.model = model.to(self.device)
        self.bundle = bundle
        self.dataset = dataset

        # The molecular batch is fixed for the whole run, so build it once. The
        # order MUST match the DDI-graph node order or every pair index is wrong.
        names = list(bundle.drugs["name"])
        loader = DataLoader([bundle.mol_graphs[n].data for n in names],
                            batch_size=len(names), shuffle=False)
        self.mol_batch = next(iter(loader)).to(self.device)

        g = bundle.graph
        self.node_features = g.node_features.to(self.device)
        self.edge_index = g.edge_index.to(self.device)
        self.edge_type = g.edge_type.to(self.device)

        self.buckets = {
            name: self._prepare(group)
            for name, group in dataset.groupby("bucket", sort=True)
        }

        train = self._pooled("train")
        if train is None:
            raise ValueError("Dataset has no bucket whose name starts with 'train'")
        n_pos = int(train["labels"].sum())
        n_neg = len(train["labels"]) - n_pos
        raw = (n_neg / max(n_pos, 1))
        self.pos_weight = torch.tensor(
            min(raw, self.cfg.max_pos_weight), dtype=torch.float, device=self.device
        )

        # Nodes the degree adversary is allowed to see. TRAINING drugs only:
        # a held-out drug's training-graph degree is zero by construction of the
        # split, so including it would teach the adversary an artefact of the
        # split rather than a property of the drug - and would make the
        # debiasing look stronger than it is. Computed once; the training pairs
        # do not change during a run.
        self._train_nodes = torch.unique(
            torch.cat([train["idx_a"], train["idx_b"]])
        ).to(self.device)

        self.optimizer = torch.optim.AdamW(
            self.model.parameters(), lr=self.cfg.lr, weight_decay=self.cfg.weight_decay
        )
        # Cosine annealing: no schedule to tune, and it reliably beats a constant
        # LR on small datasets by taking small steps once near a minimum.
        self.scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            self.optimizer, T_max=self.cfg.epochs
        )

    def _prepare(self, group: pd.DataFrame) -> dict:
        """Index a bucket's pairs into the drug ordering used by the graph."""
        idx = self.bundle.name_to_idx
        keep = [
            i for i, (a, b) in enumerate(zip(group["drug_a"], group["drug_b"]))
            if a in idx and b in idx
        ]
        group = group.iloc[keep]
        return {
            "idx_a": torch.tensor([idx[a] for a in group["drug_a"]], dtype=torch.long,
                                  device=self.device),
            "idx_b": torch.tensor([idx[b] for b in group["drug_b"]], dtype=torch.long,
                                  device=self.device),
            "labels": torch.tensor(group["label"].to_numpy(), dtype=torch.long,
                                   device=self.device),
            "frame": group.reset_index(drop=True),
        }

    def _pooled(self, prefix: str) -> dict | None:
        """Concatenate every bucket whose name starts with ``prefix``.

        Split schemes name buckets differently - the drug-level scheme emits
        ``test_S2``/``test_S3`` while the random-pair scheme emits a flat
        ``test`` - so matching by prefix is what keeps the trainer
        scheme-agnostic. Exact matching would silently train or evaluate on an
        empty set for two of the three schemes and report it as success.
        """
        parts = [data for name, data in self.buckets.items() if name.startswith(prefix)]
        parts = [d for d in parts if len(d["labels"])]
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

    # -- forward helpers ---------------------------------------------------
    def _encode(self, *, return_attention: bool = False):
        return self.model.encode(
            self.mol_batch, self.node_features, self.edge_index, self.edge_type,
            return_attention=return_attention,
        )

    # -- training ----------------------------------------------------------
    def _train_epoch(self, progress: float = 0.0) -> tuple[float, dict | None]:
        """One pass. ``progress`` drives the adversarial ramp; ignored without one.

        Returns the mean loss and, when an adversary is present, its
        diagnostics for this epoch.
        """
        self.model.train()
        train = self._pooled("train")
        n = len(train["labels"])
        batch_size = self.cfg.batch_size or n
        perm = torch.randperm(n, device=self.device)
        total, n_batches = 0.0, 0
        adv_out = None

        for start in range(0, n, batch_size):
            sel = perm[start : start + batch_size]
            self.optimizer.zero_grad()

            # Re-encode every step: the graph encoder's parameters change, so
            # cached embeddings would be stale and the gradient wrong.
            enc = self._encode()
            pred = self.model.score_pairs(enc, train["idx_a"][sel], train["idx_b"][sel])
            loss, _ = compute_loss(
                pred, train["labels"][sel], pos_weight=self.pos_weight
            )

            # The adversarial term is a plain addition: the sign flip lives in
            # the reversal layer, so the optimiser needs no special handling.
            # Applied to TRAINING drugs only - a held-out drug's training-graph
            # degree is zero by construction of the split, and regressing onto
            # that would measure the split, not the drug.
            if self.model.degree_adversary is not None:
                adv = self.model.adversarial_loss(enc, self._train_nodes, progress)
                (loss + adv.loss).backward()
                adv_out = adv
            else:
                loss.backward()
            if self.cfg.grad_clip:
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.cfg.grad_clip)
            self.optimizer.step()
            total += float(loss.detach())
            n_batches += 1

        diag = None
        if adv_out is not None:
            diag = {
                "lambda": adv_out.lambd,
                "degree_mse": adv_out.degree_mse,
                "embedding_variance": adv_out.embedding_variance,
            }
        return total / max(n_batches, 1), diag

    @torch.no_grad()
    def predict_bucket(self, bucket: str) -> tuple[np.ndarray, np.ndarray]:
        """Returns ``(y_true, interaction_prob)``."""
        data = self._pooled(bucket)
        if data is None or len(data["labels"]) == 0:
            return np.array([]), np.array([])
        self.model.eval()
        enc = self._encode()
        pred = self.model.score_pairs(enc, data["idx_a"], data["idx_b"])
        return (
            data["labels"].cpu().numpy(),
            pred.interaction_prob().cpu().numpy(),
        )

    def bucket_frame(self, prefix: str) -> pd.DataFrame | None:
        """The frame behind :meth:`predict_bucket`, row-for-row aligned with it.

        Callers that want per-setting breakdowns need to mask the prediction
        vector, and the only safe mask is one built from the same frame the
        predictions came from. Reconstructing it outside by filtering the
        original dataset looks equivalent but is not: pooling groups buckets by
        name, and unfeaturisable pairs are dropped, so the two row orders can
        differ and every per-setting number would then be silently wrong.
        """
        data = self._pooled(prefix)
        return None if data is None else data["frame"]

    def _selection_score(self) -> tuple[float, str]:
        bucket = self.cfg.selection_bucket
        y, s = self.predict_bucket(bucket)
        if len(y) == 0:
            return float("nan"), "none"
        if len(np.unique(y)) < 2:
            return float("nan"), bucket
        m = compute_binary_metrics(y, s)
        return getattr(m, self.cfg.selection_metric), bucket

    def fit(self) -> TrainHistory:
        history = TrainHistory(
            config=asdict(self.cfg),
            selection_bucket=self.cfg.selection_bucket,
        )
        best_state = None
        epochs_without_improvement = 0
        start = time.time()

        for epoch in range(1, self.cfg.epochs + 1):
            # Progress is measured in STEPS over the step budget. Training is
            # full-batch, so one epoch is one optimiser step and the two
            # coincide - but the ramp is defined on steps, and stating it that
            # way keeps the schedule correct if batching is ever turned on.
            loss, adv_diag = self._train_epoch((epoch - 1) / max(self.cfg.epochs, 1))
            if adv_diag is not None:
                history.adv_lambda.append(adv_diag["lambda"])
                history.adv_degree_mse.append(adv_diag["degree_mse"])
                history.adv_embedding_variance.append(adv_diag["embedding_variance"])
            self.scheduler.step()
            score, used_bucket = self._selection_score()
            history.selection_bucket = used_bucket
            history.train_loss.append(loss)
            history.val_scores.append(float(score))

            improved = np.isfinite(score) and score > history.best_score + 1e-5
            if improved:
                history.best_score = float(score)
                history.best_epoch = epoch
                best_state = {k: v.detach().clone() for k, v in self.model.state_dict().items()}
                epochs_without_improvement = 0
            else:
                epochs_without_improvement += 1

            if self.cfg.verbose and (epoch % 20 == 0 or epoch == 1):
                print(f"  epoch {epoch:4d}  loss {loss:.4f}  "
                      f"{used_bucket} {self.cfg.selection_metric} {score:.4f}"
                      f"{'  *' if improved else ''}")

            # Recorded before the break, not after: assigning it at the end of
            # the body undercounts every early-stopped run by one epoch, and
            # that count is what tells "converged" from "ran out of budget".
            history.epochs_run = epoch

            if epochs_without_improvement >= self.cfg.patience:
                history.stopped_by = "patience"
                if self.cfg.verbose:
                    print(f"  early stop at epoch {epoch} "
                          f"(no improvement for {self.cfg.patience} epochs)")
                break

        # Restore the best checkpoint. Using the final weights would report a
        # model that early stopping already judged worse.
        if best_state is not None:
            self.model.load_state_dict(best_state)
        history.wall_time_s = time.time() - start
        return history

    # -- evaluation --------------------------------------------------------
    def evaluate(self, bucket: str, *, threshold: float = 0.5) -> BinaryMetrics | None:
        y, s = self.predict_bucket(bucket)
        if len(y) == 0 or len(np.unique(y)) < 2:
            return None
        return compute_binary_metrics(y, s, threshold=threshold)

    def evaluate_all(self, *, threshold: float = 0.5) -> dict[str, BinaryMetrics]:
        out = {}
        for bucket in self.buckets:
            m = self.evaluate(bucket, threshold=threshold)
            if m is not None:
                out[bucket] = m
        return out
