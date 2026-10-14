// Integrity rules for the DDI-Net 3.0 evidence views.
//
// 1. No tier is ever green — not the token, not a literal.
// 2. "Nothing found" always says it is not a safety verdict, in both languages.
// 3. No copy in the v3 views tells anyone to take, stop, combine or re-dose a
//    medicine, or calls a combination safe (same vocabulary as
//    serving/evidence/explain.py::FORBIDDEN).
// 4. The report renders its five sections, numbers its sources, and keeps the
//    model score out of the status banner.
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { render, screen } from "@testing-library/react";
import { LanguageProvider } from "../../i18n";
import { STATUS_TIER, KIND_TIER, CATEGORY_LABEL } from "./evidenceStyle";
import { StatusBanner, ExplanationView, EvidenceList } from "./ReportParts";
import { buildRefIndex } from "./refs";
import type { PairReport } from "../../data/v3";

const SRC = join(__dirname, "..", "..");

function hexHue(hex: string): number | null {
  const m = /^#([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return null;
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16) / 255);
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  if (max === min) return null;
  const d = max - min;
  const h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return (h * 60 + 360) % 360;
}

describe("evidence colours", () => {
  it("defines no green evidence tier", () => {
    const css = readFileSync(join(SRC, "styles", "tokens.css"), "utf8");
    const tokens = [...css.matchAll(/--ev-[a-z]+:\s*(#[0-9a-f]{6})/gi)].map((m) => m[1]);
    expect(tokens.length).toBeGreaterThanOrEqual(5);
    for (const t of tokens) {
      const h = hexHue(t);
      if (h !== null) expect(h < 75 || h > 170, `${t} has a green hue (${h.toFixed(0)}°)`).toBe(true);
    }
  });

  it("uses no green literal anywhere in the v3 views", () => {
    const files = [
      ...readdirSync(join(SRC, "components", "v3")).map((f) => join(SRC, "components", "v3", f)),
      ...["Analyzer.tsx", "Mechanisms.tsx", "MultiDrug.tsx"].map((f) => join(SRC, "views", f)),
    ].filter((f) => /\.tsx?$/.test(f) && !f.endsWith(".test.tsx"));
    for (const f of files) {
      const text = readFileSync(f, "utf8");
      // Colour VALUES only; comments explaining the rule may say "green".
      expect(/["'`](?:dark|light|lime|sea|forest)?green["'`]|--green|#0f0\b|#00ff00|rgb\(0,\s*(?:128|255),\s*0\)/i.test(text), f).toBe(false);
    }
  });
});

describe("wording", () => {
  it("says 'nothing found' is not 'safe', in both languages", () => {
    const t = STATUS_TIER.no_documented_evidence_found;
    expect(t.hint.ru).toContain("не означает, что сочетание безопасно");
    expect(t.hint.en).toContain("does not mean the combination is safe");
  });

  it("contains no medication instructions or safety claims", () => {
    const forbidden = [
      /\bsafe to (take|combine|use)\b/i, /\bsafe together\b/i, /\bSAFE TO TAKE\b/, /\byou should\b/i,
      /\bstop taking\b/i, /\bstart taking\b/i, /\b(increase|decrease|reduce|change|adjust) (the|your) dose\b/i,
      /можно (спокойно )?принимать/i, /безопасно (принимать|сочетать|применять)/i, /прекратите/i,
      /(измените|снизьте|увеличьте|уменьшите) дозу/i, /не принимайте/i, /рекомендуем/i,
    ];
    const files = [
      ...readdirSync(join(SRC, "components", "v3")).map((f) => join(SRC, "components", "v3", f)),
      ...["Analyzer.tsx", "Mechanisms.tsx", "MultiDrug.tsx", "Limitations.tsx"].map((f) => join(SRC, "views", f)),
    ].filter((f) => /\.tsx?$/.test(f) && !f.endsWith(".test.tsx"));
    for (const f of files) {
      const text = readFileSync(f, "utf8");
      for (const p of forbidden) expect(p.test(text), `${p} in ${f}`).toBe(false);
    }
  });

  it("labels every kind and category in both languages", () => {
    for (const t of [...Object.values(STATUS_TIER), ...Object.values(KIND_TIER)]) {
      expect(t.label.ru && t.label.en && t.hint.ru && t.hint.en).toBeTruthy();
    }
    for (const c of Object.values(CATEGORY_LABEL)) expect(c.ru && c.en).toBeTruthy();
  });
});

const REPORT: PairReport = {
  report_version: "3.0",
  drug_a: { id: "DB90000", inn: "zetamab", name_ru: "зетамаб", name_ru_is_transliteration: true, groups: "", drug_type: "", query: null, matched_on: "inn" },
  drug_b: { id: "DB90001", inn: "fixtrazole", name_ru: "фикстразол", name_ru_is_transliteration: true, groups: "", drug_type: "", query: null, matched_on: "inn" },
  evidence_status: "documented_no_severity",
  evidence_status_label: { ru: "Задокументировано (тест)", en: "Documented (test)" },
  evidence: [{
    id: "drugbank-tdc:DB90000>DB90001:t47", category: "database_interaction_record", source_name: "fixture source",
    source_version: null, source_record_id: null, source_url: null, retrieval_url: null, original_identifiers: {},
    statement: "SYNTHETIC fixture statement.", statement_origin: "source_template_direction_neutral", source_template: null,
    direction: "not_verified", direction_check: null, statement_ru: "СИНТЕТИЧЕСКОЕ утверждение.", section: null,
    drug1_id: null, drug2_id: null, retrieved_at: "2026-01-01", license: null, source_severity: null, qualifiers: [],
  }],
  conflicts: [],
  mechanism: { findings: [], shared_pathways: [], n_shared_pathways_total: 0, annotations: {}, coverage: {}, note: { ru: "", en: "" } },
  model: {
    available: true, unavailable_reason: null, model: "BIO-GINE M4", checkpoint: "x", raw_model_score: 0.9, calibrated_model_score: 0.777,
    band: "high", regime: "S3", split_a: "test", split_b: "test", training_label_seen: false, reliability: "held_out_like",
    measured_performance: [], biology_available_a: true, biology_available_b: true, notes: [], abstain: false,
  },
  explanation: {
    method: "fixture",
    sections: (["known", "why", "ai", "certainty", "missing"] as const).map((id) => ({
      id, title: { ru: `Раздел ${id}`, en: `Section ${id}` },
      statements: [{ kind: id === "known" ? "documented" : "caveat", text: { ru: `текст ${id}`, en: `text ${id}` }, refs: id === "known" ? ["drugbank-tdc:DB90000>DB90001:t47"] : [] }],
    })),
  },
  sources_checked: [],
  limitations: [],
  disclaimer: { ru: "", en: "" },
  generated_at: "2026-01-01T00:00:00+00:00",
};

describe("report rendering", () => {
  it("renders the banner without the model score", () => {
    render(<LanguageProvider><StatusBanner report={REPORT} /></LanguageProvider>);
    expect(screen.getByRole("status").textContent).toContain("Задокументировано (тест)");
    expect(screen.getByRole("status").textContent).not.toContain("0.777");
  });

  it("renders five sections and links a statement to its numbered source", () => {
    render(<LanguageProvider><ExplanationView report={REPORT} refs={buildRefIndex(REPORT)} /><EvidenceList report={REPORT} research={false} /></LanguageProvider>);
    for (const id of ["known", "why", "ai", "certainty", "missing"]) expect(screen.getByText(`Раздел ${id}`)).toBeTruthy();
    expect(screen.getByRole("button", { name: "→ [1]" })).toBeTruthy();
    expect(document.getElementById("ev-1")).not.toBeNull();
  });
});
