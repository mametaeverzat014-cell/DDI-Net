"""
Turning two molecular fingerprints into one pair feature vector.

WHY SPARSE, NON-NEGOTIABLY
--------------------------
ECFP4 at 2048 bits is ~2.2% dense - the mean drug sets 44 of 2048 bits. A pair
vector is 4096 wide. At ~187,000 training pairs a dense float32 matrix is
**3.07 GB**, which is not workable, and it would be ~98% zeros. The same data
as ``scipy.sparse.csr_matrix`` is ~0.2 GB. Both scikit-learn models used here
accept CSR directly.

The construction is vectorised over the whole pair list rather than built row by
row. For binary fingerprints:

    a AND b  ==  a * b              (elementwise product)
    |a - b|  ==  a XOR b  ==  a + b - 2*(a*b)

so both encodings reduce to a couple of sparse matrix operations on
row-gathered copies of the per-drug fingerprint matrix. Row gathering from CSR
is fast; a Python loop over 187k pairs is not.

THE TWO ENCODINGS, AND WHY BOTH ARE COMPUTED
---------------------------------------------
``concat``      ``[a ; b]``
    What most published DDI work uses. It is **not symmetric**: the same pair
    yields different features depending on argument order, so a model may learn
    an asymmetric function for a relation that is symmetric by definition, and
    the score depends on which drug you typed first.

``symmetric``   ``[|a - b| ; a * b]``
    Commutative by construction. ``|a-b|`` encodes "present in one but not the
    other" - the inhibitor/substrate asymmetry that drives pharmacokinetic
    interactions - while ``a*b`` encodes shared motifs.

Both are produced from one implementation selected by a parameter. The gap
between them, measured with the same model on the same splits, is a result in
its own right for a project asking how much of published DDI performance is an
artefact of evaluation choices.

A NOTE ON WHAT ``concat`` DOES TO A CANONICALLY ORDERED DATASET
----------------------------------------------------------------
Our pairs are stored with ``drug_a < drug_b`` alphabetically. If we encode
``concat`` from that stored order, the ordering is a deterministic function of
the DrugBank accession numbers - and a model can learn from *that*, which is an
artefact of our storage rather than of the published method being reproduced.

``randomise_concat_order`` (default on) shuffles which drug goes first,
independently per pair with a fixed seed. This reproduces the published setting
faithfully - argument order carries no information - while removing an artefact
we would otherwise have introduced ourselves. Turning it off is available for
an ablation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy import sparse

from .fingerprints import MorganFeaturizer

Encoding = Literal["concat", "symmetric"]
ENCODINGS: tuple[Encoding, ...] = ("concat", "symmetric")


@dataclass
class FingerprintMatrix:
    """Per-drug fingerprints in CSR form, plus the name -> row index map."""

    matrix: sparse.csr_matrix
    index: dict[str, int]

    @property
    def n_bits(self) -> int:
        return self.matrix.shape[1]

    def rows_for(self, names) -> np.ndarray:
        """Row indices for a sequence of drug names.

        Raises on an unknown name rather than substituting a zero row: a silent
        zero vector is indistinguishable from a real all-zero fingerprint and
        would quietly corrupt whichever pairs contained it.
        """
        try:
            return np.fromiter((self.index[n] for n in names), dtype=np.int64,
                               count=len(names))
        except KeyError as exc:
            raise KeyError(
                f"Drug {exc.args[0]!r} has no fingerprint. Every drug in the "
                f"dataset must be featurised; check the exclusion step."
            ) from None


def build_fingerprint_matrix(
    names: list[str],
    smiles: list[str],
    *,
    radius: int = 2,
    n_bits: int = 2048,
) -> FingerprintMatrix:
    """ECFP4 for every drug, as one CSR matrix.

    Defaults are radius 2 and 2048 bits - i.e. ECFP4 - because that is what the
    comparable literature uses. Deviating without reason would make the
    baseline numbers harder to compare against published ones.
    """
    featurizer = MorganFeaturizer(radius=radius, n_bits=n_bits)
    rows = [featurizer.featurize_smiles(s).bits for s in smiles]
    matrix = sparse.csr_matrix(np.vstack(rows).astype(np.float32))
    return FingerprintMatrix(matrix, {n: i for i, n in enumerate(names)})


def encode_pairs(
    fingerprints: FingerprintMatrix,
    drug_a,
    drug_b,
    *,
    encoding: Encoding = "symmetric",
    randomise_concat_order: bool = True,
    seed: int = 0,
) -> sparse.csr_matrix:
    """Build the pair feature matrix for a list of pairs.

    Returns a CSR matrix of shape ``(n_pairs, 2 * n_bits)``.
    """
    if encoding not in ENCODINGS:
        raise ValueError(f"Unknown encoding {encoding!r}; expected one of {ENCODINGS}")

    ia = fingerprints.rows_for(drug_a)
    ib = fingerprints.rows_for(drug_b)

    if encoding == "concat":
        if randomise_concat_order:
            # See module docstring: without this, argument order is a
            # deterministic function of the accession numbers we happened to
            # sort by, and the model can learn our storage convention.
            rng = np.random.default_rng(seed)
            flip = rng.random(len(ia)) < 0.5
            ia, ib = np.where(flip, ib, ia), np.where(flip, ia, ib)
        left = fingerprints.matrix[ia]
        right = fingerprints.matrix[ib]
        return sparse.hstack([left, right], format="csr")

    left = fingerprints.matrix[ia]
    right = fingerprints.matrix[ib]
    product = left.multiply(right)                 # a AND b
    difference = left + right - 2 * product        # |a - b| for binary inputs
    return sparse.hstack([difference, product], format="csr")


def encode_dataset(
    fingerprints: FingerprintMatrix,
    dataset,
    *,
    encoding: Encoding = "symmetric",
    randomise_concat_order: bool = True,
    seed: int = 0,
) -> sparse.csr_matrix:
    """Convenience wrapper over a dataset frame with ``drug_a``/``drug_b``."""
    return encode_pairs(
        fingerprints,
        dataset["drug_a"].to_numpy(),
        dataset["drug_b"].to_numpy(),
        encoding=encoding,
        randomise_concat_order=randomise_concat_order,
        seed=seed,
    )
