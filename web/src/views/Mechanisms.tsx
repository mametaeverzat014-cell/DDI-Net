// DDI-Net 3.0 — Biological Mechanism Explorer.
//
// The same pair as the Analyzer, drawn as a graph of documented relations.
// What the page deliberately does not do: draw a model-derived edge. Per-protein
// attribution of the frozen model exists only for the 20 pairs the V2 study
// analysed, and attention weights or graph connectivity are not evidence of
// cause. The panel at the bottom says so instead of approximating one.
import { useEffect, useMemo, useState } from "react";
import { DrugPicker, nameOf } from "../components/DrugPicker";
import { loadDrugs, type Drug } from "../data/drugs";
import { apiConfigured } from "../data/analyze";
import { fetchGraph, fetchReport, type MechanismGraph, type PairReport, type Remote } from "../data/v3";
import { useI18n, pick, type Bi } from "../i18n";
import { MechanismGraphView } from "../components/v3/MechanismGraphView";
import { RemoteNotice } from "../components/v3/ReportParts";
import { PATTERN_LABEL } from "../components/v3/evidenceStyle";

const T = {
  eyebrow: { ru: "DDI-Net 3.0 · Биологические механизмы", en: "DDI-Net 3.0 · Biological mechanisms" },
  title: { ru: "Через какие белки могут встречаться два препарата", en: "Which proteins two drugs might meet at" },
  lede: {
    ru: "Каждая линия — задокументированная связь препарата с белком (DrugBank, ChEMBL) или белка с биологическим путём (Reactome). Пунктирное кольцо отмечает белки, на которых строится гипотеза о механизме. Общий белок или путь — повод присмотреться, а не доказательство взаимодействия.",
    en: "Every line is a documented drug–protein relation (DrugBank, ChEMBL) or protein–pathway membership (Reactome). A dashed ring marks proteins a mechanism hypothesis rests on. A shared protein or pathway is a reason to look closer, not proof of an interaction.",
  },
  hyps: { ru: "Гипотезы о механизме для этой пары", en: "Mechanism hypotheses for this pair" },
  none: { ru: "Задокументированные роли не складываются ни в одну из проверяемых конфигураций.", en: "The documented roles form none of the configurations checked." },
  modelTitle: { ru: "Объяснения модели", en: "Model explanations" },
  modelBody: {
    ru: "Для этой пары объяснение со стороны модели не показывается. В замороженном исследовании вклад отдельных белков (удаление по одному) измерен только для 20 пар, а вклад модальностей — только для тестовых пар. Связность графа и веса внимания не доказывают причинность, поэтому мы не рисуем «модельные» связи.",
    en: "No model-side explanation is shown for this pair. The frozen study measured per-protein contribution (leave-one-out) for 20 pairs only, and modality contribution for test pairs only. Graph connectivity and attention weights do not establish causality, so no 'model' links are drawn.",
  },
} satisfies Record<string, Bi>;

export function Mechanisms({ pair, setPair }: { pair: [string, string]; setPair: (p: [string, string]) => void }) {
  const { lang } = useI18n();
  const [a, b] = pair;
  const [dataset, setDataset] = useState<Drug[] | null>(null);
  const initial = apiConfigured() ? { kind: "loading" as const } : { kind: "unconfigured" as const };
  const [graph, setGraph] = useState<Remote<MechanismGraph>>(initial);
  const [report, setReport] = useState<Remote<PairReport>>(initial);

  useEffect(() => {
    let live = true;
    loadDrugs().then((d) => live && setDataset(d.drugs)).catch(() => live && setDataset([]));
    return () => { live = false; };
  }, []);

  useEffect(() => {
    if (!apiConfigured() || a === b) return;
    const ctl = new AbortController();
    setGraph({ kind: "loading" });
    setReport({ kind: "loading" });
    const fail = (set: (s: Remote<never>) => void) => (e: unknown) => {
      if (!(e instanceof DOMException && e.name === "AbortError")) set({ kind: "error", message: String(e) });
    };
    fetchGraph(a, b, ctl.signal).then(setGraph).catch(fail(setGraph));
    fetchReport(a, b, ctl.signal).then(setReport).catch(fail(setReport));
    return () => ctl.abort();
  }, [a, b]);

  const byId = useMemo(() => new Map((dataset ?? []).map((d) => [d.id, d])), [dataset]);
  const label = (id: string) => nameOf(byId.get(id), lang) ?? id;
  const findings = report.kind === "ok" ? report.data.mechanism.findings : [];

  return (
    <section className="section" style={{ paddingTop: "16vh" }}>
      <div className="wrap">
        <span className="eyebrow">{pick(T.eyebrow, lang)}</span>
        <h1 style={{ marginTop: 18, maxInlineSize: "20ch", fontSize: "clamp(30px, 5vw, 64px)" }}>{pick(T.title, lang)}</h1>
        <p style={{ marginTop: 18, maxWidth: 760 }}>{pick(T.lede, lang)}</p>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginTop: 32 }} className="collapse">
          <DrugPicker label="A" value={a} onChange={(v) => setPair([v, b])} dataset={dataset} accent="var(--blue)" />
          <DrugPicker label="B" value={b} onChange={(v) => setPair([a, v])} dataset={dataset} accent="var(--cyan)" />
        </div>

        <div style={{ marginTop: 28 }}>
          {graph.kind === "ok" ? (
            <MechanismGraphView graph={graph.data} findings={findings} nameOf={label} />
          ) : (
            <RemoteNotice state={graph} />
          )}
        </div>

        {report.kind === "ok" && (
          <div className="v3-card" style={{ marginTop: 22 }}>
            <h3 style={{ fontSize: 18 }}>{pick(T.hyps, lang)}</h3>
            {findings.filter((f) => f.pattern !== "shared_annotation").length === 0 ? (
              <p style={{ marginTop: 8, fontSize: 13.5 }}>{pick(T.none, lang)}</p>
            ) : (
              <ul style={{ margin: "10px 0 0", paddingLeft: 18, fontSize: 13.5, color: "var(--text-2)", lineHeight: 1.7 }}>
                {findings.filter((f) => f.pattern !== "shared_annotation").map((f) => (
                  <li key={f.id}>
                    <span className="mono" style={{ color: "var(--ev-hypothesis)" }}>{f.protein.gene}</span> — {pick(PATTERN_LABEL[f.pattern], lang)}
                    {f.actor_drug_id ? ` (${label(f.actor_drug_id)} → ${label(f.affected_drug_id ?? "")})` : ""}
                  </li>
                ))}
              </ul>
            )}
            <p style={{ marginTop: 10, fontSize: 12.5, color: "var(--text-3)" }}>{pick(report.data.mechanism.note, lang)}</p>
          </div>
        )}

        <div className="v3-card" style={{ marginTop: 22, borderColor: "rgba(159,179,204,0.3)" }}>
          <span className="eyebrow" style={{ color: "var(--ev-model)" }}>{pick(T.modelTitle, lang)}</span>
          <p style={{ marginTop: 10, fontSize: 13.5 }}>{pick(T.modelBody, lang)}</p>
        </div>
      </div>
    </section>
  );
}
