"""Assemble resolution, evidence, mechanism, model context and explanation.

The engine is the only place the three kinds of statement meet, and it keeps
them in separate fields of the report. The model engine (lean or full) is
optional: without it the report is complete except for the score, and says so.
"""

from __future__ import annotations

import datetime as _dt
import os
from itertools import combinations

from .adapters.http import HttpClient, SourceUnavailable
from .adapters.openfda import OpenFdaLabelAdapter
from .adapters.rxnorm import RxNormAdapter
from .classify import STATUS_LABEL, classify
from .explain import build as build_explanation, validate
from .labels import LabelEvidence
from .lexicon import DrugEntry, Resolution
from .mechanism import mechanism_block, mechanism_graph
from .model_context import model_block
from .records import database_evidence
from .schema import (
    Bi, DrugOut, EvidenceCategory, EvidenceStatus, MechanismGraph, MultiPair, MultiReport,
    PairReport, ResolveCandidate, ResolveOut, SourceCheck,
)
from .store import EvidenceStore

MAX_MULTI = 8

DISCLAIMER = Bi(
    ru="Это исследовательский прототип, а не медицинское изделие. Он не заменяет врача или фармацевта и не может сказать, безопасно ли сочетание лекарств для конкретного человека.",
    en="This is a research prototype, not a medical device. It does not replace a doctor or pharmacist and cannot say whether a combination is safe for a particular person.",
)

LIMITATIONS = [
    Bi(ru="Только 1 705 препаратов исследовательского набора данных; международные названия есть у 1 497 из них.",
       en="Only the 1,705 drugs of the research dataset; 1,497 of them have an international name."),
    Bi(ru="Записи DrugBank не содержат степени тяжести и не указывают, на чём основаны. Для многих типов записей порядок препаратов в выгрузке ненадёжен (измерено).",
       en="DrugBank records carry no severity and do not state their basis. For many record types the drug order in the export is unreliable (measured)."),
    Bi(ru="Инструкции ищутся по названию препарата. Утверждения о целых группах препаратов («сильные ингибиторы CYP3A4») не распознаются, поэтому отсутствие совпадения не означает, что в инструкции ничего нет.",
       en="Labels are searched by drug name. Statements about whole drug classes (“strong CYP3A4 inhibitors”) are not recognised, so no match does not mean the label is silent."),
    Bi(ru="Гипотезы о механизме собраны из ролей каждого препарата по отдельности; сила действия и доля участия белка неизвестны.",
       en="Mechanism hypotheses are assembled from each drug's roles separately; strength of effect and the protein's share of the work are unknown."),
    Bi(ru="Оценка BIO-GINE — исследовательский сигнал сходства с задокументированными парами. Это не вероятность вреда.",
       en="The BIO-GINE score is a research signal of resemblance to documented pairs. It is not a probability of harm."),
]

SCOPE_NOTE = Bi(
    ru="Каждая пара рассматривается отдельно. Попарные данные ничего не говорят о том, как ведут себя три и более препарата вместе: такая модель не построена и не проверена.",
    en="Each pair is examined on its own. Pairwise findings say nothing about how three or more drugs behave together: no such model has been built or validated.",
)


class ResolutionFailed(ValueError):
    def __init__(self, results: list[ResolveOut]) -> None:
        super().__init__("could not resolve every drug")
        self.results = results


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def drug_out(e: DrugEntry, query: str | None = None, matched_on: str | None = None) -> DrugOut:
    return DrugOut(id=e.id, inn=e.inn, name_ru=e.inn_ru, groups=e.groups, drug_type=e.drug_type,
                   query=query, matched_on=matched_on)


def _cand(e: DrugEntry) -> ResolveCandidate:
    return ResolveCandidate(id=e.id, inn=e.inn, name_ru=e.inn_ru)


class EvidenceEngine:
    def __init__(self, store: EvidenceStore, model=None, model_unavailable_reason: str | None = None,
                 http: HttpClient | None = None, external: bool | None = None) -> None:
        self.store = store
        self.model = model
        self.model_unavailable_reason = model_unavailable_reason
        if external is None:
            external = os.environ.get("DDINET_EXTERNAL_SOURCES", "on").lower() not in ("off", "0", "false")
        self.http = http or HttpClient(enabled=external)
        self.rxnorm = RxNormAdapter(self.http) if self.http.enabled else None
        self.labels = LabelEvidence(
            OpenFdaLabelAdapter(self.http, os.environ.get("OPENFDA_API_KEY")) if self.http.enabled else None,
            self.rxnorm)

    # -- resolution -------------------------------------------------------------
    def resolve(self, query: str) -> ResolveOut:
        r: Resolution = self.store.lexicon.resolve(query)
        if r.status == "resolved":
            return ResolveOut(query=r.query, status="resolved", drug=drug_out(r.drug, r.query, r.matched_on))
        if r.status == "invalid":
            return ResolveOut(query=r.query, status="invalid", note=r.note)
        local = ResolveOut(query=r.query, status=r.status, note=r.note,
                           candidates=[_cand(e) for e in r.suggestions])
        if self.rxnorm is None or r.query.upper().startswith("DB"):
            return local
        try:
            rx = self.rxnorm.resolve(r.query)
        except SourceUnavailable as exc:
            local.note = (local.note or "") + f" RxNorm could not be consulted ({exc})."
            return local
        if rx is None or not rx.ingredients:
            return local
        mapped = []
        for c in rx.ingredients:
            e, _ = self.store.lexicon.lookup_name(c.name)
            if e and e not in mapped:
                mapped.append(e)
        info = rx.as_dict()
        if len(rx.ingredients) > 1:
            return ResolveOut(query=r.query, status="multiple_ingredients", rxnorm=info,
                              candidates=[_cand(e) for e in mapped],
                              note="RxNorm maps this name to a product with several ingredients. "
                                   "Pairs are analysed per ingredient; choose one.")
        if mapped:
            return ResolveOut(query=r.query, status="resolved", rxnorm=info,
                              drug=drug_out(mapped[0], r.query, "rxnorm_ingredient"))
        return ResolveOut(query=r.query, status="not_in_universe", rxnorm=info,
                          candidates=[_cand(e) for e in r.suggestions],
                          note=f"RxNorm ingredient '{rx.ingredients[0].name}' does not match an INN in the "
                               "1,705-drug research universe (US and international names can differ).")

    def _require(self, queries: list[str]) -> list[DrugEntry]:
        results = [self.resolve(q) for q in queries]
        if any(r.status != "resolved" for r in results):
            raise ResolutionFailed(results)
        return [self.store.lexicon.by_id[r.drug.id] for r in results]

    # -- pieces ---------------------------------------------------------------------
    def _model(self, ea: DrugEntry, eb: DrugEntry, documented: bool):
        has_a, has_b = ea.has_protein_any, eb.has_protein_any
        score, reason = None, self.model_unavailable_reason or "model not loaded"
        reliance = None
        if self.model is not None:
            try:
                score = self.model.score(ea.id, eb.id)
                if getattr(self.model, "has_modality_reliance", False):
                    reliance = self.model.modality_reliance(ea.id, eb.id)
                has_a = bool(self.model.has_protein[self.model.index[ea.id]])
                has_b = bool(self.model.has_protein[self.model.index[eb.id]])
            except (KeyError, ValueError) as exc:     # pragma: no cover - universe mismatch
                score, reason = None, f"model could not score this pair: {exc}"
        return model_block(score=score, split_a=ea.split_seed0, split_b=eb.split_seed0,
                           documented=documented, has_protein_a=has_a, has_protein_b=has_b,
                           unavailable_reason=None if score is not None else reason,
                           reliance=reliance)

    def _evidence(self, ea: DrugEntry, eb: DrugEntry, include_labels: bool):
        db, conflicts = database_evidence(self.store, ea.index, eb.index)
        checks = [SourceCheck(source="drugbank_tdc", status="ok" if db else "no_match",
                              detail=f"{len(db)} record(s) in the local DrugBank export (TDC, retrieved "
                                     f"{self.store.sources['tdc_drugbank']['retrieved']}).")]
        labels = []
        if include_labels:
            labels, chk = self.labels.for_pair(ea, eb)
            checks.append(chk)
        else:
            checks.append(SourceCheck(source="openfda_label", status="disabled",
                                      detail="Not requested for this report."))
        return labels + db, conflicts, checks

    # -- public -------------------------------------------------------------------------
    def report(self, qa: str, qb: str, include_labels: bool = True) -> PairReport:
        ea, eb = self._require([qa, qb])
        if ea.id == eb.id:
            raise ValueError("drug_a and drug_b resolve to the same drug; a drug paired with itself "
                             "is not a drug-drug interaction question")
        evidence, conflicts, checks = self._evidence(ea, eb, include_labels)
        mech = mechanism_block(self.store, ea.index, eb.index)
        model = self._model(ea, eb, self.store.is_documented(ea.index, eb.index))
        status = classify(evidence, conflicts, model)
        explanation = build_explanation(self.store, ea.id, eb.id, evidence, conflicts, mech, model, checks, status)
        validate(explanation, evidence, mech, model)
        return PairReport(
            drug_a=drug_out(ea, qa), drug_b=drug_out(eb, qb),
            evidence_status=status, evidence_status_label=STATUS_LABEL[status],
            evidence=evidence, conflicts=conflicts, mechanism=mech, model=model,
            explanation=explanation, sources_checked=checks, limitations=LIMITATIONS,
            disclaimer=DISCLAIMER, generated_at=_now(),
        )

    def graph(self, qa: str, qb: str) -> MechanismGraph:
        ea, eb = self._require([qa, qb])
        if ea.id == eb.id:
            raise ValueError("drug_a and drug_b resolve to the same drug")
        return mechanism_graph(self.store, ea.index, eb.index)

    def multi(self, queries: list[str], include_labels: bool = True) -> MultiReport:
        if not 2 <= len(queries) <= MAX_MULTI:
            raise ValueError(f"between 2 and {MAX_MULTI} drugs are accepted")
        entries = self._require(queries)
        uniq: list[DrugEntry] = []
        for e in entries:
            if e not in uniq:
                uniq.append(e)
        if len(uniq) < 2:
            raise ValueError("at least two different drugs are needed")
        pairs: list[MultiPair] = []
        label_checks: list[SourceCheck] = []
        for ea, eb in combinations(uniq, 2):
            evidence, conflicts, checks = self._evidence(ea, eb, include_labels)
            label_checks.extend(c for c in checks if c.source == "openfda_label")
            mech = mechanism_block(self.store, ea.index, eb.index)
            model = self._model(ea, eb, self.store.is_documented(ea.index, eb.index))
            status = classify(evidence, conflicts, model)
            pk = [f for f in mech.findings if f.pattern in ("inhibitor_substrate", "inducer_substrate")]
            reasons = []
            if status in (EvidenceStatus.CONTRAINDICATION_IN_LABEL, EvidenceStatus.WARNING_IN_LABEL,
                          EvidenceStatus.DOCUMENTED_NO_SEVERITY, EvidenceStatus.CONFLICTING_EVIDENCE):
                reasons.append(f"documented:{status.value}")
            if status == EvidenceStatus.MODEL_SIGNAL_ONLY:
                reasons.append("model_signal_without_documentation")
            if pk:
                reasons.append("pharmacokinetic_mechanism_hypothesis")
            if not (model.biology_available_a and model.biology_available_b):
                reasons.append("low_annotation_coverage")
            pairs.append(MultiPair(
                drug_a=ea.id, drug_b=eb.id, evidence_status=status,
                n_database_records=sum(e.category == EvidenceCategory.DATABASE_INTERACTION_RECORD for e in evidence),
                n_label_records=sum(e.category != EvidenceCategory.DATABASE_INTERACTION_RECORD for e in evidence),
                n_mechanism_hypotheses=sum(f.pattern != "shared_annotation" for f in mech.findings),
                calibrated_model_score=None if model.abstain else model.calibrated_model_score,
                regime=model.regime, training_label_seen=model.training_label_seen,
                needs_review=any(r != "low_annotation_coverage" for r in reasons),
                review_reasons=reasons,
            ))
        checks = [SourceCheck(source="drugbank_tdc", status="ok", detail="Local DrugBank export (TDC).")]
        if include_labels:
            worst = next((c for c in label_checks if c.status == "unavailable"), None) or \
                next((c for c in label_checks if c.status == "disabled"), None)
            checks.append(worst or SourceCheck(source="openfda_label", status="ok",
                                               detail="Labels consulted for every pair with named drugs."))
        return MultiReport(drugs=[drug_out(e) for e in uniq], pairs=pairs, sources_checked=checks,
                           scope_note=SCOPE_NOTE, disclaimer=DISCLAIMER, generated_at=_now())

    def sources(self) -> dict:
        return {
            "evidence_artifact_sha256": self.store.sha256,
            "external_sources_enabled": self.http.enabled,
            "sources": self.store.sources,
            "model_loaded": self.model is not None,
            "direction_audit": {str(k): v for k, v in self.store.direction_audit.items()},
        }
