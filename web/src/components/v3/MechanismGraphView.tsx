// Interactive mechanism graph: drug A ← proteins → drug B, pathways below.
//
// Hand-laid-out SVG rather than a force simulation: the reader has to see
// immediately which proteins are SHARED (centre column) and which belong to one
// drug (side columns), and a layout that moves would hide exactly that.
// Every edge drawn is a documented relation; mechanism hypotheses are an
// overlay (dashed ring) on proteins, never an edge, so a hypothesis can never be
// mistaken for a recorded fact.
import { useMemo, useState } from "react";
import { useI18n, pick, type Bi } from "../../i18n";
import type { GraphEdge, GraphNode, MechanismFinding, MechanismGraph } from "../../data/v3";
import { PATTERN_LABEL, RELATION_LABEL, ROLE_LABEL } from "./evidenceStyle";

const W = 980;
const ROW = 40;
const TOP = 70;

const REL_COLOR: Record<string, string> = {
  enzyme: "var(--cyan)",
  transporter: "var(--blue)",
  carrier: "var(--violet)",
  target: "rgba(160,182,210,0.75)",
};

const T = {
  pick: { ru: "Выберите узел графа, чтобы увидеть, откуда взята каждая связь.", en: "Select a node to see where each link comes from." },
  general: { ru: "Общее описание семейства белков (текст проекта, не утверждение об этой паре)", en: "General description of the protein family (project text, not a statement about this pair)" },
  links: { ru: "Задокументированные связи", en: "Documented links" },
  hyps: { ru: "Гипотезы с участием этого белка", en: "Hypotheses involving this protein" },
  hypothesis: { ru: "гипотеза", en: "hypothesis" },
  pathways: { ru: "Пути в графе", en: "Pathways in the graph" },
  truncated: { ru: "Не показано белков, не общих для пары", en: "Non-shared proteins not shown" },
  shared: { ru: "общие", en: "shared" },
  documented: { ru: "задокументированное взаимодействие", en: "documented interaction" },
  proteins: { ru: "белков в пути (в данных проекта)", en: "proteins in pathway (project data)" },
} satisfies Record<string, Bi>;

interface Placed { node: GraphNode; x: number; y: number }

function layout(g: MechanismGraph): { placed: Map<string, Placed>; height: number } {
  const byKind = (kind: string, side?: string) => g.nodes.filter((n) => n.kind === kind && (!side || n.side === side));
  const shared = byKind("protein", "shared");
  const onlyA = byKind("protein", "a");
  const onlyB = byKind("protein", "b");
  const pathways = byKind("pathway");
  const rows = Math.max(shared.length, onlyA.length, onlyB.length, 3);
  const proteinBottom = TOP + rows * ROW;
  const height = proteinBottom + (pathways.length ? 150 : 40);
  const placed = new Map<string, Placed>();
  const column = (nodes: GraphNode[], x: number) => {
    const offset = TOP + ((rows - nodes.length) * ROW) / 2;
    nodes.forEach((n, i) => placed.set(n.id, { node: n, x, y: offset + i * ROW + ROW / 2 }));
  };
  column(onlyA, W * 0.3);
  column(shared, W * 0.5);
  column(onlyB, W * 0.7);
  const mid = TOP + (rows * ROW) / 2;
  for (const d of byKind("drug")) placed.set(d.id, { node: d, x: d.side === "a" ? 70 : W - 70, y: mid });
  pathways.forEach((p, i) => {
    const x = pathways.length === 1 ? W / 2 : 110 + (i * (W - 220)) / (pathways.length - 1);
    placed.set(p.id, { node: p, x, y: proteinBottom + 95 + (i % 2) * 28 });
  });
  return { placed, height };
}

export function MechanismGraphView({ graph, findings, nameOf }: {
  graph: MechanismGraph; findings: MechanismFinding[]; nameOf: (id: string) => string;
}) {
  const { lang } = useI18n();
  const [selected, setSelected] = useState<string | null>(null);
  const { placed, height } = useMemo(() => layout(graph), [graph]);
  const hypProteins = useMemo(() => new Set(findings.filter((f) => f.pattern !== "shared_annotation").map((f) => `P:${f.protein.uniprot}`)), [findings]);
  const neighbours = useMemo(() => {
    if (!selected) return null;
    const s = new Set([selected]);
    for (const e of graph.edges) {
      if (e.source === selected) s.add(e.target);
      if (e.target === selected) s.add(e.source);
    }
    return s;
  }, [selected, graph.edges]);

  const dim = (id: string) => (neighbours && !neighbours.has(id) ? 0.18 : 1);
  const edgeDim = (e: GraphEdge) => (neighbours && !(neighbours.has(e.source) && neighbours.has(e.target) && (e.source === selected || e.target === selected)) ? 0.08 : 1);

  const truncated = (graph.truncated.proteins_a ?? 0) + (graph.truncated.proteins_b ?? 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <div className="v3-card" style={{ padding: 10 }}>
        <svg viewBox={`0 0 ${W} ${height}`} width="100%" role="group" aria-label="mechanism graph" style={{ display: "block" }}>
          {/* column captions */}
          <text x={W * 0.3} y={34} textAnchor="middle" fill="var(--text-3)" fontSize={12} fontFamily="var(--font-mono)">{nameOf(graph.drug_a)}</text>
          <text x={W * 0.5} y={34} textAnchor="middle" fill="var(--cyan)" fontSize={12} fontFamily="var(--font-mono)">{pick(T.shared, lang).toUpperCase()}</text>
          <text x={W * 0.7} y={34} textAnchor="middle" fill="var(--text-3)" fontSize={12} fontFamily="var(--font-mono)">{nameOf(graph.drug_b)}</text>

          {graph.edges.map((e) => {
            const s = placed.get(e.source), t = placed.get(e.target);
            if (!s || !t) return null;
            if (e.kind === "documented_interaction") {
              const midX = (s.x + t.x) / 2;
              return (
                <g key={e.id} opacity={edgeDim(e)}>
                  <path d={`M ${s.x} ${s.y - 26} Q ${midX} ${8} ${t.x} ${t.y - 26}`} fill="none" stroke="var(--ev-documented)" strokeWidth={1.4} strokeDasharray="5 5" />
                </g>
              );
            }
            const color = e.kind === "pathway_membership" ? "rgba(155,140,255,0.45)" : REL_COLOR[String(e.detail.relation)] ?? "var(--text-3)";
            const cx = (s.x + t.x) / 2;
            return (
              <path key={e.id} d={`M ${s.x} ${s.y} C ${cx} ${s.y}, ${cx} ${t.y}, ${t.x} ${t.y}`} fill="none" stroke={color}
                strokeWidth={e.kind === "pathway_membership" ? 0.9 : 1.3} opacity={0.75 * edgeDim(e)} />
            );
          })}

          {Array.from(placed.values()).map(({ node, x, y }) => (
            <Node key={node.id} node={node} label={node.kind === "drug" ? nameOf(node.id) : node.label} x={x} y={y} hyp={hypProteins.has(node.id)} opacity={dim(node.id)}
              selected={selected === node.id} onSelect={() => setSelected(selected === node.id ? null : node.id)} />
          ))}
        </svg>
        <Legend graph={graph} />
        {truncated > 0 && <p className="mono" style={{ fontSize: 11, color: "var(--text-3)", margin: "6px 8px" }}>{pick(T.truncated, lang)}: {truncated}</p>}
      </div>
      <DetailPanel graph={graph} selected={selected} findings={findings} nameOf={nameOf} />
    </div>
  );
}

function Node({ node, label: fullLabel, x, y, hyp, opacity, selected, onSelect }: {
  node: GraphNode; label: string; x: number; y: number; hyp: boolean; opacity: number; selected: boolean; onSelect: () => void;
}) {
  const isDrug = node.kind === "drug";
  const isPath = node.kind === "pathway";
  const label = isPath && fullLabel.length > 26 ? fullLabel.slice(0, 25) + "…" : fullLabel;
  const fill = isDrug ? (node.side === "a" ? "var(--blue)" : "var(--cyan)") : isPath ? "var(--violet)" : node.side === "shared" ? "var(--cyan)" : "rgba(160,182,210,0.8)";
  return (
    <g transform={`translate(${x}, ${y})`} opacity={opacity} tabIndex={0} role="button" aria-pressed={selected}
      aria-label={`${node.kind}: ${node.label}`} style={{ cursor: "pointer", outline: "none" }}
      onClick={onSelect} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(); } }}>
      {hyp && <circle r={15} fill="none" stroke="var(--ev-hypothesis)" strokeWidth={1.2} strokeDasharray="3 3" />}
      {selected && <circle r={isDrug ? 30 : 13} fill="none" stroke="var(--text)" strokeWidth={1.2} />}
      {isDrug ? (
        <>
          <circle r={24} fill="rgba(6,16,31,0.9)" stroke={fill} strokeWidth={2} />
          <text y={46} textAnchor="middle" fill="var(--text)" fontSize={15} fontWeight={600}>{label}</text>
          <text y={62} textAnchor="middle" fill="var(--text-3)" fontSize={11} fontFamily="var(--font-mono)">{node.id}</text>
        </>
      ) : isPath ? (
        <>
          <rect x={-5} y={-5} width={10} height={10} rx={2} fill={fill} />
          <text y={21} textAnchor="middle" fill="var(--text-2)" fontSize={11.5}>{label}</text>
        </>
      ) : (
        <>
          <circle r={7} fill={fill} />
          <text x={node.side === "a" ? -12 : 12} y={4} textAnchor={node.side === "a" ? "end" : "start"} fill="var(--text)" fontSize={13} fontFamily="var(--font-mono)">{label}</text>
        </>
      )}
    </g>
  );
}

function Legend({ graph }: { graph: MechanismGraph }) {
  const { lang } = useI18n();
  const rel = (k: string) => (RELATION_LABEL[k] ? pick(RELATION_LABEL[k], lang) : k);
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 16px", padding: "8px 8px 2px", fontSize: 11.5, color: "var(--text-3)" }}>
      {Object.entries(REL_COLOR).map(([k, c]) => (
        <span key={k} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <span style={{ width: 18, height: 2, background: c, display: "inline-block" }} />{rel(k)}
        </span>
      ))}
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
        <span style={{ width: 12, height: 12, borderRadius: "50%", border: "1.2px dashed var(--ev-hypothesis)", display: "inline-block" }} />{pick(T.hypothesis, lang)}
      </span>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
        <span style={{ width: 18, height: 0, borderTop: "1.4px dashed var(--ev-documented)", display: "inline-block" }} />{pick(T.documented, lang)}
      </span>
      {graph.legend.shared && <span style={{ flexBasis: "100%" }}>{pick(graph.legend.shared, lang)}</span>}
    </div>
  );
}

function DetailPanel({ graph, selected, findings, nameOf }: {
  graph: MechanismGraph; selected: string | null; findings: MechanismFinding[]; nameOf: (id: string) => string;
}) {
  const { lang } = useI18n();
  if (!selected) return <div className="v3-card"><p style={{ fontSize: 13.5 }}>{pick(T.pick, lang)}</p></div>;
  const node = graph.nodes.find((n) => n.id === selected);
  if (!node) return null;
  const edges = graph.edges.filter((e) => e.source === selected || e.target === selected);
  const role = (r: string) => (ROLE_LABEL[r] ? pick(ROLE_LABEL[r], lang) : r);

  if (node.kind === "drug") {
    return (
      <div className="v3-card">
        <span className="eyebrow">{node.id}</span>
        <h3 style={{ fontSize: 20, marginTop: 8 }}>{nameOf(node.id)}</h3>
        <p className="mono" style={{ fontSize: 11.5, marginTop: 10 }}>
          <a href={`https://go.drugbank.com/drugs/${node.id}`} target="_blank" rel="noreferrer noopener">DrugBank ↗</a>
        </p>
        <p style={{ fontSize: 13, marginTop: 10 }}>{edges.filter((e) => e.kind === "annotation").length} {pick(T.links, lang).toLowerCase()}</p>
      </div>
    );
  }

  if (node.kind === "pathway") {
    const d = node.detail as { reactome_id?: string; n_proteins_in_pathway?: number; source?: string };
    return (
      <div className="v3-card">
        <span className="eyebrow">Reactome</span>
        <h3 style={{ fontSize: 18, marginTop: 8 }}>{node.label}</h3>
        <p className="mono" style={{ fontSize: 11.5, marginTop: 10, color: "var(--text-3)" }}>
          {d.n_proteins_in_pathway} {pick(T.proteins, lang)} ·{" "}
          <a href={`https://reactome.org/content/detail/${d.reactome_id}`} target="_blank" rel="noreferrer noopener">{d.reactome_id} ↗</a>
        </p>
        <p style={{ fontSize: 13, marginTop: 10 }}>{graph.legend.shared ? pick(graph.legend.shared, lang) : ""}</p>
      </div>
    );
  }

  const p = node.detail as { uniprot: string; gene: string; name: string; organism: string; plain: Bi };
  const involved = findings.filter((f) => `P:${f.protein.uniprot}` === selected);
  return (
    <div className="v3-card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div>
        <span className="eyebrow">{p.uniprot}{p.organism ? ` · ${p.organism}` : ""}</span>
        <h3 style={{ fontSize: 20, marginTop: 8 }} className="mono">{p.gene}</h3>
        <p style={{ fontSize: 12.5, marginTop: 4 }}>{p.name}</p>
      </div>
      <div style={{ borderLeft: "2px solid var(--border-strong)", paddingLeft: 10 }}>
        <p style={{ fontSize: 13.5, color: "var(--text)" }}>{pick(p.plain, lang)}</p>
        <p className="mono" style={{ fontSize: 10, color: "var(--text-3)", marginTop: 4 }}>{pick(T.general, lang)}</p>
      </div>
      <div>
        <span className="eyebrow">{pick(T.links, lang)}</span>
        <ul style={{ listStyle: "none", margin: "8px 0 0", padding: 0, display: "flex", flexDirection: "column", gap: 8 }}>
          {edges.filter((e) => e.kind === "annotation").map((e) => {
            const d = e.detail as { relation: string; roles: string[]; raw_action: string; source: string; source_version: string; pmids: string[] };
            return (
              <li key={e.id} style={{ fontSize: 12.5, color: "var(--text-2)" }}>
                <strong style={{ color: "var(--text)" }}>{nameOf(e.source)}</strong> · {RELATION_LABEL[d.relation] ? pick(RELATION_LABEL[d.relation], lang) : d.relation} · {d.roles.map(role).join(", ")}
                <div className="mono" style={{ fontSize: 10.5, color: "var(--text-3)" }}>
                  {d.source} {d.source_version}{d.raw_action ? ` · "${d.raw_action}"` : ""}
                </div>
                {d.pmids.length > 0 && (
                  <div className="mono" style={{ fontSize: 10.5, display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {d.pmids.slice(0, 5).map((id) => <a key={id} href={`https://pubmed.ncbi.nlm.nih.gov/${id}/`} target="_blank" rel="noreferrer noopener">PMID {id}</a>)}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </div>
      {involved.length > 0 && (
        <div>
          <span className="eyebrow" style={{ color: "var(--ev-hypothesis)" }}>{pick(T.hyps, lang)}</span>
          <ul style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 12.5, color: "var(--text-2)" }}>
            {involved.map((f) => (
              <li key={f.id}>{pick(PATTERN_LABEL[f.pattern], lang)}{f.actor_drug_id ? ` (${nameOf(f.actor_drug_id)} → ${nameOf(f.affected_drug_id ?? "")})` : ""}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="mono" style={{ fontSize: 11 }}>
        <a href={`https://www.uniprot.org/uniprotkb/${p.uniprot}/entry`} target="_blank" rel="noreferrer noopener">UniProt ↗</a>
      </p>
    </div>
  );
}
