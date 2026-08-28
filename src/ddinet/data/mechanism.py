"""
Mechanism ontology: from a raw interaction label to a mechanism plus a
confidence in that mapping.

WHY THIS IS A NEW MODULE AND NOT AN EDIT TO drugbank.py
--------------------------------------------------------
``drugbank.py::classify_description`` is the dormant first draft. Audited
against the 86 TDC templates (MECHANISM_ONTOLOGY.md section 6.2) it covers
99.0% of rows, which looks good and is misleading. Three defects:

  1. Y=49 ("The risk or severity of adverse effects can be increased...",
     60 751 rows = 31.7% of the whole corpus) is swallowed by the rule
     ``risk or severity of .+ can be increased`` and labelled `pd_synergy`.
     That mechanism is ASSIGNED, not extracted - the sentence names no
     mechanism at all.
  2. `pk_exposure` mixes confidences: Y=73 (concentration up, carrier unnamed)
     and Y=77 (concentration of ACTIVE METABOLITES up, which does point at
     metabolism) land in one bucket.
  3. The excretion rule expects "excretion of X can be decreased" while TDC
     writes "may decrease the excretion rate of #Drug2". Y=72 (1 825 rows) is
     therefore unclassified even though a rule for it exists - 1 825 of the
     2 010 uncovered rows are this single miss.

The draft is kept as-is (it is written for DrugBank's own XML text, which this
module does not target) and this replaces it for the TDC corpus.

THE FOUR LAYERS
---------------
    RAW_INTERACTION_LABEL   the template string as the source wrote it
    NORMALIZED_STATEMENT    (affected_quantity, direction, carrier, roles)
    MECHANISM_CATEGORY      a node of the ontology
    MAPPING_CONFIDENCE      HIGH / MEDIUM / LOW / AMBIGUOUS

Every layer is kept, none overwrites its input. If a rule turns out to be
wrong, re-labelling does not require re-reading the source.

THE RULE THAT MAKES THIS WORTH DOING
-------------------------------------
`UNSPEC_ADVERSE_RISK` and `PK_EXPOSURE_UNSPEC` are not junk buckets, they are
required categories. Without them we would have to assign a mechanism where the
source states none, and that is inventing data. Nearly a third of this corpus
belongs in the first of them.

Metrics for any mechanism experiment are reported SPLIT BY CONFIDENCE. An
aggregate over all labels is meaningless here: a third of it is AMBIGUOUS.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Confidence(str, Enum):
    """How well the label determines the category. Ordinal, not a weight."""

    #: Quantity, direction and carrier are all named; one reading only.
    HIGH = "HIGH"
    #: Quantity and direction are unambiguous, carrier is not named. The
    #: top-level category is safe, the sub-category is not.
    MEDIUM = "MEDIUM"
    #: The category is inferred from a clinical effect rather than from a
    #: stated mechanism.
    LOW = "LOW"
    #: The label is compatible with several top-level categories and they
    #: cannot be told apart.
    AMBIGUOUS = "AMBIGUOUS"


#: Top-level categories. PK = exposure changed; PD = response changed at the
#: same exposure; UNSPEC = the label expresses no mechanism.
PK = "PK"
PD = "PD"
UNSPEC = "UNSPEC"


@dataclass(frozen=True)
class Mechanism:
    """One classified label. Every layer of the pipeline is retained."""

    raw: str
    category: str                 # e.g. "PK_METABOLISM"
    top_level: str                # PK / PD / UNSPEC
    direction: str                # increased_exposure, reduced_efficacy, ...
    carrier: str                  # named activity or risk; "" when unnamed
    confidence: Confidence

    @property
    def is_mechanistic(self) -> bool:
        """False for labels that state no mechanism.

        The single most important predicate here: any claim of the form
        "the model predicts mechanism" must exclude these rows or report them
        separately.
        """
        return self.top_level != UNSPEC


#: Ordered rules. First match wins, so the specific patterns come first.
#: Each entry: (regex, category, direction, confidence).
#:
#: ORDER MATTERS AND IS LOAD-BEARING. The Y=49 rule must be tried BEFORE the
#: generic "risk or severity of ..." rule, or the corpus's largest class is
#: silently given a mechanism it does not state - defect 1 above.
_RULES: tuple[tuple[str, str, str, Confidence], ...] = (
    # --- the 31.7% that names no mechanism. Must come first. ---------------
    (r"risk or severity of adverse effects can be increased",
     "UNSPEC_ADVERSE_RISK", "increased_risk", Confidence.AMBIGUOUS),

    # --- PK: the carrier is named -----------------------------------------
    (r"metabolism of .+ can be (decreased|reduced)",
     "PK_METABOLISM", "increased_exposure", Confidence.HIGH),
    (r"metabolism of .+ can be increased",
     "PK_METABOLISM", "decreased_exposure", Confidence.HIGH),
    # Active metabolites: the sentence points at metabolism explicitly, so this
    # is HIGH and must be matched before the generic serum-concentration rule.
    (r"serum concentration of the active metabolites",
     "PK_METABOLISM", "increased_exposure", Confidence.HIGH),
    (r"(absorption|bioavailability) of .+ can be (decreased|reduced)",
     "PK_ABSORPTION", "decreased_exposure", Confidence.HIGH),
    (r"(absorption|bioavailability) of .+ can be increased",
     "PK_ABSORPTION", "increased_exposure", Confidence.HIGH),
    (r"cause a (decrease|reduction) in the absorption",
     "PK_ABSORPTION", "decreased_exposure", Confidence.HIGH),
    (r"cause an increase in the absorption",
     "PK_ABSORPTION", "increased_exposure", Confidence.HIGH),
    # Both sentence shapes for excretion. The second is the one the draft
    # missed - defect 3, 1 825 rows.
    (r"(excretion|clearance) (rate )?of .+ can be (decreased|reduced)",
     "PK_EXCRETION", "increased_exposure", Confidence.HIGH),
    (r"(decrease|reduce) the (excretion|clearance) rate of",
     "PK_EXCRETION", "increased_exposure", Confidence.HIGH),
    (r"(excretion|clearance) (rate )?of .+ can be increased",
     "PK_EXCRETION", "decreased_exposure", Confidence.HIGH),
    (r"increase the (excretion|clearance) rate of",
     "PK_EXCRETION", "decreased_exposure", Confidence.HIGH),
    (r"protein binding of .+ can be (decreased|reduced)",
     "PK_PROTEIN_BINDING", "increased_exposure", Confidence.HIGH),

    # --- PK: exposure moved, carrier NOT named ----------------------------
    # MEDIUM, not HIGH: metabolism, transport and excretion would all produce
    # this sentence and the source does not say which.
    (r"serum concentration of .+ can be increased",
     "PK_EXPOSURE_UNSPEC", "increased_exposure", Confidence.MEDIUM),
    (r"serum concentration of .+ can be (decreased|reduced)",
     "PK_EXPOSURE_UNSPEC", "decreased_exposure", Confidence.MEDIUM),

    # --- PD: efficacy ------------------------------------------------------
    (r"therapeutic efficacy of .+ can be (decreased|reduced)",
     "PD_ANTAGONISM", "reduced_efficacy", Confidence.MEDIUM),
    (r"therapeutic efficacy of .+ can be increased",
     "PD_SYNERGY_THERAPEUTIC", "increased_effect", Confidence.MEDIUM),
    (r"decrease effectiveness of .+ as a diagnostic agent",
     "PD_ANTAGONISM", "reduced_efficacy", Confidence.MEDIUM),

    # --- PD: a named clinical risk ----------------------------------------
    (r"risk or severity of .+ can be increased",
     "PD_SYNERGY_TOXIC", "increased_toxicity", Confidence.LOW),
    (r"risk of a hypersensitivity reaction",
     "PD_SYNERGY_TOXIC", "increased_toxicity", Confidence.LOW),

    # --- PD: a named activity ---------------------------------------------
    # LOW: the sentence names a clinical effect, not a mechanism. "increases
    # the hypotensive activities" is equally consistent with a PK cause.
    (r"may increase the .+ activities",
     "PD_SYNERGY_TOXIC", "increased_toxicity", Confidence.LOW),
    (r"may (decrease|reduce) the .+ activities",
     "PD_ANTAGONISM", "reduced_efficacy", Confidence.LOW),
)

#: What the toxicity is, when the label names one. An orthogonal axis: QTc
#: prolongation and CNS depression are the same mechanism aimed at different
#: systems, so the carrier is a field rather than part of the category name.
_CARRIER_PATTERNS = (
    re.compile(r"increase the ([a-z0-9 ,\-()/]+?) activities", re.I),
    re.compile(r"(?:decrease|reduce) the ([a-z0-9 ,\-()/]+?) activities", re.I),
    re.compile(r"risk or severity of ([a-z0-9 ,\-()/]+?) can be increased", re.I),
)

_TOP_LEVEL = {"PK": PK, "PD": PD, "UNSPEC": UNSPEC}


def _carrier(text: str) -> str:
    """The named activity or risk, or '' when the label names none."""
    for pattern in _CARRIER_PATTERNS:
        match = pattern.search(text)
        if match:
            found = match.group(1).strip()
            # "adverse effects" is the absence of a carrier, not a carrier.
            return "" if found in ("adverse effects", "adverse") else found
    return ""


def classify(description: str) -> Mechanism:
    """Map one interaction label onto the ontology.

    Unmatched labels return category ``UNCLASSIFIED`` with AMBIGUOUS
    confidence, and the unclassified RATE must be reported: a rise in it means
    the source changed its templates and the rules need revisiting. It is the
    project's detector for the two versions drifting apart.
    """
    raw = (description or "").strip()
    text = raw.lower()
    if not text:
        return Mechanism(raw, "UNCLASSIFIED", UNSPEC, "unknown", "",
                         Confidence.AMBIGUOUS)

    carrier = _carrier(text)
    for pattern, category, direction, confidence in _RULES:
        if re.search(pattern, text):
            return Mechanism(raw, category, _TOP_LEVEL[category.split("_")[0]],
                             direction, carrier, confidence)
    return Mechanism(raw, "UNCLASSIFIED", UNSPEC, "unknown", carrier,
                     Confidence.AMBIGUOUS)


def coverage_report(labels: list[str], weights: list[int] | None = None) -> dict:
    """Category and confidence distribution over a corpus.

    :param weights: row counts per label, so a template list can be weighted by
        how often each template actually occurs. Without it every distinct
        template counts once, which understates the dominant classes.
    """
    weights = weights or [1] * len(labels)
    if len(weights) != len(labels):
        raise ValueError("labels and weights must be the same length")
    by_category: dict[str, int] = {}
    by_confidence: dict[str, int] = {}
    mechanistic = 0
    total = 0
    for label, weight in zip(labels, weights):
        m = classify(label)
        by_category[m.category] = by_category.get(m.category, 0) + weight
        by_confidence[m.confidence.value] = (
            by_confidence.get(m.confidence.value, 0) + weight)
        mechanistic += weight if m.is_mechanistic else 0
        total += weight
    return {
        "total": total,
        "by_category": dict(sorted(by_category.items(), key=lambda kv: -kv[1])),
        "by_confidence": dict(sorted(by_confidence.items(), key=lambda kv: -kv[1])),
        "mechanistic": mechanistic,
        "mechanistic_fraction": mechanistic / total if total else 0.0,
        "unclassified": by_category.get("UNCLASSIFIED", 0),
        "unclassified_fraction": (by_category.get("UNCLASSIFIED", 0) / total
                                  if total else 0.0),
    }
