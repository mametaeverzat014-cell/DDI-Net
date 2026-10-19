"""Clinical Outcome Engine: what the sources say can happen, and on what basis.

Design: docs/DDINET_V3_CLINICAL_OUTCOMES_ARCHITECTURE.md. In short:

* An outcome exists only when a source statement about THIS pair supports it:
  a DrugBank record (its standard sentence for the interaction type, mapped by
  the curated table ``TYPE_MAP``) or an FDA label sentence that names the
  partner drug AND an outcome term from ``LEXICON`` (same sentence, not
  negated, not a patient-population phrase, not "no effect" wording).
* Drug-protein annotations never create a documented outcome. They explain
  documented exposure changes (``mechanistically_supported``) or, alone, give
  research-only hypotheses (``hypothesized``).
* The kind of statement is kept (``effect_level``): a clinical outcome named by
  the source is different from a stronger pharmacological effect ("anticoagulant
  activities"), an exposure change, a weaker intended effect, or unnamed
  "adverse effects".
* Seriousness is only what a source states: a Contraindications or Boxed
  Warning section, or the label sentence's own words ("fatal",
  "life-threatening", "serious"). Otherwise: not established. Never from the
  model.
* Deterministic and versioned: every support names the rule that produced it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .explain import _FORBIDDEN
from .reference_sets import EFFECTS as REF_EFFECTS, MEDDRA_MAP_VERSION
from .schema import (
    Bi,
    ChainLink,
    ChainNode,
    ClinicalOutcome,
    EvidenceCategory,
    EvidenceRecord,
    MechanismBlock,
    MechanismChain,
    ModelBlock,
    OutcomeReport,
    OutcomeSupport,
    SourceCheck,
)

TYPE_MAP_VERSION = "drugbank_type_map/v1"
LEXICON_VERSION = "label_lexicon/v4"
ANNOTATION_METHOD = "annotation_chain/v1"

# ------------------------------------------------------------------ categories --
CATEGORIES: dict[str, Bi] = {
    "bleeding_coagulation": Bi(ru="Кровотечения и свёртываемость крови", en="Bleeding and blood clotting"),
    "cardiac_rhythm": Bi(ru="Ритм и проводимость сердца", en="Heart rhythm and conduction"),
    "cardiovascular_other": Bi(ru="Сердце и сосуды (другое)", en="Heart and blood vessels (other)"),
    "blood_pressure": Bi(ru="Артериальное давление", en="Blood pressure"),
    "cns_sedation": Bi(ru="Седация и угнетение ЦНС", en="Sedation and CNS depression"),
    "respiratory_depression": Bi(ru="Угнетение дыхания", en="Respiratory depression"),
    "serotonergic": Bi(ru="Серотонинергическая токсичность", en="Serotonergic toxicity"),
    "nervous_system_other": Bi(ru="Нервная система (другое)", en="Nervous system (other)"),
    "exposure_increase": Bi(ru="Повышение содержания препарата в организме", en="Increased drug exposure"),
    "exposure_decrease": Bi(ru="Снижение содержания препарата в организме", en="Decreased drug exposure"),
    "reduced_effectiveness": Bi(ru="Снижение лечебного действия", en="Reduced therapeutic effect"),
    "increased_effect": Bi(ru="Усиление лечебного действия", en="Increased therapeutic effect"),
    "electrolyte": Bi(ru="Электролитные нарушения", en="Electrolyte disturbances"),
    "glucose": Bi(ru="Уровень глюкозы", en="Blood glucose"),
    "kidney": Bi(ru="Почки", en="Kidney"),
    "liver": Bi(ru="Печень", en="Liver"),
    "muscle": Bi(ru="Мышцы (миопатия, рабдомиолиз)", en="Muscle (myopathy, rhabdomyolysis)"),
    "bone_marrow_immune": Bi(ru="Кроветворение и иммунитет", en="Blood cell production and immunity"),
    "hypersensitivity_skin": Bi(ru="Аллергия и кожа", en="Hypersensitivity and skin"),
    "gastrointestinal": Bi(ru="Желудочно-кишечный тракт", en="Gastrointestinal tract"),
    "respiratory_airway": Bi(ru="Дыхательные пути", en="Airways"),
    "adverse_unspecified": Bi(ru="Нежелательные эффекты (не уточнены)", en="Adverse effects (not specified)"),
    "general_other": Bi(ru="Другие задокументированные явления", en="Other documented events"),
}

REF_CLINICAL_TEXT = Bi(
    ru="Справочный набор называет это последствие для данной пары. Частоту он не указывает; оценки тяжести, которые дают справочники, здесь не воспроизводятся.",
    en="The reference set names this consequence for this pair. It gives no frequency; the severity grades the compendia give are not reproduced here.")

LEVEL_TEXT: dict[str, Bi] = {
    "clinical_outcome": Bi(
        ru="Источник прямо называет это последствие для данной пары. Частоту и тяжесть он не указывает.",
        en="The source names this consequence for this pair directly. It gives no frequency and no severity."),
    "pharmacodynamic_effect": Bi(
        ru="Источник описывает усиление (или изменение) фармакологического действия одного из препаратов. Он не утверждает, что наступает конкретный вред.",
        en="The source describes a stronger (or altered) pharmacological effect of one of the drugs. It does not state that a particular harm follows."),
    "pharmacokinetic_change": Bi(
        ru="Источник описывает изменение того, сколько препарата находится в организме. Само по себе это не задокументированное клиническое последствие.",
        en="The source describes a change in how much of a drug is in the body. That, by itself, is not a documented clinical outcome."),
    "reduced_effectiveness": Bi(
        ru="Источник описывает ослабление нужного (лечебного) действия одного из препаратов.",
        en="The source describes a weaker intended (therapeutic) effect of one of the drugs."),
    "unspecified_adverse": Bi(
        ru="Источник говорит, что риск или выраженность нежелательных эффектов могут возрасти, но не называет, каких именно.",
        en="The source says the risk or severity of adverse effects can increase, without naming which."),
}


@dataclass(frozen=True)
class TypeRow:
    category: str
    effect: str
    level: str
    en: str
    ru: str
    #: Words that must appear in DrugBank's template (checked by tests).
    key: str


def _r(category, effect, level, en, ru, key) -> TypeRow:
    return TypeRow(category, effect, level, en, ru, key)


C, PD, PK, RE, UA = "clinical_outcome", "pharmacodynamic_effect", "pharmacokinetic_change", "reduced_effectiveness", "unspecified_adverse"

#: Curated map of DrugBank's 86 interaction templates. Read straight off the
#: template text; every row is checked against it in tests/test_v3_outcomes.py.
TYPE_MAP: dict[int, TypeRow] = {
    1: _r("hypersensitivity_skin", "photosensitivity_increase", PD, "Stronger photosensitizing effect", "Усиление фотосенсибилизирующего действия", "photosensitizing"),
    2: _r("nervous_system_other", "anticholinergic_increase", PD, "Stronger anticholinergic effect", "Усиление антихолинергического действия", "anticholinergic"),
    3: _r("exposure_decrease", "bioavailability_decrease", PK, "Lower bioavailability", "Снижение биодоступности", "bioavailability"),
    4: _r("exposure_decrease", "metabolism_increase", PK, "Faster metabolism (lower exposure)", "Ускорение метаболизма (меньше препарата в организме)", "metabolism"),
    5: _r("reduced_effectiveness", "vasoconstriction_decrease", RE, "Weaker vasoconstricting effect", "Ослабление сосудосуживающего действия", "vasoconstricting"),
    6: _r("bleeding_coagulation", "anticoagulant_increase", PD, "Stronger anticoagulant (blood-thinning) effect", "Усиление антикоагулянтного (противосвёртывающего) действия", "anticoagulant"),
    7: _r("nervous_system_other", "ototoxicity_increase", PD, "Stronger ototoxic (hearing-damaging) effect", "Усиление ототоксического действия (вред для слуха)", "ototoxic"),
    8: _r("increased_effect", "efficacy_increase", PD, "Stronger therapeutic effect", "Усиление лечебного действия", "therapeutic efficacy"),
    9: _r("glucose", "hypoglycemic_increase", PD, "Stronger glucose-lowering effect", "Усиление сахароснижающего действия", "hypoglycemic"),
    10: _r("blood_pressure", "antihypertensive_increase", PD, "Stronger blood-pressure-lowering effect", "Усиление гипотензивного (снижающего давление) действия", "antihypertensive"),
    11: _r("reduced_effectiveness", "active_metabolite_decrease", RE, "Lower active-metabolite levels with loss of efficacy", "Снижение уровня активных метаболитов с потерей эффективности", "loss in efficacy"),
    12: _r("reduced_effectiveness", "anticoagulant_decrease", RE, "Weaker anticoagulant effect", "Ослабление антикоагулянтного действия", "anticoagulant"),
    13: _r("exposure_decrease", "absorption_decrease", PK, "Lower absorption", "Снижение всасывания", "absorption"),
    14: _r("reduced_effectiveness", "bronchodilation_decrease", RE, "Weaker bronchodilating effect", "Ослабление бронхорасширяющего действия", "bronchodilatory"),
    15: _r("cardiovascular_other", "cardiotoxicity_increase", PD, "Stronger cardiotoxic effect", "Усиление кардиотоксического действия", "cardiotoxic"),
    16: _r("cns_sedation", "cns_depression_increase", PD, "Stronger CNS-depressant effect", "Усиление угнетающего действия на ЦНС", "central nervous system depressant"),
    17: _r("reduced_effectiveness", "neuromuscular_block_decrease", RE, "Weaker neuromuscular blocking effect", "Ослабление нервно-мышечной блокады", "neuromuscular blocking"),
    18: _r("exposure_increase", "absorption_increase", PK, "Higher absorption and serum concentration", "Усиление всасывания и повышение концентрации", "absorption"),
    19: _r("blood_pressure", "vasoconstriction_increase", PD, "Stronger vasoconstricting effect", "Усиление сосудосуживающего действия", "vasoconstricting"),
    20: _r("cardiac_rhythm", "qt_prolonging_increase", PD, "Stronger QTc-prolonging effect", "Усиление действия, удлиняющего интервал QTc", "QTc-prolonging"),
    21: _r("nervous_system_other", "neuromuscular_block_increase", PD, "Stronger neuromuscular blocking effect", "Усиление нервно-мышечной блокады", "neuromuscular blocking"),
    22: _r("nervous_system_other", "neuromuscular_adverse_increase", PD, "Stronger adverse neuromuscular effects", "Усиление нежелательного нервно-мышечного действия", "adverse neuromuscular"),
    23: _r("nervous_system_other", "stimulant_increase", PD, "Stronger stimulatory effect", "Усиление стимулирующего действия", "stimulatory"),
    24: _r("electrolyte", "hypocalcemic_increase", PD, "Stronger calcium-lowering effect", "Усиление действия, снижающего кальций", "hypocalcemic"),
    25: _r("cardiac_rhythm", "av_block_increase", PD, "Stronger AV-blocking effect", "Усиление атриовентрикулярной блокады", "atrioventricular blocking"),
    26: _r("reduced_effectiveness", "antiplatelet_decrease", RE, "Weaker antiplatelet effect", "Ослабление антиагрегантного действия", "antiplatelet"),
    27: _r("nervous_system_other", "neuroexcitation_increase", PD, "Stronger neuroexcitatory effect", "Усиление нейровозбуждающего действия", "neuroexcitatory"),
    28: _r("hypersensitivity_skin", "dermatologic_adverse_increase", PD, "Stronger dermatologic adverse effects", "Усиление нежелательного действия на кожу", "dermatologic"),
    29: _r("reduced_effectiveness", "diuretic_decrease", RE, "Weaker diuretic effect", "Ослабление мочегонного действия", "diuretic"),
    30: _r("blood_pressure", "orthostatic_hypotension_increase", PD, "Stronger orthostatic hypotensive effect", "Усиление ортостатического снижения давления", "orthostatic hypotensive"),
    31: _r("blood_pressure", "hypertension", C, "Higher risk or severity of hypertension", "Повышение риска или выраженности повышенного давления", "hypertension"),
    32: _r("cns_sedation", "sedation_increase", PD, "Stronger sedative effect", "Усиление седативного действия", "sedative"),
    33: _r("cardiac_rhythm", "qt_prolongation", C, "Higher risk or severity of QTc prolongation", "Повышение риска или выраженности удлинения интервала QTc", "QTc prolongation"),
    34: _r("bone_marrow_immune", "immunosuppression_increase", PD, "Stronger immunosuppressive effect", "Усиление иммуносупрессивного действия", "immunosuppressive"),
    35: _r("nervous_system_other", "neurotoxicity_increase", PD, "Stronger neurotoxic effect", "Усиление нейротоксического действия", "neurotoxic"),
    36: _r("increased_effect", "antipsychotic_increase", PD, "Stronger antipsychotic effect", "Усиление антипсихотического действия", "antipsychotic"),
    37: _r("reduced_effectiveness", "antihypertensive_decrease", RE, "Weaker blood-pressure-lowering effect", "Ослабление гипотензивного действия", "antihypertensive"),
    38: _r("blood_pressure", "vasodilation_increase", PD, "Stronger vasodilating effect", "Усиление сосудорасширяющего действия", "vasodilatory"),
    39: _r("gastrointestinal", "constipation_increase", PD, "Stronger constipating effect", "Усиление способности вызывать запор", "constipating"),
    40: _r("respiratory_depression", "respiratory_depression_increase", PD, "Stronger respiratory-depressant effect", "Усиление угнетения дыхания", "respiratory depressant"),
    41: _r("cns_sedation", "hypotensive_cns_depression_increase", PD, "Stronger hypotensive and CNS-depressant effects", "Усиление гипотензивного действия и угнетения ЦНС", "hypotensive and central nervous system depressant"),
    42: _r("electrolyte", "hyperkalemia", C, "Higher risk or severity of hyperkalemia", "Повышение риска или выраженности гиперкалиемии", "hyperkalemia"),
    43: _r("exposure_increase", "protein_binding_decrease", PK, "Lower protein binding", "Снижение связывания с белками", "protein binding"),
    44: _r("nervous_system_other", "central_neurotoxicity_increase", PD, "Stronger central neurotoxic effect", "Усиление центрального нейротоксического действия", "central neurotoxic"),
    45: _r("reduced_effectiveness", "diagnostic_effectiveness_decrease", RE, "Lower effectiveness as a diagnostic agent", "Снижение эффективности как диагностического средства", "diagnostic agent"),
    46: _r("respiratory_airway", "bronchoconstriction_increase", PD, "Stronger bronchoconstricting effect", "Усиление бронхосуживающего действия", "bronchoconstrictory"),
    47: _r("exposure_increase", "metabolism_decrease", PK, "Slower metabolism (higher exposure)", "Замедление метаболизма (больше препарата в организме)", "metabolism"),
    48: _r("muscle", "myopathy_rhabdomyolysis_increase", PD, "Stronger myopathy / rhabdomyolysis effect", "Усиление способности вызывать миопатию и рабдомиолиз", "myopathic rhabdomyolysis"),
    49: _r("adverse_unspecified", "adverse_effects", UA, "Higher risk or severity of adverse effects (not specified)", "Повышение риска или выраженности нежелательных эффектов (не уточнены)", "adverse effects"),
    50: _r("cardiovascular_other", "heart_failure", C, "Higher risk or severity of heart failure", "Повышение риска или выраженности сердечной недостаточности", "heart failure"),
    51: _r("electrolyte", "hypercalcemic_increase", PD, "Stronger calcium-raising effect", "Усиление действия, повышающего кальций", "hypercalcemic"),
    52: _r("reduced_effectiveness", "analgesic_decrease", RE, "Weaker analgesic effect", "Ослабление обезболивающего действия", "analgesic"),
    53: _r("bleeding_coagulation", "antiplatelet_increase", PD, "Stronger antiplatelet effect", "Усиление антиагрегантного действия", "antiplatelet"),
    54: _r("cardiac_rhythm", "bradycardia_increase", PD, "Stronger bradycardic (heart-slowing) effect", "Усиление брадикардического действия (урежение пульса)", "bradycardic"),
    55: _r("electrolyte", "hyponatremic_increase", PD, "Stronger sodium-lowering effect", "Усиление действия, снижающего натрий", "hyponatremic"),
    56: _r("blood_pressure", "hypotension", C, "Higher risk or severity of hypotension", "Повышение риска или выраженности сниженного давления", "hypotension"),
    57: _r("kidney", "nephrotoxicity_increase", PD, "Stronger nephrotoxic (kidney-damaging) effect", "Усиление нефротоксического действия (вред для почек)", "nephrotoxic"),
    58: _r("cardiovascular_other", "cardiotoxicity_decrease", PD, "Weaker cardiotoxic effect", "Ослабление кардиотоксического действия", "cardiotoxic"),
    59: _r("gastrointestinal", "ulcerogenic_increase", PD, "Stronger ulcer-causing effect", "Усиление способности вызывать язвы", "ulcerogenic"),
    60: _r("blood_pressure", "hypotensive_increase", PD, "Stronger hypotensive effect", "Усиление гипотензивного действия", "hypotensive"),
    61: _r("reduced_effectiveness", "stimulant_decrease", RE, "Weaker stimulatory effect", "Ослабление стимулирующего действия", "stimulatory"),
    62: _r("exposure_increase", "bioavailability_increase", PK, "Higher bioavailability", "Повышение биодоступности", "bioavailability"),
    63: _r("bone_marrow_immune", "myelosuppression_increase", PD, "Stronger myelosuppressive effect", "Усиление угнетения кроветворения", "myelosuppressive"),
    64: _r("serotonergic", "serotonergic_increase", PD, "Stronger serotonergic effect", "Усиление серотонинергического действия", "serotonergic"),
    65: _r("exposure_decrease", "excretion_increase", PK, "Faster excretion (lower serum level)", "Ускорение выведения (ниже уровень в крови)", "excretion"),
    66: _r("bleeding_coagulation", "bleeding", C, "Higher risk or severity of bleeding", "Повышение риска или выраженности кровотечения", "bleeding"),
    67: _r("exposure_decrease", "absorption_decrease", PK, "Lower absorption and serum concentration", "Снижение всасывания и концентрации", "absorption"),
    68: _r("electrolyte", "hyperkalemic_increase", PD, "Stronger potassium-raising effect", "Усиление действия, повышающего калий", "hyperkalemic"),
    69: _r("increased_effect", "analgesic_increase", PD, "Stronger analgesic effect", "Усиление обезболивающего действия", "analgesic"),
    70: _r("reduced_effectiveness", "efficacy_decrease", RE, "Weaker therapeutic effect", "Ослабление лечебного действия", "therapeutic efficacy"),
    71: _r("blood_pressure", "hypertensive_increase", PD, "Stronger blood-pressure-raising effect", "Усиление действия, повышающего давление", "hypertensive"),
    72: _r("exposure_increase", "excretion_decrease", PK, "Slower excretion (higher serum level)", "Замедление выведения (выше уровень в крови)", "excretion"),
    73: _r("exposure_increase", "serum_concentration_increase", PK, "Higher serum concentration", "Повышение концентрации в крови", "serum concentration"),
    74: _r("cardiovascular_other", "fluid_retention_increase", PD, "Stronger fluid-retaining effect", "Усиление задержки жидкости", "fluid retaining"),
    75: _r("exposure_decrease", "serum_concentration_decrease", PK, "Lower serum concentration", "Снижение концентрации в крови", "serum concentration"),
    76: _r("reduced_effectiveness", "sedation_decrease", RE, "Weaker sedative effect", "Ослабление седативного действия", "sedative"),
    77: _r("exposure_increase", "active_metabolite_increase", PK, "Higher active-metabolite levels", "Повышение уровня активных метаболитов", "active metabolites"),
    78: _r("glucose", "hyperglycemic_increase", PD, "Stronger glucose-raising effect", "Усиление действия, повышающего глюкозу", "hyperglycemic"),
    79: _r("cns_sedation", "cns_depression_hypertensive_increase", PD, "Stronger CNS-depressant and hypertensive effects", "Усиление угнетения ЦНС и повышения давления", "central nervous system depressant"),
    80: _r("liver", "hepatotoxicity_increase", PD, "Stronger hepatotoxic (liver-damaging) effect", "Усиление гепатотоксического действия (вред для печени)", "hepatotoxic"),
    81: _r("bleeding_coagulation", "thrombogenic_increase", PD, "Stronger thrombogenic (clot-promoting) effect", "Усиление тромбогенного действия", "thrombogenic"),
    82: _r("cardiac_rhythm", "arrhythmogenic_increase", PD, "Stronger arrhythmogenic effect", "Усиление аритмогенного действия", "arrhythmogenic"),
    83: _r("electrolyte", "hypokalemic_increase", PD, "Stronger potassium-lowering effect", "Усиление действия, снижающего калий", "hypokalemic"),
    84: _r("blood_pressure", "vasopressor_increase", PD, "Stronger vasopressor effect", "Усиление вазопрессорного действия", "vasopressor"),
    85: _r("cardiac_rhythm", "tachycardia_increase", PD, "Stronger tachycardic (heart-racing) effect", "Усиление тахикардического действия", "tachycardic"),
    86: _r("hypersensitivity_skin", "hypersensitivity_reaction", C, "Higher risk of a hypersensitivity reaction", "Повышение риска реакции гиперчувствительности", "hypersensitivity reaction"),
}

#: Exposure effects that mean "more" or "less" of a drug, for the mechanism link.
EXPOSURE_UP = {"exposure_increase"}
EXPOSURE_DOWN = {"exposure_decrease"}


# ------------------------------------------------------------------- lexicon ----
@dataclass(frozen=True)
class Term:
    name: str
    pattern: re.Pattern
    category: str
    effect: str
    level: str
    en: str
    ru: str


def _t(name, pat, category, effect, level, en, ru, flags=re.IGNORECASE) -> Term:
    return Term(name, re.compile(pat, flags), category, effect, level, en, ru)


#: Outcome terms looked for in a label sentence that names the partner drug.
#: Conservative: a term must name the consequence itself. Population phrases
#: ("patients with renal impairment") are not terms.
LEXICON: list[Term] = [
    _t("bleeding", r"\b(bleeding|bleeds?|hemorrhag\w*|haemorrhag\w*|hematuria|melena|epistaxis|bruising|ecchymos\w*)\b",
       "bleeding_coagulation", "bleeding", C, "Bleeding", "Кровотечение"),
    # v2: case-insensitive except "INR" (v1 missed a sentence-initial "Prothrombin time").
    _t("coagulation_measure", r"\b(?i:prothrombin time|international normali[sz]ed ratio|anticoagulant (?:effect|activity|response))\b|\bINR\b",
       "bleeding_coagulation", "coagulation_measure_change", PD, "Change in a blood-clotting measure (prothrombin time / INR)", "Изменение показателя свёртываемости (протромбиновое время / МНО)", flags=0),
    # v4: "effect(s) on the QT interval" (real label: "The effect of X on the QT
    # interval was augmented by ... paroxetine").
    _t("qt_arrhythmia", r"\b(QTc? (?:interval )?prolongation|prolong\w* (?:of )?(?:the )?QTc?\b|(?:effects?|increases?)(?: of [\w-]+)? on (?:the )?QTc? interval|torsades? de pointes|ventricular (?:tachy)?arrhythmias?|ventricular fibrillation|cardiac arrhythmias?)",
       "cardiac_rhythm", "qt_prolongation", C, "QT prolongation or ventricular arrhythmia", "Удлинение интервала QT или желудочковая аритмия"),
    _t("bradycardia_block", r"\b(bradycardia|heart block|AV block|atrioventricular block|sinus arrest)\b",
       "cardiac_rhythm", "bradycardia_conduction", C, "Slow heart rate or heart block", "Урежение пульса или блокада проводимости сердца"),
    _t("serotonin_syndrome", r"\b(serotonin syndrome|serotonergic syndrome|serotonin toxicity)\b",
       "serotonergic", "serotonin_syndrome", C, "Serotonin syndrome", "Серотониновый синдром"),
    _t("respiratory_depression", r"\b(respiratory depression|respiratory arrest|hypoventilation)\b",
       "respiratory_depression", "respiratory_depression", C, "Respiratory depression", "Угнетение дыхания"),
    _t("sedation", r"\b(profound sedation|excessive sedation|sedation|CNS depression|central nervous system depression|somnolence|coma)\b",
       "cns_sedation", "sedation_cns_depression", C, "Sedation or CNS depression", "Седация или угнетение ЦНС"),
    _t("hypotension", r"\b(hypotension|syncope)\b", "blood_pressure", "hypotension", C, "Low blood pressure", "Снижение давления"),
    _t("hypertension", r"\b(hypertensive crisis|hypertensive reactions?|hypertension)\b", "blood_pressure", "hypertension", C, "High blood pressure", "Повышение давления"),
    _t("hyperkalemia", r"\b(hyperkalemia|hyperkalaemia)\b", "electrolyte", "hyperkalemia", C, "High potassium (hyperkalemia)", "Повышение калия (гиперкалиемия)"),
    _t("hypokalemia", r"\b(hypokalemia|hypokalaemia)\b", "electrolyte", "hypokalemia", C, "Low potassium (hypokalemia)", "Снижение калия (гипокалиемия)"),
    _t("hyponatremia", r"\b(hyponatremia|hyponatraemia)\b", "electrolyte", "hyponatremia", C, "Low sodium (hyponatremia)", "Снижение натрия (гипонатриемия)"),
    _t("hypomagnesemia", r"\b(hypomagnesemia|hypomagnesaemia)\b", "electrolyte", "hypomagnesemia", C, "Low magnesium", "Снижение магния"),
    _t("hypoglycemia", r"\b(hypoglycemia|hypoglycaemia)\b", "glucose", "hypoglycemia", C, "Low blood glucose (hypoglycemia)", "Снижение глюкозы (гипогликемия)"),
    _t("myopathy", r"\b(rhabdomyolysis|myopathy|myositis)\b", "muscle", "myopathy_rhabdomyolysis", C, "Myopathy or rhabdomyolysis", "Миопатия или рабдомиолиз"),
    _t("nephrotoxicity", r"\b(nephrotoxicity|renal toxicity|acute renal failure|renal failure|acute kidney injury|kidney injury)\b",
       "kidney", "kidney_injury", C, "Kidney injury or toxicity", "Поражение почек"),
    _t("hepatotoxicity", r"\b(hepatotoxicity|hepatic failure|liver failure|liver injury|hepatic injury|hepatitis)\b",
       "liver", "liver_injury", C, "Liver injury or toxicity", "Поражение печени"),
    # v4: a laboratory marker, kept apart from "liver injury" so the label does
    # not overstate it ("Grade 3 increases in transaminases ... with concurrent X").
    _t("hepatotoxicity", r"\b((?:increases?|elevations?|rises?) (?:in|of) (?:serum )?(?:hepatic |liver )?(?:transaminases?|aminotransferases?|liver enzymes|ALT|AST)|(?:elevated|increased) (?:serum )?(?:transaminases?|aminotransferases?|liver enzymes))\b",
       "liver", "liver_enzyme_increase", C, "Raised liver enzymes (transaminases)", "Повышение печёночных ферментов (трансаминаз)"),
    _t("myelosuppression", r"\b(myelosuppression|bone marrow suppression|neutropenia|agranulocytosis|pancytopenia)\b",
       "bone_marrow_immune", "myelosuppression", C, "Suppressed blood cell production", "Угнетение кроветворения"),
    _t("reduced_effect", r"\b(?:(?:reduced|decreased|diminished|loss of|lower) (?:\w+ ){0,2}(?:efficacy|effectiveness|therapeutic effect)|therapeutic failure|treatment failure)\b",
       "reduced_effectiveness", "efficacy_decrease", RE, "Reduced effectiveness", "Снижение эффективности"),
]

#: Exposure (pharmacokinetic) wording: a noun and a direction word in the same sentence.
PK_NOUN = re.compile(r"\b((?:plasma|serum|blood) (?:concentrations?|levels?)|AUC|C ?max|systemic exposure|exposure|bioavailability)\b", re.IGNORECASE)
PK_UP = re.compile(r"\b(increas\w*|elevat\w*|higher|raised|doubl\w*|tripl\w*)\b", re.IGNORECASE)
PK_DOWN = re.compile(r"\b(decreas\w*|reduc\w*|lower(?:ed)?)\b", re.IGNORECASE)

#: Negation that scopes the term itself ("no bleeding", "without increases in
#: bleeding", "did not result in QT prolongation"). A negation elsewhere in the
#: sentence ("is not recommended due to increased risk of bleeding") does not.
NEGATION = re.compile(
    r"(?:\b(?:no|without|absence of|never|neither|nor)\s+(?:[\w-]+\s+){0,4}"
    r"|\b(?:not|n't)\s+(?:been\s+)?(?:associated with|result(?:ed)? in|cause[ds]?|lead to|led to|increase[ds]?|observed|reported|seen|produce[ds]?)\s+(?:[\w-]+\s+){0,4}"
    r"|\b(?:did|does|do|was|were|has|have|had) not\s+(?:[\w-]+\s+){0,5})$",
    re.IGNORECASE)
#: v2: a negation or an unknown AFTER the term, in the same clause ("bleeding
#: risk was not increased", "hypotension was not observed", "the risk of QT
#: prolongation with X is unknown", "bleeding time was unchanged").
NEGATION_AFTER = re.compile(
    r"^[^.;:]{0,40}?\b(?:was|were|is|are|has|have|had|remained)\s+(?:been\s+)?"
    r"(?:not\b|unchanged\b|unaffected\b|unknown\b|uncertain\b|similar\b)",
    re.IGNORECASE)
POPULATION = re.compile(
    r"\b(patients? (?:with|who have)|history of|in the (?:presence|setting) of|predisposed to|at risk (?:of|for)"
    # v4 (real label: "avoided in patients: * with known disturbances of electrolyte balance, e.g., hypokalemia")
    r"|with (?:known|congenital|pre-?existing|underlying)|disturbances? of|risk factors?|conditions? (?:such as|including|known to))"
    r"\b[^.;*]{0,40}$", re.IGNORECASE)
#: v4: wording that ties two drugs together (co-administration), used to tell
#: an interaction statement from a trial-arm comparison.
CO_USE = re.compile(r"\b(concomitant\w*|co-?administ\w*|coadminist\w*|combin\w*|concurrent\w*|together|in addition to|add-on|added to|plus|with (?:other|another|strong|moderate|potent))\b", re.IGNORECASE)
TRIAL_STATS = re.compile(r"\b\d+\s*/\s*\d+\b|\d+(?:\.\d+)?\s*%")
SERIOUS_WORDS = re.compile(r"\b(fatal(?:ities)?|life[- ]threatening|deaths?|serious)\b", re.IGNORECASE)

LABEL_SECTION_SERIOUSNESS = {"CONTRAINDICATIONS": "documented_contraindication", "BOXED WARNING": "explicit_serious_warning"}
SERIOUSNESS_ORDER = ["documented_contraindication", "explicit_serious_warning", "documented_no_standard_severity", "not_applicable"]

NOT_ESTABLISHED = Bi(ru="Степень серьёзности не установлена по доступным данным.",
                     en="Severity not established from available evidence.")
SERIOUSNESS_TEXT: dict[str, Bi] = {
    "documented_contraindication": Bi(
        ru="Документальное противопоказание: инструкция называет это сочетание в разделе «Противопоказания».",
        en="Documented contraindication: the label names this combination in its Contraindications section."),
    "explicit_serious_warning": Bi(
        ru="Явное предупреждение о серьёзности: так в самом источнике (раздел «Предупреждение в рамке» или слова источника, приведённые в цитате).",
        en="Explicit serious warning: stated by the source itself (a Boxed Warning, or the source's own words, quoted)."),
    "documented_no_standard_severity": NOT_ESTABLISHED,
    "not_applicable": Bi(ru="Неприменимо: задокументированного последствия нет.",
                         en="Not applicable: there is no documented outcome."),
}

STRENGTH_TEXT: dict[str, Bi] = {
    "official_label_statement": Bi(ru="Утверждение официальной инструкции FDA (цитата).",
                                   en="Statement in an official FDA label (quoted)."),
    "database_standard_sentence": Bi(ru="Стандартная фраза базы DrugBank; на чём основана запись, источник не указывает.",
                                     en="DrugBank standard sentence; the source does not state what the record is based on."),
    "label_and_database": Bi(ru="И инструкция FDA, и запись DrugBank. Это не обязательно независимые источники: DrugBank может опираться на текст инструкции.",
                             en="Both an FDA label and a DrugBank record. They are not necessarily independent: DrugBank may rest on label text."),
    "reference_set_statement": Bi(
        ru="Справочный набор CRESCENDDI: пара задокументирована в трёх клинических справочниках (2018–2019), явление взято из их описания взаимодействия. Текст справочников не приводится.",
        en="CRESCENDDI reference set: the pair is documented in three clinical compendia (2018–2019) and the event comes from their interaction description. The compendium text is not reproduced."),
    "reference_set_and_other": Bi(
        ru="Справочный набор CRESCENDDI и ещё один источник (инструкция FDA или DrugBank). Источники не обязательно независимы.",
        en="The CRESCENDDI reference set and another source (an FDA label or DrugBank). The sources are not necessarily independent."),
    "annotation_hypothesis": Bi(ru="Только роли препаратов по отдельности (аннотации белков). Это гипотеза.",
                                en="Only the drugs' separate protein roles (annotations). This is a hypothesis."),
}

STATUS_TEXT: dict[str, tuple[Bi, Bi]] = {
    "documented_interaction": (
        Bi(ru="Найдено задокументированное взаимодействие", en="Documented interaction found"),
        Bi(ru="Источники называют конкретные последствия или изменения действия для этой пары. Ниже — что именно и на каком основании.",
           en="Sources name specific consequences or changes in effect for this pair. What they are, and on what basis, is below.")),
    "documented_outcome_unclear": (
        Bi(ru="Есть данные о взаимодействии, клиническое последствие не ясно",
           en="Interaction-specific evidence found, clinical outcome unclear"),
        Bi(ru="Источники фиксируют взаимодействие (например, изменение концентрации), но не называют, к какому клиническому последствию оно ведёт.",
           en="Sources record an interaction (for example a change in concentration) but do not name the clinical consequence.")),
    "research_prediction_only": (
        Bi(ru="Только исследовательская гипотеза", en="Research prediction only"),
        Bi(ru="Задокументированного взаимодействия не найдено. Есть лишь гипотеза о механизме по ролям каждого препарата. Это не означает, что сочетание безопасно.",
           en="No documented interaction was found. There is only a mechanism hypothesis from each drug's roles. This does not mean the combination is safe.")),
    "insufficient_evidence": (
        Bi(ru="Недостаточно данных для оценки", en="Insufficient evidence to assess"),
        Bi(ru="В проверенных источниках нет записей об этой паре. Это не означает, что сочетание безопасно: источники неполны.",
           en="The sources checked hold no record of this pair. This does not mean the combination is safe: the sources are incomplete.")),
    "source_unavailable": (
        Bi(ru="Источник данных временно недоступен", en="Evidence source temporarily unavailable"),
        Bi(ru="Ничего не найдено, но один из источников, который мог бы содержать данные, не ответил. Оценить пару полностью нельзя.",
           en="Nothing was found, but a source that could hold evidence did not respond. The pair cannot be fully assessed.")),
}

#: The exact wording required whenever no specific clinical outcome is
#: established (no outcome at all, or only changes in exposure or in effect).
#: Never a statement of safety.
NO_SPECIFIC_OUTCOME = Bi(
    ru="По доступным данным конкретное клиническое последствие не установлено. Это не означает, что сочетание безопасно.",
    en="No specific clinical outcome established from available evidence. This does not mean the combination is safe.")
NO_OUTCOME = NO_SPECIFIC_OUTCOME
NO_MECHANISM = Bi(ru="Доступные данные не устанавливают механизм этого последствия.",
                  en="The available evidence does not establish a mechanism for this outcome.")
MECH_WITHOUT_OUTCOME = Bi(
    ru="Есть гипотеза о механизме, но задокументированного последствия нет; гипотеза показана только в режиме «Исследование».",
    en="There is a mechanism hypothesis but no documented outcome; it is shown in Research mode only.")
DISAGREE = Bi(
    ru="Источники расходятся: в инструкции есть предложение об этой паре, где эффект не отмечен. Обе записи показаны; вывод из них не составлен.",
    en="The sources disagree: a label sentence about this pair reports no relevant effect. Both are shown; no combined conclusion is drawn.")
INDIVIDUAL_LIMIT = Bi(
    ru="Платформа не может определить, безопасно ли конкретное сочетание для конкретного человека. Это исследовательский и учебный инструмент.",
    en="This platform cannot determine whether a particular combination is safe for an individual. It is a research and educational tool.")


# --------------------------------------------------------------- extraction ----
def _pair_key(a: str, b: str) -> str:
    return "+".join(sorted((a, b)))


def _guarded(sentence: str, start: int, end: int | None = None) -> str | None:
    """Reason to skip a term occurrence, or None when it may be used."""
    before = sentence[max(0, start - 60):start]
    if NEGATION.search(before):
        return "negated"
    if POPULATION.search(before):
        return "population"
    if end is not None and NEGATION_AFTER.search(sentence[end:]):
        return "negated_after"
    return None


def partner_clauses(sentence: str, partner: str | None) -> str:
    """v2: the clauses (split at semicolons) that name the partner drug.

    "Warfarin is an anticoagulant; this drug alone has caused hepatitis" must
    not give hepatitis to the pair. When the partner is in no clause (matched
    under another name), the whole sentence is kept.
    """
    if not partner or not CLAUSE_BREAK.search(sentence):
        return sentence
    keep = [c for c in CLAUSE_BREAK.split(sentence) if partner.lower() in c.lower()]
    return "; ".join(keep) if keep else sentence


#: v2 split at semicolons; v4 also at list bullets (" * ", "•"), which label
#: sections flatten into one "sentence" of unrelated items.
CLAUSE_BREAK = re.compile(r";\s*|\s+\*\s+|\s*•\s*")


def comparator_arm(sentence: str, partner: str | None) -> bool:
    """v4: the partner is a trial arm compared with the label drug, not co-administered.

    "hypertension was reported in 145/359 patients (40%) receiving INLYTA and
    103/355 patients (29%) receiving sorafenib" names both drugs and an outcome,
    but states no interaction.
    """
    if not partner or CO_USE.search(sentence) or not TRIAL_STATS.search(sentence):
        return False
    return bool(re.search(rf"\b(?:receiving|received|treated with|randomi[sz]ed to|on|versus|vs\.?|compared (?:with|to))\s+(?:[\w-]+\s+){{0,3}}{re.escape(partner)}", sentence, re.IGNORECASE))


def label_terms(sentence: str, partner: str | None = None) -> list[tuple[Term, str]]:
    """Outcome terms found in a label sentence, with the matched text.

    One hit per term; negated and population-context occurrences are skipped,
    and only the clauses naming the partner are read.
    """
    sentence = partner_clauses(sentence, partner)
    if comparator_arm(sentence, partner):
        return []
    out: list[tuple[Term, str]] = []
    for term in LEXICON:
        for m in term.pattern.finditer(sentence):
            if _guarded(sentence, m.start(), m.end()) is None:
                out.append((term, m.group(0)))
                break
    noun = next((m for m in PK_NOUN.finditer(sentence) if _guarded(sentence, m.start(), m.end()) is None), None)
    if noun:
        up, down = PK_UP.search(sentence), PK_DOWN.search(sentence)
        if up and not down:
            out.append((PK_TERM_UP, f"{noun.group(0)} … {up.group(0)}"))
        elif down and not up:
            out.append((PK_TERM_DOWN, f"{noun.group(0)} … {down.group(0)}"))
    return out


PK_TERM_UP = Term("exposure_increase", PK_NOUN, "exposure_increase", "exposure_increase", PK, "Higher drug exposure", "Повышение содержания препарата")
PK_TERM_DOWN = Term("exposure_decrease", PK_NOUN, "exposure_decrease", "exposure_decrease", PK, "Lower drug exposure", "Снижение содержания препарата")


def _class_list(sentence: str, term: str) -> bool:
    i = sentence.lower().find(term.lower())
    if i < 0:
        return False
    window = sentence[max(0, i - 80): i + len(term) + 80]
    return window.count(",") >= 2


def _label_seriousness(e: EvidenceRecord, sentence: str) -> tuple[str, str | None]:
    sections = [e.section or "", *e.also_in_sections]
    for sec in sections:
        if sec in LABEL_SECTION_SERIOUSNESS:
            return LABEL_SECTION_SERIOUSNESS[sec], f"section: {sec}"
    for m in SERIOUS_WORDS.finditer(sentence):
        if _guarded(sentence, m.start()) is None:
            return "explicit_serious_warning", f"wording: “{m.group(0)}”"
    return "documented_no_standard_severity", None


@dataclass
class _Draft:
    category: str
    effect: str
    level: str
    en: str
    ru: str
    supports: list[OutcomeSupport]


def _supports_from_records(evidence: list[EvidenceRecord]) -> dict[tuple[str, str], _Draft]:
    drafts: dict[tuple[str, str], _Draft] = {}

    def add(category, effect, level, en, ru, sup: OutcomeSupport):
        key = (category, effect)
        d = drafts.setdefault(key, _Draft(category, effect, level, en, ru, []))
        if level == C and d.level != C:          # a named outcome is the strongest wording
            d.level, d.en, d.ru = level, en, ru
        d.supports.append(sup)

    for e in evidence:
        if e.category == EvidenceCategory.DATABASE_INTERACTION_RECORD:
            y = int(e.original_identifiers.get("tdc_interaction_type", "0"))
            row = TYPE_MAP.get(y)
            if row is None:
                continue
            affected = None
            if e.direction == "as_exported_verified":
                affected = e.drug2_id
            add(row.category, row.effect, row.level, row.en, row.ru, OutcomeSupport(
                evidence_record_id=e.id, source_type="drugbank_tdc", source_name=e.source_name,
                source_document_id=e.source_record_id, source_url=e.source_url, section=None,
                excerpt=e.source_template or e.statement, matched_terms=[row.key],
                extraction_method=f"{TYPE_MAP_VERSION}:type={y}",
                direction=e.direction if e.direction != "not_applicable" else "not_verified",
                affected_drug_id=affected, source_seriousness=None, retrieved_at=e.retrieved_at,
                qualifiers=["DrugBank gives no severity and does not state the basis of the record."],
            ))
        elif e.category == EvidenceCategory.REFERENCE_SET_OUTCOME:
            key = e.original_identifiers.get("effect_key", "")
            eff = REF_EFFECTS.get(key)
            if eff is None:
                continue
            add(eff.category, key, eff.level, eff.en, eff.ru, OutcomeSupport(
                evidence_record_id=e.id, source_type="reference_set", source_name=e.source_name,
                source_document_id=e.source_record_id, source_url=e.source_url, section=None,
                excerpt=e.statement, matched_terms=[e.original_identifiers.get("meddra_term", "")],
                extraction_method=f"{MEDDRA_MAP_VERSION}:meddra={e.original_identifiers.get('meddra_code', '')}",
                direction="not_applicable", affected_drug_id=None, source_seriousness=None,
                retrieved_at=e.retrieved_at, qualifiers=list(e.qualifiers),
            ))
        elif e.category in (EvidenceCategory.LABEL_CONTRAINDICATION, EvidenceCategory.LABEL_BOXED_WARNING,
                            EvidenceCategory.LABEL_WARNING_OR_INTERACTION):
            sentence = e.statement
            seriousness, basis = _label_seriousness(e, sentence)
            partner_term = e.original_identifiers.get("matched_term") or None
            for term, matched in label_terms(sentence, partner_term):
                quals = ["Found in the same label sentence that names the partner drug; the sentence is quoted as written."]
                partner = e.original_identifiers.get("matched_term", "")
                if partner and _class_list(sentence, partner):
                    quals.append("The partner drug is named in a list of drugs; the sentence may concern the whole list or class.")
                add(term.category, term.effect, term.level, term.en, term.ru, OutcomeSupport(
                    evidence_record_id=e.id, source_type="fda_label", source_name=e.source_name,
                    source_document_id=e.source_record_id, source_url=e.source_url,
                    section=", ".join([e.section or "", *e.also_in_sections]).strip(", ") or None,
                    excerpt=sentence, matched_terms=[matched],
                    extraction_method=f"{LEXICON_VERSION}:term={term.name}",
                    direction="as_stated_in_excerpt", affected_drug_id=None,
                    source_seriousness=basis if seriousness != "documented_no_standard_severity" else None,
                    retrieved_at=e.retrieved_at, qualifiers=quals,
                ))
    return drafts


def _seriousness_of(supports: list[OutcomeSupport]) -> str:
    best = "documented_no_standard_severity"
    for s in supports:
        if s.source_type != "fda_label" or not s.source_seriousness:
            continue
        cls = "documented_contraindication" if s.source_seriousness.startswith("section: CONTRAINDICATIONS") \
            else "explicit_serious_warning"
        if SERIOUSNESS_ORDER.index(cls) < SERIOUSNESS_ORDER.index(best):
            best = cls
    return best


def _seriousness_basis(cls: str, supports: list[OutcomeSupport]) -> Bi:
    if cls in ("documented_contraindication", "explicit_serious_warning"):
        quoted = sorted({s.source_seriousness for s in supports if s.source_seriousness})
        base = SERIOUSNESS_TEXT[cls]
        return Bi(ru=f"{base.ru} Основание: {'; '.join(quoted)}.", en=f"{base.en} Basis: {'; '.join(quoted)}.")
    if cls == "documented_no_standard_severity" and any(s.source_type == "reference_set" for s in supports):
        base = SERIOUSNESS_TEXT[cls]
        return Bi(ru=f"{base.ru} Справочники, на которых основан CRESCENDDI, оценивают тяжесть, но их оценки здесь не воспроизводятся.",
                  en=f"{base.en} The compendia behind CRESCENDDI grade severity, but their grades are not reproduced here.")
    return SERIOUSNESS_TEXT[cls]


def _strength(supports: list[OutcomeSupport]) -> str:
    kinds = {s.source_type for s in supports}
    if "reference_set" in kinds:
        return "reference_set_and_other" if kinds & {"fda_label", "drugbank_tdc"} else "reference_set_statement"
    if {"fda_label", "drugbank_tdc"} <= kinds:
        return "label_and_database"
    if "fda_label" in kinds:
        return "official_label_statement"
    if "drugbank_tdc" in kinds:
        return "database_standard_sentence"
    return "annotation_hypothesis"


def _n_documents(supports: list[OutcomeSupport]) -> int:
    docs = set()
    for s in supports:
        if s.source_type in ("drugbank_tdc", "reference_set"):
            docs.add(s.source_type)        # one export / one reference set, however many records
        elif s.source_document_id:
            docs.add(s.source_document_id)
    return len(docs)


# ------------------------------------------------------------------ mechanism ----
PK_PATTERNS = {"inhibitor_substrate": "up", "inducer_substrate": "down"}


def _names(store, drug_id: str) -> Bi:
    e = store.lexicon.by_id[drug_id]
    cap = lambda x: x[:1].upper() + x[1:]
    return Bi(ru=cap(e.display("ru")), en=cap(e.display("en")))


def _exposure_direction(findings, record_ids: set[str]) -> dict[str, set[str]]:
    """For documented exposure records: which drug the annotations say is affected.

    Returns {"up": {affected ids}, "down": {...}} from inhibitor/inducer–substrate
    findings that the mechanism module found consistent with a record.
    """
    out: dict[str, set[str]] = {"up": set(), "down": set()}
    for f in findings:
        d = PK_PATTERNS.get(f.pattern)
        if d and f.affected_drug_id and set(f.consistent_with_records) & record_ids:
            out[d].add(f.affected_drug_id)
    return out


# ------------------------------------------------------------------ assembly ----
def build_outcomes(store, a: str, b: str, evidence: list[EvidenceRecord], mech: MechanismBlock,
                   model: ModelBlock, checks: list[SourceCheck]) -> OutcomeReport:
    key = _pair_key(a, b)
    drafts = _supports_from_records(evidence)
    findings = [f for f in mech.findings if f.pattern in PK_PATTERNS and f.relation in ("enzyme", "transporter")]

    outcomes: list[ClinicalOutcome] = []
    for (category, effect), d in drafts.items():
        status = "documented"
        affected = None
        direction_note = Bi(ru="Какой из препаратов затронут, источник не указывает (или порядок не проверен); отчёт его не называет.",
                            en="The source does not say which drug is affected (or its order is unverified); the report does not name one.")
        if any(s.direction == "as_stated_in_excerpt" for s in d.supports):
            direction_note = Bi(ru="Направление — только так, как сказано в процитированном предложении; отчёт его не выводит.",
                                en="Direction only as stated in the quoted sentence; the report infers none.")
        verified = {s.affected_drug_id for s in d.supports if s.affected_drug_id}
        if len(verified) == 1:
            affected = verified.pop()
            direction_note = Bi(ru=f"Затронут препарат «{_names(store, affected).ru}»: порядок препаратов для этого типа записей проверен.",
                                en=f"Affected drug: {_names(store, affected).en} — the drug order for this record type is verified.")
        elif d.level == PK and category in ("exposure_increase", "exposure_decrease"):
            rec_ids = {s.evidence_record_id for s in d.supports if s.evidence_record_id}
            by_dir = _exposure_direction(findings, rec_ids)
            cand = by_dir["up" if category == "exposure_increase" else "down"]
            if len(cand) == 1:
                affected = next(iter(cand))
                status = "mechanistically_supported"
                direction_note = Bi(
                    ru=f"Затронут, по ролям белков, препарат «{_names(store, affected).ru}». Это следует из аннотаций (ингибитор/индуктор и субстрат), а не из порядка в записи DrugBank.",
                    en=f"By the protein roles, the affected drug is {_names(store, affected).en}. This comes from the annotations (inhibitor/inducer and substrate), not from the DrugBank record's order.")
        cls = _seriousness_of(d.supports)
        strength = _strength(d.supports)
        lims = []
        if d.level == PD:
            lims.append(Bi(ru="Описано изменение действия, а не наступление вреда.",
                           en="A change in effect is described, not that harm occurs."))
        if d.level == PK:
            lims.append(Bi(ru="Изменение концентрации само по себе не задокументированное клиническое последствие.",
                           en="A change in concentration is not, by itself, a documented clinical outcome."))
        if any("list of drugs" in q for s in d.supports for q in s.qualifiers):
            lims.append(Bi(ru="Препарат назван в перечне; утверждение может относиться ко всей группе.",
                           en="The drug is named in a list; the statement may concern the whole group."))
        outcomes.append(ClinicalOutcome(
            id=f"outcome:{key}:{category}:{effect}", drug_a=a, drug_b=b, category=category, effect=effect,
            effect_level=d.level, label=Bi(ru=d.ru, en=d.en), explanation=REF_CLINICAL_TEXT if (d.level == C and all(s.source_type == "reference_set" for s in d.supports)) else LEVEL_TEXT[d.level],
            evidence_status=status, supports=d.supports, n_source_documents=_n_documents(d.supports),
            affected_drug_id=affected, direction_note=direction_note,
            seriousness=cls, seriousness_basis=_seriousness_basis(cls, d.supports),
            evidence_strength=strength, evidence_strength_text=STRENGTH_TEXT[strength],
            extraction_note=EXTRACTION_NOTES.get(_method_family(d.supports)), limitations=lims,
        ))

    # Hypotheses: inhibitor/inducer–substrate findings with no documented exposure change.
    documented_exposure = {o.category for o in outcomes if o.category in ("exposure_increase", "exposure_decrease")}
    hyp_seen: set[str] = set()
    for f in findings:
        cat = "exposure_increase" if PK_PATTERNS[f.pattern] == "up" else "exposure_decrease"
        if cat in documented_exposure:
            continue
        hid = f"outcome:{key}:{cat}:hypothesis:{f.affected_drug_id}"
        sup = OutcomeSupport(
            evidence_record_id=None, source_type="annotation", source_name="DrugBank / ChEMBL drug–protein annotations",
            source_document_id=f.id, section=None,
            excerpt=f"{f.protein.gene} ({f.relation}): roles A — {', '.join(f.roles_a)}; roles B — {', '.join(f.roles_b)}",
            matched_terms=[f.pattern], extraction_method=f"{ANNOTATION_METHOD}:{f.pattern}",
            direction="from_annotation", affected_drug_id=f.affected_drug_id,
        )
        if hid in hyp_seen:
            next(o for o in outcomes if o.id == hid).supports.append(sup)
            continue
        hyp_seen.add(hid)
        nm = _names(store, f.affected_drug_id)
        up = cat == "exposure_increase"
        outcomes.append(ClinicalOutcome(
            id=hid, drug_a=a, drug_b=b, category=cat, effect="exposure_hypothesis",
            effect_level=PK,
            label=Bi(ru=("Возможно повышение" if up else "Возможно снижение") + f" содержания препарата «{nm.ru}» (гипотеза)",
                     en=("Possible higher" if up else "Possible lower") + f" exposure of {nm.en} (hypothesis)"),
            explanation=Bi(ru="Собрано из ролей каждого препарата по отдельности; для этой пары не задокументировано.",
                           en="Assembled from each drug's separate roles; not documented for this pair."),
            evidence_status="hypothesized", supports=[sup], n_source_documents=0,
            affected_drug_id=f.affected_drug_id,
            direction_note=Bi(ru="Направление гипотезы — по ролям белков.", en="The hypothesis's direction comes from the protein roles."),
            seriousness="not_applicable", seriousness_basis=SERIOUSNESS_TEXT["not_applicable"],
            evidence_strength="annotation_hypothesis", evidence_strength_text=STRENGTH_TEXT["annotation_hypothesis"],
            limitations=[Bi(ru="Сила подавления и доля участия белка неизвестны.",
                            en="The strength of inhibition and the protein's share of the work are unknown.")],
            research_only=True,
        ))

    level_rank = {C: 0, PD: 1, RE: 2, PK: 3, UA: 4}
    status_rank = {"documented": 0, "mechanistically_supported": 1, "hypothesized": 2}
    outcomes.sort(key=lambda o: (status_rank[o.evidence_status], level_rank[o.effect_level],
                                 SERIOUSNESS_ORDER.index(o.seriousness), o.category, o.effect))

    chains = _chains(store, findings, outcomes)
    for o in outcomes:
        if o.evidence_status == "documented" and o.effect_level != PK and not any(o.id in c.outcome_ids for c in chains):
            o.limitations.append(NO_MECHANISM)

    # Sources that disagree: a label sentence reports no relevant effect for the
    # pair while another source documents one. Both stay visible; neither wins.
    no_effect = [e for e in evidence if e.category == EvidenceCategory.LABEL_MENTION_NO_EFFECT_REPORTED]
    if no_effect:
        for o in outcomes:
            if o.evidence_status != "hypothesized":
                o.limitations.append(DISAGREE)

    status = _interaction_status(evidence, outcomes, chains, checks)
    shown = [o for o in outcomes if not o.research_only]
    pair_ser = min((o.seriousness for o in shown), key=SERIOUSNESS_ORDER.index, default="not_applicable")
    label, hint = STATUS_TEXT[status]
    report = OutcomeReport(
        interaction_status=status, interaction_status_label=label, interaction_status_hint=hint,
        outcomes=outcomes, chains=chains, seriousness=pair_ser,
        seriousness_text=SERIOUSNESS_TEXT[pair_ser] if pair_ser != "not_applicable" else
        Bi(ru="Неприменимо: задокументированного последствия нет. Это не означает, что сочетание безопасно.",
           en="Not applicable: no documented outcome. This does not mean the combination is safe."),
        coverage=_coverage(evidence, checks, mech),
        no_outcome_text=NO_OUTCOME if not shown else None,
        no_specific_outcome_text=NO_SPECIFIC_OUTCOME if not any(o.effect_level == C for o in shown) else None,
        mechanism_without_outcome_text=MECH_WITHOUT_OUTCOME if (not shown and chains) else None,
        individual_limit=INDIVIDUAL_LIMIT,
    )
    _validate(report)
    return report


def _method_family(supports: list[OutcomeSupport]) -> str:
    if any(s.source_type == "fda_label" for s in supports):
        return LEXICON_VERSION
    if any(s.source_type == "reference_set" for s in supports):
        return MEDDRA_MAP_VERSION
    return TYPE_MAP_VERSION


#: Extraction quality of the label rules, shown beside every label-derived
#: outcome (website, Quick and Full PDF, JSON). Describes the rules, never the
#: probability that an outcome occurs.
EXTRACTION_NOTES: dict[str, Bi] = {
    # Numbers: reports/v3_real_label_benchmark_evaluation.md (held-out, rules
    # frozen before annotation) and reports/v3_reference_validation.md (DDI Corpus).
    LEXICON_VERSION: Bi(
        ru="Последствие найдено автоматическими правилами в тексте инструкции (label_lexicon/v4), а не прочитано человеком. "
           "На отложенном наборе исторических инструкций FDA с внутренней (не независимой) разметкой проекта совпали с "
           "разметкой 40 из 45 найденных последствий; последствие получили 38 из 55 описанных в инструкциях взаимодействий. "
           "На тестовой части DDI Corpus 2013 — 50 из 61. Проверьте процитированное предложение. Это не клиническая "
           "валидация и не вероятность того, что последствие наступит.",
        en="Found by automatic text rules in the label (label_lexicon/v4), not read by a person. On held-out historical FDA "
           "labels annotated internally by the project (not independently), 40 of 45 extracted outcomes matched the "
           "annotation, and 38 of 55 label-stated interactions were given an outcome; on the DDI Corpus 2013 test part, "
           "50 of 61. Check the quoted sentence. Not a clinical validation and not a probability that the outcome occurs."),
}


def _interaction_status(evidence, outcomes, chains, checks) -> str:
    real = [e for e in evidence if e.category != EvidenceCategory.LABEL_MENTION_NO_EFFECT_REPORTED]
    documented = [o for o in outcomes if o.evidence_status in ("documented", "mechanistically_supported")]
    if real:
        if any(o.effect_level in (C, PD, RE) for o in documented):
            return "documented_interaction"
        return "documented_outcome_unclear"
    if any(c.status == "unavailable" for c in checks):
        return "source_unavailable"
    if chains:
        return "research_prediction_only"
    return "insufficient_evidence"


def _coverage(evidence, checks, mech) -> list[Bi]:
    out: list[Bi] = []
    for c in checks:
        if c.source == "drugbank_tdc":
            n = sum(e.category == EvidenceCategory.DATABASE_INTERACTION_RECORD for e in evidence)
            out.append(Bi(ru=f"DrugBank (локальная выгрузка TDC): записей для пары — {n}. Степень тяжести и основание записей не указаны.",
                          en=f"DrugBank (local TDC export): {n} record(s) for the pair. No severity and no stated basis."))
        elif c.source == "crescenddi":
            n = sum(e.category == EvidenceCategory.REFERENCE_SET_OUTCOME for e in evidence)
            out.append(Bi(ru=f"Справочный набор CRESCENDDI (BNF, Micromedex, ANSM; 2018–2019): записей «пара — явление» — {n}. Охватывает только пары, общие для трёх справочников.",
                          en=f"CRESCENDDI reference set (BNF, Micromedex, ANSM; 2018–2019): {n} pair–event record(s). It covers only pairs common to all three compendia."))
        elif c.source == "openfda_label":
            txt = {"ok": ("инструкции FDA проверены", "FDA labels checked"),
                   "no_match": ("инструкции FDA проверены, другой препарат по названию не найден", "FDA labels checked, partner not named"),
                   "unavailable": ("инструкции FDA сейчас недоступны — их данные в анализ не вошли", "FDA labels unavailable now — not part of this analysis"),
                   "disabled": ("инструкции FDA не подключены", "FDA labels not connected"),
                   "not_applicable": ("инструкции FDA неприменимы (нет международного названия)", "FDA labels not applicable (no international name)")}[c.status]
            out.append(Bi(ru=txt[0][0].upper() + txt[0][1:] + ". Ищутся названия препаратов, не группы; раздел «Нежелательные реакции» не используется.",
                          en=txt[1][0].upper() + txt[1][1:] + ". Drug names are searched, not classes; Adverse Reactions sections are not used."))
    cov = mech.coverage
    if any(sum(v.values()) == 0 for v in cov.values()):
        out.append(Bi(ru="У одного из препаратов нет аннотаций белков: механизм оценить нельзя.",
                      en="One drug has no protein annotations: no mechanism can be assessed."))
    return out


# --------------------------------------------------------------------- chains ----
def _chains(store, findings, outcomes: list[ClinicalOutcome]) -> list[MechanismChain]:
    by_id = {o.id: o for o in outcomes}
    chains: list[MechanismChain] = []
    for f in findings:
        up = PK_PATTERNS[f.pattern] == "up"
        actor, affected = f.actor_drug_id, f.affected_drug_id
        an, af = _names(store, actor), _names(store, affected)
        exp_cat = "exposure_increase" if up else "exposure_decrease"
        exp_all = [o for o in outcomes if o.category == exp_cat and o.evidence_status in ("documented", "mechanistically_supported")]
        # Documented for THIS drug only when the documented change names it
        # (verified order or unambiguous annotations); a change of "one of the
        # two drugs" does not establish which.
        exp_doc = [o for o in exp_all if o.affected_drug_id == affected]
        exp_unresolved = [o for o in exp_all if o.affected_drug_id is None]
        # Which drug changes is DOCUMENTED only when a source names it (verified
        # record order or a label sentence). When it was read off these same
        # protein roles ("mechanistically_supported"), the change is documented
        # but its attribution is annotation-derived, and the link says so.
        exp_by_roles = bool(exp_doc) and all(o.evidence_status == "mechanistically_supported" for o in exp_doc)
        effect_id = f"effect:{affected}:{'up' if up else 'down'}"
        nodes = [
            ChainNode(id=f"drug:{actor}", kind="drug", label=an, ref=actor),
            ChainNode(id=f"protein:{f.protein.uniprot}", kind="protein",
                      label=Bi(ru=f"{f.protein.gene} ({'фермент' if f.relation == 'enzyme' else 'переносчик'})",
                               en=f"{f.protein.gene} ({f.relation})"), ref=f.id),
            ChainNode(id=effect_id, kind="effect",
                      label=Bi(ru=("Больше" if up else "Меньше") + f" препарата «{af.ru}» в организме",
                               en=("Higher" if up else "Lower") + f" exposure of {af.en}"),
                      ref=exp_doc[0].id if exp_doc else None),
        ]
        role = "inhibitor" if up else "inducer"
        links = [
            ChainLink(source=nodes[0].id, target=nodes[1].id, relation=role, provenance="verified_annotation",
                      text=Bi(ru=f"«{an.ru}» отмечен как {'ингибитор' if up else 'индуктор'} {f.protein.gene}.",
                              en=f"{an.en} is annotated as an {role} of {f.protein.gene}."), refs=list(f.annotation_ids)),
            ChainLink(source=nodes[1].id, target=f"drug:{affected}", relation="substrate", provenance="verified_annotation",
                      text=Bi(ru=f"«{af.ru}» отмечен как субстрат {f.protein.gene}.", en=f"{af.en} is annotated as a substrate of {f.protein.gene}."),
                      refs=list(f.annotation_ids)),
            ChainLink(source=nodes[1].id, target=effect_id, relation="exposure_change",
                      provenance="verified_annotation" if exp_by_roles else "documented" if exp_doc else "plausible_unconfirmed",
                      text=Bi(ru=("Задокументировано изменение концентрации одного из двух препаратов; что это этот препарат, следует из ролей белков (аннотации), а не из источника." if exp_by_roles
                                  else "Изменение концентрации этого препарата для пары задокументировано." if exp_doc
                                  else "Задокументировано изменение концентрации одного из двух препаратов; что это именно этот препарат, не установлено." if exp_unresolved
                                  else "Изменение концентрации правдоподобно, но для этой пары не подтверждено."),
                              en=("A change in exposure of one of the two drugs is documented; that it is this drug follows from the protein roles (annotations), not from the source." if exp_by_roles
                                  else "A change in this drug's exposure is documented for the pair." if exp_doc
                                  else "A change in exposure of one of the two drugs is documented; that it is this drug is not established." if exp_unresolved
                                  else "A change in exposure is plausible but not confirmed for this pair.")),
                      refs=[o.id for o in exp_doc + exp_unresolved]),
        ]
        nodes.insert(2, ChainNode(id=f"drug:{affected}", kind="drug", label=af, ref=affected))
        outcome_ids = [o.id for o in exp_doc + exp_unresolved]
        # Exposure change -> clinical outcomes documented for the pair.
        for o in outcomes:
            if o.evidence_status != "documented" or o.effect_level == PK or o.category in ("exposure_increase", "exposure_decrease"):
                continue
            fits = (up and o.effect_level in (C, PD, UA) and not o.effect.endswith("_decrease")) or \
                   (not up and o.effect_level == RE)
            if not fits:
                continue
            # Documented link only when ONE label sentence states both the exposure
            # change and this outcome; otherwise the route is unconfirmed.
            rec_o = {s.evidence_record_id for s in o.supports if s.source_type == "fda_label"}
            rec_e = {s.evidence_record_id for e in exp_doc for s in e.supports if s.source_type == "fda_label"}
            same_sentence = bool(rec_o & rec_e)
            nodes.append(ChainNode(id=f"outcome:{o.id}", kind="outcome", label=o.label, ref=o.id))
            links.append(ChainLink(
                source=effect_id, target=f"outcome:{o.id}", relation="may_lead_to",
                provenance="documented" if same_sentence else "plausible_unconfirmed",
                text=Bi(ru=("Одно предложение инструкции называет и изменение концентрации, и это последствие." if same_sentence
                            else "Последствие задокументировано для пары, но то, что оно вызвано именно этим путём, не подтверждено."),
                        en=("One label sentence names both the exposure change and this outcome." if same_sentence
                            else "The outcome is documented for the pair, but that it arises through this route is not confirmed.")),
                refs=[o.id]))
            outcome_ids.append(o.id)
        research_only = not any(by_id[i].evidence_status in ("documented", "mechanistically_supported") for i in outcome_ids if i in by_id)
        documented_effect = bool(exp_doc) and not exp_by_roles
        unconfirmed_route = [lk for lk in links if lk.relation == "may_lead_to" and lk.provenance != "documented"]
        summary = Bi(
            ru=(f"«{an.ru}» подавляет" if up else f"«{an.ru}» усиливает выработку") + f" {f.protein.gene}, а «{af.ru}» этим белком перерабатывается (аннотации). "
               + ("Изменение концентрации этого препарата для пары задокументировано." if documented_effect else
                  "Задокументировано изменение концентрации одного из препаратов; что это этот препарат, следует из ролей белков." if exp_by_roles else
                  "Задокументировано изменение концентрации одного из препаратов, но не какого именно." if exp_unresolved else
                  "Изменение концентрации — гипотеза.")
               + (" То, что задокументированное последствие возникает именно этим путём, не подтверждено." if unconfirmed_route else ""),
            en=f"{an.en} {'inhibits' if up else 'induces'} {f.protein.gene}, which processes {af.en} (annotations). "
               + ("This drug's exposure change is documented for the pair." if documented_effect else
                  "An exposure change of one of the drugs is documented; that it is this drug follows from the protein roles." if exp_by_roles else
                  "An exposure change of one of the drugs is documented, but not which." if exp_unresolved else
                  "The exposure change is a hypothesis.")
               + (" That the documented outcome arises through this route is not confirmed." if unconfirmed_route else ""))
        chains.append(MechanismChain(id=f"chain:{f.id}", nodes=nodes, links=links, outcome_ids=outcome_ids,
                                     research_only=research_only, summary=summary))
    return chains


def _validate(report: OutcomeReport) -> None:
    texts: list[str] = [report.interaction_status_label.en, report.interaction_status_label.ru,
                        report.interaction_status_hint.en, report.interaction_status_hint.ru]
    for o in report.outcomes:
        assert o.supports, f"outcome without support: {o.id}"
        for s in o.supports:
            assert s.excerpt.strip(), f"empty excerpt in {o.id}"
        if o.evidence_status == "hypothesized":
            assert o.research_only and o.seriousness == "not_applicable", o.id
        for bi in (o.label, o.explanation, o.direction_note, o.seriousness_basis, *o.limitations):
            texts += [bi.en, bi.ru]
    for t in texts:
        for pat in _FORBIDDEN:
            if pat.search(t):
                raise AssertionError(f"forbidden wording {pat.pattern!r} in outcome text: {t!r}")
