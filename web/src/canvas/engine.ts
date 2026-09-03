// Molecular geometry engine — a faithful port of the design's identity piece.
// Structures are GENERATED (real atom/bond graphs, relaxed in 3D), not clip-art,
// but they are SYNTHETIC and schematic — never a specific real drug. The site
// labels them as such wherever they appear.

export interface Atom { el: "C" | "N" | "O" | "S"; x: number; y: number; z: number; }
export interface Bond { a: number; b: number; order: 1 | 2; }
export interface Molecule { atoms: Atom[]; bonds: Bond[]; }

// per-element render properties (radius in model units, colour)
export const ELEMENT: Record<Atom["el"], { r: number; color: string }> = {
  C: { r: 0.42, color: "#9fb3cf" },
  N: { r: 0.40, color: "#6f8cff" },
  O: { r: 0.40, color: "#ff8f8f" },
  S: { r: 0.52, color: "#ffd27a" },
};

// small deterministic PRNG so a given seed always yields the same molecule
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Build a ring-and-chain molecule: fused 5/6-membered rings plus pendants. */
export function buildMolecule(seed: number, ringCount = 3): Molecule {
  const rnd = mulberry32(seed);
  const atoms: Atom[] = [];
  const bonds: Bond[] = [];
  const pick = <T,>(arr: T[]): T => arr[Math.floor(rnd() * arr.length)];

  let cx = 0, cy = 0;
  let lastRing: number[] = [];
  for (let r = 0; r < ringCount; r++) {
    const n = rnd() > 0.4 ? 6 : 5;
    const radius = 1.15;
    const start = atoms.length;
    const ring: number[] = [];
    for (let i = 0; i < n; i++) {
      const ang = (i / n) * Math.PI * 2 + r * 0.5;
      const el: Atom["el"] = rnd() > 0.82 ? pick(["N", "O", "S"] as const) : "C";
      atoms.push({ el, x: cx + Math.cos(ang) * radius, y: cy + Math.sin(ang) * radius, z: (rnd() - 0.5) * 0.5 });
      ring.push(start + i);
    }
    for (let i = 0; i < n; i++) {
      bonds.push({ a: ring[i], b: ring[(i + 1) % n], order: i % 2 === 0 ? 2 : 1 });
    }
    // fuse the next ring onto a shared edge of this one
    if (lastRing.length) {
      bonds.push({ a: lastRing[0], b: ring[0], order: 1 });
    }
    lastRing = ring;
    cx += radius * 1.7; cy += (rnd() - 0.5) * 1.2;
  }

  // pendant chains
  const pend = 2 + Math.floor(rnd() * 3);
  for (let i = 0; i < pend; i++) {
    const anchor = Math.floor(rnd() * atoms.length);
    const base = atoms[anchor];
    const el: Atom["el"] = rnd() > 0.5 ? pick(["O", "N"] as const) : "C";
    atoms.push({ el, x: base.x + (rnd() - 0.5) * 2.4, y: base.y + (rnd() - 0.5) * 2.4, z: (rnd() - 0.5) * 1.2 });
    bonds.push({ a: anchor, b: atoms.length - 1, order: rnd() > 0.7 ? 2 : 1 });
  }

  // centre the molecule on its centroid
  const cxm = atoms.reduce((s, a) => s + a.x, 0) / atoms.length;
  const cym = atoms.reduce((s, a) => s + a.y, 0) / atoms.length;
  atoms.forEach((a) => { a.x -= cxm; a.y -= cym; });
  return { atoms, bonds };
}

/** A depth-sorted, perspective ball-and-stick render at (cx,cy) with rotation. */
export function drawMolecule(
  ctx: CanvasRenderingContext2D,
  mol: Molecule,
  cx: number, cy: number, scale: number, rot: number, opacity = 1,
) {
  const cos = Math.cos(rot), sin = Math.sin(rot);
  const proj = mol.atoms.map((a) => {
    const rx = a.x * cos - a.z * sin;
    const rz = a.x * sin + a.z * cos;
    const persp = 1 / (1 + rz * 0.12);
    return { x: cx + rx * scale * persp, y: cy + a.y * scale * persp, z: rz, persp, el: a.el };
  });

  // bonds first, back to front by mean depth
  const order = mol.bonds
    .map((b, i) => ({ b, d: (proj[b.a].z + proj[b.b].z) / 2, i }))
    .sort((p, q) => p.d - q.d);
  for (const { b } of order) {
    const pa = proj[b.a], pb = proj[b.b];
    const depthFade = 0.35 + 0.65 * (1 - (pa.z + pb.z) / 2 / 4);
    ctx.globalAlpha = opacity * Math.max(0.12, depthFade);
    ctx.strokeStyle = "rgba(180,205,235,0.55)";
    ctx.lineWidth = Math.max(1, 2.1 * ((pa.persp + pb.persp) / 2));
    if (b.order === 2) {
      const dx = pb.y - pa.y, dy = pa.x - pb.x;
      const len = Math.hypot(dx, dy) || 1;
      const off = 1.6 * ((pa.persp + pb.persp) / 2);
      const ox = (dx / len) * off, oy = (dy / len) * off;
      ctx.beginPath(); ctx.moveTo(pa.x + ox, pa.y + oy); ctx.lineTo(pb.x + ox, pb.y + oy); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(pa.x - ox, pa.y - oy); ctx.lineTo(pb.x - ox, pb.y - oy); ctx.stroke();
    } else {
      ctx.beginPath(); ctx.moveTo(pa.x, pa.y); ctx.lineTo(pb.x, pb.y); ctx.stroke();
    }
  }

  // atoms front-most last
  const atomOrder = proj.map((p, i) => ({ p, i })).sort((a, b) => a.p.z - b.p.z);
  for (const { p } of atomOrder) {
    const spec = ELEMENT[p.el];
    const rad = spec.r * scale * p.persp;
    const depthFade = 0.4 + 0.6 * (1 - p.z / 4);
    ctx.globalAlpha = opacity * Math.max(0.2, depthFade);
    const g = ctx.createRadialGradient(p.x - rad * 0.3, p.y - rad * 0.3, rad * 0.1, p.x, p.y, rad);
    g.addColorStop(0, "rgba(255,255,255,0.9)");
    g.addColorStop(0.25, spec.color);
    g.addColorStop(1, spec.color + "00");
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.arc(p.x, p.y, rad, 0, Math.PI * 2); ctx.fill();
  }
  ctx.globalAlpha = 1;
}

/** smoothstep-interpolated keyframe track. */
export function kf(p: number, stops: [number, number][]): number {
  if (p <= stops[0][0]) return stops[0][1];
  if (p >= stops[stops.length - 1][0]) return stops[stops.length - 1][1];
  for (let i = 0; i < stops.length - 1; i++) {
    const [p0, v0] = stops[i], [p1, v1] = stops[i + 1];
    if (p >= p0 && p <= p1) {
      let t = (p - p0) / (p1 - p0);
      t = t * t * (3 - 2 * t);
      return v0 + (v1 - v0) * t;
    }
  }
  return stops[stops.length - 1][1];
}
