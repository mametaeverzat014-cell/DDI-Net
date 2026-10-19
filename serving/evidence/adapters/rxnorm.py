"""RxNorm (NLM RxNav REST): brand names and spellings -> ingredient concepts.

Used for name normalisation only. RxNorm says what a name *is* (e.g. a brand
whose ingredient is warfarin); it says nothing about interactions — NLM retired
the RxNav Drug Interaction API on 2024-01-02.

Endpoints (https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html):
  /REST/rxcui.json?name=<name>&search=2         name -> RxCUI(s), exact or normalised
  /REST/rxcui/<rxcui>/properties.json           concept name and term type (TTY)
  /REST/rxcui/<rxcui>/related.json?tty=IN+PIN   ingredient concepts of a brand/product

RxNorm names follow US usage (USAN): "acetaminophen", "rifampin". The frozen
universe is named by INN ("paracetamol"). Where the two differ, an RxNorm
ingredient will not match by name and is reported as such rather than guessed.
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass

from .http import HttpClient

BASE = "https://rxnav.nlm.nih.gov/REST"
SOURCE = "rxnorm"


@dataclass(frozen=True)
class RxConcept:
    rxcui: str
    name: str
    tty: str


@dataclass(frozen=True)
class RxResolution:
    query: str
    matched: list[RxConcept]
    ingredients: list[RxConcept]

    def as_dict(self) -> dict:
        return {
            "source": "RxNorm (NLM RxNav)",
            "query": self.query,
            "matched_concepts": [c.__dict__ for c in self.matched],
            "ingredients": [c.__dict__ for c in self.ingredients],
            "url": f"https://mor.nlm.nih.gov/RxNav/search?searchBy=String&searchTerm={urllib.parse.quote(self.query)}",
        }


class RxNormAdapter:
    def __init__(self, http: HttpClient) -> None:
        self.http = http

    def _get(self, path: str) -> dict:
        status, data = self.http.get_json(SOURCE, BASE + path)
        return data if status == 200 and isinstance(data, dict) else {}

    def resolve(self, name: str) -> RxResolution | None:
        """None when RxNorm knows no concept by this name. Raises SourceUnavailable."""
        q = urllib.parse.quote(name.strip())
        data = self._get(f"/rxcui.json?name={q}&search=2")
        ids = (data.get("idGroup") or {}).get("rxnormId") or []
        if not ids:
            return None
        matched: list[RxConcept] = []
        ingredients: dict[str, RxConcept] = {}
        for rxcui in ids[:3]:
            props = (self._get(f"/rxcui/{rxcui}/properties.json").get("properties") or {})
            if not props:
                continue
            concept = RxConcept(str(props.get("rxcui", rxcui)), str(props.get("name", "")), str(props.get("tty", "")))
            matched.append(concept)
            if concept.tty in ("IN", "PIN"):
                ingredients[concept.rxcui] = concept
                continue
            related = self._get(f"/rxcui/{rxcui}/related.json?tty=IN+PIN").get("relatedGroup") or {}
            for group in related.get("conceptGroup") or []:
                for cp in group.get("conceptProperties") or []:
                    c = RxConcept(str(cp.get("rxcui", "")), str(cp.get("name", "")), str(cp.get("tty", group.get("tty", ""))))
                    if c.tty == "IN":
                        ingredients[c.rxcui] = c
        return RxResolution(query=name, matched=matched,
                            ingredients=sorted(ingredients.values(), key=lambda c: c.name))
