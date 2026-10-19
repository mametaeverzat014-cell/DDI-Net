"""Reference-set evidence: CRESCENDDI positive controls as pair-specific outcomes.

A CRESCENDDI positive control states that a drug pair is documented as
interacting in three clinical compendia (BNF, Micromedex, ANSM Thesaurus) and
names the adverse event the authors mapped (MedDRA preferred term) from the BNF
and/or Micromedex interaction description. It is therefore a pair-specific,
source-attributed outcome — not a co-mention and not a disproportionality
signal.

Shown for each record: the MedDRA term exactly as given by CRESCENDDI, which
compendium text it was mapped from, and the citation. Not shown: the compendia's
severity and evidence ratings (proprietary editorial classifications; they are
not in the derived index at all) and any compendium text (CRESCENDDI has none).

The MedDRA term is grouped into the engine's outcome effects by a fixed,
versioned table (MEDDRA_MAP_VERSION). v2 (2026-10-18) stops grouping a term
under a broader or different outcome than it names: syncope is no longer
"low blood pressure", raised creatinine / liver enzymes are no longer "kidney /
liver injury", an abnormal ECG is no longer an arrhythmia, and haemodynamic
measures are pharmacodynamic changes, not outcomes (review table:
docs/DATASET_AUDIT.md). Every one of the 179 terms in the data is
listed; an unknown term falls back to "other documented adverse event" rather
than being guessed. The table only groups terms; it never adds an outcome the
record does not name.
"""

from __future__ import annotations

from dataclasses import dataclass

from .schema import EvidenceCategory, EvidenceRecord

MEDDRA_MAP_VERSION = "meddra_effect_map/v2"
C, PD, RE, UA = "clinical_outcome", "pharmacodynamic_effect", "reduced_effectiveness", "unspecified_adverse"


@dataclass(frozen=True)
class Effect:
    category: str
    level: str
    en: str
    ru: str


#: Effect groups. Keys shared with the DrugBank type map and the label lexicon
#: (bleeding, qt_prolongation, hyperkalemia, ...) merge with those sources'
#: outcomes for the same pair; the rest are reference-set groups.
EFFECTS: dict[str, Effect] = {
    "bleeding": Effect("bleeding_coagulation", C, "Bleeding", "Кровотечение"),
    "coagulation_measure_change": Effect("bleeding_coagulation", PD, "Change in a blood-clotting measure (prothrombin time / INR)", "Изменение показателя свёртываемости (протромбиновое время / МНО)"),
    "qt_prolongation": Effect("cardiac_rhythm", C, "QT prolongation or ventricular arrhythmia", "Удлинение интервала QT или желудочковая аритмия"),
    "arrhythmia_other": Effect("cardiac_rhythm", C, "Other heart rhythm disturbance (arrhythmia, tachycardia, palpitations)", "Другие нарушения ритма сердца (аритмия, тахикардия, сердцебиение)"),
    "ecg_change": Effect("cardiac_rhythm", PD, "ECG change (abnormal ECG, shortened AV conduction time)", "Изменение ЭКГ (отклонения на ЭКГ, укорочение АВ-проведения)"),
    "syncope": Effect("cardiovascular_other", C, "Fainting (syncope)", "Обморок (синкопе)"),
    "haemodynamic_measure": Effect("blood_pressure", PD, "Change in a haemodynamic measure (cardiac output, systemic vascular resistance)", "Изменение гемодинамического показателя (сердечный выброс, периферическое сопротивление сосудов)"),
    "bradycardia_conduction": Effect("cardiac_rhythm", C, "Slow heart rate or heart block", "Урежение пульса или блокада проводимости сердца"),
    "cardiac_arrest": Effect("cardiovascular_other", C, "Cardiac arrest or circulatory collapse", "Остановка сердца или сосудистый коллапс"),
    "heart_failure": Effect("cardiovascular_other", C, "Heart failure or reduced heart function", "Сердечная недостаточность или снижение функции сердца"),
    "cardiotoxicity": Effect("cardiovascular_other", C, "Cardiotoxicity", "Кардиотоксичность"),
    "ischaemia_vasoconstriction": Effect("cardiovascular_other", C, "Vasoconstriction or peripheral ischaemia (incl. ergotism)", "Сужение сосудов или периферическая ишемия (в т. ч. эрготизм)"),
    "embolism": Effect("cardiovascular_other", C, "Embolism", "Эмболия"),
    "oedema": Effect("cardiovascular_other", C, "Oedema", "Отёки"),
    "hypotension": Effect("blood_pressure", C, "Low blood pressure", "Снижение давления"),
    "hypertension": Effect("blood_pressure", C, "High blood pressure", "Повышение давления"),
    "respiratory_depression": Effect("respiratory_depression", C, "Respiratory depression", "Угнетение дыхания"),
    "sedation_cns_depression": Effect("cns_sedation", C, "Sedation or CNS depression", "Седация или угнетение ЦНС"),
    "seizure": Effect("nervous_system_other", C, "Seizures", "Судороги"),
    "movement_disorder": Effect("nervous_system_other", C, "Movement or coordination disorder (myoclonus, tremor, rigidity, ataxia)", "Двигательные нарушения и нарушения координации (миоклонус, тремор, ригидность, атаксия)"),
    "mental_status": Effect("nervous_system_other", C, "Change in mental state or behaviour (e.g. confusion, delirium, agitation, anxiety, insomnia)", "Изменение психического состояния или поведения (например, спутанность, делирий, возбуждение, тревога, бессонница)"),
    "neurotoxicity": Effect("nervous_system_other", C, "Neurotoxicity or encephalopathy", "Нейротоксичность или энцефалопатия"),
    "intracranial_hypertension": Effect("nervous_system_other", C, "Raised intracranial pressure", "Повышение внутричерепного давления"),
    "neuropathy": Effect("nervous_system_other", C, "Peripheral neuropathy or paraesthesia", "Периферическая нейропатия или парестезии"),
    "neuromuscular_weakness": Effect("nervous_system_other", C, "Prolonged neuromuscular block, paralysis or muscle weakness", "Затянувшаяся нервно-мышечная блокада, паралич или мышечная слабость"),
    "ototoxicity": Effect("nervous_system_other", C, "Hearing damage or tinnitus", "Поражение слуха или шум в ушах"),
    "dizziness_headache": Effect("nervous_system_other", C, "Dizziness, vertigo or headache", "Головокружение или головная боль"),
    "withdrawal": Effect("nervous_system_other", C, "Drug withdrawal syndrome", "Синдром отмены"),
    "visual": Effect("general_other", C, "Eye or vision problem", "Нарушения со стороны глаз или зрения"),
    "kidney_injury": Effect("kidney", C, "Kidney injury or toxicity", "Поражение почек"),
    "creatinine_increase": Effect("kidney", C, "Raised blood creatinine", "Повышение креатинина в крови"),
    "liver_injury": Effect("liver", C, "Liver injury or toxicity", "Поражение печени"),
    "liver_enzyme_increase": Effect("liver", C, "Raised liver enzymes (transaminases)", "Повышение печёночных ферментов (трансаминаз)"),
    "cholelithiasis": Effect("liver", C, "Gallstones", "Желчнокаменная болезнь"),
    "myelosuppression": Effect("bone_marrow_immune", C, "Suppressed blood cell production (low white cells, platelets or anaemia)", "Угнетение кроветворения (снижение лейкоцитов, тромбоцитов или анемия)"),
    "myopathy_rhabdomyolysis": Effect("muscle", C, "Myopathy or rhabdomyolysis", "Миопатия или рабдомиолиз"),
    "tendon_rupture": Effect("muscle", C, "Tendon rupture", "Разрыв сухожилия"),
    "hyperkalemia": Effect("electrolyte", C, "High potassium (hyperkalemia)", "Повышение калия (гиперкалиемия)"),
    "hypokalemia": Effect("electrolyte", C, "Low potassium (hypokalemia)", "Снижение калия (гипокалиемия)"),
    "hyponatremia": Effect("electrolyte", C, "Low sodium (hyponatremia)", "Снижение натрия (гипонатриемия)"),
    "hypomagnesemia": Effect("electrolyte", C, "Low magnesium", "Снижение магния"),
    "hypocalcaemia": Effect("electrolyte", C, "Low calcium", "Снижение кальция"),
    "acid_base": Effect("electrolyte", C, "Acid–base disturbance (acidosis or alkalosis)", "Нарушение кислотно-щелочного равновесия (ацидоз или алкалоз)"),
    "hypoglycemia": Effect("glucose", C, "Low blood glucose (hypoglycemia)", "Снижение глюкозы (гипогликемия)"),
    "hyperglycaemia": Effect("glucose", C, "High blood glucose", "Повышение глюкозы"),
    "insulin_requirement_increase": Effect("glucose", RE, "Higher insulin requirement", "Повышение потребности в инсулине"),
    "gi_bleeding_ulceration": Effect("gastrointestinal", C, "Gastrointestinal ulceration or perforation", "Язвы или перфорация желудочно-кишечного тракта"),
    "gi_upset": Effect("gastrointestinal", C, "Nausea, vomiting, diarrhoea or gastrointestinal toxicity", "Тошнота, рвота, диарея или токсическое действие на ЖКТ"),
    "ileus_constipation": Effect("gastrointestinal", C, "Ileus or constipation", "Кишечная непроходимость или запор"),
    "pancreatitis": Effect("gastrointestinal", C, "Pancreatitis", "Панкреатит"),
    "bronchospasm": Effect("respiratory_airway", C, "Bronchospasm", "Бронхоспазм"),
    "pulmonary_toxicity": Effect("respiratory_airway", C, "Lung toxicity", "Токсическое поражение лёгких"),
    "breathing_rate": Effect("respiratory_airway", C, "Rapid breathing", "Учащённое дыхание"),
    "hypersensitivity_reaction": Effect("hypersensitivity_skin", C, "Hypersensitivity reaction or angioedema", "Реакция гиперчувствительности или ангионевротический отёк"),
    "hyperthermia": Effect("general_other", C, "High body temperature (fever or hyperthermia)", "Повышение температуры тела (лихорадка или гипертермия)"),
    "endocrine_change": Effect("general_other", C, "Hormonal change (cortisol, Cushing's syndrome, thyroid, catecholamines, endometrium)", "Гормональные изменения (кортизол, синдром Кушинга, щитовидная железа, катехоламины, эндометрий)"),
    "other_symptom": Effect("general_other", C, "Other documented symptom", "Другой задокументированный симптом"),
    "pathogen_resistance": Effect("reduced_effectiveness", RE, "Pathogen resistance (loss of antimicrobial effect)", "Устойчивость возбудителя (потеря противомикробного действия)"),
    "drug_toxicity": Effect("adverse_unspecified", UA, "Toxicity of one of the drugs (not specified)", "Токсическое действие одного из препаратов (не уточнено)"),
}

_GROUPS: dict[str, tuple[str, ...]] = {
    "bleeding": ("Haemorrhage", "Gastrointestinal haemorrhage"),
    "coagulation_measure_change": ("International normalised ratio increased", "International normalised ratio decreased",
                                   "Coagulation time prolonged", "Coagulation time shortened",
                                   "Prothrombin time ratio increased", "Prothrombin time shortened"),
    "qt_prolongation": ("Electrocardiogram QT prolonged", "Torsade de pointes", "Ventricular arrhythmia", "Ventricular tachycardia"),
    "arrhythmia_other": ("Arrhythmia", "Tachycardia", "Palpitations"),
    "ecg_change": ("Electrocardiogram abnormal", "Atrioventricular conduction time shortened"),
    "syncope": ("Syncope",),
    "haemodynamic_measure": ("Cardiac output decreased", "Vascular resistance systemic decreased"),
    "bradycardia_conduction": ("Bradycardia", "Sinus bradycardia", "Heart rate decreased", "Atrioventricular block",
                               "Atrioventricular block complete", "Sinus arrest"),
    "cardiac_arrest": ("Cardiac arrest", "Circulatory collapse"),
    "heart_failure": ("Cardiac failure", "Cardiac failure congestive", "Myocardial depression"),
    "cardiotoxicity": ("Cardiotoxicity",),
    "ischaemia_vasoconstriction": ("Peripheral ischaemia", "Vasoconstriction", "Ergot poisoning"),
    "embolism": ("Embolism",),
    "oedema": ("Oedema", "Oedema peripheral"),
    "hypotension": ("Hypotension", "Blood pressure decreased", "Orthostatic hypotension", "Orthostatic intolerance",
                    "Mean arterial pressure decreased"),
    "hypertension": ("Hypertension", "Blood pressure increased", "Hypertensive crisis", "Withdrawal hypertension",
                     "Procedural hypertension"),
    "respiratory_depression": ("Respiratory depression", "Apnoea"),
    "sedation_cns_depression": ("Sedation", "Sedation complication", "Somnolence", "Depressed level of consciousness",
                                "Altered state of consciousness", "Coma", "Lethargy"),
    "seizure": ("Seizure",),
    "movement_disorder": ("Myoclonus", "Tremor", "Hyperreflexia", "Dyskinesia", "Extrapyramidal disorder",
                          "Cogwheel rigidity", "Musculoskeletal stiffness", "Ataxia", "Coordination abnormal",
                          "Gait disturbance", "Nystagmus"),
    "mental_status": ("Mental status changes", "Confusional state", "Delirium", "Cognitive disorder", "Amnesia",
                      "Acute psychosis", "Abnormal behaviour", "Agitation", "Anxiety", "Irritability", "Mood altered",
                      "Insomnia", "Screaming"),
    "neurotoxicity": ("Neurotoxicity", "Encephalopathy", "Brain injury"),
    "intracranial_hypertension": ("Idiopathic intracranial hypertension",),
    "neuropathy": ("Neuropathy peripheral", "Paraesthesia"),
    "neuromuscular_weakness": ("Neuromuscular block prolonged", "Neuromuscular blockade", "Paralysis",
                               "Muscular weakness", "Hypotonia"),
    "ototoxicity": ("Ototoxicity", "Deafness", "Tinnitus"),
    "dizziness_headache": ("Dizziness", "Vertigo", "Headache"),
    "withdrawal": ("Drug withdrawal syndrome",),
    "visual": ("Visual impairment", "Blindness", "Diplopia", "Photophobia", "Eye pain", "Uveitis"),
    "kidney_injury": ("Acute kidney injury", "Renal impairment", "Nephropathy toxic"),
    "creatinine_increase": ("Blood creatinine increased",),
    "liver_injury": ("Hepatotoxicity", "Drug-induced liver injury", "Hepatic failure", "Cholestasis"),
    "liver_enzyme_increase": ("Hepatic enzyme increased", "Alanine aminotransferase increased"),
    "cholelithiasis": ("Cholelithiasis",),
    "myelosuppression": ("Bone marrow failure", "Bone marrow toxicity", "Haematotoxicity", "Leukopenia", "Neutropenia",
                         "Thrombocytopenia", "Pancytopenia", "Anaemia", "Anaemia megaloblastic"),
    "myopathy_rhabdomyolysis": ("Myopathy", "Rhabdomyolysis"),
    "tendon_rupture": ("Tendon rupture",),
    "hyperkalemia": ("Hyperkalaemia", "Blood potassium increased"),
    "hypokalemia": ("Hypokalaemia",),
    "hyponatremia": ("Hyponatraemia",),
    "hypomagnesemia": ("Hypomagnesaemia",),
    "hypocalcaemia": ("Hypocalcaemia",),
    "acid_base": ("Acidosis hyperchloraemic", "Lactic acidosis", "Alkalosis", "Metabolic alkalosis"),
    "hypoglycemia": ("Hypoglycaemia",),
    "hyperglycaemia": ("Hyperglycaemia",),
    "insulin_requirement_increase": ("Increased insulin requirement",),
    "gi_bleeding_ulceration": ("Gastrointestinal ulcer", "Mucosal ulceration", "Gastrointestinal perforation"),
    "gi_upset": ("Gastrointestinal toxicity", "Nausea", "Vomiting", "Diarrhoea"),
    "ileus_constipation": ("Ileus", "Ileus paralytic", "Constipation"),
    "pancreatitis": ("Pancreatitis",),
    "bronchospasm": ("Bronchospasm",),
    "pulmonary_toxicity": ("Pulmonary toxicity",),
    "breathing_rate": ("Hyperventilation", "Tachypnoea"),
    "hypersensitivity_reaction": ("Hypersensitivity", "Angioedema"),
    "hyperthermia": ("Hyperthermia", "Hyperpyrexia", "Pyrexia"),
    "endocrine_change": ("Cortisol decreased", "Cortisol increased", "Cushing's syndrome", "Hypothyroidism",
                         "Blood catecholamines increased", "Endometrial hyperplasia"),
    "other_symptom": ("Dry mouth", "Urinary retention", "Flushing", "Hyperhidrosis", "Thirst", "Priapism", "Pain",
                      "Fatigue", "Asthenia"),
    "pathogen_resistance": ("Pathogen resistance",),
    "drug_toxicity": ("Toxicity to various agents",),
}
#: MedDRA preferred term (as spelled by CRESCENDDI) -> effect key.
EVENT_MAP: dict[str, str] = {term: key for key, terms in _GROUPS.items() for term in terms}
FALLBACK = "other_symptom"

REFERENCE_QUALIFIERS = [
    "CRESCENDDI positive control: the pair is documented as interacting in all three compendia the authors used "
    "(BNF, Nov 2018; IBM Micromedex, Sep 2018; ANSM Thesaurus, Sep 2019).",
    "The adverse event is the MedDRA term the authors mapped from the compendium's interaction description; "
    "the compendium text itself is not reproduced.",
    "The compendia grade severity, but those grades are proprietary editorial classifications and are not shown "
    "here. Severity is therefore not established from the evidence shown.",
    "Snapshot of 2018–2019 sources; later changes to the compendia are not reflected.",
]

SOURCE_NAME = "CRESCENDDI reference set (Kontsioti et al., Sci Data 2022)"


def effect_of(term: str) -> tuple[str, Effect]:
    key = EVENT_MAP.get(term, FALLBACK)
    return key, EFFECTS[key]


def _compendia(sources: str) -> tuple[str, str]:
    parts = [s for s in sources.split("+") if s]
    en = " and ".join(parts) or "the compendia"
    ru = " и ".join(parts) or "справочников"
    return en, ru


def reference_evidence(store, a: int, b: int) -> list[EvidenceRecord]:
    """EvidenceRecords for the CRESCENDDI positive controls of one pair."""
    src = store.sources.get("crescenddi")
    rows = store.reference_outcomes(a, b)
    if not src or not rows:
        return []
    ea, eb = store.lexicon.entries[min(a, b)], store.lexicon.entries[max(a, b)]
    na, nb = ea.inn or ea.id, eb.inn or eb.id
    ra, rb = ea.display("ru"), eb.display("ru")
    out: list[EvidenceRecord] = []
    for code, term, sources in rows:
        key, _ = effect_of(term)
        c_en, c_ru = _compendia(sources)
        out.append(EvidenceRecord(
            id=f"crescenddi:{ea.id}+{eb.id}:{code}",
            category=EvidenceCategory.REFERENCE_SET_OUTCOME,
            source_name=SOURCE_NAME,
            source_version=f"elpidakon/CRESCENDDI@{src['commit'][:12]} (data records, index {src['schema_version']})",
            source_record_id=f"positive_control:{ea.id}|{eb.id}|MedDRA {code}",
            source_url=src["url"],
            original_identifiers={"meddra_code": str(code), "meddra_term": term, "event_source": sources,
                                  "effect_key": key, "event_map": MEDDRA_MAP_VERSION},
            statement=(f"CRESCENDDI lists “{term}” (MedDRA {code}) as an adverse event of the interaction between "
                       f"{na} and {nb}, mapped from the {c_en} interaction description."),
            statement_ru=(f"В CRESCENDDI нежелательное явление «{term}» (MedDRA {code}) указано как последствие "
                          f"взаимодействия препаратов {ra} и {rb}; оно взято из описания взаимодействия в {c_ru}."),
            statement_origin="source_template_filled",
            source_template="CRESCENDDI positive control: drug pair + MedDRA event + event source",
            direction="symmetric",
            retrieved_at=src["retrieved"],
            license=src["license"],
            qualifiers=list(REFERENCE_QUALIFIERS),
        ))
    return out
