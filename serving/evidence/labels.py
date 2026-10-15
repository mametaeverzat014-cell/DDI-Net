"""Turn label lookups into evidence records, in both directions of a pair."""

from __future__ import annotations

import datetime as _dt

from .adapters.http import SourceUnavailable
from .adapters.openfda import LabelLookup, OpenFdaLabelAdapter
from .adapters.rxnorm import RxNormAdapter
from .lexicon import DrugEntry
from .schema import EvidenceCategory, EvidenceRecord, SourceCheck

SOURCE_NAME = "FDA drug label (Structured Product Labeling via openFDA)"
LICENSE = "openFDA: public domain (CC0); label text is a US government record"


def _today() -> str:
    return _dt.datetime.now(_dt.timezone.utc).date().isoformat()


class LabelEvidence:
    """Label evidence for a pair; reports source status instead of failing silently."""

    def __init__(self, labels: OpenFdaLabelAdapter | None, rxnorm: RxNormAdapter | None = None) -> None:
        self.labels = labels
        self.rxnorm = rxnorm

    def names_for(self, drug: DrugEntry) -> tuple[list[str], list[str]]:
        """(names to search labels under, names to look for in label text).

        The INN first; RxNorm ingredient names (US usage) when that source answers,
        because FDA labels use US names ("acetaminophen" for INN "paracetamol").
        """
        names = [drug.inn] if drug.inn else []
        if self.rxnorm and drug.inn:
            try:
                rx = self.rxnorm.resolve(drug.inn)
            except SourceUnavailable:
                rx = None
            if rx:
                for c in rx.ingredients:
                    if c.name and c.name.lower() not in (n.lower() for n in names):
                        names.append(c.name)
        return names, names

    def for_pair(self, a: DrugEntry, b: DrugEntry) -> tuple[list[EvidenceRecord], SourceCheck]:
        if self.labels is None:
            return [], SourceCheck(source="openfda_label", status="disabled",
                                   detail="Label source not configured on this deployment.")
        if not a.inn or not b.inn:
            missing = ", ".join(d.id for d in (a, b) if not d.inn)
            return [], SourceCheck(source="openfda_label", status="not_applicable",
                                   detail=f"No INN name for {missing}; labels are searched by name.")
        records: list[EvidenceRecord] = []
        found_labels: list[str] = []
        try:
            names_a, terms_a = self.names_for(a)
            names_b, terms_b = self.names_for(b)
            for owner, owner_names, partner, partner_terms in ((a, names_a, b, terms_b), (b, names_b, a, terms_a)):
                lookup = None
                for n in owner_names:
                    lookup = self.labels.lookup(n, partner_terms)
                    if lookup.label:
                        break
                if lookup and lookup.label:
                    found_labels.append(f"{owner.inn}: set ID {lookup.label.set_id}")
                    records.extend(self._records(owner, partner, lookup))
        except SourceUnavailable as exc:
            return [], SourceCheck(source="openfda_label", status="unavailable", detail=str(exc))
        if not found_labels:
            return [], SourceCheck(source="openfda_label", status="no_match",
                                   detail="No current FDA label found under these names.")
        detail = "; ".join(found_labels)
        return records, SourceCheck(source="openfda_label", status="ok" if records else "no_match",
                                    detail=("Labels checked — " + detail) if records
                                    else f"Labels checked, partner not named in the scanned sections — {detail}. "
                                         "Labels often refer to drug classes, which are not matched.")

    def _records(self, owner: DrugEntry, partner: DrugEntry, lookup: LabelLookup) -> list[EvidenceRecord]:
        lb = lookup.label
        assert lb is not None
        out = []
        for i, ex in enumerate(lookup.excerpts):
            category = (EvidenceCategory.LABEL_MENTION_NO_EFFECT_REPORTED if ex.no_effect_wording
                        else EvidenceCategory(ex.category))
            qualifiers = [
                f"Matched by the name '{ex.matched_term}' in the label of {owner.inn}. The sentence may "
                "concern a different context (another formulation, a class statement, a study condition).",
                "The section is a structural fact of the label; no severity grade is derived from it.",
            ]
            if ex.no_effect_wording:
                qualifiers.append("The sentence reports no relevant effect under the conditions studied. "
                                  "That is not a statement that the combination is safe.")
            if ex.truncated:
                qualifiers.append("Excerpt truncated; the full sentence is in the label.")
            if ex.also_in:
                qualifiers.append(f"The same sentence also appears in the {', '.join(ex.also_in)} section(s) of this "
                                  "label. It is listed once: repeated text in one label is not separate evidence.")
            out.append(EvidenceRecord(
                id=f"label:{lb.set_id}:{ex.section_field}:{i}:{partner.id}",
                category=category,
                source_name=SOURCE_NAME,
                source_version=f"SPL version {lb.version}, effective {lb.effective_date}",
                source_record_id=lb.set_id,
                source_url=lb.dailymed_url,
                retrieval_url=lb.retrieval_url,
                original_identifiers={
                    "spl_set_id": lb.set_id, "spl_id": lb.spl_id,
                    "label_generic_name": ", ".join(lb.generic_names),
                    "label_drug_drugbank_id": owner.id, "mentioned_drug_drugbank_id": partner.id,
                    "matched_term": ex.matched_term,
                },
                statement=ex.text,
                statement_origin="verbatim_excerpt",
                section=ex.section,
                also_in_sections=list(ex.also_in),
                drug1_id=owner.id,
                drug2_id=partner.id,
                retrieved_at=_today(),
                license=LICENSE,
                qualifiers=qualifiers,
            ))
        return out
