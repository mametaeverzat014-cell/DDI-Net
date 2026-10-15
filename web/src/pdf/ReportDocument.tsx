// The PDF report: an A4 cover page followed by one flowing body (pair or
// multi-drug). Everything shown is read from the prepared export — the API
// payload(s) the page already held, their recorded provenance, and the moment
// of export. Where the payload has no value, the report says so; it never
// substitutes one.
import { Fragment, type ReactNode } from "react";
import { Document, Page, Text, View } from "@react-pdf/renderer";
import type { MechanismGraph, MultiReport, PairReport } from "../data/v3";
import { pick, type Bi, type Lang } from "../i18n";
import { CATEGORY_LABEL, KIND_TIER, RELATION_LABEL, REVIEW_REASON, ROLE_LABEL } from "../components/v3/evidenceStyle";
import { frozen } from "../data/frozen";
import { evidenceCountsText, type Excerpt, type SourceDoc } from "../data/evidenceGroups";
import { fillPlain, GLOSSARY, METRIC_NOTES, needsPooledNote, POOLED_NOTE, SCORE_EXPLAINER } from "../data/plainLanguage";
import { fmtCalibrated, fmtRaw } from "../data/scoreFormat";
import { studyCounts } from "../data/studyCounts";
import {
  bi, drugNames, FROZEN, headerRightText, isSynthetic, KIND_COLOR, machineSummary, multiCounts, pairBrief, pairFacts, patternLabel, problemSources, refLabels,
  sortedPairs, sourceLabel, sourceStatus, STATUS_COLOR, STATUS_ORDER, statusHint, statusLabel, statusLegendItems, t, type BriefItem,
} from "./content";
import { Bullets, Card, Chip, Dot, Eyebrow, JsonBox, KV, MonoLines, RunningFooter, RunningHeader, SafeText, SectionTitle, Seg, SubTitle, Table, Url } from "./components";
import { colPoints, st, tint, type Col } from "./styles";
import {
  CoverMotif, DotSwatch, LineSwatch, MechanismFigure, NetworkFigure, PairMatrixFigure, PathwayMatrixFigure, RelianceChart,
} from "./Diagrams";
import { diagramData } from "./diagram";
import { chunkText, clean, countWords, drugName, humanDateTime, int } from "./format";
import { STATUS_CODE, type StringKey } from "./strings";
import { C, CONTENT_WIDTH, DRUG_COLOR, EV, FONT, PAGE, REL, SIZE } from "./theme";
import type { FetchMeta } from "../data/v3";
import type { PreparedExport } from "./types";

type Tr = (k: StringKey, vars?: Record<string, string | number>) => string;

// ===================================================================== root ==

export function ReportDocument({ prep }: { prep: PreparedExport }) {
  const { input, ctx } = prep;
  const lang = ctx.lang;
  const tr: Tr = (k, vars) => t(k, lang, vars);
  const names = drugNames(input, lang);
  const title = input.kind === "pair" ? tr("title") : tr("titleMulti");
  const headerRight = headerRightText(input, lang);
  return (
    <Document
      title={`${title} — ${names}`}
      author="DDI-Net 3.0"
      subject={`${title}. ${tr("footerLeft")}. ${prep.reportId}`}
      keywords="drug-drug interaction, DDI-Net, BIO-GINE, research report, evidence, mechanism"
      creator="DDI-Net web — in-browser PDF export"
      producer="@react-pdf/renderer"
      language={lang}
    >
      <Cover prep={prep} tr={tr} />
      <Page size="A4" style={st.page} wrap>
        <RunningHeader left={tr("headerLeft")} right={headerRight} />
        <RunningFooter left={tr("footerLeft")} center={prep.reportId} pageText={(n, total) => tr("page", { n, t: total })} />
        {input.kind === "pair"
          ? <PairBody prep={prep} report={input.report.data} graph={input.graph?.data ?? null} tr={tr} />
          : <MultiBody prep={prep} m={input.report.data} tr={tr} />}
      </Page>
    </Document>
  );
}

// ==================================================================== cover ==

function Cover({ prep, tr }: { prep: PreparedExport; tr: Tr }) {
  const { input, ctx } = prep;
  const lang = ctx.lang;
  const many = input.kind === "multi" && input.report.data.drugs.length > 4;
  const bandH = input.kind === "pair" ? 292 : many ? 214 : 246;
  // The cover is one page: with many drugs each name gets one or two lines here
  // (shortened with "…"); section 2 and the tables print every name in full.
  const coverName = (x: string, max: number) => (input.kind === "multi" && x.length > max ? `${x.slice(0, max - 1).trimEnd()}…` : x);
  const meta = input.report.meta;
  const drugs = input.kind === "pair" ? [input.report.data.drug_a, input.report.data.drug_b] : input.report.data.drugs;
  const serverGenerated = input.report.data.generated_at;
  const modelLine = input.kind === "pair"
    ? `${input.report.data.model.model} · ${input.report.data.model.checkpoint} · ${tr("seed0")}`
    : tr("multiModel", { ck: frozen.checkpoint.seed0_run_id });
  const subtitle = input.kind === "pair"
    ? `${drugName(drugs[0], lang)} + ${drugName(drugs[1], lang)}`
    : `${countWords(drugs.length, "drug", lang)} · ${countWords(input.report.data.pairs.length, "pair", lang)}`;
  return (
    <Page size="A4" style={{ fontFamily: FONT.sans, backgroundColor: C.white, color: C.ink }}>
      <View style={{ height: bandH, backgroundColor: C.navy, position: "relative" }}>
        <CoverMotif seed={prep.payloadSha256} width={PAGE.width} height={bandH} />
        <View style={{ paddingHorizontal: PAGE.marginX, paddingTop: 54 }}>
          <Text style={{ fontFamily: FONT.mono, fontSize: 8, color: "#7CC4BC" }}>{tr("brand")}</Text>
          <Text style={{ fontSize: 8.6, color: "#B8C6DA", marginTop: 4 }}>{tr("brandLine")}</Text>
          <Text style={{ fontFamily: FONT.serif, fontWeight: 600, fontSize: SIZE.h1, color: C.white, marginTop: input.kind === "pair" ? 58 : many ? 24 : 36, lineHeight: 1.12, maxWidth: 420 }}>{input.kind === "pair" ? tr("title") : tr("titleMulti")}</Text>
          <Text style={{ fontSize: 13, color: "#D6E0EE", marginTop: 12 }}>{subtitle}</Text>
        </View>
      </View>

      <View style={{ paddingHorizontal: PAGE.marginX, paddingTop: 24 }}>
        {isSynthetic(prep) ? <SyntheticBanner tr={tr} /> : null}
        <Eyebrow>{tr("drugsAnalyzed")}</Eyebrow>
        <View style={{ flexDirection: "row", flexWrap: "wrap", marginTop: 8, marginHorizontal: -4 }}>
          {drugs.map((d, i) => {
            const color = input.kind === "pair" ? DRUG_COLOR[i === 0 ? "a" : "b"] : C.navy3;
            const tag = input.kind === "pair" ? (i === 0 ? "A" : "B") : String(i + 1);
            const compact = drugs.length > 2;
            return (
              <View key={d.id} wrap={false} style={{ width: "50%", paddingHorizontal: 4, marginBottom: compact ? 5 : 7 }}>
                <View style={{ borderWidth: 0.6, borderColor: C.hair, borderLeftWidth: 2.6, borderLeftColor: color, borderRadius: 3, padding: compact ? 6 : 9, backgroundColor: C.tint, flexDirection: "row" }}>
                  <Text style={{ fontFamily: FONT.mono, fontSize: 8, color, width: 16 }}>{tag}</Text>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontFamily: FONT.serif, fontWeight: 600, fontSize: compact ? 10.5 : 13, color: C.navy }}>{coverName(drugName(d, lang), 34)}</Text>
                    {lang === "ru" && d.inn && !many ? <Text style={{ fontSize: 7.6, color: C.slate2, marginTop: 1 }}>{coverName(clean(d.inn), 44)}{d.name_ru && d.name_ru_is_transliteration ? ` · ${tr("nameRu").toLowerCase()} — ${tr("translit")}` : ""}</Text> : null}
                    <Text style={{ fontFamily: FONT.mono, fontSize: 7, color: C.muted, marginTop: 2 }}>{d.id}{d.groups ? ` · ${d.groups.replace(/\|/g, ", ")}` : ""}</Text>
                  </View>
                </View>
              </View>
            );
          })}
        </View>

        <View style={{ marginTop: 10 }}>
          <KV keyWidth={170} rows={[
            [tr("reportId"), <Text key="id" style={{ fontFamily: FONT.mono, fontSize: 8.2, color: C.navy }}>{prep.reportId}</Text>],
            [tr("generated"), humanDateTime(ctx.now, ctx.timeZone, lang)],
            [tr("generatedUtc"), ctx.now.toISOString()],
            [tr("modelVersion"), modelLine],
            [tr("reportVersion"), input.report.data.report_version],
            [tr("analysisTime"), serverGenerated],
            [tr("receivedAt"), meta?.receivedAt ?? tr("notRecorded")],
            [tr("apiOrigin"), meta ? originOf(meta.endpoint) : tr("notRecorded")],
            [tr("language"), tr("languageValue")],
          ]} />
        </View>

        <View wrap={false} style={{ marginTop: 14, flexDirection: "row" }}>
          <View style={{ width: "40%", paddingRight: 12 }}>
            <Eyebrow>{tr("contents")}</Eyebrow>
            {contents(prep, tr).map(([n, title]) => (
              <View key={n} style={{ flexDirection: "row", marginTop: 2.5 }}>
                <Text style={{ fontFamily: FONT.mono, fontSize: 7.2, color: C.teal, width: 14 }}>{n}</Text>
                <Text style={{ fontSize: 7.8, color: C.slate, flex: 1 }}>{title}</Text>
              </View>
            ))}
          </View>
          <View style={{ width: "60%", borderWidth: 0.8, borderColor: C.navy, borderLeftWidth: 3, borderRadius: 3, padding: 10 }}>
            <Text style={{ fontFamily: FONT.mono, fontSize: 7.2, color: C.navy }}>{tr("researchOnlyTitle").toUpperCase()}</Text>
            <Text style={{ fontSize: 8.4, color: C.slate, marginTop: 4, lineHeight: 1.45 }}>{tr("researchOnly")}</Text>
          </View>
        </View>
      </View>
      <Text style={{ position: "absolute", bottom: 30, left: PAGE.marginX, right: PAGE.marginX, fontSize: 6.8, color: C.muted, lineHeight: 1.4 }}>{tr("coverNote")}</Text>
    </Page>
  );
}

/** Section numbers: the glossary follows the limitations; Supplement S1 exists
 *  only for a pair report with evidence records. */
const glossaryNumber = (kind: "pair" | "multi") => (kind === "pair" ? "9" : "8");
const hasSupplement = (prep: PreparedExport) => prep.input.kind === "pair" && prep.input.report.data.evidence.length > 0;

function contents(prep: PreparedExport, tr: Tr): [string, string][] {
  const kind = prep.input.kind;
  const pair: StringKey[] = ["secSummary", "secDrugs", "secDocumented", "secMechanisms", "secModel", "secExplanation", "secSources", "secLimitations", "secGlossary"];
  const multi: StringKey[] = ["secSummary", "secMultiOverview", "secMultiNetwork", "secMultiPairs", "secMultiCoverage", "secSources", "secLimitations", "secGlossary"];
  const strip = (x: string) => x.replace(/^[^.]*\.\s*/, "");
  return [
    ...(kind === "pair" ? pair : multi).map((k, i) => [String(i + 1), tr(k)] as [string, string]),
    ...(hasSupplement(prep) ? [["S1", strip(tr("supplementTitle"))] as [string, string]] : []),
    ["A", strip(tr("secAppendix"))],
  ];
}

function originOf(u: string): string {
  try {
    return new URL(u).origin;
  } catch {
    return clean(u).slice(0, 80);
  }
}

// ===================================================================== pair ==

function PairBody({ prep, report: r, graph, tr }: { prep: PreparedExport; report: PairReport; graph: MechanismGraph | null; tr: Tr }) {
  const lang = prep.ctx.lang;
  const gn = glossaryNumber("pair");
  return (
    <>
      <PairSummary r={r} lang={lang} tr={tr} synthetic={isSynthetic(prep)} glossaryN={gn} />
      <DrugInfo r={r} lang={lang} tr={tr} />
      <Documented r={r} lang={lang} tr={tr} />
      <Mechanisms r={r} graph={graph} lang={lang} tr={tr} />
      <ModelSection r={r} lang={lang} tr={tr} />
      <ExplanationSection r={r} lang={lang} tr={tr} glossaryN={gn} />
      <SourcesSection prep={prep} lang={lang} tr={tr} />
      <Limitations lang={lang} tr={tr} apiLimits={r.limitations} disclaimer={bi(r.disclaimer, lang)} multi={false} />
      <Glossary n={gn} lang={lang} tr={tr} />
      {hasSupplement(prep) ? <Supplement r={r} lang={lang} tr={tr} /> : null}
      <Appendix prep={prep} tr={tr} />
    </>
  );
}

function BriefRow({ item, color }: { item: BriefItem; color: string }) {
  const refs = item.refs ? <Text style={{ fontFamily: FONT.mono, fontStyle: "normal", fontSize: 6.8, color: C.navy3 }}>{` ${item.refs}`}</Text> : null;
  if (item.quote !== undefined) {
    return (
      <View style={{ flexDirection: "row", marginBottom: 5 }}>
        <View style={{ width: 11 }}><Dot color={color} /></View>
        <View style={{ flex: 1 }}>
          {item.lead ? <Text style={{ fontSize: 7, color: C.muted, lineHeight: 1.3 }}>{item.lead}</Text> : null}
          <Text style={{ fontFamily: FONT.serif, fontStyle: "italic", fontSize: 9, color: C.ink, lineHeight: 1.42, marginTop: 1 }}>
            “{clean(item.quote)}”{refs}
          </Text>
        </View>
      </View>
    );
  }
  return (
    <View style={{ flexDirection: "row", marginBottom: 4.5 }}>
      <View style={{ width: 11 }}><Dot color={color} /></View>
      <Text style={[st.small, { flex: 1, color: C.slate }]}>{item.text}{refs}</Text>
    </View>
  );
}

function PairSummary({ r, lang, tr, synthetic, glossaryN }: { r: PairReport; lang: Lang; tr: Tr; synthetic: boolean; glossaryN: string }) {
  const f = pairFacts(r);
  const brief = pairBrief(r, lang);
  const color = STATUS_COLOR[r.evidence_status];
  const missing = problemSources(r.sources_checked);
  const m = r.model;
  const kinds: { title: string; hint: string; body: string; color: string }[] = [
    {
      title: tr("kindDocumented"), hint: tr("kindDocumentedHint"), color: EV.documented,
      body: r.evidence.length ? tr("kindCountDoc", { ld: f.nLabelDocs, lab: f.nLabel, db: f.nDb }) : tr("kindNoneFound"),
    },
    { title: tr("kindHypothesis"), hint: tr("kindHypothesisHint"), color: EV.hypothesis, body: tr("kindCountHyp", { n: f.hypotheses.length, p: f.nPathways }) },
    {
      title: tr("kindModel"), hint: tr("kindModelHint"), color: EV.model,
      body: !m.available ? `${tr("modelUnavailable")}${m.unavailable_reason ? ` — ${m.unavailable_reason}` : ""}`
        : m.abstain ? tr("kindModelAbstain") : tr("kindModelScore", { cal: fmtCalibrated(m.calibrated_model_score), reg: m.regime }),
    },
    {
      title: tr("kindMissing"), hint: tr("kindMissingHint"), color: EV.missing,
      body: missing.length ? missing.map((c) => `${sourceLabel(c.source, lang)}: ${sourceStatus(c.status, lang)}`).join("; ") : tr("kindNoMissing"),
    },
  ];
  const tile = (k: (typeof kinds)[number]) => (
    <View key={k.title} style={{ width: "50%", paddingHorizontal: 3 }}>
      <View style={{ borderWidth: 0.6, borderColor: C.hair, borderTopWidth: 2, borderTopColor: k.color, padding: 7, minHeight: 60, backgroundColor: C.white }}>
        <Text style={{ fontWeight: 600, fontSize: 8.4, color: k.color }}>{k.title}</Text>
        <Text style={{ fontSize: 8.4, color: C.ink, marginTop: 3, lineHeight: 1.35 }}>{k.body}</Text>
        <Text style={{ fontSize: 6.8, color: C.muted, marginTop: 3, lineHeight: 1.3 }}>{k.hint}</Text>
      </View>
    </View>
  );
  return (
    <>
      <SectionTitle n="1" title={tr("secSummary")} breakBefore={false} />
      {synthetic ? <SyntheticBanner tr={tr} /> : null}
      <Card accent={color} background={tint(color, 0.06)}>
        <Chip color={color} filled>{statusLabel(r.evidence_status, lang)}</Chip>
        <Text style={{ fontFamily: FONT.serif, fontSize: 12, color: C.navy, marginTop: 6, lineHeight: 1.3 }}>{bi(r.evidence_status_label, lang)}</Text>
        <Text style={[st.small, { marginTop: 4 }]}>{statusHint(r.evidence_status, lang)}</Text>
        <Text style={[st.mono, { marginTop: 4, fontSize: 6.6 }]}>{tr("notSeverity")}</Text>
      </Card>

      <View wrap={false} style={{ marginBottom: 8, paddingLeft: 9, borderLeftWidth: 2, borderLeftColor: C.navy }}>
        <Eyebrow color={C.navy}>{tr("briefTitle")}</Eyebrow>
        <Text style={{ fontFamily: FONT.serif, fontSize: 10.2, color: C.ink, marginTop: 3, lineHeight: 1.42 }}>{brief.headline}</Text>
      </View>

      <View wrap={false} minPresenceAhead={60}><Eyebrow>{tr("kindsTitle")}</Eyebrow></View>
      <View wrap={false} style={{ flexDirection: "row", marginTop: 5, marginHorizontal: -3, marginBottom: 6 }}>{kinds.slice(0, 2).map(tile)}</View>
      <View wrap={false} style={{ flexDirection: "row", marginHorizontal: -3, marginBottom: 6 }}>{kinds.slice(2).map(tile)}</View>

      {brief.parts.map((part) => {
        const c = part.kind === "missing" ? EV.missing : KIND_COLOR[part.kind];
        const [first, ...rest] = part.items;
        return (
          <Fragment key={part.id}>
            {/* the heading travels with its first item, so it never ends a page */}
            <View wrap={false} style={{ marginTop: 9 }}>
              <View style={{ flexDirection: "row", alignItems: "center", borderBottomWidth: 0.6, borderBottomColor: tint(c, 0.45), paddingBottom: 3, marginBottom: 5 }}>
                <View style={{ width: 3, height: 10, backgroundColor: c, marginRight: 6 }} />
                <Text style={{ fontWeight: 600, fontSize: SIZE.h3, color: C.navy }}>{part.title}</Text>
              </View>
              {first ? <BriefRow item={first} color={c} /> : null}
            </View>
            {rest.map((it, i) => <View key={i} wrap={false}><BriefRow item={it} color={c} /></View>)}
          </Fragment>
        );
      })}
      <Text style={[st.tiny, { marginTop: 4 }]}>{tr("glossaryPointer", { n: glossaryN })}</Text>
    </>
  );
}

function SyntheticBanner({ tr }: { tr: Tr }) {
  return (
    <View wrap={false} style={{ borderWidth: 1.2, borderColor: EV.missing, backgroundColor: tint(EV.missing, 0.08), borderRadius: 3, padding: 8, marginBottom: 8 }}>
      <Text style={{ fontWeight: 600, fontSize: 8.4, color: EV.missing, lineHeight: 1.4 }}>{tr("syntheticBanner")}</Text>
    </View>
  );
}

function DrugInfo({ r, lang, tr }: { r: PairReport; lang: Lang; tr: Tr }) {
  const cols: Col[] = [{ title: tr("field"), width: 1.25 }, { title: `A · ${drugName(r.drug_a, lang)}`, width: 1 }, { title: `B · ${drugName(r.drug_b, lang)}`, width: 1 }];
  const cov = (id: string) => {
    const c = r.mechanism.coverage[id];
    return c ? `${c.target ?? 0} / ${c.enzyme ?? 0} / ${c.transporter ?? 0} / ${c.carrier ?? 0}` : "—";
  };
  const both = <T,>(f: (d: PairReport["drug_a"], side: "a" | "b") => T) => [f(r.drug_a, "a"), f(r.drug_b, "b")];
  const mono = (s: string) => <Text style={{ fontFamily: FONT.mono, fontSize: 7.2, color: C.ink }}>{s}</Text>;
  const rows: ReactNode[][] = [
    [tr("nameEn"), ...both((d) => (d.inn ? clean(d.inn) : tr("noInn")))],
    [tr("nameRu"), ...both((d) => (d.name_ru ? `${clean(d.name_ru)}${d.name_ru_is_transliteration ? ` (${tr("translit")})` : ""}` : "—"))],
    [tr("drugbankId"), ...both((d) => mono(d.id))],
    [tr("groups"), ...both((d) => (d.groups ? d.groups.replace(/\|/g, ", ") : "—"))],
    [tr("drugType"), ...both((d) => d.drug_type || "—")],
    [tr("query"), ...both((d) => (d.query ? mono(clean(d.query).slice(0, 100)) : "—"))],
    [tr("matchedOn"), ...both((d) => d.matched_on ?? "—")],
    [tr("coverage"), ...both((d) => mono(cov(d.id)))],
    [tr("modelSplit"), ...both((_, s) => (s === "a" ? r.model.split_a : r.model.split_b))],
    [tr("bioForModel"), ...both((_, s) => ((s === "a" ? r.model.biology_available_a : r.model.biology_available_b) ? tr("yes") : tr("no")))],
    [tr("drugbankPage"), ...both((d) => <Url key={d.id} url={`https://go.drugbank.com/drugs/${d.id}`} width={colPoints(cols, 1)} size={6.2} />)],
  ];
  return (
    <>
      <SectionTitle n="2" title={tr("secDrugs")} />
      <Table cols={cols} rows={rows} />
      <Text style={st.tiny}>{tr("drugProvenance")}</Text>
    </>
  );
}

/** Inner width of a Seg card (accent rule, right hairline, padding). */
const SEG_W = CONTENT_WIDTH - 2.4 - 0.6 - 18;
const KEY_W = 112;

function SegRow({ k, children }: { k: string; children: ReactNode }) {
  return (
    <View style={{ flexDirection: "row", paddingVertical: 1.6, borderTopWidth: 0.4, borderTopColor: C.hair }}>
      <Text style={{ width: KEY_W, fontSize: 7, color: C.muted, paddingRight: 6, lineHeight: 1.35 }}>{k}</Text>
      <View style={{ flex: 1 }}>{typeof children === "string" ? <Text style={{ fontSize: 7.2, color: C.ink, lineHeight: 1.35 }}>{children}</Text> : children}</View>
    </View>
  );
}

const docColor = (d: SourceDoc) => (d.kind === "database" ? EV.documented : d.excerpts.every((x) => x.category === "label_mention_no_effect_reported") ? EV.none : EV.label);
const excerptColor = (x: Excerpt) => (x.category === "database_interaction_record" ? EV.documented : x.category === "label_mention_no_effect_reported" ? EV.none : EV.label);

function DocBlock({ d, r, lang, tr }: { d: SourceDoc; r: PairReport; lang: Lang; tr: Tr }) {
  const first = d.records[0];
  const name = (id: string | null) => (id === r.drug_a.id ? drugName(r.drug_a, lang) : id === r.drug_b.id ? drugName(r.drug_b, lang) : id ?? "—");
  const vw = SEG_W - KEY_W - 6;
  const parts: ReactNode[] = [];
  parts.push(
    <View>
      <View style={{ flexDirection: "row", alignItems: "baseline" }}>
        <Text style={{ fontFamily: FONT.mono, fontSize: 8.4, color: C.navy, width: 24 }}>[{d.n}]</Text>
        <View style={{ flex: 1 }}>
          <Text style={{ fontWeight: 600, fontSize: 9.4, color: C.navy, lineHeight: 1.3 }}>
            {d.kind === "label" ? tr("labelDocTitle", { owner: name(d.ownerId) }) : tr("dbDocTitle")}
          </Text>
          <Text style={{ fontSize: 7.6, color: C.slate2, lineHeight: 1.35 }}>
            {d.kind === "label" ? tr("labelDocSub", { partner: name(d.mentionedId), k: d.excerpts.length }) : tr("dbDocSub", { k: d.records.length })}
          </Text>
        </View>
        <Text style={{ fontFamily: FONT.mono, fontSize: 6.4, color: C.muted }}>{tr("retrieved")} {first.retrieved_at}</Text>
      </View>
      <Text style={{ fontSize: 7, color: C.slate2, marginTop: 3, marginLeft: 24, lineHeight: 1.35 }}>
        {clean(first.source_name)}{first.source_version ? ` · ${clean(first.source_version)}` : ""}
      </Text>
      {d.kind === "label" ? <View style={{ marginLeft: 24, marginTop: 1 }}><MonoLines text={`${tr("splSetId")}: ${d.id}`} width={SEG_W - 24} size={6.4} /></View> : null}
    </View>,
  );
  for (const x of d.excerpts) {
    const e = x.records[0];
    const chunks = chunkText(clean(x.text));
    const dc = e.direction_check;
    const multi = d.excerpts.length > 1;
    parts.push(
      <View style={{ marginTop: 5, paddingTop: 5, borderTopWidth: 0.5, borderTopColor: C.hair }}>
        <View style={{ flexDirection: "row", alignItems: "center", flexWrap: "wrap" }}>
          {multi ? <Text style={{ fontFamily: FONT.mono, fontSize: 7.6, color: C.navy, width: 30 }}>{x.label}</Text> : null}
          <Chip color={excerptColor(x)}>{pick(CATEGORY_LABEL[x.category], lang)}</Chip>
          {e.direction === "not_verified" ? <Chip color={EV.missing}>{tr("dir_not_verified").split(":")[0]}</Chip> : null}
          <Text style={{ fontSize: 6.6, color: C.muted, marginLeft: 2 }}>{tr("sourceWords")} · {tr(`origin_${e.statement_origin}` as StringKey)}</Text>
        </View>
        {x.sections.length ? <Text style={{ fontSize: 7, color: C.slate2, marginTop: 3 }}>{tr("foundIn", { s: x.sections.join(" · ") })}</Text> : null}
        <Text style={{ fontFamily: FONT.serif, fontStyle: "italic", fontSize: 9.4, color: C.ink, marginTop: 3, lineHeight: 1.45 }}>
          “{chunks[0]}{chunks.length === 1 ? "”" : ""}
        </Text>
      </View>,
    );
    for (const [i, c] of chunks.slice(1).entries()) {
      parts.push(<Text style={{ fontFamily: FONT.serif, fontStyle: "italic", fontSize: 9.4, color: C.ink, lineHeight: 1.45 }}>{c}{i === chunks.length - 2 ? "”" : ""}</Text>);
    }
    if (lang === "ru" && x.textRu) {
      parts.push(
        <View style={{ marginTop: 3 }}>
          <Text style={{ fontSize: 6.6, color: C.muted }}>{tr("projectTranslation")}</Text>
          <Text style={{ fontSize: 8.8, color: C.slate, marginTop: 1, lineHeight: 1.45 }}>{clean(x.textRu)}</Text>
        </View>,
      );
    }
    if (x.sections.length > 1) parts.push(<Text style={{ fontSize: 7, color: C.slate2, marginTop: 2, lineHeight: 1.35 }}>{tr("repeatNote")}</Text>);
    if (d.kind === "database") {
      parts.push(
        <Text style={{ fontSize: 7.4, color: e.direction === "not_verified" ? EV.missing : C.slate2, marginTop: 3, lineHeight: 1.4 }}>
          {tr(`dir_${e.direction}` as StringKey)}{dc && dc.n_informative ? `. ${tr("directionCheck", { c: int(dc.n_consistent, lang), n: int(dc.n_informative, lang), p: dc.consistency === null ? "—" : `${(dc.consistency * 100).toFixed(1)}%` })}` : ""}
        </Text>,
      );
    }
  }
  // provenance of the document (per-record detail: Supplement S1)
  parts.push(<Text style={{ fontFamily: FONT.mono, fontSize: 6.2, color: C.muted, marginTop: 6, marginBottom: 1 }}>{tr("docProvenance").toUpperCase()}</Text>);
  if (first.source_url) parts.push(<SegRow k={tr("url")}><Url url={first.source_url} width={vw} size={6.4} /></SegRow>);
  const retrievalUrls = Array.from(new Set(d.records.map((e) => e.retrieval_url).filter((u): u is string => !!u)));
  for (const u of retrievalUrls) parts.push(<SegRow k={tr("retrievalUrl")}><Url url={u} width={vw} size={6.2} /></SegRow>);
  if (d.kind === "database") {
    parts.push(<SegRow k={tr("recordId")}><MonoLines text={d.records.map((e) => e.source_record_id ?? e.id).join("\n")} width={vw} size={6.4} /></SegRow>);
  }
  parts.push(<SegRow k={tr("retrieved")}>{Array.from(new Set(d.records.map((e) => e.retrieved_at))).join(", ")}</SegRow>);
  if (first.license) parts.push(<SegRow k={tr("license")}>{clean(first.license)}</SegRow>);
  const sev = Array.from(new Set(d.records.map((e) => e.source_severity).filter((s): s is string => !!s)));
  parts.push(<SegRow k={tr("severityBySource")}>{sev.length ? sev.map(clean).join("; ") : tr("severityNone")}</SegRow>);
  const quals = Array.from(new Set(d.records.flatMap((e) => e.qualifiers)));
  if (quals.length) {
    parts.push(<Text style={{ fontFamily: FONT.mono, fontSize: 6.2, color: C.muted, marginTop: 5, marginBottom: 1 }}>{tr("qualifiers").toUpperCase()}</Text>);
    for (const q of quals) {
      parts.push(
        <View style={{ flexDirection: "row", marginBottom: 1.5 }}>
          <Text style={{ width: 9, color: C.faint, fontSize: 7.2 }}>•</Text>
          <Text style={{ flex: 1, fontSize: 7.2, color: C.slate, lineHeight: 1.4 }}>{clean(q)}</Text>
        </View>,
      );
    }
  }
  return <Seg accent={docColor(d)} parts={parts} />;
}

function Documented({ r, lang, tr }: { r: PairReport; lang: Lang; tr: Tr }) {
  const g = pairFacts(r).groups;
  const cols: Col[] = [{ title: tr("source"), width: 1.3 }, { title: tr("status"), width: 1 }, { title: tr("detail"), width: 2.6 }];
  const dcols: Col[] = [
    { title: "#", width: 0.35 }, { title: tr("docCol"), width: 1.7 }, { title: tr("docIdCol"), width: 1.75 },
    { title: tr("versionCol"), width: 1.25 }, { title: tr("excerptsCol"), width: 0.55, align: "right" }, { title: tr("sectionsCol"), width: 1.5 },
  ];
  const name = (id: string | null) => (id === r.drug_a.id ? drugName(r.drug_a, lang) : id === r.drug_b.id ? drugName(r.drug_b, lang) : id ?? "—");
  return (
    <>
      <SectionTitle n="3" title={tr("secDocumented")} lead={tr("evidenceIntro")} />
      {r.evidence.length === 0 ? (
        <Card accent={EV.none}>
          <Text style={{ fontWeight: 600, color: C.navy }}>{tr("noEvidenceTitle")}</Text>
          <Text style={[st.p, { marginTop: 3 }]}>{tr("sumNoEvidence")}</Text>
        </Card>
      ) : (
        <>
          <View wrap={false} style={{ marginBottom: 6 }}>
            <Text style={{ fontWeight: 600, fontSize: 8.6, color: C.navy, lineHeight: 1.4 }}>{evidenceCountsText(g.counts, lang)}</Text>
            {g.counts.mergedRepeats > 0 ? <Text style={[st.tiny, { marginTop: 2 }]}>{tr("briefOneSource")}</Text> : null}
          </View>
          <SubTitle first>{tr("docTable")}</SubTitle>
          <Table cols={dcols} rows={g.docs.map((d) => {
            const sections = Array.from(new Set(d.excerpts.flatMap((x) => x.sections)));
            return [
              <Text key="n" style={{ fontFamily: FONT.mono, fontSize: 7.2, color: C.navy }}>[{d.n}]</Text>,
              d.kind === "label" ? tr("labelDocTitle", { owner: name(d.ownerId) }) : tr("dbDocTitle"),
              <MonoLines key="i" text={d.kind === "label" ? d.id : d.records.map((e) => e.source_record_id ?? e.id).join("\n")} width={colPoints(dcols, 2)} size={6.2} />,
              d.records[0].source_version ? <SafeText key="v" text={clean(d.records[0].source_version)} width={colPoints(dcols, 3)} /> : "—",
              String(d.excerpts.length),
              sections.length ? sections.join("; ") : "—",
            ];
          })} />
          {g.docs.map((d) => <DocBlock key={d.id} d={d} r={r} lang={lang} tr={tr} />)}
        </>
      )}
      {r.conflicts.length ? (
        <>
          <SubTitle color={EV.missing}>{tr("conflicts")}</SubTitle>
          {r.conflicts.map((c, i) => (
            <Card key={i} accent={EV.missing}>
              <Text style={st.p}>{bi(c.description, lang)}</Text>
              <Text style={[st.mono, { marginTop: 3 }]}>{refLabels(r, c.record_ids).join(" ")}</Text>
            </Card>
          ))}
        </>
      ) : null}
      <SubTitle>{tr("sourcesChecked")}</SubTitle>
      <Table cols={cols} rows={r.sources_checked.map((c) => [
        sourceLabel(c.source, lang),
        <Text key="s" style={{ fontSize: 7.6, color: c.status === "unavailable" || c.status === "disabled" ? EV.missing : C.ink }}>{sourceStatus(c.status, lang)}</Text>,
        c.detail ? <MonoLines key="d" text={c.detail} width={colPoints(cols, 2)} size={6.4} /> : "—",
      ])} />
    </>
  );
}

function Legend({ items }: { items: { swatch: ReactNode; label: string }[] }) {
  return (
    <View style={{ flexDirection: "row", flexWrap: "wrap", marginTop: 4, marginBottom: 2 }}>
      {items.map((it, i) => (
        <View key={i} style={{ flexDirection: "row", alignItems: "center", marginRight: 10, marginBottom: 3 }}>
          {it.swatch}
          <Text style={{ fontSize: 6.8, color: C.slate2, marginLeft: 3 }}>{it.label}</Text>
        </View>
      ))}
    </View>
  );
}

function Mechanisms({ r, graph, lang, tr }: { r: PairReport; graph: MechanismGraph | null; lang: Lang; tr: Tr }) {
  const data = diagramData(r, graph, { a: drugName(r.drug_a, lang), b: drugName(r.drug_b, lang) });
  const hyps = r.mechanism.findings;
  const rel = (k: string) => (RELATION_LABEL[k] ? pick(RELATION_LABEL[k], lang) : k);
  const role = (k: string) => (ROLE_LABEL[k] ? pick(ROLE_LABEL[k], lang) : k);
  const name = (id: string | null) => (id === r.drug_a.id ? drugName(r.drug_a, lang) : id === r.drug_b.id ? drugName(r.drug_b, lang) : id ?? "—");
  const hasGraph = data.links.length > 0;
  const hcols: Col[] = [
    { title: "#", width: 0.35 }, { title: tr("protein"), width: 1.5 }, { title: tr("configuration"), width: 2.1 },
    { title: tr("rolesAB"), width: 1.25 }, { title: tr("basis"), width: 1.6 },
  ];
  const pcols: Col[] = [{ title: "R", width: 0.35 }, { title: tr("pathway"), width: 2.3 }, { title: "Reactome", width: 1.6 }, { title: tr("proteinsInPathway"), width: 0.6, align: "right" }, { title: tr("viaA"), width: 1.1 }, { title: tr("viaB"), width: 1.1 }];
  const viaOf = new Map(r.mechanism.shared_pathways.map((p) => [p.id, p]));
  const proteinsWithText = Array.from(new Map(hyps.filter((f) => f.pattern !== "shared_annotation").map((f) => [f.protein.uniprot, f.protein])).values());
  return (
    <>
      <SectionTitle n="4" title={tr("secMechanisms")} lead={bi(r.mechanism.note, lang)} />
      {hasGraph ? (
        <>
          <SubTitle first>{tr("diagramTitle")}</SubTitle>
          <Text style={[st.tiny, { marginBottom: 6 }]}>{data.source === "graph" ? tr("diagramFromGraph") : tr("diagramFromReport")}</Text>
          <MechanismFigure data={data} lang={lang} />
          <Legend items={[
            ...(["enzyme", "transporter", "carrier", "target"] as const).map((k) => ({ swatch: <LineSwatch color={REL[k]} />, label: rel(k) })),
            { swatch: <DotSwatch color={EV.hypothesis} ring />, label: tr("legendHypothesis") },
            { swatch: <LineSwatch color={EV.documented} dash="4 2.5" />, label: tr("legendDocumented") },
          ]} />
          <Text style={[st.tiny, { marginTop: 1 }]}>{tr("rolesLegend")}</Text>
          {data.documented !== "none" ? <Text style={[st.tiny, { marginTop: 2 }]}>{data.documented === "verified_order" ? tr("diagramDirectionVerified") : tr("diagramDirection")}</Text> : null}
          {data.truncated > 0 ? <Text style={[st.tiny, { marginTop: 2 }]}>{tr("diagramTruncated", { n: data.truncated })}</Text> : null}
        </>
      ) : (
        <Text style={st.p}>{tr("noMechanismData")}</Text>
      )}

      <SubTitle>{tr("hypotheses")}</SubTitle>
      {hyps.length === 0 ? <Text style={st.p}>{tr("sumNoHyp")}</Text> : (
        <Table cols={hcols} rows={hyps.map((f, i) => {
          const ann = f.annotation_ids.map((id) => r.mechanism.annotations[id]).filter(Boolean);
          const pmids = Array.from(new Set(ann.flatMap((a) => a.pmids)));
          const sources = Array.from(new Set(ann.map((a) => `${a.source_name} ${a.source_version}`)));
          return [
            <Text key="n" style={{ fontFamily: FONT.mono, fontSize: 7.4, color: EV.hypothesis }}>H{i + 1}</Text>,
            <View key="p">
              <Text style={{ fontFamily: FONT.mono, fontSize: 7.6, color: C.navy }}>{f.protein.gene}</Text>
              <Text style={{ fontSize: 6.8, color: C.slate2 }}>{clean(f.protein.name)}</Text>
              <Text style={{ fontFamily: FONT.mono, fontSize: 6.2, color: C.muted }}>{f.protein.uniprot} · {rel(f.relation)}</Text>
            </View>,
            <View key="c">
              <Text style={{ fontSize: 7.4, color: C.ink }}>{patternLabel(f.pattern, lang)}</Text>
              {f.actor_drug_id ? <Text style={{ fontSize: 6.8, color: EV.hypothesis, marginTop: 1 }}>{tr("hypDirection", { x: name(f.actor_drug_id), y: name(f.affected_drug_id) })}</Text> : null}
              {f.consistent_with_records.length ? <Text style={{ fontSize: 6.6, color: EV.documented, marginTop: 1 }}>{tr("consistentWith", { r: refLabels(r, f.consistent_with_records).join(" ") || "—" })}</Text> : null}
            </View>,
            <View key="r">
              <Text style={{ fontSize: 7.2, color: C.ink }}>{`A: ${f.roles_a.map(role).join(", ") || "—"}`}</Text>
              <Text style={{ fontSize: 7.2, color: C.ink }}>{`B: ${f.roles_b.map(role).join(", ") || "—"}`}</Text>
            </View>,
            <View key="b">
              <Text style={{ fontSize: 6.6, color: C.slate2 }}>{sources.join("; ")}</Text>
              {pmids.length ? <Text style={{ fontFamily: FONT.mono, fontSize: 6.2, color: C.navy3, marginTop: 1 }}>PMID {pmids.join(", ")}</Text> : null}
            </View>,
          ];
        })} />
      )}

      {data.pathways.length ? (
        <>
          <SubTitle>{tr("pathways")} · {r.mechanism.n_shared_pathways_total}</SubTitle>
          <Text style={[st.tiny, { marginBottom: 5 }]}>{tr("pathwaysShown", { k: data.pathways.length, n: r.mechanism.n_shared_pathways_total })} {tr("matrixLegend")}</Text>
          <PathwayMatrixFigure data={data} lang={lang} />
          <Legend items={[
            { swatch: <DotSwatch color={DRUG_COLOR.a} />, label: tr("sideA") },
            { swatch: <DotSwatch color={DRUG_COLOR.b} />, label: tr("sideB") },
            { swatch: <DotSwatch color={C.slate} />, label: tr("sideShared") },
          ]} />
          <Table cols={pcols} rows={data.pathways.map((p) => {
            const via = viaOf.get(p.id);
            return [
              <Text key="r" style={{ fontFamily: FONT.mono, fontSize: 7.2, color: C.navy }}>{p.ref}</Text>,
              clean(p.name),
              <Url key="u" url={`https://reactome.org/content/detail/${p.id}`} width={colPoints(pcols, 2)} size={6} />,
              p.n === null ? "—" : String(p.n),
              via ? via.via_a.join(", ") : "—",
              via ? via.via_b.join(", ") : "—",
            ];
          })} />
        </>
      ) : null}

      {proteinsWithText.length ? (
        <>
          <SubTitle>{tr("proteinNotes")}</SubTitle>
          {proteinsWithText.map((p) => (
            <View key={p.uniprot} wrap={false} style={{ flexDirection: "row", marginBottom: 4 }}>
              <Text style={{ fontFamily: FONT.mono, fontSize: 7.4, color: C.navy, width: 60 }}>{p.gene}</Text>
              <Text style={[st.small, { flex: 1 }]}>{bi(p.plain, lang)}</Text>
            </View>
          ))}
        </>
      ) : null}
    </>
  );
}

/** Which test set the measured figures come from, in plain words (frozen study counts). */
function regimeNotes(m: PairReport["model"]): Bi[] {
  const out: Bi[] = [];
  if (m.regime === "S1") out.push(METRIC_NOTES.s1);
  else {
    out.push(m.regime === "S3" ? METRIC_NOTES.s3 : METRIC_NOTES.pooledS2);
    if (m.measured_performance.some((p) => p.view.includes("both annotated"))) out.push(METRIC_NOTES.bothAnnotated);
    out.push(METRIC_NOTES.datasetVsPair);
  }
  return out;
}

function studyVars(lang: Lang): Record<string, string | number> {
  const sc = studyCounts();
  return { pooled: int(sc.pooled, lang), s2: int(sc.s2, lang), s3: int(sc.s3, lang), seeds: sc.seeds, bothAnnotated: int(sc.bothAnnotated, lang) };
}

function ModelSection({ r, lang, tr }: { r: PairReport; lang: Lang; tr: Tr }) {
  const m = r.model;
  const rel = m.modality_reliance ?? null;
  const vars = studyVars(lang);
  const tile = (label: string, value: string, opts?: { strike?: boolean; color?: string; mono?: boolean }) => (
    <View style={{ flex: 1, borderWidth: 0.6, borderColor: C.hair, padding: 7, marginRight: 5, backgroundColor: C.tint }}>
      <Text style={{ fontFamily: FONT.mono, fontSize: 6, color: C.muted }}>{label.toUpperCase()}</Text>
      <Text style={{ fontFamily: opts?.mono === false ? FONT.sans : FONT.mono, fontSize: opts?.mono === false ? 8.4 : 13, color: opts?.color ?? C.navy, marginTop: 3, textDecoration: opts?.strike ? "line-through" : "none" }}>{value}</Text>
    </View>
  );
  const pcols: Col[] = [{ title: tr("metric"), width: 0.7 }, { title: tr("meanSd"), width: 1.05 }, { title: tr("seeds"), width: 0.55, align: "right" }, { title: tr("testSetCol"), width: 2.2 }, { title: tr("source"), width: 2.4 }];
  const relAbsentReason = !m.available ? tr("modelUnavailable") : m.abstain ? tr("rel_training_label_seen") : tr("relianceAbsentApi");
  const usable = m.available && !m.abstain;
  const explainer = [
    fillPlain(pick(SCORE_EXPLAINER.raw, lang), { raw: fmtRaw(m.raw_model_score) }),
    fillPlain(pick(SCORE_EXPLAINER.calibrated, lang), { cal: fmtCalibrated(m.calibrated_model_score) }),
    pick(SCORE_EXPLAINER.notProbability, lang),
    pick(SCORE_EXPLAINER.can, lang),
    pick(SCORE_EXPLAINER.cannot, lang),
  ];
  const valPair = m.split_a === "val" || m.split_b === "val";
  return (
    <>
      <SectionTitle n="5" title={tr("secModel")} />
      {!m.available ? (
        <Card accent={EV.missing}>
          <Text style={{ fontWeight: 600, color: C.navy }}>{tr("modelUnavailable")}</Text>
          <Text style={[st.p, { marginTop: 2 }]}>{m.unavailable_reason ?? tr("notRecorded")}</Text>
        </Card>
      ) : (
        <View wrap={false} style={{ marginBottom: 8 }}>
          <View style={{ flexDirection: "row", marginRight: -5 }}>
            {tile(tr("calibrated"), fmtCalibrated(m.calibrated_model_score), { strike: m.abstain, color: m.abstain ? C.faint : EV.model })}
            {tile(tr("raw"), fmtRaw(m.raw_model_score), { strike: m.abstain, color: m.abstain ? C.faint : C.navy })}
            {tile(tr("regime"), m.regime)}
            {tile(tr("reliability"), tr(`rel_${m.reliability}` as StringKey), { mono: false, color: m.abstain ? EV.missing : C.ink })}
          </View>
          <Text style={[st.tiny, { marginTop: 3 }]}>{tr("roundedNote")}</Text>
        </View>
      )}
      <KV rows={[
        [tr("modelIdentity"), `${m.model} · ${m.checkpoint} · ${tr("seed0")}`],
        [tr("regime"), tr(`regime_${m.regime}` as StringKey)],
        [tr("splits"), `${m.split_a} / ${m.split_b}`],
        [tr("trainingLabelSeen"), m.training_label_seen ? tr("yes") : tr("no")],
        [tr("bioForModel"), `A: ${m.biology_available_a ? tr("yes") : tr("no")} · B: ${m.biology_available_b ? tr("yes") : tr("no")}`],
      ]} />

      {usable ? (
        <>
          <View style={{ height: 8 }} />
          <Seg accent={EV.model} background={C.white} parts={[
            <Text key="t" style={{ fontWeight: 600, fontSize: 8.8, color: C.navy, marginBottom: 2 }}>{pick(SCORE_EXPLAINER.title, lang)}</Text>,
            ...explainer.map((x, i) => (
              <View key={i} style={{ flexDirection: "row", marginBottom: 2.5 }}>
                <Text style={{ width: 9, fontSize: 8, color: EV.model }}>•</Text>
                <Text style={[st.small, { flex: 1, color: C.slate }]}>{x}</Text>
              </View>
            )),
          ]} />
        </>
      ) : (
        <View wrap={false} style={{ marginTop: 8 }}>
          <Card accent={EV.model} background={C.white}>
            <Text style={{ fontWeight: 600, fontSize: 8.6, color: C.navy }}>{tr("interpretationTitle")}</Text>
            <Text style={[st.small, { marginTop: 3 }]}>{tr("interpretation")}</Text>
          </Card>
        </View>
      )}

      <SubTitle>{tr("measuredTitle")}</SubTitle>
      {m.measured_performance.length ? (
        <Table cols={pcols} rows={m.measured_performance.map((p) => [
          p.metric,
          <Text key="v" style={{ fontFamily: FONT.mono, fontSize: 7.2 }}>{`${p.mean.toFixed(3)} ± ${p.sd.toFixed(3)}`}</Text>,
          String(p.n_seeds), clean(p.view),
          <MonoLines key="s" text={p.source} width={colPoints(pcols, 4)} size={6} />,
        ])} />
      ) : null}
      <Bullets size={SIZE.small} color={EV.model} items={[
        ...regimeNotes(m).map((n) => fillPlain(pick(n, lang), vars)),
        ...(valPair ? [tr("briefValPair")] : []),
      ]} />

      <SubTitle>{tr("uncertainty")}</SubTitle>
      {m.available ? <Text style={[st.small, { marginBottom: 6 }]}>{tr("gapNoCi")}</Text> : <Text style={st.small}>{tr("modelUnavailable")}</Text>}

      <SubTitle>{tr("reliance")}</SubTitle>
      {rel && !m.abstain ? (
        <>
          <Text style={[st.tiny, { marginBottom: 5 }]}>{tr("relianceLead")} {tr("relianceParen")}</Text>
          <RelianceChart r={rel} lang={lang} />
          <Text style={[st.tiny, { marginTop: 3 }]}>{tr("raw")}: {fmtRaw(rel.baseline_raw)}</Text>
          {rel.baseline_raw > 0.999 || rel.baseline_raw < 0.001 ? <Text style={[st.tiny, { color: EV.missing, marginTop: 2 }]}>{tr("relianceSaturated")}</Text> : null}
          <Text style={[st.tiny, { marginTop: 2 }]}>{bi(rel.interpretation, lang)}</Text>
          <Text style={[st.tiny, { marginTop: 2 }]}>{tr("relianceValidated", { n: int(rel.validation.n_rows, lang), d: rel.validation.max_abs_diff.toExponential(1) })}</Text>
          <Text style={[st.mono, { marginTop: 1, fontSize: 6 }]}>{tr("method")}: {clean(rel.method)}</Text>
        </>
      ) : (
        <Text style={st.small}>{tr("relianceAbsent", { r: relAbsentReason })}</Text>
      )}

      {m.notes.length ? (
        <>
          <SubTitle>{tr("modelNotes")}</SubTitle>
          <Bullets items={m.notes.map((n) => bi(n, lang))} color={EV.model} size={SIZE.small} />
        </>
      ) : null}
    </>
  );
}

function ExplanationSection({ r, lang, tr, glossaryN }: { r: PairReport; lang: Lang; tr: Tr; glossaryN: string }) {
  return (
    <>
      <SectionTitle n="6" title={tr("secExplanation")} lead={`${tr("explanationIntro")} ${tr("readerNote6", { n: glossaryN })}`} />
      {r.explanation.sections.map((sec) => (
        <Fragment key={sec.id}>
          <SubTitle>{bi(sec.title, lang)}</SubTitle>
          {sec.statements.map((s, i) => {
            const refs = refLabels(r, s.refs);
            return (
              <View key={i} wrap={false} style={{ flexDirection: "row", marginBottom: 4.5 }}>
                <View style={{ width: 70 }}><Chip color={KIND_COLOR[s.kind]}>{pick(KIND_TIER[s.kind].label, lang)}</Chip></View>
                <Text style={[st.small, { flex: 1, color: s.kind === "caveat" ? C.muted : C.slate }]}>
                  {bi(s.text, lang)}
                  {refs.length ? <Text style={{ fontFamily: FONT.mono, fontSize: 6.6, color: C.navy3 }}>{` ${refs.join(" ")}`}</Text> : null}
                  {needsPooledNote(s.text, r.model.regime) ? <Text style={{ color: EV.missing }}>{` ${pick(POOLED_NOTE, lang)}`}</Text> : null}
                </Text>
              </View>
            );
          })}
        </Fragment>
      ))}
      <Text style={[st.mono, { marginTop: 4, fontSize: 6.4 }]}>{tr("method")}: {clean(r.explanation.method)}</Text>
    </>
  );
}

function Glossary({ n, lang, tr }: { n: string; lang: Lang; tr: Tr }) {
  const vars = studyVars(lang);
  // A definition list of atomic rows, not a Table: the rows are page-level
  // siblings and break between pages one by one (see components.tsx, PAGE BREAKS).
  const row = (i: number) => (
    <View key={i} wrap={false} style={{
      flexDirection: "row", paddingVertical: 4, paddingHorizontal: 4, backgroundColor: i % 2 ? C.tint : C.white,
      borderLeftWidth: 0.5, borderRightWidth: 0.5, borderColor: C.rule, borderTopWidth: 0.5, borderTopColor: i ? C.hair : C.rule,
      borderBottomWidth: i === GLOSSARY.length - 1 ? 0.5 : 0, borderBottomColor: C.rule,
    }}>
      <Text style={{ width: 118, paddingRight: 8, fontWeight: 600, fontSize: 7.6, color: C.navy, lineHeight: 1.35 }}>{pick(GLOSSARY[i].term, lang)}</Text>
      <Text style={{ flex: 1, fontSize: 7.6, color: C.slate, lineHeight: 1.42 }}>{fillPlain(pick(GLOSSARY[i].text, lang), vars)}</Text>
    </View>
  );
  return (
    <>
      <SectionTitle n={n} title={tr("secGlossary")} lead={tr("glossaryIntro")} />
      {GLOSSARY.map((_, i) => row(i))}
    </>
  );
}

/** Supplement S1: every evidence record of the response, with full provenance. */
function Supplement({ r, lang, tr }: { r: PairReport; lang: Lang; tr: Tr }) {
  const g = pairFacts(r).groups;
  const vw = SEG_W - KEY_W - 6;
  return (
    <>
      <SectionTitle n="S1" title={tr("supplementTitle")} lead={tr("supplementIntro")} />
      {g.docs.flatMap((d) => d.excerpts.flatMap((x) => x.records.map((e, i) => {
        const ids = Object.entries(e.original_identifiers);
        const parts: ReactNode[] = [
          <View style={{ flexDirection: "row", alignItems: "baseline" }}>
            <Text style={{ fontFamily: FONT.mono, fontSize: 8, color: C.navy, width: 34 }}>{x.label}</Text>
            <View style={{ flex: 1 }}>
              <MonoLines text={e.id} width={SEG_W - 34} size={6.6} color={C.ink} />
              {i > 0 ? <Text style={{ fontSize: 6.8, color: EV.missing, marginTop: 1 }}>{tr("sameAs", { x: x.label })}</Text> : null}
            </View>
          </View>,
          <SegRow k={tr("category")}>{pick(CATEGORY_LABEL[e.category], lang)}</SegRow>,
        ];
        if (e.section) parts.push(<SegRow k={tr("section")}>{[e.section, ...(e.also_in_sections ?? [])].map(clean).join(" · ")}</SegRow>);
        parts.push(<SegRow k={tr("source")}>{`${clean(e.source_name)}${e.source_version ? ` · ${clean(e.source_version)}` : ""}`}</SegRow>);
        parts.push(<SegRow k={tr("recordId")}><MonoLines text={e.source_record_id ?? "—"} width={vw} size={6.4} /></SegRow>);
        if (ids.length) parts.push(<SegRow k={tr("identifiers")}><MonoLines text={ids.map(([k, v]) => `${k}: ${v}`).join("\n")} width={vw} size={6.2} /></SegRow>);
        if (e.source_url) parts.push(<SegRow k={tr("url")}><Url url={e.source_url} width={vw} size={6.2} /></SegRow>);
        if (e.retrieval_url) parts.push(<SegRow k={tr("retrievalUrl")}><Url url={e.retrieval_url} width={vw} size={6.2} /></SegRow>);
        parts.push(<SegRow k={tr("retrieved")}>{e.retrieved_at}</SegRow>);
        if (e.source_template) parts.push(<SegRow k={tr("templateKey")}><Text style={{ fontSize: 7, color: C.ink, lineHeight: 1.35 }}>{clean(e.source_template)}</Text></SegRow>);
        parts.push(<SegRow k={tr("direction")}>{tr(`dir_${e.direction}` as StringKey)}</SegRow>);
        if (e.license) parts.push(<SegRow k={tr("license")}>{clean(e.license)}</SegRow>);
        return <Seg key={e.id} accent={excerptColor(x)} background={C.white} parts={parts} />;
      })))}
    </>
  );
}

// ================================================================== sources ==

function provenanceRows(prep: PreparedExport, tr: Tr): [string, ReactNode][] {
  const { input, ctx } = prep;
  const w = CONTENT_WIDTH - 170 - 4;
  const metas: [string, FetchMeta | null | undefined][] = input.kind === "pair"
    ? [["report", input.report.meta], ...(input.graph ? [["graph", input.graph.meta] as [string, FetchMeta | null | undefined]] : [])]
    : [["multi", input.report.meta]];
  const rows: [string, ReactNode][] = [];
  for (const [label, m] of metas) {
    rows.push([`${tr("endpoint")} (${label})`, m ? <Url key={`e${label}`} url={m.endpoint} width={w} size={6.6} /> : tr("notRecorded")]);
    rows.push([`${tr("requestBody")} (${label})`, m ? <MonoLines key={`q${label}`} text={JSON.stringify(m.request)} width={w} size={6.4} /> : tr("notRecorded")]);
    rows.push([`${tr("receivedAt")} (${label})`, m?.receivedAt ?? tr("notRecorded")]);
  }
  const data = input.report.data;
  rows.push([tr("serverGenerated"), data.generated_at]);
  rows.push([tr("reportVersion"), data.report_version]);
  if (input.kind === "pair") {
    rows.push([tr("explanationMethod"), clean(input.report.data.explanation.method)]);
    rows.push([tr("modelVersion"), `${input.report.data.model.model} · ${input.report.data.model.checkpoint} · ${tr("seed0")}`]);
    if (input.graph) {
      const tcount = input.graph.data.truncated;
      rows.push([tr("graphTruncation"), `${tcount.proteins_a ?? 0} / ${tcount.proteins_b ?? 0}`]);
    }
  } else {
    rows.push([tr("modelVersion"), tr("multiModel", { ck: frozen.checkpoint.seed0_run_id })]);
  }
  rows.push([tr("frozenTag"), <MonoLines key="ft" text={`${FROZEN.tag} · ${FROZEN.commit}`} width={w} size={6.6} />]);
  rows.push([tr("siteOrigin"), ctx.siteOrigin ?? tr("notRecorded")]);
  rows.push([tr("siteCommit"), ctx.siteCommit ? <MonoLines key="sc" text={ctx.siteCommit} width={w} size={6.6} /> : tr("notRecorded")]);
  rows.push([tr("generator"), tr("generatorValue")]);
  rows.push([tr("generated"), humanDateTime(ctx.now, ctx.timeZone, ctx.lang)]);
  rows.push([tr("generatedUtc"), ctx.now.toISOString()]);
  rows.push([tr("language"), tr("languageValue")]);
  rows.push([tr("payloadSha"), <View key="sha"><MonoLines text={prep.payloadSha256} width={w} size={6.6} color={C.navy} /><Text style={{ fontSize: 6.6, color: C.muted, marginTop: 2 }}>{tr("payloadShaNote")}</Text></View>]);
  return rows;
}

function SourcesSection({ prep, lang, tr }: { prep: PreparedExport; lang: Lang; tr: Tr }) {
  const input = prep.input;
  if (input.kind !== "pair") return null;
  const r = input.report.data;
  const ecols: Col[] = [{ title: "#", width: 0.35 }, { title: tr("source"), width: 1.8 }, { title: tr("docIdCol"), width: 1.45 }, { title: tr("retrieved"), width: 0.8 }, { title: tr("url"), width: 2.2 }];
  const docs = pairFacts(r).groups.docs;
  const used = Array.from(new Set(r.mechanism.findings.flatMap((f) => f.annotation_ids))).map((id) => r.mechanism.annotations[id]).filter(Boolean);
  const acols: Col[] = [{ title: tr("drug"), width: 1 }, { title: tr("protein"), width: 1 }, { title: tr("roles"), width: 1.4 }, { title: tr("source"), width: 1.6 }, { title: tr("retrieved"), width: 0.8 }, { title: tr("pmids"), width: 1.4 }];
  const name = (id: string) => (id === r.drug_a.id ? drugName(r.drug_a, lang) : id === r.drug_b.id ? drugName(r.drug_b, lang) : id);
  const geneOf = (uniprot: string) => r.mechanism.findings.find((f) => f.protein.uniprot === uniprot)?.protein.gene ?? uniprot;
  const role = (k: string) => (ROLE_LABEL[k] ? pick(ROLE_LABEL[k], lang) : k);
  return (
    <>
      <SectionTitle n="7" title={tr("secSources")} />
      <SubTitle first>{tr("evidenceRecords")}</SubTitle>
      {docs.length ? (
        <Table cols={ecols} rows={docs.map((d) => {
          const e = d.records[0];
          return [
            <Text key="n" style={{ fontFamily: FONT.mono, fontSize: 7.2, color: C.navy }}>[{d.n}]</Text>,
            <SafeText key="s" text={`${clean(e.source_name)}${e.source_version ? ` · ${clean(e.source_version)}` : ""}`} width={colPoints(ecols, 1)} />,
            <MonoLines key="r" text={d.kind === "label" ? d.id : d.records.map((x) => x.source_record_id ?? x.id).join("\n")} width={colPoints(ecols, 2)} size={6.2} />,
            Array.from(new Set(d.records.map((x) => x.retrieved_at))).join(", "),
            e.source_url ? <Url key="u" url={e.source_url} width={colPoints(ecols, 4)} size={6.2} /> : "—",
          ];
        })} />
      ) : <Text style={st.small}>{tr("noEvidenceTitle")}.</Text>}

      {used.length ? (
        <>
          <SubTitle>{tr("annotationRecords")}</SubTitle>
          <Table cols={acols} rows={used.map((a) => [
            name(a.drug_id),
            <View key="p">
              <Text style={{ fontFamily: FONT.mono, fontSize: 7, color: C.navy }}>{geneOf(a.uniprot)}</Text>
              <Text style={{ fontFamily: FONT.mono, fontSize: 6.4, color: C.muted }}>{a.uniprot}</Text>
            </View>,
            <View key="r">
              <Text style={{ fontSize: 7.4, color: C.ink }}>{a.roles.map(role).join(", ")}</Text>
              {a.raw_action ? <Text style={{ fontSize: 6.6, color: C.muted }}>{`${tr("rawAction")}: ${clean(a.raw_action)}`}</Text> : null}
            </View>,
            `${clean(a.source_name)} · ${clean(a.source_version)}`,
            a.retrieved_at,
            a.pmids.length ? <Text key="m" style={{ fontFamily: FONT.mono, fontSize: 6.4, color: C.navy3 }}>{a.pmids.join(", ")}</Text> : "—",
          ])} />
          <Text style={st.tiny}>PubMed: https://pubmed.ncbi.nlm.nih.gov/&lt;PMID&gt;/ · UniProt: https://www.uniprot.org/uniprotkb/&lt;accession&gt;/entry</Text>
        </>
      ) : null}

      <SubTitle>{tr("provenance")}</SubTitle>
      <KV rows={provenanceRows(prep, tr)} keyWidth={170} size={7.4} />
      <Text style={[st.tiny, { marginTop: 5 }]}>{tr("retrievalTimes")}</Text>
    </>
  );
}

function Limitations({ lang, tr, apiLimits, disclaimer, multi }: { lang: Lang; tr: Tr; apiLimits: { ru: string; en: string }[]; disclaimer: string; multi: boolean }) {
  const core = [tr("lim1"), tr("lim2"), tr("lim3"), tr("lim4"), tr("lim5"), ...(multi ? [tr("lim6")] : [])];
  return (
    <>
      <SectionTitle n={multi ? "7" : "8"} title={tr("secLimitations")} />
      <SubTitle first>{tr("limitsCore")}</SubTitle>
      <Bullets items={core} color={C.navy} />
      {apiLimits.length ? (
        <>
          <SubTitle>{tr("limitsFromApi")}</SubTitle>
          <Bullets items={apiLimits.map((l) => bi(l, lang))} color={C.faint} size={SIZE.small} />
        </>
      ) : null}
      <View wrap={false} style={{ marginTop: 8 }}>
        <Card accent={C.navy} background={C.white}>
          <Text style={{ fontFamily: FONT.mono, fontSize: 6.8, color: C.navy }}>{tr("researchOnlyTitle").toUpperCase()}</Text>
          <Text style={[st.small, { marginTop: 3 }]}>{disclaimer}</Text>
        </Card>
      </View>
    </>
  );
}

function Appendix({ prep, tr }: { prep: PreparedExport; tr: Tr }) {
  return (
    <>
      <SectionTitle n="A" title={tr("secAppendix")} lead={tr("appendixIntro")} />
      <JsonBox value={machineSummary(prep)} width={CONTENT_WIDTH} size={6} />
    </>
  );
}

// ==================================================================== multi ==

function MultiBody({ prep, m, tr }: { prep: PreparedExport; m: MultiReport; tr: Tr }) {
  const lang = prep.ctx.lang;
  const counts = multiCounts(m);
  const idx = new Map(m.drugs.map((d, i) => [d.id, i + 1]));
  const dn = (id: string) => {
    const d = m.drugs.find((x) => x.id === id);
    return d ? drugName(d, lang) : id;
  };
  const missing = problemSources(m.sources_checked);
  // n_label_documents is absent in responses from API versions before it existed.
  const hasDocs = m.pairs.every((p) => typeof p.n_label_documents === "number");
  const ocols: Col[] = [{ title: "#", width: 0.3 }, { title: tr("nameEn"), width: 1.5 }, { title: tr("nameRu"), width: 1.5 }, { title: tr("drugbankId"), width: 1 }, { title: tr("groups"), width: 1.4 }, { title: tr("drugType"), width: 1 }];
  const pcols: Col[] = [
    { title: tr("pair"), width: 1.85 }, { title: tr("found"), width: 1.55 }, { title: tr("dbRecords"), width: 0.62, align: "right" },
    { title: hasDocs ? tr("labelDocsCol") : tr("labelRecords"), width: hasDocs ? 0.75 : 0.55, align: "right" }, { title: tr("hypCount"), width: 0.45, align: "right" },
    { title: tr("modelCol"), width: 1.08 }, { title: tr("reasons"), width: 1.9 },
  ];
  const reason = (k: string) => (REVIEW_REASON[k] ? pick(REVIEW_REASON[k], lang) : k);
  const scoreCell = (p: MultiReport["pairs"][number]) => (p.calibrated_model_score === null
    ? (p.training_label_seen ? tr("scoreNotCounted") : tr("noModelScore"))
    : fmtCalibrated(p.calibrated_model_score));
  const abstained = m.pairs.filter((p) => p.training_label_seen);
  const scols: Col[] = [{ title: tr("source"), width: 1.3 }, { title: tr("status"), width: 1 }, { title: tr("detail"), width: 2.6 }];
  return (
    <>
      <>
        <SectionTitle n="1" title={tr("secSummary")} />
        <View wrap={false} style={{ flexDirection: "row", marginBottom: 6 }}>
          <Dot color={C.navy} />
          <Text style={[st.p, { flex: 1 }]}>{tr("multiSumDrugs", { n: m.drugs.length, p: m.pairs.length })}</Text>
        </View>
        <Text style={[st.small, { marginBottom: 4 }]}>{tr("multiSumStatus")}</Text>
        <View style={{ marginBottom: 6 }}>
          {STATUS_ORDER.map((s) => (
            <View key={s} wrap={false} style={{ flexDirection: "row", alignItems: "center", paddingVertical: 2, borderBottomWidth: 0.5, borderBottomColor: C.hair }}>
              <Text style={{ fontFamily: FONT.sans, fontWeight: 600, fontSize: 8, color: STATUS_COLOR[s], width: 22 }}>{STATUS_CODE[s]}</Text>
              <Text style={{ fontSize: 8, color: C.ink, flex: 1 }}>{statusLabel(s, lang)}{s === "no_documented_evidence_found" ? ` — ${tr("nothingSafe")}` : ""}</Text>
              <Text style={{ fontWeight: 600, fontSize: 8.4, color: C.navy, width: 40, textAlign: "right" }}>{String(counts.byStatus.get(s) ?? 0)}</Text>
            </View>
          ))}
        </View>
        <Bullets items={[tr("multiSumReview", { n: counts.review }), tr("multiSumAbstain", { n: counts.abstain })]} size={SIZE.small} />
        <Card accent={C.navy} background={C.white}>
          <Text style={st.p}>{tr("multiNoOverall")}</Text>
        </Card>
        <Card accent={EV.missing} background={tint(EV.missing, 0.06)}>
          <Text style={[st.p, { color: C.ink }]}>{bi(m.scope_note, lang)}</Text>
        </Card>
        <SubTitle color={EV.missing}>{tr("sumGapsTitle")}</SubTitle>
        <Bullets color={EV.missing} size={SIZE.small} items={[
          ...missing.map((c) => tr("gapSource", { s: sourceLabel(c.source, lang), st: sourceStatus(c.status, lang) })),
          tr("gapNoCi"), tr("gapSeverity"), tr("gapIndividual"),
        ]} />
      </>

      <>
        <SectionTitle n="2" title={tr("secMultiOverview")} />
        <Table cols={ocols} rows={m.drugs.map((d, i) => [
          <Text key="i" style={{ fontFamily: FONT.mono, fontSize: 7.2, color: C.navy }}>{String(i + 1)}</Text>,
          d.inn ? clean(d.inn) : tr("noInn"),
          d.name_ru ? `${clean(d.name_ru)}${d.name_ru_is_transliteration ? ` (${tr("translit")})` : ""}` : "—",
          <Text key="id" style={{ fontFamily: FONT.mono, fontSize: 7.2 }}>{d.id}</Text>,
          d.groups ? d.groups.replace(/\|/g, ", ") : "—",
          d.drug_type || "—",
        ])} />
        <Text style={st.tiny}>{tr("drugProvenance")}</Text>
      </>

      <>
        <SectionTitle n="3" title={tr("secMultiNetwork")} />
        <NetworkFigure m={m} lang={lang} />
        <Text style={[st.tiny, { marginTop: 2, marginBottom: 8 }]}>{tr("networkNote")}</Text>
        <View wrap={false}>
          <SubTitle>{tr("matrixTitle")}</SubTitle>
          <Text style={[st.tiny, { marginBottom: 5 }]}>{tr("matrixNote")} {tr("matrixNotCountedNote")}</Text>
          <PairMatrixFigure m={m} lang={lang} />
          <Legend items={statusLegendItems(lang).map((s) => ({
            swatch: <Text style={{ fontFamily: FONT.sans, fontWeight: 600, fontSize: 7.2, color: s.color, width: 14 }}>{s.code}</Text>,
            label: s.label,
          }))} />
        </View>
      </>

      <>
        <SectionTitle n="4" title={tr("secMultiPairs")} lead={`${tr("mechanismSummaryMulti")} ${hasDocs ? tr("labelColNote") : tr("labelColNoteOld")}`} />
        <Table cols={pcols} rows={sortedPairs(m).map((p) => [
          <View key="p">
            <Text style={{ fontSize: 7.6, color: C.ink }}>{`${dn(p.drug_a)} + ${dn(p.drug_b)}`}</Text>
            <Text style={{ fontFamily: FONT.mono, fontSize: 6.2, color: C.muted }}>{`${idx.get(p.drug_a)}–${idx.get(p.drug_b)} · ${p.drug_a} · ${p.drug_b}`}</Text>
          </View>,
          <View key="s">
            <Text style={{ fontSize: 7.4, color: STATUS_COLOR[p.evidence_status] }}>{statusLabel(p.evidence_status, lang)}</Text>
            {p.evidence_status === "no_documented_evidence_found" ? <Text style={{ fontSize: 6.4, color: C.muted }}>{tr("nothingSafe")}</Text> : null}
          </View>,
          String(p.n_database_records), hasDocs ? `${p.n_label_documents} (${p.n_label_records})` : String(p.n_label_records), String(p.n_mechanism_hypotheses),
          <View key="m">
            <Text style={{ fontFamily: FONT.mono, fontSize: 7.2, color: p.training_label_seen ? C.faint : C.ink }}>{scoreCell(p)}</Text>
            <Text style={{ fontFamily: FONT.mono, fontSize: 6.2, color: C.muted }}>{p.regime}</Text>
          </View>,
          <Text key="r" style={{ fontSize: 6.8, color: p.needs_review ? C.ink : C.muted }}>{p.review_reasons.length ? p.review_reasons.map(reason).join("; ") : "—"}</Text>,
        ])} />
      </>

      <>
        <SectionTitle n="5" title={tr("secMultiCoverage")} />
        <Bullets size={SIZE.small} items={[tr("regimesNote"), tr("mechanismSummaryMulti"), tr("gapNoCi")]} />
        {abstained.length ? (
          <>
            <SubTitle>{tr("abstainedPairs")}</SubTitle>
            <Bullets size={SIZE.small} color={EV.missing} items={abstained.map((p) => `${dn(p.drug_a)} + ${dn(p.drug_b)} (${p.regime})`)} />
          </>
        ) : null}
        <SubTitle>{tr("sourcesChecked")}</SubTitle>
        <Table cols={scols} rows={m.sources_checked.map((c) => [
          sourceLabel(c.source, lang),
          <Text key="s" style={{ fontSize: 7.6, color: c.status === "unavailable" || c.status === "disabled" ? EV.missing : C.ink }}>{sourceStatus(c.status, lang)}</Text>,
          c.detail ? <MonoLines key="d" text={c.detail} width={colPoints(scols, 2)} size={6.4} /> : "—",
        ])} />
      </>

      <>
        <SectionTitle n="6" title={tr("secSources")} />
        <KV rows={provenanceRows(prep, tr)} keyWidth={170} size={7.4} />
      </>

      <Limitations lang={lang} tr={tr} apiLimits={[]} disclaimer={bi(m.disclaimer, lang)} multi />
      <Glossary n={glossaryNumber("multi")} lang={lang} tr={tr} />
      <Appendix prep={prep} tr={tr} />
    </>
  );
}

