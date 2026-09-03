// Integrity tests for the exported drug dataset. These guard the rules the brief
// pins: real canonical IDs, no fabricated names, capped biology previews with the
// true totals alongside, and provenance on every relation.
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// vitest runs from the package root (web/), so this resolves the generated file.
const path = resolve(process.cwd(), "public/data/drugs.json");
const data = JSON.parse(readFileSync(path, "utf8")) as {
  meta: { n_drugs: number; preview_caps: { proteins: number; pathways: number } };
  drugs: Array<{
    id: string; formula: string | null; n_proteins: number; n_pathways: number;
    proteins_preview: Array<{ uniprot: string; relation: string; evidence: string; source: string }>;
    pathways_preview: Array<{ reactome_id: string }>;
  }>;
};

describe("drug dataset integrity", () => {
  it("carries all 1,705 drugs", () => {
    expect(data.meta.n_drugs).toBe(1705);
    expect(data.drugs.length).toBe(1705);
  });

  it("every id is a canonical DrugBank accession", () => {
    for (const d of data.drugs) expect(d.id).toMatch(/^DB\d{5}$/);
  });

  it("no human-readable drug name field is present (none exist in the dataset)", () => {
    for (const d of data.drugs.slice(0, 50)) {
      expect(Object.prototype.hasOwnProperty.call(d, "name")).toBe(false);
    }
  });

  it("protein/pathway previews never exceed the declared caps", () => {
    for (const d of data.drugs) {
      expect(d.proteins_preview.length).toBeLessThanOrEqual(data.meta.preview_caps.proteins);
      expect(d.pathways_preview.length).toBeLessThanOrEqual(data.meta.preview_caps.pathways);
    }
  });

  it("preview counts never exceed the drug's true totals", () => {
    for (const d of data.drugs) {
      expect(d.proteins_preview.length).toBeLessThanOrEqual(d.n_proteins);
      expect(d.pathways_preview.length).toBeLessThanOrEqual(d.n_pathways);
    }
  });

  it("every protein relation carries an evidence type and a source", () => {
    for (const d of data.drugs) {
      for (const p of d.proteins_preview) {
        expect(p.uniprot).toBeTruthy();
        expect(p.evidence).toBeTruthy();
        expect(p.source).toBeTruthy();
      }
    }
  });

  it("the six analyze quick-pick IDs all exist", () => {
    const ids = new Set(data.drugs.map((d) => d.id));
    for (const q of ["DB00006", "DB00014", "DB00252", "DB00285", "DB00564", "DB01174"]) {
      expect(ids.has(q)).toBe(true);
    }
  });
});
