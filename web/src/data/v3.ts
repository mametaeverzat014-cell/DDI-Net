// Client for the DDI-Net 3.0 evidence API (/api/v3). Types mirror
// serving/evidence/schema.py field for field.
//
// The same rule as the v2 client: a report is shown only when one actually
// came back. "Not configured", "service unavailable", "a drug could not be
// identified" and "error" are distinct states, because rendering any of them
// as an empty report would read as "nothing found" — and on this page
// "nothing found" is the reading most likely to be mistaken for "safe".
import { API_BASE, apiConfigured } from "./analyze";
import type { Bi } from "../i18n";

export type EvidenceCategory =
  | "label_contraindication"
  | "label_boxed_warning"
  | "label_warning_or_interaction"
  | "database_interaction_record"
  | "reference_set_outcome"
  | "label_mention_no_effect_reported";

export type EvidenceStatus =
  | "contraindication_in_label"
  | "warning_in_label"
  | "documented_no_severity"
  | "conflicting_evidence"
  | "model_signal_only"
  | "no_documented_evidence_found";

export interface DrugOut {
  id: string;
  inn: string | null;
  name_ru: string | null;
  name_ru_is_transliteration: boolean;
  groups: string;
  drug_type: string;
  query: string | null;
  matched_on: string | null;
}

export interface ResolveCandidate { id: string; inn: string | null; name_ru: string | null }

export interface ResolveOut {
  query: string;
  status: "resolved" | "suggestions" | "multiple_ingredients" | "not_in_universe" | "not_found" | "invalid";
  drug: DrugOut | null;
  candidates: ResolveCandidate[];
  note: string | null;
  rxnorm: Record<string, unknown> | null;
}

export interface EvidenceRecord {
  id: string;
  category: EvidenceCategory;
  source_name: string;
  source_version: string | null;
  source_record_id: string | null;
  source_url: string | null;
  retrieval_url: string | null;
  original_identifiers: Record<string, string>;
  statement: string;
  statement_origin: "verbatim_excerpt" | "source_template_filled" | "source_template_direction_neutral";
  source_template: string | null;
  direction: "symmetric" | "as_exported_verified" | "not_verified" | "not_applicable";
  direction_check: { n_informative: number; n_consistent: number; consistency: number | null } | null;
  statement_ru: string | null;
  section: string | null;
  /** Other sections of the same label with the same sentence. Absent from older APIs, which repeat the record instead. */
  also_in_sections?: string[];
  drug1_id: string | null;
  drug2_id: string | null;
  retrieved_at: string;
  license: string | null;
  source_severity: string | null;
  qualifiers: string[];
}

export interface Conflict { record_ids: string[]; affected_drug_id: string; description: Bi }

export interface ProteinOut { uniprot: string; gene: string; name: string; organism: string; family: string; plain: Bi }

export type Relation = "target" | "enzyme" | "transporter" | "carrier";

export interface AnnotationRef {
  id: string;
  drug_id: string;
  uniprot: string;
  relation: Relation;
  roles: string[];
  raw_action: string;
  source_name: string;
  source_version: string;
  known_action: string | null;
  pmids: string[];
  organism: string;
  retrieved_at: string;
}

export type Pattern =
  | "inhibitor_substrate" | "inducer_substrate" | "shared_substrate"
  | "opposing_target_action" | "same_direction_target_action" | "shared_annotation";

export interface MechanismFinding {
  id: string;
  protein: ProteinOut;
  relation: Relation;
  pattern: Pattern;
  actor_drug_id: string | null;
  affected_drug_id: string | null;
  roles_a: string[];
  roles_b: string[];
  annotation_ids: string[];
  consistent_with_records: string[];
  status: "hypothesis";
}

export interface SharedPathway {
  id: string; name: string; n_proteins_in_pathway: number; via_a: string[]; via_b: string[]; source: string;
}

export interface MechanismBlock {
  findings: MechanismFinding[];
  shared_pathways: SharedPathway[];
  n_shared_pathways_total: number;
  annotations: Record<string, AnnotationRef>;
  coverage: Record<string, Record<Relation, number>>;
  note: Bi;
}

export interface MeasuredPerformance { view: string; metric: string; mean: number; sd: number; n_seeds: number; source: string }

export interface ModalityReliance {
  baseline_raw: number;
  without_molecular_raw: number;
  without_protein_raw: number;
  without_pathway_raw: number;
  delta_molecular: number;
  delta_protein: number;
  delta_pathway: number;
  method: string;
  validation: { n_rows: number; max_abs_diff: number; source: string };
  interpretation: Bi;
}

export interface ModelBlock {
  available: boolean;
  unavailable_reason: string | null;
  model: string;
  checkpoint: string;
  raw_model_score: number | null;
  calibrated_model_score: number | null;
  band: "high" | "moderate" | "low" | null;
  regime: "S1" | "S2" | "S3";
  split_a: string;
  split_b: string;
  training_label_seen: boolean;
  reliability: "training_label_seen" | "not_evaluated_regime" | "held_out_like";
  measured_performance: MeasuredPerformance[];
  biology_available_a: boolean;
  biology_available_b: boolean;
  notes: Bi[];
  abstain: boolean;
  /** Absent from APIs older than the reliance readout. */
  modality_reliance?: ModalityReliance | null;
}

export type StatementKind = "documented" | "annotation" | "hypothesis" | "model" | "missing" | "caveat";
export interface Statement { kind: StatementKind; text: Bi; refs: string[] }
export interface Section { id: "known" | "why" | "ai" | "certainty" | "missing"; title: Bi; statements: Statement[] }

export interface SourceCheck { source: string; status: "ok" | "no_match" | "unavailable" | "disabled" | "not_applicable"; detail: string | null }

export interface PairReport {
  report_version: "3.0";
  drug_a: DrugOut;
  drug_b: DrugOut;
  evidence_status: EvidenceStatus;
  evidence_status_label: Bi;
  evidence: EvidenceRecord[];
  conflicts: Conflict[];
  mechanism: MechanismBlock;
  model: ModelBlock;
  explanation: { method: string; sections: Section[] };
  sources_checked: SourceCheck[];
  limitations: Bi[];
  disclaimer: Bi;
  generated_at: string;
  /** Clinical outcome block. Absent from API versions before the outcome engine. */
  outcomes?: OutcomeReport | null;
}

// ------------------------------------------------------- clinical outcomes ---
export type OutcomeEvidenceStatus = "documented" | "mechanistically_supported" | "hypothesized";
export type EffectLevel = "clinical_outcome" | "pharmacodynamic_effect" | "pharmacokinetic_change" | "reduced_effectiveness" | "unspecified_adverse";
export type SeriousnessClass = "documented_contraindication" | "explicit_serious_warning" | "documented_no_standard_severity" | "not_applicable";
export type InteractionStatus = "documented_interaction" | "documented_outcome_unclear" | "research_prediction_only" | "insufficient_evidence" | "source_unavailable";
export type LinkProvenance = "documented" | "verified_annotation" | "plausible_unconfirmed" | "unavailable";

export interface OutcomeSupport {
  evidence_record_id: string | null;
  source_type: "fda_label" | "drugbank_tdc" | "reference_set" | "annotation";
  source_name: string;
  source_document_id: string | null;
  source_url: string | null;
  section: string | null;
  /** Verbatim: the label sentence or DrugBank's template. */
  excerpt: string;
  matched_terms: string[];
  extraction_method: string;
  direction: "symmetric" | "as_exported_verified" | "not_verified" | "from_annotation" | "as_stated_in_excerpt" | "not_applicable";
  affected_drug_id: string | null;
  source_seriousness: string | null;
  retrieved_at: string | null;
  qualifiers: string[];
}

export interface ClinicalOutcome {
  id: string;
  drug_a: string;
  drug_b: string;
  category: string;
  effect: string;
  effect_level: EffectLevel;
  label: Bi;
  explanation: Bi;
  evidence_status: OutcomeEvidenceStatus;
  supports: OutcomeSupport[];
  n_source_documents: number;
  affected_drug_id: string | null;
  direction_note: Bi;
  seriousness: SeriousnessClass;
  seriousness_basis: Bi;
  evidence_strength: "official_label_statement" | "database_standard_sentence" | "label_and_database" | "reference_set_statement" | "reference_set_and_other" | "annotation_hypothesis";
  evidence_strength_text: Bi;
  extraction_note: Bi | null;
  limitations: Bi[];
  research_only: boolean;
}

export interface ChainNode { id: string; kind: "drug" | "protein" | "effect" | "outcome"; label: Bi; ref: string | null }
export interface ChainLink { source: string; target: string; relation: string; provenance: LinkProvenance; text: Bi; refs: string[] }
export interface MechanismChain { id: string; nodes: ChainNode[]; links: ChainLink[]; outcome_ids: string[]; research_only: boolean; summary: Bi }

export interface OutcomeReport {
  method: string;
  interaction_status: InteractionStatus;
  interaction_status_label: Bi;
  interaction_status_hint: Bi;
  outcomes: ClinicalOutcome[];
  chains: MechanismChain[];
  seriousness: SeriousnessClass;
  seriousness_text: Bi;
  coverage: Bi[];
  no_outcome_text: Bi | null;
  /** Exact wording, set whenever no specific clinical outcome is documented (also when only exposure
   *  or effect changes are). Never a statement of safety. Absent from older APIs. */
  no_specific_outcome_text?: Bi | null;
  mechanism_without_outcome_text: Bi | null;
  individual_limit: Bi;
}

export interface MultiPair {
  drug_a: string;
  drug_b: string;
  evidence_status: EvidenceStatus;
  n_database_records: number;
  /** Label excerpts (older APIs count a sentence repeated across sections twice). */
  n_label_records: number;
  /** Distinct label documents (SPL set IDs). Absent from older APIs. */
  n_label_documents?: number | null;
  /** CRESCENDDI reference-set pair–event records. Absent from older APIs. */
  n_reference_records?: number;
  n_mechanism_hypotheses: number;
  calibrated_model_score: number | null;
  regime: string;
  training_label_seen: boolean;
  needs_review: boolean;
  review_reasons: string[];
  /** Outcome-engine fields; absent from older APIs. */
  interaction_status?: InteractionStatus | null;
  outcome_categories?: string[];
  outcome_ids?: string[];
  seriousness?: SeriousnessClass | null;
}

export interface MultiReport {
  report_version: "3.0";
  drugs: DrugOut[];
  pairs: MultiPair[];
  sources_checked: SourceCheck[];
  scope_note: Bi;
  disclaimer: Bi;
  generated_at: string;
  /** Documented outcome category -> pairs it was documented for (only categories shared by 2+ pairs). */
  shared_outcome_categories?: Record<string, [string, string][]>;
  outcome_categories?: Record<string, Bi>;
}

export interface GraphNode { id: string; kind: "drug" | "protein" | "pathway"; label: string; side: "a" | "b" | "shared" | "pathway"; detail: Record<string, unknown> }
export interface GraphEdge {
  id: string; source: string; target: string;
  kind: "annotation" | "pathway_membership" | "documented_interaction" | "model_reliance";
  established: boolean;
  /** False when source/target order means nothing (unverified DrugBank drug order). Absent from older APIs. */
  directed?: boolean;
  detail: Record<string, unknown>;
}
export interface MechanismGraph { drug_a: string; drug_b: string; nodes: GraphNode[]; edges: GraphEdge[]; truncated: Record<string, number>; legend: Record<string, Bi> }

/** Where a response came from: recorded once, when it arrived, so an export can
 *  cite the exact request instead of re-running it. */
export interface FetchMeta {
  /** Full URL that answered, e.g. https://…/api/v3/report */
  endpoint: string;
  /** The JSON body that was sent, verbatim. */
  request: unknown;
  /** Browser clock, ISO 8601 UTC, when the response body was read. */
  receivedAt: string;
}

export type Remote<T> =
  | { kind: "unconfigured" }
  | { kind: "loading" }
  | { kind: "ok"; data: T; meta?: FetchMeta }
  | { kind: "unresolved"; resolutions: ResolveOut[]; message: string }
  | { kind: "unavailable"; message: string }
  | { kind: "rate_limited"; retryAfter: number }
  | { kind: "error"; message: string };

async function post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<Remote<T>> {
  if (!apiConfigured()) return { kind: "unconfigured" };
  try {
    const endpoint = `${API_BASE}${path}`;
    const r = await fetch(endpoint, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
    const out = await interpret<T>(r);
    return out.kind === "ok" ? { ...out, meta: { endpoint, request: body, receivedAt: new Date().toISOString() } } : out;
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    return { kind: "error", message: String(e) };
  }
}

/** Map an HTTP response to a state. Exported for tests. */
export async function interpret<T>(r: Response): Promise<Remote<T>> {
  if (r.ok) return { kind: "ok", data: (await r.json()) as T };
  const body = await r.json().catch(() => null);
  const detail = body?.detail;
  if (r.status === 429) {
    // The server's rate limit (serving/ratelimit.py). Seconds come from the JSON
    // body, falling back to the Retry-After header, then to a minute.
    const fromBody = Number(detail?.retry_after_seconds);
    const fromHeader = Number(r.headers.get("retry-after"));
    const retryAfter = Number.isFinite(fromBody) && fromBody > 0 ? fromBody
      : Number.isFinite(fromHeader) && fromHeader > 0 ? fromHeader : 60;
    return { kind: "rate_limited", retryAfter };
  }
  if (r.status === 503) return { kind: "unavailable", message: typeof detail === "string" ? detail : `HTTP ${r.status}` };
  if (r.status === 404) return { kind: "unavailable", message: "this API does not provide the DDI-Net 3.0 evidence layer yet" };
  if (r.status === 422 && detail && typeof detail === "object" && Array.isArray(detail.resolutions)) {
    return { kind: "unresolved", resolutions: detail.resolutions as ResolveOut[], message: String(detail.message ?? "") };
  }
  const message = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((d: { msg?: string }) => d.msg).join("; ") : `HTTP ${r.status}`;
  return { kind: "error", message };
}

export function fetchReport(drugA: string, drugB: string, signal?: AbortSignal) {
  return post<PairReport>("/api/v3/report", { drug_a: drugA, drug_b: drugB, include_labels: true }, signal);
}

export function fetchGraph(drugA: string, drugB: string, signal?: AbortSignal) {
  return post<MechanismGraph>("/api/v3/graph", { drug_a: drugA, drug_b: drugB }, signal);
}

export function fetchMulti(drugs: string[], signal?: AbortSignal) {
  return post<MultiReport>("/api/v3/multi", { drugs, include_labels: true }, signal);
}

export const MAX_MULTI = 8;
