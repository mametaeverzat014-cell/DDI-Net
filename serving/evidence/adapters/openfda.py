"""openFDA drug labels: what an official label says about a named partner drug.

QUESTION ANSWERED. "Does the current FDA label of drug A mention drug B in its
boxed warning, contraindications, warnings/precautions or drug interactions
section, and in which words?" Both directions are asked: A's label about B and
B's label about A.

WHAT A MATCH IS. A whole-word, case-insensitive occurrence of the partner's
name in one of those sections. The sentence containing it is returned verbatim,
with the section's name, the label's set ID, version and effective date, and a
DailyMed link built from the set ID.

WHAT IT IS NOT, AND THE QUALIFIERS SAY SO.

* Labels very often speak of classes ("strong CYP3A4 inhibitors",
  "anticoagulants") without naming each member. No class membership is
  inferred here, so the absence of a name match is *not* the absence of a
  label statement.
* A sentence can mention a drug to say that *no* relevant change was seen.
  Such sentences are detected by explicit wording and kept in their own
  category; they never raise the evidence status and are never rendered as
  reassurance.
* The section a sentence sits in is a structural fact of the label. It is not
  converted into a severity grade.

ONE SENTENCE, ONE EXCERPT. Older-format labels keep their "Drug Interactions"
subsection inside PRECAUTIONS, and openFDA also returns that subsection as a
separate `drug_interactions` field, so the same sentence is found twice. Within
one label, a sentence identical to (or contained in, or a near-verbatim copy of)
one already found is not a new excerpt: the section it was found in again is
added to `also_in`. Distinct sentences stay distinct even when they name the same
drugs, and excerpts from different labels are never merged.
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field

from .http import HttpClient

BASE = "https://api.fda.gov/drug/label.json"
SOURCE = "openfda_label"

#: SPL section field -> (display name, category)
SECTIONS: dict[str, tuple[str, str]] = {
    "boxed_warning": ("BOXED WARNING", "label_boxed_warning"),
    "contraindications": ("CONTRAINDICATIONS", "label_contraindication"),
    "warnings_and_cautions": ("WARNINGS AND PRECAUTIONS", "label_warning_or_interaction"),
    "warnings": ("WARNINGS", "label_warning_or_interaction"),
    "precautions": ("PRECAUTIONS", "label_warning_or_interaction"),
    "drug_interactions": ("DRUG INTERACTIONS", "label_warning_or_interaction"),
}

#: Wording that reports an absence of effect. Conservative on purpose: a miss
#: here leaves a sentence in the warning category, which is the safer error.
NO_EFFECT = re.compile(
    r"\b(no clinically (?:significant|relevant|meaningful|important)"
    r"|did not (?:significantly )?(?:affect|alter|change|increase|decrease|influence|interfere with)"
    r"|does not (?:significantly )?(?:affect|alter|change|increase|decrease|influence|interfere with)"
    r"|no (?:statistically )?(?:significant|relevant|meaningful) (?:effects?|changes?|interactions?|differences?)"
    r"|not (?:clinically )?(?:significantly )?(?:altered|affected|changed)"
    # v3 (from DDI Corpus development errors): "had no effect on", "did not
    # result in clinically significant increases"
    r"|(?:had|has|have|there (?:is|was)) no effect on"
    r"|did not (?:result in|produce|cause) (?:a |any )?(?:clinically |statistically )?(?:significant|relevant|meaningful)"
    r"|no dose adjustment)\b",
    re.IGNORECASE,
)

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])")
#: A full stop after these is not a sentence end ("St. John's Wort", "e.g. Drug").
#: Found on real label text: "strong CYP3A4 inducers (for example, carbamazepine,
#: ... and St. John's Wort) may reduce ..." was cut at "St." and lost its outcome.
ABBREVIATION_END = re.compile(r"(?:^|[\s(\[])(?:St|e\.g|i\.e|vs|approx|Dr|Fig|cf|al|Inc|Ltd|ca|incl|No)\.$",
                              re.IGNORECASE)
MAX_EXCERPT = 600
#: When a sentence is longer than MAX_EXCERPT, the excerpt keeps its start and a
#: window around the partner's name, so the quoted text always shows the name
#: it was matched on (and every outcome term extracted from it).
HEAD_CHARS, BEFORE_HIT, AFTER_HIT = 180, 200, 220


def split_sentences(text: str) -> list[str]:
    """Sentences of a section, not split after common abbreviations."""
    out: list[str] = []
    for piece in SENTENCE_SPLIT.split(text):
        if out and ABBREVIATION_END.search(out[-1]):
            out[-1] = f"{out[-1]} {piece}"
        else:
            out.append(piece)
    return out


def excerpt_of(sentence: str, hit: re.Match) -> tuple[str, bool]:
    """The quotable excerpt of a sentence: whole, or its start plus the partner's window."""
    if len(sentence) <= MAX_EXCERPT:
        return sentence, False
    if hit.end() <= MAX_EXCERPT - 40:
        return sentence[:MAX_EXCERPT].rstrip() + "…", True
    lo, hi = max(HEAD_CHARS, hit.start() - BEFORE_HIT), min(len(sentence), hit.end() + AFTER_HIT)
    lo = sentence.find(" ", lo) + 1 if sentence.find(" ", lo) != -1 and sentence.find(" ", lo) < hit.start() else lo
    tail = "" if hi >= len(sentence) else "…"
    return f"{sentence[:HEAD_CHARS].rstrip()} … {sentence[lo:hi].strip()}{tail}", True
MAX_PER_SECTION = 3


@dataclass
class Label:
    set_id: str
    spl_id: str
    version: str
    effective_time: str
    generic_names: list[str]
    brand_names: list[str]
    substance_names: list[str]
    product_type: str
    sections: dict[str, str]
    retrieval_url: str

    @property
    def dailymed_url(self) -> str:
        return f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={self.set_id}"

    @property
    def effective_date(self) -> str:
        t = self.effective_time
        return f"{t[:4]}-{t[4:6]}-{t[6:8]}" if len(t) == 8 and t.isdigit() else t


@dataclass
class Excerpt:
    section_field: str
    section: str
    category: str
    text: str
    truncated: bool
    no_effect_wording: bool
    matched_term: str
    #: Other sections of the same label where the same sentence was found.
    also_in: list[str] = field(default_factory=list)


@dataclass
class LabelLookup:
    owner_query: str
    label: Label | None
    candidates_considered: int = 0
    excerpts: list[Excerpt] = field(default_factory=list)


def _first(x) -> str:
    return str(x[0]) if isinstance(x, list) and x else ""


def _parse(result: dict, url: str) -> Label:
    of = result.get("openfda") or {}
    sections = {}
    for f in SECTIONS:
        v = result.get(f)
        if isinstance(v, list) and v:
            sections[f] = "\n".join(str(t) for t in v)
    return Label(
        set_id=str(result.get("set_id", "")),
        spl_id=str(result.get("id", "")),
        version=str(result.get("version", "")),
        effective_time=str(result.get("effective_time", "")),
        generic_names=[str(x) for x in of.get("generic_name", [])],
        brand_names=[str(x) for x in of.get("brand_name", [])],
        substance_names=[str(x) for x in of.get("substance_name", [])],
        product_type=_first(of.get("product_type")),
        sections=sections,
        retrieval_url=url,
    )


def _norm(sentence: str) -> str:
    """Case, punctuation and spacing removed: the comparable core of a sentence."""
    return re.sub(r"[^0-9a-z]+", " ", sentence.casefold()).strip()


def same_finding(a: str, b: str) -> bool:
    """True when two sentences of ONE label are the same statement.

    Identical after normalisation; or one contained in the other (a heading or
    numbering glued to one copy), with at least 40 characters in common; or a
    near-verbatim copy (word sets 90 % alike and lengths within 10 %). Anything
    else is a different statement, even about the same two drugs.
    """
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    short, long_ = sorted((na, nb), key=len)
    if len(short) >= 40 and short in long_:
        return True
    ta, tb = set(na.split()), set(nb.split())
    jaccard = len(ta & tb) / len(ta | tb)
    return jaccard >= 0.9 and len(short) / len(long_) >= 0.9


def _single_ingredient(label: Label) -> bool:
    return len(label.substance_names) <= 1


class OpenFdaLabelAdapter:
    def __init__(self, http: HttpClient, api_key: str | None = None) -> None:
        self.http = http
        self.api_key = api_key

    def _url(self, search: str, limit: int = 10) -> str:
        q = {"search": search, "limit": str(limit)}
        if self.api_key:
            q["api_key"] = self.api_key
        return BASE + "?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)

    @staticmethod
    def public_url(url: str) -> str:
        """The retrieval URL with any API key removed, safe to return to clients."""
        parts = urllib.parse.urlsplit(url)
        q = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query) if k != "api_key"]
        return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(q, quote_via=urllib.parse.quote)))

    def current_label(self, ingredient: str) -> tuple[Label | None, int]:
        """Most recent single-ingredient human prescription label for an ingredient.

        Falls back to any single-ingredient label, then to any label. Returns
        (label, number of candidate labels seen). Raises SourceUnavailable.
        """
        term = ingredient.strip().lower()
        if not term:
            return None, 0
        url = self._url(f'openfda.generic_name:"{term}"')
        status, data = self.http.get_json(SOURCE, url)
        results = (data or {}).get("results") if status == 200 else None
        if not results:
            url = self._url(f'openfda.substance_name:"{term}"')
            status, data = self.http.get_json(SOURCE, url)
            results = (data or {}).get("results") if status == 200 else None
        if not results:
            return None, 0
        labels = [_parse(r, self.public_url(url)) for r in results if isinstance(r, dict)]
        labels = [lb for lb in labels if lb.set_id]
        ranked = sorted(
            labels,
            key=lambda lb: (
                _single_ingredient(lb),
                lb.product_type == "HUMAN PRESCRIPTION DRUG",
                lb.effective_time,
            ),
            reverse=True,
        )
        return (ranked[0] if ranked else None), len(labels)

    @staticmethod
    def find_mentions(label: Label, terms: list[str]) -> list[Excerpt]:
        out: list[Excerpt] = []
        pats = [(t, re.compile(rf"(?<![\w-]){re.escape(t)}(?![\w-])", re.IGNORECASE))
                for t in sorted({t.strip() for t in terms if len(t.strip()) >= 4}, key=len, reverse=True)]
        if not pats:
            return out
        # label.sections follows SECTIONS order (boxed warning first), so the
        # first copy of a sentence keeps its most prominent section.
        for field_name, text in label.sections.items():
            display, category = SECTIONS[field_name]
            found = 0
            seen: set[str] = set()
            for sentence in split_sentences(re.sub(r"\s+", " ", text)):
                hit, m = next(((t, p.search(sentence)) for t, p in pats if p.search(sentence)), (None, None))
                if not hit or sentence in seen:
                    continue
                seen.add(sentence)
                twin = next((e for e in out if same_finding(e.text.rstrip("…"), sentence)), None)
                if twin is not None:
                    if display != twin.section and display not in twin.also_in:
                        twin.also_in.append(display)
                    continue
                excerpt, truncated = excerpt_of(sentence, m)
                out.append(Excerpt(
                    section_field=field_name, section=display, category=category,
                    text=excerpt, truncated=truncated,
                    no_effect_wording=bool(NO_EFFECT.search(sentence)),
                    matched_term=hit,
                ))
                found += 1
                if found >= MAX_PER_SECTION:
                    break
        return out

    def lookup(self, owner_ingredient: str, partner_terms: list[str]) -> LabelLookup:
        label, n = self.current_label(owner_ingredient)
        res = LabelLookup(owner_query=owner_ingredient, label=label, candidates_considered=n)
        if label:
            res.excerpts = self.find_mentions(label, partner_terms)
        return res
