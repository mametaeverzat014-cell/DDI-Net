// One drug's documented biology, read from the static drugs.json: counts by
// relation and a capped preview of proteins with their evidence type. Works
// with no API at all, which is why it stays on the page when the evidence
// service is not connected.
import type { Drug } from "../data/drugs";
import { useI18n } from "../i18n";
import { relationLabel, evidenceLabel } from "../data/vocab";
import { nameOf } from "./DrugPicker";

export function BiologyPanel({ drug, accent }: { drug: Drug | undefined; accent: string }) {
  const { t, lang } = useI18n();
  if (!drug) return null;
  const name = nameOf(drug, lang);
  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", background: "var(--surface)", padding: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
        <span style={{ fontSize: 15, color: accent, fontWeight: 600 }}>
          {name ? <>{name} <span className="mono" style={{ fontSize: 12, opacity: 0.75 }}>{drug.id}</span></> : <span className="mono">{drug.id}</span>}
        </span>
        <span className="mono" style={{ fontSize: 11, color: "var(--text-3)" }}>{drug.formula} · {drug.mol_weight} Da</span>
      </div>
      <div style={{ display: "flex", gap: 18, marginTop: 12, flexWrap: "wrap" }}>
        <Stat n={drug.n_targets} label={t("dx.targets")} />
        <Stat n={drug.n_enzymes} label={t("dx.enzymes")} />
        <Stat n={drug.n_transporters} label={t("dx.transporters")} />
        <Stat n={drug.n_proteins} label={t("dx.proteins")} />
        <Stat n={drug.n_pathways} label={t("dx.pathways")} />
      </div>
      {drug.proteins_preview.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <span className="eyebrow">{t("an.evidence")} {drug.n_proteins})</span>
          <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 5 }}>
            {drug.proteins_preview.slice(0, 6).map((p, i) => (
              <div key={p.uniprot + i} style={{ display: "flex", justifyContent: "space-between", gap: 12, fontSize: 12.5 }}>
                <span style={{ color: "var(--text-2)" }}>
                  <span className="mono" style={{ color: "var(--cyan)" }}>{p.gene || p.uniprot}</span>
                  <span style={{ color: "var(--text-3)" }} title={p.relation}> · {relationLabel(p.relation, lang)}</span>
                </span>
                <span style={{ fontSize: 10.5, color: "var(--text-3)", whiteSpace: "nowrap" }} title={p.evidence}>{evidenceLabel(p.evidence, lang)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      <span className="mono" style={{ display: "block", marginTop: 14, fontSize: 10, color: "var(--text-3)" }}>data/mechanism_v1/drug_protein_edges.parquet</span>
    </div>
  );
}

function Stat({ n, label }: { n: number; label: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <span className="mono" style={{ fontSize: 18, color: "var(--text)" }}>{n}</span>
      <span className="eyebrow">{label}</span>
    </div>
  );
}

