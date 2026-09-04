import { frozen } from "../data/frozen";
import { Metric } from "../components/Metric";
import { count, pct } from "../lib/format";
import { useI18n, pick, type Bi } from "../i18n";
import { relationLabel, evidenceLabel } from "../data/vocab";

// Source names (DrugBank, ChEMBL, Reactome, SIDER) are proper nouns and stay as
// they are in every language; only the role description is translated.
const SOURCE_ROLE: Record<string, Bi> = {
  DrugBank: { ru: "метки DDI + белковые отношения", en: "DDI labels + protein relations" },
  ChEMBL: { ru: "курированный механизм действия + биоактивность", en: "curated MoA + bioactivity" },
  Reactome: { ru: "принадлежность путям", en: "pathway membership" },
  SIDER: { ru: "нежелательные явления (исключены из обучения)", en: "adverse events (held out of training)" },
};
const SOURCE_COV: Record<string, Bi> = {
  DrugBank: { ru: "препаратов с ≥1 белком", en: "drugs with ≥1 protein" },
  ChEMBL: { ru: "препаратов сопоставлено", en: "drugs mapped" },
  Reactome: { ru: "препаратов с ≥1 путём", en: "drugs with ≥1 pathway" },
  SIDER: { ru: "препаратов есть в SIDER", en: "drugs with SIDER" },
};

export function Data() {
  const { t, lang } = useI18n();
  const cov = frozen.coverage;
  const bg = frozen.biology_graph;
  const d = frozen.dataset;

  const sources = [
    { name: "DrugBank", cov: cov.protein_any_pct as number },
    { name: "ChEMBL", cov: cov.chembl_pct as number },
    { name: "Reactome", cov: cov.reactome_pct as number },
    { name: "SIDER", cov: cov.sider_pct as number },
  ];

  return (
    <section className="section" style={{ paddingTop: "16vh" }}>
      <div className="wrap">
        <span className="eyebrow">{t("dt.eyebrow")}</span>
        <h1 style={{ marginTop: 18, maxInlineSize: "16ch" }}>{t("dt.title")}</h1>
        <p style={{ marginTop: 18, maxWidth: 640 }}>
          {count(d.n_drugs, lang)} {t("dt.lede1")} {count(d.n_pairs, lang)} {t("dt.lede2")} {d.dataset_version}).{" "}
          {d.excluded_drug} {t("dt.lede3")} ({d.excluded_pairs} {t("dt.lede4")}{" "}
          <strong>{t("dt.lede5")}</strong>.
        </p>

        {/* headline counts */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 26, marginTop: 40 }}>
          <Metric value={count(d.n_drugs, lang)} label={t("dt.m.drugs")} source={d.source} size={30} />
          <Metric value={count(d.n_pairs, lang)} label={t("dt.m.pairs")} source={d.source} size={30} />
          <Metric value={count(bg.drug_protein_edge_rows, lang)} label={t("dt.m.dp")} source={bg.source} size={30} />
          <Metric value={count(bg.protein_pathway_edges, lang)} label={t("dt.m.pp")} source={bg.source} size={30} />
        </div>

        {/* source coverage cards */}
        <h2 style={{ marginTop: 80 }}>{t("dt.sources")}</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: 16, marginTop: 24 }}>
          {sources.map((s) => (
            <div key={s.name} style={{ border: "1px solid var(--border)", borderRadius: "var(--radius)", background: "var(--surface)", padding: 20 }}>
              <div className="mono" style={{ fontSize: 15, color: "var(--cyan)" }}>{s.name}</div>
              <p style={{ marginTop: 8, fontSize: 13 }}>{pick(SOURCE_ROLE[s.name], lang)}</p>
              <div style={{ marginTop: 14 }}>
                <div style={{ height: 6, background: "rgba(255,255,255,0.06)", borderRadius: 3, overflow: "hidden" }}>
                  <div style={{ width: `${s.cov}%`, height: "100%", background: "var(--cyan)" }} />
                </div>
                <div className="mono" style={{ marginTop: 6, fontSize: 11, color: "var(--text-3)" }}>{pct(s.cov)} · {pick(SOURCE_COV[s.name], lang)}</div>
              </div>
            </div>
          ))}
        </div>
        <span className="mono" style={{ display: "block", marginTop: 14, fontSize: 10.5, color: "var(--text-3)" }}>{cov.source as string}</span>

        {/* edge classes / relation types */}
        <h2 style={{ marginTop: 80 }}>{t("dt.relations")}</h2>
        <div style={{ marginTop: 24, overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 460 }}>
            <thead>
              <tr>{["dt.col.rel", "dt.col.edges", "dt.col.share"].map((h) => (
                <th key={h} className="mono" style={{ textAlign: "left", fontSize: 11, color: "var(--text-3)", fontWeight: 400, padding: "8px 12px", borderBottom: "1px solid var(--border)" }}>{t(h)}</th>
              ))}</tr>
            </thead>
            <tbody>
              {Object.entries(bg.relation_counts).map(([k, v]) => {
                const total = Object.values(bg.relation_counts).reduce((a, b) => a + b, 0);
                return (
                  <tr key={k}>
                    {/* canonical value kept in the tooltip, translated label shown */}
                    <td style={td} title={k}>{relationLabel(k, lang)}</td>
                    <td className="mono" style={td}>{count(v, lang)}</td>
                    <td className="mono" style={{ ...td, color: "var(--text-3)" }}>{pct((v / total) * 100)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p style={{ marginTop: 16, maxWidth: 640, fontSize: 13.5 }}>
          {t("dt.evidence")}{" "}
          {bg.evidence_types.map((e) => evidenceLabel(e, lang)).join(" · ")}{t("dt.evidence2")}
        </p>
        <span className="mono" style={{ display: "block", marginTop: 8, fontSize: 10.5, color: "var(--text-3)" }}>{bg.source}</span>

        {/* held-out-coverage honesty */}
        <div style={{ marginTop: 70, border: "1px solid rgba(255,196,120,0.25)", background: "rgba(255,196,120,0.04)", borderRadius: "var(--radius)", padding: 22 }}>
          <span className="eyebrow" style={{ color: "var(--amber)" }}>{t("dt.notmean")}</span>
          <p style={{ marginTop: 12, maxWidth: 720 }}>
            {t("dt.notmeanp1")} {pct(100 - (cov.protein_any_pct as number))} {t("dt.notmeanp2")}
          </p>
        </div>
      </div>
    </section>
  );
}

const td: React.CSSProperties = { fontSize: 13, color: "var(--text-2)", padding: "9px 12px", borderBottom: "1px solid var(--border-soft)" };
