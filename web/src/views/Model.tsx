import { Badge } from "../components/Badge";
import { frozen } from "../data/frozen";
import { count } from "../lib/format";

// Architecture blocks. Every block is Implemented in frozen V2 (the biological
// branch, marked "specified" in the original design, was completed). I/O
// signatures are the real code values verified against src/ddinet/models/bio_gine.py.
const BLOCKS = [
  { name: "GINE molecular encoder", io: "atom graph (50 feat) → 64-d structural vector", body: "Graph Isomorphism Network with edge features, 3 layers, hidden 64, sum pooling. Transfers to any structure — computable for an unseen drug.", kind: "implemented" as const },
  { name: "Deep Sets protein encoder", io: "set of (protein, relation, evidence) → 128-d vector", body: "Each element concatenates a protein embedding (128), a relation-type embedding (16) and an evidence-type embedding (16) = 160-d, mapped by φ (160→256→128), MEAN-aggregated. Mean, not sum, so annotation count is not the path of least resistance.", kind: "implemented" as const },
  { name: "Deep Sets pathway encoder", io: "set of Reactome pathways → 128-d vector", body: "Pathway-membership set, φ (128→256→128), MEAN-aggregated. Membership only — no reaction topology or direction.", kind: "implemented" as const },
  { name: "Multimodal fusion", io: "molecular ⊕ protein ⊕ pathway → 128-d drug vector", body: "Concatenate the active branches, then Linear → LayerNorm. Empty biology gets a learned MISSING token, never a zero vector.", kind: "implemented" as const },
  { name: "Symmetric pair decoder", io: "(drug A, drug B) → interaction logit", body: "Commutative terms only — sum, |difference|, elementwise product, and min/max of the modality masks (388-d) — so f(A,B) = f(B,A) exactly, not approximately.", kind: "implemented" as const },
  { name: "Calibrated probability head", io: "logit → temperature-scaled probability", body: "One temperature per seed, fitted on validation only. Monotonic, so it corrects probability calibration without changing ranking.", kind: "implemented" as const },
];

export function Model() {
  const c = frozen.config;
  return (
    <section className="section" style={{ paddingTop: "16vh" }}>
      <div className="wrap">
        <span className="eyebrow">How BIO-GINE works</span>
        <h1 style={{ marginTop: 18, maxInlineSize: "16ch" }}>A drug, encoded three ways.</h1>
        <p style={{ marginTop: 18, maxWidth: 640 }}>
          BIO-GINE builds each drug from its molecular structure and its biological
          annotations, fuses them into one vector, and scores a pair symmetrically. No edge
          of the known interaction graph enters the representation — which is what lets it be
          evaluated on drugs held out of training.
        </p>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 16, marginTop: 44 }}>
          {BLOCKS.map((b) => (
            <div key={b.name} style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", background: "var(--surface)", backdropFilter: "var(--blur)", padding: 22, transition: "transform 0.3s var(--ease)" }}
              onMouseEnter={(e) => (e.currentTarget.style.transform = "translateY(-3px)")}
              onMouseLeave={(e) => (e.currentTarget.style.transform = "none")}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: 16, fontWeight: 600, color: "var(--text)" }}>{b.name}</span>
                <Badge kind={b.kind}>{b.kind}</Badge>
              </div>
              <div className="mono" style={{ fontSize: 11, color: "var(--cyan)", marginTop: 10 }}>{b.io}</div>
              <p style={{ marginTop: 12, fontSize: 13.5 }}>{b.body}</p>
            </div>
          ))}
        </div>

        {/* commutativity essay */}
        <div style={{ marginTop: 60, borderTop: "1px solid var(--border-soft)", paddingTop: 40, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 48 }} className="collapse">
          <div>
            <h3>Why the decoder is symmetric</h3>
            <p style={{ marginTop: 14 }}>
              "A interacts with B" is the same statement as "B interacts with A". Rather than
              hoping the model learns this, the decoder is built from operations that are
              commutative by construction. A concatenation <span className="mono">[mask_A | mask_B]</span> would
              break symmetry for exactly the pairs where one drug has biology and the other
              does not — so the masks are combined as elementwise min and max instead.
            </p>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div className="mono" style={{ fontSize: 14, color: "var(--text-2)", padding: "16px 18px", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--radius)" }}>
              f(A, B) = f(B, A)
            </div>
            <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
              <FigStat n={count(c.total_parameters as number)} label="parameters" />
              <FigStat n={String(c.bio_dim)} label="bio dim" />
              <FigStat n={count(c.optimizer_steps as number)} label="optimizer steps" />
              <FigStat n={`${c.validation_configs}×${c.validation_seeds}`} label="validation grid" />
            </div>
            <span className="mono" style={{ fontSize: 10, color: "var(--text-3)" }}>{c.source as string}</span>
          </div>
        </div>

        <p className="mono" style={{ marginTop: 40, fontSize: 12, color: "var(--text-3)", maxWidth: 680 }}>
          Honest note: adding the pathway rung (M3→M4) did not improve held-out AUPRC, and the
          SUM-aggregation variant outperformed this MEAN model on the test set. See Research.
        </p>
      </div>
    </section>
  );
}

function FigStat({ n, label }: { n: string; label: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <span className="mono" style={{ fontSize: 22, color: "var(--text)" }}>{n}</span>
      <span className="eyebrow">{label}</span>
    </div>
  );
}
