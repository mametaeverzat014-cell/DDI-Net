// Client for the frozen-inference API.
//
// The page must work in three states, and must never blur them: the backend is
// reachable and returns a score; the backend is reachable but has no model
// loaded; the backend is not configured or not reachable at all. Only the first
// shows a number. The other two say so plainly, because a placeholder number
// attributed to a frozen research model would be a fabricated result.

/** Base URL of the inference API. Empty string = not configured on this deploy. */
export const API_BASE: string = (import.meta.env.VITE_ANALYZE_API ?? "").replace(/\/$/, "");

export interface AnalyzeDrug {
  id: string;
  /** (protein, relation, evidence) triples the DeepSets branch encodes. */
  n_protein_annotations: number;
  /** Distinct proteins — the count the Drug Explorer shows. */
  n_distinct_proteins: number;
  n_pathways: number;
  biology_available: boolean;
  pathways_available: boolean;
}

export interface AnalyzeResponse {
  drug_a: AnalyzeDrug;
  drug_b: AnalyzeDrug;
  model: string;
  checkpoint: string;
  raw_model_score: number;
  calibrated_model_score: number;
  experimental_context: {
    in_frozen_universe: boolean;
    biology_available_a: boolean;
    biology_available_b: boolean;
    evaluation: string;
  };
  dataset_record: {
    documented_in_frozen_dataset: boolean;
    note_en: string;
    note_ru: string;
  };
  provenance: {
    frozen_tag: string;
    frozen_commit: string;
    checkpoint_sha256: string;
    calibration_source: string;
    temperature: number;
    parity_tolerance_prob: number;
  };
  status: "research_prediction";
  disclaimer_ru: string;
  disclaimer_en: string;
}

export type AnalyzeState =
  | { kind: "unconfigured" }
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; data: AnalyzeResponse }
  | { kind: "model_unavailable" }
  | { kind: "error"; message: string };

export function apiConfigured(): boolean {
  return API_BASE.length > 0;
}

export async function analyzePair(
  drugA: string,
  drugB: string,
  signal?: AbortSignal,
): Promise<AnalyzeState> {
  if (!apiConfigured()) return { kind: "unconfigured" };
  try {
    const r = await fetch(`${API_BASE}/api/analyze`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ drug_a: drugA, drug_b: drugB }),
      signal,
    });
    if (r.status === 503) return { kind: "model_unavailable" };
    if (!r.ok) {
      const detail = await r.json().catch(() => null);
      return { kind: "error", message: detail?.detail ?? `HTTP ${r.status}` };
    }
    return { kind: "ok", data: (await r.json()) as AnalyzeResponse };
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    return { kind: "error", message: String(e) };
  }
}
