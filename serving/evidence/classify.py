"""One status per pair, chosen by explicit precedence — never by blending.

The status names the *strongest kind of documentation found*; it is not a
severity, and it does not merge what sources say. Records keep their own words
underneath it.

    label contraindication section  >  label warning / interaction section
    >  database record  >  (records that contradict each other)
    >  model-only research signal  >  nothing documented found

"Nothing documented found" is worded as exactly that. It is never "safe".
"""

from __future__ import annotations

from .model_context import MODEL_SIGNAL_THRESHOLD
from .schema import Bi, Conflict, EvidenceCategory, EvidenceRecord, EvidenceStatus, ModelBlock

STATUS_LABEL: dict[EvidenceStatus, Bi] = {
    EvidenceStatus.CONTRAINDICATION_IN_LABEL: Bi(
        ru="Упоминается в разделе «Противопоказания» официальной инструкции",
        en="Named in the Contraindications section of an official label"),
    EvidenceStatus.WARNING_IN_LABEL: Bi(
        ru="Упоминается в предупреждениях или разделе о взаимодействиях официальной инструкции",
        en="Named in the warnings or drug-interactions section of an official label"),
    EvidenceStatus.DOCUMENTED_NO_SEVERITY: Bi(
        ru="Взаимодействие задокументировано в базе данных или справочном наборе; степень тяжести в отчёте не указывается",
        en="Interaction documented in a database or reference set; no severity grade is shown in this report"),
    EvidenceStatus.CONFLICTING_EVIDENCE: Bi(
        ru="Записи источника противоречат друг другу",
        en="Source records contradict each other"),
    EvidenceStatus.MODEL_SIGNAL_ONLY: Bi(
        ru="Задокументированных данных не найдено; есть только сигнал исследовательской модели",
        en="No documentation found; only a research-model signal"),
    EvidenceStatus.NO_DOCUMENTED_EVIDENCE_FOUND: Bi(
        ru="В проверенных источниках взаимодействие не найдено. Это не означает, что сочетание безопасно",
        en="No interaction found in the sources checked. This does not mean the combination is safe"),
}

WARNING_CATEGORIES = {EvidenceCategory.LABEL_BOXED_WARNING, EvidenceCategory.LABEL_WARNING_OR_INTERACTION}


def classify(evidence: list[EvidenceRecord], conflicts: list[Conflict], model: ModelBlock) -> EvidenceStatus:
    cats = {e.category for e in evidence}
    if EvidenceCategory.LABEL_CONTRAINDICATION in cats:
        return EvidenceStatus.CONTRAINDICATION_IN_LABEL
    if cats & WARNING_CATEGORIES:
        return EvidenceStatus.WARNING_IN_LABEL
    if cats & {EvidenceCategory.DATABASE_INTERACTION_RECORD, EvidenceCategory.REFERENCE_SET_OUTCOME}:
        return EvidenceStatus.CONFLICTING_EVIDENCE if conflicts else EvidenceStatus.DOCUMENTED_NO_SEVERITY
    if (model.available and not model.abstain and model.calibrated_model_score is not None
            and model.calibrated_model_score >= MODEL_SIGNAL_THRESHOLD):
        return EvidenceStatus.MODEL_SIGNAL_ONLY
    return EvidenceStatus.NO_DOCUMENTED_EVIDENCE_FOUND
