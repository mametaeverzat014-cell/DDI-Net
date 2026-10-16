// One place for how each kind of statement looks and is named.
//
// Colour encodes the KIND of statement, never a level of danger, and nothing is
// ever green: a reassuring colour on "nothing found" is exactly the misreading
// this layer exists to prevent. evidenceStyle.test.ts enforces both.
import type { Bi } from "../../i18n";
import type { EvidenceCategory, EvidenceStatus, StatementKind } from "../../data/v3";

export interface Tier { color: string; label: Bi; hint: Bi }

export const STATUS_TIER: Record<EvidenceStatus, Tier> = {
  contraindication_in_label: {
    color: "var(--ev-label)",
    label: { ru: "Противопоказание в инструкции", en: "Contraindication in a label" },
    hint: { ru: "Препарат назван в разделе «Противопоказания» официальной инструкции. Прочитайте цитату ниже.", en: "The drug is named in an official label's Contraindications section. Read the quotation below." },
  },
  warning_in_label: {
    color: "var(--ev-label)",
    label: { ru: "Упомянуто в инструкции", en: "Named in a label" },
    hint: { ru: "Официальная инструкция упоминает второй препарат в предупреждениях или во взаимодействиях.", en: "An official label names the other drug in its warnings or interactions." },
  },
  documented_no_severity: {
    color: "var(--ev-documented)",
    label: { ru: "Задокументировано в базе", en: "Documented in a database" },
    hint: { ru: "База данных описывает взаимодействие; степень тяжести в ней не указана.", en: "A database describes an interaction; it gives no severity." },
  },
  conflicting_evidence: {
    color: "var(--ev-missing)",
    label: { ru: "Источники противоречат", en: "Sources conflict" },
    hint: { ru: "Записи источника утверждают противоположное. Обе показаны; общий вывод не составлен.", en: "Source records say opposite things. Both are shown; no combined conclusion is drawn." },
  },
  model_signal_only: {
    color: "var(--ev-model)",
    label: { ru: "Только сигнал модели", en: "Model signal only" },
    hint: { ru: "Документов не найдено. Исследовательская модель видит сходство с описанными парами — это гипотеза, не факт.", en: "No documentation found. The research model sees resemblance to recorded pairs — a hypothesis, not a fact." },
  },
  no_documented_evidence_found: {
    color: "var(--ev-none)",
    label: { ru: "Документов не найдено", en: "No documentation found" },
    hint: { ru: "В проверенных источниках записей нет. Это не означает, что сочетание безопасно.", en: "The sources checked hold no record. This does not mean the combination is safe." },
  },
};

export const KIND_TIER: Record<StatementKind, Tier> = {
  documented: { color: "var(--ev-documented)", label: { ru: "Источник", en: "Source" }, hint: { ru: "Утверждение из источника", en: "A source's statement" } },
  annotation: { color: "var(--violet)", label: { ru: "Аннотация", en: "Annotation" }, hint: { ru: "Задокументированный факт о каждом препарате отдельно", en: "A documented fact about each drug separately" } },
  hypothesis: { color: "var(--ev-hypothesis)", label: { ru: "Гипотеза", en: "Hypothesis" }, hint: { ru: "Вывод из задокументированных частей; для этой пары не проверен", en: "Inferred from documented parts; not tested for this pair" } },
  model: { color: "var(--ev-model)", label: { ru: "Модель", en: "Model" }, hint: { ru: "Исследовательский сигнал BIO-GINE", en: "BIO-GINE research signal" } },
  missing: { color: "var(--ev-missing)", label: { ru: "Нет данных", en: "Missing" }, hint: { ru: "Чего не хватает", en: "What is missing" } },
  caveat: { color: "var(--text-3)", label: { ru: "Оговорка", en: "Caveat" }, hint: { ru: "Ограничение или уточнение", en: "A limitation or qualification" } },
};

export const CATEGORY_LABEL: Record<EvidenceCategory, Bi & { color: string }> = {
  label_contraindication: { ru: "Инструкция · Противопоказания", en: "Label · Contraindications", color: "var(--ev-label)" },
  label_boxed_warning: { ru: "Инструкция · Предупреждение в рамке", en: "Label · Boxed warning", color: "var(--ev-label)" },
  label_warning_or_interaction: { ru: "Инструкция · Предупреждения / взаимодействия", en: "Label · Warnings / interactions", color: "var(--ev-label)" },
  database_interaction_record: { ru: "База данных · DrugBank", en: "Database · DrugBank", color: "var(--ev-documented)" },
  label_mention_no_effect_reported: { ru: "Инструкция · Эффекта не наблюдали", en: "Label · No effect reported", color: "var(--ev-none)" },
  reference_set_outcome: { ru: "Справочный набор · CRESCENDDI", en: "Reference set · CRESCENDDI", color: "var(--ev-documented)" },
};

export const SOURCE_NAME: Record<string, Bi> = {
  drugbank_tdc: { ru: "DrugBank (выгрузка TDC, локально)", en: "DrugBank (TDC export, local)" },
  crescenddi: { ru: "CRESCENDDI (справочный набор, 2018–2019)", en: "CRESCENDDI (reference set, 2018–2019)" },
  openfda_label: { ru: "Инструкции FDA (openFDA)", en: "FDA labels (openFDA)" },
  rxnorm: { ru: "RxNorm (названия)", en: "RxNorm (names)" },
};

export const SOURCE_STATUS: Record<string, Bi> = {
  ok: { ru: "проверено", en: "checked" },
  no_match: { ru: "проверено, совпадений нет", en: "checked, no match" },
  unavailable: { ru: "недоступен", en: "unavailable" },
  disabled: { ru: "не подключён", en: "not connected" },
  not_applicable: { ru: "неприменимо", en: "not applicable" },
};

export const PATTERN_LABEL: Record<string, Bi> = {
  inhibitor_substrate: { ru: "подавляет белок, который обрабатывает другой препарат", en: "inhibits a protein that handles the other drug" },
  inducer_substrate: { ru: "усиливает выработку белка, который обрабатывает другой препарат", en: "induces a protein that handles the other drug" },
  shared_substrate: { ru: "оба обрабатываются одним белком", en: "both handled by one protein" },
  opposing_target_action: { ru: "противоположное действие на одну мишень", en: "opposite action on one target" },
  same_direction_target_action: { ru: "однонаправленное действие на одну мишень", en: "same-direction action on one target" },
  shared_annotation: { ru: "общий белок, роли не уточнены", en: "shared protein, roles unspecified" },
};

export const RELATION_LABEL: Record<string, Bi> = {
  enzyme: { ru: "фермент", en: "enzyme" },
  transporter: { ru: "переносчик", en: "transporter" },
  carrier: { ru: "белок-носитель", en: "carrier" },
  target: { ru: "мишень", en: "target" },
};

export const ROLE_LABEL: Record<string, Bi> = {
  substrate: { ru: "субстрат", en: "substrate" },
  inhibitor: { ru: "ингибитор", en: "inhibitor" },
  inducer: { ru: "индуктор", en: "inducer" },
  activating: { ru: "активирует", en: "activates" },
  inhibiting: { ru: "подавляет", en: "inhibits" },
  unspecified: { ru: "роль не указана", en: "role not stated" },
};

export const REVIEW_REASON: Record<string, Bi> = {
  "documented:contraindication_in_label": { ru: "противопоказание в инструкции", en: "contraindication in a label" },
  "documented:warning_in_label": { ru: "упомянуто в инструкции", en: "named in a label" },
  "documented:documented_no_severity": { ru: "запись в базе данных", en: "database record" },
  "documented:conflicting_evidence": { ru: "противоречивые записи", en: "conflicting records" },
  model_signal_without_documentation: { ru: "сигнал модели без документов", en: "model signal without documentation" },
  pharmacokinetic_mechanism_hypothesis: { ru: "гипотеза о фармакокинетическом механизме", en: "pharmacokinetic mechanism hypothesis" },
  low_annotation_coverage: { ru: "мало данных о белках", en: "sparse protein annotation" },
};

/** Russian plural for counts shown next to nouns. */
export function pluralRu(n: number, forms: [string, string, string]): string {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return forms[0];
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return forms[1];
  return forms[2];
}
