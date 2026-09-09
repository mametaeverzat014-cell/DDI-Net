// Plain-language copy for the shared-biology block.
//
// The block's whole point is that "CYP2C9" tells a patient nothing. Each
// relation type gets a heading and an explanation written for someone who does
// not know what an enzyme is; the gene symbols sit underneath, small, for a
// pharmacist. 72% of shared enzymes are cytochrome P450s, so "фермент печени"
// is accurate rather than a simplification that shades into being wrong.
//
// The empty state matters most: 71% of random pairs share nothing, and that is
// exactly where a conventional checker's "no interactions found" gets read as
// "safe". It is written to refuse that reading.
import type { Bi } from "../i18n";
import type { Relation } from "../data/analyze";

export interface RelationCopy { title: Bi; body: Bi; node: Bi }

export const RELATION_COPY: Record<Relation, RelationCopy> = {
  enzyme: {
    title: { ru: "Перерабатываются одним ферментом", en: "Broken down by the same enzyme" },
    body: {
      ru: "Печень разбирает оба препарата с помощью одного и того же фермента. Когда два лекарства попадают на один «конвейер», они могут задерживать друг друга — одно может выводиться медленнее обычного, и в организме его окажется больше.",
      en: "The liver breaks down both drugs using the same enzyme. When two medicines share one production line, they can hold each other up — one may clear more slowly than usual and build up in the body.",
    },
    node: { ru: "фермент печени", en: "liver enzyme" },
  },
  transporter: {
    title: { ru: "Переносятся одним переносчиком", en: "Moved by the same transporter" },
    body: {
      ru: "Чтобы попасть в кровь или выйти из организма, лекарство проходит сквозь стенки клеток — его переносят особые белки-перевозчики. У этих двух препаратов перевозчик общий, и они могут за него конкурировать.",
      en: "To enter the blood or leave the body, a drug crosses cell walls — carried by special transporter proteins. These two drugs share a transporter and can compete for it.",
    },
    node: { ru: "белок-переносчик", en: "transporter protein" },
  },
  carrier: {
    title: { ru: "Переносятся по крови одним белком", en: "Carried in the blood by the same protein" },
    body: {
      ru: "В крови лекарства путешествуют, прицепившись к белкам-носителям. Носитель у этих двух общий — один препарат может вытеснить другой, и свободного лекарства в крови станет больше.",
      en: "In the bloodstream drugs travel attached to carrier proteins. These two share a carrier — one drug can displace the other, leaving more free drug in the blood.",
    },
    node: { ru: "белок крови", en: "blood carrier" },
  },
  target: {
    title: { ru: "Действуют на одну мишень", en: "Act on the same target" },
    body: {
      ru: "Оба препарата влияют на один и тот же белок в организме. В этой точке их действие может складываться или, наоборот, гасить друг друга.",
      en: "Both drugs act on the same protein in the body. At that point their effects may add up, or cancel each other out.",
    },
    node: { ru: "общая мишень", en: "shared target" },
  },
};

export const HEADING: Bi = {
  ru: "Что у этих препаратов общего в организме",
  en: "What these two drugs have in common in the body",
};

export const EMPTY_TITLE: Bi = {
  ru: "Общих записей не найдено",
  en: "No shared records found",
};

export const EMPTY_BODY: Bi = {
  ru: "Это не заключение о безопасности. Это значит только одно: в базе нет записей о том, что эти два препарата затрагивают одни и те же белки. Для большинства пар такие данные просто никогда не собирали.",
  en: "This is not a safety verdict. It means one thing only: the database holds no record that these two drugs touch the same proteins. For most pairs, that data was simply never collected.",
};

export const CAVEAT: Bi = {
  ru: "Общий фермент — повод посмотреть внимательнее, а не признак опасности. У многих пар с общим ферментом ничего не происходит: всё зависит от дозы, от того, насколько сильно каждый препарат занимает фермент, и от конкретного человека. Решение принимает врач, а не эта страница.",
  en: "A shared enzyme is a reason to look closer, not a sign of danger. For many pairs with a shared enzyme nothing happens: it depends on the dose, on how strongly each drug occupies the enzyme, and on the individual. A doctor decides, not this page.",
};

export const FACTS_NOT_PREDICTION: Bi = {
  ru: "Ниже — задокументированные аннотации из DrugBank, а не предсказание модели.",
  en: "Below are documented DrugBank annotations, not a model prediction.",
};
