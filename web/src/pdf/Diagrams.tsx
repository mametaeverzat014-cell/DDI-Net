// Vector figures of the report. Geometry comes from diagram.ts; this file only
// draws it. No figure encodes a level of danger, and no documented-interaction
// line has an arrowhead.
import { Circle, G, Line, Path, Rect, Svg, Text, View } from "@react-pdf/renderer";
import type { ModalityReliance, MultiReport } from "../data/v3";
import type { Lang } from "../i18n";
import { STATUS_COLOR, statusDash, t } from "./content";
import { tint } from "./styles";
import { layoutMechanism, layoutNetwork, L, type DiagramData, type Side } from "./diagram";
import { deltaText, drugName, fixed } from "./format";
import { STATUS_CODE } from "./strings";
import { C, CONTENT_WIDTH, DRUG_COLOR, EV, FONT, REL } from "./theme";

const SIDE_COLOR: Record<Side, string> = { a: DRUG_COLOR.a, b: DRUG_COLOR.b, shared: C.slate };
const relColor = (r: string | null) => (r && r in REL ? REL[r as keyof typeof REL] : C.faint);

/** Shorten a label to fit `width`: proportional faces at a conservative 0.62 em
 *  per glyph, the mono face at its exact 0.6 em. */
function fitText(s: string, width: number, size: number, em = 0.62): string {
  const max = Math.floor(width / (em * size));
  return s.length <= max ? s : `${s.slice(0, Math.max(1, max - 1))}…`;
}
const fitMono = (s: string, width: number, size: number) => fitText(s, width, size, 0.6);

// ------------------------------------------------------------- mechanism ----

export function MechanismFigure({ data, lang }: { data: DiagramData; lang: Lang }) {
  const W = CONTENT_WIDTH;
  const only = (name: string) => (lang === "ru" ? `только ${fitMono(name, 120, L.headerFont)}` : `${fitMono(name, 120, L.headerFont)} only`).toUpperCase();
  const lay = layoutMechanism(data, W, lang, { onlyA: only(data.drugA.name), onlyB: only(data.drugB.name), shared: t("colShared", lang) });
  const graphH = lay.matrix ? lay.matrix.y - 22 : lay.height;
  const box = (b: typeof lay.boxA, side: "a" | "b", name: string, id: string) => {
    const color = DRUG_COLOR[side];
    const left = side === "a";
    const tx = left ? b.x + 22 : b.x + b.w - 22;
    const anchor = left ? "start" : "end";
    return (
      <G>
        <Rect x={b.x + 0.5} y={b.y} width={b.w - 1} height={b.h} rx={3} fill={tint(color, 0.07)} stroke={color} strokeWidth={0.8} />
        <Circle cx={left ? b.x + 11 : b.x + b.w - 11} cy={b.y + b.h / 2} r={6.5} fill={color} />
        <Text x={left ? b.x + 11 : b.x + b.w - 11} y={b.y + b.h / 2 + 2.3} textAnchor="middle" fill={C.white} style={{ fontFamily: FONT.mono, fontSize: 6.6 }}>{side.toUpperCase()}</Text>
        <Text x={tx} y={b.y + 15.5} textAnchor={anchor} fill={C.navy} style={{ fontFamily: FONT.serif, fontWeight: 600, fontSize: 10.5 }}>{fitText(name, b.w - 34, 10.5)}</Text>
        <Text x={tx} y={b.y + 27} textAnchor={anchor} fill={C.muted} style={{ fontFamily: FONT.mono, fontSize: 6.4 }}>{id}</Text>
      </G>
    );
  };
  const linkLabel = data.documented === "none"
    ? [lang === "ru" ? "записи о" : "no interaction", lang === "ru" ? "взаимодействии нет" : "record found"]
    : [lang === "ru" ? "задокументировано" : "documented record", data.documented === "verified_order"
      ? (lang === "ru" ? "порядок подтверждён" : "drug order verified")
      : (lang === "ru" ? "направление не указано" : "no direction stated")];
  const lx1 = lay.boxA.x + lay.boxA.w, lx2 = lay.boxB.x, ly = lay.boxA.y + lay.boxA.h / 2;

  return (
    <View wrap={false}>
      <Svg width={W} height={graphH} viewBox={`0 0 ${W} ${graphH}`}>
        {/* documented interaction between the drugs: never an arrowhead */}
        <Line x1={lx1} y1={ly} x2={lx2} y2={ly} stroke={data.documented === "none" ? C.faint : EV.documented}
          strokeWidth={data.documented === "none" ? 0.7 : 1.1} strokeDasharray={data.documented === "none" ? "1 2.5" : "4 2.5"} />
        <Text x={(lx1 + lx2) / 2} y={ly - 4} textAnchor="middle" fill={data.documented === "none" ? C.muted : EV.documented} style={{ fontFamily: FONT.mono, fontSize: 5.4 }}>{linkLabel[0]}</Text>
        <Text x={(lx1 + lx2) / 2} y={ly + 9} textAnchor="middle" fill={C.muted} style={{ fontFamily: FONT.mono, fontSize: 5.4 }}>{linkLabel[1]}</Text>

        {box(lay.boxA, "a", data.drugA.name, data.drugA.id)}
        {box(lay.boxB, "b", data.drugB.name, data.drugB.id)}

        {lay.headers.map((h, i) => (
          <Text key={`h${i}`} x={h.x} y={h.y} textAnchor={h.anchor} fill={h.text === t("colShared", lang) ? C.teal : C.muted} style={{ fontFamily: FONT.mono, fontSize: L.headerFont }}>{h.text}</Text>
        ))}

        {lay.trunks.map((tr, i) => (
          <Line key={`t${i}`} x1={tr.x} y1={tr.y1} x2={tr.x} y2={tr.y2} stroke={DRUG_COLOR[tr.drug]} strokeWidth={0.8} />
        ))}
        {lay.branches.map((b, i) => {
          const end = b.drug === "a" ? b.x2 : b.x1; // the pill side
          return (
            <G key={`b${i}`}>
              <Line x1={b.x1} y1={b.y} x2={b.x2} y2={b.y} stroke={relColor(b.relation)} strokeWidth={1.05} />
              <Circle cx={end} cy={b.y} r={1.5} fill={relColor(b.relation)} />
              <Circle cx={b.drug === "a" ? b.x1 : b.x2} cy={b.y} r={1.1} fill={DRUG_COLOR[b.drug]} />
              {b.roles ? <Text x={(b.x1 + b.x2) / 2} y={b.y - 2.2} textAnchor="middle" fill={C.slate2} style={{ fontFamily: FONT.mono, fontSize: L.roleFont }}>{b.roles}</Text> : null}
            </G>
          );
        })}
        {lay.pills.map((p, i) => {
          const hyp = p.protein.hyps.length > 0;
          const shared = p.protein.side === "shared";
          return (
            <G key={`p${i}`}>
              {hyp ? <Rect x={p.x - 2.2} y={p.y - 2.2} width={p.w + 4.4} height={p.h + 4.4} rx={7} fill="none" stroke={EV.hypothesis} strokeWidth={0.8} strokeDasharray="2 1.6" /> : null}
              <Rect x={p.x} y={p.y} width={p.w} height={p.h} rx={5.5} fill={shared ? tint(C.slate, 0.1) : C.white} stroke={shared ? C.slate2 : C.rule} strokeWidth={0.6} />
              <Text x={p.x + p.w / 2} y={p.y + p.h / 2 + 2.2} textAnchor="middle" fill={hyp ? EV.hypothesis : C.ink} style={{ fontFamily: FONT.mono, fontSize: L.pillFont }}>{p.label}</Text>
            </G>
          );
        })}
      </Svg>
    </View>
  );
}

export function PathwayMatrixFigure({ data, lang }: { data: DiagramData; lang: Lang }) {
  const lay = layoutMechanism(data, CONTENT_WIDTH, lang, { onlyA: "", onlyB: "", shared: "" });
  const m = lay.matrix;
  if (!m) return null;
  const top = m.y - 14;
  const H = m.h + 16;
  const cell = L.matrixCell;
  return (
    <View wrap={false}>
      <Svg width={m.w + 2} height={H} viewBox={`0 ${top} ${m.w + 2} ${H}`}>
        {m.colLabels.map((c, j) => (
          <G key={`c${j}`}>
            <Rect x={c.x - cell / 2} y={m.y} width={cell} height={m.h} fill={j % 2 ? C.tint : C.white} />
            <Text x={c.x} y={c.y} textAnchor="middle" fill={C.slate2} style={{ fontFamily: FONT.mono, fontSize: L.matrixFont }}>{c.text}</Text>
          </G>
        ))}
        {m.rowLabels.map((r, i) => (
          <G key={`r${i}`}>
            <Line x1={m.x} y1={m.y + (i + 1) * cell} x2={m.x + m.w} y2={m.y + (i + 1) * cell} stroke={C.hair} strokeWidth={0.4} />
            <Text x={r.x} y={r.y} fill={C.ink} style={{ fontFamily: FONT.mono, fontSize: L.matrixFont }}>{r.text}</Text>
          </G>
        ))}
        <Line x1={m.x} y1={m.y} x2={m.x + m.w} y2={m.y} stroke={C.rule} strokeWidth={0.5} />
        {m.cells.map((c, k) => <Circle key={k} cx={c.x} cy={c.y} r={3} fill={SIDE_COLOR[c.side]} />)}
      </Svg>
    </View>
  );
}

// --------------------------------------------------------------- reliance ----

export function RelianceChart({ r, lang }: { r: ModalityReliance; lang: Lang }) {
  const W = CONTENT_WIDTH;
  const rows = [
    { k: t("proteins", lang), d: r.delta_protein, without: r.without_protein_raw },
    { k: t("molecular", lang), d: r.delta_molecular, without: r.without_molecular_raw },
    { k: t("pathwaysData", lang), d: r.delta_pathway, without: r.without_pathway_raw },
  ];
  const labelW = 110, valueW = 120;
  const barX0 = labelW, barW = W - labelW - valueW;
  const mid = barX0 + barW / 2;
  const rowH = 17;
  const H = rows.length * rowH + 18;
  return (
    <View wrap={false}>
      <Svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
        <Line x1={mid} y1={2} x2={mid} y2={rows.length * rowH + 2} stroke={C.rule} strokeWidth={0.6} />
        {[-1, -0.5, 0.5, 1].map((v) => (
          <G key={v}>
            <Line x1={mid + (v * barW) / 2} y1={2} x2={mid + (v * barW) / 2} y2={rows.length * rowH + 2} stroke={C.hair} strokeWidth={0.4} strokeDasharray="1 2" />
            <Text x={mid + (v * barW) / 2} y={rows.length * rowH + 12} textAnchor="middle" fill={C.muted} style={{ fontFamily: FONT.mono, fontSize: 5.6 }}>{v < 0 ? `−${-v}` : `+${v}`}</Text>
          </G>
        ))}
        <Text x={mid} y={rows.length * rowH + 12} textAnchor="middle" fill={C.muted} style={{ fontFamily: FONT.mono, fontSize: 5.6 }}>0</Text>
        {rows.map((row, i) => {
          const y = 2 + i * rowH;
          const len = (Math.min(Math.abs(row.d), 1) * barW) / 2;
          // Positive delta = the score drops without the data: drawn to the left (−).
          const x = row.d >= 0 ? mid - len : mid;
          return (
            <G key={row.k}>
              <Text x={0} y={y + 10} fill={C.ink} style={{ fontFamily: FONT.sans, fontSize: 7.6 }}>{row.k}</Text>
              <Rect x={barX0} y={y + 4} width={barW} height={7} fill={C.tint2} />
              <Rect x={x} y={y + 4} width={Math.max(len, 0.6)} height={7} fill={EV.model} />
              <Text x={W} y={y + 10} textAnchor="end" fill={C.ink} style={{ fontFamily: FONT.mono, fontSize: 6.8 }}>{`${deltaText(row.d)}  (${fixed(row.without, 4)})`}</Text>
            </G>
          );
        })}
      </Svg>
    </View>
  );
}

// ------------------------------------------------------------------ multi ----


export function NetworkFigure({ m, lang }: { m: MultiReport; lang: Lang }) {
  const W = CONTENT_WIDTH, H = 212, font = 6.8;
  // Labels sit outside the ring and cannot wrap: shorten any that would leave
  // less than a 60 pt radius (full names are in the tables).
  const maxLabel = W / 2 - 60 - 22;
  const names = m.drugs.map((d, i) => `${i + 1} ${fitMono(drugName(d, lang), maxLabel - 0.6 * font * 3, font)}`);
  const { nodes } = layoutNetwork(m.drugs.map((d) => d.id), names, W, H, font);
  const pos = new Map(nodes.map((n) => [n.id, n]));
  return (
    <View wrap={false}>
      <Svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
        {m.pairs.map((p) => {
          const a = pos.get(p.drug_a), b = pos.get(p.drug_b);
          if (!a || !b) return null;
          const none = p.evidence_status === "no_documented_evidence_found";
          return (
            <Line key={p.drug_a + p.drug_b} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={STATUS_COLOR[p.evidence_status]}
              strokeWidth={none ? 0.7 : p.needs_review ? 2.1 : 1.1} strokeDasharray={statusDash(p.evidence_status)} strokeOpacity={none ? 0.75 : 0.9} />
          );
        })}
        {nodes.map((n) => (
          <G key={n.id}>
            <Circle cx={n.x} cy={n.y} r={7.5} fill={C.white} stroke={C.navy} strokeWidth={1} />
            <Text x={n.x} y={n.y + 2.4} textAnchor="middle" fill={C.navy} style={{ fontFamily: FONT.mono, fontSize: 6.6 }}>{String(n.index)}</Text>
            <Text x={n.labelX} y={n.labelY} textAnchor={n.anchor} fill={C.ink} style={{ fontFamily: FONT.mono, fontSize: font }}>{n.label.replace(/^\d+ /, "")}</Text>
          </G>
        ))}
      </Svg>
    </View>
  );
}

export function PairMatrixFigure({ m, lang }: { m: MultiReport; lang: Lang }) {
  const n = m.drugs.length;
  const labelW = 120;
  const cell = Math.min(40, (CONTENT_WIDTH - labelW) / n);
  const W = labelW + n * cell, H = 16 + n * cell;
  const idx = new Map(m.drugs.map((d, i) => [d.id, i]));
  const pairAt = new Map(m.pairs.map((p) => {
    const i = idx.get(p.drug_a)!, j = idx.get(p.drug_b)!;
    return [`${Math.min(i, j)}:${Math.max(i, j)}`, p];
  }));
  return (
    <View wrap={false}>
      <Svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
        {m.drugs.map((_, j) => (
          <Text key={`c${j}`} x={labelW + j * cell + cell / 2} y={10} textAnchor="middle" fill={C.slate2} style={{ fontFamily: FONT.mono, fontSize: 6.6 }}>{String(j + 1)}</Text>
        ))}
        {m.drugs.map((d, i) => (
          <G key={`r${i}`}>
            <Text x={0} y={16 + i * cell + cell / 2 + 2.4} fill={C.ink} style={{ fontFamily: FONT.mono, fontSize: 6.6 }}>{`${i + 1} ${fitMono(drugName(d, lang), labelW - 18, 6.6)}`}</Text>
            {m.drugs.map((_, j) => {
              const x = labelW + j * cell, y = 16 + i * cell;
              if (j === i) return <Rect key={j} x={x + 0.5} y={y + 0.5} width={cell - 1} height={cell - 1} fill={C.tint2} />;
              if (j < i) return <Rect key={j} x={x + 0.5} y={y + 0.5} width={cell - 1} height={cell - 1} fill={C.white} stroke={C.hair} strokeWidth={0.4} />;
              const p = pairAt.get(`${i}:${j}`);
              if (!p) return null;
              const color = STATUS_COLOR[p.evidence_status];
              const score = p.calibrated_model_score === null ? (p.training_label_seen ? t("matrixNotCounted", lang) : "—") : fixed(p.calibrated_model_score, 2);
              return (
                <G key={j}>
                  <Rect x={x + 0.5} y={y + 0.5} width={cell - 1} height={cell - 1} fill={tint(color, 0.16)} stroke={p.needs_review ? color : tint(color, 0.45)} strokeWidth={p.needs_review ? 1.1 : 0.5} />
                  <Text x={x + cell / 2} y={y + cell / 2 - 1} textAnchor="middle" fill={color} style={{ fontFamily: FONT.sans, fontWeight: 600, fontSize: 8 }}>{STATUS_CODE[p.evidence_status]}</Text>
                  <Text x={x + cell / 2} y={y + cell / 2 + 8} textAnchor="middle" fill={C.slate2} style={{ fontFamily: FONT.mono, fontSize: 5.6 }}>{score}</Text>
                </G>
              );
            })}
          </G>
        ))}
      </Svg>
    </View>
  );
}


export function LineSwatch({ color, dash, width = 1.1 }: { color: string; dash?: string; width?: number }) {
  return (
    <Svg width={16} height={6} viewBox="0 0 16 6"><Line x1={0} y1={3} x2={16} y2={3} stroke={color} strokeWidth={width} strokeDasharray={dash} /></Svg>
  );
}

export function DotSwatch({ color, ring }: { color: string; ring?: boolean }) {
  return (
    <Svg width={9} height={9} viewBox="0 0 9 9">
      {ring ? <Rect x={0.6} y={1.6} width={7.8} height={5.8} rx={2.9} fill="none" stroke={color} strokeWidth={0.8} strokeDasharray="1.6 1.2" /> : <Circle cx={4.5} cy={4.5} r={3} fill={color} />}
    </Svg>
  );
}

// ------------------------------------------------------------------ cover ----

/** Decorative network motif for the cover band, seeded by the report hash so
 *  each report's cover differs. Pure decoration; it encodes no data. */
export function CoverMotif({ seed, width, height }: { seed: string; width: number; height: number }) {
  let s = parseInt(seed.slice(0, 8), 16) || 1;
  const rnd = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 0x100000000);
  const pts = Array.from({ length: 46 }, () => ({ x: width * (0.42 + 0.58 * rnd()), y: height * rnd() }));
  const lines: [number, number][] = [];
  pts.forEach((p, i) => {
    const near = pts.map((q, j) => ({ j, d: Math.hypot(p.x - q.x, p.y - q.y) })).filter((o) => o.j !== i).sort((a, b) => a.d - b.d).slice(0, 2);
    for (const o of near) if (o.j > i) lines.push([i, o.j]);
  });
  return (
    <Svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ position: "absolute", top: 0, left: 0 }}>
      {lines.map(([i, j], k) => (
        <Line key={k} x1={pts[i].x} y1={pts[i].y} x2={pts[j].x} y2={pts[j].y} stroke="#5FA8A1" strokeWidth={0.5} strokeOpacity={0.35} />
      ))}
      {pts.map((p, k) => <Circle key={k} cx={p.x} cy={p.y} r={k % 7 === 0 ? 2.2 : 1.2} fill={k % 7 === 0 ? "#7CC4BC" : "#9FB3CC"} fillOpacity={0.55} />)}
      <Path d={`M 0 ${height - 0.5} L ${width} ${height - 0.5}`} stroke="#0F766E" strokeWidth={2} />
    </Svg>
  );
}
