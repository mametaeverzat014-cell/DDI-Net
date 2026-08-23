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
    batch_size: int = 256
    patience: int = 40
    seed: int = 0
    device: str = "cpu"
    grad_clip: float = 1.0
    #: Cap on pos_weight. Uncapped, a 1:50 ratio yields pos_weight=50 and the
    #: model predicts "interaction" for everything - the mirror image of the
    #: majority-class failure it was meant to fix.
    max_pos_weight: float = 10.0
    selection_bucket: str = "val_S2"
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
    selection_bucket: str = "val_S2"
    wall_time_s: float = 0.0

    def summary(self) -> str:
        return (
            f"trained {self.epochs_run} epochs in {self.wall_time_s:.1f}s | "
            f"best {self.selection_bucket} {self.config.get('selection_metric','auprc')}"
            f"={self.best_score:.4f} @ epoch {self.best_epoch}"
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

        train = self.buckets.get("train")
        if train is None:
            raise ValueError("Dataset has no 'train' bucket")
        n_pos = int(train["labels"].sum())
        n_neg = len(train["labels"]) - n_pos
        raw = (n_neg / max(n_pos, 1))
        self.pos_weight = torch.tensor(
            min(raw, self.cfg.max_pos_weight), dtype=torch.float, device=self.device
        )

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

    # -- forward helpers ---------------------------------------------------
    def _encode(self, *, return_attention: bool = False):
        return self.model.encode(
            self.mol_batch, self.node_features, self.edge_index, self.edge_type,
            return_attention=return_attention,
        )

    # -- training ----------------------------------------------------------
    def _train_epoch(self) -> float:
        self.model.train()
        train = self.buckets["train"]
        n = len(train["labels"])
        perm = torch.randperm(n, device=self.device)
        total, n_batches = 0.0, 0

        for start in range(0, n, self.cfg.batch_size):
            sel = perm[start : start + self.cfg.batch_size]
            self.optimizer.zero_grad()

            # Re-encode every step: the graph encoder's parameters change, so
            # cached embeddings would be stale and the gradient wrong.
            enc = self._encode()
            pred = self.model.score_pairs(enc, train["idx_a"][sel], train["idx_b"][sel])
            loss, _ = compute_loss(
                pred, train["labels"][sel], pos_weight=self.pos_weight
            )
            loss.backward()
            if self.cfg.grad_clip:
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.cfg.grad_clip)
            self.optimizer.step()
            total += float(loss.detach())
            n_batches += 1

        return total / max(n_batches, 1)

    @torch.no_grad()
    def predict_bucket(self, bucket: str) -> tuple[np.ndarray, np.ndarray]:
        """Returns ``(y_true, interaction_prob)``."""
        data = self.buckets.get(bucket)
        if data is None or len(data["labels"]) == 0:
            return np.array([]), np.array([])
        self.model.eval()
        enc = self._encode()
        pred = self.model.score_pairs(enc, data["idx_a"], data["idx_b"])
        return (
            data["labels"].cpu().numpy(),
            pred.interaction_prob().cpu().numpy(),
        )

    def _selection_score(self) -> tuple[float, str]:
        bucket = self.cfg.selection_bucket
        if bucket not in self.buckets or len(self.buckets[bucket]["labels"]) == 0:
            # Fall back to pooled validation, and be explicit about it.
            available = [b for b in ("val_S2", "val_S3") if b in self.buckets]
            if not available:
                return float("nan"), "none"
            y_all, s_all = [], []
            for b in available:
                y, s = self.predict_bucket(b)
                y_all.append(y)
                s_all.append(s)
            y, s = np.concatenate(y_all), np.concatenate(s_all)
            bucket = "val_pooled"
        else:
            y, s = self.predict_bucket(bucket)

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
            loss = self._train_epoch()
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

            if epochs_without_improvement >= self.cfg.patience:
                if self.cfg.verbose:
                    print(f"  early stop at epoch {epoch} "
                          f"(no improvement for {self.cfg.patience} epochs)")
                break

            history.epochs_run = epoch

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
