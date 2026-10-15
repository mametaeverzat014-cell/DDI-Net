// Outcome-engine parts of the full research report: the status and outcome
// list in the summary, the outcome table with per-outcome provenance in
// section 3, and the mechanism-to-outcome figure in section 4. Read from the
// API's `outcomes` block only; excerpts are printed verbatim.
import { Text, View } from "@react-pdf/renderer";
import type { ClinicalOutcome, LinkProvenance, MechanismChain, MultiReport, OutcomeReport, PairReport } from "../data/v3";
import { pick, type Lang } from "../i18n";
import { LEVEL_OF, OT, PROVENANCE_OF, SERIOUSNESS_OF, STATUS_OF } from "../data/outcomeText";
import { groupEvidence } from "../data/evidenceGroups";
import { bi, t } from "./content";
import { Chip, Dot, MonoLines, Seg, SubTitle, Table } from "./components";
import { chunkText, clean, drugName } from "./format";
import { st, tint, type Col } from "./styles";
import { C, CONTENT_WIDTH, EV, FONT, SIZE } from "./theme";

const STATUS_COLOR = {
  documented_interaction: EV.label, documented_outcome_unclear: EV.documented, research_prediction_only: EV.hypothesis,
  insufficient_evidence: EV.none, source_unavailable: EV.missing,
} as const;

const LINK: Record<LinkProvenance, { style: "solid" | "dashed" | "dotted"; color: string }> = {
  documented: { style: "solid", color: EV.label },
  verified_annotation: { style: "solid", color: EV.documented },
  plausible_unconfirmed: { style: "dashed", color: EV.hypothesis },
  unavailable: { style: "dotted", color: EV.none },
};

const refsOf = (r: PairReport) => {
  const g = groupEvidence(r.evidence);
  return (x: ClinicalOutcome) => Array.from(new Set(x.supports.map((s) => (s.evidence_record_id ? g.excerptOf(s.evidence_record_id)?.label ?? "" : "")).filter(Boolean)));
};

/** Section 1: what the outcome engine concludes, before the brief. */
export function OutcomeSummaryBlock({ r, lang }: { r: PairReport; lang: Lang }) {
  const o = r.outcomes;
  if (!o) return <View wrap={false} style={{ marginBottom: 6 }}><Text style={[st.small, { color: EV.missing }]}>{pick(OT.oldApi, lang)}</Text></View>;
  const shown = o.outcomes.filter((x) => !x.research_only);
  const refs = refsOf(r);
  const color = STATUS_COLOR[o.interaction_status];
  return (
    <>
      <View wrap={false} style={{ borderLeftWidth: 3, borderLeftColor: color, backgroundColor: tint(color, 0.07), padding: 8, marginBottom: 6 }}>
        <Text style={{ fontFamily: FONT.mono, fontSize: 6.6, color: C.muted }}>{t("outcomeStatusTitle", lang).toUpperCase()}</Text>
        <Text style={{ fontFamily: FONT.serif, fontSize: 11.5, color: C.navy, marginTop: 3 }}>{bi(o.interaction_status_label, lang)}</Text>
        <Text style={[st.small, { marginTop: 2 }]}>{bi(o.interaction_status_hint, lang)}</Text>
      </View>
      <View wrap={false} minPresenceAhead={30} style={{ marginBottom: 3 }}>
        <Text style={{ fontWeight: 600, fontSize: SIZE.h3, color: C.navy }}>{pick(OT.bTitle, lang)}</Text>
      </View>
      {shown.length === 0
        ? <View wrap={false} style={{ marginBottom: 6 }}><Text style={st.small}>{o.no_outcome_text ? bi(o.no_outcome_text, lang) : ""}</Text></View>
        : shown.map((x) => (
          <View key={x.id} wrap={false} style={{ flexDirection: "row", marginBottom: 3 }}>
            <View style={{ width: 11 }}><Dot color={EV.label} /></View>
            <Text style={[st.small, { flex: 1, color: C.slate }]}>
              <Text style={{ fontWeight: 600, color: C.ink }}>{bi(x.label, lang)}</Text>
              {` — ${pick(LEVEL_OF[x.effect_level], lang)}; ${pick(STATUS_OF[x.evidence_status], lang)}; ${pick(SERIOUSNESS_OF[x.seriousness], lang)}.`}
              <Text style={{ fontFamily: FONT.mono, fontSize: 6.8, color: C.navy3 }}>{refs(x).length ? ` ${refs(x).join(" ")}` : ""}</Text>
            </Text>
          </View>
        ))}
      <View wrap={false} style={{ marginBottom: 6 }}>
        <Text style={[st.tiny, { marginTop: 2 }]}>{pick(OT.dSeriousness, lang)}: {bi(o.seriousness_text, lang)}</Text>
      </View>
    </>
  );
}

/** Section 3: the outcome table and each outcome's provenance. */
export function OutcomeEvidence({ r, lang }: { r: PairReport; lang: Lang }) {
  const o = r.outcomes;
  if (!o) return null;
  const refs = refsOf(r);
  const cols: Col[] = [
    { title: t("outcomeCol", lang), width: 2 }, { title: t("kindCol", lang), width: 1.5 },
    { title: t("seriousCol", lang), width: 1.25 }, { title: t("refsCol", lang), width: 0.85 },
  ];
  const all = o.outcomes;
  return (
    <>
      <SubTitle>{t("outcomesTitle", lang)}</SubTitle>
      <View wrap={false} style={{ marginBottom: 4 }}><Text style={st.tiny}>{t("outcomesLead", lang)}</Text></View>
      {all.length === 0
        ? <View wrap={false}><Text style={st.small}>{o.no_outcome_text ? bi(o.no_outcome_text, lang) : ""}</Text></View>
        : (
          <Table cols={cols} rows={all.map((x) => [
            <View key="l"><Text style={{ fontSize: 7.4, color: C.ink, lineHeight: 1.35 }}>{bi(x.label, lang)}</Text>
              <Text style={{ fontSize: 6.4, color: C.muted }}>{x.research_only ? pick(OT.researchHyp, lang) : ""}</Text></View>,
            <View key="k"><Text style={{ fontSize: 7, color: C.ink }}>{pick(LEVEL_OF[x.effect_level], lang)}</Text>
              <Text style={{ fontSize: 6.6, color: C.slate2 }}>{pick(STATUS_OF[x.evidence_status], lang)}</Text></View>,
            <Text key="s" style={{ fontSize: 7, color: C.ink, lineHeight: 1.35 }}>{pick(SERIOUSNESS_OF[x.seriousness], lang)}</Text>,
            <Text key="r" style={{ fontFamily: FONT.mono, fontSize: 6.8, color: C.navy3 }}>{refs(x).join(" ") || "—"}</Text>,
          ])} />
        )}
      {all.map((x) => <OutcomeProvenance key={x.id} x={x} r={r} lang={lang} />)}
    </>
  );
}

const SEG_W = CONTENT_WIDTH - 21;

function OutcomeProvenance({ x, r, lang }: { x: ClinicalOutcome; r: PairReport; lang: Lang }) {
  const affected = x.affected_drug_id === r.drug_a.id ? r.drug_a : x.affected_drug_id === r.drug_b.id ? r.drug_b : null;
  const parts = [
    <View>
      <View style={{ flexDirection: "row", flexWrap: "wrap" }}>
        <Chip color={EV.label}>{pick(LEVEL_OF[x.effect_level], lang)}</Chip>
        <Chip color={x.evidence_status === "hypothesized" ? EV.hypothesis : EV.documented}>{pick(STATUS_OF[x.evidence_status], lang)}</Chip>
        <Chip color={C.muted}>{pick(SERIOUSNESS_OF[x.seriousness], lang)}</Chip>
      </View>
      <Text style={{ fontWeight: 600, fontSize: 9, color: C.navy, marginTop: 3 }}>{bi(x.label, lang)}{affected ? ` · ${drugName(affected, lang)}` : ""}</Text>
      <Text style={[st.tiny, { marginTop: 1 }]}>{bi(x.explanation, lang)}</Text>
      <Text style={[st.tiny, { marginTop: 1 }]}>{bi(x.seriousness_basis, lang)} {bi(x.direction_note, lang)}</Text>
      <Text style={[st.tiny, { marginTop: 1 }]}>{bi(x.evidence_strength_text, lang)} {pick(OT.documents, lang)}: {x.n_source_documents}.</Text>
      {x.extraction_note ? <Text style={[st.tiny, { marginTop: 1 }]}>{bi(x.extraction_note, lang)}</Text> : null}
      <MonoLines text={x.id} width={SEG_W} size={6} color={C.muted} />
    </View>,
    ...x.supports.flatMap((s, i) => {
      const chunks = chunkText(clean(s.excerpt), 700);
      return [
        <View style={{ marginTop: 4, paddingTop: 3, borderTopWidth: 0.4, borderTopColor: C.hair }}>
          <Text style={{ fontFamily: FONT.mono, fontSize: 6.2, color: C.muted }}>{`${i + 1}. ${clean(s.source_name)}${s.section ? ` · ${clean(s.section)}` : ""}${s.retrieved_at ? ` · ${s.retrieved_at}` : ""}`}</Text>
          <Text style={{ fontFamily: FONT.serif, fontStyle: "italic", fontSize: 8.4, color: C.ink, lineHeight: 1.4, marginTop: 1 }}>“{chunks[0]}{chunks.length === 1 ? "”" : ""}</Text>
        </View>,
        ...chunks.slice(1).map((c, k) => <Text style={{ fontFamily: FONT.serif, fontStyle: "italic", fontSize: 8.4, color: C.ink, lineHeight: 1.4 }}>{c}{k === chunks.length - 2 ? "”" : ""}</Text>),
        <View>
          <MonoLines text={`${s.extraction_method}${s.matched_terms.length ? ` · ${s.matched_terms.join(" | ")}` : ""}${s.source_document_id ? ` · ${s.source_document_id}` : ""}${s.source_seriousness ? ` · ${s.source_seriousness}` : ""}`} width={SEG_W} size={6} />
          {s.qualifiers.map((q) => <Text key={q} style={{ fontSize: 6.6, color: C.slate2, lineHeight: 1.35 }}>{clean(q)}</Text>)}
        </View>,
      ];
    }),
    ...x.limitations.map((l) => <Text style={{ fontSize: 6.8, color: C.slate2, lineHeight: 1.35 }}>• {bi(l, lang)}</Text>),
  ];
  return <Seg accent={x.evidence_status === "hypothesized" ? EV.hypothesis : EV.label} background={C.white} parts={parts} />;
}

/** Section 4: one row per chain; link style says what the link rests on. */
export function ChainFigure({ o, lang }: { o: OutcomeReport | null | undefined; lang: Lang }) {
  if (!o || !o.chains.length) return null;
  return (
    <>
      <SubTitle>{t("chainsTitle", lang)}</SubTitle>
      <View wrap={false} style={{ marginBottom: 4 }}>
        <Text style={st.tiny}>{t("chainsLead", lang)}</Text>
        <View style={{ flexDirection: "row", flexWrap: "wrap", marginTop: 3 }}>
          {(Object.keys(LINK) as LinkProvenance[]).map((k) => (
            <View key={k} style={{ flexDirection: "row", alignItems: "center", marginRight: 10, marginTop: 2 }}>
              <View style={{ width: 22, borderTopWidth: 1.4, borderTopStyle: LINK[k].style, borderTopColor: LINK[k].color, marginRight: 3 }} />
              <Text style={{ fontSize: 6.6, color: C.slate2 }}>{pick(PROVENANCE_OF[k], lang)}</Text>
            </View>
          ))}
        </View>
      </View>
      {o.chains.map((c) => <ChainRowPdf key={c.id} c={c} lang={lang} />)}
    </>
  );
}

function ChainRowPdf({ c, lang }: { c: MechanismChain; lang: Lang }) {
  const [actor, protein, affected, effect] = c.nodes;
  const toEffect = c.links.find((l) => l.relation === "exposure_change");
  const steps: { n: (typeof c.nodes)[number]; p?: LinkProvenance }[] = [
    { n: actor }, { n: protein, p: c.links[0]?.provenance }, { n: affected, p: c.links[1]?.provenance }, { n: effect, p: toEffect?.provenance },
    ...c.links.filter((l) => l.relation === "may_lead_to").map((l) => ({ n: c.nodes.find((n) => n.id === l.target)!, p: l.provenance })),
  ].filter((s) => s.n);
  const kindColor = { drug: C.navy3, protein: EV.documented, effect: EV.hypothesis, outcome: EV.label } as const;
  return (
    <View wrap={false} style={{ borderWidth: 0.5, borderColor: C.hair, padding: 6, marginBottom: 5 }}>
      <View style={{ flexDirection: "row", flexWrap: "wrap", alignItems: "center" }}>
        {steps.map((s, i) => (
          // connector and box wrap together, so no line is left dangling at a row end
          <View key={i} style={{ flexDirection: "row", alignItems: "center" }}>
            {s.p ? <View style={{ width: 18, borderTopWidth: 1.4, borderTopStyle: LINK[s.p].style, borderTopColor: LINK[s.p].color, marginHorizontal: 2, marginVertical: 3 }} /> : null}
            <View style={{ borderWidth: 0.7, borderColor: kindColor[s.n.kind], borderRadius: 3, paddingHorizontal: 4, paddingVertical: 2, marginVertical: 2, maxWidth: 150 }}>
              <Text style={{ fontSize: 6.8, color: kindColor[s.n.kind], lineHeight: 1.3 }}>{bi(s.n.label, lang)}</Text>
            </View>
          </View>
        ))}
        {c.research_only ? <Text style={{ fontFamily: FONT.mono, fontSize: 6, color: EV.hypothesis, marginLeft: 4 }}>{pick(OT.researchHyp, lang)}</Text> : null}
      </View>
      <Text style={[st.tiny, { marginTop: 2 }]}>{bi(c.summary, lang)}</Text>
      {c.links.map((l, i) => (
        <Text key={i} style={{ fontSize: 6.4, color: LINK[l.provenance].color === EV.none ? C.muted : C.slate2, lineHeight: 1.3 }}>
          {`${pick(PROVENANCE_OF[l.provenance], lang)}: ${bi(l.text, lang)}`}
        </Text>
      ))}
    </View>
  );
}

/** Multi-drug summary: categories documented per pair and shared by several pairs. */
export function MultiOutcomeBlock({ m, lang, dn }: { m: MultiReport; lang: Lang; dn: (id: string) => string }) {
  const cats = m.outcome_categories ?? {};
  if (!m.pairs.some((p) => p.interaction_status)) return null;
  const shared = Object.entries(m.shared_outcome_categories ?? {});
  const cols: Col[] = [{ title: t("pair", lang), width: 1.5 }, { title: t("outcomeStatusTitle", lang), width: 1.4 }, { title: t("outcomesTitle", lang), width: 2.4 }];
  return (
    <>
      <SubTitle>{t("outcomesTitle", lang)}</SubTitle>
      <Table cols={cols} rows={m.pairs.map((p) => [
        `${dn(p.drug_a)} + ${dn(p.drug_b)}`,
        <Text key="s" style={{ fontSize: 7, color: STATUS_COLOR[p.interaction_status ?? "insufficient_evidence"] }}>{p.interaction_status ? interactionShort(p.interaction_status, lang) : "—"}</Text>,
        <Text key="c" style={{ fontSize: 7, color: C.ink, lineHeight: 1.35 }}>
          {(p.outcome_categories ?? []).length ? (p.outcome_categories ?? []).map((k) => (cats[k] ? pick(cats[k], lang) : k)).join("; ") : pick(OT.noneDocumented, lang)}
        </Text>,
      ])} />
      {shared.length ? (
        <>
          <View wrap={false} minPresenceAhead={30}><Text style={{ fontWeight: 600, fontSize: 8.4, color: C.navy, marginTop: 4 }}>{pick(OT.sharedTitle, lang)}</Text></View>
          {shared.map(([k, pairs]) => (
            <View key={k} wrap={false} style={{ flexDirection: "row", marginTop: 2 }}>
              <Text style={{ width: 9, fontSize: 8, color: EV.label }}>•</Text>
              <Text style={[st.small, { flex: 1 }]}>{`${cats[k] ? pick(cats[k], lang) : k}: ${pairs.map(([a, b]) => `${dn(a)} + ${dn(b)}`).join("; ")}`}</Text>
            </View>
          ))}
          <View wrap={false}><Text style={[st.tiny, { marginTop: 3 }]}>{pick(OT.sharedNote, lang)}</Text></View>
        </>
      ) : null}
    </>
  );
}

function interactionShort(s: NonNullable<MultiReport["pairs"][number]["interaction_status"]>, lang: Lang): string {
  const m = {
    documented_interaction: ["задокументировано", "documented interaction"],
    documented_outcome_unclear: ["есть данные, последствие не ясно", "evidence, outcome unclear"],
    research_prediction_only: ["только гипотеза", "research prediction only"],
    insufficient_evidence: ["недостаточно данных", "insufficient evidence"],
    source_unavailable: ["источник недоступен", "source unavailable"],
  } as const;
  return m[s][lang === "ru" ? 0 : 1];
}

