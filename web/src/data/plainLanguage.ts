// Plain-language explanations shared by the site and the PDF report: what the
// two BIO-GINE scores mean, how to read the test-set metrics, and a glossary.
//
// Written for a reader without medical or machine-learning training. Every
// sentence describes how the numbers were made or what a term means; none gives
// advice, grades severity or calls a combination safe (the wording tests in
// components/v3/evidence.test.tsx and pdf/strings.test.ts cover this file).
// Numbers are passed in from the payload or from the frozen study data, never
// typed here.
import type { Bi } from "../i18n";

export const SCORE_EXPLAINER = {
  title: { ru: "Что означают эти два числа", en: "What the two numbers mean" },
  raw: {
    ru: "Сырая оценка ({raw}) — прямой результат нейросети, число от 0 до 1. У краёв шкалы значения скапливаются: различия в четвёртом-пятом знаке после запятой ничего не значат, кроме «очень высокая» (или «очень низкая»).",
    en: "Raw score ({raw}): the network's direct output, a number between 0 and 1. Near the ends of the scale the values bunch up: differences in the fourth or fifth decimal place mean nothing beyond “very high” (or “very low”).",
  },
  calibrated: {
    ru: "Калиброванная оценка ({cal}) — тот же результат, пересчитанный «температурным масштабированием». Пересчёт подобран на проверочных парах, где половина — задокументированные взаимодействия, половина — случайные пары. Он отодвигает слишком уверенные значения от краёв шкалы, но порядок пар не меняет. Поэтому два числа различаются.",
    en: "Calibrated score ({cal}): the same output, rescaled by “temperature scaling”. The rescaling was fitted on validation pairs of which half were documented interactions and half random pairs. It pulls over-confident values back from the edges of the scale but does not change the order of pairs. That is why the two numbers differ.",
  },
  notProbability: {
    ru: "Ни одно из чисел не вероятность того, что сочетание кому-то навредит. Модель училась только отличать задокументированные пары от случайных. Калиброванную оценку можно читать как долю задокументированных пар лишь в смеси «половина на половину», на которой её подбирали; реальные сочетания лекарств — не такая смесь, а запись о взаимодействии ничего не говорит о его тяжести.",
    en: "Neither number is the probability that the combination harms anyone. The model only learned to tell documented pairs from random ones. The calibrated score could be read as a share of documented pairs only in a half-and-half mix like the one it was fitted on; real drug combinations are not such a mix, and a documented interaction says nothing about how serious it is.",
  },
  can: {
    ru: "Что они могут сказать: насколько уверенно модель относит эту пару к парам, уже описанным как взаимодействующие. Это полезно, чтобы упорядочить пары для исследования.",
    en: "What they can tell: how strongly the model groups this pair with pairs already documented as interacting. That is useful for ranking pairs for research.",
  },
  cannot: {
    ru: "Чего они сказать не могут: произойдёт ли взаимодействие у конкретного человека, насколько оно сильное или опасное, какой препарат на какой влияет и что кому-либо следует делать.",
    en: "What they cannot tell: whether an interaction happens in a particular person, how strong or serious it would be, which drug affects which, or what anyone should do.",
  },
} satisfies Record<string, Bi>;

export const METRIC_NOTES = {
  datasetVsPair: {
    ru: "AUPRC и AUROC описывают качество модели на тысячах тестовых пар; «±» — разброс между {seeds} запусками обучения. Они не говорят, насколько вероятно, что верно именно это предсказание. Оценки неопределённости для отдельной пары сервис не даёт: он использует одну обученную копию модели (сид 0).",
    en: "AUPRC and AUROC describe the model's quality over thousands of test pairs; “±” is the spread between {seeds} training runs. They do not say how likely this particular prediction is to be right. The service gives no uncertainty for a single pair: it uses one trained copy of the model (seed 0).",
  },
  pooledS2: {
    ru: "Режим этой пары — S2. В замороженных результатах пары S2 оценены только вместе с парами S3: объединённый тест — {pooled} пар, из них S2 — {s2}, S3 — {s3}. Отдельной оценки только для S2 нет, поэтому показан объединённый результат, и он так и подписан.",
    en: "This pair's regime is S2. The frozen results evaluate S2 pairs only together with S3 pairs: the pooled test has {pooled} pairs, {s2} of them S2 and {s3} S3. No S2-only estimate exists, so the pooled figure is shown and labelled as pooled.",
  },
  s3: {
    ru: "Режим этой пары — S3; показаны результаты на {s3} тестовых парах S3, где модель не видела при обучении ни один из двух препаратов.",
    en: "This pair's regime is S3; the figures are for the {s3} S3 test pairs, in which the model saw neither drug during training.",
  },
  s1: {
    ru: "Режим этой пары — S1: оба препарата были в обучении. Для таких пар качество модели не измерялось.",
    en: "This pair's regime is S1: both drugs were in training. The model's quality was never measured for such pairs.",
  },
  bothAnnotated: {
    ru: "«both annotated» — только тестовые пары, у обоих препаратов которых есть данные о белках ({bothAnnotated} пар объединённого теста).",
    en: "“both annotated”: only test pairs whose two drugs both have protein data ({bothAnnotated} pairs of the pooled test).",
  },
} satisfies Record<string, Bi>;

export interface GlossaryEntry { term: Bi; text: Bi }

export const GLOSSARY: GlossaryEntry[] = [
  {
    term: { ru: "Доказательство из источника и предсказание модели", en: "Source evidence vs model prediction" },
    text: {
      ru: "Доказательство из источника — текст, который действительно есть в официальной инструкции или базе данных об этих двух препаратах. Предсказание модели — число, которое BIO-GINE вычисляет по закономерностям в данных, на которых она обучалась. Первое — запись того, что известно; второе — исследовательская догадка.",
      en: "Source evidence is text that an official label or a database actually contains about these two drugs. A model prediction is a number BIO-GINE computes from patterns in the data it was trained on. The first records what is known; the second is a research guess.",
    },
  },
  {
    term: { ru: "Инструкция FDA (SPL)", en: "FDA label (SPL)" },
    text: {
      ru: "Официальная инструкция лекарства в США, которую FDA публикует в формате Structured Product Labeling. Одна инструкция — один документ с идентификатором set ID; в ней есть разделы, например «Предупреждения» или «Лекарственные взаимодействия».",
      en: "A medicine's official prescribing information in the United States, published by the FDA as Structured Product Labeling. One label is one document with its own set ID, divided into sections such as Warnings or Drug Interactions.",
    },
  },
  {
    term: { ru: "Документ и фрагмент", en: "Document and excerpt" },
    text: {
      ru: "Фрагмент — одно предложение, процитированное из документа. Несколько фрагментов одной инструкции — всё равно один источник: они не подтверждают друг друга. Если инструкция повторяет предложение в двух разделах, оно показано один раз.",
      en: "An excerpt is one sentence quoted from a document. Several excerpts of one label are still one source and do not confirm each other. When a label repeats a sentence in two sections, it is shown once.",
    },
  },
  {
    term: { ru: "DrugBank (выгрузка TDC)", en: "DrugBank (TDC export)" },
    text: {
      ru: "Большая база данных о лекарствах и известных взаимодействиях; DDI-Net использует её открытую копию из Therapeutics Data Commons. Запись сообщает только тип взаимодействия стандартной фразой, без степени тяжести и без указания, на чём она основана.",
      en: "A large database of drugs and known interactions; DDI-Net uses the public copy distributed by Therapeutics Data Commons. A record states only an interaction type, in a standard sentence, with no severity and no note of what it is based on.",
    },
  },
  {
    term: { ru: "Направление", en: "Direction" },
    text: {
      ru: "Какой препарат на какой влияет. В выгрузке DrugBank для большинства типов взаимодействий порядок препаратов ненадёжен, поэтому по DrugBank отчёт направление не называет. Предложения инструкций приводятся как написаны; из одного того, что в инструкции препарата упомянут другой, направление не выводится.",
      en: "Which drug affects which. For most interaction types the drug order in the DrugBank export is unreliable, so the report names no direction from DrugBank. Label sentences are quoted as written; no direction is inferred from the mere fact that one drug's label names the other.",
    },
  },
  {
    term: { ru: "Цитохромы P450 (CYP450)", en: "Cytochrome P450 (CYP450)" },
    text: {
      ru: "Семейство ферментов, в основном в печени (например, CYP2C9, CYP3A4), которые расщепляют многие лекарства. Если один препарат замедляет фермент, который расщепляет другой, второй может дольше оставаться в организме.",
      en: "A family of enzymes, mostly in the liver (for example CYP2C9, CYP3A4), that break down many medicines. If one drug slows an enzyme that breaks down another, the second may stay in the body longer.",
    },
  },
  {
    term: { ru: "Субстрат, ингибитор, индуктор", en: "Substrate, inhibitor, inducer" },
    text: {
      ru: "Субстрат — препарат, который белок перерабатывает. Ингибитор замедляет работу белка. Индуктор заставляет организм вырабатывать больше этого белка.",
      en: "A substrate is a drug a protein processes. An inhibitor slows the protein down. An inducer makes the body produce more of it.",
    },
  },
  {
    term: { ru: "Гипотеза о механизме", en: "Mechanism hypothesis" },
    text: {
      ru: "Возможное биологическое объяснение, собранное из того, что базы данных сообщают о каждом препарате по отдельности (например: препарат X подавляет фермент, который перерабатывает препарат Y). Для этой пары оно не проверялось и ничего не говорит о силе эффекта.",
      en: "A possible biological explanation assembled from what databases record about each drug separately (for example: drug X inhibits an enzyme that processes drug Y). It was not tested for this pair and says nothing about the size of any effect.",
    },
  },
  {
    term: { ru: "Путь Reactome", en: "Reactome pathway" },
    text: {
      ru: "Описанная учёными цепочка реакций в клетке. Общий путь у двух препаратов — фоновая информация, а не причина взаимодействия.",
      en: "A curated chain of reactions in the cell. Two drugs sharing a pathway is background information, not a cause of interaction.",
    },
  },
  {
    term: { ru: "Сырая и калиброванная оценка", en: "Raw and calibrated score" },
    text: {
      ru: "Сырая — прямой результат модели от 0 до 1; калиброванная — тот же результат, пересчитанный на сбалансированных проверочных парах. Порядок пар у них одинаков. Ни одна не вероятность вреда.",
      en: "The raw score is the model's direct output between 0 and 1; the calibrated score is the same output rescaled on balanced validation pairs. Both put pairs in the same order. Neither is a probability of harm.",
    },
  },
  {
    term: { ru: "Режимы S1, S2, S3", en: "Regimes S1, S2, S3" },
    text: {
      ru: "Видела ли модель препараты при обучении. S1 — оба препарата были в обучении (качество не измерялось). S2 — один препарат не был в обучении. S3 — ни один не был: это самая трудная проверка.",
      en: "Whether the model saw the drugs during training. S1: both drugs were in training (quality not measured). S2: one drug was not in training. S3: neither was — the hardest test.",
    },
  },
  {
    term: { ru: "Отложенный тест; «объединённый» (pooled)", en: "Held-out test; “pooled”" },
    text: {
      ru: "Пары, отложенные заранее и не использованные в обучении: на них измеряют качество. «Объединённый» — пары S2 и S3, измеренные вместе ({pooled} пар, из них {s3} — S3).",
      en: "Pairs set aside in advance and never used for training; quality is measured on them. “Pooled” means S2 and S3 test pairs measured together ({pooled} pairs, {s3} of them S3).",
    },
  },
  {
    term: { ru: "AUROC", en: "AUROC" },
    text: {
      ru: "Вероятность того, что модель поставит случайно выбранную задокументированную пару выше случайно выбранной пары из сравнительного набора (случайные пары без записи). 0.5 — угадывание, 1 — идеальный порядок.",
      en: "The chance that the model ranks a randomly chosen documented pair above a randomly chosen pair from the comparison set (random pairs without a record). 0.5 is guessing; 1 is a perfect ranking.",
    },
  },
  {
    term: { ru: "AUPRC", en: "AUPRC" },
    text: {
      ru: "Площадь под кривой «точность — полнота»: насколько хорошо модель находит задокументированные пары, не поднимая при этом много ложных тревог, при всех порогах сразу. В тесте половина пар задокументирована, поэтому угадывание даёт около 0.5; 1 — идеально.",
      en: "Area under the precision–recall curve: how well the model finds documented pairs without raising many false alarms, over all thresholds at once. Half of the test pairs are documented, so guessing gives about 0.5; 1 is perfect.",
    },
  },
  {
    term: { ru: "± (разброс между запусками)", en: "± (spread between runs)" },
    text: {
      ru: "Модель обучали несколько раз (запусков: {seeds}), каждый раз с другой случайной начальной точкой — сидом. «±» — стандартное отклонение результата между этими запусками. Это не погрешность для отдельной пары.",
      en: "The model was trained {seeds} times, each from a different random starting point (seed). “±” is the standard deviation of the result between those runs. It is not an error bar for a single pair.",
    },
  },
];

/** Values the texts above refer to, read from the frozen study data. */
export interface StudyCounts { pooled: number; s3: number; s2: number; seeds: number; bothAnnotated: number }

export function fillPlain(text: string, vars: Record<string, string | number>): string {
  return text.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m));
}

/** Note attached to a service sentence that quotes a test metric for an S2 pair
 *  without saying it is pooled. Responses from API versions before the fix
 *  wrote "(as here): AUPRC 0.812", which reads as an S2 figure; the frozen
 *  results hold only the pooled S2+S3 figure. Independent of API version: a
 *  sentence that already says "pooled" gets no note. */
export const POOLED_NOTE: Bi = {
  ru: "Примечание отчёта: это значение получено на объединённом отложенном тесте (пары S2 и S3 вместе); отдельной оценки только для S2 нет.",
  en: "Note added by the report: this figure comes from the pooled held-out test (S2 and S3 pairs together); no S2-only estimate exists.",
};

export function needsPooledNote(text: Bi, regime: string | null | undefined): boolean {
  return regime === "S2" && /\b(AUPRC|AUROC)\b/.test(text.en) && !/pooled/i.test(text.en);
}
