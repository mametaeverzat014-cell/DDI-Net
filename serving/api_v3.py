"""DDI-Net 3.0 evidence API, mounted beside the frozen /api/analyze endpoint.

    GET  /api/v3/resolve?q=<name or DrugBank ID>
    POST /api/v3/report   {"drug_a": "...", "drug_b": "...", "include_labels": true}
    POST /api/v3/graph    {"drug_a": "...", "drug_b": "..."}
    POST /api/v3/multi    {"drugs": ["...", "..."], "include_labels": true}
    GET  /api/v3/sources

/api/analyze is unchanged; existing clients keep working.

Inputs are drug names or DrugBank IDs only. Nothing about the person asking —
age, conditions, doses — is accepted, stored or logged: the service has no use
for it and would only acquire a duty to protect it.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .evidence.engine import MAX_MULTI, EvidenceEngine, ResolutionFailed
from .evidence.lexicon import ALLOWED_INPUT
from .evidence.schema import MechanismGraph, MultiReport, PairReport, ResolveOut

router = APIRouter(prefix="/api/v3", tags=["DDI-Net 3.0 evidence"])

_engine: EvidenceEngine | None = None
_unavailable: str | None = "evidence engine not started"


def install(engine: EvidenceEngine | None, reason: str | None = None) -> None:
    global _engine, _unavailable
    _engine, _unavailable = engine, reason


def engine() -> EvidenceEngine:
    if _engine is None:
        raise HTTPException(503, f"evidence layer unavailable: {_unavailable}")
    return _engine


def _check(q: str, field: str) -> str:
    q = (q or "").strip()
    if not q or not ALLOWED_INPUT.match(q):
        raise HTTPException(422, f"{field}: expected a drug name or DrugBank ID (letters, digits, "
                                 "spaces and - . , ' ( ) / + only, at most 100 characters)")
    return q


def _unresolved(exc: ResolutionFailed) -> HTTPException:
    return HTTPException(422, {
        "message": "Not every drug could be identified. Nothing was guessed; see the candidates.",
        "resolutions": [r.model_dump() for r in exc.results],
    })


class PairRequest(BaseModel):
    drug_a: str = Field(..., min_length=1, max_length=100, examples=["warfarin"])
    drug_b: str = Field(..., min_length=1, max_length=100, examples=["fluconazole"])
    include_labels: bool = True


class MultiRequest(BaseModel):
    drugs: list[str] = Field(..., min_length=2, max_length=MAX_MULTI)
    include_labels: bool = True


@router.get("/resolve", response_model=ResolveOut)
def resolve(q: str = Query(..., min_length=1, max_length=100)) -> ResolveOut:
    return engine().resolve(_check(q, "q"))


@router.post("/report", response_model=PairReport)
def report(req: PairRequest) -> PairReport:
    e = engine()
    a, b = _check(req.drug_a, "drug_a"), _check(req.drug_b, "drug_b")
    try:
        return e.report(a, b, include_labels=req.include_labels)
    except ResolutionFailed as exc:
        raise _unresolved(exc) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/graph", response_model=MechanismGraph)
def graph(req: PairRequest) -> MechanismGraph:
    e = engine()
    a, b = _check(req.drug_a, "drug_a"), _check(req.drug_b, "drug_b")
    try:
        return e.graph(a, b)
    except ResolutionFailed as exc:
        raise _unresolved(exc) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/multi", response_model=MultiReport)
def multi(req: MultiRequest) -> MultiReport:
    e = engine()
    drugs = [_check(q, f"drugs[{i}]") for i, q in enumerate(req.drugs)]
    try:
        return e.multi(drugs, include_labels=req.include_labels)
    except ResolutionFailed as exc:
        raise _unresolved(exc) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/sources")
def sources() -> dict:
    return engine().sources()
