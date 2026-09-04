// Russian labels for the small CLOSED vocabularies that come out of the frozen
// dataset (relation type, evidence type, DrugBank groups, drug type).
//
// SCOPE — why translating these is safe and translating anything else is not.
// These four fields are controlled vocabularies with a handful of members each,
// fixed by the pipeline that built data/mechanism_v1. Their Russian forms are
// standard pharmacological terms, so a label carries no new claim. Everything
// that identifies a biological entity — UniProt accession, gene symbol, protein
// name, Reactome pathway id and name, DrugBank ID, InChIKey, SMILES, formula —
// is left exactly as the source has it, because those ARE the data.
//
// The canonical English value is always kept available (rendered in `title`), so
// nothing is hidden behind a translation.
import type { Lang } from "../i18n";

const RELATION: Record<string, string> = {
  target: "мишень",
  enzyme: "фермент",
  transporter: "транспортёр",
  carrier: "переносчик",
};

const EVIDENCE: Record<string, string> = {
  DOCUMENTED_DATABASE_RELATION: "задокументированная связь в базе",
  EXPERIMENTAL_BIOACTIVITY: "экспериментальная биоактивность",
  CURATED_MOA: "курированный механизм действия",
};

const GROUP: Record<string, string> = {
  approved: "одобрен",
  investigational: "исследуется",
  experimental: "экспериментальный",
  withdrawn: "отозван",
  illicit: "запрещён",
  nutraceutical: "нутрицевтик",
  vet_approved: "одобрен в ветеринарии",
};

const DRUG_TYPE: Record<string, string> = {
  "small molecule": "малая молекула",
  biotech: "биотехнологический",
};

/** Pretty English form: DOCUMENTED_DATABASE_RELATION -> documented database relation. */
export function prettyEn(v: string): string {
  return v.replace(/_/g, " ").toLowerCase();
}

export function relationLabel(v: string, lang: Lang): string {
  return lang === "ru" ? RELATION[v] ?? v : v;
}

export function evidenceLabel(v: string, lang: Lang): string {
  return lang === "ru" ? EVIDENCE[v] ?? prettyEn(v) : prettyEn(v);
}

/** DrugBank `groups` is a pipe-joined multi-value field. */
export function groupsLabel(v: string, lang: Lang): string {
  return v
    .split("|")
    .map((g) => (lang === "ru" ? GROUP[g] ?? g : g.replace(/_/g, " ")))
    .join(" · ");
}

export function drugTypeLabel(v: string, lang: Lang): string {
  return lang === "ru" ? DRUG_TYPE[v] ?? v : v;
}
