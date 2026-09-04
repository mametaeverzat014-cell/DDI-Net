"""Read-only research API for the Analyze page.

    POST /api/analyze   {"drug_a": "DB00331", "drug_b": "DB00682"}

SCOPE. Only the 1,705 drugs of the frozen experimental universe are accepted.
Arbitrary SMILES are refused: the frozen result characterises this universe, and
a score for a molecule outside it would carry none of the evaluation behind it.

THE LABEL RULE (the one that would invalidate everything if broken).
The pair's known DDI label is NEVER an input. The representation is built from
molecular structure and the drug's own biological annotations; ``load_universe``
is followed by ``assert_no_ddi_features``, and no adjacency, degree, or
neighbour set is read at inference. The response DOES report whether the pair is
documented in the frozen dataset, because hiding retrospective metadata helps
nobody — but it arrives in a separate ``dataset_record`` object, is computed
after scoring from a lookup the model never touches, and is labelled as such.

WORDING. Scores are ``research model score`` / ``documented-DDI model score``.
Nothing here is a probability of harm, a clinical risk, or a statement that a
combination is safe or unsafe. The frozen dataset holds documented positive
interactions and sampled unlabelled pairs — not verified clinical outcomes.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from .constants import PROB_TOLERANCE  # noqa: E402

#: Which engine backs this process.
#:   "lean" (default) — numpy over the precomputed artifact, ~34 MiB RSS.
#:   "full"           — the torch pipeline, ~1.15 GiB RSS, re-encodes from the
#:                      checkpoint. Slower and much heavier, kept because it is
#:                      the path the parity test validates and the one that
#:                      regenerates the artifact.
#: Both return the same numbers within the served tolerance; tests assert it.
ENGINE_MODE = os.environ.get("DDINET_ENGINE", "lean").lower()

DISCLAIMER_RU = (
    "Это вычислительный исследовательский прототип. Результат модели не "
    "является медицинской рекомендацией и не предназначен для принятия "
    "клинических решений."
)
DISCLAIMER_EN = (
    "This is a computational research prototype. The model output is not "
    "medical advice and is not validated for clinical decision-making."
)


class AnalyzeRequest(BaseModel):
    drug_a: str = Field(..., min_length=7, max_length=16, examples=["DB00331"])
    drug_b: str = Field(..., min_length=7, max_length=16, examples=["DB00682"])


class DrugInfo(BaseModel):
    """Biological coverage as the MODEL sees it.

    ``n_protein_annotations`` counts (protein, relation, evidence) triples —
    the DeepSets elements actually encoded. ``n_distinct_proteins`` counts
    proteins, which is what the Drug Explorer displays. They differ whenever a
    protein is asserted under more than one relation or evidence type, so both
    are returned rather than one being passed off as the other.
    """

    id: str
    n_protein_annotations: int
    n_distinct_proteins: int
    n_pathways: int
    biology_available: bool
    pathways_available: bool


class DatasetRecord(BaseModel):
    """Retrospective dataset metadata. NOT an input to the model."""

    documented_in_frozen_dataset: bool
    note_en: str = (
        "Recorded dataset label — not used as an inference feature."
    )
    note_ru: str = (
        "Метка из датасета — не используется как признак при инференсе."
    )


class Provenance(BaseModel):
    frozen_tag: str
    frozen_commit: str
    checkpoint_sha256: str
    calibration_source: str
    temperature: float
    parity_tolerance_prob: float


class AnalyzeResponse(BaseModel):
    drug_a: DrugInfo
    drug_b: DrugInfo
    model: str = "BIO-GINE M4"
    checkpoint: str = "bd45f84e3c1b2c33"
    raw_model_score: float
    calibrated_model_score: float
    experimental_context: dict
    dataset_record: DatasetRecord
    provenance: Provenance
    status: Literal["research_prediction"] = "research_prediction"
    disclaimer_ru: str = DISCLAIMER_RU
    disclaimer_en: str = DISCLAIMER_EN


app = FastAPI(
    title="DDI-Net research inference",
    description=(
        "Read-only scoring against the frozen seed-0 BIO-GINE M4 checkpoint. "
        "Research prototype — not validated for clinical decision-making."
    ),
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # read-only, no credentials, no cookies
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_engine = None


def get_engine():
    if _engine is None:
        raise HTTPException(503, "model not loaded")
    return _engine


@app.on_event("startup")
def _startup() -> None:
    """Load once. A request must never pay for the checkpoint or the dataset."""
    global _engine
    if ENGINE_MODE == "full":
        from .engine import FrozenBioGineEngine

        _engine = FrozenBioGineEngine()
    else:
        from .lean import LeanEngine

        _engine = LeanEngine()


@app.get("/api/health")
def health() -> dict:
    if _engine is None:
        return {"status": "loading", "model_available": False}
    out = {
        "status": "ok",
        "model_available": True,
        "engine": ENGINE_MODE,
        "n_drugs": len(_engine.ordered_ids),
        "frozen_tag": _frozen_tag(),
        "checkpoint_sha256": _checkpoint_sha(),
    }
    if ENGINE_MODE == "full":
        out["n_parameters"] = _engine.n_parameters
        out["startup_seconds"] = round(_engine.startup_seconds, 3)
    return out


def _frozen_tag() -> str:
    return (getattr(_engine, "integrity", None).frozen_tag
            if ENGINE_MODE == "full" else _engine.meta["frozen_tag"])


def _checkpoint_sha() -> str:
    return (getattr(_engine, "integrity", None).checkpoint_sha256
            if ENGINE_MODE == "full" else _engine.meta["source_checkpoint_sha256"])


@lru_cache(maxsize=1)
def _frozen_commit() -> str:
    """The lean artifact records its source tag; the commit comes from the manifest."""
    from .integrity import load_manifest

    return load_manifest()["frozen_commit"]


def _documented(engine, a: str, b: str) -> bool:
    """Dataset metadata lookup, on whichever engine backs this process."""
    if hasattr(engine, "is_documented"):
        return engine.is_documented(a, b)
    from ddinet.data.v2_dataset import load_universe

    global _doc_cache
    if _doc_cache is None:
        u = load_universe()
        _doc_cache = {tuple(sorted(p))
                      for p in zip(u.pairs["drug_a"], u.pairs["drug_b"])}
    return tuple(sorted((a, b))) in _doc_cache


_doc_cache: set[tuple[str, str]] | None = None


@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    engine = get_engine()
    a, b = req.drug_a.strip().upper(), req.drug_b.strip().upper()

    if a == b:
        raise HTTPException(
            422, "drug_a and drug_b must differ; a drug paired with itself is "
                 "not a drug-drug interaction question"
        )
    for d in (a, b):
        if d not in engine.index:
            raise HTTPException(
                404,
                f"{d} is not in the frozen 1,705-drug experimental universe. "
                "Scores are only defined for drugs the study evaluated.",
            )

    try:
        s = engine.score(a, b)
    except (KeyError, ValueError) as exc:  # pragma: no cover
        raise HTTPException(422, str(exc)) from exc

    def info(drug: str) -> DrugInfo:
        i = engine.index[drug]
        return DrugInfo(
            id=drug,
            n_protein_annotations=int(engine.n_protein_annotations[i]),
            n_distinct_proteins=int(engine.n_distinct_proteins[i]),
            n_pathways=int(engine.n_pathways[i]),
            biology_available=bool(engine.has_protein[i]),
            pathways_available=bool(engine.has_pathway[i]),
        )

    return AnalyzeResponse(
        drug_a=info(a),
        drug_b=info(b),
        raw_model_score=s.raw_model_score,
        calibrated_model_score=s.calibrated_model_score,
        experimental_context={
            "in_frozen_universe": True,
            "biology_available_a": s.biology_available_a,
            "biology_available_b": s.biology_available_b,
            "evaluation": (
                "Scores come from a model evaluated under drug-disjoint "
                "holdout. They are not clinical predictions."
            ),
        },
        dataset_record=DatasetRecord(
            documented_in_frozen_dataset=_documented(engine, a, b)
        ),
        provenance=Provenance(
            frozen_tag=_frozen_tag(),
            frozen_commit=_frozen_commit(),
            checkpoint_sha256=_checkpoint_sha(),
            calibration_source=(
                engine.temperature_source if ENGINE_MODE == "full"
                else "reports/v2_calibration/m4_temperature_scaling.csv @ "
                     + engine.meta["frozen_tag"]
            ),
            temperature=engine.temperature,
            parity_tolerance_prob=PROB_TOLERANCE,
        ),
    )
