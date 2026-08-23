"""
Baselines. The GNN is only interesting relative to these.

WHY EACH BASELINE IS HERE
-------------------------
A baseline is not a formality; each one tests a specific "maybe the model isn't
doing anything clever" hypothesis. If you cannot beat a baseline, that baseline
*is* your finding.

``PrevalenceBaseline``
    Constant prediction. The absolute floor. Its AUPRC equals the prevalence, so
    it also tells you what number an AUPRC has to beat to mean anything.

``DegreeBaseline``  <-- the most diagnostic one
    Scores a pair using ONLY how many training interactions each drug has, with
    no chemistry whatsoever. If this scores well, your task is substantially
    "guess which drugs are promiscuous" and any fancy model is mostly
    rediscovering hub structure. Reporting it is the strongest evidence that
    your headline number is not degree memorisation - and it is the baseline
    almost no DDI paper includes.

``SimilarityBaseline``
    Chemical nearest-neighbour: "predict A-B interacts if A is structurally
    similar to drugs that interact with B, and vice versa". This is the classic
    non-parametric approach and is genuinely strong. If a GNN cannot beat
    Tanimoto similarity plus a lookup table, the graph machinery is not paying
    for itself.

``RulesBaseline``
    Fires when a mechanistic pathway edge exists (CYP inhibitor-substrate, etc).
    This is the domain-expert baseline: what a pharmacologist would say without
    any machine learning.

``LogisticRegressionBaseline`` / ``RandomForestBaseline``
    Standard ML on symmetric pair fingerprints. These are what a reviewer means
    by "did you try something simpler?". Random forests are particularly strong
    on sparse binary fingerprints, and on warm-start (S1) they are often
    genuinely competitive with GNNs - which is worth knowing and saying.

FAIRNESS RULES ENFORCED THROUGHOUT
-----------------------------------
Every baseline sees exactly the same information as the GNN:
  * fitted on the training bucket only;
  * "known interactions" means training-bucket interactions only;
  * symmetric pair features, so no baseline can exploit argument order;
  * evaluated on the identical buckets with identical metrics.

A baseline that is quietly handicapped makes the model look good and the
comparison worthless.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from ..features.ddi_graph import PATHWAY_EDGE_TYPES, derive_pathway_edges
from ..features.fingerprints import pair_features


class Baseline(ABC):
    """Common interface so the evaluation harness can treat all models alike."""

    name: str = "baseline"

    @abstractmethod
    def fit(self, train: pd.DataFrame, context: "BaselineContext") -> "Baseline": ...

    @abstractmethod
    def predict_proba(self, pairs: pd.DataFrame, context: "BaselineContext") -> np.ndarray: ...


class BaselineContext:
    """Everything a baseline may look at, and nothing it may not.

    Deliberately built from the training bucket alone. Passing this object
    around (instead of loose globals) makes it structurally hard to leak
    evaluation information into a baseline by accident.
    """

    def __init__(
        self,
        drugs: pd.DataFrame,
        fingerprints: dict[str, np.ndarray],
        train_pairs: pd.DataFrame,
    ) -> None:
        self.drugs = drugs
        self.fingerprints = fingerprints
        self.train_pairs = train_pairs

        self.train_edges: set[tuple[str, str]] = set()
        self.neighbours: dict[str, set[str]] = defaultdict(set)
        self.degree: dict[str, int] = defaultdict(int)
        for a, b in zip(train_pairs["drug_a"], train_pairs["drug_b"]):
            key = (a, b) if a < b else (b, a)
            self.train_edges.add(key)
            self.neighbours[a].add(b)
            self.neighbours[b].add(a)
            self.degree[a] += 1
            self.degree[b] += 1

        self._pathway = derive_pathway_edges(drugs)

    def fingerprint(self, name: str) -> np.ndarray:
        dim = len(next(iter(self.fingerprints.values())))
        return self.fingerprints.get(name, np.zeros(dim, dtype=np.float32))

    def pathway_edges(self, edge_type: str) -> set[tuple[str, str]]:
        return self._pathway.get(edge_type, set())

    def pair_matrix(self, pairs: pd.DataFrame, mode: str = "symmetric") -> np.ndarray:
        return np.vstack(
            [
                pair_features(self.fingerprint(a), self.fingerprint(b), mode)
                for a, b in zip(pairs["drug_a"], pairs["drug_b"])
            ]
        )


# --------------------------------------------------------------------------

class PrevalenceBaseline(Baseline):
    """Constant prediction = training prevalence. The floor."""

    name = "prevalence"

    def fit(self, train, context):
        self.p = float(train["label"].mean()) if len(train) else 0.5
        return self

    def predict_proba(self, pairs, context):
        return np.full(len(pairs), self.p, dtype=float)


class DegreeBaseline(Baseline):
    """Uses ONLY training-interaction degree. No chemistry at all.

    This is the shortcut detector. A high score here means the dataset is
    substantially solvable by "which drugs are promiscuous", and any model's
    apparent skill has to be discounted accordingly.

    Note it is structurally near-useless in S3 (both drugs unseen, so both
    degrees are 0) - which is itself informative: it shows how much of the S1
    signal was degree.
    """

    name = "degree"

    def fit(self, train, context):
        degrees = np.array(list(context.degree.values()) or [0.0], dtype=float)
        self.max_degree = float(degrees.max()) or 1.0
        return self

    def predict_proba(self, pairs, context):
        out = []
        for a, b in zip(pairs["drug_a"], pairs["drug_b"]):
            da = context.degree.get(a, 0) / self.max_degree
            db = context.degree.get(b, 0) / self.max_degree
            # Geometric mean: a pair is likely only if BOTH drugs are
            # promiscuous, which is the actual shortcut a GNN would learn.
            out.append(float(np.sqrt(da * db)))
        return np.asarray(out)


class SimilarityBaseline(Baseline):
    """Chemical nearest-neighbour over the training interaction graph.

    Score(A, B) = max over B's known training partners P of Tanimoto(A, P),
    symmetrised with the same computed the other way round.

    Reading: "A looks like something B is already known to interact with."
    This is the strongest non-parametric baseline and the one most likely to
    embarrass an under-trained GNN.
    """

    name = "similarity"

    def fit(self, train, context):
        self._binary = {
            name: (fp > 0) for name, fp in context.fingerprints.items()
        }
        return self

    def _tanimoto(self, a: str, b: str) -> float:
        fa = self._binary.get(a)
        fb = self._binary.get(b)
        if fa is None or fb is None:
            return 0.0
        union = float(np.sum(fa | fb))
        return float(np.sum(fa & fb)) / union if union else 0.0

    def _one_side(self, query: str, other: str, context) -> float:
        partners = context.neighbours.get(other, set())
        # Exclude the query itself: if the pair were in training we would be
        # scoring a known edge, which is not the question.
        sims = [self._tanimoto(query, p) for p in partners if p != query]
        return max(sims) if sims else 0.0

    def predict_proba(self, pairs, context):
        out = []
        for a, b in zip(pairs["drug_a"], pairs["drug_b"]):
            out.append(max(self._one_side(a, b, context), self._one_side(b, a, context)))
        return np.asarray(out, dtype=float)


class RulesBaseline(Baseline):
    """The domain-expert baseline: fire on any mechanistic pathway edge.

    Fits one weight per relation type on the training bucket (a tiny logistic
    regression over 6 binary features), so it is the *best* the rules can do
    rather than an arbitrary OR. Beating an optimally-weighted rule set is a
    much stronger claim than beating an unweighted one.
    """

    name = "rules"

    def __init__(self, edge_types: tuple[str, ...] | None = None) -> None:
        self.edge_types = edge_types or PATHWAY_EDGE_TYPES

    def _features(self, pairs, context) -> np.ndarray:
        keys = [
            (a, b) if a < b else (b, a)
            for a, b in zip(pairs["drug_a"], pairs["drug_b"])
        ]
        return np.column_stack(
            [
                np.array([1.0 if k in context.pathway_edges(t) else 0.0 for k in keys])
                for t in self.edge_types
            ]
        )

    def fit(self, train, context):
        X = self._features(train, context)
        y = train["label"].to_numpy()
        if len(np.unique(y)) < 2:
            self.model = None
            return self
        self.model = LogisticRegression(max_iter=1000, class_weight="balanced")
        self.model.fit(X, y)
        return self

    def predict_proba(self, pairs, context):
        X = self._features(pairs, context)
        if self.model is None:
            return np.full(len(pairs), 0.5)
        return self.model.predict_proba(X)[:, 1]

    def rule_weights(self) -> dict[str, float]:
        """Learned coefficient per relation - directly interpretable."""
        if self.model is None:
            return {}
        return {t: float(w) for t, w in zip(self.edge_types, self.model.coef_[0])}


class LogisticRegressionBaseline(Baseline):
    """L2 logistic regression on symmetric pair fingerprints."""

    name = "logistic_regression"

    def __init__(self, C: float = 1.0, mode: str = "symmetric") -> None:
        self.C = C
        self.mode = mode
        # The encoding is part of the model's identity, so it belongs in the
        # name - otherwise two rows of a results table are indistinguishable.
        self.name = f"logistic_regression[{mode}]"

    def fit(self, train, context):
        X = context.pair_matrix(train, self.mode)
        y = train["label"].to_numpy()
        # Scaling matters: the |a-b| and a*b blocks have very different scales,
        # and unscaled L2 would penalise them unevenly.
        self.scaler = StandardScaler(with_mean=False).fit(X)
        self.model = LogisticRegression(
            C=self.C, max_iter=2000, class_weight="balanced", solver="liblinear"
        )
        self.model.fit(self.scaler.transform(X), y)
        return self

    def predict_proba(self, pairs, context):
        X = self.scaler.transform(context.pair_matrix(pairs, self.mode))
        return self.model.predict_proba(X)[:, 1]


class RandomForestBaseline(Baseline):
    """Random forest on symmetric pair fingerprints.

    Strong on sparse binary features and frequently competitive with GNNs in the
    warm-start setting. Including it is what makes an S2/S3 win meaningful.
    """

    name = "random_forest"

    def __init__(self, n_estimators: int = 300, max_depth: int | None = None,
                 mode: str = "symmetric", seed: int = 0) -> None:
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.mode = mode
        self.seed = seed
        self.name = f"random_forest[{mode}]"

    def fit(self, train, context):
        X = context.pair_matrix(train, self.mode)
        y = train["label"].to_numpy()
        self.model = RandomForestClassifier(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            class_weight="balanced_subsample",
            random_state=self.seed,
            n_jobs=-1,
            min_samples_leaf=2,     # mild regularisation; n is small
        )
        self.model.fit(X, y)
        return self

    def predict_proba(self, pairs, context):
        return self.model.predict_proba(context.pair_matrix(pairs, self.mode))[:, 1]

    def feature_importances(self) -> np.ndarray:
        return self.model.feature_importances_


#: Pair-encoding schemes compared in Phase A.
#:
#:   "concat"     [a; b]           - what most published DDI models use.
#:                                   NOT symmetric: the same pair yields
#:                                   different features depending on argument
#:                                   order, so the model may learn an
#:                                   asymmetric function for a symmetric
#:                                   relation.
#:   "symmetric"  [|a-b|; a*b]     - commutative by construction. |a-b| encodes
#:                                   "present in one but not the other", which
#:                                   is the inhibitor/substrate asymmetry that
#:                                   drives CYP interactions; a*b encodes
#:                                   shared motifs.
#:
#: The GAP BETWEEN THEM IS ITSELF A RESULT for this project's main question: if
#: concatenation scores higher under a leaky split and the advantage vanishes
#: under a drug-level split, part of the published advantage was the model
#: exploiting argument order rather than chemistry.
PAIR_ENCODINGS: tuple[str, ...] = ("concat", "symmetric")


def default_baselines(
    seed: int = 0,
    *,
    pair_encodings: tuple[str, ...] = PAIR_ENCODINGS,
) -> list[Baseline]:
    """The standard suite, ordered from weakest to strongest.

    Feature-based baselines are instantiated once per pair encoding, so both
    schemes are measured on identical folds. Encoding is a PARAMETER, not a
    forked copy of the code - a second copy would drift and the comparison
    would stop being like-for-like.

    Baselines that do not consume pair features (prevalence, degree, rules,
    similarity) are instantiated once; duplicating them per encoding would
    produce identical rows under different names.
    """
    suite: list[Baseline] = [
        PrevalenceBaseline(),
        DegreeBaseline(),
        RulesBaseline(),
        SimilarityBaseline(),
    ]
    for mode in pair_encodings:
        suite.append(LogisticRegressionBaseline(mode=mode))
        suite.append(RandomForestBaseline(mode=mode, seed=seed))
    return suite
