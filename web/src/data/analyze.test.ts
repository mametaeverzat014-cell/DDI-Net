// The Analyze client's contract: a score is shown only when one actually came
// back. Every other state must be distinguishable, because a placeholder number
// attributed to the frozen research model would be a fabricated result.
import { describe, it, expect, vi, afterEach } from "vitest";
import { analyzePair, apiConfigured, API_BASE } from "./analyze";

const ok = {
  drug_a: { id: "DB00331", n_protein_annotations: 113, n_distinct_proteins: 111, n_pathways: 365, biology_available: true, pathways_available: true },
  drug_b: { id: "DB00682", n_protein_annotations: 119, n_distinct_proteins: 112, n_pathways: 391, biology_available: true, pathways_available: true },
  model: "BIO-GINE M4", checkpoint: "bd45f84e3c1b2c33",
  raw_model_score: 0.1650189137760003, calibrated_model_score: 0.4439423027276109,
  experimental_context: { in_frozen_universe: true, biology_available_a: true, biology_available_b: true, evaluation: "" },
  dataset_record: { documented_in_frozen_dataset: false, note_en: "", note_ru: "" },
  provenance: { frozen_tag: "v2-final-github-safe-2026-09-03", frozen_commit: "92c481eeaba8", checkpoint_sha256: "b828a471", calibration_source: "", temperature: 7.200316619603008, parity_tolerance_prob: 1e-5 },
  status: "research_prediction" as const, disclaimer_ru: "", disclaimer_en: "",
};

afterEach(() => vi.unstubAllGlobals());

describe("analyze client", () => {
  it("reports unconfigured when no API base is set (the default build)", async () => {
    expect(API_BASE).toBe("");
    expect(apiConfigured()).toBe(false);
    expect(await analyzePair("DB00331", "DB00682")).toEqual({ kind: "unconfigured" });
  });

  it("never calls the network when unconfigured", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    await analyzePair("DB00331", "DB00682");
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

// With a base URL configured, the state machine must map each response
// faithfully. These re-import the module with a stubbed env.
describe("analyze client with an API configured", () => {
  async function withBase(response: Response | Error) {
    vi.resetModules();
    vi.stubEnv("VITE_ANALYZE_API", "https://api.example/");
    vi.stubGlobal("fetch", vi.fn(() =>
      response instanceof Error ? Promise.reject(response) : Promise.resolve(response)));
    return await import("./analyze");
  }

  it("strips a trailing slash from the base URL", async () => {
    const m = await withBase(new Response(JSON.stringify(ok), { status: 200 }));
    expect(m.API_BASE).toBe("https://api.example");
  });

  it("returns the parsed score on 200", async () => {
    const m = await withBase(new Response(JSON.stringify(ok), { status: 200 }));
    const s = await m.analyzePair("DB00331", "DB00682");
    expect(s.kind).toBe("ok");
    if (s.kind === "ok") {
      expect(s.data.calibrated_model_score).toBeCloseTo(0.4439423, 6);
      expect(s.data.status).toBe("research_prediction");
      expect(s.data.provenance.temperature).toBeCloseTo(7.2003166, 6);
    }
  });

  it("maps 503 to model_unavailable rather than to a score", async () => {
    const m = await withBase(new Response("{}", { status: 503 }));
    expect((await m.analyzePair("A", "B")).kind).toBe("model_unavailable");
  });

  it("surfaces a 404 as an error carrying the server's reason", async () => {
    const m = await withBase(new Response(JSON.stringify({ detail: "not in the frozen universe" }), { status: 404 }));
    const s = await m.analyzePair("DB99999", "DB00682");
    expect(s.kind).toBe("error");
    if (s.kind === "error") expect(s.message).toMatch(/frozen universe/);
  });

  it("maps a network failure to error, never to a score", async () => {
    const m = await withBase(new TypeError("network down"));
    const s = await m.analyzePair("A", "B");
    expect(s.kind).toBe("error");
  });

  it("no state other than ok can carry a number", async () => {
    for (const r of [new Response("{}", { status: 503 }), new Response("{}", { status: 500 })]) {
      const m = await withBase(r);
      const s = await m.analyzePair("A", "B");
      expect(s).not.toHaveProperty("data");
    }
  });
});
