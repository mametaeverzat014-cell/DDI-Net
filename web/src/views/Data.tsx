import { frozen } from "../data/frozen";
import { Metric } from "../components/Metric";
import { count, pct } from "../lib/format";

export function Data() {
  const cov = frozen.coverage;
  const bg = frozen.biology_graph;
  const d = frozen.dataset;

  const sources = [
    { name: "DrugBank", role: "DDI labels + protein relations", cov: cov.protein_any_pct as number, covLabel: "drugs with ≥1 protein" },
    { name: "ChEMBL", role: "curated MoA + bioactivity", cov: cov.chembl_pct as number, covLabel: "drugs mapped" },
    { name: "Reactome", role: "pathway membership", cov: cov.reactome_pct as number, covLabel: "drugs with ≥1 pathway" },
    { name: "SIDER", role: "adverse events (held out of training)", cov: cov.sider_pct as number, covLabel: "drugs with SIDER" },
  ];

  return (
    <section className="section" style={{ paddingTop: "16vh" }}>
      <div className="wrap">
        <span className="eyebrow">Data &amp; provenance</span>
        <h1 style={{ marginTop: 18, maxInlineSize: "16ch" }}>Every edge has a source.</h1>
        <p style={{ marginTop: 18, maxWidth: 640 }}>
          {count(d.n_drugs)} drugs and {count(d.n_pairs)} documented positive DDI pairs
          (dataset {d.dataset_version}). {d.excluded_drug} was excluded for an unparseable
          SMILES ({d.excluded_pairs} pairs). The biological graph is built only from a drug's
          own annotations — <strong>no interaction edge enters it</strong>.
        </p>

        {/* headline counts */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 26, marginTop: 40 }}>
          <Metric value={count(d.n_drugs)} label="drugs" source={d.source} size={30} />
          <Metric value={count(d.n_pairs)} label="documented DDI pairs" source={d.source} size={30} />
          <Metric value={count(bg.drug_protein_edge_rows)} label="drug–protein edges" source={bg.source} size={30} />
          <Metric value={count(bg.protein_pathway_edges)} label="protein–pathway edges" source={bg.source} size={30} />
        </div>

        {/* source coverage cards */}
        <h2 style={{ marginTop: 80 }}>Sources</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: 16, marginTop: 24 }}>
          {sources.map((s) => (
            <div key={s.name} style={{ border: "1px solid var(--border)", borderRadius: "var(--radius)", background: "var(--surface)", padding: 20 }}>
              <div className="mono" style={{ fontSize: 15, color: "var(--cyan)" }}>{s.name}</div>
              <p style={{ marginTop: 8, fontSize: 13 }}>{s.role}</p>
              <div style={{ marginTop: 14 }}>
                <div style={{ height: 6, background: "rgba(255,255,255,0.06)", borderRadius: 3, overflow: "hidden" }}>
                  <div style={{ width: `${s.cov}%`, height: "100%", background: "var(--cyan)" }} />
                </div>
                <div className="mono" style={{ marginTop: 6, fontSize: 11, color: "var(--text-3)" }}>{pct(s.cov)} · {s.covLabel}</div>
              </div>
            </div>
          ))}
        </div>
        <span className="mono" style={{ display: "block", marginTop: 14, fontSize: 10.5, color: "var(--text-3)" }}>{cov.source as string}</span>

        {/* edge classes / relation types */}
        <h2 style={{ marginTop: 80 }}>Drug → protein relations</h2>
        <div style={{ marginTop: 24, overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 460 }}>
            <thead>
              <tr>{["relation type", "edges", "share"].map((h) => (
                <th key={h} className="mono" style={{ textAlign: "left", fontSize: 11, color: "var(--text-3)", fontWeight: 400, padding: "8px 12px", borderBottom: "1px solid var(--border)" }}>{h}</th>
              ))}</tr>
            </thead>
            <tbody>
              {Object.entries(bg.relation_counts).map(([k, v]) => {
                const total = Object.values(bg.relation_counts).reduce((a, b) => a + b, 0);
                return (
                  <tr key={k}>
                    <td className="mono" style={td}>{k}</td>
                    <td className="mono" style={td}>{count(v)}</td>
                    <td className="mono" style={{ ...td, color: "var(--text-3)" }}>{pct((v / total) * 100)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p style={{ marginTop: 16, maxWidth: 640, fontSize: 13.5 }}>
          Evidence type is carried on every edge and distinguishes how a relation is known:{" "}
          {bg.evidence_types.map((e) => e.replace(/_/g, " ").toLowerCase()).join(" · ")}. These map to the
          M1→M4 evidence ladder.
        </p>
        <span className="mono" style={{ display: "block", marginTop: 8, fontSize: 10.5, color: "var(--text-3)" }}>{bg.source}</span>

        {/* held-out-coverage honesty */}
        <div style={{ marginTop: 70, border: "1px solid rgba(255,196,120,0.25)", background: "rgba(255,196,120,0.04)", borderRadius: "var(--radius)", padding: 22 }}>
          <span className="eyebrow" style={{ color: "var(--amber)" }}>What the coverage does not mean</span>
          <p style={{ marginTop: 12, maxWidth: 720 }}>
            These 1,705 drugs are a TDC-selected subset of DrugBank (~15,000 drugs) chosen by
            upstream criteria unknown to us — not a representative sample. Coverage is high but
            not complete: {pct(100 - (cov.protein_any_pct as number))} of drugs have no protein
            annotation. Adverse-event (SIDER) data is present for provenance but is held out of
            training and out of every predictive claim on this site.
          </p>
        </div>
      </div>
    </section>
  );
}

const td: React.CSSProperties = { fontSize: 13, color: "var(--text-2)", padding: "9px 12px", borderBottom: "1px solid var(--border-soft)" };
