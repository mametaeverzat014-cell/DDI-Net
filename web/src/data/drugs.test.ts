// Integrity tests for the exported drug dataset. These guard the rules the brief
// pins: real canonical IDs, no fabricated names, capped biology previews with the
// true totals alongside, and provenance on every relation.
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { matchesQuery, drugLabel, type Drug } from "./drugs";

// vitest runs from the package root (web/), so this resolves the generated file.
const path = resolve(process.cwd(), "public/data/drugs.json");
const data = JSON.parse(readFileSync(path, "utf8")) as {
  meta: {
    n_drugs: number;
    preview_caps: { proteins: number; pathways: number };
    names: { n_with_inn: number; coverage_pct: number; ru_is_transliteration: boolean; en_source: string; ru_source: string; ru_warning: string };
  };
  drugs: Array<Drug>;
};

describe("drug dataset integrity", () => {
  it("carries all 1,705 drugs", () => {
    expect(data.meta.n_drugs).toBe(1705);
    expect(data.drugs.length).toBe(1705);
  });

  it("every id is a canonical DrugBank accession", () => {
    for (const d of data.drugs) expect(d.id).toMatch(/^DB\d{5}$/);
  });

  it("carries no invented `name` field — names live in `inn`, which is sourced", () => {
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

  it("every English name is attributed to a source, and no name exists without one", () => {
    for (const d of data.drugs) {
      if (d.inn) expect(d.name_source).toBe("DrugCentral INN (matched on InChIKey)");
      else expect(d.name_source).toBeNull();
    }
  });

  it("a Russian label never exists without the INN it was transliterated from", () => {
    for (const d of data.drugs) {
      if (d.inn_ru) expect(d.inn).toBeTruthy();
    }
  });

  it("the payload flags Russian names as transliteration, not sourced data", () => {
    expect(data.meta.names.ru_is_transliteration).toBe(true);
    expect(data.meta.names.ru_warning).toMatch(/NOT sourced/);
    expect(data.meta.names.n_with_inn).toBe(data.drugs.filter((d) => d.inn).length);
  });

  it("name coverage is partial and the unmatched drugs keep the ID alone", () => {
    const unnamed = data.drugs.filter((d) => !d.inn);
    expect(unnamed.length).toBeGreaterThan(0);
    for (const d of unnamed.slice(0, 20)) {
      expect(drugLabel(d, "ru")).toBe(d.id);
      expect(drugLabel(d, "en")).toBe(d.id);
    }
  });

  it("the six analyze quick-pick IDs all exist", () => {
    const ids = new Set(data.drugs.map((d) => d.id));
    for (const q of ["DB00006", "DB00014", "DB00252", "DB00285", "DB00564", "DB01174"]) {
      expect(ids.has(q)).toBe(true);
    }
  });
});

describe("drug search", () => {
  const find = (q: string) => data.drugs.filter((d) => matchesQuery(d, q));

  it("finds a drug by its DrugBank ID", () => {
    expect(find("DB00331").map((d) => d.id)).toContain("DB00331");
  });

  it("finds a drug by its English INN", () => {
    const hits = find("metformin");
    expect(hits.length).toBeGreaterThan(0);
    expect(hits.some((d) => d.inn === "metformin")).toBe(true);
  });

  it("finds the same drug by its Russian label", () => {
    const byEn = find("metformin").map((d) => d.id);
    const byRu = find("метформин").map((d) => d.id);
    expect(byRu.length).toBeGreaterThan(0);
    expect(byRu).toEqual(expect.arrayContaining(byEn));
  });

  it("is case-insensitive in both scripts", () => {
    expect(find("METFORMIN").length).toBe(find("metformin").length);
    expect(find("МЕТФОРМИН").length).toBe(find("метформин").length);
  });

  it("still finds by molecular formula", () => {
    expect(find("C4H11N5").length).toBeGreaterThan(0);
  });

  it("an empty query matches nothing (the caller shows the full list instead)", () => {
    expect(matchesQuery(data.drugs[0], "   ")).toBe(false);
  });

  it("a label always keeps the canonical ID beside the name", () => {
    const named = data.drugs.find((d) => d.inn_ru)!;
    expect(drugLabel(named, "ru")).toContain(named.id);
    expect(drugLabel(named, "ru")).toContain(named.inn_ru!);
    expect(drugLabel(named, "en")).toContain(named.inn!);
  });
});
