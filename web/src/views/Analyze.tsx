// Pair analysis. The biology shown here is real, read from the frozen dataset.
// The prediction slot is deliberately empty: no trained checkpoint is installed
// on this deployment, and an empty slot is honest where a placeholder number
// would not be. Nothing on this page is a clinical recommendation.
import { useEffect, useMemo, useState } from "react";
import { DrugPicker, nameOf } from "../components/DrugPicker";
import { BiologyPanel } from "../components/BiologyPanel";
import { Badge } from "../components/Badge";
import { frozen } from "../data/frozen";
import { loadDrugs, type Drug } from "../data/drugs";
import { count } from "../lib/format";
import { useI18n } from "../i18n";
import { PredictionPanel } from "../components/PredictionPanel";
import { Explainer } from "../components/Explainer";
import { SharedBiologyPanel } from "../components/SharedBiologyPanel";
import { analyzePair, apiConfigured, type AnalyzeState } from "../data/analyze";

// Six real high-degree DrugBank IDs from the frozen extract, used as quick
// picks. The DrugBank ID is the canonical identifier; the name beside it comes
// from the DrugCentral INN join and may be absent.
const QUICK = ["DB00006", "DB00014", "DB00252", "DB00285", "DB00564", "DB01174"];

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

        <Explainer />

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

            {analysis.kind === "ok" && (
              <SharedBiologyPanel
                data={analysis.data}
                nameA={nameOf(drugA, lang) ?? a}
                nameB={nameOf(drugB, lang) ?? b}
              />
            )}

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
