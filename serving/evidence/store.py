"""Load the evidence artifact once and index it for per-request lookups.

Standard library only: the lean runtime image has no pandas. A request is then
a handful of dictionary lookups and set intersections.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .lexicon import DrugLexicon

ROOT = Path(__file__).resolve().parents[2]
#: DDINET_EVIDENCE_ARTIFACT overrides the location (tests, alternative mounts).
ARTIFACT = Path(os.environ.get("DDINET_EVIDENCE_ARTIFACT",
                               ROOT / "runtime" / "evidence" / "evidence_v1.json.gz"))


class EvidenceArtifactError(RuntimeError):
    pass


@dataclass(frozen=True)
class Annotation:
    drug: int
    protein: int
    relation: str
    action: str
    source: str
    known_action: str
    pmids: tuple[str, ...]
    organism: str


class EvidenceStore:
    def __init__(self, payload: dict, sha256: str | None = None) -> None:
        if payload.get("schema_version") != 1:
            raise EvidenceArtifactError(
                f"unsupported evidence artifact schema {payload.get('schema_version')}")
        self.sha256 = sha256
        self.sources: dict = payload["sources"]
        self.lexicon = DrugLexicon(payload["drugs"])
        self.ids = [e.id for e in self.lexicon.entries]
        self.index = {d: i for i, d in enumerate(self.ids)}

        self.ddi_types: dict[int, str] = {int(k): v for k, v in payload["ddi_types"].items()}
        # Unordered pair -> list of ordered (drug1, drug2, type) records.
        self.records: dict[tuple[int, int], list[tuple[int, int, int]]] = defaultdict(list)
        for a, b, y in payload["ddi_records"]:
            self.records[(min(a, b), max(a, b))].append((a, b, y))

        self.proteins: list[dict] = payload["proteins"]
        sources: list[str] = payload["annotation_sources"]
        self.annotations: list[Annotation] = [
            Annotation(drug=d, protein=p, relation=rel, action=act, source=sources[s],
                       known_action=ka, pmids=tuple(x for x in pm.split("|") if x),
                       organism=org)
            for d, p, rel, act, s, ka, pm, org in payload["annotations"]
        ]
        self.by_drug: dict[int, list[Annotation]] = defaultdict(list)
        for an in self.annotations:
            self.by_drug[an.drug].append(an)

        #: Per-type orientation audit (direction.py). Absent only while the
        #: builder is computing it from this very payload.
        self.direction_audit: dict[int, dict] = {
            int(k): v for k, v in payload.get("direction_audit", {}).items()}

        self.pathways: list[dict] = payload["pathways"]
        self.pathway_index = {pw["id"]: i for i, pw in enumerate(self.pathways)}
        self.pathways_of: dict[int, dict[int, str]] = defaultdict(dict)
        for p, w, codes in payload["pathway_membership"]:
            self.pathways_of[p][w] = codes

    # -- construction ---------------------------------------------------------
    @classmethod
    def load(cls, path: Path | None = None) -> "EvidenceStore":
        path = Path(path or ARTIFACT)
        if not path.exists():
            raise EvidenceArtifactError(
                f"evidence artifact missing at {path}. Build it with:\n"
                "  python -m serving.evidence.build")
        blob = path.read_bytes()
        digest = hashlib.sha256(blob).hexdigest()
        meta_path = path.with_name("evidence_v1.meta.json")
        if meta_path.exists():
            expected = json.loads(meta_path.read_text())["sha256"]
            if expected != digest:
                raise EvidenceArtifactError(
                    f"evidence artifact SHA-256 mismatch\n  expected {expected}\n  actual   {digest}")
        return cls(json.loads(gzip.decompress(blob)), sha256=digest)

    # -- queries ----------------------------------------------------------------
    def pair_records(self, a: int, b: int) -> list[tuple[int, int, int]]:
        return sorted(self.records.get((min(a, b), max(a, b)), []))

    def is_documented(self, a: int, b: int) -> bool:
        return (min(a, b), max(a, b)) in self.records

    def annotations_of(self, drug: int) -> list[Annotation]:
        return self.by_drug.get(drug, [])
