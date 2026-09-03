import { useEffect, useMemo, useState } from "react";
import { loadDrugs, type Drug } from "../data/drugs";
import { Badge } from "../components/Badge";
import { count } from "../lib/format";

export function DrugExplorer() {
  const [drugs, setDrugs] = useState<Drug[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    loadDrugs().then((d) => live && setDrugs(d.drugs)).catch((e) => live && setErr(String(e)));
    return () => { live = false; };
  }, []);

  const filtered = useMemo(() => {
    if (!drugs) return [];
    const s = q.trim().toUpperCase();
    const base = s ? drugs.filter((d) => d.id.includes(s) || (d.formula ?? "").toUpperCase().includes(s)) : drugs;
    return base.slice(0, 200);
  }, [q, drugs]);

  const selected = drugs?.find((d) => d.id === sel) ?? null;

  return (
    <section className="section" style={{ paddingTop: "16vh" }}>
      <div className="wrap">
        <span className="eyebrow">Drug explorer</span>
        <h1 style={{ marginTop: 18, maxInlineSize: "18ch" }}>Browse the experimental universe.</h1>
        <p style={{ marginTop: 18, maxWidth: 640 }}>
          {drugs ? count(drugs.length) : "…"} drugs, identified by canonical DrugBank ID —
          the frozen dataset carries <strong>no human-readable names</strong>, and none are
          invented here. Search by ID or molecular formula.
        </p>

        {err && <p className="mono" style={{ color: "var(--red)", marginTop: 20, fontSize: 13 }}>Failed to load drug data: {err}</p>}

        <input
          aria-label="Search drugs by DrugBank ID or formula"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={drugs ? "Search DrugBank ID (DB00331) or formula (C4H11NO3)…" : "loading drug dataset…"}
          disabled={!drugs}
          className="mono"
          style={{ marginTop: 30, width: "100%", maxWidth: 520, background: "rgba(0,0,0,0.25)", border: "1px solid var(--border-strong)", borderRadius: 8, color: "var(--text)", padding: "11px 14px", fontSize: 13 }}
        />

        <div style={{ display: "grid", gridTemplateColumns: sel ? "1.3fr 1fr" : "1fr", gap: 24, marginTop: 28, alignItems: "start" }} className="collapse">
          {/* table */}
          <div style={{ overflowX: "auto", border: "1px solid var(--border)", borderRadius: "var(--radius)", background: "var(--surface)" }}>
            <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 520 }}>
              <thead>
                <tr>{["DrugBank ID", "formula", "proteins", "pathways", "targets"].map((h) => (
                  <th key={h} className="mono" style={{ textAlign: "left", fontSize: 10.5, color: "var(--text-3)", fontWeight: 400, padding: "10px 14px", borderBottom: "1px solid var(--border)", position: "sticky", top: 0, background: "#0a1525" }}>{h}</th>
                ))}</tr>
              </thead>
              <tbody>
                {filtered.map((d) => (
                  <tr key={d.id} onClick={() => setSel(d.id)} style={{ cursor: "pointer", background: sel === d.id ? "rgba(111,227,245,0.06)" : "transparent" }}>
                    <td className="mono" style={{ ...td, color: "var(--cyan)" }}>{d.id}</td>
                    <td className="mono" style={td}>{d.formula ?? "—"}</td>
                    <td className="mono" style={td}>{d.n_proteins}</td>
                    <td className="mono" style={td}>{d.n_pathways}</td>
                    <td className="mono" style={td}>{d.n_targets}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {drugs && filtered.length === 0 && (
              <div style={{ padding: 24 }}><Badge kind="pending">No match</Badge><p style={{ marginTop: 10, fontSize: 13 }}>No drug matches “{q}”.</p></div>
            )}
            {drugs && q.trim() === "" && (
              <div className="mono" style={{ padding: "10px 14px", fontSize: 10.5, color: "var(--text-3)", borderTop: "1px solid var(--border-soft)" }}>
                showing first {filtered.length} of {count(drugs.length)} — search to narrow
              </div>
            )}
          </div>

          {/* detail */}
          {selected && (
            <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", background: "var(--surface)", backdropFilter: "var(--blur)", padding: 22, position: "sticky", top: 100 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span className="mono" style={{ fontSize: 18, color: "var(--cyan)" }}>{selected.id}</span>
                <button onClick={() => setSel(null)} className="mono" style={{ background: "none", border: "none", color: "var(--text-3)", cursor: "pointer", fontSize: 16 }}>×</button>
              </div>
              <div className="mono" style={{ fontSize: 11, color: "var(--text-3)", marginTop: 6 }}>
                {selected.formula} · {selected.mol_weight} Da · {selected.n_heavy_atoms} heavy atoms
              </div>
              {selected.groups && <div style={{ marginTop: 10 }}><Badge kind="measured">{selected.groups.replace(/\|/g, " · ")}</Badge></div>}
              {selected.inchikey && <div className="mono" style={{ fontSize: 10.5, color: "var(--text-3)", marginTop: 10, wordBreak: "break-all" }}>InChIKey {selected.inchikey}</div>}

              <div style={{ display: "flex", gap: 16, marginTop: 16, flexWrap: "wrap" }}>
                {[["targets", selected.n_targets], ["enzymes", selected.n_enzymes], ["transporters", selected.n_transporters], ["proteins", selected.n_proteins], ["pathways", selected.n_pathways]].map(([l, n]) => (
                  <div key={l as string} style={{ display: "flex", flexDirection: "column" }}>
                    <span className="mono" style={{ fontSize: 17, color: "var(--text)" }}>{n}</span>
                    <span className="eyebrow">{l}</span>
                  </div>
                ))}
              </div>

              {selected.proteins_preview.length > 0 && (
                <div style={{ marginTop: 18 }}>
                  <span className="eyebrow">Proteins (preview of {selected.n_proteins})</span>
                  <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 5 }}>
                    {selected.proteins_preview.map((p, i) => (
                      <div key={p.uniprot + i} style={{ display: "flex", justifyContent: "space-between", gap: 10, fontSize: 12 }}>
                        <span><span className="mono" style={{ color: "var(--cyan)" }}>{p.gene || p.uniprot}</span> <span style={{ color: "var(--text-3)" }}>· {p.relation}</span></span>
                        <span className="mono" style={{ fontSize: 9.5, color: "var(--text-3)" }}>{p.source}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {selected.pathways_preview.length > 0 && (
                <div style={{ marginTop: 18 }}>
                  <span className="eyebrow">Reactome pathways (preview of {selected.n_pathways})</span>
                  <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
                    {selected.pathways_preview.slice(0, 6).map((p) => (
                      <div key={p.reactome_id} style={{ fontSize: 12, color: "var(--text-2)" }}>
                        <span className="mono" style={{ color: "var(--violet)", fontSize: 10.5 }}>{p.reactome_id}</span> {p.name}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <span className="mono" style={{ display: "block", marginTop: 16, fontSize: 10, color: "var(--text-3)" }}>data/mechanism_v1/*.parquet</span>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

const td: React.CSSProperties = { fontSize: 12.5, color: "var(--text-2)", padding: "9px 14px", borderBottom: "1px solid var(--border-soft)" };
