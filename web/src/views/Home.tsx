import type { View } from "../App";
import { HomeCanvas } from "../canvas/HomeCanvas";
import { Badge } from "../components/Badge";
import { Metric } from "../components/Metric";
import { frozen, model } from "../data/frozen";
import { auprc, count, delta, meanSd, pct } from "../lib/format";

export function Home({ setView }: { setView: (v: View) => void }) {
  const m4 = model("BIO-GINE M4");
  const m0 = model("Aligned molecular GINE (M0)");
  const shuffled = model("BIO-GINE M4, shuffled biology (CONTROL F)");
  const d = frozen.dataset;
  const leak = frozen.leakage.both_endpoints_seen;

  return (
    <>
      <HomeCanvas />

      {/* HERO */}
      <section style={{ minHeight: "100vh", display: "flex", flexDirection: "column", justifyContent: "center", position: "relative", zIndex: 1 }}>
        <div className="wrap" style={{ pointerEvents: "none" }}>
          <span className="eyebrow">Mechanism-aware drug interaction research</span>
          <h1 style={{ marginTop: 22, maxInlineSize: "16ch" }}>
            Understand the biology<br />behind drug interactions.
          </h1>
          <p style={{ marginTop: 26, maxWidth: 560 }}>
            Can biologically grounded drug representations transfer to drugs a model has
            never seen — without relying on the known interaction network? A preregistered
            study with falsification controls.
          </p>
          <div style={{ marginTop: 34, display: "flex", gap: 14, flexWrap: "wrap", pointerEvents: "auto" }}>
            <button onClick={() => setView("analyze")} style={btnFilled}>Explore a drug pair</button>
            <button onClick={() => setView("model")} style={btnOutline}>Explore the model</button>
          </div>
        </div>
        <div className="wrap" style={{ position: "absolute", bottom: 34, left: 0, right: 0, display: "flex", justifyContent: "space-between", alignItems: "baseline", pointerEvents: "none" }}>
          <span className="mono" style={{ fontSize: 11, color: "var(--text-3)" }}>
            TDC DrugBank · {count(d.n_drugs)} drugs · {count(d.n_pairs)} pairs
          </span>
          <span className="mono" style={{ fontSize: 11, color: "var(--text-3)" }}>Research software · not a clinical tool</span>
        </div>
      </section>

      {/* 01 THE PROBLEM */}
      <section className="section">
        <div className="wrap">
          <span className="eyebrow">01 — The problem</span>
          <h2 className="reveal" style={{ marginTop: 18, maxWidth: "14ch" }}>Known interactions are not enough.</h2>
          <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 48, marginTop: 40, alignItems: "start" }} className="collapse">
            <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
              <p>
                Most drug-interaction benchmarks split data at the level of <em>pairs</em>.
                A single drug can then appear in both training and test pairs, and a model
                scores well by recognising familiar drugs and their known interaction
                neighbourhoods — context that vanishes for a genuinely new compound.
              </p>
              <p>
                Splitting by <em>drug</em> removes that shortcut: every test drug is unseen.
                The table shows how completely the leak disappears.
              </p>
              <span className="hand" style={{ fontSize: 24, color: "var(--amber)", opacity: 0.9 }}>
                what happens when the drug is new?
              </span>
            </div>
            <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius)", background: "var(--surface)", backdropFilter: "var(--blur)", padding: 22 }}>
              <span className="eyebrow" style={{ display: "block", marginBottom: 14 }}>Test pairs with both drugs already in training</span>
              {([["random_pair", "Random pair split"], ["drug", "Drug holdout"], ["scaffold", "Scaffold holdout"]] as const).map(([k, label]) => (
                <div key={k} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 0", borderTop: "1px solid var(--border-soft)" }}>
                  <span style={{ fontSize: 14, color: "var(--text-2)" }}>{label}</span>
                  <span className="mono" style={{ fontSize: 16, color: k === "random_pair" ? "var(--amber)" : "var(--cyan)" }}>
                    {pct(leak[k] * 100, 2)}
                  </span>
                </div>
              ))}
              <span className="mono" style={{ display: "block", marginTop: 14, fontSize: 10, color: "var(--text-3)" }}>{frozen.leakage.source}</span>
            </div>
          </div>
        </div>
      </section>

      {/* 02 RESEARCH QUESTION + PRIMARY RESULT */}
      <section className="section">
        <div className="wrap">
          <span className="eyebrow">02 — The question &amp; the result</span>
          <h2 className="reveal" style={{ marginTop: 18, maxWidth: "18ch" }}>
            Does biological identity transfer to unseen drugs?
          </h2>
          <p style={{ marginTop: 22, maxWidth: 620 }}>
            BIO-GINE encodes each drug from its molecular structure and its biological
            annotations — the proteins it acts on and the pathways they sit in — with no
            edge of the interaction graph entering the representation. Evaluated on drugs
            held out of training:
          </p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: 28, marginTop: 40 }}>
            <Metric label="BIO-GINE M4 · pooled drug-holdout (S2+S3)" value={meanSd(m4.pooled_mean, m4.pooled_std)} accent="var(--cyan)" source={m4.source} />
            <Metric label="Aligned molecular GINE (M0)" value={meanSd(m0.pooled_mean, m0.pooled_std)} accent="var(--blue)" source={m0.source} />
            <Metric label="Improvement over molecular-only" value={delta(m4.pooled_mean - m0.pooled_mean)} sub="AUPRC · all five seeds agree in direction" accent="var(--text)" source="reports/v2_statistics/final_h1_h5_holm.csv" />
          </div>
          <p className="mono" style={{ marginTop: 26, fontSize: 12, color: "var(--text-3)", maxWidth: 640 }}>
            Pooled = S2 (one drug held out) + S3 (both held out). AUPRC 0.5 is a random
            ranker at 50% prevalence. The number is meaningful only against its baselines.
          </p>
        </div>
      </section>

      {/* 03 WHY CONTROL F MATTERS */}
      <section className="section">
        <div className="wrap">
          <span className="eyebrow">03 — The control that carries the claim</span>
          <h2 className="reveal" style={{ marginTop: 18, maxWidth: "16ch" }}>Identity, not popularity.</h2>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 48, marginTop: 40, alignItems: "center" }} className="collapse">
            <p>
              Well-studied drugs carry more annotations <em>and</em> more documented
              interactions, so a biological gain could just be detecting how much a drug has
              been studied. CONTROL F rewires <em>which</em> proteins each drug is annotated
              against while preserving the exact annotation count per drug and per protein.
              If counting were the signal, performance should barely move.
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
              <Metric label="True biology · M4" value={auprc(m4.pooled_mean)} accent="var(--cyan)" source={m4.source} size={40} />
              <Metric label="Degree-preserving shuffled biology" value={auprc(shuffled.pooled_mean)} accent="var(--violet)" source={shuffled.source} size={40} />
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span className="mono" style={{ fontSize: 20, color: "var(--text)" }}>{delta(m4.pooled_mean - shuffled.pooled_mean)}</span>
                <span style={{ fontSize: 13, color: "var(--text-2)" }}>
                  AUPRC lost when identity is destroyed — larger than the entire benefit of adding biology.
                </span>
              </div>
              <p style={{ fontSize: 13, color: "var(--text-3)" }}>
                This <em>supports</em> that biological identity carries information beyond
                annotation count. It does not establish causal mechanism.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* HONEST FINDINGS STRIP */}
      <section className="section" style={{ paddingTop: 0 }}>
        <div className="wrap">
          <div style={{ border: "1px solid rgba(255,196,120,0.25)", background: "rgba(255,196,120,0.05)", borderRadius: "var(--radius)", padding: 24 }}>
            <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 14 }}>
              <Badge kind="exploratory">Reported honestly</Badge>
              <span style={{ fontSize: 13, color: "var(--text-2)" }}>This study reports against itself.</span>
            </div>
            <ul style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 8 }}>
              <li style={{ fontSize: 14, color: "var(--text-2)" }}>
                The evidence ladder is <strong>non-monotonic</strong>: M2 ({auprc(model("M2").pooled_mean)}) and the
                SUM control ({auprc(model("M4 SUM (CONTROL C)").pooled_mean)}) both exceed the preregistered primary M4 ({auprc(m4.pooled_mean)}).
              </li>
              <li style={{ fontSize: 14, color: "var(--text-2)" }}>Hypothesis H-V2-5 was an exploratory direction and was <strong>not supported</strong>.</li>
              <li style={{ fontSize: 14, color: "var(--text-2)" }}>CONTROL E's held-out R² is <strong>not identifiable</strong> (target variance is zero).</li>
              <li style={{ fontSize: 14, color: "var(--text-2)" }}>Scaffold-disjoint evaluation was <strong>not performed</strong> in final V2.</li>
            </ul>
          </div>
          <div style={{ marginTop: 46, display: "flex", gap: 14, flexWrap: "wrap" }}>
            <button onClick={() => setView("research")} style={btnFilled}>Read the results</button>
            <button onClick={() => setView("model")} style={btnOutline}>See how the model works</button>
          </div>
        </div>
      </section>
    </>
  );
}

const btnFilled: React.CSSProperties = {
  background: "var(--cyan)", color: "#06101f", border: "none", borderRadius: 24,
  padding: "12px 22px", fontSize: 14, fontWeight: 600, cursor: "pointer", fontFamily: "var(--font-ui)",
};
const btnOutline: React.CSSProperties = {
  background: "none", color: "var(--text)", border: "1px solid var(--border-strong)", borderRadius: 24,
  padding: "12px 22px", fontSize: 14, fontWeight: 500, cursor: "pointer", fontFamily: "var(--font-ui)",
};
