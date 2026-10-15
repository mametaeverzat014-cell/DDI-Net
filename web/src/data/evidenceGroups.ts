// Evidence records grouped into SOURCE DOCUMENTS and DISTINCT EXCERPTS.
//
// Why: an FDA label of the older format repeats its "Drug Interactions"
// subsection under PRECAUTIONS and again as openFDA's separate drug_interactions
// field, so one sentence arrived as two records — and six records read as six
// corroborating sources when they were two labels. The API now merges such
// repeats itself (also_in_sections), but older deployments still send them, so
// the site and the PDF group again here, with the same rule as the server
// (serving/evidence/adapters/openfda.py::same_finding):
//
//   * a document is one FDA label (SPL set ID) or the DrugBank export;
//   * within ONE label, sentences that are identical after normalisation, or one
//     contained in the other (≥ 40 characters), or near-verbatim copies (word
//     sets ≥ 90 % alike, lengths within 10 %) are one excerpt, found in several
//     sections — every section name and every raw record is kept;
//   * different sentences stay different even when they name the same drugs;
//     different labels are never merged; DrugBank records are never merged.
//
// The website and the PDF both use this module, so their counts and reference
// labels ([1], [1.2]) agree. The raw records stay untouched in the API payload
// and in the JSON export.
import type { EvidenceCategory, EvidenceRecord } from "./v3";

export interface Excerpt {
  /** "1" when the document has one excerpt, else "1.2". */
  key: string;
  label: string;
  anchor: string;
  text: string;
  textRu: string | null;
  /** Every section the sentence was found in, most prominent first. */
  sections: string[];
  category: EvidenceCategory;
  /** All raw records merged into this excerpt; the first is the primary one. */
  records: EvidenceRecord[];
}

export interface SourceDoc {
  n: number;
  kind: "label" | "database";
  /** SPL set ID for a label; "drugbank_tdc" for the database. */
  id: string;
  /** Label owner (the drug whose label it is) and the drug it names. */
  ownerId: string | null;
  mentionedId: string | null;
  excerpts: Excerpt[];
  records: EvidenceRecord[];
}

export interface EvidenceCounts {
  /** Distinct FDA label documents. */
  labelDocuments: number;
  /** Distinct label excerpts that report an effect or a warning (no-effect wording excluded). */
  labelExcerpts: number;
  /** Label excerpts whose wording reports no relevant effect. */
  noEffectExcerpts: number;
  /** Raw label records as the API sent them. */
  labelRecords: number;
  /** Raw records folded into another excerpt (repeats across sections of one label). */
  mergedRepeats: number;
  databaseRecords: number;
}

export interface EvidenceGroups {
  docs: SourceDoc[];
  counts: EvidenceCounts;
  /** Excerpt for a raw record id. */
  excerptOf: (recordId: string) => Excerpt | null;
  /** Reference labels for a list of record ids: one per excerpt, collapsed to
   *  "[n]" when every excerpt of document n is cited. */
  labelsFor: (recordIds: string[]) => { label: string; anchor: string }[];
}

const PROMINENCE: EvidenceCategory[] = [
  "label_contraindication", "label_boxed_warning", "label_warning_or_interaction",
  "label_mention_no_effect_reported", "database_interaction_record",
];

// Exactly the server's normalisation: lower case, anything but [0-9a-z] separates.
const norm = (s: string) => s.toLowerCase().replace(/[^0-9a-z]+/g, " ").trim();

/** Same rule as serving/evidence/adapters/openfda.py::same_finding. */
export function sameFinding(a: string, b: string): boolean {
  const na = norm(a.replace(/…$/, "")), nb = norm(b.replace(/…$/, ""));
  if (!na || !nb) return false;
  if (na === nb) return true;
  const [short, long] = na.length <= nb.length ? [na, nb] : [nb, na];
  if (short.length >= 40 && long.includes(short)) return true;
  const ta = new Set(na.split(" ")), tb = new Set(nb.split(" "));
  let inter = 0;
  ta.forEach((w) => { if (tb.has(w)) inter++; });
  const jaccard = inter / (ta.size + tb.size - inter);
  return jaccard >= 0.9 && short.length / long.length >= 0.9;
}

const isLabel = (e: EvidenceRecord) => e.category !== "database_interaction_record";
const docId = (e: EvidenceRecord) => (isLabel(e) ? e.source_record_id ?? e.original_identifiers.spl_set_id ?? e.id : "drugbank_tdc");

export function groupEvidence(evidence: EvidenceRecord[]): EvidenceGroups {
  const byDoc = new Map<string, EvidenceRecord[]>();
  // Labels first (they carry the source's own words), then the database.
  for (const e of [...evidence.filter(isLabel), ...evidence.filter((x) => !isLabel(x))]) {
    const id = docId(e);
    byDoc.set(id, [...(byDoc.get(id) ?? []), e]);
  }
  const docs: SourceDoc[] = [];
  const excerptByRecord = new Map<string, Excerpt>();
  let n = 0;
  for (const [id, records] of byDoc) {
    n += 1;
    const label = isLabel(records[0]);
    const groups: EvidenceRecord[][] = [];
    for (const e of records) {
      const twin = label ? groups.find((g) => sameFinding(g[0].statement, e.statement)) : undefined;
      if (twin) twin.push(e);
      else groups.push([e]);
    }
    const excerpts: Excerpt[] = groups.map((g, i) => {
      const key = groups.length === 1 ? `${n}` : `${n}.${i + 1}`;
      const sections: string[] = [];
      for (const e of g) for (const s of [e.section, ...(e.also_in_sections ?? [])]) if (s && !sections.includes(s)) sections.push(s);
      const category = g.map((e) => e.category).sort((x, y) => PROMINENCE.indexOf(x) - PROMINENCE.indexOf(y))[0];
      const ex: Excerpt = { key, label: `[${key}]`, anchor: `ev-${key.replace(".", "-")}`, text: g[0].statement, textRu: g[0].statement_ru, sections, category, records: g };
      g.forEach((e) => excerptByRecord.set(e.id, ex));
      return ex;
    });
    docs.push({ n, kind: label ? "label" : "database", id, ownerId: records[0].drug1_id, mentionedId: records[0].drug2_id, excerpts, records });
  }
  const labelDocs = docs.filter((d) => d.kind === "label");
  const labelExcerpts = labelDocs.flatMap((d) => d.excerpts);
  const counts: EvidenceCounts = {
    labelDocuments: labelDocs.length,
    labelExcerpts: labelExcerpts.filter((x) => x.category !== "label_mention_no_effect_reported").length,
    noEffectExcerpts: labelExcerpts.filter((x) => x.category === "label_mention_no_effect_reported").length,
    labelRecords: labelDocs.reduce((s, d) => s + d.records.length, 0),
    mergedRepeats: labelDocs.reduce((s, d) => s + d.records.length - d.excerpts.length, 0),
    databaseRecords: docs.filter((d) => d.kind === "database").reduce((s, d) => s + d.records.length, 0),
  };
  const docOf = new Map(docs.flatMap((d) => d.excerpts.map((x) => [x, d] as const)));
  return {
    docs,
    counts,
    excerptOf: (id) => excerptByRecord.get(id) ?? null,
    labelsFor(ids) {
      const cited = Array.from(new Set(ids.map((id) => excerptByRecord.get(id)).filter((x): x is Excerpt => !!x)));
      const out: { label: string; anchor: string }[] = [];
      const done = new Set<number>();
      for (const ex of cited) {
        const d = docOf.get(ex)!;
        if (d.excerpts.length > 1 && d.excerpts.every((x) => cited.includes(x))) {
          if (!done.has(d.n)) { out.push({ label: `[${d.n}]`, anchor: `ev-${d.n}` }); done.add(d.n); }
        } else out.push({ label: ex.label, anchor: ex.anchor });
      }
      return out;
    },
  };
}

/** The counts line shown on the site and in the PDF, worded identically. The
 *  genitive-with-colon form reads correctly for any number in Russian. */
export function evidenceCountsText(c: EvidenceCounts, lang: "ru" | "en"): string {
  const parts: string[] = [];
  if (lang === "ru") {
    parts.push(`инструкций FDA: ${c.labelDocuments}`, `различных фрагментов: ${c.labelExcerpts}`);
    if (c.noEffectExcerpts) parts.push(`упоминаний без отмеченного эффекта: ${c.noEffectExcerpts}`);
    parts.push(`записей DrugBank: ${c.databaseRecords}`);
  } else {
    parts.push(`FDA label documents: ${c.labelDocuments}`, `distinct excerpts: ${c.labelExcerpts}`);
    if (c.noEffectExcerpts) parts.push(`label mentions with no effect reported: ${c.noEffectExcerpts}`);
    parts.push(`DrugBank records: ${c.databaseRecords}`);
  }
  return parts.join(" · ");
}
