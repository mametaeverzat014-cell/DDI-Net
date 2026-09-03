import { frozen } from "../data/frozen";
import { pct } from "../lib/format";

// Limitations are prominent, not hidden — a dedicated view. Every item is a real
// constraint of the frozen study, phrased as the manuscript phrases it.
const ITEMS: { title: string; body: string }[] = [
  { title: "Sampled negatives are not confirmed non-interactions", body: "The source has only documented positives; ~86.8% of the pair space is unlabelled, not negative. Some sampled degree-matched pairs are almost certainly undocumented true interactions, which depresses measured performance by an unknown amount." },
  { title: "One frozen drug partition", body: "Results come from a single drug-holdout split. No cross-partition replication was performed, so the numbers do not estimate variability across alternative drug universes." },
  { title: "Five seeds quantify training noise only", body: "Seeds vary initialisation, batch order and negative draws on one fixed partition — not the drug universe. With n=5 the t-test's normality assumption cannot be checked." },
  { title: "Non-monotonic ablation ladder", body: "M2 and the SUM control both exceed the preregistered primary M4 on the test set. M4 was fixed on validation before test evaluation; it is the preregistered model, not the best test performer." },
  { title: "CONTROL E is not identifiable", body: "The planned probe predicts training-DDI degree from the embedding. Held-out R² is undefined because every held-out drug has degree zero (target variance is zero). Only the training-side R² is interpretable, and only descriptively." },
  { title: "Scaffold-disjoint not evaluated", body: "Drug-holdout does not stop a test drug sharing a Bemis–Murcko scaffold with a training drug. Scaffold-disjoint evaluation was not performed in final V2, so falsification criterion F5 is only partly resolved." },
  { title: "No external or prospective validation", body: "All results are from one frozen retrospective dataset. No independent interaction resource and no post-snapshot prospective test were used." },
  { title: "No clinical validation", body: "The system has never been evaluated against clinical outcomes. Nothing here supports a clinical claim, and no output is a medical recommendation." },
  { title: "No patient-level context", body: "Age, sex, dose, renal or hepatic function and genotype are not inputs. The model has no representation of a patient and cannot make age- or dose-specific predictions." },
  { title: "Interpretability is not causality", body: "Perturbation analyses measure model reliance — how far the prediction moves when an input is withheld. They do not establish that a protein mediates an interaction." },
];

export function Limitations() {
  return (
    <section className="section" style={{ paddingTop: "16vh" }}>
      <div className="wrap">
        <span className="eyebrow">Limitations &amp; threats to validity</span>
        <h1 style={{ marginTop: 18, maxInlineSize: "16ch" }}>What this does not show.</h1>
        <p style={{ marginTop: 18, maxWidth: 640 }}>
          A research result is only as trustworthy as the limitations stated alongside it.
          These are the real constraints of the frozen study — {pct(100 - (frozen.coverage.protein_any_pct as number))} of
          drugs lack protein annotation, one partition, five seeds, no clinical validation.
        </p>

        <div style={{ marginTop: 44, display: "flex", flexDirection: "column", gap: 2 }}>
          {ITEMS.map((it, i) => (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: 20, padding: "22px 0", borderTop: "1px solid var(--border-soft)" }}>
              <span className="mono" style={{ fontSize: 12, color: "var(--text-3)" }}>{String(i + 1).padStart(2, "0")}</span>
              <div>
                <div style={{ fontSize: 16, fontWeight: 600, color: "var(--text)" }}>{it.title}</div>
                <p style={{ marginTop: 8, maxWidth: 720 }}>{it.body}</p>
              </div>
            </div>
          ))}
        </div>

        <div style={{ marginTop: 40, border: "1px solid var(--border-strong)", borderRadius: "var(--radius)", padding: 22, background: "var(--surface)" }}>
          <p style={{ fontSize: 14, color: "var(--text)" }}>
            This system is a computational research prototype and is not validated for clinical
            decision-making. It is not a medical device and not a clinical decision support system.
          </p>
        </div>
      </div>
    </section>
  );
}
