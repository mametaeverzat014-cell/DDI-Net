"""
Drug-level cross-validation: the honest way to report a number.

WHY CROSS-VALIDATION, AND WHY OVER *DRUGS*
------------------------------------------
A single train/test split gives you one number with no error bar. On a graph of
~100 drugs, that number moves a great deal depending on which drugs happened to
land in test - if warfarin and amiodarone are held out you get a very different
result than if two peripheral compounds are.

So the dominant source of variance here is **which drugs were held out**, not
random weight initialisation. Cross-validating over drug folds measures exactly
that source. Reporting "AUPRC 0.46 +/- 0.07 across 5 drug-disjoint folds" is a
defensible claim; reporting "AUPRC 0.46" from one split is not, and "how do you
know that isn't luck?" is a question judges reliably ask.

PAIRED COMPARISON, NOT TWO SEPARATE AVERAGES
---------------------------------------------
Comparing "model mean 0.46" against "baseline mean 0.47" throws away the fact
that both were evaluated on the *same folds*. Folds differ enormously in
difficulty, and that shared difficulty is common noise. Comparing per-fold
*differences* removes it, which is far more sensitive - a model can win on every
single fold while its mean looks similar, and only the paired view reveals that.

We report the per-fold win count and a Wilcoxon signed-rank test. With 5 folds
the test has very little power (the smallest attainable p-value is 0.0625), so
**treat it as descriptive, not confirmatory** - and say so rather than dressing
up a 5-fold p-value as significance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from ..data.assemble import AssemblyConfig, build_supervised_dataset
from ..data.split import DrugLevelSplit, drug_level_kfold
from ..features.build import FeatureConfig, build_feature_bundle
from .baselines import Baseline, BaselineContext, default_baselines
from .metrics import compute_binary_metrics

#: Metrics carried through to the summary table.
REPORTED_METRICS = (
    "auc_roc", "auprc", "auprc_lift", "balanced_accuracy", "f1", "f2",
    "precision", "recall",
)


@dataclass
class CVResult:
    """Long-format results plus the fold splits, for auditing."""

    rows: pd.DataFrame
    splits: list[DrugLevelSplit] = field(default_factory=list)

    def summary(self, bucket: str = "test_S2") -> pd.DataFrame:
        """Mean +/- SD per model for one bucket."""
        sub = self.rows[self.rows["bucket"] == bucket]
        if sub.empty:
            return pd.DataFrame()
        agg = (
            sub.groupby("model")[list(REPORTED_METRICS)]
            .agg(["mean", "std"])
            .round(3)
        )
        return agg.sort_values(("auprc", "mean"), ascending=False)

    def formatted(self, bucket: str = "test_S2", metric: str = "auprc") -> pd.DataFrame:
        """A ``mean +/- sd`` table that can be pasted straight into a poster."""
        sub = self.rows[self.rows["bucket"] == bucket]
        if sub.empty:
            return pd.DataFrame()
        out = []
        for model, grp in sub.groupby("model"):
            values = grp[metric].dropna()
            out.append(
                {
                    "model": model,
                    "n_folds": len(values),
                    metric: f"{values.mean():.3f} +/- {values.std():.3f}",
                    "_mean": values.mean(),
                }
            )
        return (
            pd.DataFrame(out).sort_values("_mean", ascending=False)
            .drop(columns="_mean").reset_index(drop=True)
        )

    def paired_comparison(
        self, model_a: str, model_b: str, *,
        bucket: str = "test_S2", metric: str = "auprc",
    ) -> dict:
        """Fold-by-fold comparison of two models on identical folds."""
        sub = self.rows[self.rows["bucket"] == bucket]
        a = sub[sub["model"] == model_a].set_index("fold")[metric]
        b = sub[sub["model"] == model_b].set_index("fold")[metric]
        common = sorted(set(a.index) & set(b.index))
        if not common:
            return {"error": "no shared folds"}
        va, vb = a.loc[common].to_numpy(), b.loc[common].to_numpy()
        diff = va - vb
        valid = np.isfinite(diff)
        diff = diff[valid]
        if len(diff) == 0:
            return {"error": "no comparable folds"}

        result = {
            "model_a": model_a,
            "model_b": model_b,
            "metric": metric,
            "bucket": bucket,
            "n_folds": int(len(diff)),
            "mean_a": float(np.nanmean(va[valid])),
            "mean_b": float(np.nanmean(vb[valid])),
            "mean_difference": float(diff.mean()),
            "folds_a_wins": int((diff > 0).sum()),
            "folds_b_wins": int((diff < 0).sum()),
        }
        try:
            from scipy.stats import wilcoxon

            if len(diff) >= 5 and np.any(diff != 0):
                stat, p = wilcoxon(diff)
                result["wilcoxon_p"] = float(p)
                result["note"] = (
                    "With this few folds the test has minimal power "
                    "(min attainable p = 0.0625 at n=5) - descriptive only."
                )
        except Exception:
            pass
        return result


def run_cross_validation(
    drugs: pd.DataFrame,
    pairs: pd.DataFrame,
    *,
    n_folds: int = 5,
    seed: int = 0,
    group_by: str = "drug",
    neg_ratio: float = 3.0,
    dangerous_only: bool = False,
    feature_config: FeatureConfig | None = None,
    baselines: list[Baseline] | None = None,
    gnn_factory: Callable[[dict], tuple] | None = None,
    buckets: tuple[str, ...] = ("test_S2", "test_S3"),
    verbose: bool = True,
) -> CVResult:
    """Run every model across drug-disjoint folds.

    ``gnn_factory`` is a callable receiving a dict of fold context and returning
    ``(name, y_true_by_bucket, y_score_by_bucket)``. Passing it in keeps this
    module free of any torch import, so the baseline-only comparison can run in
    a plain scientific-Python environment.

    Every model in a fold sees the identical split, identical negatives and
    identical features. Anything else makes the comparison meaningless.
    """
    fold_splits = drug_level_kfold(
        drugs, pairs, n_folds=n_folds, seed=seed, group_by=group_by
    )
    all_keys = set(pairs["pair_key"])
    rows: list[dict] = []

    for fold_idx, split in enumerate(fold_splits):
        if verbose:
            print(f"\n--- fold {fold_idx + 1}/{n_folds} "
                  f"(train={len(split.train_drugs)} drugs, "
                  f"test={len(split.test_drugs)} drugs) ---")

        dataset = build_supervised_dataset(
            split, all_keys,
            AssemblyConfig(neg_ratio=neg_ratio, seed=seed + fold_idx,
                           dangerous_only=dangerous_only),
        )
        bundle = build_feature_bundle(drugs, split, feature_config or FeatureConfig())
        fingerprints = {n: bundle.fingerprints[n].bits for n in drugs["name"]}
        context = BaselineContext(drugs, fingerprints, split.buckets["train"])
        train = dataset[dataset["bucket"] == "train"]

        def record(model_name: str, bucket: str, y: np.ndarray, s: np.ndarray) -> None:
            if len(y) == 0 or len(np.unique(y)) < 2:
                return
            m = compute_binary_metrics(y, s)
            rows.append({"fold": fold_idx, "model": model_name, "bucket": bucket,
                         **{k: getattr(m, k) for k in REPORTED_METRICS},
                         "n": m.n, "n_positive": m.n_positive})

        for baseline in (baselines if baselines is not None else default_baselines(seed)):
            baseline.fit(train, context)
            for bucket in buckets:
                sub = dataset[dataset["bucket"] == bucket]
                if len(sub) == 0:
                    continue
                record(baseline.name, bucket,
                       sub["label"].to_numpy(), baseline.predict_proba(sub, context))
            if verbose:
                sub = dataset[dataset["bucket"] == "test_S2"]
                if len(sub) and len(np.unique(sub["label"])) > 1:
                    m = compute_binary_metrics(sub["label"].to_numpy(),
                                               baseline.predict_proba(sub, context))
                    print(f"    {baseline.name:22s} test_S2 AUPRC {m.auprc:.3f} "
                          f"AUC {m.auc_roc:.3f}")

        if gnn_factory is not None:
            name, y_by_bucket, s_by_bucket = gnn_factory(
                {"fold": fold_idx, "split": split, "bundle": bundle,
                 "dataset": dataset, "seed": seed + fold_idx}
            )
            for bucket in buckets:
                if bucket in y_by_bucket:
                    record(name, bucket, y_by_bucket[bucket], s_by_bucket[bucket])
            if verbose and "test_S2" in y_by_bucket:
                m = compute_binary_metrics(y_by_bucket["test_S2"], s_by_bucket["test_S2"])
                print(f"    {name:22s} test_S2 AUPRC {m.auprc:.3f} AUC {m.auc_roc:.3f}")

    return CVResult(pd.DataFrame(rows), fold_splits)


def make_gnn_factory(
    *,
    architecture: str = "gat",
    hidden_dim: int = 128,
    epochs: int = 200,
    patience: int = 50,
    dropout: float = 0.2,
    lr: float = 1e-3,
    use_molecular_branch: bool = True,
    use_graph_branch: bool = True,
    name: str | None = None,
    buckets: tuple[str, ...] = ("test_S2", "test_S3"),
) -> Callable[[dict], tuple]:
    """Build a ``gnn_factory`` for :func:`run_cross_validation`.

    Torch is imported lazily inside the closure so that importing this module
    does not require torch at all.
    """

    def factory(ctx: dict):
        from ..features.molgraph import ATOM_FEATURE_DIM, BOND_FEATURE_DIM
        from ..models.ddinet import DDINet, DDINetConfig
        from ..models.train import Trainer, TrainConfig

        bundle = ctx["bundle"]
        cfg = DDINetConfig(
            atom_dim=ATOM_FEATURE_DIM,
            bond_dim=BOND_FEATURE_DIM,
            node_feature_dim=bundle.node_features.shape[1],
            hidden_dim=hidden_dim,
            dropout=dropout,
            architecture=architecture,
            use_molecular_branch=use_molecular_branch,
            use_graph_branch=use_graph_branch,
        )
        model = DDINet(cfg)
        trainer = Trainer(
            model, bundle, ctx["dataset"],
            TrainConfig(epochs=epochs, patience=patience, lr=lr,
                        seed=ctx["seed"], verbose=False),
        )
        trainer.fit()
        y_by, s_by = {}, {}
        for bucket in buckets:
            y, s = trainer.predict_bucket(bucket)
            if len(y):
                y_by[bucket] = y
                s_by[bucket] = s
        return name or f"DDI-Net[{cfg.ablation_name()}]", y_by, s_by

    return factory
