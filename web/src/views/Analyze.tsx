// Pair analysis. The biology shown here is real, read from the frozen dataset.
// The prediction slot is deliberately empty: no trained checkpoint is installed
// on this deployment, and an empty slot is honest where a placeholder number
// would not be. Nothing on this page is a clinical recommendation.
import { useEffect, useMemo, useState } from "react";
import { Badge } from "../components/Badge";
import { frozen } from "../data/frozen";
import { loadDrugs, matchesQuery, type Drug } from "../data/drugs";
import { PairCanvas } from "../canvas/PairCanvas";
import { count } from "../lib/format";
import { useI18n, type Lang } from "../i18n";
import { relationLabel, evidenceLabel } from "../data/vocab";
import { PredictionPanel } from "../components/PredictionPanel";
import { analyzePair, apiConfigured, type AnalyzeState } from "../data/analyze";

// Six real high-degree DrugBank IDs from the frozen extract, used as quick
// picks. The DrugBank ID is the canonical identifier; the name beside it comes
// from the DrugCentral INN join and may be absent.
const QUICK = ["DB00006", "DB00014", "DB00252", "DB00285", "DB00564", "DB01174"];

/** Name in the active UI language, or null when the drug has no matched INN. */
function nameOf(d: Drug | undefined, lang: Lang): string | null {
  if (!d) return null;
  return (lang === "ru" ? d.inn_ru ?? d.inn : d.inn) ?? null;
}

export function Analyze() {
  const { t, lang } = useI18n();
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

  // Score the pair whenever the selection changes. An in-flight request is
  // aborted so a slow earlier pair can never overwrite a newer result.
  const [analysis, setAnalysis] = useState<AnalyzeState>(
    apiConfigured() ? { kind: "idle" } : { kind: "unconfigured" },
  );
  useEffect(() => {
    if (!apiConfigured() || a === b) return;
    const ctl = new AbortController();
    setAnalysis({ kind: "loading" });
    analyzePair(a, b, ctl.signal)
      .then(setAnalysis)
      .catch((e) => { if (!(e instanceof DOMException && e.name === "AbortError")) throw e; });
    return () => ctl.abort();
  }, [a, b]);

  //: True only when a real score came back — never when the API is merely configured.
  const live = analysis.kind === "ok";

  return (
    <section className="section" style={{ paddingTop: "16vh" }}>
      <div className="wrap">
        <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
          <span className="eyebrow">{t("an.eyebrow")}</span>
          <Badge kind={live ? "measured" : "demo"}>{live ? t("an.badge.live") : t("an.badge")}</Badge>
        </div>
        <h1 style={{ marginTop: 18, maxInlineSize: "14ch" }}>{t("an.title")}</h1>
        <p style={{ marginTop: 18, maxWidth: 640 }}>
          {t("an.lede1")} {count(frozen.dataset.n_drugs, lang)}{t(live ? "an.lede2.live" : "an.lede2")}
        </p>

        {err && (
          <div style={{ marginTop: 24, border: "1px solid rgba(255,158,158,0.4)", background: "rgba(255,158,158,0.06)", borderRadius: "var(--radius)", padding: 18 }}>
            <span className="mono" style={{ color: "var(--red)", fontSize: 13 }}>{t("an.loadfail")} {err}</span>
          </div>
        )}

        {/* selectors */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginTop: 40 }} className="collapse">
          <DrugPicker label={t("an.drugA")} value={a} onChange={setA} dataset={dataset} accent="var(--blue)" />
          <DrugPicker label={t("an.drugB")} value={b} onChange={setB} dataset={dataset} accent="var(--cyan)" />
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 16, flexWrap: "wrap" }}>
          <span className="eyebrow" style={{ alignSelf: "center" }}>{t("an.quick")}</span>
          {QUICK.map((id) => {
            const n = nameOf(byId.get(id), lang);
            return (
              <button key={id} onClick={() => (a === id ? setB(id) : setA(id))}
                style={{ background: "none", border: "1px solid var(--border-strong)", color: "var(--text-2)", borderRadius: 16, padding: "4px 12px", fontSize: 12, cursor: "pointer", fontFamily: "var(--font-ui)" }}>
                {n ? <>{n} <span className="mono" style={{ fontSize: 10.5, color: "var(--text-3)" }}>{id}</span></> : <span className="mono" style={{ fontSize: 11 }}>{id}</span>}
              </button>
            );
          })}
        </div>

        {/* result grid */}
        <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 22, marginTop: 42, alignItems: "start" }} className="collapse">
          {/* LEFT — schematic pair + biology evidence */}
          <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
            <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", background: "var(--surface)", backdropFilter: "var(--blur)", padding: 20 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <span className="eyebrow">{t("an.schematic")}</span>
                <Badge kind="specified">{t("an.illustrative")}</Badge>
              </div>
              <PairCanvas seedA={hash(a)} seedB={hash(b)} />
              <p className="mono" style={{ fontSize: 10.5, color: "var(--text-3)", marginTop: 8 }}>
                {t("an.schematicnote")} {a} / {b}.
              </p>
            </div>

            <BiologyPanel drug={drugA} accent="var(--blue)" />
            <BiologyPanel drug={drugB} accent="var(--cyan)" />
          </div>

          {/* RIGHT — research model score, or why there is none */}
          <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
            <PredictionPanel state={analysis} />
          </div>
        </div>
      </div>
    </section>
  );
}

function DrugPicker({ label, value, onChange, dataset, accent }: { label: string; value: string; onChange: (v: string) => void; dataset: Drug[] | null; accent: string }) {
  const { t, lang } = useI18n();
  const [q, setQ] = useState("");
  const matches = useMemo(() => {
    if (!dataset || !q.trim()) return [];
    return dataset.filter((d) => matchesQuery(d, q)).slice(0, 8);
  }, [q, dataset]);

  const current = dataset?.find((d) => d.id === value);
  const currentName = nameOf(current, lang);

  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius)", background: "var(--surface)", padding: 16 }}>
      <span className="eyebrow" style={{ color: accent }}>{label}</span>
      <div style={{ fontSize: 20, color: "var(--text)", marginTop: 8, fontWeight: 600, minHeight: 26 }}>
        {currentName ?? <span className="mono">{value}</span>}
      </div>
      {currentName && <div className="mono" style={{ fontSize: 12, color: accent, marginTop: 2 }}>{value}</div>}
      <input
        aria-label={`${label} — ${t("an.search")}`}
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder={dataset ? t("an.search") : t("an.loading")}
        disabled={!dataset}
        style={{ marginTop: 12, width: "100%", background: "rgba(0,0,0,0.25)", border: "1px solid var(--border-strong)", borderRadius: 6, color: "var(--text)", padding: "8px 10px", fontSize: 13, fontFamily: "var(--font-ui)" }}
      />
      {matches.length > 0 && (
        <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 2 }}>
          {matches.map((d) => {
            const n = nameOf(d, lang);
            return (
              <button key={d.id} onClick={() => { onChange(d.id); setQ(""); }}
                style={{ textAlign: "left", background: "none", border: "none", color: "var(--text-2)", padding: "5px 6px", fontSize: 12.5, cursor: "pointer", borderRadius: 4, fontFamily: "var(--font-ui)" }}>
                {n ? <span style={{ color: "var(--text)" }}>{n} </span> : null}
                <span className="mono" style={{ color: "var(--cyan)", fontSize: 11 }}>{d.id}</span>{" "}
                <span className="mono" style={{ color: "var(--text-3)", fontSize: 10.5 }}>{d.formula ?? "?"}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function BiologyPanel({ drug, accent }: { drug: Drug | undefined; accent: string }) {
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

function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (Math.imul(h, 31) + s.charCodeAt(i)) | 0;
  return Math.abs(h) % 100000;
}
