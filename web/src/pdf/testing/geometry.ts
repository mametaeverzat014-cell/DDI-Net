// Test helper: where things are actually drawn on each page of a rendered PDF.
//
// Reads the PDF with pdfjs-dist (independent of the renderer) and returns, per
// page, the page-space bounding box of every text run and every painted path
// (fills and strokes; clip paths are ignored). The checks in render.test.ts use
// it to prove that report content never enters the running header or footer.
//
// Not imported by application code.
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

export interface Rect { x0: number; y0: number; x1: number; y1: number; kind: "text" | "path"; text?: string }
export interface PageGeometry { page: number; width: number; height: number; items: Rect[] }

type M = [number, number, number, number, number, number];
const mul = (a: M, b: M): M => [
  a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3],
  a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
  a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5],
];
const apply = (m: M, x: number, y: number): [number, number] => [x * m[0] + y * m[2] + m[4], x * m[1] + y * m[3] + m[5]];

export async function pageGeometry(bytes: Uint8Array): Promise<PageGeometry[]> {
  const pdfjs = await import("pdfjs-dist/legacy/build/pdf.mjs");
  pdfjs.GlobalWorkerOptions.workerSrc = require.resolve("pdfjs-dist/legacy/build/pdf.worker.mjs");
  const OPS = pdfjs.OPS as Record<string, number>;
  const painted = new Set([OPS.stroke, OPS.closeStroke, OPS.fill, OPS.eoFill, OPS.fillStroke, OPS.eoFillStroke, OPS.closeFillStroke, OPS.closeEOFillStroke]);
  const doc = await pdfjs.getDocument({ data: bytes.slice(), disableFontFace: true, verbosity: 0 }).promise;
  const out: PageGeometry[] = [];
  for (let n = 1; n <= doc.numPages; n++) {
    const page = await doc.getPage(n);
    const [, , width, height] = page.view;
    const items: Rect[] = [];
    const ops = await page.getOperatorList();
    let ctm: M = [1, 0, 0, 1, 0, 0];
    const stack: M[] = [];
    for (let i = 0; i < ops.fnArray.length; i++) {
      const fn = ops.fnArray[i], args = ops.argsArray[i] as unknown[];
      if (fn === OPS.save) stack.push(ctm);
      else if (fn === OPS.restore) ctm = stack.pop() ?? ctm;
      else if (fn === OPS.transform) ctm = mul(args as unknown as M, ctm);
      else if (fn === OPS.constructPath) {
        const op = args[0] as number;
        const mm = args[2] as ArrayLike<number> | null;
        if (!painted.has(op) || !mm || mm.length < 4 || !Number.isFinite(mm[0])) continue;
        const corners = [apply(ctm, mm[0], mm[1]), apply(ctm, mm[2], mm[3]), apply(ctm, mm[0], mm[3]), apply(ctm, mm[2], mm[1])];
        const xs = corners.map((c) => c[0]), ys = corners.map((c) => c[1]);
        const r: Rect = { kind: "path", x0: Math.min(...xs), x1: Math.max(...xs), y0: Math.min(...ys), y1: Math.max(...ys) };
        // the page's own white background
        if (r.x0 <= 0.5 && r.y0 <= 0.5 && r.x1 >= width - 0.5 && r.y1 >= height - 0.5) continue;
        items.push(r);
      }
    }
    const tc = await page.getTextContent();
    for (const it of tc.items as { str?: string; transform: number[]; width: number; height: number }[]) {
      if (typeof it.str !== "string" || !it.str.trim()) continue;
      const x = it.transform[4], y = it.transform[5];
      const size = Math.hypot(it.transform[2], it.transform[3]) || it.height;
      // baseline y; glyphs reach about 0.25 em below and 0.8 em above it
      items.push({ kind: "text", text: it.str, x0: x, x1: x + it.width, y0: y - 0.25 * size, y1: y + 0.8 * size });
    }
    out.push({ page: n, width, height, items });
  }
  return out;
}

export interface Bands { contentBottom: number; contentTop: number; footerTop: number; headerBottom: number }

/** Items that sit neither inside the content area nor wholly inside the header
 *  or footer band — i.e. content running into the page furniture. */
export function bandViolations(g: PageGeometry, b: Bands, tol = 0.75): Rect[] {
  return g.items.filter((r) => {
    const inContent = r.y0 >= b.contentBottom - tol && r.y1 <= b.contentTop + tol;
    const inFooter = r.y1 <= b.footerTop + tol;
    const inHeader = r.y0 >= b.headerBottom - tol;
    return !(inContent || inFooter || inHeader);
  });
}

export interface Furniture { header: string; footer: string }

const squash = (s: string) => s.replace(/\s+/g, "");

/** Items inside the header or footer band that are not the running header or
 *  footer themselves: report content pushed down (or up) into the furniture.
 *  Only text that is part of the furniture's own strings and thin rules pass. */
export function furnitureIntruders(g: PageGeometry, b: Bands, f: Furniture, tol = 0.75): Rect[] {
  const head = squash(f.header), foot = squash(f.footer);
  return g.items.filter((r) => {
    const inFooter = r.y1 <= b.footerTop + tol;
    const inHeader = r.y0 >= b.headerBottom - tol;
    if (!inFooter && !inHeader) return false;
    if (r.kind === "path") return r.y1 - r.y0 > 1.5;               // only hairline rules belong there
    const s = squash(r.text ?? "");
    return !(inFooter ? foot.includes(s) : head.includes(s));
  });
}

/** Pairs of text runs drawn on top of each other (different lines occupying
 *  the same place) — what a compressed or collapsed block looks like. */
export function overlappingText(g: PageGeometry, minOverlap = 0.35): [Rect, Rect][] {
  const t = g.items.filter((r) => r.kind === "text");
  const out: [Rect, Rect][] = [];
  for (let i = 0; i < t.length; i++) {
    for (let j = i + 1; j < t.length; j++) {
      const a = t[i], c = t[j];
      const w = Math.min(a.x1, c.x1) - Math.max(a.x0, c.x0);
      if (w <= 1) continue;
      // tight glyph boxes: baseline to about 0.7 em above it
      const ha = (a.y1 - a.y0) / 1.05, hc = (c.y1 - c.y0) / 1.05;
      const ba = a.y0 + 0.25 * ha, bc = c.y0 + 0.25 * hc;
      if (Math.abs(ba - bc) < 0.6) continue;                      // same line, adjacent runs
      const h = Math.min(ba + 0.7 * ha, bc + 0.7 * hc) - Math.max(ba, bc);
      if (h > minOverlap * Math.min(0.7 * ha, 0.7 * hc)) out.push([a, c]);
    }
  }
  return out;
}
