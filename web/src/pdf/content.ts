// Language-resolved content of a report, derived only from the API payload(s)
// and the export context. Every count and number here is read off the response;
// nothing is estimated or filled in. Kept free of React so tests can check the
// text itself.
import type { EvidenceStatus, MechanismFinding, MultiReport, PairReport, SourceCheck, StatementKind } from "../data/v3";
import { fill, pick, type Bi, type Lang } from "../i18n";
import { PATTERN_LABEL, SOURCE_NAME, SOURCE_STATUS, STATUS_TIER } from "../components/v3/evidenceStyle";
import { buildRefIndex } from "../components/v3/refs";
import { evidenceCountsText, groupEvidence, type EvidenceGroups, type Excerpt } from "../data/evidenceGroups";
import { frozen } from "../data/frozen";
import { fmtCalibrated } from "../data/scoreFormat";
import { drugName, isoLocal } from "./format";
import { S, STATUS_CODE, type StringKey } from "./strings";
import { C, EV } from "./theme";
import type { PreparedExport } from "./types";

export const t = (k: StringKey, lang: Lang, vars?: Record<string, string | number>): string =>
  vars ? fill(S[k][lang], vars) : S[k][lang];

export const bi = (b: Bi | null | undefined, lang: Lang): string => (b ? pick(b, lang) : "");

export const FROZEN = { tag: frozen.meta.frozen_tag, commit: frozen.meta.frozen_commit };

export const STATUS_COLOR: Record<EvidenceStatus, string> = {
  contraindication_in_label: EV.label,
  warning_in_label: EV.label,
  documented_no_severity: EV.documented,
  conflicting_evidence: EV.missing,
  model_signal_only: EV.model,
  no_documented_evidence_found: EV.none,
};

export const KIND_COLOR: Record<StatementKind, string> = {
  documented: EV.documented,
  annotation: EV.annotation,
  hypothesis: EV.hypothesis,
  model: EV.model,
  missing: EV.missing,
  caveat: C.muted,
};

export const statusLabel = (s: EvidenceStatus, lang: Lang) => pick(STATUS_TIER[s].label, lang);
export const statusHint = (s: EvidenceStatus, lang: Lang) => pick(STATUS_TIER[s].hint, lang);
export const sourceLabel = (s: string, lang: Lang) => (SOURCE_NAME[s] ? pick(SOURCE_NAME[s], lang) : s);
export const sourceStatus = (s: string, lang: Lang) => (SOURCE_STATUS[s] ? pick(SOURCE_STATUS[s], lang) : s);
export const patternLabel = (p: string, lang: Lang) => (PATTERN_LABEL[p] ? pick(PATTERN_LABEL[p], lang) : p);

/** Findings that are real hypotheses (a shared protein without a role pattern is not). */
export const hypothesesOf = (r: PairReport): MechanismFinding[] => r.mechanism.findings.filter((f) => f.pattern !== "shared_annotation");

export const problemSources = (checks: SourceCheck[]) => checks.filter((c) => c.status === "unavailable" || c.status === "disabled");

export interface PairFacts {
  /** Evidence grouped into source documents and distinct excerpts (shared with the site). */
  groups: EvidenceGroups;
  nDb: number;
  nLabelDocs: number;
  /** Distinct label excerpts reporting an effect or warning. */
  nLabel: number;
  nNoEffect: number;
  nConflicts: number;
  nDbNotVerified: number;
  hypotheses: MechanismFinding[];
  nPathways: number;
}

export function pairFacts(r: PairReport): PairFacts {
  const groups = groupEvidence(r.evidence);
  const db = r.evidence.filter((e) => e.category === "database_interaction_record");
  return {
    groups,
    nDb: db.length,
    nLabelDocs: groups.counts.labelDocuments,
    nLabel: groups.counts.labelExcerpts,
    nNoEffect: groups.counts.noEffectExcerpts,
    nConflicts: r.conflicts.length,
    nDbNotVerified: db.filter((e) => e.direction === "not_verified").length,
    hypotheses: hypothesesOf(r),
    nPathways: r.mechanism.n_shared_pathways_total,
  };
}

/** The counts line, worded exactly as on the site. */
export const countsLine = (r: PairReport, lang: Lang) => evidenceCountsText(groupEvidence(r.evidence).counts, lang);

const PROMINENCE: Record<string, number> = {
  label_contraindication: 0, label_boxed_warning: 1, label_warning_or_interaction: 2, label_mention_no_effect_reported: 3, database_interaction_record: 4,
};

/** A quotation shortened for the summary at a word boundary; the full text is in section 3. */
export function shortQuote(text: string, max = 260): string {
  const s = text.replace(/\s+/g, " ").trim();
  if (s.length <= max) return s;
  const cut = s.lastIndexOf(" ", max - 1);
  return `${s.slice(0, cut > max / 2 ? cut : max - 1).replace(/[\s,;:–—-]+$/, "")}…`;
}

export interface BriefItem { text?: string; quote?: string; lead?: string; refs?: string; lang?: "en" }
export interface BriefPart { id: "documents" | "quotes" | "hypotheses" | "model" | "uncertain"; kind: StatementKind; title: string; items: BriefItem[] }

/** Executive summary of a pair report, built deterministically from the
 *  payload: what the sources document, what their words directly say (quoted,
 *  never paraphrased), what is only a hypothesis, what the model adds, and what
 *  remains uncertain. Nothing here grades severity or gives advice. */
export function pairBrief(r: PairReport, lang: Lang): { headline: string; parts: BriefPart[] } {
  const f = pairFacts(r);
  const g = f.groups;
  const name = (id: string | null) => (id === r.drug_a.id ? drugName(r.drug_a, lang) : id === r.drug_b.id ? drugName(r.drug_b, lang) : id ?? "—");
  const m = r.model;
  const modelUsable = m.available && !m.abstain;

  // headline ------------------------------------------------------------
  const head: string[] = [r.evidence.length ? t("briefCounts", lang, { c: evidenceCountsText(g.counts, lang) }) : t("briefNoRecords", lang)];
  head.push(t("briefHypCount", lang, { n: f.hypotheses.length }));
  head.push(!m.available ? t("briefModelNone", lang) : m.abstain ? t("briefModelAbstain", lang) : t("briefModelScore", lang, { cal: fmtCalibrated(m.calibrated_model_score) }));

  // 1. documents ----------------------------------------------------------
  const docs: BriefItem[] = [];
  for (const d of g.docs) {
    if (d.kind === "label") {
      const effect = d.excerpts.filter((x) => x.category !== "label_mention_no_effect_reported");
      const sections = Array.from(new Set(d.excerpts.flatMap((x) => x.sections)));
      docs.push({
        refs: `[${d.n}]`,
        text: effect.length
          ? t("briefLabelDoc", lang, { owner: name(d.ownerId), partner: name(d.mentionedId), k: effect.length, s: sections.join(", ") || "—" })
          : t("briefLabelDocNoEffect", lang, { owner: name(d.ownerId), partner: name(d.mentionedId), k: d.excerpts.length }),
      });
    } else {
      docs.push({ refs: `[${d.n}]`, text: t("briefDbDoc", lang, { d: d.records.length }) });
    }
  }
  if (!g.docs.length) docs.push({ text: t("sumNoEvidence", lang) });
  if (f.nConflicts) docs.push({ text: t("briefConflicts", lang, { n: f.nConflicts }) });
  if (g.counts.labelDocuments > 0 && (g.docs.some((d) => d.kind === "label" && d.excerpts.length > 1) || g.counts.mergedRepeats > 0)) {
    docs.push({ text: t("briefOneSource", lang) });
  }

  // 2. quotes -------------------------------------------------------------
  const quotes: BriefItem[] = [];
  for (const d of g.docs) {
    const ranked: Excerpt[] = [...d.excerpts].sort((x, y) => PROMINENCE[x.category] - PROMINENCE[y.category]);
    const shown = d.kind === "label" ? ranked.slice(0, 2) : ranked.slice(0, 3);
    for (const x of shown) {
      const e = x.records[0];
      if (d.kind === "label") {
        const what = x.category === "label_mention_no_effect_reported" ? t("briefNoEffectTag", lang) : x.sections.join(", ");
        quotes.push({ lead: t("briefQuoteLabel", lang, { owner: name(d.ownerId), s: what }), quote: shortQuote(x.text), refs: x.label, lang: "en" });
      } else {
        const dir = e.direction === "not_verified" ? t("briefDbNeutral", lang) : t("briefDbStandard", lang);
        const ru = lang === "ru" && x.textRu;
        quotes.push({ lead: ru ? `${dir} · ${t("briefTranslated", lang)}` : dir, quote: shortQuote(ru ? x.textRu! : x.text), refs: x.label, lang: ru ? undefined : "en" });
      }
    }
    if (d.excerpts.length > shown.length) quotes.push({ text: t("briefMoreExcerpts", lang, { n: d.excerpts.length - shown.length, d: `[${d.n}]` }) });
  }
  if (quotes.length) quotes.unshift({ text: t("briefQuoteIntro", lang) });
  else quotes.push({ text: t("briefNoQuotes", lang) });
  if (f.nDbNotVerified > 0 && g.counts.labelDocuments > 0) quotes.push({ text: t("briefDirectionLabels", lang) });
  else if (f.nDbNotVerified > 0) quotes.push({ text: t("briefDirectionDb", lang) });

  // 3. hypotheses ---------------------------------------------------------
  const hyps: BriefItem[] = [];
  const idx = buildRefIndex(r);
  const byRoute = new Map<string, MechanismFinding[]>();
  for (const h of f.hypotheses) {
    const k = `${h.actor_drug_id ?? ""}|${h.affected_drug_id ?? ""}|${h.pattern}`;
    byRoute.set(k, [...(byRoute.get(k) ?? []), h]);
  }
  for (const list of byRoute.values()) {
    const h0 = list[0];
    const genes = list.map((h) => h.protein.gene).join(", ");
    const refs = list.map((h) => idx.label(h.id)?.label).filter(Boolean).join(" ");
    hyps.push({
      refs,
      text: h0.actor_drug_id
        ? t("briefHypRoute", lang, { x: name(h0.actor_drug_id), y: name(h0.affected_drug_id), p: patternLabel(h0.pattern, lang), g: genes })
        : t("briefHypShared", lang, { p: patternLabel(h0.pattern, lang), g: genes }),
    });
  }
  if (f.hypotheses.length) {
    hyps.push({ text: t("briefHypCaveat", lang) });
    if (f.hypotheses.some((h) => h.consistent_with_records.length)) hyps.push({ text: t("briefHypConsistent", lang) });
  } else hyps.push({ text: t("sumNoHyp", lang) });
  hyps.push({ text: t("sumPathways", lang, { n: f.nPathways }) });

  // 4. model --------------------------------------------------------------
  const model: BriefItem[] = [];
  if (!m.available) model.push({ text: t("sumModelUnavailable", lang, { r: m.unavailable_reason ?? t("notRecorded", lang) }) });
  else if (m.abstain) model.push({ text: t("sumModelAbstain", lang) });
  else {
    const band = t(`band_${m.band ?? "low"}` as StringKey, lang);
    model.push({ refs: "M", text: t(r.evidence.length ? "briefModelDocumented" : "briefModelUndocumented", lang, { cal: fmtCalibrated(m.calibrated_model_score), reg: m.regime, band }) });
    const p = m.measured_performance[0];
    if (p) {
      const v = `${p.metric} ${p.mean.toFixed(3)} ± ${p.sd.toFixed(3)}`;
      model.push({ text: m.regime === "S3" ? t("briefPerfS3", lang, { v }) : t("briefPerfPooled", lang, { v }) });
    } else if (m.regime === "S1") model.push({ text: t("briefPerfS1", lang) });
    if (m.split_a === "val" || m.split_b === "val") model.push({ text: t("briefValPair", lang) });
  }
  if (modelUsable || !m.available) model.push({ text: t("briefModelLimits", lang) });

  // 5. uncertain ----------------------------------------------------------
  const unc: BriefItem[] = [];
  for (const c of problemSources(r.sources_checked)) unc.push({ text: t("gapSource", lang, { s: sourceLabel(c.source, lang), st: sourceStatus(c.status, lang) }) });
  if (f.nDbNotVerified > 0) unc.push({ text: t("gapDirection", lang, { n: f.nDbNotVerified, m: f.nDb }) });
  if (g.counts.labelDocuments > 0) unc.push({ text: t("gapLabelMatch", lang) });
  if (g.counts.labelDocuments > 0 && f.nDb > 0) unc.push({ text: t("gapNotIndependent", lang) });
  if (f.hypotheses.length) unc.push({ text: t("gapStrength", lang) });
  if (m.available) unc.push({ text: t("gapNoCi", lang) });
  unc.push({ text: t("gapSeverity", lang) });
  unc.push({ text: t("gapIndividual", lang) });

  const parts: BriefPart[] = [
    { id: "documents", kind: r.evidence.length ? "documented" : "missing", title: t("briefDocsTitle", lang), items: docs },
    { id: "quotes", kind: "documented", title: t("briefQuotesTitle", lang), items: quotes },
    { id: "hypotheses", kind: "hypothesis", title: t("briefHypTitle", lang), items: hyps },
    { id: "model", kind: "model", title: t("briefModelTitle", lang), items: model },
    { id: "uncertain", kind: "missing", title: t("briefUncertainTitle", lang), items: unc },
  ];
  return { headline: head.join(" "), parts };
}

/** Labels [n], [n.k], H#, M, R for the references a statement carries; evidence
 *  collapses to [n] when every excerpt of document n is cited. */
export function refLabels(r: PairReport, refs: string[]): string[] {
  return buildRefIndex(r).labels(refs).map((x) => x.label);
}

// ------------------------------------------------------------------- multi --

export const STATUS_ORDER: EvidenceStatus[] = [
  "contraindication_in_label", "warning_in_label", "conflicting_evidence", "documented_no_severity",
  "model_signal_only", "no_documented_evidence_found",
];

export function multiCounts(m: MultiReport) {
  const byStatus = new Map<EvidenceStatus, number>();
  for (const p of m.pairs) byStatus.set(p.evidence_status, (byStatus.get(p.evidence_status) ?? 0) + 1);
  return {
    byStatus,
    review: m.pairs.filter((p) => p.needs_review).length,
    abstain: m.pairs.filter((p) => p.training_label_seen).length,
  };
}

/** Pairs in the site's order: flagged first, then by kind of documentation. */
export function sortedPairs(m: MultiReport) {
  return [...m.pairs].sort((x, y) =>
    Number(y.needs_review) - Number(x.needs_review) ||
    STATUS_ORDER.indexOf(x.evidence_status) - STATUS_ORDER.indexOf(y.evidence_status));
}

/** All drug names of an export, as the title and the running header print them. */
export function drugNames(input: PreparedExport["input"], lang: Lang): string {
  return input.kind === "pair"
    ? `${drugName(input.report.data.drug_a, lang)} + ${drugName(input.report.data.drug_b, lang)}`
    : input.report.data.drugs.map((d) => drugName(d, lang)).join(", ");
}

/** Right side of the running header: one line (about 60 characters fit); the
 *  full names are in the report. */
export function headerRightText(input: PreparedExport["input"], lang: Lang): string {
  const names = drugNames(input, lang);
  return names.length > 58 ? `${names.slice(0, 56).trimEnd()}…` : names;
}

/** True when any input came from a synthetic test fixture (endpoint synthetic://…). */
export function isSynthetic(p: PreparedExport): boolean {
  const metas = p.input.kind === "pair" ? [p.input.report.meta, p.input.graph?.meta] : [p.input.report.meta];
  return metas.some((m) => !!m && m.endpoint.startsWith("synthetic:"));
}

// ---------------------------------------------------------------- appendix --

/** Compact, machine-readable summary printed in Appendix A. Values are copied
 *  from the payload; nothing is computed except reference labels and counts. */
export function machineSummary(p: PreparedExport): Record<string, unknown> {
  const { input, ctx } = p;
  const head = {
    schema: "ddinet.pdf-summary/1",
    report_id: p.reportId,
    generated_at: isoLocal(ctx.now, ctx.timeZone),
    generated_at_utc: ctx.now.toISOString(),
    time_zone: ctx.timeZone,
    language: ctx.lang,
    payload_sha256: p.payloadSha256,
  };
  const metaOf = (m: { endpoint: string; request: unknown; receivedAt: string } | null | undefined) =>
    m ? { endpoint: m.endpoint, request: m.request, received_at: m.receivedAt } : null;

  if (input.kind === "pair") {
    const r = input.report.data;
    const idx = buildRefIndex(r);
    return {
      ...head,
      inputs: [metaOf(input.report.meta), ...(input.graph ? [metaOf(input.graph.meta)] : [])],
      server_generated_at: r.generated_at,
      report_version: r.report_version,
      drugs: [r.drug_a, r.drug_b].map((d, i) => ({ role: i ? "B" : "A", id: d.id, inn: d.inn, name_ru: d.name_ru })),
      evidence_status: r.evidence_status,
      evidence_counts: idx.groups.counts,
      source_documents: idx.groups.docs.map((d) => ({
        ref: `[${d.n}]`, kind: d.kind, document_id: d.id, owner: d.ownerId, mentions: d.mentionedId,
        excerpts: d.excerpts.map((x) => ({ ref: x.label, category: x.category, sections: x.sections, records: x.records.map((e) => e.id) })),
      })),
      evidence: r.evidence.map((e) => ({
        ref: idx.label(e.id)?.label, id: e.id, category: e.category, source: e.source_name,
        record_id: e.source_record_id, section: e.section, also_in_sections: e.also_in_sections ?? [],
        direction: e.direction, retrieved_at: e.retrieved_at, url: e.source_url,
      })),
      conflicts: r.conflicts.length,
      hypotheses: r.mechanism.findings.map((f) => ({
        ref: idx.label(f.id)?.label, gene: f.protein.gene, uniprot: f.protein.uniprot, relation: f.relation,
        pattern: f.pattern, actor: f.actor_drug_id, affected: f.affected_drug_id,
      })),
      shared_pathways_total: r.mechanism.n_shared_pathways_total,
      model: {
        model: r.model.model, checkpoint: r.model.checkpoint, available: r.model.available,
        calibrated_score: r.model.calibrated_model_score, raw_score: r.model.raw_model_score,
        regime: r.model.regime, reliability: r.model.reliability, abstain: r.model.abstain,
      },
      sources_checked: r.sources_checked.map((c) => ({ source: c.source, status: c.status })),
    };
  }
  const m = input.report.data;
  return {
    ...head,
    inputs: [metaOf(input.report.meta)],
    server_generated_at: m.generated_at,
    report_version: m.report_version,
    drugs: m.drugs.map((d) => ({ id: d.id, inn: d.inn, name_ru: d.name_ru })),
    pairs: m.pairs.map((q) => ({
      a: q.drug_a, b: q.drug_b, status: q.evidence_status, db: q.n_database_records, label_documents: q.n_label_documents ?? null, label_excerpts: q.n_label_records,
      hypotheses: q.n_mechanism_hypotheses, score: q.calibrated_model_score, regime: q.regime,
      label_seen: q.training_label_seen, review: q.needs_review,
    })),
    sources_checked: m.sources_checked.map((c) => ({ source: c.source, status: c.status })),
  };
}

/** Companion JSON: the full API payload(s) verbatim, with provenance and the hash. */
export function companionJson(p: PreparedExport, payload: Record<string, unknown>): Record<string, unknown> {
  const { input, ctx } = p;
  return {
    schema: "ddinet.report-export/1",
    report_id: p.reportId,
    generated_at: isoLocal(ctx.now, ctx.timeZone),
    generated_at_utc: ctx.now.toISOString(),
    time_zone: ctx.timeZone,
    language: ctx.lang,
    site: { origin: ctx.siteOrigin, build_commit: ctx.siteCommit },
    exported_from: input.kind === "pair" ? input.origin : "multi",
    frozen_research_tag: { tag: FROZEN.tag, commit: FROZEN.commit },
    inputs: input.kind === "pair"
      ? { report: input.report.meta ?? null, graph: input.graph?.meta ?? null }
      : { multi: input.report.meta ?? null },
    payload_sha256: p.payloadSha256,
    payload_sha256_of: "SHA-256 of JSON.stringify(payload) with object keys sorted at every level (ECMAScript number formatting, no whitespace)",
    payload,
  };
}

export const statusDash = (s: EvidenceStatus) => (s === "no_documented_evidence_found" ? "1 2.4" : s === "model_signal_only" ? "4 2.5" : undefined);

/** Legend rows for the multi-drug figures. */
export function statusLegendItems(lang: Lang) {
  return STATUS_ORDER.map((s) => ({ code: STATUS_CODE[s], color: STATUS_COLOR[s], label: statusLabel(s, lang), dash: statusDash(s) }));
}
