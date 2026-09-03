import { useEffect, useMemo, useState } from "react";
import { Badge } from "../components/Badge";
import { frozen } from "../data/frozen";
import { loadDrugs, type Drug } from "../data/drugs";
import { PairCanvas } from "../canvas/PairCanvas";
import { count } from "../lib/format";

// Six real high-degree DrugBank IDs from the frozen extract, used as quick
// picks. They are canonical identifiers — the dataset has no drug names.
const QUICK = ["DB00006", "DB00014", "DB00252", "DB00285", "DB00564", "DB01174"];

export function Analyze() {
  const [dataset, setDataset] = useState<Drug[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [a, setA] = useState("DB00006");
  const [b, setB] = useState("DB00564");

  useEffect(() => {
    let live = true;
    loadDrugs().then((d) => live && setDataset(d.drugs)).catch((e) => live && setErr(String(e)));
    return () => { live = false; };
  }, []);

  const byId = useMemo(() => new Map((dataset ?? []).map((d) => [d.id, d])), [dataset]);
  const drugA = byId.get(a);
  const drugB = byId.get(b);

  return (
    <section className="section" style={{ paddingTop: "16vh" }}>
      <div className="wrap">
        <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
          <span className="eyebrow">Analyze a drug pair</span>
          <Badge kind="demo">No trained model connected on this deployment</Badge>
        </div>
        <h1 style={{ marginTop: 18, maxInlineSize: "14ch" }}>Select two drugs.</h1>
        <p style={{ marginTop: 18, maxWidth: 640 }}>
          Choose two drugs from the {count(frozen.dataset.n_drugs)}-drug experimental universe.
          The biological evidence below is real, read from the frozen dataset. A calibrated
          interaction probability is <strong>not</strong> shown, because the frozen inference
          checkpoint is not installed here — see the panel on the right.
        </p>

        {err && (
          <div style={{ marginTop: 24, border: "1px solid rgba(255,158,158,0.4)", background: "rgba(255,158,158,0.06)", borderRadius: "var(--radius)", padding: 18 }}>
            <span className="mono" style={{ color: "var(--red)", fontSize: 13 }}>Could not load the drug dataset: {err}</span>
          </div>
        )}

        {/* selectors */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginTop: 40 }} className="collapse">
          <DrugPicker label="Drug A" value={a} onChange={setA} dataset={dataset} accent="var(--blue)" />
          <DrugPicker label="Drug B" value={b} onChange={setB} dataset={dataset} accent="var(--cyan)" />
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 16, flexWrap: "wrap" }}>
          <span className="eyebrow" style={{ alignSelf: "center" }}>quick picks</span>
          {QUICK.map((id) => (
            <button key={id} className="mono" onClick={() => (a === id ? setB(id) : setA(id))}
              style={{ background: "none", border: "1px solid var(--border-strong)", color: "var(--text-2)", borderRadius: 16, padding: "4px 12px", fontSize: 11, cursor: "pointer" }}>
              {id}
            </button>
          ))}
        </div>

        {/* result grid */}
        <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 22, marginTop: 42, alignItems: "start" }} className="collapse">
          {/* LEFT — schematic pair + biology evidence */}
          <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
            <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", background: "var(--surface)", backdropFilter: "var(--blur)", padding: 20 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <span className="eyebrow">Schematic pair · synthetic geometry</span>
                <Badge kind="specified">Illustrative</Badge>
              </div>
              <PairCanvas seedA={hash(a)} seedB={hash(b)} />
              <p className="mono" style={{ fontSize: 10.5, color: "var(--text-3)", marginTop: 8 }}>
                Ball-and-stick geometry is generated and schematic — not the real 3D conformer of {a} / {b}.
              </p>
            </div>

            <BiologyPanel drug={drugA} accent="var(--blue)" />
            <BiologyPanel drug={drugB} accent="var(--cyan)" />
          </div>

          {/* RIGHT — prediction (disabled) + provenance */}
          <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
            <div style={{ border: "1px solid rgba(255,196,120,0.3)", background: "rgba(255,196,120,0.05)", borderRadius: "var(--radius-lg)", padding: 22 }}>
              <span className="eyebrow" style={{ color: "var(--amber)" }}>Predicted interaction probability</span>
              <div className="mono" style={{ fontSize: 40, color: "var(--amber)", marginTop: 12, letterSpacing: "-0.02em" }}>—</div>
              <p style={{ fontSize: 13, marginTop: 8 }}>{frozen.checkpoint.note}</p>
              <div className="mono" style={{ fontSize: 11, color: "var(--text-3)", marginTop: 16, lineHeight: 1.9 }}>
                <div>model &nbsp;&nbsp;&nbsp;BIO-GINE M4 · seed 0</div>
                <div>run id &nbsp;&nbsp;{frozen.checkpoint.seed0_run_id}</div>
                <div style={{ wordBreak: "break-all" }}>sha256 &nbsp;{frozen.checkpoint.seed0_sha256.slice(0, 24)}…</div>
                <div>uncertainty &nbsp;± not estimated</div>
              </div>
              <p style={{ fontSize: 12, color: "var(--text-3)", marginTop: 16 }}>
                When the frozen checkpoint is installed and its SHA-256 verified, a calibrated
                probability appears here. It would be the model's confidence in the documented-DDI
                class, not a patient risk figure — and never a clinical recommendation.
              </p>
            </div>

            <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", background: "var(--surface)", padding: 20 }}>
              <span className="eyebrow">Provenance</span>
              <ul style={{ margin: "12px 0 0", paddingLeft: 16, display: "flex", flexDirection: "column", gap: 7 }}>
                <li style={{ fontSize: 13, color: "var(--text-2)" }}>Drugs &amp; biology: <span className="mono" style={{ fontSize: 11 }}>data/mechanism_v1/</span></li>
                <li style={{ fontSize: 13, color: "var(--text-2)" }}>Model config: <span className="mono" style={{ fontSize: 11 }}>{frozen.config.selected_config_id as string}</span></li>
                <li style={{ fontSize: 13, color: "var(--text-2)" }}>No edge of the interaction graph enters the drug representation.</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function DrugPicker({ label, value, onChange, dataset, accent }: { label: string; value: string; onChange: (v: string) => void; dataset: Drug[] | null; accent: string }) {
  const [q, setQ] = useState("");
  const matches = useMemo(() => {
    if (!dataset) return [];
    const s = q.trim().toUpperCase();
    if (!s) return [];
    return dataset.filter((d) => d.id.includes(s) || (d.formula ?? "").toUpperCase().includes(s)).slice(0, 8);
  }, [q, dataset]);

  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius)", background: "var(--surface)", padding: 16 }}>
      <span className="eyebrow" style={{ color: accent }}>{label}</span>
      <div className="mono" style={{ fontSize: 22, color: "var(--text)", marginTop: 8 }}>{value}</div>
      <input
        aria-label={`Search ${label} by DrugBank ID`}
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder={dataset ? "Search DrugBank ID (e.g. DB00331)" : "loading drugs…"}
        disabled={!dataset}
        className="mono"
        style={{ marginTop: 12, width: "100%", background: "rgba(0,0,0,0.25)", border: "1px solid var(--border-strong)", borderRadius: 6, color: "var(--text)", padding: "8px 10px", fontSize: 12 }}
      />
      {matches.length > 0 && (
        <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 2 }}>
          {matches.map((d) => (
            <button key={d.id} onClick={() => { onChange(d.id); setQ(""); }} className="mono"
              style={{ textAlign: "left", background: "none", border: "none", color: "var(--text-2)", padding: "5px 6px", fontSize: 12, cursor: "pointer", borderRadius: 4 }}>
              {d.id} · <span style={{ color: "var(--text-3)" }}>{d.formula ?? "?"} · {d.n_proteins}p/{d.n_pathways}path</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function BiologyPanel({ drug, accent }: { drug: Drug | undefined; accent: string }) {
  if (!drug) return null;
  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", background: "var(--surface)", padding: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <span className="mono" style={{ fontSize: 15, color: accent }}>{drug.id}</span>
        <span className="mono" style={{ fontSize: 11, color: "var(--text-3)" }}>{drug.formula} · {drug.mol_weight} Da</span>
      </div>
      <div style={{ display: "flex", gap: 18, marginTop: 12, flexWrap: "wrap" }}>
        <Stat n={drug.n_targets} label="targets" />
        <Stat n={drug.n_enzymes} label="enzymes" />
        <Stat n={drug.n_transporters} label="transporters" />
        <Stat n={drug.n_proteins} label="proteins" />
        <Stat n={drug.n_pathways} label="pathways" />
      </div>
      {drug.proteins_preview.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <span className="eyebrow">Protein evidence (preview of {drug.n_proteins})</span>
          <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 5 }}>
            {drug.proteins_preview.slice(0, 6).map((p, i) => (
              <div key={p.uniprot + i} style={{ display: "flex", justifyContent: "space-between", gap: 12, fontSize: 12.5 }}>
                <span style={{ color: "var(--text-2)" }}>
                  <span className="mono" style={{ color: "var(--cyan)" }}>{p.gene || p.uniprot}</span>
                  <span style={{ color: "var(--text-3)" }}> · {p.relation}</span>
                </span>
                <span className="mono" style={{ fontSize: 10, color: "var(--text-3)", whiteSpace: "nowrap" }}>{p.evidence.replace(/_/g, " ").toLowerCase()}</span>
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

function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (Math.imul(h, 31) + s.charCodeAt(i)) | 0;
  return Math.abs(h) % 100000;
}
