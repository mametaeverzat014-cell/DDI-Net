// DDI-Net 3.0 — Drug Interaction Analyzer.
//
// Answers, in this order: what is documented, why it might happen, what the
// research model sees, how certain each part is, and what is missing. Simple
// mode (the default) is written for someone who has never heard of CYP2C9;
// research mode adds identifiers, roles, PubMed links, the model's regime and
// its measured performance — nothing from the earlier pages is removed, the
// v2 score page stays one click away.
//
// The page never shows a reassuring state. "No documentation found" is grey,
// says it is not a safety verdict, and is the same weight as any other status.
import { useEffect, useMemo, useState } from "react";
import type { View } from "../App";
import { DrugPicker, nameOf } from "../components/DrugPicker";
import { BiologyPanel } from "../components/BiologyPanel";
import { loadDrugs, type Drug } from "../data/drugs";
import { fetchReport, type PairReport, type Remote } from "../data/v3";
import { apiConfigured } from "../data/analyze";
import { useI18n, pick, type Bi } from "../i18n";
import {
  EvidenceList, ExplanationView, MechanismTable, ModelPanelV3, RemoteNotice, SourcesChecked, StatusBanner,
} from "../components/v3/ReportParts";
import { buildRefIndex } from "../components/v3/refs";
import { ExportReport } from "../components/v3/ExportReport";
import type { ExportInput } from "../pdf/types";

// Real DrugBank IDs, chosen to show different kinds of result: a documented
// pair with a pharmacokinetic hypothesis, a statin + macrolide, and a pair with
// no documented record.
const EXAMPLES: [string, string][] = [
  ["DB00682", "DB00196"],   // warfarin + fluconazole
  ["DB00641", "DB01211"],   // simvastatin + clarithromycin
  ["DB00331", "DB00682"],   // metformin + warfarin
];

const T = {
  eyebrow: { ru: "DDI-Net 3.0 · Анализатор взаимодействий", en: "DDI-Net 3.0 · Interaction Analyzer" },
  title: { ru: "Что известно о сочетании двух препаратов", en: "What is known about a combination of two drugs" },
  lede: {
    ru: "Сначала — что записано в источниках. Затем — какие известные свойства препаратов могли бы это объяснить. И отдельно — что видит исследовательская модель. Каждое утверждение помечено: источник, гипотеза или модель.",
    en: "First, what the sources record. Then, which known properties of the drugs could explain it. And separately, what the research model sees. Every statement is labelled: source, hypothesis or model.",
  },
  drugA: { ru: "Препарат A", en: "Drug A" },
  drugB: { ru: "Препарат B", en: "Drug B" },
  examples: { ru: "Примеры", en: "Examples" },
  swap: { ru: "Поменять местами", en: "Swap" },
  simple: { ru: "Простой режим", en: "Simple mode" },
  research: { ru: "Исследовательский режим", en: "Research mode" },
  same: { ru: "Выберите два разных препарата.", en: "Choose two different drugs." },
  explore: { ru: "Открыть граф механизмов →", en: "Open the mechanism graph →" },
  v2: { ru: "Страница оценки модели (v2) →", en: "Model score page (v2) →" },
  pathways: { ru: "Общие биологические пути (Reactome)", en: "Shared biological pathways (Reactome)" },
  pathwaysNote: { ru: "Сначала пути через общий белок, затем самые узкие. Общий путь — фон, а не причина взаимодействия.", en: "Pathways through a shared protein first, then the most specific. A shared pathway is background, not a cause." },
  limits: { ru: "Ограничения этого отчёта", en: "Limitations of this report" },
  biology: { ru: "Белки каждого препарата (статические данные)", en: "Each drug's proteins (static data)" },
  method: { ru: "Как составлен текст", en: "How the text is produced" },
} satisfies Record<string, Bi>;

export function Analyzer({ pair, setPair, setView }: {
  pair: [string, string]; setPair: (p: [string, string]) => void; setView: (v: View) => void;
}) {
  const { lang } = useI18n();
  const [a, b] = pair;
  const [dataset, setDataset] = useState<Drug[] | null>(null);
  const [mode, setMode] = useState<"simple" | "research">(() => {
    try { return localStorage.getItem("ddinet.mode") === "research" ? "research" : "simple"; } catch { return "simple"; }
  });
  const [state, setState] = useState<Remote<PairReport>>(apiConfigured() ? { kind: "loading" } : { kind: "unconfigured" });

  useEffect(() => {
    let live = true;
    loadDrugs().then((d) => live && setDataset(d.drugs)).catch(() => live && setDataset([]));
    return () => { live = false; };
  }, []);

  useEffect(() => { try { localStorage.setItem("ddinet.mode", mode); } catch { /* non-fatal */ } }, [mode]);

  useEffect(() => {
    if (!apiConfigured() || a === b) return;
    const ctl = new AbortController();
    setState({ kind: "loading" });
    fetchReport(a, b, ctl.signal)
      .then(setState)
      .catch((e) => { if (!(e instanceof DOMException && e.name === "AbortError")) setState({ kind: "error", message: String(e) }); });
    return () => ctl.abort();
  }, [a, b]);

  const byId = useMemo(() => new Map((dataset ?? []).map((d) => [d.id, d])), [dataset]);
  const label = (id: string) => nameOf(byId.get(id), lang) ?? id;
  const report = state.kind === "ok" ? state.data : null;
  const refs = useMemo(() => (report ? buildRefIndex(report) : undefined), [report]);
  // The export uses the very response on screen, with its recorded provenance.
  const exportInput = useMemo<ExportInput | null>(
    () => (state.kind === "ok" && a !== b ? { kind: "pair", origin: "analyzer", report: { data: state.data, meta: state.meta } } : null),
    [state, a, b],
  );

  return (
    <section className="section" style={{ paddingTop: "16vh" }}>
      <div className="wrap">
        <span className="eyebrow">{pick(T.eyebrow, lang)}</span>
        <h1 style={{ marginTop: 18, maxInlineSize: "18ch", fontSize: "clamp(30px, 5vw, 64px)" }}>{pick(T.title, lang)}</h1>
        <p style={{ marginTop: 18, maxWidth: 720 }}>{pick(T.lede, lang)}</p>

        <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr", gap: 14, marginTop: 36, alignItems: "stretch" }} className="collapse">
          <DrugPicker label={pick(T.drugA, lang)} value={a} onChange={(v) => setPair([v, b])} dataset={dataset} accent="var(--blue)" />
          <button onClick={() => setPair([b, a])} aria-label={pick(T.swap, lang)} title={pick(T.swap, lang)}
            style={{ alignSelf: "center", background: "none", border: "1px solid var(--border-strong)", color: "var(--text-2)", borderRadius: 20, padding: "8px 12px", cursor: "pointer", fontSize: 16 }}>⇄</button>
          <DrugPicker label={pick(T.drugB, lang)} value={b} onChange={(v) => setPair([a, v])} dataset={dataset} accent="var(--cyan)" />
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", gap: 16, marginTop: 18, flexWrap: "wrap", alignItems: "center" }}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <span className="eyebrow">{pick(T.examples, lang)}</span>
            {EXAMPLES.map(([x, y]) => (
              <button key={x + y} onClick={() => setPair([x, y])}
                style={{ background: "none", border: "1px solid var(--border-strong)", color: "var(--text-2)", borderRadius: 16, padding: "4px 12px", fontSize: 12, cursor: "pointer", fontFamily: "var(--font-ui)" }}>
                {label(x)} + {label(y)}
              </button>
            ))}
          </div>
          <div className="v3-toggle" role="group" aria-label="mode">
            <button aria-pressed={mode === "simple"} onClick={() => setMode("simple")}>{pick(T.simple, lang)}</button>
            <button aria-pressed={mode === "research"} onClick={() => setMode("research")}>{pick(T.research, lang)}</button>
          </div>
        </div>

        <div style={{ marginTop: 22 }}>
          <ExportReport input={exportInput} id="export-analyzer" />
        </div>

        <div style={{ marginTop: 26, display: "flex", flexDirection: "column", gap: 22 }}>
          {a === b ? (
            <p style={{ color: "var(--ev-missing)" }}>{pick(T.same, lang)}</p>
          ) : !report ? (
            <RemoteNotice state={state} />
          ) : (
            <>
              <StatusBanner report={report} />
              <div style={{ display: "grid", gridTemplateColumns: mode === "research" ? "minmax(0, 1.5fr) minmax(0, 1fr)" : "minmax(0, 1fr)", gap: 22, alignItems: "start" }} className="collapse">
                <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
                  <ExplanationView report={report} refs={refs} />
                  <EvidenceList report={report} research={mode === "research"} groups={refs?.groups} />
                </div>
                {mode === "research" && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
                    <ModelPanelV3 model={report.model} />
                    <SourcesChecked checks={report.sources_checked} />
                  </div>
                )}
              </div>
              {mode === "research" && <MechanismTable report={report} nameOf={label} />}
              {mode === "research" && report.mechanism.shared_pathways.length > 0 && <Pathways report={report} />}
              {mode === "simple" && <SourcesChecked checks={report.sources_checked} detail={false} />}
              <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
                <button onClick={() => setView("mechanisms")} className="mono" style={linkBtn}>{pick(T.explore, lang)}</button>
                {mode === "research" && <button onClick={() => setView("analyze")} className="mono" style={linkBtn}>{pick(T.v2, lang)}</button>}
              </div>
              <details className="v3-card">
                <summary className="mono" style={{ cursor: "pointer", fontSize: 12, color: "var(--cyan)" }}>{pick(T.limits, lang)}</summary>
                <ul style={{ margin: "12px 0 0", paddingLeft: 18, fontSize: 13.5, color: "var(--text-2)", lineHeight: 1.7 }}>
                  {report.limitations.map((l, i) => <li key={i}>{pick(l, lang)}</li>)}
                </ul>
                <p className="mono" style={{ marginTop: 12, fontSize: 11, color: "var(--text-3)" }}>{pick(T.method, lang)}: {report.explanation.method}</p>
              </details>
              <p style={{ fontSize: 13, color: "var(--amber)" }}>{pick(report.disclaimer, lang)}</p>
            </>
          )}

          {(mode === "research" || !report) && a !== b && (
            <div>
              <span className="eyebrow">{pick(T.biology, lang)}</span>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18, marginTop: 12 }} className="collapse">
                <BiologyPanel drug={byId.get(a)} accent="var(--blue)" />
                <BiologyPanel drug={byId.get(b)} accent="var(--cyan)" />
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function Pathways({ report }: { report: PairReport }) {
  const { lang } = useI18n();
  const m = report.mechanism;
  return (
    <div id="pathways-block" className="v3-card" style={{ scrollMarginTop: 120 }}>
      <h3 style={{ fontSize: 18 }}>{pick(T.pathways, lang)} · {m.n_shared_pathways_total}</h3>
      <p style={{ fontSize: 12.5, marginTop: 6 }}>{pick(T.pathwaysNote, lang)}</p>
      <ul style={{ listStyle: "none", margin: "12px 0 0", padding: 0, display: "flex", flexDirection: "column", gap: 8 }}>
        {m.shared_pathways.map((p) => (
          <li key={p.id} style={{ fontSize: 13 }}>
            <a href={`https://reactome.org/content/detail/${p.id}`} target="_blank" rel="noreferrer noopener">{p.name}</a>{" "}
            <span className="mono" style={{ fontSize: 10.5, color: "var(--text-3)" }}>{p.id} · n={p.n_proteins_in_pathway} · A: {p.via_a.join(", ")} · B: {p.via_b.join(", ")}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

const linkBtn: React.CSSProperties = { background: "none", border: "none", color: "var(--cyan)", cursor: "pointer", fontSize: 12.5, padding: 0 };
