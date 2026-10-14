// Short, stable labels for the references a statement carries, so a reader can
// follow any sentence back to the record it rests on: evidence records are
// numbered [1], [2] …; mechanism hypotheses H1, H2 …; the model is M; a Reactome
// pathway is R. Annotation IDs are reached through their hypothesis.
import type { PairReport } from "../../data/v3";

export interface RefLabel { label: string; anchor: string | null }

export interface RefIndex {
  label: (id: string) => RefLabel | null;
  evidenceNumber: Map<string, number>;
  findingNumber: Map<string, number>;
}

export function buildRefIndex(report: PairReport): RefIndex {
  const evidenceNumber = new Map(report.evidence.map((e, i) => [e.id, i + 1]));
  const findingNumber = new Map(report.mechanism.findings.map((f, i) => [f.id, i + 1]));
  return {
    evidenceNumber,
    findingNumber,
    label(id: string): RefLabel | null {
      const n = evidenceNumber.get(id);
      if (n !== undefined) return { label: `[${n}]`, anchor: `ev-${n}` };
      const h = findingNumber.get(id);
      if (h !== undefined) return { label: `H${h}`, anchor: `hyp-${h}` };
      if (id === "model") return { label: "M", anchor: "model-block" };
      if (id.startsWith("pathway:")) return { label: "R", anchor: "pathways-block" };
      return null; // annotation IDs: reachable through their hypothesis
    },
  };
}

export function scrollToAnchor(anchor: string): void {
  const el = document.getElementById(anchor);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.animate?.([{ outline: "2px solid var(--cyan)" }, { outline: "2px solid transparent" }], { duration: 1400 });
}
