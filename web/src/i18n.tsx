// Bilingual UI. Russian is the default; English stays available because the
// scientific vocabulary and the manuscript are English.
//
// SCOPE RULE: only UI text is translated. Canonical biomedical identifiers —
// DrugBank IDs, UniProt accessions, gene symbols, Reactome pathway IDs and
// names — are NEVER translated or replaced; they are the data. Drug names carry
// a Russian transliteration that is explicitly labelled as a UI label.
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type Lang = "ru" | "en";

/** A bilingual string. Long prose lives next to its component as a `Bi`, so the
 *  dictionary below stays the chrome vocabulary rather than the whole site. */
export interface Bi { ru: string; en: string }


type Dict = Record<string, { ru: string; en: string }>;

const DICT: Dict = {
  // ── nav / chrome ─────────────────────────────────────────────
  "nav.analyze": { ru: "АНАЛИЗ", en: "ANALYZE" },
  "nav.model": { ru: "МОДЕЛЬ", en: "MODEL" },
  "nav.research": { ru: "РЕЗУЛЬТАТЫ", en: "RESEARCH" },
  "nav.data": { ru: "ДАННЫЕ", en: "DATA" },
  "nav.drugs": { ru: "ПРЕПАРАТЫ", en: "DRUGS" },
  "nav.limitations": { ru: "ОГРАНИЧЕНИЯ", en: "LIMITATIONS" },
  "nav.repo": { ru: "Репозиторий", en: "Repository" },
  "nav.home": { ru: "DDI-Net, на главную", en: "DDI-Net home" },

  "footer.disclaimer": {
    ru: "Regeneron ISEF · Вычислительная биология и биоинформатика. Эта система — исследовательский прототип и",
    en: "Regeneron ISEF · Computational Biology & Bioinformatics. This system is a computational research prototype and is",
  },
  "footer.notvalidated": {
    ru: "не валидирована для принятия клинических решений",
    en: "not validated for clinical decision-making",
  },
  "footer.notdevice": {
    ru: ". Это не медицинское изделие и не система поддержки клинических решений.",
    en: ". It is not a medical device and not a clinical decision support system.",
  },
  "footer.readlimits": { ru: "Полный список ограничений →", en: "Read the full limitations →" },
  "footer.tag": { ru: "замороженный тег", en: "frozen tag" },
  "footer.commit": { ru: "коммит", en: "commit" },

  // ── home ─────────────────────────────────────────────────────
  "home.eyebrow": { ru: "Исследование лекарственных взаимодействий на основе биологии", en: "Mechanism-aware drug interaction research" },
  "home.title1": { ru: "Понять биологию", en: "Understand the biology" },
  "home.title2": { ru: "за лекарственными взаимодействиями.", en: "behind drug interactions." },
  "home.lede": {
    ru: "Могут ли биологически обоснованные представления препаратов переноситься на препараты, которых модель никогда не видела — без опоры на известную сеть взаимодействий? Пререгистрированное исследование с контролями фальсификации.",
    en: "Can biologically grounded drug representations transfer to drugs a model has never seen — without relying on the known interaction network? A preregistered study with falsification controls.",
  },
  "home.cta.pair": { ru: "Разобрать пару препаратов", en: "Explore a drug pair" },
  "home.cta.model": { ru: "Как устроена модель", en: "Explore the model" },
  "home.rail.dataset": { ru: "TDC DrugBank · 1 705 препаратов · 191 392 пар", en: "TDC DrugBank · 1,705 drugs · 191,392 pairs" },
  "home.rail.research": { ru: "Исследовательское ПО · не клинический инструмент", en: "Research software · not a clinical tool" },

  "home.s1.eyebrow": { ru: "01 — Проблема", en: "01 — The problem" },
  "home.s1.title": { ru: "Известных взаимодействий недостаточно.", en: "Known interactions are not enough." },
  "home.s1.p1": {
    ru: "Большинство бенчмарков делят данные на уровне пар. Один и тот же препарат тогда попадает и в обучение, и в тест, и модель набирает очки, узнавая знакомые препараты и их известное окружение — контекст, которого у по-настоящему нового соединения нет.",
    en: "Most drug-interaction benchmarks split data at the level of pairs. A single drug can then appear in both training and test pairs, and a model scores well by recognising familiar drugs and their known interaction neighbourhoods — context that vanishes for a genuinely new compound.",
  },
  "home.s1.p2": {
    ru: "Деление по препаратам убирает эту лазейку: каждый тестовый препарат не виден при обучении. Таблица показывает, насколько полностью исчезает утечка.",
    en: "Splitting by drug removes that shortcut: every test drug is unseen. The table shows how completely the leak disappears.",
  },
  "home.s1.hand": { ru: "а что если препарат новый?", en: "what happens when the drug is new?" },
  "home.s1.tablehead": { ru: "Тестовые пары, где оба препарата уже были в обучении", en: "Test pairs with both drugs already in training" },
  "home.s1.random": { ru: "Случайное деление пар", en: "Random pair split" },
  "home.s1.drug": { ru: "Отложенные препараты", en: "Drug holdout" },
  "home.s1.scaffold": { ru: "Отложенные скаффолды", en: "Scaffold holdout" },

  "home.s2.eyebrow": { ru: "02 — Вопрос и результат", en: "02 — The question & the result" },
  "home.s2.title": { ru: "Переносится ли биологическая идентичность на новые препараты?", en: "Does biological identity transfer to unseen drugs?" },
  "home.s2.p": {
    ru: "BIO-GINE кодирует каждый препарат из его молекулярной структуры и биологических аннотаций — белков, на которые он действует, и путей, в которых те участвуют, — при этом ни одно ребро графа взаимодействий не входит в представление. На препаратах, отложенных из обучения:",
    en: "BIO-GINE encodes each drug from its molecular structure and its biological annotations — the proteins it acts on and the pathways they sit in — with no edge of the interaction graph entering the representation. Evaluated on drugs held out of training:",
  },
  "home.s2.m4": { ru: "BIO-GINE M4 · объединённый тест (S2+S3)", en: "BIO-GINE M4 · pooled drug-holdout (S2+S3)" },
  "home.s2.m0": { ru: "Молекулярный GINE (M0)", en: "Aligned molecular GINE (M0)" },
  "home.s2.delta": { ru: "Прирост к чисто молекулярной модели", en: "Improvement over molecular-only" },
  "home.s2.deltasub": { ru: "AUPRC · все пять сидов согласны по направлению", en: "AUPRC · all five seeds agree in direction" },
  "home.s2.note": {
    ru: "Объединённый = S2 (один препарат отложен) + S3 (оба отложены). AUPRC 0,5 — случайное ранжирование при доле положительных 50%. Число осмысленно только рядом с базовыми моделями.",
    en: "Pooled = S2 (one drug held out) + S3 (both held out). AUPRC 0.5 is a random ranker at 50% prevalence. The number is meaningful only against its baselines.",
  },

  "home.s3.eyebrow": { ru: "03 — Контроль, на котором держится вывод", en: "03 — The control that carries the claim" },
  "home.s3.title": { ru: "Идентичность, а не популярность.", en: "Identity, not popularity." },
  "home.s3.p": {
    ru: "У хорошо изученных препаратов больше и аннотаций, и задокументированных взаимодействий — значит, прирост от биологии мог бы просто отражать степень изученности. CONTROL F переставляет, к каким именно белкам привязан каждый препарат, сохраняя при этом точное число аннотаций на препарат и на белок. Если бы сигналом был подсчёт, результат почти не изменился бы.",
    en: "Well-studied drugs carry more annotations and more documented interactions, so a biological gain could just be detecting how much a drug has been studied. CONTROL F rewires which proteins each drug is annotated against while preserving the exact annotation count per drug and per protein. If counting were the signal, performance should barely move.",
  },
  "home.s3.true": { ru: "Настоящая биология · M4", en: "True biology · M4" },
  "home.s3.shuf": { ru: "Перемешанная биология (степени сохранены)", en: "Degree-preserving shuffled biology" },
  "home.s3.lost": {
    ru: "AUPRC теряется при разрушении идентичности — больше, чем весь выигрыш от добавления биологии.",
    en: "AUPRC lost when identity is destroyed — larger than the entire benefit of adding biology.",
  },
  "home.s3.caveat": {
    ru: "Это подтверждает, что биологическая идентичность несёт информацию сверх числа аннотаций. Это не доказывает причинный механизм.",
    en: "This supports that biological identity carries information beyond annotation count. It does not establish causal mechanism.",
  },

  "home.honest.badge": { ru: "Честная отчётность", en: "Reported honestly" },
  "home.honest.lede": { ru: "Это исследование сообщает и то, что против него.", en: "This study reports against itself." },
  "home.honest.1a": { ru: "Лестница доказательств", en: "The evidence ladder is" },
  "home.honest.1b": { ru: "немонотонна", en: "non-monotonic" },
  "home.honest.1c": { ru: "и контроль SUM", en: "and the SUM control" },
  "home.honest.1d": { ru: "превышают пререгистрированную основную M4", en: "both exceed the preregistered primary M4" },
  "home.honest.2": { ru: "Гипотеза H-V2-5 была поисковой, и её направление не подтвердилось.", en: "Hypothesis H-V2-5 was an exploratory direction and was not supported." },
  "home.honest.3": { ru: "Held-out R² в CONTROL E неидентифицируем (нулевая дисперсия целевой переменной).", en: "CONTROL E's held-out R² is not identifiable (target variance is zero)." },
  "home.honest.4": { ru: "Оценка на отложенных скаффолдах в финальном V2 не проводилась.", en: "Scaffold-disjoint evaluation was not performed in final V2." },
  "home.cta.results": { ru: "Смотреть результаты", en: "Read the results" },

  // ── analyze ──────────────────────────────────────────────────
  "an.eyebrow": { ru: "Анализ пары препаратов", en: "Analyze a drug pair" },
  "an.badge": { ru: "Обученная модель на этом развёртывании не подключена", en: "No trained model connected on this deployment" },
  "an.title": { ru: "Выберите два препарата.", en: "Select two drugs." },
  "an.lede1": { ru: "Выберите два препарата из вселенной в", en: "Choose two drugs from the" },
  "an.lede2": {
    ru: " препаратов. Биологические данные ниже — настоящие, из замороженного датасета. Калиброванная вероятность взаимодействия не показывается, потому что файл весов модели здесь не установлен — см. панель справа.",
    en: "-drug experimental universe. The biological evidence below is real, read from the frozen dataset. A calibrated interaction probability is not shown, because the frozen inference checkpoint is not installed here — see the panel on the right.",
  },
  "an.drugA": { ru: "Препарат A", en: "Drug A" },
  "an.drugB": { ru: "Препарат B", en: "Drug B" },
  "an.search": { ru: "Поиск: название или DrugBank ID", en: "Search: name or DrugBank ID" },
  "an.loading": { ru: "загрузка препаратов…", en: "loading drugs…" },
  "an.quick": { ru: "быстрый выбор", en: "quick picks" },
  "an.schematic": { ru: "Схематичная пара · синтетическая геометрия", en: "Schematic pair · synthetic geometry" },
  "an.illustrative": { ru: "Иллюстрация", en: "Illustrative" },
  "an.schematicnote": {
    ru: "Шаростержневая геометрия сгенерирована и схематична — это не реальная 3D-конформация",
    en: "Ball-and-stick geometry is generated and schematic — not the real 3D conformer of",
  },
  "an.prediction": { ru: "Предсказанная вероятность взаимодействия", en: "Predicted interaction probability" },
  "an.uncertainty": { ru: "неопределённость", en: "uncertainty" },
  "an.notestimated": { ru: "± не оценена", en: "± not estimated" },
  "an.whenInstalled": {
    ru: "Когда файл весов будет установлен и его SHA-256 проверен, здесь появится калиброванная вероятность. Это будет уверенность модели в классе «задокументированное взаимодействие», а не показатель риска для пациента — и никогда не клиническая рекомендация.",
    en: "When the frozen checkpoint is installed and its SHA-256 verified, a calibrated probability appears here. It would be the model's confidence in the documented-DDI class, not a patient risk figure — and never a clinical recommendation.",
  },
  "an.provenance": { ru: "Происхождение данных", en: "Provenance" },
  "an.prov1": { ru: "Препараты и биология:", en: "Drugs & biology:" },
  "an.prov2": { ru: "Конфигурация модели:", en: "Model config:" },
  "an.prov3": { ru: "Ни одно ребро графа взаимодействий не входит в представление препарата.", en: "No edge of the interaction graph enters the drug representation." },
  "an.evidence": { ru: "Данные о белках (показано из", en: "Protein evidence (preview of" },
  "an.loadfail": { ru: "Не удалось загрузить датасет препаратов:", en: "Could not load the drug dataset:" },

  // ── drug explorer ────────────────────────────────────────────
  "dx.eyebrow": { ru: "Каталог препаратов", en: "Drug explorer" },
  "dx.title": { ru: "Экспериментальная вселенная.", en: "Browse the experimental universe." },
  "dx.lede": {
    ru: "препаратов. Поиск по названию (рус./англ.) или по DrugBank ID. Канонический идентификатор — DrugBank ID, он показывается всегда.",
    en: "drugs. Search by name (English or Russian) or by DrugBank ID. The canonical identifier is the DrugBank ID and is always shown.",
  },
  "dx.namenote": {
    ru: "Английские названия — INN из DrugCentral (сопоставление по InChIKey), настоящие данные. Русские — транслитерация INN, служебная подпись интерфейса, а не данные источника. У {n} препаратов названия нет — показывается только ID.",
    en: "English names are INN from DrugCentral (matched on InChIKey) — real data. Russian names are a transliteration of the INN, a UI label rather than sourced data. {n} drugs have no name and show the ID alone.",
  },
  "dx.searchph": { ru: "Например: метформин, warfarin, DB00331, C4H11NO3…", en: "e.g. metformin, варфарин, DB00331, C4H11NO3…" },
  "dx.col.id": { ru: "DrugBank ID", en: "DrugBank ID" },
  "dx.col.name": { ru: "название", en: "name" },
  "dx.col.formula": { ru: "формула", en: "formula" },
  "dx.col.proteins": { ru: "белки", en: "proteins" },
  "dx.col.pathways": { ru: "пути", en: "pathways" },
  "dx.col.targets": { ru: "мишени", en: "targets" },
  "dx.nomatch": { ru: "Ничего не найдено", en: "No match" },
  "dx.nomatchfor": { ru: "Нет препаратов по запросу", en: "No drug matches" },
  "dx.showing": { ru: "показаны первые", en: "showing first" },
  "dx.of": { ru: "из", en: "of" },
  "dx.narrow": { ru: "— уточните запрос", en: "— search to narrow" },
  "dx.noname": { ru: "название отсутствует в источнике", en: "no name in source" },
  "dx.targets": { ru: "мишени", en: "targets" },
  "dx.enzymes": { ru: "ферменты", en: "enzymes" },
  "dx.transporters": { ru: "транспортёры", en: "transporters" },
  "dx.proteins": { ru: "белки", en: "proteins" },
  "dx.pathways": { ru: "пути", en: "pathways" },
  "dx.proteinsPreview": { ru: "Белки (показано из", en: "Proteins (preview of" },
  "dx.pathwaysPreview": { ru: "Пути Reactome (показано из", en: "Reactome pathways (preview of" },
  "dx.canonical": { ru: "Названия белков, генов и путей — канонические идентификаторы UniProt/Reactome и не переводятся.", en: "Protein, gene and pathway names are canonical UniProt/Reactome identifiers and are not translated." },

  // ── model ────────────────────────────────────────────────────
  "md.eyebrow": { ru: "Как устроена BIO-GINE", en: "How BIO-GINE works" },
  "md.title": { ru: "Препарат, закодированный тремя способами.", en: "A drug, encoded three ways." },
  "md.lede": {
    ru: "BIO-GINE строит каждый препарат из молекулярной структуры и биологических аннотаций, сливает их в один вектор и оценивает пару симметрично. Ни одно ребро известного графа взаимодействий не входит в представление — именно поэтому модель можно оценивать на препаратах, отложенных из обучения.",
    en: "BIO-GINE builds each drug from its molecular structure and its biological annotations, fuses them into one vector, and scores a pair symmetrically. No edge of the known interaction graph enters the representation — which is what lets it be evaluated on drugs held out of training.",
  },
  "md.symtitle": { ru: "Почему декодер симметричен", en: "Why the decoder is symmetric" },
  "md.symbody1": {
    ru: "«A взаимодействует с B» — то же утверждение, что «B взаимодействует с A». Вместо того чтобы надеяться, что модель это выучит, декодер собран из операций, коммутативных по построению. Конкатенация",
    en: "\"A interacts with B\" is the same statement as \"B interacts with A\". Rather than hoping the model learns this, the decoder is built from operations that are commutative by construction. A concatenation",
  },
  "md.symbody2": {
    ru: "нарушила бы симметрию ровно для тех пар, где у одного препарата биология есть, а у другого нет — поэтому маски объединяются поэлементными min и max.",
    en: "would break symmetry for exactly the pairs where one drug has biology and the other does not — so the masks are combined as elementwise min and max instead.",
  },
  "md.params": { ru: "параметров", en: "parameters" },
  "md.biodim": { ru: "размерность биологии", en: "bio dim" },
  "md.steps": { ru: "шагов оптимизатора", en: "optimizer steps" },
  "md.grid": { ru: "сетка валидации", en: "validation grid" },
  "md.honest": {
    ru: "Честное замечание: добавление ступени путей (M3→M4) не улучшило AUPRC на отложенных препаратах, а вариант с SUM-агрегацией превзошёл эту MEAN-модель на тесте. См. раздел «Результаты».",
    en: "Honest note: adding the pathway rung (M3→M4) did not improve held-out AUPRC, and the SUM-aggregation variant outperformed this MEAN model on the test set. See Research.",
  },
  "md.implemented": { ru: "реализовано", en: "implemented" },

  // ── data ─────────────────────────────────────────────────────
  "dt.eyebrow": { ru: "Данные и происхождение", en: "Data & provenance" },
  "dt.title": { ru: "У каждого ребра есть источник.", en: "Every edge has a source." },
  "dt.lede1": { ru: "препаратов и", en: "drugs and" },
  "dt.lede2": { ru: "задокументированных положительных пар DDI (датасет", en: "documented positive DDI pairs (dataset" },
  "dt.lede3": { ru: "был исключён из-за неразбираемого SMILES", en: "was excluded for an unparseable SMILES" },
  "dt.lede4": { ru: "пар). Биологический граф строится только из собственных аннотаций препарата —", en: "pairs). The biological graph is built only from a drug\u2019s own annotations —" },
  "dt.lede5": { ru: "ни одно ребро взаимодействий в него не входит", en: "no interaction edge enters it" },
  "dt.m.drugs": { ru: "препаратов", en: "drugs" },
  "dt.m.pairs": { ru: "задокументированных пар DDI", en: "documented DDI pairs" },
  "dt.m.dp": { ru: "рёбер препарат–белок", en: "drug–protein edges" },
  "dt.m.pp": { ru: "рёбер белок–путь", en: "protein–pathway edges" },
  "dt.sources": { ru: "Источники", en: "Sources" },
  "dt.relations": { ru: "Отношения препарат → белок", en: "Drug → protein relations" },
  "dt.col.rel": { ru: "тип отношения", en: "relation type" },
  "dt.col.edges": { ru: "рёбер", en: "edges" },
  "dt.col.share": { ru: "доля", en: "share" },
  "dt.evidence": {
    ru: "Тип свидетельства хранится на каждом ребре и различает, откуда известно отношение:",
    en: "Evidence type is carried on every edge and distinguishes how a relation is known:",
  },
  "dt.evidence2": { ru: ". Они соответствуют лестнице свидетельств M1→M4.", en: ". These map to the M1→M4 evidence ladder." },
  "dt.notmean": { ru: "Чего покрытие не означает", en: "What the coverage does not mean" },
  "dt.notmeanp1": {
    ru: "Эти 1 705 препаратов — отобранное TDC подмножество DrugBank (~15 000 препаратов) по неизвестным нам критериям, а не репрезентативная выборка. Покрытие высокое, но неполное:",
    en: "These 1,705 drugs are a TDC-selected subset of DrugBank (~15,000 drugs) chosen by upstream criteria unknown to us — not a representative sample. Coverage is high but not complete:",
  },
  "dt.notmeanp2": {
    ru: "препаратов не имеют белковых аннотаций. Данные о нежелательных явлениях (SIDER) присутствуют для полноты происхождения, но исключены из обучения и из всех предсказательных утверждений на этом сайте.",
    en: "of drugs have no protein annotation. Adverse-event (SIDER) data is present for provenance but is held out of training and out of every predictive claim on this site.",
  },

  // ── limitations ──────────────────────────────────────────────
  "lm.eyebrow": { ru: "Ограничения и угрозы валидности", en: "Limitations & threats to validity" },
  "lm.title": { ru: "Чего это не показывает.", en: "What this does not show." },
  "lm.lede1": {
    ru: "Научный результат надёжен ровно настолько, насколько честно перечислены его ограничения. Вот реальные ограничения замороженного исследования —",
    en: "A research result is only as trustworthy as the limitations stated alongside it. These are the real constraints of the frozen study —",
  },
  "lm.lede2": {
    ru: "препаратов без белковых аннотаций, одно разбиение, пять сидов, отсутствие клинической валидации.",
    en: "of drugs lack protein annotation, one partition, five seeds, no clinical validation.",
  },
  "lm.disclaimer": {
    ru: "Эта система — вычислительный исследовательский прототип и не валидирована для принятия клинических решений. Это не медицинское изделие и не система поддержки клинических решений.",
    en: "This system is a computational research prototype and is not validated for clinical decision-making. It is not a medical device and not a clinical decision support system.",
  },

  // ── research ─────────────────────────────────────────────────
  "rs.eyebrow": { ru: "Результаты — из замороженного состояния V2", en: "Results — read from the frozen V2 state" },
  "rs.title": { ru: "Все доказательства целиком.", en: "The evidence, in full." },
  "rs.lede1": { ru: "Каждое число ниже сгенерировано из замороженных артефактов на теге", en: "Every number below is generated from the frozen artifacts at tag" },
  "rs.lede2": {
    ru: ". Доверительные интервалы, p-значения с поправкой Холма и размеры эффекта пересчитываются из по-сидовых значений, а не перепечатываются. Основная конфигурация была зафиксирована до любой оценки на тесте.",
    en: ". Confidence intervals, Holm-adjusted p-values and effect sizes are recomputed from the per-seed values, not retyped. The primary configuration was frozen before any test evaluation.",
  },
  "rs.pooled": { ru: "ОБЪЕДИНЁННЫЙ ТЕСТ (S2+S3)", en: "POOLED DRUG-HOLDOUT (S2+S3)" },
  "rs.s3": { ru: "S3 · ОБА ПРЕПАРАТА ОТЛОЖЕНЫ", en: "S3 · BOTH DRUGS HELD OUT" },
  "rs.cmp.pooled": { ru: "Сравнение моделей — AUPRC на объединённом тесте", en: "Model comparison — pooled drug-holdout AUPRC" },
  "rs.cmp.s3": { ru: "Сравнение моделей — AUPRC на S3 (оба препарата отложены)", en: "Model comparison — S3 AUPRC (both drugs held out)" },
  "rs.note.s3": {
    ru: "S3 — самое трудное условие: ни у одного препарата нет смежности в обучающем графе взаимодействий. Модель Dual, которая на неё опирается, деградирует сильнее всех.",
    en: "S3 is the hardest condition: neither drug has any interaction adjacency in the training graph. The Dual model, which relies on that adjacency, degrades most here.",
  },
  "rs.note.pooled": {
    ru: "Цвет: голубой — полная модель · синий — базовые · фиолетовый — контроли на срезание пути. Ось начинается с 0,5 и никогда не обрезается.",
    en: "Colour: cyan = full model · blue = baselines · violet = shortcut controls. Axis begins at 0.5 and is never truncated.",
  },
  "rs.hyp": { ru: "Пререгистрированные гипотезы", en: "Preregistered hypotheses" },
  "rs.hyplede": {
    ru: "Пять гипотез, зафиксированных до любого запуска. Поправка Холма–Бонферрони охватывает все пять, включая поисковую H-V2-5 — что делает поправку строже для четырёх подтверждающих.",
    en: "Five hypotheses, fixed before any run. Holm–Bonferroni correction spans all five, including the exploratory H-V2-5 — which makes the correction stricter for the four confirmatory ones.",
  },
  "rs.confirmatory": { ru: "подтверждающая", en: "confirmatory" },
  "rs.exploratory": { ru: "поисковая", en: "exploratory" },
  "rs.ladder": { ru: "Лестница свидетельств — немонотонная", en: "Evidence ladder — non-monotonic" },
  "rs.ladderlede": {
    ru: "Биологические свидетельства добавляются по одному источнику за раз. Каждый биологический вариант превосходит базовую модель без биологии (M0), но лестница не возрастает монотонно: M2 — сильнейший вариант, а контроль SUM превосходит основную MEAN-модель. M4 была зафиксирована как основная на валидации до открытия теста — это пререгистрированная модель, а не лучшая на тесте.",
    en: "Adding biological evidence one source at a time. Every biological variant beats the no-biology baseline (M0), but the ladder does not rise monotonically: M2 is the strongest variant, and the SUM control beats the primary MEAN model. M4 was fixed as primary on validation before the test set was opened — it is the preregistered model, not the best test performer.",
  },
  "rs.controls": { ru: "Контроли на обходные пути", en: "Shortcut controls" },
  "rs.cf.title": { ru: "CONTROL F — перемешивание идентичности", en: "CONTROL F — identity shuffle" },
  "rs.cf.body": {
    ru: "Перепривязка того, к каким белкам аннотирован каждый препарат, при сохранении степеней снижает AUPRC с {a} до {b}. Изменено {c}% рёбер; сохранено {d}%.",
    en: "Rewiring which proteins each drug is annotated against, at fixed degree, drops AUPRC from {a} to {b}. {c}% of edges changed; {d}% retained.",
  },
  "rs.ca.title": { ru: "CONTROL A — базовая модель только по счётчикам", en: "CONTROL A — count-only baseline" },
  "rs.ca.body": {
    ru: "Случайный лес только на числе аннотаций достигает {a} — выше случайного, то есть изученность действительно предсказательна, но далеко ниже полной модели.",
    en: "A random forest on annotation counts alone reaches {a} — above chance, so popularity is genuinely predictive, but far below the full model.",
  },
  "rs.ce.title": { ru: "CONTROL E — неидентифицируем", en: "CONTROL E — not identifiable" },
  "rs.ce.body": {
    ru: "Запланированный зонд предсказывает обучающую степень DDI по эмбеддингу. Held-out R² не определён: у каждого отложенного препарата степень равна нулю, поэтому дисперсия целевой переменной нулевая. Train R² = {a}, приводится описательно.",
    en: "The planned probe predicts training-DDI degree from the embedding. Held-out R² is undefined: every held-out drug has degree zero, so target variance is zero. Train R² = {a}, reported descriptively.",
  },
  "rs.calib": { ru: "Калибровка", en: "Calibration" },
  "rs.caliblede": {
    ru: "Одна температура на сид, подобранная только на валидационных предсказаниях и применённая к замороженным тестовым. Ожидаемая ошибка калибровки падает примерно втрое; ранжирование не меняется, потому что температурное шкалирование монотонно.",
    en: "One temperature per seed, fitted only on validation predictions and applied to the frozen test predictions. Expected calibration error falls by roughly a factor of three; ranking is unchanged, because temperature scaling is monotonic.",
  },
  "rs.col.seed": { ru: "сид", en: "seed" },
  "rs.col.temp": { ru: "температура", en: "temperature" },
  "rs.col.ece": { ru: "ECE до → после", en: "ECE raw → scaled" },
  "rs.col.brier": { ru: "Brier до → после", en: "Brier raw → scaled" },
  "rs.headline": { ru: "Главный вывод", en: "Headline" },
  "rs.headlinep": {
    ru: "Биологическая идентичность несла предсказательную информацию, которая переносилась на невиданные препараты и не объяснялась количеством аннотаций — при одном замороженном разбиении по препаратам, на курированном подмножестве из {n} препаратов. Клинически не валидировано.",
    en: "Biological identity carried predictive information that transferred to unseen drugs and was not explained by annotation quantity — under one frozen drug partition, on a curated {n}-drug subset. Not clinically validated.",
  },

  // ── shared ───────────────────────────────────────────────────
  "c.notbuilt": { ru: "Ещё не построено", en: "Not yet built" },
  "c.source": { ru: "источник", en: "source" },
};

interface Ctx { lang: Lang; setLang: (l: Lang) => void; t: (k: string) => string; }
const LangCtx = createContext<Ctx>({ lang: "ru", setLang: () => {}, t: (k) => k });

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(() => {
    try {
      const s = localStorage.getItem("ddinet.lang");
      if (s === "ru" || s === "en") return s;
    } catch { /* storage may be blocked; fall through to the default */ }
    return "ru";
  });

  useEffect(() => {
    try { localStorage.setItem("ddinet.lang", lang); } catch { /* non-fatal */ }
    document.documentElement.lang = lang;
  }, [lang]);

  const t = (k: string) => DICT[k]?.[lang] ?? k;
  return <LangCtx.Provider value={{ lang, setLang, t }}>{children}</LangCtx.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useI18n(): Ctx {
  return useContext(LangCtx);
}

/** Resolve a bilingual literal. */
// eslint-disable-next-line react-refresh/only-export-components
export function pick(b: Bi, lang: Lang): string {
  return b[lang];
}

/** Fill {name} placeholders in a dictionary string. */
// eslint-disable-next-line react-refresh/only-export-components
export function fill(s: string, vars: Record<string, string | number>): string {
  return s.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? `{${k}}`));
}
