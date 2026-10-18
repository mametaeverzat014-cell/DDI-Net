// Grouping of evidence into source documents: labels, the DrugBank export and the
// CRESCENDDI reference set are separate documents and are counted separately.
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { evidenceCountsText, groupEvidence } from "./evidenceGroups";
import type { PairReport } from "./v3";

const fx = (n: string) => JSON.parse(readFileSync(join(__dirname, "..", "pdf", "__fixtures__", n), "utf8")).report.data as PairReport;

describe("evidence groups with a reference set", () => {
  it("puts CRESCENDDI records in their own document after DrugBank, never in the label counts", () => {
    const r = fx("pair_synthetic_reference_simvastatin_clarithromycin.json");
    const g = groupEvidence(r.evidence);
    expect(g.docs.map((d) => d.kind)).toEqual(["database", "reference"]);
    const ref = g.docs.find((d) => d.kind === "reference")!;
    expect(ref.id).toBe("crescenddi");
    expect(ref.records.every((e) => e.category === "reference_set_outcome")).toBe(true);
    expect(g.counts.labelDocuments).toBe(0);
    expect(g.counts.referenceRecords).toBe(ref.records.length);
    expect(evidenceCountsText(g.counts, "en")).toContain(`CRESCENDDI records: ${ref.records.length}`);
    expect(evidenceCountsText(g.counts, "ru")).toContain(`записей CRESCENDDI: ${ref.records.length}`);
  });

  it("an older response without reference records keeps the old counts line", () => {
    const r = fx("pair_outcomes_warfarin_fluconazole.json");
    expect(evidenceCountsText(groupEvidence(r.evidence).counts, "en")).not.toContain("CRESCENDDI");
  });
});
