// Building blocks of the DDI-Net 3.0 pair report.
//
// Layout rule: documentation, hypotheses and the model never share a box. The
// status banner names the strongest KIND of documentation found and says in so
// many words that it is not a severity; the explanation tags every sentence
// with its kind; sources are numbered so every sentence can be traced.
import { useI18n, pick, type Bi } from "../../i18n";
import type {
  EvidenceRecord, MechanismFinding, ModelBlock, PairReport, Remote, ResolveOut, SourceCheck,
} from "../../data/v3";
import {
  CATEGORY_LABEL, KIND_TIER, PATTERN_LABEL, RELATION_LABEL, ROLE_LABEL, SOURCE_NAME, SOURCE_STATUS, STATUS_TIER,
} from "./evidenceStyle";
import { buildRefIndex, scrollToAnchor, type RefIndex } from "./refs";
import { RelianceBars } from "./RelianceBars";

const T = {
  notSeverity: { ru: "Это вид найденной документации, а не степень опасности.", en: "This is the kind of documentation found, not a level of danger." },
  sources: { ru: "Источники", en: "Sources" },
  original: { ru: "Оригинал источника", en: "Source original" },
  translation: { ru: "Перевод проекта", en: "Project translation" },
  template: { ru: "Шаблон DrugBank", en: "DrugBank template" },
  directionNeutral: { ru: "направление не подтверждено", en: "direction not verified" },
  retrieved: { ru: "получено", en: "retrieved" },
  openSource: { ru: "Открыть источник", en: "Open source" },
  checked: { ru: "Проверенные источники", en: "Sources checked" },
  qualifiers: { ru: "Оговорки источника", en: "Qualifiers" },
  ids: { ru: "Идентификаторы", en: "Identifiers" },
  hyp: { ru: "Гипотезы о механизме", en: "Mechanism hypotheses" },
  protein: { ru: "Белок", en: "Protein" },
  pattern: { ru: "Конфигурация", en: "Configuration" },
  roles: { ru: "Роли (A / B)", en: "Roles (A / B)" },
  evidenceCol: { ru: "Основание", en: "Basis" },
  consistent: { ru: "согласуется с записью", en: "consistent with record" },
  general: { ru: "Общее описание семейства белков (текст проекта)", en: "General description of the protein family (project text)" },
  modelTitle: { ru: "Исследовательская модель BIO-GINE", en: "BIO-GINE research model" },
  calibrated: { ru: "калиброванная оценка", en: "calibrated score" },
  raw: { ru: "сырая оценка", en: "raw score" },
  regime: { ru: "режим", en: "regime" },
  split: { ru: "разбиение (сид 0)", en: "split (seed 0)" },
  measured: { ru: "Измеренное качество для этого режима", en: "Measured quality for this regime" },
  abstain: { ru: "Оценка не учитывается: модель обучалась на этой записи.", en: "Score not counted: the model was trained on this record." },
  unavailable: { ru: "Модель недоступна", en: "Model unavailable" },
} satisfies Record<string, Bi>;

// ---------------------------------------------------------------- banner ----
export function StatusBanner({ report }: { report: PairReport }) {
  const { lang } = useI18n();
  const tier = STATUS_TIER[report.evidence_status];
  return (
    <div className="v3-card v3-in" role="status" style={{ borderColor: tier.color, borderLeftWidth: 4, display: "flex", flexDirection: "column", gap: 8 }}>
      <span className="v3-chip" style={{ color: tier.color, alignSelf: "flex-start" }}>{pick(tier.label, lang)}</span>
      <p style={{ color: "var(--text)", fontSize: 17, lineHeight: 1.5 }}>{pick(report.evidence_status_label, lang)}</p>
      <p style={{ fontSize: 13 }}>{pick(tier.hint, lang)}</p>
      <p className="mono" style={{ fontSize: 11, color: "var(--text-3)" }}>{pick(T.notSeverity, lang)}</p>
    </div>
  );
}

// ----------------------------------------------------------- explanation ----
export function ExplanationView({ report, refs }: { report: PairReport; refs?: RefIndex }) {
  const { lang } = useI18n();
  const index = refs ?? buildRefIndex(report);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {report.explanation.sections.map((sec, si) => (
        <section key={sec.id} className="v3-card v3-in" style={{ animationDelay: `${si * 60}ms` }} aria-labelledby={`sec-${sec.id}`}>
          <h3 id={`sec-${sec.id}`} style={{ fontSize: 19, marginBottom: 14 }}>{pick(sec.title, lang)}</h3>
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 12 }}>
            {sec.statements.map((st, i) => {
              const tier = KIND_TIER[st.kind];
              const labels = Array.from(new Map(st.refs.map((r) => index.label(r)).filter((x): x is NonNullable<typeof x> => !!x).map((x) => [x.label, x])).values());
              return (
                <li key={i} style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: 12, alignItems: "baseline" }}>
                  <span className="v3-chip" title={pick(tier.hint, lang)} style={{ color: tier.color, minWidth: 92, justifyContent: "center" }}>{pick(tier.label, lang)}</span>
                  <p style={{ fontSize: 14.5, color: st.kind === "caveat" ? "var(--text-3)" : "var(--text-2)" }}>
                    {pick(st.text, lang)}
                    {labels.map((l) => (
                      <button key={l.label} className="v3-ref" onClick={() => l.anchor && scrollToAnchor(l.anchor)} aria-label={`→ ${l.label}`}>{l.label}</button>
                    ))}
                  </p>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}

// --------------------------------------------------------------- sources ----
export function EvidenceList({ report, research }: { report: PairReport; research: boolean }) {
  const { lang } = useI18n();
  if (report.evidence.length === 0) return null;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <span className="eyebrow">{pick(T.sources, lang)} · {report.evidence.length}</span>
      {report.evidence.map((e, i) => <EvidenceCard key={e.id} e={e} n={i + 1} research={research} />)}
    </div>
  );
}

function EvidenceCard({ e, n, research }: { e: EvidenceRecord; n: number; research: boolean }) {
  const { lang } = useI18n();
  const cat = CATEGORY_LABEL[e.category];
  const showRu = lang === "ru" && e.statement_ru;
  return (
    <article id={`ev-${n}`} className="v3-card" style={{ borderLeft: `3px solid ${cat.color}`, scrollMarginTop: 120 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        <span style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <span className="mono" style={{ fontSize: 12, color: "var(--text-3)" }}>[{n}]</span>
          <span className="v3-chip" style={{ color: cat.color }}>{pick(cat, lang)}</span>
          {e.direction === "not_verified" && <span className="v3-chip" style={{ color: "var(--ev-missing)" }}>{pick(T.directionNeutral, lang)}</span>}
        </span>
        <span className="mono" style={{ fontSize: 10.5, color: "var(--text-3)" }}>{pick(T.retrieved, lang)} {e.retrieved_at}</span>
      </div>
      {showRu && (
        <p style={{ marginTop: 12, fontSize: 14.5, color: "var(--text)" }}>
          {e.statement_ru} <span className="mono" style={{ fontSize: 10, color: "var(--text-3)" }}>· {pick(T.translation, lang)}</span>
        </p>
      )}
      <blockquote lang="en" style={{ margin: "10px 0 0", padding: "8px 12px", borderLeft: "2px solid var(--border-strong)", color: showRu ? "var(--text-2)" : "var(--text)", fontSize: showRu ? 13 : 14.5, lineHeight: 1.6 }}>
        {e.statement}
        {showRu && <span className="mono" style={{ display: "block", marginTop: 4, fontSize: 10, color: "var(--text-3)" }}>{pick(T.original, lang)}</span>}
      </blockquote>
      <div className="mono" style={{ marginTop: 10, fontSize: 11, color: "var(--text-3)", lineHeight: 1.8 }}>
        {e.source_name}{e.source_version ? ` · ${e.source_version}` : ""}{e.section ? ` · ${e.section}` : ""}
        {e.source_url && <> · <a href={e.source_url} target="_blank" rel="noreferrer noopener">{pick(T.openSource, lang)} ↗</a></>}
      </div>
      {research && (
        <details style={{ marginTop: 10 }}>
          <summary className="mono" style={{ cursor: "pointer", fontSize: 11, color: "var(--cyan)" }}>{pick(T.qualifiers, lang)} · {pick(T.ids, lang)}</summary>
          <ul style={{ margin: "8px 0 0", paddingLeft: 18, color: "var(--text-3)", fontSize: 12.5, lineHeight: 1.6 }}>
            {e.qualifiers.map((q) => <li key={q}>{q}</li>)}
          </ul>
          {e.source_template && <p className="mono" style={{ marginTop: 8, fontSize: 11, color: "var(--text-3)" }}>{pick(T.template, lang)}: {e.source_template}</p>}
          <div className="mono" style={{ marginTop: 8, fontSize: 10.5, color: "var(--text-3)", wordBreak: "break-all", lineHeight: 1.8 }}>
            {Object.entries(e.original_identifiers).map(([k, v]) => <div key={k}>{k}: {v}</div>)}
            {e.license && <div>license: {e.license}</div>}
          </div>
        </details>
      )}
    </article>
  );
}

export function SourcesChecked({ checks, detail = true }: { checks: SourceCheck[]; detail?: boolean }) {
  const { lang } = useI18n();
  return (
    <div className="v3-card" style={{ padding: 16 }}>
      <span className="eyebrow">{pick(T.checked, lang)}</span>
      <ul style={{ listStyle: "none", margin: "10px 0 0", padding: 0, display: "flex", flexDirection: "column", gap: 6 }}>
        {checks.map((c) => {
          const bad = c.status === "unavailable" || c.status === "disabled";
          return (
            <li key={c.source} style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "baseline", fontSize: 13 }}>
              <span style={{ color: "var(--text)" }}>{SOURCE_NAME[c.source] ? pick(SOURCE_NAME[c.source], lang) : c.source}</span>
              <span className="mono" style={{ fontSize: 11, color: bad ? "var(--ev-missing)" : "var(--text-3)" }}>{SOURCE_STATUS[c.status] ? pick(SOURCE_STATUS[c.status], lang) : c.status}</span>
              {detail && c.detail && <span style={{ fontSize: 11.5, color: "var(--text-3)" }}>{c.detail}</span>}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// ------------------------------------------------------------- mechanism ----
export function MechanismTable({ report, nameOf }: { report: PairReport; nameOf: (id: string) => string }) {
  const { lang } = useI18n();
  const m = report.mechanism;
  if (m.findings.length === 0) return null;
  const rolesText = (r: string[]) => r.map((x) => (ROLE_LABEL[x] ? pick(ROLE_LABEL[x], lang) : x)).join(", ");
  return (
    <div className="v3-card">
      <h3 style={{ fontSize: 18 }}>{pick(T.hyp, lang)}</h3>
      <p style={{ fontSize: 13, marginTop: 8 }}>{pick(m.note, lang)}</p>
      <div className="v3-scroll" style={{ marginTop: 14 }}>
        <table className="v3-table">
          <thead><tr>
            <th>#</th><th>{pick(T.protein, lang)}</th><th>{pick(T.pattern, lang)}</th><th>{pick(T.roles, lang)}</th><th>{pick(T.evidenceCol, lang)}</th>
          </tr></thead>
          <tbody>
            {m.findings.map((f, i) => <FindingRow key={f.id} f={f} n={i + 1} report={report} nameOf={nameOf} rolesText={rolesText} />)}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FindingRow({ f, n, report, nameOf, rolesText }: {
  f: MechanismFinding; n: number; report: PairReport; nameOf: (id: string) => string; rolesText: (r: string[]) => string;
}) {
  const { lang } = useI18n();
  const pmids = Array.from(new Set(f.annotation_ids.flatMap((id) => report.mechanism.annotations[id]?.pmids ?? []))).slice(0, 6);
  const sources = Array.from(new Set(f.annotation_ids.map((id) => report.mechanism.annotations[id]?.source_name).filter(Boolean)));
  return (
    <tr id={`hyp-${n}`} style={{ scrollMarginTop: 120 }}>
      <td className="mono">H{n}</td>
      <td>
        <span className="mono" style={{ color: "var(--ev-hypothesis)" }}>{f.protein.gene}</span>{" "}
        <span style={{ color: "var(--text-3)" }}>· {pick(RELATION_LABEL[f.relation], lang)}</span>
        <div style={{ fontSize: 11.5, color: "var(--text-3)", marginTop: 3 }}>{f.protein.name} · {f.protein.uniprot}</div>
      </td>
      <td>
        {pick(PATTERN_LABEL[f.pattern], lang)}
        {f.actor_drug_id && <div style={{ fontSize: 11.5, color: "var(--text-3)", marginTop: 3 }}>{nameOf(f.actor_drug_id)} → {nameOf(f.affected_drug_id ?? "")}</div>}
        {f.consistent_with_records.length > 0 && <div className="mono" style={{ fontSize: 10.5, color: "var(--ev-documented)", marginTop: 3 }}>{pick(T.consistent, lang)}</div>}
      </td>
      <td>{rolesText(f.roles_a)} / {rolesText(f.roles_b)}</td>
      <td>
        <div style={{ fontSize: 11.5 }}>{sources.join("; ")}</div>
        <div className="mono" style={{ fontSize: 10.5, marginTop: 3, display: "flex", gap: 6, flexWrap: "wrap" }}>
          {pmids.map((p) => <a key={p} href={`https://pubmed.ncbi.nlm.nih.gov/${p}/`} target="_blank" rel="noreferrer noopener">PMID {p}</a>)}
        </div>
      </td>
    </tr>
  );
}

// ----------------------------------------------------------------- model ----
export function ModelPanelV3({ model }: { model: ModelBlock }) {
  const { lang } = useI18n();
  return (
    <div id="model-block" className="v3-card" style={{ borderColor: "rgba(159,179,204,0.35)", scrollMarginTop: 120 }}>
      <span className="eyebrow" style={{ color: "var(--ev-model)" }}>{pick(T.modelTitle, lang)}</span>
      {!model.available ? (
        <p style={{ marginTop: 10, fontSize: 13.5 }}>{pick(T.unavailable, lang)}{model.unavailable_reason ? ` — ${model.unavailable_reason}` : ""}</p>
      ) : (
        <>
          <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginTop: 12, flexWrap: "wrap" }}>
            <span className="mono" style={{ fontSize: 34, color: model.abstain ? "var(--text-3)" : "var(--ev-model)", textDecoration: model.abstain ? "line-through" : "none" }}>
              {model.calibrated_model_score?.toFixed(3)}
            </span>
            <span className="eyebrow">{pick(T.calibrated, lang)}</span>
          </div>
          {model.abstain && <p style={{ fontSize: 13, color: "var(--ev-missing)", marginTop: 6 }}>{pick(T.abstain, lang)}</p>}
          <div className="mono" style={{ fontSize: 11.5, color: "var(--text-3)", marginTop: 12, lineHeight: 1.9 }}>
            <div>{pick(T.raw, lang)} {model.raw_model_score?.toFixed(6)}</div>
            <div>{model.model} · {model.checkpoint} · seed 0</div>
          </div>
        </>
      )}
      <div className="mono" style={{ fontSize: 11.5, color: "var(--text-3)", marginTop: 10, lineHeight: 1.9 }}>
        <div>{pick(T.regime, lang)} {model.regime} · {pick(T.split, lang)}: {model.split_a} / {model.split_b}</div>
      </div>
      {model.measured_performance.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <span className="eyebrow">{pick(T.measured, lang)}</span>
          <ul style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 12.5, color: "var(--text-2)", lineHeight: 1.7 }}>
            {model.measured_performance.map((p) => (
              <li key={p.view + p.metric}>
                {p.metric} <span className="mono">{p.mean.toFixed(3)} ± {p.sd.toFixed(3)}</span> · {p.view} · n={p.n_seeds}
                <div className="mono" style={{ fontSize: 10, color: "var(--text-3)" }}>{p.source}</div>
              </li>
            ))}
          </ul>
        </div>
      )}
      {model.modality_reliance && !model.abstain && (
        <div style={{ marginTop: 16, borderTop: "1px solid var(--border-soft)", paddingTop: 14 }}>
          <RelianceBars r={model.modality_reliance} />
        </div>
      )}
      <ul style={{ margin: "12px 0 0", paddingLeft: 18, fontSize: 12.5, color: "var(--text-3)", lineHeight: 1.65 }}>
        {model.notes.map((n, i) => <li key={i}>{pick(n, lang)}</li>)}
      </ul>
    </div>
  );
}

// ----------------------------------------------------------------- states ---
const STATE_TEXT = {
  unconfigured: {
    ru: "Сервис доказательств DDI-Net 3.0 не подключён к этой сборке сайта (не задан VITE_ANALYZE_API). Отчёт не показан — мы не подставляем вместо него примерные данные. Ниже остаются задокументированные данные о белках каждого препарата.",
    en: "The DDI-Net 3.0 evidence service is not connected to this build of the site (VITE_ANALYZE_API is not set). No report is shown — we do not substitute sample data. Each drug's documented protein data remains below.",
  },
  unavailable: { ru: "Сервис доказательств сейчас недоступен:", en: "The evidence service is unavailable:" },
  error: { ru: "Ошибка запроса:", en: "Request error:" },
  unresolved: { ru: "Не удалось однозначно определить препарат. Ничего не подставлено автоматически.", en: "A drug could not be identified unambiguously. Nothing was substituted automatically." },
  loading: { ru: "Собираем записи источников…", en: "Gathering source records…" },
  rateLimited: {
    ru: "Слишком много запросов за короткое время. Сервис ограничивает частоту, чтобы оставаться доступным всем. Попробуйте снова через {s} с.",
    en: "Too many requests in a short time. The service limits request rates to stay available to everyone. Try again in {s} s.",
  },
} satisfies Record<string, Bi>;

export function RemoteNotice({ state }: { state: Remote<unknown> }) {
  const { lang } = useI18n();
  if (state.kind === "ok") return null;
  if (state.kind === "loading") {
    return (
      <div aria-busy="true" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <span className="mono" style={{ fontSize: 12, color: "var(--text-3)" }}>{pick(STATE_TEXT.loading, lang)}</span>
        <div className="v3-skeleton" style={{ height: 96 }} />
        <div className="v3-skeleton" style={{ height: 160 }} />
      </div>
    );
  }
  const box = { border: "1px solid rgba(255,196,120,0.35)", background: "rgba(255,196,120,0.05)", borderRadius: "var(--radius-lg)", padding: 20 } as const;
  if (state.kind === "unconfigured") return <div style={box}><p style={{ fontSize: 14 }}>{pick(STATE_TEXT.unconfigured, lang)}</p></div>;
  if (state.kind === "unresolved") return <Unresolved resolutions={state.resolutions} />;
  if (state.kind === "rate_limited") {
    return <div style={box} role="alert"><p style={{ fontSize: 14 }}>{pick(STATE_TEXT.rateLimited, lang).replace("{s}", String(state.retryAfter))}</p></div>;
  }
  const head = state.kind === "unavailable" ? STATE_TEXT.unavailable : STATE_TEXT.error;
  return <div style={box}><p style={{ fontSize: 14 }}>{pick(head, lang)} <span className="mono" style={{ fontSize: 12 }}>{state.message}</span></p></div>;
}

function Unresolved({ resolutions }: { resolutions: ResolveOut[] }) {
  const { lang } = useI18n();
  return (
    <div style={{ border: "1px solid rgba(255,196,120,0.35)", background: "rgba(255,196,120,0.05)", borderRadius: "var(--radius-lg)", padding: 20 }}>
      <p style={{ fontSize: 14 }}>{pick(STATE_TEXT.unresolved, lang)}</p>
      <ul style={{ margin: "10px 0 0", paddingLeft: 18, fontSize: 13, color: "var(--text-2)" }}>
        {resolutions.filter((r) => r.status !== "resolved").map((r) => (
          <li key={r.query}>
            <span className="mono">{r.query}</span> — {r.status}
            {r.candidates.length > 0 && <> · {r.candidates.map((c) => `${c.inn ?? c.id} (${c.id})`).join(", ")}</>}
            {r.note && <div style={{ fontSize: 12, color: "var(--text-3)" }}>{r.note}</div>}
          </li>
        ))}
      </ul>
    </div>
  );
}
