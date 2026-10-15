// Short, stable labels for the references a statement carries, so a reader can
// follow any sentence back to the record it rests on: source documents are
// numbered [1], [2] … and, when a document has several distinct excerpts,
// [1.1], [1.2] … (data/evidenceGroups.ts — the PDF uses the same numbering);
// mechanism hypotheses H1, H2 …; the model is M; a Reactome pathway is R.
// Annotation IDs are reached through their hypothesis.
import type { PairReport } from "../../data/v3";
import { groupEvidence, type EvidenceGroups } from "../../data/evidenceGroups";

export interface RefLabel { label: string; anchor: string | null }

export interface RefIndex {
  /** Label of one reference id (an evidence record maps to its excerpt). */
  label: (id: string) => RefLabel | null;
  /** Labels for all references of a statement, evidence collapsed per document. */
  labels: (ids: string[]) => RefLabel[];
  groups: EvidenceGroups;
  findingNumber: Map<string, number>;
}

export function buildRefIndex(report: PairReport): RefIndex {
  const groups = groupEvidence(report.evidence);
  const findingNumber = new Map(report.mechanism.findings.map((f, i) => [f.id, i + 1]));
  const other = (id: string): RefLabel | null => {
    const h = findingNumber.get(id);
    if (h !== undefined) return { label: `H${h}`, anchor: `hyp-${h}` };
    if (id === "model") return { label: "M", anchor: "model-block" };
    if (id.startsWith("pathway:")) return { label: "R", anchor: "pathways-block" };
    return null; // annotation IDs: reachable through their hypothesis
  };
  return {
    groups,
    findingNumber,
    label(id) {
      const ex = groups.excerptOf(id);
      return ex ? { label: ex.label, anchor: ex.anchor } : other(id);
    },
    labels(ids) {
      const ev = groups.labelsFor(ids);
      const rest = ids.filter((id) => !groups.excerptOf(id)).map(other).filter((x): x is RefLabel => !!x);
      const seen = new Set<string>();
      return [...ev, ...rest].filter((x) => (seen.has(x.label) ? false : (seen.add(x.label), true)));
    },
  };
}

export function scrollToAnchor(anchor: string): void {
  const el = document.getElementById(anchor);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.animate?.([{ outline: "2px solid var(--cyan)" }, { outline: "2px solid transparent" }], { duration: 1400 });
}
