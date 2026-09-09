// Plain-language copy for the Analyze page explainer.
//
// Separate from the component so the wording itself can be tested. It is the
// highest-risk text on the site: simplifying an interaction score is exactly
// where a page slides into "the higher the number, the more dangerous", which
// is both forbidden wording and false. The frozen dataset holds documented
// interactions and sampled UNLABELLED pairs, not clinical outcomes.
import type { Bi } from "../i18n";

export interface Entry { term: Bi; body: Bi }

/** Plain sentence for the score, chosen by band. The bands are presentational
 *  only — the model outputs a continuous number and no threshold is claimed to
 *  separate anything. Deliberately about RESEMBLANCE to documented pairs, never
 *  about danger: the dataset holds documented interactions and sampled
 *  unlabelled pairs, not clinical outcomes. */
export function scoreSentence(calibrated: number): Bi {
  if (calibrated >= 0.66) {
    return {
      ru: "Модель считает, что эта пара сильно похожа на те, что уже описаны как взаимодействующие.",
      en: "The model finds this pair strongly resembles those already recorded as interacting.",
    };
  }
  if (calibrated >= 0.40) {
    return {
      ru: "Модель считает, что эта пара умеренно похожа на те, что уже описаны как взаимодействующие.",
      en: "The model finds this pair moderately resembles those already recorded as interacting.",
    };
  }
  return {
    ru: "Модель считает, что эта пара мало похожа на те, что уже описаны как взаимодействующие.",
    en: "The model finds this pair bears little resemblance to those already recorded as interacting.",
  };
}

export const SCORE_NOT_RISK: Bi = {
  ru: "Это сходство, а не риск: модель училась отличать задокументированные взаимодействия от случайно набранных пар и ничего не знает об исходах у людей.",
  en: "This is resemblance, not risk: the model learned to tell documented interactions from randomly drawn pairs and knows nothing about outcomes in people.",
};

export const HOW_IT_WORKS: Bi = {
  ru: "Ты выбираешь два препарата. Модель смотрит только на них самих — из чего состоит молекула, на какие белки в организме она действует и в каких биологических процессах эти белки участвуют. Список уже известных взаимодействий модель НЕ видит: именно поэтому её можно честно проверять на препаратах, которых она никогда не встречала. Дальше она говорит, насколько эта пара похожа на те пары, что задокументированы как взаимодействующие.",
  en: "You pick two drugs. The model looks only at the drugs themselves — what the molecule is made of, which proteins in the body it acts on, and which biological processes those proteins take part in. It never sees the list of known interactions: that is exactly what makes it fair to test on drugs it has never met. It then says how much this pair resembles the pairs that are documented as interacting.",
};

export const DRUG_NUMBERS: Entry[] = [
  {
    term: { ru: "Мишени", en: "Targets" },
    body: {
      ru: "Белки, на которые лекарство действует специально — ради лечебного эффекта. Обезболивающее блокирует белок, вызывающий боль: это и есть его мишень.",
      en: "Proteins the drug acts on deliberately, to produce its therapeutic effect. A painkiller blocks the protein that drives pain: that protein is its target.",
    },
  },
  {
    term: { ru: "Ферменты", en: "Enzymes" },
    body: {
      ru: "Белки, которые перерабатывают лекарство и выводят его из организма, в основном в печени. Это самое частое место взаимодействий: если два препарата обрабатывает один и тот же фермент, они мешают друг другу выводиться.",
      en: "Proteins that break the drug down and clear it from the body, mostly in the liver. This is where interactions most often arise: if one enzyme handles two drugs, they get in each other's way.",
    },
  },
  {
    term: { ru: "Транспортёры", en: "Transporters" },
    body: {
      ru: "Белки-перевозчики. Переносят лекарство через стенки клеток — в кровь, в мозг, обратно в кишечник. Их тоже можно «занять» другим препаратом.",
      en: "Carrier proteins. They move the drug across cell walls — into the blood, into the brain, back into the gut. Another drug can occupy them too.",
    },
  },
  {
    term: { ru: "Белки", en: "Proteins" },
    body: {
      ru: "Сколько всего белков связано с этим препаратом — мишени, ферменты, транспортёры и переносчики вместе. Общая мера того, насколько подробно препарат изучен.",
      en: "How many proteins are linked to this drug in total — targets, enzymes, transporters and carriers together. A rough measure of how thoroughly the drug has been studied.",
    },
  },
  {
    term: { ru: "Пути", en: "Pathways" },
    body: {
      ru: "Биологические процессы (по базе Reactome), в которых участвуют эти белки: свёртывание крови, обмен сахара и так далее. Два препарата могут не делить ни одного белка, но встретиться в одном процессе.",
      en: "Biological processes (from the Reactome database) those proteins take part in: blood clotting, sugar metabolism, and so on. Two drugs can share no protein at all and still meet inside one process.",
    },
  },
];

export const SCORE_NUMBERS: Entry[] = [
  {
    term: { ru: "Исследовательская оценка (калиброванная)", en: "Research model score (calibrated)" },
    body: {
      ru: "Число от 0 до 1. Насколько модель уверена, что эта пара относится к классу «задокументированное взаимодействие». Ближе к 1 — пара сильно похожа на те, что описаны в базе; ближе к 0 — не похожа. Это НЕ вероятность вреда и НЕ степень опасности.",
      en: "A number from 0 to 1. How confident the model is that this pair belongs to the documented-interaction class. Nearer 1 means the pair strongly resembles those recorded in the database; nearer 0 means it does not. It is NOT a probability of harm and NOT a level of danger.",
    },
  },
  {
    term: { ru: "Сырая оценка модели", en: "Raw model score" },
    body: {
      ru: "То же самое число до калибровки. Модель по своей природе слишком самоуверенна — сырые оценки жмутся к 0 и 1. Калибровка это исправляет.",
      en: "The same number before calibration. The model is naturally overconfident — raw scores crowd towards 0 and 1. Calibration corrects that.",
    },
  },
  {
    term: { ru: "T (температура)", en: "T (temperature)" },
    body: {
      ru: "Одно число, которым «разжимают» слишком уверенные оценки. Подобрано на отдельных данных, которых не было ни в обучении, ни в тесте. Порядок пар оно не меняет — только делает числа честнее.",
      en: "A single number that spreads out over-confident scores. It was fitted on separate data that appeared in neither training nor test. It never changes the ordering of pairs — only makes the numbers honest.",
    },
  },
  {
    term: { ru: "Запись в датасете", en: "Dataset record" },
    body: {
      ru: "Есть ли эта пара в базе задокументированных взаимодействий. Показано отдельно, потому что модель эту метку не видела — иначе она просто списывала бы ответ.",
      en: "Whether this pair appears in the database of documented interactions. Shown separately because the model never saw this label — otherwise it would simply be copying the answer.",
    },
  },
  {
    term: { ru: "Происхождение данных", en: "Provenance" },
    body: {
      ru: "Откуда именно взяты веса модели и данные: метка версии, коммит, файл весов и его контрольная сумма. Нужно, чтобы результат можно было воспроизвести и проверить, а не поверить на слово.",
      en: "Exactly where the model weights and data came from: version tag, commit, weights file and its checksum. There so the result can be reproduced and checked rather than taken on trust.",
    },
  },
];

export const CAVEATS: Bi[] = [
  {
    ru: "Высокая оценка не значит «опасно», а низкая не значит «безопасно». Модель обучена отличать задокументированные взаимодействия от случайных пар — она ничего не знает об исходах у людей.",
    en: "A high score does not mean “dangerous” and a low one does not mean “safe”. The model was trained to tell documented interactions from randomly drawn pairs — it knows nothing about outcomes in people.",
  },
  {
    ru: "Если пары нет в базе — это не значит, что взаимодействия нет. Около 86,8% всех возможных пар просто никто не проверял.",
    en: "A pair missing from the database does not mean there is no interaction. Roughly 86.8% of all possible pairs have simply never been checked.",
  },
  {
    ru: "Модель ничего не знает о конкретном человеке: ни возраста, ни дозы, ни работы почек и печени. Она видит только два препарата.",
    en: "The model knows nothing about an individual: not age, not dose, not kidney or liver function. It sees two drugs and nothing else.",
  },
  {
    ru: "Это исследовательский прототип. Он не проверялся на клинических исходах и не предназначен для принятия решений о лечении.",
    en: "This is a research prototype. It has never been tested against clinical outcomes and is not for making treatment decisions.",
  },
];
