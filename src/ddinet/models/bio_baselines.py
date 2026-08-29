"""
Non-GNN biological baselines: the two models BIO-GINE has to beat.

WHY THESE EXIST BEFORE THE GNN DOES
------------------------------------
Phase A-2 produced a result this project takes seriously: on the honest splits
the ladder runs *downhill* with sophistication. Degree-only 0.549, random forest
on ECFP4 0.763, GINE 0.754, dual GINE+DDI-net 0.730. The random forest beat both
neural models. Any V2 claim of the form "biology helps" therefore has to be
stated against a random forest given the same biology, or it is not a claim
about biology at all - it is a claim about having more parameters.

Two baselines, both preregistered (docs/V2_PREREGISTRATION.md, H-V2-4 and
section 11 item 6):

**CONTROL A - biological-degree RF.** Eight scalar counts per drug and nothing
else: how many targets, enzymes, transporters, carriers, distinct proteins,
pathways, adverse events, ChEMBL proteins. No protein identity whatsoever. This
is the null model for *biological popularity*, and it is the direct analogue of
Phase A-2's degree-only baseline, which is the model that made the leakage
result legible. Spearman correlation between DDI degree and these counts reaches
0.443, so the null is not a straw man.

If BIO-GINE does not clearly exceed this, the honest conclusion is that the
biological encoder learned to count annotations. Falsification criterion F3.

**BIO-RF.** The same eight counts, plus protein and pathway *membership*
compressed by SVD, plus the ECFP4 block Phase A-2's winning baseline used. This
is the strong version: everything BIO-GINE is given, in a form a forest can eat.
If it matches BIO-GINE, the DeepSets encoder is an expensive reimplementation of
a feature vector.

Neither is a formality. Both are set up to win, because a control designed to
lose measures nothing.

WHERE THE LEAKAGE BOUNDARY SITS
--------------------------------
Drug-level biological annotation is available for a held-out drug - that is V2's
inductive premise, and ``integration/biograph.py`` states the same rule. What is
not available is anything *fitted* on drugs outside the training split.

So the SVD is fitted on training-drug rows only, and the training drug list is a
constructor argument rather than something inferred from the batch handed to
``fit``. That makes the boundary visible at the call site: a reader can see which
drugs the transform saw without tracing where the batch came from. Fitting the
SVD on all 1,705 drugs would leak the held-out drugs' annotation *co-occurrence
structure* into the basis, which is a subtle enough leak to survive review and
large enough to matter, given that the biological vocabulary is 2,893 proteins
over 1,705 drugs.

Counts are not fitted on anything - a count is a property of one drug - so they
cross the boundary without a transform.

STATED DEVIATIONS FROM THE PLAN TEXT
-------------------------------------
1. ``log1p`` on the counts before the pair terms are formed. The plan says
   "difference, product, sum" without specifying a scale. Counts span 0 to
   >1,000 with a heavy right tail, and a random forest's split thresholds are
   invariant to a monotone transform of a single feature but NOT to one applied
   before a product: ``a*b`` and ``log1p(a)*log1p(b)`` order pairs differently.
   log1p matches what Phase A-2's degree-only baseline does with DDI degree, so
   the two null models are on the same footing. ``log_counts=False`` restores
   the literal reading.

2. The ECFP4 block is optional and off by default in ``BioRF``. The plan
   specifies "~3 x (7 + 128 + 64 + ECFP4_dim)" features. With the Phase A-2
   encoding that is 4,096 sparse fingerprint columns beside 600 dense
   biological ones. Memory is not the objection - measured, the pair matrix for
   380k training pairs is 1.70 GiB without the block and 2.01 GiB with it, and
   ``estimate_memory`` reports both before anything is allocated. The objection
   is dilution: with ``max_features='sqrt'`` the forest samples ~69 of 4,696
   columns per split, of which ~87% are fingerprint columns, so the biological
   features - the entire point of the model - are examined at a rate set by how
   many fingerprint bits happen to sit beside them. A biological baseline whose
   sensitivity to biology depends on the fingerprint width is not measuring what
   H-V2-4 asks. ``use_fingerprints=True`` builds the literal version for the
   appendix; the default is the one the hypothesis is read from.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import sparse
from sklearn.decomposition import TruncatedSVD
from sklearn.ensemble import RandomForestClassifier

from ..data.biology import COUNT_FEATURES, BiologyBundle
from .classical import ClassicalModel, PairBatch


def _pair_terms(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """The three commutative pair terms: |a-b|, a*b, a+b.

    Commutative by construction, for the same reason the neural decoder's terms
    are: a drug interaction is symmetric, and a baseline that scores (A,B) and
    (B,A) differently would be measuring argument order. Concatenation - which
    much of the published literature uses - is what this project's Phase A
    protocol deliberately does not do.
    """
    return np.hstack([np.abs(left - right), left * right, left + right])


def _multi_hot(bundle: BiologyBundle, kind: str) -> sparse.csr_matrix:
    """Binary drug x vocabulary membership matrix.

    Binary, not a count: a drug annotated against CYP3A4 through both DrugBank
    and two ChEMBL assays is not three times as related to CYP3A4. Multiplicity
    here would be assay volume, i.e. literature attention, which is the
    confound. The counts block carries set size separately and explicitly.
    """
    n = bundle.n_drugs
    if kind == "protein":
        vocab, items = bundle.n_proteins, [x[:, 0] for x in bundle.protein_items]
    elif kind == "pathway":
        vocab, items = bundle.n_pathways, bundle.pathway_items
    else:
        raise ValueError(f"kind must be 'protein' or 'pathway', got {kind!r}")

    rows, cols = [], []
    for i, ids in enumerate(items):
        uniq = np.unique(ids)
        rows.append(np.full(len(uniq), i, dtype=np.int64))
        cols.append(uniq)
    if rows:
        rows_arr = np.concatenate(rows)
        cols_arr = np.concatenate(cols)
    else:
        rows_arr = cols_arr = np.zeros(0, dtype=np.int64)
    data = np.ones(len(rows_arr), dtype=np.float32)
    return sparse.csr_matrix((data, (rows_arr, cols_arr)), shape=(n, vocab))


@dataclass
class BiologicalDrugFeatures:
    """Per-drug dense feature block, plus a record of how it was built."""

    matrix: np.ndarray                      # [n_drugs, dim]
    names: list[str]
    index: dict[str, int]
    fitted_on: int = 0
    notes: dict = field(default_factory=dict)

    def rows_for(self, drugs) -> np.ndarray:
        try:
            idx = np.fromiter((self.index[d] for d in drugs), dtype=np.int64,
                              count=len(drugs))
        except KeyError as exc:
            raise KeyError(
                f"Drug {exc.args[0]!r} has no biological features. Every drug "
                f"in the dataset must be present in the BiologyBundle."
            ) from None
        return self.matrix[idx]


class BiologicalFeaturizer:
    """Builds the per-drug block, with every fitted step confined to train drugs.

    ``fit`` takes the training drug IDs explicitly. It is a hard error to
    transform before fitting: an unfitted SVD would return the raw multi-hot,
    the pair matrix would silently gain 2,893 columns instead of 128, and the
    run would look like an unusually slow success.
    """

    def __init__(
        self,
        bundle: BiologyBundle,
        *,
        use_counts: bool = True,
        protein_components: int = 128,
        pathway_components: int = 64,
        log_counts: bool = True,
        seed: int = 0,
    ) -> None:
        self.bundle = bundle
        self.use_counts = use_counts
        self.protein_components = protein_components
        self.pathway_components = pathway_components
        self.log_counts = log_counts
        self.seed = seed
        self._features: BiologicalDrugFeatures | None = None
        self._svd: dict[str, TruncatedSVD] = {}

    def fit(self, train_drugs) -> "BiologicalFeaturizer":
        train_drugs = list(train_drugs)
        unknown = [d for d in train_drugs if d not in self.bundle.index]
        if unknown:
            raise KeyError(
                f"{len(unknown)} training drugs are absent from the "
                f"BiologyBundle, first: {unknown[0]!r}"
            )
        train_rows = np.array([self.bundle.index[d] for d in train_drugs], dtype=np.int64)

        blocks: list[np.ndarray] = []
        names: list[str] = []
        notes: dict = {"n_train_drugs": len(train_rows)}

        if self.use_counts:
            counts = self.bundle.counts
            blocks.append(np.log1p(counts) if self.log_counts else counts.copy())
            names += [f"{'log1p_' if self.log_counts else ''}{c}" for c in COUNT_FEATURES]

        for kind, k in (("protein", self.protein_components),
                        ("pathway", self.pathway_components)):
            if k <= 0:
                continue
            full = _multi_hot(self.bundle, kind)
            # TruncatedSVD needs n_components strictly below n_features, and a
            # tiny test vocabulary would otherwise raise deep inside sklearn.
            # Clamping is recorded rather than silent: a run whose protein basis
            # is 3-dimensional because the fixture was small must say so.
            k_eff = min(k, max(full.shape[1] - 1, 1))
            if k_eff != k:
                notes[f"{kind}_components_clamped"] = {"requested": k, "used": k_eff}
            svd = TruncatedSVD(n_components=k_eff, random_state=self.seed)
            svd.fit(full[train_rows])            # TRAIN DRUGS ONLY
            self._svd[kind] = svd
            blocks.append(np.asarray(svd.transform(full), dtype=np.float64))
            names += [f"{kind}_svd_{i}" for i in range(k_eff)]
            notes[f"{kind}_explained_variance"] = float(
                svd.explained_variance_ratio_.sum()
            )

        if not blocks:
            raise ValueError("BiologicalFeaturizer produces no features")

        self._features = BiologicalDrugFeatures(
            matrix=np.hstack(blocks),
            names=names,
            index=dict(self.bundle.index),
            fitted_on=len(train_rows),
            notes=notes,
        )
        return self

    @property
    def features(self) -> BiologicalDrugFeatures:
        if self._features is None:
            raise RuntimeError(
                "BiologicalFeaturizer.fit() was never called; the SVD basis "
                "would be undefined and the feature width wrong"
            )
        return self._features

    def transform_pairs(self, drug_a, drug_b) -> np.ndarray:
        f = self.features
        return _pair_terms(f.rows_for(drug_a), f.rows_for(drug_b))

    def pair_feature_names(self) -> list[str]:
        f = self.features
        return (
            [f"absdiff_{n}" for n in f.names]
            + [f"product_{n}" for n in f.names]
            + [f"sum_{n}" for n in f.names]
        )

    def estimate_memory(self, n_pairs: int, *, fingerprint_bits: int = 0,
                        fingerprint_nnz_per_row: int = 110) -> dict:
        """Bytes the pair matrix would occupy, before anything is allocated.

        The dense biological block is ``3 x dim`` float64 columns; the optional
        fingerprint block is sparse and costed at 8 bytes per stored value
        (float32 data + int32 index) using a measured nnz-per-row estimate.
        """
        dim = self.features.matrix.shape[1]
        dense = n_pairs * 3 * dim * 8
        sparse_bytes = 0
        if fingerprint_bits:
            sparse_bytes = n_pairs * fingerprint_nnz_per_row * 8
        return {
            "n_pairs": n_pairs,
            "dense_columns": 3 * dim,
            "dense_bytes": dense,
            "fingerprint_bytes": sparse_bytes,
            "total_gib": (dense + sparse_bytes) / 2**30,
        }


class _BiologicalRF(ClassicalModel):
    """Shared plumbing: featurise from drug names, then a standard forest.

    Hyperparameters follow ``docs/V2_ARCHITECTURE_PLAN.md`` section 6
    (n_estimators=500, max_features='sqrt'). ``max_depth`` is capped for the
    same reason Phase A-2 capped it: an unbounded forest in a high-dimensional
    space memorises individual pairs, and a project measuring memorisation
    should not let its control memorise freely. The cap makes these numbers a
    conservative lower bound, which is the safe direction for a control that
    BIO-GINE must beat - an under-fit control would flatter the GNN.
    """

    def __init__(
        self,
        featurizer: BiologicalFeaturizer,
        train_drugs,
        *,
        n_estimators: int = 500,
        max_depth: int | None = 20,
        min_samples_leaf: int = 5,
        seed: int = 0,
        n_jobs: int = -1,
    ) -> None:
        self.featurizer = featurizer
        self.train_drugs = list(train_drugs)
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.seed = seed
        self.n_jobs = n_jobs
        self.model: RandomForestClassifier | None = None

    def _design(self, batch: PairBatch):
        return self.featurizer.transform_pairs(batch.drug_a, batch.drug_b)

    def fit(self, batch: PairBatch) -> "_BiologicalRF":
        self.featurizer.fit(self.train_drugs)
        X = self._design(batch)
        self.model = RandomForestClassifier(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            min_samples_leaf=self.min_samples_leaf,
            max_features="sqrt",
            class_weight="balanced_subsample",
            random_state=self.seed,
            n_jobs=self.n_jobs,
        ).fit(X, batch.y)
        return self

    def predict_proba(self, batch: PairBatch) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("fit() must be called before predict_proba()")
        return self.model.predict_proba(self._design(batch))[:, 1]

    def describe(self) -> dict:
        out = {
            "name": self.name,
            "n_estimators": self.n_estimators,
            "max_depth": self.max_depth,
            "min_samples_leaf": self.min_samples_leaf,
            "max_features": "sqrt",
            "seed": self.seed,
            "n_train_drugs": len(self.train_drugs),
            "policy": self.featurizer.bundle.policy.name,
            "biology_source": self.featurizer.bundle.source,
        }
        if self.featurizer._features is not None:
            out["n_drug_features"] = int(self.featurizer.features.matrix.shape[1])
            out["n_pair_features"] = 3 * out["n_drug_features"]
            out.update(self.featurizer.features.notes)
        return out


class BiologicalDegreeRF(_BiologicalRF):
    """CONTROL A. Eight scalar counts per drug, no protein identity at all.

    H-V2-4 is the comparison against this model. A BIO-GINE that does not
    exceed it has learned annotation volume, not mechanism, and the
    preregistration says so before the number is known (falsification F3).
    """

    name = "biological_degree_rf"

    @classmethod
    def build(
        cls,
        bundle: BiologyBundle,
        train_drugs,
        *,
        log_counts: bool = True,
        seed: int = 0,
        **kwargs,
    ) -> "BiologicalDegreeRF":
        featurizer = BiologicalFeaturizer(
            bundle,
            use_counts=True,
            protein_components=0,      # identity is exactly what this omits
            pathway_components=0,
            log_counts=log_counts,
            seed=seed,
        )
        return cls(featurizer, train_drugs, seed=seed, **kwargs)


class BioRF(_BiologicalRF):
    """Model 6: counts + SVD-compressed protein and pathway membership.

    Optionally the Phase A-2 ECFP4 pair block as well; see the module docstring
    for why it is off by default and what turning it on costs. When it is on the
    design matrix is sparse, and the fingerprint half is bit-identical to the
    encoding Phase A-2's random forest used, so BIO-RF strictly contains that
    baseline and the difference between them is the biology.
    """

    name = "bio_rf"

    def __init__(self, *args, fingerprints=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        #: A :class:`ddinet.features.pair_encoding.FingerprintMatrix`, or None.
        self.fingerprints = fingerprints

    @classmethod
    def build(
        cls,
        bundle: BiologyBundle,
        train_drugs,
        *,
        protein_components: int = 128,
        pathway_components: int = 64,
        log_counts: bool = True,
        fingerprints=None,
        seed: int = 0,
        **kwargs,
    ) -> "BioRF":
        featurizer = BiologicalFeaturizer(
            bundle,
            use_counts=True,
            protein_components=protein_components,
            pathway_components=pathway_components,
            log_counts=log_counts,
            seed=seed,
        )
        return cls(featurizer, train_drugs, fingerprints=fingerprints, seed=seed, **kwargs)

    def _design(self, batch: PairBatch):
        dense = self.featurizer.transform_pairs(batch.drug_a, batch.drug_b)
        if self.fingerprints is None:
            return dense
        # Imported here rather than at module scope: the fingerprint path is
        # optional, and a baseline that needs only counts should not drag in
        # the RDKit-backed feature stack.
        from ..features.pair_encoding import encode_pairs

        fp = encode_pairs(
            self.fingerprints, batch.drug_a, batch.drug_b, encoding="symmetric"
        )
        return sparse.hstack(
            [sparse.csr_matrix(dense.astype(np.float32)), fp], format="csr"
        )

    def describe(self) -> dict:
        out = super().describe()
        out["use_fingerprints"] = self.fingerprints is not None
        if self.fingerprints is not None:
            out["fingerprint_bits"] = int(self.fingerprints.n_bits)
        return out
