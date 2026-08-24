"""
Classical baselines for Phase A: degree-only, logistic regression, random forest.

WHY THE DEGREE-ONLY MODEL IS THE MOST IMPORTANT ONE HERE
---------------------------------------------------------
``DegreeOnlyModel`` uses two numbers per pair: how many training interactions
each of the two drugs has. **No chemistry whatsoever** - no fingerprint, no
structure, not even the drugs' identities beyond their connectivity.

It answers a question every DDI paper should ask and almost none do: *how much
of this task is solvable without looking at the molecules at all?* Whatever it
scores is the floor above which a chemistry-aware model has to rise before its
chemistry can be said to be doing anything.

It is also the instrument that makes the split comparison interpretable. Under
a random pair split both endpoints of a test pair have a known training degree,
so this model can work. Under a drug-level split a test drug's training degree
is zero by construction, so the model degrades to near-chance *structurally*.
If a fingerprint model degrades by a similar amount between the two schemes,
that is evidence its apparent skill was also degree-driven.

Degree is computed from TRAINING positive pairs only. Using the full graph
would leak: it would tell the model how promiscuous the test drugs are.

MODEL CHOICES
-------------
``LogisticRegressionECFP`` - liblinear on sparse pair features. Linear, fast,
and the standard "did you try something simple?" baseline. Regularisation
strength is the one hyperparameter and it matters: on this data C=0.1 both
converges faster and scores better than C=1.0.

``RandomForestECFP`` - strong on sparse binary fingerprints and frequently
competitive with GNNs in warm-start settings. ``min_samples_leaf`` is raised
above the default because a 4096-dimensional sparse space with ~187k rows will
otherwise grow trees that memorise individual pairs.

Both accept ``scipy.sparse`` input directly. A dense pair matrix at this scale
is ~3 GB and ~98% zeros; see ``features.pair_encoding``.

INTERFACE
---------
Models consume a :class:`PairBatch` rather than a bare matrix, because
``DegreeOnlyModel`` needs the drug names and the others need the encoded
features. One interface keeps the experiment runner free of per-model
branching, which is what rule 4 of the project (independent modules) asks for.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Mapping

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression


@dataclass
class PairBatch:
    """One set of labelled pairs: names, labels, and optionally encoded features."""

    drug_a: np.ndarray
    drug_b: np.ndarray
    y: np.ndarray
    X: sparse.csr_matrix | None = None
    setting: np.ndarray | None = None

    def __len__(self) -> int:
        return len(self.y)

    @classmethod
    def from_frame(cls, frame: pd.DataFrame, X: sparse.csr_matrix | None = None) -> "PairBatch":
        return cls(
            drug_a=frame["drug_a"].to_numpy(),
            drug_b=frame["drug_b"].to_numpy(),
            y=frame["label"].to_numpy(),
            X=X,
            setting=frame["setting"].to_numpy() if "setting" in frame else None,
        )


def training_degree(train_positives: pd.DataFrame) -> dict[str, int]:
    """Interaction degree from TRAINING POSITIVE pairs only.

    Note it is the positives, not the assembled dataset: sampled negatives are
    not interactions and counting them would make "degree" mean something else
    entirely, and would vary with the negative-sampling scheme.
    """
    degree: dict[str, int] = {}
    for a, b in zip(train_positives["drug_a"], train_positives["drug_b"]):
        degree[a] = degree.get(a, 0) + 1
        degree[b] = degree.get(b, 0) + 1
    return degree


class ClassicalModel(ABC):
    """Common interface so the runner never branches on model type."""

    name: str = "model"

    @abstractmethod
    def fit(self, batch: PairBatch) -> "ClassicalModel": ...

    @abstractmethod
    def predict_proba(self, batch: PairBatch) -> np.ndarray: ...

    def describe(self) -> dict:
        return {"name": self.name}


class DegreeOnlyModel(ClassicalModel):
    """Two features: the smaller and larger training degree of the pair.

    Using (min, max) rather than (a, b) makes the model symmetric by
    construction - a drug interaction is symmetric, and an order-dependent
    baseline would be measuring the wrong thing.

    ``log1p`` because degree spans 0..913 with a long tail; on the raw scale a
    handful of hubs would dominate the fit.
    """

    name = "degree_only"

    def __init__(self, degree: Mapping[str, int], C: float = 1.0) -> None:
        self.degree = degree
        self.C = C
        self.model: LogisticRegression | None = None

    def _features(self, batch: PairBatch) -> np.ndarray:
        da = np.fromiter((self.degree.get(x, 0) for x in batch.drug_a),
                         dtype=np.float64, count=len(batch))
        db = np.fromiter((self.degree.get(x, 0) for x in batch.drug_b),
                         dtype=np.float64, count=len(batch))
        lo, hi = np.minimum(da, db), np.maximum(da, db)
        return np.column_stack([np.log1p(lo), np.log1p(hi)])

    def fit(self, batch: PairBatch) -> "DegreeOnlyModel":
        X = self._features(batch)
        if len(np.unique(batch.y)) < 2:
            self.model = None
            return self
        self.model = LogisticRegression(
            C=self.C, max_iter=1000, class_weight="balanced"
        ).fit(X, batch.y)
        return self

    def predict_proba(self, batch: PairBatch) -> np.ndarray:
        if self.model is None:
            return np.full(len(batch), 0.5)
        return self.model.predict_proba(self._features(batch))[:, 1]

    def describe(self) -> dict:
        coef = self.model.coef_[0].tolist() if self.model is not None else []
        return {"name": self.name, "C": self.C,
                "coef_log1p_min_degree": coef[0] if coef else None,
                "coef_log1p_max_degree": coef[1] if len(coef) > 1 else None}


class LogisticRegressionECFP(ClassicalModel):
    """L2 logistic regression on sparse pair features."""

    name = "logreg"

    def __init__(self, C: float = 0.1, max_iter: int = 200) -> None:
        self.C = C
        self.max_iter = max_iter
        self.model: LogisticRegression | None = None

    def fit(self, batch: PairBatch) -> "LogisticRegressionECFP":
        if batch.X is None:
            raise ValueError("LogisticRegressionECFP requires encoded features")
        self.model = LogisticRegression(
            C=self.C,
            max_iter=self.max_iter,
            solver="liblinear",       # handles sparse input well at this size
            class_weight="balanced",
        ).fit(batch.X, batch.y)
        return self

    def predict_proba(self, batch: PairBatch) -> np.ndarray:
        return self.model.predict_proba(batch.X)[:, 1]

    def describe(self) -> dict:
        return {"name": self.name, "C": self.C, "max_iter": self.max_iter}


class RandomForestECFP(ClassicalModel):
    """Random forest on sparse pair features."""

    name = "random_forest"

    def __init__(
        self,
        n_estimators: int = 100,
        max_depth: int | None = 20,
        min_samples_leaf: int = 5,
        seed: int = 0,
        n_jobs: int = -1,
    ) -> None:
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.seed = seed
        self.n_jobs = n_jobs
        self.model: RandomForestClassifier | None = None

    def fit(self, batch: PairBatch) -> "RandomForestECFP":
        if batch.X is None:
            raise ValueError("RandomForestECFP requires encoded features")
        self.model = RandomForestClassifier(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            min_samples_leaf=self.min_samples_leaf,
            class_weight="balanced_subsample",
            random_state=self.seed,
            n_jobs=self.n_jobs,
        ).fit(batch.X, batch.y)
        return self

    def predict_proba(self, batch: PairBatch) -> np.ndarray:
        return self.model.predict_proba(batch.X)[:, 1]

    def describe(self) -> dict:
        return {"name": self.name, "n_estimators": self.n_estimators,
                "max_depth": self.max_depth,
                "min_samples_leaf": self.min_samples_leaf}


#: Hyperparameter grids searched on VALIDATION only. Deliberately small: the
#: experiment is about evaluation protocol, not about squeezing the last point
#: out of a baseline, and a large grid on 12 configurations would dominate the
#: compute budget without changing any conclusion.
HYPERPARAMETER_GRIDS: dict[str, list[dict]] = {
    "logreg": [{"C": 0.01}, {"C": 0.1}, {"C": 1.0}],
    "random_forest": [{"max_depth": 10}, {"max_depth": 20}, {"max_depth": 30}],
}

#: ``max_depth=None`` was searched in a first attempt at the grid and won on
#: validation, but cost 6-7 minutes per fit against ~20 seconds at depth 20 -
#: which put the full grid at roughly nine hours. It is excluded on two grounds:
#:
#:   * tractability, stated plainly: the reported random-forest numbers are
#:     therefore a conservative LOWER BOUND, and that caveat belongs in the
#:     write-up rather than being quietly omitted;
#:   * modelling: an unbounded forest over 4,096 sparse dimensions with ~187k
#:     rows grows trees that memorise individual pairs. For a project whose
#:     question is how much apparent performance is memorisation, letting the
#:     baseline memorise freely would muddy the comparison.
#:
#: Depth 30 is kept so the grid still reaches beyond the depth-20 setting and
#: can show whether validation performance is still climbing at the boundary.
RANDOM_FOREST_DEPTH_EXCLUSION_NOTE = (
    "max_depth=None excluded from the search: ~20x slower per fit, and an "
    "unbounded forest in a 4096-dim sparse space memorises individual pairs. "
    "Reported random-forest numbers are a lower bound."
)


def build_model(name: str, params: dict, *, degree: Mapping[str, int] | None = None,
                seed: int = 0) -> ClassicalModel:
    """Construct a model by name. Keeps the runner free of import branching."""
    if name == "degree_only":
        if degree is None:
            raise ValueError("degree_only requires a training-degree mapping")
        return DegreeOnlyModel(degree, **params)
    if name == "logreg":
        return LogisticRegressionECFP(**params)
    if name == "random_forest":
        return RandomForestECFP(seed=seed, **params)
    raise ValueError(f"Unknown model {name!r}")
