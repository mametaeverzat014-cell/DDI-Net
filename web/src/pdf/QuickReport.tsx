// Quick Report: one or two A4 pages answering the reader's question from the
// same API payload as the site and the full report — interaction status, the
// documented outcomes with their sources' words, the mechanism summary, the
// sources, the key uncertainty, what BIO-GINE adds and the research-only limit.
// Every block is atomic or a list of atomic rows (components.tsx, PAGE BREAKS).
import { Page, Text, View } from "@react-pdf/renderer";
import type { ClinicalOutcome, PairReport } from "../data/v3";
import { pick } from "../i18n";
import { LEVEL_OF, OT, SERIOUSNESS_OF, STATUS_OF } from "../data/outcomeText";
import { fmtCalibrated } from "../data/scoreFormat";
import { bi, isSynthetic, pairBrief, pairFacts, t } from "./content";
import { Chip, MonoLines, RunningFooter, RunningHeader } from "./components";
import { clean, drugName, humanDateTime } from "./format";
import { st, tint } from "./styles";
import { C, CONTENT_WIDTH, EV, FONT, SIZE } from "./theme";
import type { PreparedExport } from "./types";

const STATUS_COLOR = {
  documented_interaction: EV.label,
  documented_outcome_unclear: EV.documented,
  research_prediction_only: EV.hypothesis,
  insufficient_evidence: EV.none,
  source_unavailable: EV.missing,
} as const;

export function QuickReportPage({ prep, r }: { prep: PreparedExport; r: PairReport }) {
  const lang = prep.ctx.lang;
  const tr = (k: Parameters<typeof t>[0], v?: Record<string, string | number>) => t(k, lang, v);
  const o = r.outcomes;
  const groups = pairFacts(r).groups;
  const brief = pairBrief(r, lang);
  const names = `${drugName(r.drug_a, lang)} + ${drugName(r.drug_b, lang)}`;
  const shown = o ? o.outcomes.filter((x) => !x.research_only) : [];
  const unc = brief.parts.find((p) => p.id === "uncertain")?.items.map((i) => i.text ?? "").filter(Boolean).slice(0, 4) ?? [];
  const H = ({ children, color = C.navy }: { children: string; color?: string }) => (
    <View wrap={false} minPresenceAhead={40} style={{ marginTop: 10, marginBottom: 4, borderBottomWidth: 0.6, borderBottomColor: tint(color, 0.5), paddingBottom: 2 }}>
      <Text style={{ fontWeight: 600, fontSize: SIZE.h3, color }}>{children}</Text>
    </View>
  );
  return (
    <Page size="A4" style={st.page} wrap>
      <RunningHeader left={tr("headerLeft")} right={names.length > 58 ? `${names.slice(0, 56)}…` : names} />
      <RunningFooter left={tr("footerLeft")} center={prep.reportId} pageText={(n, total) => tr("page", { n, t: total })} />

      <View wrap={false} style={{ marginBottom: 6 }}>
        <Text style={{ fontFamily: FONT.mono, fontSize: 7, color: C.teal }}>{tr("brand")} · {tr("quickTitle").toUpperCase()}</Text>
        <Text style={{ fontFamily: FONT.serif, fontWeight: 600, fontSize: 17, color: C.navy, marginTop: 3, lineHeight: 1.2 }}>{names}</Text>
        <Text style={{ fontFamily: FONT.mono, fontSize: 6.8, color: C.muted, marginTop: 2 }}>
          {r.drug_a.id} · {r.drug_b.id} · {prep.reportId} · {humanDateTime(prep.ctx.now, prep.ctx.timeZone, lang)}
        </Text>
        <Text style={{ fontSize: 7.4, color: C.slate2, marginTop: 3 }}>{tr("researchOnly")}</Text>
      </View>
      {isSynthetic(prep) ? (
        <View wrap={false} style={{ borderWidth: 1, borderColor: EV.missing, padding: 6, marginBottom: 6 }}>
          <Text style={{ fontWeight: 600, fontSize: 8, color: EV.missing }}>{tr("syntheticBanner")}</Text>
        </View>
      ) : null}

      {!o ? (
        <View wrap={false}><Text style={[st.p, { color: EV.missing }]}>{pick(OT.oldApi, lang)}</Text></View>
      ) : (
        <>
          <H>{pick(OT.aTitle, lang)}</H>
          <View wrap={false} style={{ borderLeftWidth: 3, borderLeftColor: STATUS_COLOR[o.interaction_status], backgroundColor: tint(STATUS_COLOR[o.interaction_status], 0.07), padding: 7 }}>
            <Text style={{ fontFamily: FONT.serif, fontSize: 11.5, color: C.navy }}>{bi(o.interaction_status_label, lang)}</Text>
            <Text style={[st.small, { marginTop: 2 }]}>{bi(o.interaction_status_hint, lang)}</Text>
          </View>

          <H>{pick(OT.bTitle, lang)}</H>
          {shown.length === 0
            ? <View wrap={false}><Text style={st.p}>{o.no_outcome_text ? bi(o.no_outcome_text, lang) : ""}</Text></View>
            : shown.map((x) => <QuickOutcome key={x.id} x={x} prep={prep} r={r} refsOf={(id) => groups.excerptOf(id)?.label ?? ""} />)}

          <H>{pick(OT.cTitle, lang)}</H>
          {(() => {
            const verified = o.chains.filter((c) => !c.research_only);
            if (!verified.length) {
              return <View wrap={false}><Text style={st.small}>{pick(OT.cNone, lang)}{o.chains.length ? ` ${pick(OT.cResearchOnly, lang)}` : ""}</Text></View>;
            }
            return verified.map((c) => (
              <View key={c.id} wrap={false} style={{ flexDirection: "row", marginBottom: 2 }}>
                <Text style={{ width: 9, fontSize: 8, color: EV.hypothesis }}>•</Text>
                <Text style={[st.small, { flex: 1 }]}>{bi(c.summary, lang)}</Text>
              </View>
            ));
          })()}

          <H>{pick(OT.dTitle, lang)}</H>
          <View wrap={false}>
            <Text style={st.small}><Text style={{ fontWeight: 600 }}>{pick(OT.dSeriousness, lang)}: </Text>{bi(o.seriousness_text, lang)}</Text>
          </View>
          {groups.docs.map((d) => (
            <View key={d.id} wrap={false} style={{ flexDirection: "row", marginTop: 2 }}>
              <Text style={{ width: 22, fontFamily: FONT.mono, fontSize: 7, color: C.navy }}>[{d.n}]</Text>
              <Text style={[st.tiny, { flex: 1 }]}>
                {clean(d.records[0].source_name)}{d.kind === "label" ? ` · SPL ${d.id}` : ""} · {d.records[0].retrieved_at}
                {d.records[0].source_url ? ` · ${d.records[0].source_url}` : ""}
              </Text>
            </View>
          ))}
          {[...o.coverage.map((c) => bi(c, lang)), ...unc].map((s, i) => (
            <View key={i} wrap={false} style={{ flexDirection: "row", marginTop: 2 }}>
              <Text style={{ width: 9, fontSize: 8, color: EV.missing }}>•</Text>
              <Text style={[st.tiny, { flex: 1, color: C.slate }]}>{s}</Text>
            </View>
          ))}

          <H color={EV.model}>{pick(OT.eTitle, lang)}</H>
          <View wrap={false}>
            <Text style={st.small}>{pick(OT.eText, lang)}</Text>
            <Text style={{ fontFamily: FONT.mono, fontSize: 7.2, color: EV.model, marginTop: 2 }}>
              {!r.model.available ? pick(OT.eUnavailable, lang) : r.model.abstain ? pick(OT.eAbstain, lang)
                : `${pick(OT.eScore, lang)}: ${fmtCalibrated(r.model.calibrated_model_score)} · ${r.model.regime}`}
            </Text>
          </View>

          <H color={EV.missing}>{pick(OT.fTitle, lang)}</H>
          <View wrap={false}>
            <Text style={[st.small, { color: C.ink }]}>{bi(o.individual_limit, lang)}</Text>
            <Text style={[st.tiny, { marginTop: 3 }]}>{tr("quickFullNote")}</Text>
          </View>
        </>
      )}
    </Page>
  );
}

function QuickOutcome({ x, prep, r, refsOf }: { x: ClinicalOutcome; prep: PreparedExport; r: PairReport; refsOf: (id: string) => string }) {
  const lang = prep.ctx.lang;
  const s = x.supports[0];
  const serColor = x.seriousness === "documented_contraindication" || x.seriousness === "explicit_serious_warning" ? EV.label : C.muted;
  const affected = x.affected_drug_id === r.drug_a.id ? r.drug_a : x.affected_drug_id === r.drug_b.id ? r.drug_b : null;
  const refs = Array.from(new Set(x.supports.map((p) => (p.evidence_record_id ? refsOf(p.evidence_record_id) : "")).filter(Boolean)));
  return (
    <View wrap={false} style={{ borderWidth: 0.6, borderColor: C.hair, borderLeftWidth: 2.4, borderLeftColor: EV.label, padding: 6, marginBottom: 5 }}>
      <View style={{ flexDirection: "row", flexWrap: "wrap", marginBottom: 2 }}>
        <Chip color={EV.label}>{pick(LEVEL_OF[x.effect_level], lang)}</Chip>
        <Chip color={EV.documented}>{pick(STATUS_OF[x.evidence_status], lang)}</Chip>
        <Chip color={serColor}>{pick(SERIOUSNESS_OF[x.seriousness], lang)}</Chip>
      </View>
      <Text style={{ fontWeight: 600, fontSize: 9.4, color: C.navy }}>
        {bi(x.label, lang)}{affected ? ` · ${drugName(affected, lang)}` : ""}
        <Text style={{ fontFamily: FONT.mono, fontSize: 6.8, color: C.navy3 }}>{refs.length ? ` ${refs.join(" ")}` : ""}</Text>
      </Text>
      <Text style={[st.tiny, { marginTop: 1 }]}>{bi(x.explanation, lang)} {bi(x.seriousness_basis, lang)}</Text>
      {s ? (
        <View style={{ marginTop: 3 }}>
          <Text style={{ fontFamily: FONT.serif, fontStyle: "italic", fontSize: 8.4, color: C.ink, lineHeight: 1.4 }}>“{clean(s.excerpt)}”</Text>
          <View style={{ marginTop: 1 }}>
            <MonoLines text={`${clean(s.source_name)}${s.section ? ` · ${clean(s.section)}` : ""} · ${s.extraction_method}${x.supports.length > 1 ? ` · +${x.supports.length - 1}` : ""}`}
              width={CONTENT_WIDTH - 16} size={6.2} color={C.muted} />
          </View>
        </View>
      ) : null}
    </View>
  );
}
