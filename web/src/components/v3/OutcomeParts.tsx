// The clinical-outcome view of a pair report (API `outcomes` block).
//
// Simple mode answers, in order: A. is there a documented interaction, B. what
// could happen, C. why, D. how certain, E. what BIO-GINE adds, F. the limit of
// what this can say. Every outcome card quotes its source; a hypothesis never
// appears in B; seriousness is shown only as a source states it; the model
// never changes A–D. Research mode adds every outcome with full provenance and
// the mechanism-to-outcome chains with one line style per kind of link.
import { useState } from "react";
import { useI18n, pick, type Bi } from "../../i18n";
import type {
  ChainLink, ClinicalOutcome, InteractionStatus, LinkProvenance, MechanismChain, ModelBlock, OutcomeReport, PairReport,
} from "../../data/v3";
import { LEVEL_OF, OT, PROVENANCE_OF, SERIOUSNESS_OF, STATUS_OF } from "../../data/outcomeText";
import { fmtCalibrated } from "../../data/scoreFormat";
import { scrollToAnchor, type RefIndex } from "./refs";

const STATUS_COLOR: Record<InteractionStatus, string> = {
  documented_interaction: "var(--ev-label)",
  documented_outcome_unclear: "var(--ev-documented)",
  research_prediction_only: "var(--ev-hypothesis)",
  insufficient_evidence: "var(--ev-none)",
  source_unavailable: "var(--ev-missing)",
};

const LINK_STYLE: Record<LinkProvenance, { line: string; color: string }> = {
  documented: { line: "solid", color: "var(--ev-label)" },
  verified_annotation: { line: "solid", color: "var(--ev-documented)" },
  plausible_unconfirmed: { line: "dashed", color: "var(--ev-hypothesis)" },
  unavailable: { line: "dotted", color: "var(--ev-none)" },
};

export function OutcomeOverview({ report, refs, research }: { report: PairReport; refs?: RefIndex; research: boolean }) {
  const { lang } = useI18n();
  const o = report.outcomes;
  if (!o) {
    return <p className="v3-card" style={{ fontSize: 13.5, color: "var(--ev-missing)" }}>{pick(OT.oldApi, lang)}</p>;
  }
  const shown = o.outcomes.filter((x) => !x.research_only);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <StatusCard o={o} />
      <Block title={OT.bTitle} lead={OT.bLead} id="outcomes-b">
        {shown.length ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {o.no_specific_outcome_text && (
              <p data-testid="no-specific-outcome" style={{ fontSize: 14, color: "var(--text)", borderLeft: "3px solid var(--ev-missing)", paddingLeft: 10 }}>
                {pick(o.no_specific_outcome_text, lang)}
              </p>
            )}
            {shown.map((x) => <OutcomeCard key={x.id} x={x} report={report} refs={refs} />)}
          </div>
        ) : (
          <p style={{ fontSize: 14.5, color: "var(--text)" }}>{o.no_outcome_text ? pick(o.no_outcome_text, lang) : ""}</p>
        )}
      </Block>
      <WhyBlock o={o} research={research} />
      <CertaintyBlock o={o} />
      <ModelBlockNote model={report.model} />
      <div className="v3-card" style={{ borderLeft: "3px solid var(--amber)" }}>
        <span className="eyebrow" style={{ color: "var(--amber)" }}>{pick(OT.fTitle, lang)}</span>
        <p style={{ marginTop: 8, fontSize: 14, color: "var(--text)" }}>{pick(o.individual_limit, lang)}</p>
      </div>
    </div>
  );
}

function Block({ title, lead, id, children }: { title: Bi; lead?: Bi; id?: string; children: React.ReactNode }) {
  const { lang } = useI18n();
  return (
    <section className="v3-card" aria-labelledby={id ? `${id}-h` : undefined} id={id} style={{ scrollMarginTop: 120 }}>
      <h3 id={id ? `${id}-h` : undefined} style={{ fontSize: 19 }}>{pick(title, lang)}</h3>
      {lead && <p style={{ fontSize: 12.5, color: "var(--text-3)", marginTop: 6 }}>{pick(lead, lang)}</p>}
      <div style={{ marginTop: 12 }}>{children}</div>
    </section>
  );
}

function StatusCard({ o }: { o: OutcomeReport }) {
  const { lang } = useI18n();
  const color = STATUS_COLOR[o.interaction_status];
  return (
    <div className="v3-card v3-in" role="status" style={{ borderColor: color, borderLeftWidth: 4 }}>
      <span className="eyebrow">{pick(OT.aTitle, lang)}</span>
      <p style={{ color: "var(--text)", fontSize: 20, lineHeight: 1.35, marginTop: 8 }}>{pick(o.interaction_status_label, lang)}</p>
      <p style={{ fontSize: 13.5, marginTop: 6 }}>{pick(o.interaction_status_hint, lang)}</p>
    </div>
  );
}

function Chip({ color, children, title }: { color: string; children: React.ReactNode; title?: string }) {
  return <span className="v3-chip" title={title} style={{ color }}>{children}</span>;
}

function OutcomeCard({ x, report, refs }: { x: ClinicalOutcome; report: PairReport; refs?: RefIndex }) {
  const { lang } = useI18n();
  const labels = refs ? refs.labels(x.supports.map((s) => s.evidence_record_id).filter((v): v is string => !!v)) : [];
  const serColor = x.seriousness === "documented_contraindication" || x.seriousness === "explicit_serious_warning" ? "var(--ev-label)" : "var(--text-3)";
  const name = (id: string | null) => (id === report.drug_a.id ? report.drug_a : id === report.drug_b.id ? report.drug_b : null);
  const affected = name(x.affected_drug_id);
  return (
    <article className="v3-card" style={{ background: "var(--surface)", padding: 16 }} id={`outcome-${x.category}-${x.effect}`}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <Chip color="var(--ev-label)">{pick(LEVEL_OF[x.effect_level], lang)}</Chip>
        <Chip color="var(--ev-documented)">{pick(STATUS_OF[x.evidence_status], lang)}</Chip>
        <Chip color={serColor} title={pick(x.seriousness_basis, lang)}>{pick(SERIOUSNESS_OF[x.seriousness], lang)}</Chip>
      </div>
      <h4 style={{ fontSize: 16.5, marginTop: 10, color: "var(--text)" }}>
        {pick(x.label, lang)}
        {affected && <span style={{ fontSize: 13, color: "var(--text-3)" }}> · {lang === "ru" ? affected.name_ru ?? affected.inn : affected.inn}</span>}
      </h4>
      <p style={{ fontSize: 13.5, marginTop: 6 }}>{pick(x.explanation, lang)}</p>
      <p style={{ fontSize: 12.5, marginTop: 6, color: "var(--text-3)" }}>{pick(x.seriousness_basis, lang)}</p>
      <p style={{ fontSize: 12.5, marginTop: 4, color: "var(--text-3)" }}>{pick(x.direction_note, lang)}</p>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8, alignItems: "baseline" }}>
        <span className="mono" style={{ fontSize: 11, color: "var(--text-3)" }}>{pick(x.evidence_strength_text, lang)} · {pick(OT.documents, lang)}: {x.n_source_documents}</span>
        {labels.map((l) => (
          <button key={l.label} className="v3-ref" onClick={() => l.anchor && scrollToAnchor(l.anchor)} aria-label={`→ ${l.label}`}>{l.label}</button>
        ))}
      </div>
      {x.extraction_note && (
        <p data-testid="extraction-note" style={{ fontSize: 12, color: "var(--text-2)", margin: "8px 0 0", borderLeft: "2px solid var(--amber)", paddingLeft: 8 }}>
          {pick(x.extraction_note, lang)}
        </p>
      )}
      <SupportList x={x} />
      {x.limitations.length > 0 && (
        <ul style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 12.5, color: "var(--text-3)" }}>
          {x.limitations.map((l, i) => <li key={i}>{pick(l, lang)}</li>)}
        </ul>
      )}
    </article>
  );
}

function SupportList({ x }: { x: ClinicalOutcome }) {
  const { lang } = useI18n();
  return (
    <details style={{ marginTop: 10 }}>
      <summary className="mono" style={{ cursor: "pointer", fontSize: 11.5, color: "var(--cyan)" }}>{pick(OT.showSource, lang)} · {x.supports.length}</summary>
      <ul style={{ listStyle: "none", padding: 0, margin: "8px 0 0", display: "flex", flexDirection: "column", gap: 10 }}>
        {x.supports.map((s, i) => (
          <li key={i}>
            <blockquote lang="en" style={{ margin: 0, padding: "6px 10px", borderLeft: "2px solid var(--border-strong)", fontSize: 13.5, color: "var(--text)" }}>{s.excerpt}</blockquote>
            <div className="mono" style={{ fontSize: 10.5, color: "var(--text-3)", marginTop: 4, overflowWrap: "anywhere", lineHeight: 1.7 }}>
              {s.source_name}{s.section ? ` · ${pick(OT.section, lang)}: ${s.section}` : ""}{s.retrieved_at ? ` · ${s.retrieved_at}` : ""}
              {s.source_url && <> · <a href={s.source_url} target="_blank" rel="noreferrer noopener">↗</a></>}
              <div>{pick(OT.method, lang)}: {s.extraction_method}{s.matched_terms.length ? ` · “${s.matched_terms.join("”, “")}”` : ""}</div>
              {s.qualifiers.map((q) => <div key={q}>{q}</div>)}
            </div>
          </li>
        ))}
      </ul>
    </details>
  );
}

function WhyBlock({ o, research }: { o: OutcomeReport; research: boolean }) {
  const { lang } = useI18n();
  const verified = o.chains.filter((c) => !c.research_only);
  const hyps = o.chains.filter((c) => c.research_only);
  return (
    <Block title={OT.cTitle} id="outcomes-c">
      {verified.length > 0 ? (
        <>
          <span className="eyebrow">{pick(OT.cVerified, lang)}</span>
          <ul style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 14, color: "var(--text-2)", display: "flex", flexDirection: "column", gap: 6 }}>
            {verified.map((c) => <li key={c.id}>{pick(c.summary, lang)}</li>)}
          </ul>
        </>
      ) : (
        <p style={{ fontSize: 14 }}>{pick(OT.cNone, lang)}</p>
      )}
      {hyps.length > 0 && (research ? (
        <div style={{ marginTop: 12 }}>
          <span className="eyebrow" style={{ color: "var(--ev-hypothesis)" }}>{pick(OT.cHypothesis, lang)}</span>
          <ul style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 13.5, color: "var(--text-3)", display: "flex", flexDirection: "column", gap: 6 }}>
            {hyps.map((c) => <li key={c.id}>{pick(c.summary, lang)}</li>)}
          </ul>
        </div>
      ) : (
        <p style={{ fontSize: 12.5, marginTop: 10, color: "var(--text-3)" }}>{pick(OT.cResearchOnly, lang)}</p>
      ))}
      {o.chains.length > 0 && <ChainExplorer o={o} research={research} />}
    </Block>
  );
}

function CertaintyBlock({ o }: { o: OutcomeReport }) {
  const { lang } = useI18n();
  const strengths = Array.from(new Map(o.outcomes.filter((x) => !x.research_only).map((x) => [x.evidence_strength, x.evidence_strength_text])).values());
  return (
    <Block title={OT.dTitle} id="outcomes-d">
      <dl style={{ margin: 0, display: "grid", gridTemplateColumns: "minmax(140px, auto) 1fr", gap: "8px 16px", fontSize: 13.5 }}>
        <dt style={{ color: "var(--text-3)" }}>{pick(OT.dSeriousness, lang)}</dt>
        <dd style={{ margin: 0 }}>{pick(o.seriousness_text, lang)}</dd>
        <dt style={{ color: "var(--text-3)" }}>{pick(OT.dStrength, lang)}</dt>
        <dd style={{ margin: 0 }}>{strengths.length ? strengths.map((s) => pick(s, lang)).join(" ") : "—"}</dd>
        <dt style={{ color: "var(--text-3)" }}>{pick(OT.dCoverage, lang)}</dt>
        <dd style={{ margin: 0 }}>
          <ul style={{ margin: 0, paddingLeft: 18 }}>{o.coverage.map((c, i) => <li key={i}>{pick(c, lang)}</li>)}</ul>
        </dd>
      </dl>
    </Block>
  );
}

function ModelBlockNote({ model }: { model: ModelBlock }) {
  const { lang } = useI18n();
  return (
    <Block title={OT.eTitle} id="outcomes-e">
      <p style={{ fontSize: 13.5 }}>{pick(OT.eText, lang)}</p>
      <p className="mono" style={{ fontSize: 12, marginTop: 8, color: "var(--ev-model)" }}>
        {!model.available ? pick(OT.eUnavailable, lang)
          : model.abstain ? pick(OT.eAbstain, lang)
            : `${pick(OT.eScore, lang)}: ${fmtCalibrated(model.calibrated_model_score)} · ${model.regime}`}
      </p>
    </Block>
  );
}

// ------------------------------------------------------------ chain explorer --
export function ChainExplorer({ o, research }: { o: OutcomeReport; research: boolean }) {
  const { lang } = useI18n();
  const chains = o.chains.filter((c) => research || !c.research_only);
  const [sel, setSel] = useState<{ chain: string; i: number } | null>(null);
  if (!chains.length) return null;
  return (
    <div style={{ marginTop: 16 }}>
      <span className="eyebrow">{pick(OT.chainTitle, lang)}</span>
      <Legend />
      <p style={{ fontSize: 12, color: "var(--text-3)", marginTop: 4 }}>{pick(OT.chainHint, lang)}</p>
      <div style={{ display: "flex", flexDirection: "column", gap: 14, marginTop: 10 }}>
        {chains.map((c) => <ChainRow key={c.id} c={c} sel={sel?.chain === c.id ? sel.i : null} onSel={(i) => setSel(sel && sel.chain === c.id && sel.i === i ? null : { chain: c.id, i })} o={o} />)}
      </div>
    </div>
  );
}

function Legend() {
  const { lang } = useI18n();
  return (
    <div role="list" aria-label={pick(OT.chainLegend, lang)} style={{ display: "flex", flexWrap: "wrap", gap: 14, marginTop: 8 }}>
      {(Object.keys(LINK_STYLE) as LinkProvenance[]).map((k) => (
        <span role="listitem" key={k} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-2)" }}>
          <span aria-hidden style={{ width: 28, borderTop: `2px ${LINK_STYLE[k].line} ${LINK_STYLE[k].color}` }} />
          {pick(PROVENANCE_OF[k], lang)}
        </span>
      ))}
    </div>
  );
}

/** One chain as a horizontal path: actor → protein → affected → effect → outcomes. */
function ChainRow({ c, sel, onSel, o }: { c: MechanismChain; sel: number | null; onSel: (i: number) => void; o: OutcomeReport }) {
  const { lang } = useI18n();
  const node = (id: string) => c.nodes.find((n) => n.id === id);
  // Display order: actor, protein, affected drug, effect, outcomes; links between.
  const [actor, protein, affected, effect, ...outs] = c.nodes;
  const toEffect = c.links.find((l) => l.relation === "exposure_change");
  const steps: { n: typeof actor; link?: ChainLink; li?: number }[] = [
    { n: actor },
    { n: protein, link: c.links[0], li: 0 },
    { n: affected, link: c.links[1], li: 1 },
    { n: effect, link: toEffect, li: toEffect ? c.links.indexOf(toEffect) : undefined },
  ];
  const outcomeLinks = c.links.map((l, i) => ({ l, i })).filter(({ l }) => l.relation === "may_lead_to");
  const selected = sel !== null ? c.links[sel] : null;
  const kindColor = { drug: "var(--blue)", protein: "var(--ev-documented)", effect: "var(--ev-hypothesis)", outcome: "var(--ev-label)" } as const;
  // Render helpers, not components: components declared here would remount on
  // every selection and drop keyboard focus.
  const box = (n: typeof actor) => (
    <span className="v3-chip" style={{ color: kindColor[n.kind], padding: "4px 10px", fontSize: 12.5, minWidth: 0 }}>{pick(n.label, lang)}</span>
  );
  const link = (l: ChainLink, i: number) => (
    <button onClick={() => onSel(i)} aria-pressed={sel === i} aria-label={`${pick(PROVENANCE_OF[l.provenance], lang)}: ${pick(l.text, lang)}`}
      style={{ background: "none", border: "none", padding: "6px 2px", cursor: "pointer", display: "inline-flex", alignItems: "center", flexShrink: 0 }}>
      <span aria-hidden style={{ width: 34, borderTop: `2px ${LINK_STYLE[l.provenance].line} ${LINK_STYLE[l.provenance].color}`, outline: sel === i ? "1px solid var(--cyan)" : "none" }} />
      <span aria-hidden style={{ color: LINK_STYLE[l.provenance].color, fontSize: 11 }}>▸</span>
    </button>
  );
  const linkFor = link;
  return (
    <div style={{ border: "1px solid var(--border-soft)", borderRadius: 10, padding: 12 }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 2 }}>
        {steps.map(({ n, link, li }) => (
          <span key={n.id} style={{ display: "inline-flex", alignItems: "center", maxWidth: "100%" }}>
            {link && li !== undefined && linkFor(link, li)}
            {box(n)}
          </span>
        ))}
        {outcomeLinks.map(({ l, i }) => {
          const n = node(l.target) ?? outs[0];
          return (
            <span key={l.target} style={{ display: "inline-flex", alignItems: "center", maxWidth: "100%" }}>
              {linkFor(l, i)}
              {n && box(n)}
            </span>
          );
        })}
        {c.research_only && <span className="mono" style={{ fontSize: 10.5, color: "var(--ev-hypothesis)", marginLeft: 8 }}>{pick(OT.researchHyp, lang)}</span>}
      </div>
      {selected && (
        <div className="mono" style={{ marginTop: 10, fontSize: 12, color: "var(--text-2)", lineHeight: 1.7 }}>
          <div style={{ color: LINK_STYLE[selected.provenance].color }}>{pick(PROVENANCE_OF[selected.provenance], lang)}</div>
          <div style={{ fontFamily: "var(--font-ui)" }}>{pick(selected.text, lang)}</div>
          {selected.refs.map((r) => {
            const out = o.outcomes.find((x) => x.id === r);
            return <div key={r} style={{ overflowWrap: "anywhere" }}>{out ? `${pick(out.label, lang)} — “${out.supports[0]?.excerpt ?? ""}”` : r}</div>;
          })}
        </div>
      )}
    </div>
  );
}

/** Research mode: every outcome (hypotheses included) with full provenance. */
export function OutcomeTable({ report }: { report: PairReport }) {
  const { lang } = useI18n();
  const o = report.outcomes;
  if (!o || !o.outcomes.length) return null;
  return (
    <div className="v3-card">
      <h3 style={{ fontSize: 18 }}>{pick(OT.outcomeTable, lang)}</h3>
      <div className="v3-scroll" style={{ marginTop: 12 }}>
        <table className="v3-table">
          <thead><tr>
            <th>{lang === "ru" ? "Последствие" : "Outcome"}</th><th>{lang === "ru" ? "Статус" : "Status"}</th>
            <th>{pick(OT.dSeriousness, lang)}</th><th>{pick(OT.sources, lang)}</th><th>{pick(OT.method, lang)}</th>
          </tr></thead>
          <tbody>
            {o.outcomes.map((x) => (
              <tr key={x.id}>
                <td>{pick(x.label, lang)}<div className="mono" style={{ fontSize: 10, color: "var(--text-3)" }}>{x.id}</div></td>
                <td>{pick(STATUS_OF[x.evidence_status], lang)}<div style={{ fontSize: 11.5, color: "var(--text-3)" }}>{pick(LEVEL_OF[x.effect_level], lang)}</div></td>
                <td style={{ fontSize: 12.5 }}>{pick(SERIOUSNESS_OF[x.seriousness], lang)}</td>
                <td style={{ fontSize: 12 }}>{x.supports.map((s, i) => <div key={i} style={{ overflowWrap: "anywhere" }}>{s.source_type} · {s.source_document_id ?? "—"}{s.section ? ` · ${s.section}` : ""}</div>)}</td>
                <td className="mono" style={{ fontSize: 10.5 }}>{Array.from(new Set(x.supports.map((s) => s.extraction_method))).join(" ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
