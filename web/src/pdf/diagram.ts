// Geometry of the report's vector diagrams, computed without the PDF library so
// the tests can check it: every label inside the frame, no two labels or pills
// overlapping.
//
// Mechanism graph, as a schematic rather than a force layout:
//
//   ┌ Drug A ───────────┐  - - documented - -  ┌─────────── Drug B ┐
//   │                   │                      │                   │
//   ├─[A-only]          ├── sub/inh ─[SHARED]─ inh ──┤          [B-only]─┤
//
// Each drug hangs its relations from a vertical trunk; a branch ends at the
// protein pill with a dot, so a line passing behind a pill can never be read as
// ending there. Proteins documented for both drugs sit in the middle column.
// Pathway membership is a separate dot matrix (protein × pathway), not a web of
// lines. The documented-interaction link between the drugs never has an
// arrowhead: for most DrugBank interaction types the export's drug order is not
// verified, and the drawing must not claim what the data does not support.
import type { MechanismFinding, MechanismGraph, PairReport, Relation } from "../data/v3";

export const MONO_EM = 0.6; // IBM Plex Mono: every glyph is 600/1000 em wide
export const monoWidth = (s: string, size: number) => s.length * MONO_EM * size;

export type Side = "a" | "b" | "shared";

export interface DProtein { id: string; gene: string; uniprot: string | null; side: Side; hyps: string[] }
export interface DLink { drug: "a" | "b"; protein: string; relation: Relation | null; roles: string[] }
export interface DPathway { id: string; ref: string; name: string; n: number | null }
export interface DMembership { protein: string; pathway: string }

export interface DiagramData {
  source: "graph" | "report";
  drugA: { id: string; name: string };
  drugB: { id: string; name: string };
  proteins: DProtein[];
  links: DLink[];
  pathways: DPathway[];
  membership: DMembership[];
  /** Documented interaction between the drugs: none, or present with the
   *  direction status of the underlying records. */
  documented: "none" | "undirected" | "verified_order";
  truncated: number;
}

const hypRefs = (findings: MechanismFinding[]) => {
  const m = new Map<string, string[]>();
  findings.forEach((f, i) => {
    if (f.pattern === "shared_annotation") return;
    const k = f.protein.uniprot;
    m.set(k, [...(m.get(k) ?? []), `H${i + 1}`]);
  });
  return m;
};

const documentedState = (r: PairReport | null, g: MechanismGraph | null): DiagramData["documented"] => {
  if (g) {
    const e = g.edges.filter((x) => x.kind === "documented_interaction");
    if (!e.length) return "none";
    return e.every((x) => x.directed === true) ? "verified_order" : "undirected";
  }
  const db = (r?.evidence ?? []).filter((e) => e.category === "database_interaction_record");
  if (!db.length) return "none";
  return db.every((e) => e.direction === "as_exported_verified") ? "verified_order" : "undirected";
};

/** Normalise the /api/v3/graph response (preferred) or, without one, the
 *  report's mechanism block, into the diagram's data. */
export function diagramData(report: PairReport | null, graph: MechanismGraph | null, names: { a: string; b: string }): DiagramData {
  const findings = report?.mechanism.findings ?? [];
  const hyps = hypRefs(findings);
  if (graph) {
    const proteins: DProtein[] = graph.nodes.filter((n) => n.kind === "protein").map((n) => {
      const uniprot = String((n.detail as { uniprot?: string }).uniprot ?? n.id.replace(/^P:/, ""));
      return { id: n.id, gene: n.label, uniprot, side: n.side === "a" || n.side === "b" ? n.side : "shared", hyps: hyps.get(uniprot) ?? [] };
    });
    const pathwayNodes = graph.nodes.filter((n) => n.kind === "pathway");
    const pathways: DPathway[] = pathwayNodes.map((n, i) => {
      const d = n.detail as { reactome_id?: string; n_proteins_in_pathway?: number };
      return { id: d.reactome_id ?? n.id, ref: `R${i + 1}`, name: n.label, n: d.n_proteins_in_pathway ?? null };
    });
    const byNode = new Map(pathwayNodes.map((n, i) => [n.id, pathways[i].id]));
    const links: DLink[] = graph.edges.filter((e) => e.kind === "annotation").map((e) => {
      const d = e.detail as { relation?: Relation; roles?: string[] };
      return { drug: e.source === graph.drug_a ? "a" : "b", protein: e.target, relation: d.relation ?? null, roles: d.roles ?? [] };
    });
    const membership = graph.edges.filter((e) => e.kind === "pathway_membership" && byNode.has(e.target))
      .map((e) => ({ protein: e.source, pathway: byNode.get(e.target)! }));
    return {
      source: "graph", drugA: { id: graph.drug_a, name: names.a }, drugB: { id: graph.drug_b, name: names.b },
      proteins, links, pathways, membership,
      documented: documentedState(report, graph),
      truncated: (graph.truncated.proteins_a ?? 0) + (graph.truncated.proteins_b ?? 0),
    };
  }
  // From the report alone: the proteins documented for both drugs.
  const r = report!;
  const seen = new Map<string, DProtein>();
  for (const f of findings) {
    const id = `P:${f.protein.uniprot}`;
    if (!seen.has(id)) seen.set(id, { id, gene: f.protein.gene, uniprot: f.protein.uniprot, side: "shared", hyps: hyps.get(f.protein.uniprot) ?? [] });
  }
  const links: DLink[] = Object.values(r.mechanism.annotations)
    .filter((a) => seen.has(`P:${a.uniprot}`) && (a.drug_id === r.drug_a.id || a.drug_id === r.drug_b.id))
    .map((a) => ({ drug: a.drug_id === r.drug_a.id ? "a" : "b", protein: `P:${a.uniprot}`, relation: a.relation, roles: a.roles }));
  const pathways: DPathway[] = r.mechanism.shared_pathways.map((p, i) => ({ id: p.id, ref: `R${i + 1}`, name: p.name, n: p.n_proteins_in_pathway }));
  // via_a / via_b name genes; a gene seen through both drugs is shared.
  const genes = new Map<string, Side>();
  for (const p of r.mechanism.shared_pathways) {
    for (const g of p.via_a) genes.set(g, genes.get(g) === "b" || genes.get(g) === "shared" ? "shared" : "a");
    for (const g of p.via_b) genes.set(g, genes.get(g) === "a" || genes.get(g) === "shared" ? "shared" : "b");
  }
  const geneProteins: DProtein[] = [];
  const geneId = (g: string) => {
    const hit = Array.from(seen.values()).find((p) => p.gene === g);
    return hit ? hit.id : `G:${g}`;
  };
  for (const [g, side] of genes) {
    if (!Array.from(seen.values()).some((p) => p.gene === g)) geneProteins.push({ id: `G:${g}`, gene: g, uniprot: null, side, hyps: [] });
  }
  const membership: DMembership[] = [];
  for (const p of r.mechanism.shared_pathways) {
    for (const g of new Set([...p.via_a, ...p.via_b])) membership.push({ protein: geneId(g), pathway: p.id });
  }
  return {
    source: "report", drugA: { id: r.drug_a.id, name: names.a }, drugB: { id: r.drug_b.id, name: names.b },
    // Pathway-only genes appear in the membership matrix, not as graph nodes:
    // the report does not say how each drug relates to them.
    proteins: [...seen.values(), ...geneProteins],
    links, pathways, membership, documented: documentedState(r, null), truncated: 0,
  };
}

// ------------------------------------------------------------------- layout --

export interface Box { x: number; y: number; w: number; h: number }
export interface PlacedPill extends Box { protein: DProtein; label: string }
export interface Branch { drug: "a" | "b"; x1: number; x2: number; y: number; relation: Relation | null; roles: string; shared: boolean }
export interface Trunk { x: number; y1: number; y2: number; drug: "a" | "b" }
export interface MatrixCell { x: number; y: number; side: Side }

export interface MechanismLayout {
  width: number;
  height: number;
  boxA: Box;
  boxB: Box;
  link: { x1: number; x2: number; y: number } | null;
  headers: { x: number; y: number; text: string; anchor: "start" | "middle" | "end" }[];
  pills: PlacedPill[];
  trunks: Trunk[];
  branches: Branch[];
  /** Pathway membership matrix, below the graph. */
  matrix: null | {
    x: number; y: number; rowLabels: { x: number; y: number; text: string }[];
    colLabels: { x: number; y: number; text: string }[]; cells: MatrixCell[]; w: number; h: number;
  };
  /** Every text placed, with its box, for the overlap test. */
  labels: (Box & { text: string })[];
}

export const L = {
  pillH: 11,
  row: 17,
  pillFont: 6.4,
  roleFont: 5.2,
  headerFont: 5.8,
  boxH: 36,
  topRows: 74,
  matrixCell: 13,
  matrixFont: 5.8,
};

const ROLE_SHORT: Record<string, { ru: string; en: string }> = {
  substrate: { ru: "суб", en: "sub" },
  inhibitor: { ru: "инг", en: "inh" },
  inducer: { ru: "инд", en: "ind" },
  activating: { ru: "акт", en: "act" },
  inhibiting: { ru: "инг", en: "inh" },
  unspecified: { ru: "н/у", en: "n/s" },
};
export const roleShort = (r: string, lang: "ru" | "en") => ROLE_SHORT[r]?.[lang] ?? r.slice(0, 3);

export function layoutMechanism(d: DiagramData, width: number, lang: "ru" | "en", headers: { onlyA: string; onlyB: string; shared: string }): MechanismLayout {
  const linked = new Set(d.links.map((l) => l.protein));
  // Proteins drawn as graph nodes: those with a documented drug relation.
  const nodeProteins = d.proteins.filter((p) => linked.has(p.id));
  const col = (s: Side) => nodeProteins.filter((p) => p.side === s);
  const onlyA = col("a"), shared = col("shared"), onlyB = col("b");
  const label = (p: DProtein) => (p.hyps.length ? `${p.gene} · ${p.hyps.join(",")}` : p.gene);
  const pillW = (p: DProtein) => monoWidth(label(p), L.pillFont) + 10;
  const rows = Math.max(onlyA.length, shared.length, onlyB.length, 1);

  const boxW = width * 0.38;
  const boxA: Box = { x: 0, y: 4, w: boxW, h: L.boxH };
  const boxB: Box = { x: width - boxW, y: 4, w: boxW, h: L.boxH };
  const link = { x1: boxA.x + boxA.w, x2: boxB.x, y: boxA.y + boxA.h / 2 };

  const branchSpan = 46;
  const rowY = (i: number) => L.topRows + i * L.row;
  const sharedMaxW = Math.max(0, ...shared.map(pillW));
  const sharedLeft = width / 2 - sharedMaxW / 2;
  const sharedRight = width / 2 + sharedMaxW / 2;
  const trunkAOwn = 6, trunkBOwn = width - 6;
  const trunkAShared = sharedLeft - branchSpan, trunkBShared = sharedRight + branchSpan;

  const pills: PlacedPill[] = [];
  const branches: Branch[] = [];
  const trunks: Trunk[] = [];
  const labels: (Box & { text: string })[] = [];
  const linksOf = (pid: string, drug: "a" | "b") => d.links.filter((l) => l.protein === pid && l.drug === drug);
  // Role abbreviations above a branch; shortened with "+" if they would not fit.
  const rolesText = (ls: DLink[]) => {
    const all = Array.from(new Set(ls.flatMap((l) => l.roles))).map((r) => roleShort(r, lang));
    for (let k = all.length; k > 0; k--) {
      const s = all.slice(0, k).join("/") + (k < all.length ? "+" : "");
      if (monoWidth(s, L.roleFont) <= branchSpan - 6) return s;
    }
    return "";
  };
  const relationOf = (ls: DLink[]) => (ls[0]?.relation ?? null);

  const offset = (n: number) => ((rows - n) * L.row) / 2;
  onlyA.forEach((p, i) => {
    const y = rowY(i) + offset(onlyA.length);
    const w = pillW(p);
    pills.push({ x: trunkAOwn + 16, y: y - L.pillH / 2, w, h: L.pillH, protein: p, label: label(p) });
    branches.push({ drug: "a", x1: trunkAOwn, x2: trunkAOwn + 16, y, relation: relationOf(linksOf(p.id, "a")), roles: "", shared: false });
  });
  onlyB.forEach((p, i) => {
    const y = rowY(i) + offset(onlyB.length);
    const w = pillW(p);
    pills.push({ x: trunkBOwn - 16 - w, y: y - L.pillH / 2, w, h: L.pillH, protein: p, label: label(p) });
    branches.push({ drug: "b", x1: trunkBOwn - 16, x2: trunkBOwn, y, relation: relationOf(linksOf(p.id, "b")), roles: "", shared: false });
  });
  shared.forEach((p, i) => {
    const y = rowY(i) + offset(shared.length);
    const w = pillW(p);
    const x = width / 2 - w / 2;
    pills.push({ x, y: y - L.pillH / 2, w, h: L.pillH, protein: p, label: label(p) });
    const la = linksOf(p.id, "a"), lb = linksOf(p.id, "b");
    if (la.length) branches.push({ drug: "a", x1: trunkAShared, x2: x, y, relation: relationOf(la), roles: rolesText(la), shared: true });
    if (lb.length) branches.push({ drug: "b", x1: x + w, x2: trunkBShared, y, relation: relationOf(lb), roles: rolesText(lb), shared: true });
  });

  const lastY = (bs: Branch[]) => Math.max(...bs.map((b) => b.y));
  const boxBottom = boxA.y + boxA.h;
  const ownA = branches.filter((b) => b.drug === "a" && !b.shared);
  const ownB = branches.filter((b) => b.drug === "b" && !b.shared);
  const shA = branches.filter((b) => b.drug === "a" && b.shared);
  const shB = branches.filter((b) => b.drug === "b" && b.shared);
  if (ownA.length) trunks.push({ drug: "a", x: trunkAOwn, y1: boxBottom, y2: lastY(ownA) });
  if (ownB.length) trunks.push({ drug: "b", x: trunkBOwn, y1: boxBottom, y2: lastY(ownB) });
  if (shA.length) trunks.push({ drug: "a", x: trunkAShared, y1: boxBottom, y2: lastY(shA) });
  if (shB.length) trunks.push({ drug: "b", x: trunkBShared, y1: boxBottom, y2: lastY(shB) });

  const hy = L.topRows - 14;
  const hdrs: MechanismLayout["headers"] = [];
  if (onlyA.length) hdrs.push({ x: trunkAOwn + 16, y: hy, text: headers.onlyA, anchor: "start" });
  if (shared.length) hdrs.push({ x: width / 2, y: hy, text: headers.shared, anchor: "middle" });
  if (onlyB.length) hdrs.push({ x: trunkBOwn - 16, y: hy, text: headers.onlyB, anchor: "end" });
  for (const h of hdrs) {
    const w = monoWidth(h.text, L.headerFont);
    const x = h.anchor === "start" ? h.x : h.anchor === "end" ? h.x - w : h.x - w / 2;
    labels.push({ x, y: h.y - L.headerFont, w, h: L.headerFont * 1.2, text: h.text });
  }
  for (const p of pills) labels.push({ x: p.x, y: p.y, w: p.w, h: p.h, text: p.label });
  for (const b of branches) {
    if (!b.roles) continue;
    const w = monoWidth(b.roles, L.roleFont);
    const cx = (b.x1 + b.x2) / 2;
    labels.push({ x: cx - w / 2, y: b.y - 2.2 - L.roleFont, w, h: L.roleFont, text: b.roles });
  }

  let height = rowY(rows - 1) + L.row / 2 + 6;

  // Pathway membership matrix.
  let matrix: MechanismLayout["matrix"] = null;
  const memberProteins = d.proteins.filter((p) => d.membership.some((m) => m.protein === p.id));
  if (d.pathways.length && memberProteins.length) {
    const order: Side[] = ["a", "shared", "b"];
    memberProteins.sort((x, y) => order.indexOf(x.side) - order.indexOf(y.side) || x.gene.localeCompare(y.gene));
    const labelW = Math.max(...memberProteins.map((p) => monoWidth(p.gene, L.matrixFont))) + 8;
    const cell = L.matrixCell;
    const top = height + 22;
    const x0 = 0;
    const gridX = x0 + labelW;
    const rowLabels = memberProteins.map((p, i) => ({ x: x0, y: top + i * cell + cell / 2 + L.matrixFont * 0.35, text: p.gene }));
    const colLabels = d.pathways.map((p, j) => ({ x: gridX + j * cell + cell / 2, y: top - 4, text: p.ref }));
    const cells: MatrixCell[] = [];
    memberProteins.forEach((p, i) => d.pathways.forEach((pw, j) => {
      if (d.membership.some((m) => m.protein === p.id && m.pathway === pw.id)) cells.push({ x: gridX + j * cell + cell / 2, y: top + i * cell + cell / 2, side: p.side });
    }));
    const w = labelW + d.pathways.length * cell;
    const h = memberProteins.length * cell;
    matrix = { x: x0, y: top, rowLabels, colLabels, cells, w, h };
    for (const r of rowLabels) labels.push({ x: r.x, y: r.y - L.matrixFont, w: monoWidth(r.text, L.matrixFont), h: L.matrixFont * 1.1, text: r.text });
    for (const c of colLabels) {
      const w2 = monoWidth(c.text, L.matrixFont);
      labels.push({ x: c.x - w2 / 2, y: c.y - L.matrixFont, w: w2, h: L.matrixFont * 1.1, text: c.text });
    }
    height = top + h + 4;
  }
  return { width, height, boxA, boxB, link: d.documented === "none" ? null : link, headers: hdrs, pills, trunks, branches, matrix, labels };
}

// -------------------------------------------------------- pairwise network --

export interface NetNode { id: string; x: number; y: number; index: number; label: string; labelX: number; labelY: number; anchor: "start" | "end" | "middle" }

/** Circle layout for up to eight drugs; labels outside the ring, sized so they
 *  stay inside the frame. Labels use the mono face so their width is exact. */
export function layoutNetwork(ids: string[], names: string[], width: number, height: number, font: number): { nodes: NetNode[]; r: number } {
  const n = ids.length;
  const longest = Math.max(...names.map((s) => monoWidth(s, font)));
  const cx = width / 2, cy = height / 2;
  // Room for a label above the top node and below the bottom one, and beside the side ones.
  const r = Math.max(30, Math.min(height / 2 - 20, width / 2 - longest - 22));
  const nodes = ids.map((id, i) => {
    const ang = -Math.PI / 2 + (2 * Math.PI * i) / n;
    const x = cx + r * Math.cos(ang), y = cy + r * Math.sin(ang);
    const c = Math.cos(ang);
    const anchor: NetNode["anchor"] = Math.abs(c) < 0.2 ? "middle" : c > 0 ? "start" : "end";
    const lx = x + (anchor === "start" ? 12 : anchor === "end" ? -12 : 0);
    const ly = y + (anchor === "middle" ? (Math.sin(ang) < 0 ? -11 : 15) : 2.5);
    return { id, x, y, index: i + 1, label: names[i], labelX: lx, labelY: ly, anchor };
  });
  return { nodes, r };
}

export function labelBox(n: NetNode, font: number): Box {
  const w = monoWidth(n.label, font);
  const x = n.anchor === "start" ? n.labelX : n.anchor === "end" ? n.labelX - w : n.labelX - w / 2;
  return { x, y: n.labelY - font, w, h: font * 1.2 };
}

export const overlaps = (a: Box, b: Box) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
export const inside = (a: Box, w: number, h: number) => a.x >= -0.01 && a.y >= -0.01 && a.x + a.w <= w + 0.01 && a.y + a.h <= h + 0.01;
