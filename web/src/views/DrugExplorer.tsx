// Drug catalogue. Search accepts a Russian name, an English INN, a DrugBank ID
// or a molecular formula; the DrugBank ID is the canonical identifier and is
// shown on every row regardless of language, because it is what the model and
// every artifact key on.
import { useEffect, useMemo, useState } from "react";
import { loadDrugs, matchesQuery, type DrugDataset } from "../data/drugs";
import { Badge } from "../components/Badge";
import { count } from "../lib/format";
import { useI18n, fill } from "../i18n";
import { relationLabel, groupsLabel, drugTypeLabel } from "../data/vocab";

export function DrugExplorer() {
  const { t, lang } = useI18n();
  const [data, setData] = useState<DrugDataset | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    loadDrugs().then((d) => live && setData(d)).catch((e) => live && setErr(String(e)));
    return () => { live = false; };
  }, []);

  const drugs = data?.drugs ?? null;

  const filtered = useMemo(() => {
    if (!drugs) return [];
    const base = q.trim() ? drugs.filter((d) => matchesQuery(d, q)) : drugs;
    return base.slice(0, 200);
  }, [q, drugs]);

  const selected = drugs?.find((d) => d.id === sel) ?? null;
  const nUnnamed = data ? data.meta.n_drugs - data.meta.names.n_with_inn : 0;

  return (
    <section className="section" style={{ paddingTop: "16vh" }}>
      <div className="wrap">
        <span className="eyebrow">{t("dx.eyebrow")}</span>
        <h1 style={{ marginTop: 18, maxInlineSize: "18ch" }}>{t("dx.title")}</h1>
        <p style={{ marginTop: 18, maxWidth: 640 }}>
          {drugs ? count(drugs.length, lang) : "…"} {t("dx.lede")}
        </p>

        {/* name provenance — English INN is real data, Russian is a UI label */}
        {data && (
          <p className="mono" style={{ marginTop: 14, maxWidth: 680, fontSize: 11.5, color: "var(--text-3)", lineHeight: 1.8 }}>
            {fill(t("dx.namenote"), { n: nUnnamed })}
          </p>
        )}

        {err && <p className="mono" style={{ color: "var(--red)", marginTop: 20, fontSize: 13 }}>{t("an.loadfail")} {err}</p>}

        <input
          aria-label={t("an.search")}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={drugs ? t("dx.searchph") : t("an.loading")}
          disabled={!drugs}
          style={{ marginTop: 24, width: "100%", maxWidth: 560, background: "rgba(0,0,0,0.25)", border: "1px solid var(--border-strong)", borderRadius: 8, color: "var(--text)", padding: "11px 14px", fontSize: 14, fontFamily: "var(--font-ui)" }}
        />

        <div style={{ display: "grid", gridTemplateColumns: sel ? "1.3fr 1fr" : "1fr", gap: 24, marginTop: 28, alignItems: "start" }} className="collapse">
          {/* table */}
          <div style={{ overflowX: "auto", border: "1px solid var(--border)", borderRadius: "var(--radius)", background: "var(--surface)" }}>
            <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 640 }}>
              <thead>
                <tr>{["dx.col.name", "dx.col.id", "dx.col.formula", "dx.col.proteins", "dx.col.pathways", "dx.col.targets"].map((h) => (
                  <th key={h} className="mono" style={{ textAlign: "left", fontSize: 10.5, color: "var(--text-3)", fontWeight: 400, padding: "10px 14px", borderBottom: "1px solid var(--border)", position: "sticky", top: 0, background: "#0a1525" }}>{t(h)}</th>
                ))}</tr>
              </thead>
              <tbody>
                {filtered.map((d) => {
                  const name = lang === "ru" ? d.inn_ru ?? d.inn : d.inn;
                  return (
                    <tr key={d.id} onClick={() => setSel(d.id)} style={{ cursor: "pointer", background: sel === d.id ? "rgba(111,227,245,0.06)" : "transparent" }}>
                      <td style={{ ...td, color: name ? "var(--text)" : "var(--text-3)" }} title={d.inn ?? undefined}>
                        {name ?? t("dx.noname")}
                      </td>
                      <td className="mono" style={{ ...td, color: "var(--cyan)" }}>{d.id}</td>
                      <td className="mono" style={td}>{d.formula ?? "—"}</td>
                      <td className="mono" style={td}>{d.n_proteins}</td>
                      <td className="mono" style={td}>{d.n_pathways}</td>
                      <td className="mono" style={td}>{d.n_targets}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {drugs && filtered.length === 0 && (
              <div style={{ padding: 24 }}><Badge kind="pending">{t("dx.nomatch")}</Badge><p style={{ marginTop: 10, fontSize: 13 }}>{t("dx.nomatchfor")} «{q}».</p></div>
            )}
            {drugs && q.trim() === "" && (
              <div className="mono" style={{ padding: "10px 14px", fontSize: 10.5, color: "var(--text-3)", borderTop: "1px solid var(--border-soft)" }}>
                {t("dx.showing")} {filtered.length} {t("dx.of")} {count(drugs.length, lang)} {t("dx.narrow")}
              </div>
            )}
          </div>

          {/* detail */}
          {selected && (
            <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", background: "var(--surface)", backdropFilter: "var(--blur)", padding: 22, position: "sticky", top: 100 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
                <div>
                  <div style={{ fontSize: 19, color: "var(--text)", fontWeight: 600 }}>
                    {(lang === "ru" ? selected.inn_ru ?? selected.inn : selected.inn) ?? selected.id}
                  </div>
                  <div className="mono" style={{ fontSize: 13, color: "var(--cyan)", marginTop: 3 }}>{selected.id}</div>
                  {selected.inn && lang === "ru" && (
                    <div className="mono" style={{ fontSize: 10.5, color: "var(--text-3)", marginTop: 3 }}>INN: {selected.inn}</div>
                  )}
                </div>
                <button onClick={() => setSel(null)} className="mono" aria-label="close" style={{ background: "none", border: "none", color: "var(--text-3)", cursor: "pointer", fontSize: 16 }}>×</button>
              </div>
              <div className="mono" style={{ fontSize: 11, color: "var(--text-3)", marginTop: 8 }}>
                {selected.formula} · {selected.mol_weight} Da · {selected.n_heavy_atoms} {lang === "ru" ? "тяжёлых атомов" : "heavy atoms"}
              </div>
              <div style={{ display: "flex", gap: 6, marginTop: 10, flexWrap: "wrap" }}>
                {selected.groups && <Badge kind="measured">{groupsLabel(selected.groups, lang)}</Badge>}
                {selected.drug_type && <Badge kind="measured">{drugTypeLabel(selected.drug_type, lang)}</Badge>}
              </div>
              {selected.inchikey && <div className="mono" style={{ fontSize: 10.5, color: "var(--text-3)", marginTop: 10, wordBreak: "break-all" }}>InChIKey {selected.inchikey}</div>}

              <div style={{ display: "flex", gap: 16, marginTop: 16, flexWrap: "wrap" }}>
                {([["dx.targets", selected.n_targets], ["dx.enzymes", selected.n_enzymes], ["dx.transporters", selected.n_transporters], ["dx.proteins", selected.n_proteins], ["dx.pathways", selected.n_pathways]] as const).map(([k, n]) => (
                  <div key={k} style={{ display: "flex", flexDirection: "column" }}>
                    <span className="mono" style={{ fontSize: 17, color: "var(--text)" }}>{n}</span>
                    <span className="eyebrow">{t(k)}</span>
                  </div>
                ))}
              </div>

              {selected.proteins_preview.length > 0 && (
                <div style={{ marginTop: 18 }}>
                  <span className="eyebrow">{t("dx.proteinsPreview")} {selected.n_proteins})</span>
                  <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 5 }}>
                    {selected.proteins_preview.map((p, i) => (
                      <div key={p.uniprot + i} style={{ display: "flex", justifyContent: "space-between", gap: 10, fontSize: 12 }}>
                        <span>
                          <span className="mono" style={{ color: "var(--cyan)" }}>{p.gene || p.uniprot}</span>{" "}
                          <span style={{ color: "var(--text-3)" }} title={p.relation}>· {relationLabel(p.relation, lang)}</span>
                        </span>
                        <span className="mono" style={{ fontSize: 9.5, color: "var(--text-3)" }}>{p.source}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {selected.pathways_preview.length > 0 && (
                <div style={{ marginTop: 18 }}>
                  <span className="eyebrow">{t("dx.pathwaysPreview")} {selected.n_pathways})</span>
                  <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
                    {selected.pathways_preview.slice(0, 6).map((p) => (
                      <div key={p.reactome_id} style={{ fontSize: 12, color: "var(--text-2)" }}>
                        <span className="mono" style={{ color: "var(--violet)", fontSize: 10.5 }}>{p.reactome_id}</span> {p.name}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <p className="mono" style={{ marginTop: 14, fontSize: 10, color: "var(--text-3)", lineHeight: 1.7 }}>{t("dx.canonical")}</p>
              <span className="mono" style={{ display: "block", marginTop: 8, fontSize: 10, color: "var(--text-3)" }}>{data?.meta.source}</span>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

const td: React.CSSProperties = { fontSize: 12.5, color: "var(--text-2)", padding: "9px 14px", borderBottom: "1px solid var(--border-soft)" };
