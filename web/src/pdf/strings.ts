// Every fixed string of the PDF report, in both languages. Data-derived text
// (source statements, API explanations, labels of evidence kinds) comes from the
// API response or from components/v3/evidenceStyle.ts, never from here.
//
// Wording rules are the site's (components/v3/evidence.test.tsx): no advice to
// start, stop, combine or change a medicine, nothing that calls a combination
// safe, and the model score is never a risk or a probability of harm.
// strings.test.ts runs the same checks over this file.
import type { Bi } from "../i18n";

export const S = {
  // ── chrome ──────────────────────────────────────────────────────────────
  brand: { ru: "DDI-Net 3.0", en: "DDI-Net 3.0" },
  brandLine: { ru: "Объяснимый анализ лекарственных взаимодействий", en: "Explainable drug interaction intelligence" },
  title: { ru: "Исследовательский отчёт о взаимодействии препаратов", en: "Drug–Drug Interaction Research Report" },
  titleMulti: { ru: "Исследовательский отчёт: несколько препаратов", en: "Multi-Drug Interaction Research Report" },
  headerLeft: { ru: "DDI-Net 3.0 · исследовательский отчёт", en: "DDI-Net 3.0 · research report" },
  footerLeft: { ru: "Только для исследований · не для клинических решений", en: "Research use only · not for clinical decisions" },
  page: { ru: "Стр. {n} из {t}", en: "Page {n} of {t}" },
  researchOnlyTitle: { ru: "Только для исследовательских целей", en: "Research use only" },
  researchOnly: {
    ru: "DDI-Net — исследовательский прототип, а не медицинское изделие и не система поддержки клинических решений. Отсутствие задокументированного взаимодействия не доказывает безопасность. Оценка BIO-GINE — исследовательский сигнал сходства с задокументированными парами, а не вероятность клинического вреда.",
    en: "DDI-Net is a research prototype — not a medical device and not clinical decision support. The absence of a documented interaction is not evidence of safety. The BIO-GINE score is a research signal of resemblance to documented pairs, not a probability of clinical harm.",
  },
  coverNote: {
    ru: "PDF собран в браузере из того же ответа сервиса, что был показан на странице. Для отчёта ничего не запрашивалось повторно.",
    en: "This PDF was assembled in the browser from the same service response shown on the page. Nothing was requested again for the report.",
  },

  contents: { ru: "Содержание", en: "Contents" },
  // ── metadata ────────────────────────────────────────────────────────────
  reportId: { ru: "ID отчёта", en: "Report ID" },
  generated: { ru: "Создан", en: "Generated" },
  generatedUtc: { ru: "Создан (UTC)", en: "Generated (UTC)" },
  language: { ru: "Язык", en: "Language" },
  languageValue: { ru: "русский", en: "English" },
  modelVersion: { ru: "Модель", en: "Model" },
  reportVersion: { ru: "Версия отчёта API", en: "API report version" },
  analysisTime: { ru: "Анализ выполнен сервисом", en: "Analysis produced by the service" },
  receivedAt: { ru: "Ответ получен браузером", en: "Response received by the browser" },
  apiOrigin: { ru: "Сервис", en: "Service" },
  notRecorded: { ru: "не записано", en: "not recorded" },
  drugA: { ru: "Препарат A", en: "Drug A" },
  drugB: { ru: "Препарат B", en: "Drug B" },
  drugsAnalyzed: { ru: "Проанализированные препараты", en: "Drugs analysed" },
  seed0: { ru: "сид 0", en: "seed 0" },

  // ── section titles ──────────────────────────────────────────────────────
  secSummary: { ru: "Краткое резюме", en: "Executive summary" },
  secDrugs: { ru: "Сведения о препаратах", en: "Drug information" },
  secDocumented: { ru: "Задокументированные взаимодействия", en: "Documented interactions" },
  secMechanisms: { ru: "Биологические механизмы", en: "Biological mechanisms" },
  secModel: { ru: "Исследовательский анализ BIO-GINE", en: "BIO-GINE research analysis" },
  secExplanation: { ru: "Пояснение сервиса по разделам", en: "Structured explanation from the service" },
  secSources: { ru: "Источники и воспроизводимость", en: "Sources and reproducibility" },
  secLimitations: { ru: "Ограничения", en: "Limitations" },
  secAppendix: { ru: "Приложение A. Машиночитаемая сводка (JSON)", en: "Appendix A. Machine-readable summary (JSON)" },
  secMultiOverview: { ru: "Обзор препаратов", en: "Overview of the drugs" },
  secMultiNetwork: { ru: "Попарная карта", en: "Pairwise map" },
  secMultiPairs: { ru: "Все пары: доказательства и модель", en: "All pairs: evidence and model" },
  secMultiCoverage: { ru: "Охват и неопределённость", en: "Coverage and uncertainty" },

  // ── four kinds ──────────────────────────────────────────────────────────
  kindsTitle: { ru: "Четыре вида информации в этом отчёте", en: "Four kinds of information in this report" },
  kindDocumented: { ru: "Задокументированные доказательства", en: "Documented evidence" },
  kindDocumentedHint: { ru: "Источник прямо описывает взаимодействие этих двух препаратов.", en: "A source states that these two drugs interact." },
  kindHypothesis: { ru: "Гипотезы о механизме", en: "Mechanism hypotheses" },
  kindHypothesisHint: { ru: "Собраны из задокументированных ролей каждого препарата отдельно; для пары не проверены.", en: "Assembled from each drug's documented roles separately; not tested for the pair." },
  kindModel: { ru: "Предсказание модели", en: "Machine-learning prediction" },
  kindModelHint: { ru: "Сходство с задокументированными парами по оценке BIO-GINE; не вероятность вреда.", en: "BIO-GINE's resemblance to documented pairs; not a probability of harm." },
  kindMissing: { ru: "Отсутствующие или недоступные данные", en: "Missing or unavailable evidence" },
  kindMissingHint: { ru: "Что не удалось проверить или чего нет в источниках.", en: "What could not be checked, or is absent from the sources." },

  // ── summary sentences ({x} placeholders) ───────────────────────────────
  sumDrugs: { ru: "Проанализирована пара {a} ({ia}) и {b} ({ib}).", en: "The pair analysed is {a} ({ia}) and {b} ({ib})." },
  sumStatus: { ru: "Вид найденной документации: {s}. Это вид источника, а не степень опасности.", en: "Kind of documentation found: {s}. This is the kind of source, not a level of danger." },
  sumEvidenceCounts: {
    ru: "Записей в базе DrugBank: {db}; фрагментов официальных инструкций: {lab}; упоминаний в инструкциях без отмеченного эффекта: {noeff}; противоречий между записями: {conf}.",
    en: "DrugBank interaction records: {db}; official label excerpts: {lab}; label mentions reporting no effect: {noeff}; conflicts between records: {conf}.",
  },
  sumNoEvidence: {
    ru: "В проверенных источниках не найдено ни одной записи о взаимодействии этой пары. Это не означает, что сочетание безопасно: источники неполны, а часть из них могла быть недоступна.",
    en: "No interaction record for this pair was found in the sources checked. This does not mean the combination is safe: the sources are incomplete, and some may have been unavailable.",
  },
  sumHyp: {
    ru: "Гипотез о механизме, собранных из задокументированных ролей препаратов: {n} ({list}). Ни одна не проверялась для этой пары.",
    en: "Mechanism hypotheses assembled from documented drug–protein roles: {n} ({list}). None was tested for this pair.",
  },
  sumNoHyp: {
    ru: "Задокументированные роли препаратов не складываются ни в одну из проверяемых конфигураций механизма.",
    en: "The drugs' documented roles form none of the mechanism configurations checked.",
  },
  sumPathways: { ru: "Общих биологических путей Reactome: {n} (фон, а не причина взаимодействия).", en: "Shared Reactome pathways: {n} (background, not a cause of interaction)." },
  sumModel: {
    ru: "BIO-GINE M4: калиброванная оценка {cal} (сырая {raw}), режим {reg}. Оценка показывает сходство с задокументированными парами; это не вероятность клинического вреда и не степень тяжести.",
    en: "BIO-GINE M4: calibrated score {cal} (raw {raw}), regime {reg}. The score expresses resemblance to documented pairs; it is not a probability of clinical harm and carries no severity.",
  },
  sumModelAbstain: {
    ru: "BIO-GINE M4: оценка не учитывается — модель обучалась на записи именно этой пары, поэтому её ответ здесь не независим.",
    en: "BIO-GINE M4: the score is not counted — the model was trained on this pair's own record, so its output here is not independent.",
  },
  sumModelUnavailable: { ru: "BIO-GINE M4: модель недоступна ({r}).", en: "BIO-GINE M4: model unavailable ({r})." },
  sumGapsTitle: { ru: "Неопределённость и пробелы", en: "Uncertainty and evidence gaps" },
  gapSource: { ru: "Источник «{s}»: {st}. Его данные не вошли в отчёт.", en: "Source “{s}”: {st}. Its data is not part of this report." },
  gapDirection: {
    ru: "Для {n} из {m} записей DrugBank порядок препаратов в выгрузке не подтверждён, поэтому отчёт не называет, какой препарат на какой влияет.",
    en: "For {n} of {m} DrugBank records the drug order in the export is not verified, so the report does not say which drug affects which.",
  },
  gapNoCi: {
    ru: "Сервис использует одну контрольную точку модели (сид 0) и не даёт ни доверительного интервала для пары, ни ансамблевой оценки. Ниже приведено измеренное качество для этого режима — среднее по многим парам, а не уверенность в этой паре.",
    en: "The service uses one model checkpoint (seed 0) and provides neither a per-pair confidence interval nor an ensemble estimate. Measured performance for this regime is given instead — an average over many pairs, not confidence in this pair.",
  },
  gapSeverity: { ru: "Ни один источник не указывает степень тяжести; отчёт её не присваивает.", en: "No source gives a severity, and none is assigned here." },
  gapIndividual: {
    ru: "Дозы, длительность, возраст, функция почек и печени, другие лекарства и индивидуальные факторы не учитываются.",
    en: "Doses, duration, age, kidney and liver function, other medicines and individual factors are not taken into account.",
  },

  kindCountDoc: { ru: "записей DrugBank: {db}; фрагментов инструкций: {lab}", en: "DrugBank records: {db}; label excerpts: {lab}" },
  kindNoneFound: { ru: "ничего не найдено — это не означает «безопасно»", en: "none found — this does not mean “safe”" },
  kindCountHyp: { ru: "гипотез: {n}; общих путей Reactome: {p}", en: "hypotheses: {n}; shared Reactome pathways: {p}" },
  kindModelScore: { ru: "калиброванная оценка {cal} · режим {reg}", en: "calibrated score {cal} · regime {reg}" },
  kindModelAbstain: { ru: "оценка не учитывается (запись пары была в обучении)", en: "score not counted (the pair's record was in training)" },
  kindNoMissing: { ru: "все перечисленные источники ответили; см. ограничения", en: "every listed source responded; see the limitations" },
  multiModel: {
    ru: "BIO-GINE M4 — замороженная контрольная точка {ck} по замороженным данным сайта; ответ для нескольких препаратов сам её не называет",
    en: "BIO-GINE M4 — frozen checkpoint {ck} per the site's frozen data; the multi-drug response itself does not name it",
  },
  noInn: { ru: "нет (не сопоставлено в DrugCentral)", en: "none (no DrugCentral match)" },
  drugbankPage: { ru: "Страница DrugBank", en: "DrugBank page" },
  statusCounts: { ru: "Пар", en: "Pairs" },
  nothingSafe: { ru: "не означает «безопасно»", en: "does not mean “safe”" },
  abstainedPairs: { ru: "Пары, где оценка не учитывается", en: "Pairs whose score is not counted" },
  reviewReasonsTitle: { ru: "Причины отметки «стоит изучить»", en: "Reasons a pair is flagged" },
  scoreTiles: { ru: "Оценка модели", en: "Model score" },
  trainingLabelSeen: { ru: "Запись пары была в обучении", en: "Pair's record seen in training" },
  rolesLegend: { ru: "Роли на линиях: суб — субстрат, инг — ингибитор / подавляет, инд — индуктор, акт — активирует, н/у — не указана.", en: "Roles on branches: sub — substrate, inh — inhibitor / inhibits, ind — inducer, act — activates, n/s — not stated." },
  matrixLegend: { ru: "Членство белков в путях Reactome (точка — белок входит в путь; цвет — чей это белок: A, B или общий).", en: "Protein membership in Reactome pathways (a dot means the protein is in the pathway; colour shows whose protein it is: A, B or shared)." },
  sideA: { ru: "белок A", en: "protein of A" },
  sideB: { ru: "белок B", en: "protein of B" },
  sideShared: { ru: "общий белок", en: "shared protein" },
  coverGeneratedBy: { ru: "Отчёт создан", en: "Report generated" },

  // ── drug table ──────────────────────────────────────────────────────────
  field: { ru: "Поле", en: "Field" },
  nameEn: { ru: "Международное название (INN)", en: "International name (INN)" },
  nameRu: { ru: "Русское название", en: "Russian name" },
  translit: { ru: "транслитерация", en: "transliteration" },
  drugbankId: { ru: "DrugBank ID", en: "DrugBank ID" },
  groups: { ru: "Группы DrugBank", en: "DrugBank groups" },
  drugType: { ru: "Тип", en: "Type" },
  query: { ru: "Запрос", en: "Query as entered" },
  matchedOn: { ru: "Сопоставлено по", en: "Matched on" },
  coverage: { ru: "Аннотации белков (мишени / ферменты / переносчики / носители)", en: "Protein annotations (targets / enzymes / transporters / carriers)" },
  modelSplit: { ru: "Выборка модели (сид 0)", en: "Model split (seed 0)" },
  bioForModel: { ru: "Белковые данные для модели", en: "Protein data available to the model" },
  yes: { ru: "да", en: "yes" },
  no: { ru: "нет", en: "no" },
  none: { ru: "нет", en: "none" },
  drugProvenance: {
    ru: "Идентификаторы — DrugBank. INN — DrugCentral, сопоставление по InChIKey (нет значения — сопоставление не найдено). Русские названия — правило транслитерации, подпись интерфейса, а не данные источника.",
    en: "Identifiers: DrugBank. INN: DrugCentral, joined on InChIKey (no value means no match). Russian names: rule-based transliteration — an interface label, not sourced data.",
  },

  // ── evidence ────────────────────────────────────────────────────────────
  evidenceIntro: {
    ru: "Каждая запись пронумерована; на эти номера ссылаются пояснения. Английский текст — слова источника (цитата или стандартная фраза DrugBank); русский — перевод проекта.",
    en: "Each record is numbered; the explanations refer to these numbers. The English text is the source's own words (an excerpt or DrugBank's standard sentence).",
  },
  sourceWords: { ru: "Слова источника", en: "Source's words" },
  projectTranslation: { ru: "Перевод проекта (не слова источника)", en: "Project translation (not the source's words)" },
  origin_verbatim_excerpt: { ru: "дословная цитата", en: "verbatim excerpt" },
  origin_source_template_filled: { ru: "шаблон DrugBank с подставленными названиями", en: "DrugBank template, names filled in" },
  origin_source_template_direction_neutral: { ru: "шаблон DrugBank без указания направления", en: "DrugBank template, direction-neutral" },
  dir_symmetric: { ru: "симметричный тип: направление не имеет значения", en: "symmetric type: direction carries no meaning" },
  dir_as_exported_verified: { ru: "порядок препаратов в выгрузке подтверждён аудитом", en: "drug order in the export verified by the audit" },
  dir_not_verified: { ru: "направление не подтверждено: не указано, какой препарат на какой влияет", en: "direction not verified: the report does not say which drug affects which" },
  dir_not_applicable: { ru: "направление неприменимо", en: "direction not applicable" },
  directionCheck: { ru: "Проверка порядка для этого типа: согласуется {c} из {n} проверяемых записей ({p}).", en: "Order check for this type: {c} of {n} checkable records consistent ({p})." },
  source: { ru: "Источник", en: "Source" },
  version: { ru: "Версия", en: "Version" },
  section: { ru: "Раздел", en: "Section" },
  recordId: { ru: "ID записи", en: "Record ID" },
  identifiers: { ru: "Исходные идентификаторы", en: "Original identifiers" },
  url: { ru: "Ссылка", en: "URL" },
  retrievalUrl: { ru: "Запрос к источнику", en: "Retrieval URL" },
  retrieved: { ru: "Получено", en: "Retrieved" },
  license: { ru: "Лицензия", en: "Licence" },
  severityBySource: { ru: "Степень тяжести по источнику", en: "Severity as stated by the source" },
  severityNone: { ru: "не указана источником", en: "not stated by the source" },
  qualifiers: { ru: "Оговорки", en: "Qualifiers" },
  conflicts: { ru: "Противоречия между записями", en: "Conflicts between records" },
  sourcesChecked: { ru: "Проверенные источники", en: "Sources checked" },
  status: { ru: "Статус", en: "Status" },
  detail: { ru: "Подробности", en: "Detail" },
  noEvidenceTitle: { ru: "Документов не найдено", en: "No documentation found" },

  // ── mechanisms ──────────────────────────────────────────────────────────
  diagramTitle: { ru: "Граф механизмов", en: "Mechanism graph" },
  diagramFromGraph: {
    ru: "Граф построен по ответу /api/v3/graph для этой пары: каждая линия — задокументированная связь. Гипотезы отмечены пунктирным кольцом на белке и никогда не рисуются линией.",
    en: "Drawn from the /api/v3/graph response for this pair: every line is a documented relation. Hypotheses are a dashed ring on a protein and are never drawn as a line.",
  },
  diagramFromReport: {
    ru: "Граф построен по блоку механизмов отчёта: белки, задокументированные у обоих препаратов. Полный граф (включая белки только одного препарата) — на странице «Механизмы».",
    en: "Drawn from the report's mechanism block: proteins documented for both drugs. The full graph, including proteins of only one drug, is on the Mechanisms page.",
  },
  diagramDirection: {
    ru: "Дуга между препаратами — задокументированная запись о взаимодействии. Стрелки нет: порядок препаратов в выгрузке DrugBank для этого типа не подтверждён.",
    en: "The arc between the drugs is a documented interaction record. It has no arrowhead: the DrugBank export's drug order is not verified for this type.",
  },
  diagramDirectionVerified: {
    ru: "Дуга между препаратами — задокументированная запись о взаимодействии; для её типа порядок препаратов подтверждён аудитом, но и здесь стрелка не рисуется — направление указано в тексте записи.",
    en: "The arc between the drugs is a documented interaction record; its type's drug order passed the audit, yet no arrowhead is drawn — the record's text states the direction.",
  },
  diagramTruncated: { ru: "Не показано белков, не общих для пары: {n}.", en: "Proteins not shared by the pair and not shown: {n}." },
  legendEnzyme: { ru: "фермент", en: "enzyme" },
  legendTransporter: { ru: "переносчик", en: "transporter" },
  legendCarrier: { ru: "белок-носитель", en: "carrier" },
  legendTarget: { ru: "мишень", en: "target" },
  legendPathway: { ru: "входит в путь Reactome", en: "member of a Reactome pathway" },
  legendDocumented: { ru: "задокументированное взаимодействие (без направления)", en: "documented interaction (no direction)" },
  legendHypothesis: { ru: "белок, на котором строится гипотеза", en: "protein a hypothesis rests on" },
  legendShared: { ru: "общий белок", en: "shared protein" },
  colShared: { ru: "ОБЩИЕ", en: "SHARED" },
  hypotheses: { ru: "Гипотезы о механизме", en: "Mechanism hypotheses" },
  protein: { ru: "Белок", en: "Protein" },
  relation: { ru: "Связь", en: "Relation" },
  configuration: { ru: "Конфигурация", en: "Configuration" },
  rolesAB: { ru: "Роли A / B", en: "Roles A / B" },
  basis: { ru: "Основание", en: "Basis" },
  hypDirection: { ru: "гипотеза: {x} → {y}", en: "hypothesis: {x} → {y}" },
  consistentWith: { ru: "согласуется с записью {r} (не независимое подтверждение)", en: "consistent with record {r} (not independent confirmation)" },
  pathways: { ru: "Общие биологические пути (Reactome)", en: "Shared biological pathways (Reactome)" },
  pathwaysShown: { ru: "Показано {k} из {n}: сначала пути через общий белок, затем самые узкие.", en: "{k} of {n} shown: pathways through a shared protein first, then the most specific." },
  pathway: { ru: "Путь", en: "Pathway" },
  proteinsInPathway: { ru: "белков", en: "proteins" },
  viaA: { ru: "через A", en: "via A" },
  viaB: { ru: "через B", en: "via B" },
  proteinNotes: { ru: "Белки гипотез: общее описание семейства (текст проекта, не утверждение об этой паре)", en: "Proteins in the hypotheses: family background (project text, not a statement about this pair)" },
  noMechanismData: { ru: "Для этой пары нет данных о механизмах.", en: "No mechanism data for this pair." },

  // ── model ───────────────────────────────────────────────────────────────
  modelIdentity: { ru: "Модель и контрольная точка", en: "Model and checkpoint" },
  calibrated: { ru: "Калиброванная оценка", en: "Calibrated score" },
  raw: { ru: "Сырая оценка", en: "Raw score" },
  regime: { ru: "Режим", en: "Regime" },
  regime_S1: { ru: "S1 — оба препарата были в обучающей выборке; этот режим в замороженном исследовании не оценивался", en: "S1 — both drugs were in the training set; the frozen study did not evaluate this regime" },
  regime_S2: { ru: "S2 — один препарат не входил в обучающую выборку", en: "S2 — one drug was outside the training set" },
  regime_S3: { ru: "S3 — ни один препарат не входил в обучающую выборку", en: "S3 — neither drug was in the training set" },
  splits: { ru: "Выборки A / B", en: "Splits A / B" },
  reliability: { ru: "Надёжность для этой пары", en: "Reliability for this pair" },
  rel_training_label_seen: { ru: "модель обучалась на записи этой пары — оценка не учитывается", en: "the model was trained on this pair's record — score not counted" },
  rel_not_evaluated_regime: { ru: "режим не оценивался на отложенных данных", en: "regime not evaluated on held-out data" },
  rel_held_out_like: { ru: "как на отложенных парах замороженного теста", en: "like the held-out pairs of the frozen test" },
  abstained: { ru: "не учитывается", en: "not counted" },
  interpretationTitle: { ru: "Как читать оценку", en: "How to read the score" },
  interpretation: {
    ru: "Оценка BIO-GINE говорит, насколько пара похожа на пары, уже записанные как взаимодействующие. Калибровка подобрана на проверочных парах с равной долей задокументированных и случайно набранных пар, поэтому число — не вероятность вреда, не частота взаимодействий в практике и не степень тяжести. Её смысл — ранжирование для исследования.",
    en: "The BIO-GINE score says how closely a pair resembles pairs already recorded as interacting. Calibration was fitted on validation pairs with equal shares of documented and randomly drawn pairs, so the number is not a probability of harm, not a frequency of interactions in practice, and not a severity. Its use is ranking for research.",
  },
  measured: { ru: "Измеренное качество для этого режима", en: "Measured performance for this regime" },
  metric: { ru: "Метрика", en: "Metric" },
  meanSd: { ru: "Среднее ± SD", en: "Mean ± SD" },
  seeds: { ru: "Сидов", en: "Seeds" },
  view: { ru: "Срез данных", en: "Evaluation view" },
  reliance: { ru: "На что опирается модель (зануление одного вида данных)", en: "What the model leans on (one kind of data zeroed)" },
  relianceLead: {
    ru: "Изменение сырой оценки, если убрать один вид данных у обоих препаратов. Минус — оценка падает без этих данных.",
    en: "Change in the raw score when one kind of data is removed for both drugs. A minus sign means the score drops without that data.",
  },
  molecular: { ru: "строение молекул", en: "molecular structure" },
  proteins: { ru: "белки", en: "proteins" },
  pathwaysData: { ru: "биологические пути", en: "pathways" },
  relianceParen: { ru: "В скобках — сырая оценка без этих данных.", en: "In brackets: the raw score without this data." },
  notSeverity: { ru: "Это вид найденной документации, а не степень опасности.", en: "This is the kind of documentation found, not a level of danger." },
  relianceValidated: { ru: "Проверка метода: воспроизводит замороженный анализ V2 на {n} тестовых строках, max |Δ| = {d}.", en: "Method check: reproduces the frozen V2 analysis on {n} test rows, max |Δ| = {d}." },
  relianceSaturated: {
    ru: "Сырая оценка близка к краю шкалы (0 или 1); изменения там сжимаются, и опора может выглядеть меньше, чем есть.",
    en: "The raw score is near the edge of the scale (0 or 1); changes are compressed there, and reliance can look smaller than it is.",
  },
  relianceAbsent: { ru: "Опора модели для этой пары не приводится: {r}.", en: "Model reliance is not given for this pair: {r}." },
  relianceAbsentApi: { ru: "сервис её не вернул", en: "the service did not return it" },
  modelNotes: { ru: "Примечания сервиса", en: "Notes from the service" },
  uncertainty: { ru: "Неопределённость", en: "Uncertainty" },
  modelUnavailable: { ru: "Модель недоступна", en: "Model unavailable" },

  // ── explanation ─────────────────────────────────────────────────────────
  explanationIntro: {
    ru: "Текст ниже составлен сервисом детерминированными шаблонами по найденным записям (без языковой модели) и проверен им на отсутствие советов. Метки в скобках ведут к записям: [n] — доказательство, H — гипотеза, M — модель, R — путь Reactome.",
    en: "The text below was written by the service with deterministic templates over the retrieved records (no language model) and checked by it for advice wording. Bracketed labels point to records: [n] evidence, H hypothesis, M model, R Reactome pathway.",
  },
  method: { ru: "Метод", en: "Method" },

  // ── sources & reproducibility ───────────────────────────────────────────
  evidenceRecords: { ru: "Записи-доказательства", en: "Evidence records" },
  annotationRecords: { ru: "Аннотации белков, на которых строятся гипотезы", en: "Protein annotations the hypotheses rest on" },
  annotation: { ru: "Аннотация", en: "Annotation" },
  drug: { ru: "Препарат", en: "Drug" },
  roles: { ru: "Роли", en: "Roles" },
  rawAction: { ru: "исходное действие", en: "raw action" },
  pmids: { ru: "PubMed", en: "PubMed" },
  provenance: { ru: "Происхождение данных и параметры", en: "Provenance and parameters" },
  endpoint: { ru: "Адрес запроса", en: "Endpoint" },
  requestBody: { ru: "Тело запроса", en: "Request body" },
  serverGenerated: { ru: "Отчёт создан сервисом (generated_at)", en: "Report generated by the service (generated_at)" },
  explanationMethod: { ru: "Метод пояснения", en: "Explanation method" },
  frozenTag: { ru: "Замороженный тег исследования", en: "Frozen research tag" },
  siteCommit: { ru: "Коммит сборки сайта", en: "Site build commit" },
  siteOrigin: { ru: "Сайт", en: "Site" },
  generator: { ru: "Генератор PDF", en: "PDF generator" },
  generatorValue: { ru: "DDI-Net web, экспорт в браузере (@react-pdf/renderer)", en: "DDI-Net web, in-browser export (@react-pdf/renderer)" },
  payloadSha: { ru: "SHA-256 данных ответа", en: "SHA-256 of the response data" },
  payloadShaNote: {
    ru: "Хэш JSON ответа(ов) сервиса в каноническом виде (ключи отсортированы, сериализация JSON.stringify). Тот же хэш записан в сопутствующем JSON-файле, который можно скачать кнопкой «JSON» рядом с «Экспорт PDF».",
    en: "Hash of the service response(s) as canonical JSON (keys sorted, serialised with JSON.stringify). The same hash is in the companion JSON file, available from the “JSON” button next to “Export PDF”.",
  },
  graphTruncation: { ru: "Усечение графа (не показано белков A / B)", en: "Graph truncation (proteins of A / B not shown)" },
  retrievalTimes: {
    ru: "Время получения записей указано у каждой записи (retrieved_at) так, как его вернул сервис; для локальных выгрузок это дата выгрузки, для инструкций — дата запроса.",
    en: "Retrieval times are given per record (retrieved_at) as returned by the service: the export date for local extracts, the request date for labels.",
  },

  // ── limitations ─────────────────────────────────────────────────────────
  limitsCore: { ru: "Основные ограничения", en: "Core limitations" },
  limitsFromApi: { ru: "Ограничения, сообщённые сервисом для этого отчёта", en: "Limitations reported by the service for this report" },
  lim1: {
    ru: "DDI-Net — исследовательский инструмент, а не система поддержки клинических решений и не медицинское изделие. Решения о лекарствах принимают врач или фармацевт.",
    en: "DDI-Net is a research tool, not clinical decision support and not a medical device. Decisions about medicines belong to a doctor or pharmacist.",
  },
  lim2: {
    ru: "Пары без записи о взаимодействии не подтверждены как безопасные. Отсутствие документа означает только, что проверенные источники его не содержат.",
    en: "Unlabelled pairs are not confirmed safe. A missing record means only that the sources checked do not contain one.",
  },
  lim3: {
    ru: "Оценки BIO-GINE не являются откалиброванными вероятностями клинического вреда: температурная калибровка подобрана на проверочных парах с долей положительных 50% против случайно набранных непомеченных пар.",
    en: "BIO-GINE scores are not calibrated probabilities of clinical harm: temperature scaling was fitted on validation pairs at 50% prevalence against randomly drawn unlabelled pairs.",
  },
  lim4: {
    ru: "Порядок препаратов в выгрузке DrugBank (TDC) подтверждён измерением только для двух типов взаимодействий; для остальных он либо не имеет значения (симметричные типы), либо не подтверждён, поэтому утверждения о направлении («A повышает концентрацию B») не делаются.",
    en: "The drug order in the DrugBank (TDC) export was verified by measurement for only two interaction types; for the others it is either meaningless (symmetric types) or unverified, so directional claims (“A raises the level of B”) are not made.",
  },
  lim5: {
    ru: "Внешние медицинские источники (инструкции FDA, RxNorm) могут быть неполными или недоступными в момент запроса; их статус указан в разделе «Проверенные источники».",
    en: "External medical evidence (FDA labels, RxNorm) may be incomplete or unavailable at query time; its status is listed under “Sources checked”.",
  },
  lim6: {
    ru: "Попарные результаты ничего не говорят о сочетании трёх и более препаратов одновременно; такой модели здесь нет, и общий балл не вычисляется.",
    en: "Pairwise results say nothing about three or more drugs taken together; no such model exists here, and no overall score is computed.",
  },

  // ── appendix ────────────────────────────────────────────────────────────
  appendixIntro: {
    ru: "Сводка ключевых полей в формате JSON для автоматической проверки. Полные ответы сервиса — в сопутствующем JSON-файле (тот же SHA-256).",
    en: "Key fields as JSON for automated checking. The full service responses are in the companion JSON file (same SHA-256).",
  },

  // ── multi ───────────────────────────────────────────────────────────────
  multiSumDrugs: { ru: "Проанализировано препаратов: {n}; уникальных пар: {p}. Каждая пара проверена отдельно.", en: "Drugs analysed: {n}; unique pairs: {p}. Each pair was examined on its own." },
  multiSumStatus: { ru: "Пары по виду найденной документации:", en: "Pairs by kind of documentation found:" },
  multiSumReview: { ru: "Пар, отмеченных сервисом для подробного изучения: {n}.", en: "Pairs flagged by the service for a closer look: {n}." },
  multiSumAbstain: { ru: "Пар, где модель обучалась на их записи (оценка не учитывается): {n}.", en: "Pairs whose own record the model was trained on (score not counted): {n}." },
  multiNoOverall: {
    ru: "Общего балла для набора препаратов нет и он не вычисляется: попарные находки нельзя сложить в вывод о сочетании нескольких лекарств.",
    en: "There is no overall score for the set, and none is computed: pairwise findings cannot be added up into a conclusion about several medicines together.",
  },
  pair: { ru: "Пара", en: "Pair" },
  found: { ru: "Что найдено", en: "What was found" },
  dbRecords: { ru: "DrugBank", en: "DrugBank" },
  labelRecords: { ru: "Инстр.", en: "Labels" },
  hypCount: { ru: "Гип.", en: "Hyp." },
  modelCol: { ru: "Модель", en: "Model" },
  reasons: { ru: "Почему стоит посмотреть", en: "Why look closer" },
  matrixTitle: { ru: "Матрица пар", en: "Pair matrix" },
  matrixNote: {
    ru: "Ячейка — вид найденной документации для пары (строка × столбец), число — калиброванная оценка модели. Цвет обозначает вид источника, а не опасность.",
    en: "Each cell is the kind of documentation found for the pair (row × column); the number is the calibrated model score. Colour encodes the kind of source, not danger.",
  },
  networkNote: {
    ru: "Линии: сплошная — запись в базе или инструкции, штриховая — только сигнал модели, точечная — документов не найдено. Толстая линия — пара отмечена для изучения.",
    en: "Lines: solid — database or label record; dashed — model signal only; dotted — no documentation found. A thick line marks a pair flagged for a closer look.",
  },
  mechanismSummaryMulti: {
    ru: "Для каждой пары сервис сообщает число гипотез о механизме; сами гипотезы, белки и пути приводятся в отчёте по паре (анализатор).",
    en: "For each pair the service reports the number of mechanism hypotheses; the hypotheses, proteins and pathways themselves are in the per-pair report (Analyzer).",
  },
  regimesNote: {
    ru: "Режим показывает, были ли препараты пары в обучающей выборке модели: S1 — оба (не оценивался), S2 — один, S3 — ни одного.",
    en: "The regime says whether the pair's drugs were in the model's training set: S1 — both (not evaluated), S2 — one, S3 — neither.",
  },
  scoreNotCounted: { ru: "не учитывается", en: "not counted" },
  matrixNotCounted: { ru: "не уч.", en: "n/c" },
  matrixNotCountedNote: { ru: "«не уч.» — оценка не учитывается: модель обучалась на записи этой пары.", en: "“n/c” — not counted: the model was trained on this pair's record." },
  noModelScore: { ru: "нет", en: "none" },
  code: { ru: "Код", en: "Code" },
} satisfies Record<string, Bi>;

export type StringKey = keyof typeof S;

/** Short codes for evidence status, used in the matrix. */
export const STATUS_CODE: Record<string, string> = {
  contraindication_in_label: "CI",
  warning_in_label: "L",
  conflicting_evidence: "≠",
  documented_no_severity: "DB",
  model_signal_only: "M",
  no_documented_evidence_found: "–",
};
