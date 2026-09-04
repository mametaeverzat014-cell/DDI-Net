"""Numpy-only scorer over the precomputed artifact.

Same numbers as serving/engine.py, without torch, torch_geometric or rdkit. The
encoders have already run — their output is in the artifact — so a request is
the symmetric pair decoder and nothing else, which numpy does exactly as well.

This is a deployment shape, not a second model. It reads weights the checkpoint
supplied and encodings the frozen encoders produced; tests assert it agrees with
the torch path, so a change in one that is not matched in the other fails.

RSS is ~90 MB against the full pipeline's ~1.15 GiB, which is the difference
between a 512 MB host and a 2 GB one.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "runtime" / "model_assets" / "lean_decoder_v1.npz"

EPSILON = 1e-12  # matches ddinet.eval.calibration


class ArtifactError(RuntimeError):
    pass


@dataclass(frozen=True)
class LeanScore:
    drug_a: str
    drug_b: str
    raw_logit: float
    raw_model_score: float
    calibrated_model_score: float
    biology_available_a: bool
    biology_available_b: bool


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -700, 700)))


def _to_logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), EPSILON, 1 - EPSILON)
    return np.log(p / (1 - p))


class LeanEngine:
    """Loads the artifact once. Scores pairs with three matmuls."""

    def __init__(self, artifact: Path = ARTIFACT, expect_sha256: str | None = None) -> None:
        if not artifact.exists():
            raise ArtifactError(
                f"lean artifact missing at {artifact}. Build it with:\n"
                f"  python -m serving.precompute"
            )
        meta_path = artifact.with_suffix(".json")
        if expect_sha256 is None and meta_path.exists():
            expect_sha256 = json.loads(meta_path.read_text())["sha256"]
        if expect_sha256:
            actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
            if actual != expect_sha256:
                raise ArtifactError(
                    f"lean artifact SHA-256 mismatch\n  expected {expect_sha256}\n"
                    f"  actual   {actual}"
                )
        self.meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}

        z = np.load(artifact, allow_pickle=True)
        self._h = z["h"]
        self._mask = z["mask"]
        self.ordered_ids: list[str] = [str(x) for x in z["drug_ids"]]
        self.index = {d: i for i, d in enumerate(self.ordered_ids)}
        self.temperature = float(z["temperature"])
        self.n_protein_annotations = z["n_protein_annotations"].tolist()
        self.n_distinct_proteins = z["n_distinct_proteins"].tolist()
        self.n_pathways = z["n_pathways"].tolist()
        self.has_protein = [n > 0 for n in self.n_protein_annotations]
        self.has_pathway = [n > 0 for n in self.n_pathways]
        self._w = [z[f"w{i}"] for i in range(3)]
        self._b = [z[f"b{i}"] for i in range(3)]
        # Display metadata, held as a set of ordered index pairs. Deliberately
        # NOT reachable from _decode: the label is never an inference feature.
        self._documented = {
            (int(a), int(b)) for a, b in z["documented_pairs"]
        }

    def is_documented(self, a: str, b: str) -> bool:
        """Retrospective dataset metadata. Never touched during scoring."""
        i, j = self.index[a], self.index[b]
        return (min(i, j), max(i, j)) in self._documented

    # -- the symmetric pair decoder, term for term -------------------------
    def _decode(self, ia: np.ndarray, ib: np.ndarray) -> np.ndarray:
        ha, hb = self._h[ia], self._h[ib]
        ma, mb = self._mask[ia], self._mask[ib]
        # Exactly BioGine.score_pairs: every term commutative, masks reduced by
        # elementwise min/max rather than concatenated, so f(A,B) = f(B,A).
        x = np.concatenate(
            [ha + hb, np.abs(ha - hb), ha * hb,
             np.minimum(ma, mb), np.maximum(ma, mb)],
            axis=-1,
        )
        # Linear -> ReLU -> [Dropout: identity in eval] -> Linear -> ReLU -> Linear
        x = np.maximum(x @ self._w[0].T + self._b[0], 0.0)
        x = np.maximum(x @ self._w[1].T + self._b[1], 0.0)
        return (x @ self._w[2].T + self._b[2]).squeeze(-1)

    def score_many(self, pairs: list[tuple[str, str]]) -> list[LeanScore]:
        for a, b in pairs:
            if a not in self.index:
                raise KeyError(a)
            if b not in self.index:
                raise KeyError(b)
            if a == b:
                raise ValueError(f"{a} paired with itself is not a DDI question")
        ia = np.array([self.index[a] for a, _ in pairs], dtype=np.int64)
        ib = np.array([self.index[b] for _, b in pairs], dtype=np.int64)
        logits = self._decode(ia, ib).astype(np.float64)
        raw = _sigmoid(logits)
        calibrated = _sigmoid(_to_logit(raw) / self.temperature)
        return [
            LeanScore(a, b, float(lg), float(r), float(c),
                      bool(self.has_protein[self.index[a]]),
                      bool(self.has_protein[self.index[b]]))
            for (a, b), lg, r, c in zip(pairs, logits, raw, calibrated)
        ]

    def score(self, a: str, b: str) -> LeanScore:
        return self.score_many([(a, b)])[0]
