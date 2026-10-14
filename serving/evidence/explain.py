"""Plain-language explanation of a pair report — deterministic, no language model.

WHY NO LLM. Every sentence below is a template filled from records already in
the report, so each factual statement can carry the IDs of the records it rests
on, and ``validate`` can check that it does. A generative model would add
fluency and lose that guarantee; for medical text the guarantee matters more.

FIVE QUESTIONS, ONE SECTION EACH. What is known (documented sources only). Why
it may happen (hypotheses from documented roles, labelled as hypotheses). What
the AI found (the research score and whether it means anything here). How
certain this is. What is missing.

WHAT THE TEXT NEVER DOES. It never calls a combination safe, never tells anyone
to start, stop, combine or re-dose a medicine, and never turns a model score or
a missing record into a statement about harm. ``validate`` enforces the
vocabulary; tests run it over every report they build.

Russian is the default interface language. Drug names in Russian are the
project's transliterations and are always used with the word "препарат", which
keeps them in the nominative — a transliterated name cannot be declined.
"""

from __future__ import annotations

import re

from .schema import (
    Bi, Conflict, EvidenceCategory, EvidenceRecord, EvidenceStatus, Explanation,
    MechanismBlock, MechanismFinding, ModelBlock, Section, SourceCheck, Statement,
)

TITLES = {
    "known": Bi(ru="Что известно", en="What is known"),
    "why": Bi(ru="Почему это может происходить", en="Why this may happen"),
    "ai": Bi(ru="Что нашла модель", en="What the AI found"),
    "certainty": Bi(ru="Насколько это надёжно", en="How certain is this?"),
    "missing": Bi(ru="Чего мы не знаем", en="What is missing"),
}

SECTION_RU = {
    "BOXED WARNING": "Предупреждение в рамке",
    "CONTRAINDICATIONS": "Противопоказания",
    "WARNINGS AND PRECAUTIONS": "Предупреждения и меры предосторожности",
    "WARNINGS": "Предупреждения",
    "PRECAUTIONS": "Меры предосторожности",
    "DRUG INTERACTIONS": "Лекарственные взаимодействия",
}

SOURCE_LABEL = {
    "drugbank_tdc": Bi(ru="база DrugBank (выгрузка TDC)", en="DrugBank (TDC export)"),
    "openfda_label": Bi(ru="официальные инструкции FDA (openFDA)", en="FDA labels (openFDA)"),
    "rxnorm": Bi(ru="справочник названий RxNorm", en="RxNorm names"),
}

#: Affirmative safety claims and medication instructions. Matched
#: case-insensitively in both languages. A negated disclaimer ("this does not
#: mean the combination is safe") is allowed and is not caught by these.
FORBIDDEN = [
    r"\bsafe to (take|combine|use)\b", r"\bsafe together\b", r"\bcan be taken together\b",
    r"\bno risk\b", r"\byou should\b", r"\bstop taking\b", r"\bstart taking\b",
    r"\b(increase|decrease|reduce|change|adjust) (the|your) dose\b", r"\bdo not take\b",
    r"\bdon't take\b", r"\bwe recommend\b",
    r"\bcan (safely )?(be )?(take|taken|combine|combined|use|used) (both|together|them)\b",
    r"мож(но|ете|ем|ешь) (спокойно |смело |без опасений )?(принимать|сочетать|применять|пить)",
    r"безопасно (принимать|сочетать|применять)", r"(принимайте|пейте|сочетайте)\b",
    r"прекратите", r"начните принимать", r"(измените|снизьте|увеличьте|уменьшите) дозу",
    r"не принимайте", r"следует принимать", r"рекомендуем", r"риска нет",
]
_FORBIDDEN = [re.compile(p, re.IGNORECASE) for p in FORBIDDEN]

MAX_LISTED = 4


class ExplanationError(AssertionError):
    pass


def _plural_ru(n: int, forms: tuple[str, str, str]) -> str:
    m10, m100 = n % 10, n % 100
    if m10 == 1 and m100 != 11:
        return forms[0]
    if 2 <= m10 <= 4 and not 12 <= m100 <= 14:
        return forms[1]
    return forms[2]


class Names:
    def __init__(self, store) -> None:
        self.store = store

    def ru(self, drug_id: str) -> str:
        return self.store.lexicon.by_id[drug_id].display("ru")

    def en(self, drug_id: str) -> str:
        return self.store.lexicon.by_id[drug_id].display("en")


# --------------------------------------------------------------- known ------
def _known(n: Names, a: str, b: str, evidence: list[EvidenceRecord], conflicts: list[Conflict],
           checks: list[SourceCheck]) -> list[Statement]:
    out: list[Statement] = []
    labels = [e for e in evidence if e.category in (
        EvidenceCategory.LABEL_CONTRAINDICATION, EvidenceCategory.LABEL_BOXED_WARNING,
        EvidenceCategory.LABEL_WARNING_OR_INTERACTION)]
    no_effect = [e for e in evidence if e.category == EvidenceCategory.LABEL_MENTION_NO_EFFECT_REPORTED]
    db = [e for e in evidence if e.category == EvidenceCategory.DATABASE_INTERACTION_RECORD]

    for e in labels[:MAX_LISTED]:
        sec_ru = SECTION_RU.get(e.section or "", e.section or "")
        out.append(Statement(kind="documented", refs=[e.id], text=Bi(
            ru=f"В официальной инструкции к препарату {n.ru(e.drug1_id)} (раздел «{sec_ru}») упоминается препарат {n.ru(e.drug2_id)}. Цитата на английском — в карточке источника.",
            en=f"The official label of {n.en(e.drug1_id)} names {n.en(e.drug2_id)} in its {(e.section or '').title()} section. The quotation is in the source card.",
        )))
    if len(labels) > MAX_LISTED:
        rest = labels[MAX_LISTED:]
        out.append(Statement(kind="documented", refs=[e.id for e in rest], text=Bi(
            ru=f"Ещё {len(rest)} {_plural_ru(len(rest), ('фрагмент', 'фрагмента', 'фрагментов'))} инструкций — в списке источников.",
            en=f"{len(rest)} more label excerpt(s) are in the source list.")))
    for e in no_effect[:2]:
        out.append(Statement(kind="documented", refs=[e.id], text=Bi(
            ru=f"В инструкции к препарату {n.ru(e.drug1_id)} есть фрагмент о препарате {n.ru(e.drug2_id)}, где сообщается, что в изученных условиях заметного эффекта не наблюдали. Это описание конкретных условий исследования, а не гарантия безопасности.",
            en=f"The label of {n.en(e.drug1_id)} has an excerpt about {n.en(e.drug2_id)} reporting no notable effect under the conditions studied. That describes a study's conditions; it is not a guarantee of safety.",
        )))

    for e in db[:MAX_LISTED]:
        ru = e.statement_ru or e.statement
        out.append(Statement(kind="documented", refs=[e.id], text=Bi(
            ru=f"В базе DrugBank это сочетание описано так: «{ru}» (перевод проекта; оригинал — в карточке источника).",
            en=f"DrugBank describes this combination as: “{e.statement}”",
        )))
    if len(db) > MAX_LISTED:
        rest = db[MAX_LISTED:]
        out.append(Statement(kind="documented", refs=[e.id for e in rest], text=Bi(
            ru=f"Ещё {len(rest)} {_plural_ru(len(rest), ('запись', 'записи', 'записей'))} DrugBank — в списке источников.",
            en=f"{len(rest)} more DrugBank record(s) are in the source list.")))
    unverified = [e.id for e in db if e.direction == "not_verified"]
    if unverified:
        out.append(Statement(kind="caveat", refs=unverified, text=Bi(
            ru="Для этого типа записей порядок препаратов в выгрузке DrugBank оказался ненадёжным (мы это измерили), поэтому здесь не сказано, какой из двух препаратов на какой влияет.",
            en="For this record type the drug order in the DrugBank export proved unreliable (we measured it), so the text does not say which drug affects which.",
        )))
    for c in conflicts:
        out.append(Statement(kind="caveat", refs=c.record_ids, text=c.description))

    if not labels and not db:
        consulted = [SOURCE_LABEL[c.source] for c in checks if c.status in ("ok", "no_match") and c.source in SOURCE_LABEL]
        src_ru = ", ".join(s.ru for s in consulted) or "локальная база DrugBank"
        src_en = ", ".join(s.en for s in consulted) or "the local DrugBank records"
        out.append(Statement(kind="missing", text=Bi(
            ru=f"В проверенных источниках ({src_ru}) записей о взаимодействии препаратов {n.ru(a)} и {n.ru(b)} не найдено. Это не означает, что сочетание безопасно: для многих пар такие данные просто не собирали, а инструкции часто описывают взаимодействия сразу для целых групп препаратов.",
            en=f"No record of an interaction between {n.en(a)} and {n.en(b)} was found in the sources checked ({src_en}). This does not mean the combination is safe: for many pairs this data was never collected, and labels often describe interactions for whole drug classes.",
        )))
    return out


# ----------------------------------------------------------------- why ------
_VERB = {
    "enzyme": Bi(ru="перерабатывает", en="processes"),
    "transporter": Bi(ru="переносит", en="moves"),
    "carrier": Bi(ru="переносит по крови", en="carries in the blood"),
}

#: What changes for the affected drug, by relation: (inhibited, induced).
_CONSEQUENCE = {
    "enzyme": (Bi(ru="может перерабатываться медленнее обычного", en="may be broken down more slowly than usual"),
               Bi(ru="может перерабатываться быстрее обычного", en="may be broken down faster than usual")),
    "transporter": (Bi(ru="может переноситься хуже обычного", en="may be moved less efficiently than usual"),
                    Bi(ru="может переноситься активнее обычного", en="may be moved more actively than usual")),
    "carrier": (Bi(ru="может иначе связываться с этим белком в крови", en="may bind this blood protein differently"),
                Bi(ru="может иначе связываться с этим белком в крови", en="may bind this blood protein differently")),
}


def _finding_text(n: Names, f: MechanismFinding) -> Bi:
    g = f.protein.gene
    if f.pattern in ("inhibitor_substrate", "inducer_substrate"):
        act, aff = f.actor_drug_id, f.affected_drug_id
        verb = _VERB[f.relation]
        slower, faster = _CONSEQUENCE[f.relation]
        if f.pattern == "inhibitor_substrate":
            return Bi(
                ru=f"Препарат {n.ru(act)} отмечен в базах как вещество, подавляющее белок {g}, а препарат {n.ru(aff)} — как вещество, которое этот белок {verb.ru}. Когда белок подавлен, препарат {n.ru(aff)} {slower.ru}.",
                en=f"{n.en(act)} is recorded as inhibiting {g}, and {n.en(aff)} as something {g} {verb.en}. With {g} inhibited, {n.en(aff)} {slower.en}.")
        return Bi(
            ru=f"Препарат {n.ru(act)} отмечен в базах как вещество, усиливающее выработку белка {g}, а препарат {n.ru(aff)} — как вещество, которое этот белок {verb.ru}. Тогда препарат {n.ru(aff)} {faster.ru}.",
            en=f"{n.en(act)} is recorded as inducing {g}, and {n.en(aff)} as something {g} {verb.en}. With more {g} available, {n.en(aff)} {faster.en}.")
    if f.pattern == "shared_substrate":
        verb = _VERB[f.relation]
        return Bi(
            ru=f"Белок {g} {verb.ru} оба препарата. Само по себе это слабый признак: общий путь переработки есть у многих пар, которые не влияют друг на друга.",
            en=f"{g} {verb.en} both drugs. On its own this is a weak sign: many pairs that share a route do not affect each other.")
    if f.pattern == "opposing_target_action":
        return Bi(
            ru=f"Оба препарата действуют на белок {g}, но в противоположных направлениях: один его активирует, другой подавляет. В этой точке их действие может ослаблять друг друга.",
            en=f"Both drugs act on {g}, in opposite directions: one activates it, the other inhibits it. At this point their effects may cancel each other out.")
    if f.pattern == "same_direction_target_action":
        return Bi(
            ru=f"Оба препарата действуют на белок {g} в одном направлении. В этой точке их действие может складываться.",
            en=f"Both drugs act on {g} in the same direction. At this point their effects may add up.")
    return Bi(
        ru=f"Оба препарата связаны в базах с белком {g}, но роли не позволяют сказать, как они могли бы влиять друг на друга.",
        en=f"Both drugs are linked to {g} in the databases, but their recorded roles do not say how they might affect each other.")


def _why(n: Names, mech: MechanismBlock, has_documented: bool) -> list[Statement]:
    out: list[Statement] = []
    strong = [f for f in mech.findings if f.pattern != "shared_annotation"]
    shown = (strong or mech.findings)[:3]
    for f in shown:
        out.append(Statement(kind="hypothesis", refs=[f.id, *f.annotation_ids], text=_finding_text(n, f)))
    consistent = [f for f in shown if f.consistent_with_records]
    if consistent:
        recs = sorted({r for f in consistent for r in f.consistent_with_records})
        one = len(consistent) == 1
        out.append(Statement(kind="caveat", refs=[*(f.id for f in consistent), *recs], text=Bi(
            ru=("Эта гипотеза согласуется" if one else "Эти гипотезы согласуются") + " с записью DrugBank о взаимодействии. Но это не независимое подтверждение: DrugBank мог составить запись по тем же сведениям о белках.",
            en=("This hypothesis agrees" if one else "These hypotheses agree") + " with a DrugBank interaction record. That is not independent confirmation: DrugBank may have derived the record from the same protein annotations.")))
    if shown:
        out.append(Statement(kind="caveat", refs=[f.id for f in shown], text=Bi(
            ru="Базы не указывают, насколько сильно препарат подавляет или усиливает белок и какую долю работы с препаратом этот белок выполняет. Поэтому это гипотезы, а не вывод о том, что взаимодействие произойдёт.",
            en="The databases record neither how strongly a drug inhibits or induces a protein nor how much of a drug's handling that protein does. These are hypotheses, not a conclusion that an interaction will happen.")))
    else:
        out.append(Statement(kind="missing", text=Bi(
            ru="Среди задокументированных ролей этих препаратов нет общего белка, через который они могли бы влиять друг на друга. Механизм может быть иным или ещё не изученным.",
            en="The documented roles of these drugs share no protein through which they might affect each other. The mechanism may be different, or not yet studied.")))
        if has_documented:
            out.append(Statement(kind="caveat", text=Bi(
                ru="Источник, описывающий взаимодействие, не указывает его механизм.",
                en="The source that documents the interaction does not state its mechanism.")))
    if mech.shared_pathways:
        p = mech.shared_pathways[0]
        k = mech.n_shared_pathways_total
        out.append(Statement(kind="annotation", refs=[f"pathway:{p.id}"], text=Bi(
            ru=f"Белки обоих препаратов участвуют в {k} {_plural_ru(k, ('общем биологическом процессе', 'общих биологических процессах', 'общих биологических процессах'))} по базе Reactome — например, «{p.name}». Общий процесс — это фон, а не причина взаимодействия.",
            en=f"Proteins of both drugs take part in {k} shared biological process(es) in Reactome — for example “{p.name}”. A shared process is background, not a cause of interaction.")))
    return out


# ------------------------------------------------------------------ ai ------
def _score_sentence(band: str) -> Bi:
    return {
        "high": Bi(ru="Модель BIO-GINE считает, что эта пара сильно похожа на пары, уже описанные как взаимодействующие.",
                   en="BIO-GINE finds this pair strongly resembles pairs already recorded as interacting."),
        "moderate": Bi(ru="Модель BIO-GINE считает, что эта пара умеренно похожа на пары, уже описанные как взаимодействующие.",
                       en="BIO-GINE finds this pair moderately resembles pairs already recorded as interacting."),
        "low": Bi(ru="Модель BIO-GINE считает, что эта пара мало похожа на пары, уже описанные как взаимодействующие.",
                  en="BIO-GINE finds this pair bears little resemblance to pairs already recorded as interacting."),
    }[band]


def _ai(model: ModelBlock) -> list[Statement]:
    out: list[Statement] = []
    if not model.available:
        out.append(Statement(kind="missing", text=Bi(
            ru="Исследовательская модель сейчас недоступна, поэтому её оценка не показана.",
            en="The research model is not available right now, so no score is shown.")))
    elif model.training_label_seen:
        out.append(Statement(kind="model", refs=["model"], text=Bi(
            ru="Модель BIO-GINE обучалась в том числе на записи об этой паре, поэтому её оценка здесь — не самостоятельный сигнал, и мы её не учитываем.",
            en="BIO-GINE was trained on the record of this very pair, so its score here is not an independent signal and is not counted.")))
    else:
        s = _score_sentence(model.band or "low")
        out.append(Statement(kind="model", refs=["model"], text=Bi(
            ru=s.ru + " Это сходство с уже описанными парами, а не оценка вреда.",
            en=s.en + " This is resemblance to recorded pairs, not an estimate of harm.")))
    for note in model.notes:
        out.append(Statement(kind="caveat", refs=["model"], text=note))
    return out


# ----------------------------------------------------------- certainty ------
def _certainty(evidence: list[EvidenceRecord], mech: MechanismBlock, model: ModelBlock) -> list[Statement]:
    out: list[Statement] = []
    docs = [e for e in evidence if e.category != EvidenceCategory.LABEL_MENTION_NO_EFFECT_REPORTED]
    if docs:
        k = len(docs)
        out.append(Statement(kind="documented", refs=[e.id for e in docs], text=Bi(
            ru=f"Задокументировано: {k} {_plural_ru(k, ('запись', 'записи', 'записей'))} в источниках. Это самая надёжная часть страницы.",
            en=f"Documented: {k} source record(s). This is the most reliable part of the page.")))
    out.append(Statement(kind="caveat", text=Bi(
        ru="Степень тяжести здесь не присваивается: в выгрузке DrugBank её нет, а для инструкций показан только раздел, в котором упомянут препарат.",
        en="No severity is assigned: the DrugBank export has none, and for labels only the section that names the drug is shown.")))
    hyps = [f for f in mech.findings if f.pattern != "shared_annotation"]
    if hyps:
        k = len(hyps)
        out.append(Statement(kind="hypothesis", refs=[f.id for f in hyps], text=Bi(
            ru=f"Гипотезы о механизме ({k}) собраны из задокументированных ролей каждого препарата по отдельности. Для этой пары они не проверялись.",
            en=f"The {k} mechanism hypothesis(es) are assembled from each drug's documented roles separately. None was tested for this pair.")))
    if model.available and not model.abstain and model.measured_performance:
        p = model.measured_performance[0]
        if model.regime == "S3":
            ru_view, en_view = "где оба препарата модель не видела при обучении (как здесь)", "where the model saw neither drug in training (as here)"
        else:
            ru_view, en_view = "где один из препаратов модель не видела при обучении (как здесь)", "where the model did not see one of the drugs in training (as here)"
        out.append(Statement(kind="model", refs=["model"], text=Bi(
            ru=f"Качество модели на отложенных парах, {ru_view}: {p.metric} {p.mean:.3f} ± {p.sd:.3f} по {p.n_seeds} запускам. Это средняя характеристика по многим парам, а не уверенность в этой конкретной паре.",
            en=f"Model quality on held-out pairs {en_view}: {p.metric} {p.mean:.3f} ± {p.sd:.3f} over {p.n_seeds} runs. That is an average over many pairs, not confidence in this particular pair.")))
    elif model.available and model.regime == "S1" and not model.training_label_seen:
        out.append(Statement(kind="model", refs=["model"], text=Bi(
            ru="Для пар из двух препаратов, на которых модель обучалась, её точность не измерялась.",
            en="For pairs of two drugs the model was trained on, its accuracy was never measured.")))
    return out


# ------------------------------------------------------------- missing ------
def _missing(n: Names, a: str, b: str, checks: list[SourceCheck]) -> list[Statement]:
    out: list[Statement] = []
    for c in checks:
        if c.source not in SOURCE_LABEL:
            continue
        lbl = SOURCE_LABEL[c.source]
        if c.status == "unavailable":
            out.append(Statement(kind="missing", text=Bi(
                ru=f"Источник «{lbl.ru}» сейчас не удалось проверить. Его данные в этот ответ не вошли.",
                en=f"The source “{lbl.en}” could not be checked right now. Its data is not part of this answer.")))
        elif c.status == "disabled":
            out.append(Statement(kind="missing", text=Bi(
                ru=f"Источник «{lbl.ru}» не подключён в этой версии сервиса, поэтому его данные в ответ не вошли.",
                en=f"The source “{lbl.en}” is not connected in this deployment, so its data is not part of this answer.")))
    for d in (a, b):
        if not n.store.lexicon.by_id[d].inn:
            out.append(Statement(kind="missing", text=Bi(
                ru=f"У препарата {d} в данных проекта нет международного названия, поэтому его нельзя искать в инструкциях по названию.",
                en=f"Drug {d} has no international name in the project data, so labels cannot be searched for it by name.")))
    out.append(Statement(kind="caveat", text=Bi(
        ru="Здесь не учитываются дозы, длительность приёма, возраст, работа почек и печени, другие лекарства и особенности конкретного человека — всё, от чего зависит, проявится ли взаимодействие и насколько сильно.",
        en="Doses, duration, age, kidney and liver function, other medicines and individual factors are not taken into account — everything that decides whether an interaction shows up and how strongly.")))
    out.append(Statement(kind="caveat", text=Bi(
        ru="Решения о приёме лекарств принимают врач или фармацевт. Эта страница не может их заменить.",
        en="Decisions about medicines belong to a doctor or pharmacist. This page cannot replace them.")))
    return out


# ------------------------------------------------------------- assemble ------
def build(store, a: str, b: str, evidence: list[EvidenceRecord], conflicts: list[Conflict],
          mech: MechanismBlock, model: ModelBlock, checks: list[SourceCheck],
          status: EvidenceStatus) -> Explanation:
    n = Names(store)
    has_documented = any(e.category != EvidenceCategory.LABEL_MENTION_NO_EFFECT_REPORTED for e in evidence)
    sections = [
        Section(id="known", title=TITLES["known"], statements=_known(n, a, b, evidence, conflicts, checks)),
        Section(id="why", title=TITLES["why"], statements=_why(n, mech, has_documented)),
        Section(id="ai", title=TITLES["ai"], statements=_ai(model)),
        Section(id="certainty", title=TITLES["certainty"], statements=_certainty(evidence, mech, model)),
        Section(id="missing", title=TITLES["missing"], statements=_missing(n, a, b, checks)),
    ]
    return Explanation(sections=sections)


def validate(explanation: Explanation, evidence: list[EvidenceRecord], mech: MechanismBlock,
             model: ModelBlock) -> None:
    """Refuse an explanation with an unsupported claim or forbidden wording."""
    known = {e.id for e in evidence} | set(mech.annotations) | {f.id for f in mech.findings} \
        | {f"pathway:{p.id}" for p in mech.shared_pathways} | {"model"}
    for sec in explanation.sections:
        for st in sec.statements:
            if st.kind in ("documented", "annotation", "hypothesis", "model") and not st.refs:
                raise ExplanationError(f"{sec.id}: a {st.kind} statement carries no reference: {st.text.en!r}")
            unknown = [r for r in st.refs if r not in known]
            if unknown:
                raise ExplanationError(f"{sec.id}: references not in the report: {unknown}")
            if "model" in st.refs and st.kind in ("model",) and not model.available:
                raise ExplanationError("a model statement was produced while the model is unavailable")
            for text in (st.text.ru, st.text.en):
                for pat in _FORBIDDEN:
                    if pat.search(text):
                        raise ExplanationError(f"forbidden wording {pat.pattern!r} in: {text!r}")
