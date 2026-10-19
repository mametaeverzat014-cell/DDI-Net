// Fixed wording of the clinical-outcome view, shared by the site and the PDF so
// both say the same thing about the same API data. Data-derived text (outcome
// labels, explanations, seriousness basis, coverage) comes from the API's
// `outcomes` block; nothing here invents an outcome, a severity or a number.
import type { Bi } from "../i18n";
import type { EffectLevel, InteractionStatus, LinkProvenance, OutcomeEvidenceStatus, SeriousnessClass } from "./v3";

export const OT = {
  aTitle: { ru: "Есть ли задокументированное взаимодействие?", en: "Is there a documented interaction?" },
  bTitle: { ru: "Что может произойти?", en: "What could happen?" },
  bLead: {
    ru: "Только последствия, которые источники называют для этой пары. Каждое — с цитатой источника.",
    en: "Only consequences the sources state for this pair, each with the source's words.",
  },
  cTitle: { ru: "Почему это может происходить?", en: "Why could it happen?" },
  cVerified: { ru: "Цепочки с подтверждёнными звеньями (каждое звено помечено отдельно)", en: "Chains with supported steps (each step is marked separately)" },
  cHypothesis: { ru: "Гипотезы (не подтверждены для этой пары)", en: "Hypotheses (not confirmed for this pair)" },
  cNone: {
    ru: "Доступные данные не устанавливают механизм задокументированных последствий.",
    en: "The available evidence does not establish a mechanism for the documented outcomes.",
  },
  cResearchOnly: {
    ru: "Гипотезы о механизме без задокументированного последствия показаны в режиме «Исследование».",
    en: "Mechanism hypotheses without a documented outcome are shown in Research mode.",
  },
  dTitle: { ru: "Насколько это надёжно?", en: "How certain is the information?" },
  dSeriousness: { ru: "Серьёзность", en: "Seriousness" },
  dStrength: { ru: "Сила доказательств (описательно, без процентов)", en: "Strength of evidence (described, no percentages)" },
  dCoverage: { ru: "Какие источники проверены", en: "Which sources were checked" },
  eTitle: { ru: "Что добавляет BIO-GINE?", en: "What does BIO-GINE add?" },
  eText: {
    ru: "BIO-GINE — исследовательская модель, которая ищет закономерности, похожие на задокументированные взаимодействия. Её оценка не является вероятностью вреда и не говорит о риске для конкретного человека; на статус и последствия выше она не влияет.",
    en: "BIO-GINE is a research model that looks for patterns resembling documented interactions. Its score is not a probability of harm or an individual's risk, and it does not affect the status or the outcomes above.",
  },
  eScore: { ru: "Калиброванная оценка", en: "Calibrated score" },
  eUnavailable: { ru: "Модель недоступна.", en: "The model is unavailable." },
  eAbstain: { ru: "Оценка не учитывается: модель обучалась на записи этой пары.", en: "Score not counted: the model was trained on this pair's record." },
  fTitle: { ru: "Важное ограничение", en: "Important limitation" },
  sources: { ru: "Источник", en: "Source" },
  showSource: { ru: "Слова источника", en: "Source's words" },
  method: { ru: "Метод извлечения", en: "Extraction method" },
  section: { ru: "Раздел", en: "Section" },
  documents: { ru: "Документов-источников", en: "Source documents" },
  direction: { ru: "Направление", en: "Direction" },
  limitations: { ru: "Оговорки", en: "Limitations" },
  oldApi: {
    ru: "Этот ответ сервиса не содержит анализа последствий (версия API до движка последствий). Показаны задокументированные записи как есть.",
    en: "This service response contains no outcome analysis (an API version before the outcome engine). The documented records are shown as they are.",
  },
  outcomeTable: { ru: "Все последствия и гипотезы (полное происхождение)", en: "All outcomes and hypotheses (full provenance)" },
  chainTitle: { ru: "От механизма к последствию", en: "From mechanism to outcome" },
  chainLegend: { ru: "Условные обозначения", en: "Legend" },
  chainHint: {
    ru: "Нажмите на звено или узел, чтобы увидеть основание.",
    en: "Select a link or node to see what it rests on.",
  },
  researchHyp: { ru: "только исследование", en: "research only" },
  sharedTitle: { ru: "Общие задокументированные категории последствий", en: "Documented outcome categories shared by several pairs" },
  sharedNote: {
    ru: "Это совпадение категорий в попарных данных. Оно не означает, что эффекты складываются, и ничего не говорит о сочетании трёх и более препаратов.",
    en: "This is an overlap of categories in pairwise data. It does not mean the effects add up, and says nothing about three or more drugs together.",
  },
  filter: { ru: "Фильтр по категории", en: "Filter by category" },
  all: { ru: "все", en: "all" },
  noneDocumented: { ru: "задокументированных последствий нет", en: "no documented outcome" },
} satisfies Record<string, Bi>;

export const STATUS_OF: Record<OutcomeEvidenceStatus, Bi> = {
  documented: { ru: "задокументировано", en: "documented" },
  mechanistically_supported: { ru: "задокументировано, механизм подтверждён аннотациями", en: "documented, mechanism supported by annotations" },
  hypothesized: { ru: "гипотеза", en: "hypothesis" },
};

export const LEVEL_OF: Record<EffectLevel, Bi> = {
  clinical_outcome: { ru: "клиническое последствие", en: "clinical outcome" },
  pharmacodynamic_effect: { ru: "изменение действия", en: "change in effect" },
  pharmacokinetic_change: { ru: "изменение концентрации", en: "change in exposure" },
  reduced_effectiveness: { ru: "ослабление лечебного действия", en: "reduced effectiveness" },
  unspecified_adverse: { ru: "последствие не уточнено", en: "outcome not specified" },
};

export const SERIOUSNESS_OF: Record<SeriousnessClass, Bi> = {
  documented_contraindication: { ru: "противопоказание по инструкции", en: "contraindication in label" },
  explicit_serious_warning: { ru: "явное предупреждение о серьёзности", en: "explicit serious warning" },
  documented_no_standard_severity: { ru: "серьёзность не установлена", en: "severity not established" },
  not_applicable: { ru: "неприменимо", en: "not applicable" },
};

export const PROVENANCE_OF: Record<LinkProvenance, Bi> = {
  documented: { ru: "задокументировано", en: "directly documented" },
  verified_annotation: { ru: "проверенная аннотация", en: "verified biological annotation" },
  plausible_unconfirmed: { ru: "правдоподобно, не подтверждено", en: "plausible but unconfirmed" },
  unavailable: { ru: "нет данных", en: "unsupported or unavailable" },
};

export const INTERACTION_STATUS_ORDER: InteractionStatus[] = [
  "documented_interaction", "documented_outcome_unclear", "source_unavailable", "research_prediction_only", "insufficient_evidence",
];
