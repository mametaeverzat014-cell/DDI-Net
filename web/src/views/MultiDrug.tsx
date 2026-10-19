// DDI-Net 3.0 — Multi-Drug Explorer (research mode).
//
// Up to eight drugs; every unique pair is examined on its own and drawn as a
// network. The page states, above the results and not in a footnote, that
// pairwise findings say nothing about three or more drugs together: no such
// model exists here, and a list of pairwise results is easily misread as one.
import { useEffect, useMemo, useState } from "react";
import type { View } from "../App";
import { nameOf } from "../components/DrugPicker";
import { loadDrugs, matchesQuery, type Drug } from "../data/drugs";
import { apiConfigured } from "../data/analyze";
import { fetchMulti, MAX_MULTI, type MultiPair, type MultiReport, type Remote } from "../data/v3";
import { fmtCalibrated } from "../data/scoreFormat";
import { useI18n, pick, type Bi } from "../i18n";
import { RemoteNotice, SourcesChecked } from "../components/v3/ReportParts";
import { REVIEW_REASON, STATUS_TIER } from "../components/v3/evidenceStyle";
import { ExportReport } from "../components/v3/ExportReport";
import { MultiOutcomes } from "../components/v3/MultiOutcomes";
import type { ExportInput } from "../pdf/types";

const T = {
  eyebrow: { ru: "DDI-Net 3.0 · Несколько препаратов", en: "DDI-Net 3.0 · Multiple drugs" },
  title: { ru: "Все пары из списка препаратов", en: "Every pair in a list of drugs" },
  lede: {
    ru: "Добавьте от двух до восьми препаратов. Для каждой пары собираются те же источники, что в анализаторе, а пары, которые стоит изучить подробнее, поднимаются наверх.",
    en: "Add two to eight drugs. Each pair is checked against the same sources as the Analyzer, and pairs worth a closer look rise to the top.",
  },
  add: { ru: "Добавить препарат", en: "Add a drug" },
  run: { ru: "Проверить пары", en: "Check pairs" },
  remove: { ru: "убрать", en: "remove" },
  max: { ru: `Не больше ${MAX_MULTI} препаратов.`, en: `At most ${MAX_MULTI} drugs.` },
  pair: { ru: "Пара", en: "Pair" },
  status: { ru: "Что найдено", en: "What was found" },
  reasons: { ru: "Почему стоит посмотреть", en: "Why look closer" },
  score: { ru: "Модель", en: "Model" },
  open: { ru: "открыть", en: "open" },
  review: { ru: "стоит изучить", en: "worth a look" },
  nothing: { ru: "ничего не найдено — не означает «безопасно»", en: "nothing found — does not mean 'safe'" },
  abstain: { ru: "не учитывается", en: "not counted" },
} satisfies Record<string, Bi>;

const STATUS_ORDER = [
  "contraindication_in_label", "warning_in_label", "conflicting_evidence", "documented_no_severity",
  "model_signal_only", "no_documented_evidence_found",
] as const;

export function MultiDrug({ setPair, setView }: { setPair: (p: [string, string]) => void; setView: (v: View) => void }) {
  const { lang } = useI18n();
  const [dataset, setDataset] = useState<Drug[] | null>(null);
  const [list, setList] = useState<string[]>(["DB00682", "DB00196", "DB00641", "DB01211"]);
  const [q, setQ] = useState("");
  const [state, setState] = useState<Remote<MultiReport> | null>(apiConfigured() ? null : { kind: "unconfigured" });

  useEffect(() => {
    let live = true;
    loadDrugs().then((d) => live && setDataset(d.drugs)).catch(() => live && setDataset([]));
    return () => { live = false; };
  }, []);

  const byId = useMemo(() => new Map((dataset ?? []).map((d) => [d.id, d])), [dataset]);
  const label = (id: string) => nameOf(byId.get(id), lang) ?? id;
  const matches = useMemo(() => (dataset && q.trim() ? dataset.filter((d) => matchesQuery(d, q) && !list.includes(d.id)).slice(0, 6) : []), [q, dataset, list]);

  const add = (id: string) => { if (list.length < MAX_MULTI && !list.includes(id)) setList([...list, id]); setQ(""); };
  const run = () => {
    if (!apiConfigured()) return;
    setState({ kind: "loading" });
    fetchMulti(list).then(setState).catch((e) => setState({ kind: "error", message: String(e) }));
  };

  const report = state?.kind === "ok" ? state.data : null;
  const exportInput = useMemo<ExportInput | null>(
    () => (state?.kind === "ok" ? { kind: "multi", report: { data: state.data, meta: state.meta } } : null),
    [state],
  );
  const pairs = useMemo(() => report ? [...report.pairs].sort((x, y) =>
    Number(y.needs_review) - Number(x.needs_review) ||
    STATUS_ORDER.indexOf(x.evidence_status) - STATUS_ORDER.indexOf(y.evidence_status)) : [], [report]);

  return (
    <section className="section" style={{ paddingTop: "16vh" }}>
      <div className="wrap">
        <span className="eyebrow">{pick(T.eyebrow, lang)}</span>
        <h1 style={{ marginTop: 18, maxInlineSize: "18ch", fontSize: "clamp(30px, 5vw, 64px)" }}>{pick(T.title, lang)}</h1>
        <p style={{ marginTop: 18, maxWidth: 720 }}>{pick(T.lede, lang)}</p>

        <div className="v3-card" style={{ marginTop: 30 }}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {list.map((id) => (
              <span key={id} style={{ display: "inline-flex", alignItems: "center", gap: 8, border: "1px solid var(--border-strong)", borderRadius: 18, padding: "5px 6px 5px 12px", fontSize: 13 }}>
                {label(id)} <span className="mono" style={{ fontSize: 10.5, color: "var(--text-3)" }}>{id}</span>
                <button onClick={() => setList(list.filter((x) => x !== id))} aria-label={`${pick(T.remove, lang)} ${label(id)}`}
                  style={{ background: "none", border: "none", color: "var(--text-3)", cursor: "pointer", fontSize: 14 }}>×</button>
              </span>
            ))}
          </div>
          <div style={{ display: "flex", gap: 10, marginTop: 14, flexWrap: "wrap", alignItems: "flex-start" }}>
            <div style={{ flex: "1 1 260px" }}>
              <input value={q} onChange={(e) => setQ(e.target.value)} disabled={list.length >= MAX_MULTI || !dataset}
                onKeyDown={(e) => { if (e.key === "Enter" && matches[0]) add(matches[0].id); }}
                placeholder={list.length >= MAX_MULTI ? pick(T.max, lang) : pick(T.add, lang)} aria-label={pick(T.add, lang)}
                style={{ width: "100%", background: "rgba(0,0,0,0.25)", border: "1px solid var(--border-strong)", borderRadius: 6, color: "var(--text)", padding: "9px 11px", fontSize: 13, fontFamily: "var(--font-ui)" }} />
              {matches.length > 0 && (
                <div style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 2 }}>
                  {matches.map((d) => (
                    <button key={d.id} onClick={() => add(d.id)} style={{ textAlign: "left", background: "none", border: "none", color: "var(--text-2)", padding: "4px 6px", fontSize: 12.5, cursor: "pointer", fontFamily: "var(--font-ui)" }}>
                      {nameOf(d, lang) ?? d.id} <span className="mono" style={{ color: "var(--cyan)", fontSize: 11 }}>{d.id}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <button onClick={run} disabled={list.length < 2 || !apiConfigured()}
              style={{ background: "var(--cyan)", color: "#04121f", border: "none", borderRadius: 8, padding: "10px 18px", fontWeight: 700, cursor: list.length < 2 ? "not-allowed" : "pointer", opacity: list.length < 2 ? 0.5 : 1, fontFamily: "var(--font-ui)" }}>
              {pick(T.run, lang)} · {(list.length * (list.length - 1)) / 2}
            </button>
          </div>
        </div>

        <div style={{ marginTop: 18 }}>
          <ExportReport input={exportInput} id="export-multi" />
        </div>

        <div style={{ marginTop: 22, display: "flex", flexDirection: "column", gap: 22 }}>
          {state && !report && <RemoteNotice state={state} />}
          {report && (
            <>
              <div className="v3-card" role="note" style={{ borderColor: "rgba(255,196,120,0.45)", borderLeftWidth: 4 }}>
                <p style={{ color: "var(--text)", fontSize: 15 }}>{pick(report.scope_note, lang)}</p>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 0.85fr) minmax(0, 1.5fr)", gap: 22, alignItems: "start" }} className="collapse">
                <Network report={report} label={label} onPick={(p) => { setPair([p.drug_a, p.drug_b]); setView("analyzer"); }} />
                <PairTable pairs={pairs} label={label} onPick={(p) => { setPair([p.drug_a, p.drug_b]); setView("analyzer"); }} />
              </div>
              <MultiOutcomes report={report} label={label} onPick={(p) => { setPair([p.drug_a, p.drug_b]); setView("analyzer"); }} />
              <SourcesChecked checks={report.sources_checked} detail={false} />
              <p style={{ fontSize: 13, color: "var(--amber)" }}>{pick(report.disclaimer, lang)}</p>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

function Network({ report, label, onPick }: { report: MultiReport; label: (id: string) => string; onPick: (p: MultiPair) => void }) {
  const { lang } = useI18n();
  const S = 420, R = 150, C = S / 2;
  const pos = new Map(report.drugs.map((d, i) => {
    const ang = -Math.PI / 2 + (2 * Math.PI * i) / report.drugs.length;
    return [d.id, { x: C + R * Math.cos(ang), y: C + R * Math.sin(ang), ang }];
  }));
  return (
    <div className="v3-card" style={{ padding: 10 }}>
      <svg viewBox={`-90 0 ${S + 180} ${S}`} width="100%" role="group" aria-label="pairwise network">
        {report.pairs.map((p) => {
          const a = pos.get(p.drug_a)!, b = pos.get(p.drug_b)!;
          const tier = STATUS_TIER[p.evidence_status];
          const none = p.evidence_status === "no_documented_evidence_found";
          const modelOnly = p.evidence_status === "model_signal_only";
          return (
            <line key={p.drug_a + p.drug_b} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={tier.color}
              strokeWidth={none ? 1.4 : p.needs_review ? 3.2 : 2} strokeDasharray={none ? "2 5" : modelOnly ? "6 4" : undefined}
              opacity={none ? 0.55 : 0.9} style={{ cursor: "pointer" }} onClick={() => onPick(p)}>
              <title>{label(p.drug_a)} + {label(p.drug_b)}: {pick(tier.label, lang)}</title>
            </line>
          );
        })}
        {report.drugs.map((d) => {
          const p = pos.get(d.id)!;
          const right = Math.cos(p.ang) >= 0;
          return (
            <g key={d.id} transform={`translate(${p.x}, ${p.y})`}>
              <circle r={11} fill="rgba(6,16,31,0.95)" stroke="var(--cyan)" strokeWidth={2} />
              <text x={right ? 17 : -17} y={6} textAnchor={right ? "start" : "end"} fill="var(--text)" fontSize={18}>{label(d.id)}</text>
            </g>
          );
        })}
      </svg>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 14px", padding: "6px 8px", fontSize: 11.5, color: "var(--text-3)" }}>
        {STATUS_ORDER.map((s) => (
          <span key={s} style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
            <span style={{ width: 16, height: 0, borderTop: `2px ${s === "no_documented_evidence_found" ? "dotted" : s === "model_signal_only" ? "dashed" : "solid"} ${STATUS_TIER[s].color}`, display: "inline-block" }} />
            {pick(STATUS_TIER[s].label, lang)}
          </span>
        ))}
      </div>
    </div>
  );
}

function PairTable({ pairs, label, onPick }: { pairs: MultiPair[]; label: (id: string) => string; onPick: (p: MultiPair) => void }) {
  const { lang } = useI18n();
  return (
    <div className="v3-card v3-scroll">
      <table className="v3-table">
        <thead><tr><th>{pick(T.pair, lang)}</th><th>{pick(T.status, lang)}</th><th>{pick(T.reasons, lang)}</th><th>{pick(T.score, lang)}</th></tr></thead>
        <tbody>
          {pairs.map((p) => {
            const tier = STATUS_TIER[p.evidence_status];
            return (
              <tr key={p.drug_a + p.drug_b}>
                <td>
                  <button onClick={() => onPick(p)} title={pick(T.open, lang)}
                    style={{ background: "none", border: "none", padding: 0, color: "var(--text)", cursor: "pointer", textAlign: "left", fontFamily: "var(--font-ui)", fontSize: 13 }}>
                    {label(p.drug_a)} + {label(p.drug_b)} <span style={{ color: "var(--cyan)" }}>→</span>
                  </button>
                  {p.needs_review && <div className="mono" style={{ fontSize: 10, color: "var(--cyan)" }}>{pick(T.review, lang)}</div>}
                </td>
                <td><span className="v3-chip" style={{ color: tier.color }}>{pick(tier.label, lang)}</span>
                  {p.evidence_status === "no_documented_evidence_found" && <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 4 }}>{pick(T.nothing, lang)}</div>}
                </td>
                <td style={{ fontSize: 12 }}>{p.review_reasons.map((r) => (REVIEW_REASON[r] ? pick(REVIEW_REASON[r], lang) : r)).join("; ")}</td>
                <td className="mono" style={{ fontSize: 12 }}>{p.calibrated_model_score === null ? (p.training_label_seen ? pick(T.abstain, lang) : "—") : fmtCalibrated(p.calibrated_model_score)}<div style={{ fontSize: 10, color: "var(--text-3)" }}>{p.regime}</div></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
