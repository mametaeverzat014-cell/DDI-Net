// Language-resolved content of a report, derived only from the API payload(s)
// and the export context. Every count and number here is read off the response;
// nothing is estimated or filled in. Kept free of React so tests can check the
// text itself.
import type { EvidenceStatus, MechanismFinding, MultiReport, PairReport, SourceCheck, StatementKind } from "../data/v3";
import { fill, pick, type Bi, type Lang } from "../i18n";
import { PATTERN_LABEL, SOURCE_NAME, SOURCE_STATUS, STATUS_TIER } from "../components/v3/evidenceStyle";
import { buildRefIndex } from "../components/v3/refs";
import { frozen } from "../data/frozen";
import { drugName, fixed, isoLocal } from "./format";
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
  nDb: number;
  nLabel: number;
  nNoEffect: number;
  nConflicts: number;
  nDbNotVerified: number;
  hypotheses: MechanismFinding[];
  nPathways: number;
}

export function pairFacts(r: PairReport): PairFacts {
  const db = r.evidence.filter((e) => e.category === "database_interaction_record");
  return {
    nDb: db.length,
    nLabel: r.evidence.filter((e) => e.category.startsWith("label_") && e.category !== "label_mention_no_effect_reported").length,
    nNoEffect: r.evidence.filter((e) => e.category === "label_mention_no_effect_reported").length,
    nConflicts: r.conflicts.length,
    nDbNotVerified: db.filter((e) => e.direction === "not_verified").length,
    hypotheses: hypothesesOf(r),
    nPathways: r.mechanism.n_shared_pathways_total,
  };
}

/** Executive summary of a pair report: four paragraphs and a list of gaps. */
export function pairSummary(r: PairReport, lang: Lang): { lines: { kind: StatementKind | "drugs"; text: string }[]; gaps: string[] } {
  const f = pairFacts(r);
  const name = (d: PairReport["drug_a"]) => drugName(d, lang);
  const lines: { kind: StatementKind | "drugs"; text: string }[] = [];
  lines.push({ kind: "drugs", text: t("sumDrugs", lang, { a: name(r.drug_a), ia: r.drug_a.id, b: name(r.drug_b), ib: r.drug_b.id }) });

  if (r.evidence.length === 0) {
    lines.push({ kind: "missing", text: t("sumNoEvidence", lang) });
  } else {
    lines.push({ kind: "documented", text: `${t("sumStatus", lang, { s: statusLabel(r.evidence_status, lang) })} ${t("sumEvidenceCounts", lang, { db: f.nDb, lab: f.nLabel, noeff: f.nNoEffect, conf: f.nConflicts })}` });
  }

  if (f.hypotheses.length > 0) {
    const list = f.hypotheses.map((h) => `${h.protein.gene} — ${patternLabel(h.pattern, lang)}`).join("; ");
    lines.push({ kind: "hypothesis", text: `${t("sumHyp", lang, { n: f.hypotheses.length, list })} ${t("sumPathways", lang, { n: f.nPathways })}` });
  } else {
    lines.push({ kind: "hypothesis", text: `${t("sumNoHyp", lang)} ${t("sumPathways", lang, { n: f.nPathways })}` });
  }

  const m = r.model;
  if (!m.available) lines.push({ kind: "model", text: t("sumModelUnavailable", lang, { r: m.unavailable_reason ?? t("notRecorded", lang) }) });
  else if (m.abstain) lines.push({ kind: "model", text: t("sumModelAbstain", lang) });
  else lines.push({ kind: "model", text: t("sumModel", lang, { cal: fixed(m.calibrated_model_score, 3), raw: fixed(m.raw_model_score, 6), reg: m.regime }) });

  const gaps: string[] = [];
  for (const c of problemSources(r.sources_checked)) gaps.push(t("gapSource", lang, { s: sourceLabel(c.source, lang), st: sourceStatus(c.status, lang) }));
  if (f.nDbNotVerified > 0) gaps.push(t("gapDirection", lang, { n: f.nDbNotVerified, m: f.nDb }));
  if (m.available) gaps.push(t("gapNoCi", lang));
  gaps.push(t("gapSeverity", lang));
  gaps.push(t("gapIndividual", lang));
  return { lines, gaps };
}

/** Labels [n], H#, M, R for every reference id a statement can carry. */
export function refLabels(r: PairReport, refs: string[]): string[] {
  const idx = buildRefIndex(r);
  return Array.from(new Set(refs.map((id) => idx.label(id)?.label).filter((x): x is string => !!x)));
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
      evidence: r.evidence.map((e) => ({
        ref: idx.label(e.id)?.label, id: e.id, category: e.category, source: e.source_name,
        record_id: e.source_record_id, direction: e.direction, retrieved_at: e.retrieved_at, url: e.source_url,
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
      a: q.drug_a, b: q.drug_b, status: q.evidence_status, db: q.n_database_records, labels: q.n_label_records,
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
