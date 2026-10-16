// @vitest-environment node
// End-to-end checks of generated PDFs. Each report is rendered by the same code
// path the browser uses (renderPdf), from recorded API responses, and then read
// back with an independent parser (pdfjs-dist) and the font files themselves.
//
// Fixtures in __fixtures__ are real responses of the DDI-Net 3.0 API captured
// from a local server, except pair_synthetic_labels_no_model.json (see its
// _comment) and the variants built below, which are marked SYNTHETIC.
import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import type { MultiReport, PairReport } from "../data/v3";
import { evidenceCountsText, groupEvidence } from "../data/evidenceGroups";
import { renderPdf } from "./exportReport";
import { prepareExport } from "./format";
import { PAGE } from "./theme";
import type { ExportContext, ExportInput, PreparedExport } from "./types";

const require = createRequire(import.meta.url);
const ROOT = join(__dirname, "..", "..");
const FONT_DIR = join(ROOT, "public", "fonts", "pdf");
const font = (f: string) => join(FONT_DIR, f);
const fx = (n: string) => JSON.parse(readFileSync(join(__dirname, "__fixtures__", n), "utf8"));
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x));

interface Item { str: string; x: number; y: number; w: number }
interface Parsed { maxCoord: number; prep: PreparedExport; bytes: Uint8Array; raw: string; pages: string[]; items: Item[][]; text: string; flat: string; numPages: number; info: Record<string, unknown>; sizes: number[][] }

async function parse(prep: PreparedExport, bytes: Uint8Array): Promise<Parsed> {
  const pdfjs = await import("pdfjs-dist/legacy/build/pdf.mjs");
  pdfjs.GlobalWorkerOptions.workerSrc = require.resolve("pdfjs-dist/legacy/build/pdf.worker.mjs");
  const doc = await pdfjs.getDocument({ data: bytes.slice(), disableFontFace: true, verbosity: 0 }).promise;
  const pages: string[] = [], items: Item[][] = [], sizes: number[][] = [];
  let maxCoord = 0;
  for (let i = 1; i <= doc.numPages; i++) {
    const p = await doc.getPage(i);
    sizes.push(p.view);
    // Largest absolute number among drawing operators: catches layout blow-ups
    // (a box placed millions of points off the page) that render invisibly.
    const ops = await p.getOperatorList();
    for (const args of ops.argsArray) {
      const walk = (a: unknown): void => {
        if (typeof a === "number") maxCoord = Math.max(maxCoord, Math.abs(a));
        else if (Array.isArray(a) || ArrayBuffer.isView(a)) Array.from(a as ArrayLike<unknown>).forEach(walk);
      };
      walk(args);
    }
    const tc = await p.getTextContent();
    const its: Item[] = [];
    let s = "";
    for (const it of tc.items as { str?: string; transform: number[]; width: number; hasEOL?: boolean }[]) {
      if (typeof it.str !== "string") continue;
      s += it.str + (it.hasEOL ? "\n" : "");
      if (it.str.trim()) its.push({ str: it.str, x: it.transform[4], y: it.transform[5], w: it.width });
    }
    pages.push(s);
    items.push(its);
  }
  const meta = await doc.getMetadata();
  const text = pages.join("\n");
  return {
    maxCoord, prep, bytes, raw: Buffer.from(bytes).toString("latin1"), pages, items, text,
    flat: text.replace(/\s+/g, " "), numPages: doc.numPages, info: meta.info as Record<string, unknown>, sizes,
  };
}

const ctx = (lang: "ru" | "en", variant: "full" | "quick" = "full"): ExportContext => ({ variant,
  lang, now: new Date("2026-10-14T09:15:00.000Z"), timeZone: "Europe/Moscow", siteOrigin: "https://preview.example.test", siteCommit: "5e6781d",
});

async function make(input: ExportInput, lang: "ru" | "en", variant: "full" | "quick" = "full"): Promise<Parsed> {
  const prep = await prepareExport(input, ctx(lang, variant));
  const blob = await renderPdf(prep, font);
  return parse(prep, new Uint8Array(await blob.arrayBuffer()));
}

const wf = fx("pair_warfarin_fluconazole.json");
const sc = fx("pair_simvastatin_clarithromycin.json");
const mw = fx("pair_metformin_warfarin.json");
const m8 = fx("multi_8.json");
const syn = fx("pair_synthetic_labels_no_model.json");
const dup = fx("pair_synthetic_duplicated_labels.json");

// SYNTHETIC variants of real responses, for edge cases the real data lacks.
function longNames(): ExportInput {
  const m = clone(m8);
  m.data.drugs = m.data.drugs.map((d: MultiReport["drugs"][number], i: number) => ({
    ...d,
    inn: `supercalifragilisticexpialidociousamycin-hydrochloride-monohydrate-${i}`,
    name_ru: `сверхдлинноеназваниепрепаратадляпроверкипереноса строки-${i}`,
  }));
  return { kind: "multi", report: m };
}
function missingFields(): ExportInput {
  const r = clone(syn.report);
  delete r.meta;
  r.data.drug_b.inn = null;
  r.data.drug_b.name_ru = null;
  return { kind: "pair", origin: "analyzer", report: r };
}
function hostile(): ExportInput {
  const r = clone(wf.report);
  r.data.drug_a.query = "<b>warfarin</b>\u0007<script>x</script>";
  r.data.evidence[0].source_url = "javascript:alert(1)";
  r.data.evidence[0].retrieval_url = "data:text/html,<b>x</b>";
  return { kind: "pair", origin: "analyzer", report: r };
}

const docs: Record<string, Parsed> = {};
const realInputs: Record<string, [ExportInput, "en" | "ru"]> = {
  wfEn: [{ kind: "pair", origin: "analyzer", report: wf.report }, "en"],
  wfRu: [{ kind: "pair", origin: "analyzer", report: wf.report }, "ru"],
  scEn: [{ kind: "pair", origin: "mechanisms", report: sc.report, graph: sc.graph }, "en"],
  scRu: [{ kind: "pair", origin: "mechanisms", report: sc.report, graph: sc.graph }, "ru"],
  mwEn: [{ kind: "pair", origin: "mechanisms", report: mw.report, graph: mw.graph }, "en"],
  m8En: [{ kind: "multi", report: m8 }, "en"],
  m8Ru: [{ kind: "multi", report: m8 }, "ru"],
};
const synthInputs: Record<string, [ExportInput, "en" | "ru"]> = {
  synEn: [missingFields(), "en"],
  longRu: [longNames(), "ru"],
  hostileEn: [hostile(), "en"],
  // SYNTHETIC label text in the structure of a real old-format label that
  // repeats its Drug Interactions subsection (as an older API returned it)
  dupEn: [{ kind: "pair", origin: "analyzer", report: dup.report }, "en"],
  dupRu: [{ kind: "pair", origin: "analyzer", report: dup.report }, "ru"],
};

// Outcome-engine responses (captured from the current API; synMerged has SYNTHETIC label text).
const owf = fx("pair_outcomes_warfarin_fluconazole.json");
const omw = fx("pair_outcomes_metformin_warfarin.json");
const synMerged = fx("pair_synthetic_merged_labels.json");
const refWf = fx("pair_reference_warfarin_fluconazole.json");
const outcomeInputs: Record<string, [ExportInput, "en" | "ru", "full" | "quick"]> = {
  oSynEn: [{ kind: "pair", origin: "analyzer", report: synMerged.report }, "en", "full"],
  oSynRu: [{ kind: "pair", origin: "analyzer", report: synMerged.report }, "ru", "full"],
  qSynRu: [{ kind: "pair", origin: "analyzer", report: synMerged.report }, "ru", "quick"],
  qSynEn: [{ kind: "pair", origin: "analyzer", report: synMerged.report }, "en", "quick"],
  qWfEn: [{ kind: "pair", origin: "analyzer", report: owf.report }, "en", "quick"],
  qMwRu: [{ kind: "pair", origin: "analyzer", report: omw.report }, "ru", "quick"],
  rWfEn: [{ kind: "pair", origin: "analyzer", report: refWf.report }, "en", "full"],
  rWfRu: [{ kind: "pair", origin: "analyzer", report: refWf.report }, "ru", "full"],
  qrWfRu: [{ kind: "pair", origin: "analyzer", report: refWf.report }, "ru", "quick"],
};

beforeAll(async () => {
  for (const [k, [input, lang]] of Object.entries({ ...realInputs, ...synthInputs })) {
    docs[k] = await make(input, lang);
    // DDINET_PDF_DUMP=<dir> keeps the generated files for inspection.
    if (process.env.DDINET_PDF_DUMP) writeFileSync(join(process.env.DDINET_PDF_DUMP, `${k}.pdf`), docs[k].bytes);
  }
  for (const [k, [input, lang, variant]] of Object.entries(outcomeInputs)) {
    docs[k] = await make(input, lang, variant);
    // DDINET_PDF_DUMP=<dir> keeps the generated files for inspection.
    if (process.env.DDINET_PDF_DUMP) writeFileSync(join(process.env.DDINET_PDF_DUMP, `${k}.pdf`), docs[k].bytes);
  }
}, 300_000);

const all = () => Object.entries(docs);
const nospace = (s: string) => s.replace(/\s+/g, "");

describe("PDF files", () => {
  it("are valid, non-empty, A4 and readable by an independent parser", () => {
    for (const [k, d] of all()) {
      expect(d.bytes.length, k).toBeGreaterThan(30_000);
      expect(d.raw.startsWith("%PDF-1."), k).toBe(true);
      expect(d.raw.trimEnd().endsWith("%%EOF"), k).toBe(true);
      expect(d.numPages, k).toBeGreaterThanOrEqual(d.prep.ctx.variant === "quick" ? 1 : 5);
      for (const v of d.sizes) expect(v.map((x) => Math.round(x)), k).toEqual([0, 0, 595, 842]);
      expect(String(d.info.Producer), k).toContain("react-pdf");
      expect(String(d.info.Title), k).toMatch(/Report|Отчёт|отчёт/i);
    }
    expect(docs.wfEn.numPages).toBeLessThanOrEqual(14);
    expect(docs.m8En.numPages).toBeLessThanOrEqual(12);
  });

  it("draw nothing at absurd coordinates on any page (running header and footer stay put)", () => {
    for (const [k, d] of all()) expect(d.maxCoord, k).toBeLessThan(10_000);
  });

  it("embed every font, and only IBM Plex", () => {
    for (const [k, d] of all()) {
      const fonts = Array.from(new Set(d.raw.match(/\/BaseFont \/[A-Za-z0-9+_-]+/g) ?? []));
      expect(fonts.length, k).toBeGreaterThanOrEqual(3);
      for (const f of fonts) expect(f, k).toMatch(/\/BaseFont \/[A-Z]{6}\+IBMPlex/);
      expect((d.raw.match(/\/FontFile2/g) ?? []).length, k).toBeGreaterThanOrEqual(fonts.length);
      expect(d.raw.includes("/Helvetica"), k).toBe(false);
    }
  });

  it("draw every character with a real glyph (Latin, Cyrillic, symbols)", () => {
    const fontkit = require("fontkit") as { openSync(p: string): { hasGlyphForCodePoint(c: number): boolean } };
    const sans = fontkit.openSync(font("IBMPlexSans-Regular.woff"));
    const serif = fontkit.openSync(font("IBMPlexSerif-SemiBold.woff"));
    const mono = fontkit.openSync(font("IBMPlexMono-Regular.woff"));
    let cyrillic = 0;
    for (const [k, d] of all()) {
      for (const ch of new Set(d.text.replace(/\s/g, ""))) {
        const cp = ch.codePointAt(0)!;
        const at = d.text.indexOf(ch);
        expect(sans.hasGlyphForCodePoint(cp), `${k}: U+${cp.toString(16)} near ${JSON.stringify(d.text.slice(at - 50, at + 20))}`).toBe(true);
        if (/[A-Za-z0-9Ѐ-ӿ]/.test(ch)) {
          expect(serif.hasGlyphForCodePoint(cp), `${k}: serif ${ch}`).toBe(true);
          expect(mono.hasGlyphForCodePoint(cp), `${k}: mono ${ch}`).toBe(true);
        }
        if (/[Ѐ-ӿ]/.test(ch)) cyrillic++;
      }
    }
    expect(cyrillic).toBeGreaterThan(40);
  });

  it("keep all text inside the page margins (no overflow, long names wrap)", () => {
    for (const [k, d] of all()) {
      d.items.forEach((its, pi) => {
        for (const it of its) {
          expect(it.x, `${k} p${pi + 1} "${it.str}"`).toBeGreaterThanOrEqual(PAGE.marginX - 1);
          expect(it.x + it.w, `${k} p${pi + 1} "${it.str}"`).toBeLessThanOrEqual(PAGE.width - PAGE.marginX + 1);
          expect(it.y, `${k} p${pi + 1} "${it.str}"`).toBeGreaterThan(14);
          expect(it.y, `${k} p${pi + 1} "${it.str}"`).toBeLessThan(PAGE.height - 14);
        }
      });
    }
  });

  it("have no blank pages", () => {
    for (const [k, d] of all()) {
      d.pages.forEach((p, i) => {
        const body = p.replace(/DDI-NET 3\.0 · [^\n]*\n?/g, "").replace(/(Page|Стр\.) \d+ (of|из) \d+/g, "");
        expect(body.replace(/\s/g, "").length, `${k} page ${i + 1}`).toBeGreaterThan(150);
      });
    }
  });
});

describe("content", () => {
  it("two-drug report (English) carries the analysis on screen", () => {
    const d = docs.wfEn, r = wf.report.data as PairReport;
    for (const s of [
      "DDI-Net 3.0", "Drug–Drug Interaction Research Report", "Warfarin", "Fluconazole", "DB00682", "DB00196",
      "Research use only", "Executive summary", "Drug information", "Documented interactions", "Biological mechanisms",
      "BIO-GINE research analysis", "Sources and reproducibility", "Limitations", "Machine-readable summary",
      "Europe/Moscow, UTC+03:00", "BIO-GINE M4 · bd45f84e3c1b2c33 · seed 0", "0.81", "> 0.9999", "0.812 ± 0.010",
      "neither a per-pair confidence interval nor an ensemble estimate", "not a probability of clinical harm",
      "What the two numbers mean", "Neither number is the probability that the combination harms anyone", "Glossary",
      "Unlabelled pairs are not confirmed safe", "CYP2C9", "H1", "Shared biological pathways (Reactome) · 10",
    ]) expect(d.flat, s).toContain(s);
    expect(d.flat).toContain(d.prep.reportId);
    expect(nospace(d.text)).toContain(d.prep.payloadSha256);
    expect(d.flat).toContain(r.evidence[0].statement);
  });

  it("Russian report is in Russian, with the source's English words kept and labelled", () => {
    const d = docs.wfRu, r = wf.report.data as PairReport;
    for (const s of ["Исследовательский отчёт о взаимодействии препаратов", "Варфарин", "Флуконазол", "Краткое резюме", "Ограничения", "DDI-Net — исследовательский прототип, а не медицинское изделие", "транслитерация", "Стр. 2 из", "Что означают эти два числа", "Словарь терминов", "Что остаётся гипотезой"]) {
      expect(d.flat, s).toContain(s);
    }
    expect(d.flat.toLowerCase()).toContain("перевод проекта (не слова источника)");
    expect(d.flat).toContain(r.evidence[0].statement_ru!);
    expect(d.flat).toContain(r.evidence[0].statement);
  });

  it("cites every source record and reference exactly as given", () => {
    for (const k of ["wfEn", "scEn", "synEn", "dupEn"] as const) {
      const d = docs[k];
      const r = (d.prep.input as Extract<ExportInput, { kind: "pair" }>).report.data;
      const flat = nospace(d.text);
      const g = groupEvidence(r.evidence);
      r.evidence.forEach((e) => {
        if (e.source_url) expect(flat, `${k} url ${e.source_url}`).toContain(nospace(e.source_url));
        if (e.retrieval_url) expect(flat, `${k} retrieval url`).toContain(nospace(e.retrieval_url));
        if (e.source_record_id) expect(flat, `${k} id`).toContain(nospace(e.source_record_id));
        expect(flat, `${k} API record id in Supplement S1`).toContain(nospace(e.id));
        expect(d.flat).toContain(g.excerptOf(e.id)!.label);
        expect(d.flat).toContain(e.retrieved_at);
        if (e.section) expect(d.flat).toContain(e.section);
      });
      for (const f of r.mechanism.findings) {
        for (const id of f.annotation_ids) for (const pmid of r.mechanism.annotations[id]?.pmids ?? []) expect(d.flat, `PMID ${pmid}`).toContain(pmid);
        expect(d.flat).toContain(f.protein.uniprot);
      }
      for (const p of r.mechanism.shared_pathways.slice(0, 3)) expect(flat).toContain(`https://reactome.org/content/detail/${p.id}`);
    }
  });

  it("states no number that is not in the payload", () => {
    const numbers = (v: unknown, out: number[] = []): number[] => {
      if (typeof v === "number") out.push(v);
      else if (v && typeof v === "object") Object.values(v).forEach((x) => numbers(x, out));
      return out;
    };
    for (const k of ["wfEn", "wfRu", "scEn", "m8En", "synEn", "oSynEn", "qWfEn", "qSynRu"] as const) {
      const d = docs[k];
      const input = d.prep.input;
      const pool = numbers(input.kind === "pair" ? [input.report.data, input.graph?.data] : input.report.data).map(Math.abs);
      const formatted = new Set(pool.flatMap((x) => [0, 1, 2, 3, 4, 6].flatMap((n) => [x.toFixed(n), (x * 100).toFixed(1)])));
      // a raw score at the edge of the scale is printed as a bound: "> 0.9999", "< 0.0001"
      const bounds = (d.text.match(/[<>] 0\.(9999|0001)\b/g) ?? []).length;
      const text = d.text
        .replace(/\d{4}-\d{2}-\d{2}T[\d:.]+(Z|[+-]\d{2}:\d{2})?/g, " ")   // timestamps
        .replace(/\b[0-9a-f]{16,}\b/g, " ")                                 // hashes
        .replace(/https?:\S+/g, " ")                                        // URLs
        .replace(/"[a-z_]+":\s*-?[\d.e-]+/g, " ");                          // the JSON appendix copies values verbatim
      const tokens = text.match(/(?<![\d.\w-])[−+-]?\d+\.\d{2,6}(?![\d.])/g) ?? [];
      expect(tokens.length, k).toBeGreaterThan(k === "synEn" || d.prep.ctx.variant === "quick" ? 0 : input.kind === "pair" ? 5 : 10);
      for (const tok of tokens) {
        const v = tok.replace(/^[−+-]/, "");
        const bound = (v === "0.9999" || v === "0.0001") && bounds > 0;
        expect(formatted.has(v) || bound || ["3.0", "0.5", "1.1", "5.1"].includes(v), `${k}: ${tok} is not in the payload`).toBe(true);
      }
      // A score is never turned into a percentage of risk.
      expect(/\b\d{1,3}(\.\d)?\s?% (risk|chance|probability)/i.test(d.flat), k).toBe(false);
    }
  });

  it("never states a DrugBank drug order the audit did not verify", () => {
    for (const k of ["wfEn", "wfRu", "scEn", "scRu", "synEn"] as const) {
      const d = docs[k];
      const r = (d.prep.input as Extract<ExportInput, { kind: "pair" }>).report.data;
      for (const e of r.evidence.filter((x) => x.direction === "not_verified")) {
        expect(e.source_template).toBeTruthy();
        const names = (x: PairReport["drug_a"]) => [x.inn, x.name_ru, x.id].filter(Boolean).flatMap((n) => [n!, n!.charAt(0).toUpperCase() + n!.slice(1)]);
        for (const n1 of names(r.drug_a)) for (const n2 of names(r.drug_b)) {
          for (const [x, y] of [[n1, n2], [n2, n1]]) {
            const filled = e.source_template!.replace("#Drug1", x).replace("#Drug2", y);
            expect(d.flat.includes(filled), `${k}: "${filled}"`).toBe(false);
          }
        }
        expect(d.flat).toContain(e.statement);
      }
      expect(d.flat).toMatch(k.endsWith("Ru") ? /направление не (подтверждено|указано)/ : /direction not verified|no direction stated/);
    }
    // The graph link between the drugs carries no direction.
    expect(docs.scEn.flat).toContain("no direction stated");
    expect(docs.scRu.flat).toContain("направление не указано");
  });

  it("says plainly when nothing is documented, without calling it safe", () => {
    const d = docs.mwEn;
    expect(d.flat).toContain("No documentation found");
    expect(d.flat).toContain("does not mean the combination is safe");
    expect(d.flat).toContain("FDA labels (openFDA)");
    expect(d.flat).toContain("unavailable");
    expect(d.flat).toContain("no interaction record found");
  });

  it("handles missing optional fields without inventing them", () => {
    const d = docs.synEn;
    expect(d.flat).toContain("Model unavailable");
    expect(d.flat).toContain("model not loaded in this synthetic test fixture");
    expect(d.flat).toContain("not recorded");
    expect(d.flat).toContain("none (no DrugCentral match)");
    expect(d.flat).toContain("BOXED WARNING");
    expect(d.flat.toLowerCase()).toContain("verbatim excerpt");
    expect(d.flat).toContain("Model reliance is not given for this pair");
    expect(d.flat).not.toMatch(/Calibrated score\s+\d/);
    expect(d.flat).not.toContain("NaN");
    expect(d.flat).not.toContain("undefined");
    expect(d.flat).not.toMatch(/\bnull\b(?!,|\s*[}\]])/);
  });

  it("multi-drug report covers every drug and pair, and computes no overall score", () => {
    for (const k of ["m8En", "m8Ru"] as const) {
      const d = docs[k];
      const m = m8.data as MultiReport;
      for (const drug of m.drugs) expect(d.flat).toContain(drug.id);
      for (const p of m.pairs) expect(d.flat, `${p.drug_a}-${p.drug_b}`).toContain(`${p.drug_a} · ${p.drug_b}`);
      expect(m.pairs).toHaveLength(28);
    }
    expect(docs.m8En.flat).toContain("There is no overall score for the set, and none is computed");
    expect(docs.m8Ru.flat).toContain("Общего балла для набора препаратов нет");
    expect(docs.m8En.flat).toContain("Pairs whose own record the model was trained on (score not counted): 5");
    expect(docs.m8En.flat).toContain("n/c");
    expect(docs.m8En.flat).not.toMatch(/overall (risk|score)\s*[:=]?\s*\d/i);
  });

  it("long names and large tables wrap instead of overflowing", () => {
    const d = docs.longRu;
    expect(d.numPages).toBeGreaterThanOrEqual(6);
    // wrapped, not cut: every character is there (line-break hyphens aside)
    expect(nospace(d.text).replace(/-/g, "")).toContain("supercalifragilisticexpialidociousamycinhydrochloridemonohydrate7");
  });

  it("prints user-supplied text literally and links only http(s) URLs", () => {
    const d = docs.hostileEn;
    expect(nospace(d.text).replace(/-/g, "")).toContain("<b>warfarin</b><script>x</script>");
    expect(d.flat).toContain("javascript:alert(1)");
    expect(/\/URI\s*\((javascript|data):/i.test(d.raw)).toBe(false);
    expect(/\/URI\s*\(https:\/\/go\.drugbank\.com\/drugs\/DB00682\)/.test(d.raw)).toBe(true);
  });

  it("contains no advice and no safety claim, in either language", () => {
    const forbidden = [
      /\bsafe to (take|combine|use)\b/i, /\bsafe together\b/i, /\byou should\b/i, /\bstop taking\b/i, /\bstart taking\b/i,
      /\b(increase|decrease|reduce|change|adjust) (the|your) dose\b/i, /можно (спокойно )?принимать/i,
      /безопасно (принимать|сочетать|применять)/i, /прекратите/i, /(измените|снизьте|увеличьте|уменьшите) дозу/i,
      /не принимайте/i, /рекомендуем/i,
    ];
    for (const [k, d] of all()) for (const p of forbidden) expect(p.test(d.flat), `${p} in ${k}`).toBe(false);
  });

  it("counts source documents, shows a sentence a label repeats once, and keeps every record's provenance", () => {
    const r = dup.report.data as PairReport;
    const g = groupEvidence(r.evidence);
    expect(r.evidence.filter((e) => e.category !== "database_interaction_record")).toHaveLength(6);   // as the old API sent them
    expect([g.counts.labelDocuments, g.counts.labelExcerpts, g.counts.mergedRepeats]).toEqual([2, 4, 2]);
    for (const [k, lang] of [["dupEn", "en"], ["dupRu", "ru"]] as const) {
      const d = docs[k];
      // the counts line is word for word the site's (data/evidenceGroups.ts)
      expect(d.flat).toContain(evidenceCountsText(g.counts, lang));
      // section 3 (before Supplement S1) quotes the repeated sentence once
      const start = d.flat.indexOf(lang === "en" ? "Source documents" : "Документы-источники");
      const end = d.flat.indexOf(lang === "en" ? "Supplement S1. Evidence records" : "Приложение S1. Записи-доказательства");
      expect(start, k).toBeGreaterThan(0);
      expect(end, k).toBeGreaterThan(start);
      const body = d.flat.slice(start, end);
      const sentence = "Careful monitoring of prothrombin time in patients receiving fluconazole and warfarin";
      expect(body.split(sentence).length - 1, `${k}: repeated sentence in section 3`).toBe(1);
      expect(d.flat).toContain(lang === "en" ? "not separate confirmations" : "не отдельные подтверждения");
      expect(d.flat).toContain(lang === "en" ? "Found in sections: PRECAUTIONS · DRUG INTERACTIONS" : "Найдено в разделах: PRECAUTIONS · DRUG INTERACTIONS");
      // the duplicate records are still listed, and marked as the same text
      expect(d.flat).toContain(lang === "en" ? "same text as [2.1]" : "тот же текст, что [2.1]");
      expect(d.flat).toContain(lang === "en" ? "SYNTHETIC TEST DATA" : "СИНТЕТИЧЕСКИЕ ТЕСТОВЫЕ ДАННЫЕ");
    }
  });

  it("labels the pooled test metric as pooled and never as an S2 figure", () => {
    for (const k of ["wfEn", "wfRu", "scEn"] as const) {
      const d = docs[k];
      const r = (d.prep.input as Extract<ExportInput, { kind: "pair" }>).report.data;
      expect(r.model.regime).toBe("S2");
      if (k.endsWith("Ru")) {
        expect(d.flat).toContain("Отдельной оценки только для S2 нет");
        expect(d.flat).toContain("объединённом отложенном тесте (пары S2 и S3 вместе");
      } else {
        expect(d.flat).toContain("No S2-only estimate exists");
        expect(d.flat).toContain("pooled held-out test (S2 and S3 pairs together; no S2-only estimate exists): AUPRC 0.812 ± 0.010");
        expect(d.flat).toContain("84,690 pairs, 76,932 of them S2 and 7,758 S3");
        expect(d.flat).not.toMatch(/Measured (performance|quality) for this regime/);
        // the stored response predates the backend fix and says "(as here): AUPRC"; the report labels it
        expect(d.flat).toContain("(as here): AUPRC 0.812 ± 0.010");
        expect(d.flat).toContain("Note added by the report: this figure comes from the pooled held-out test");
        // no figure presented as S2's own: "S2 AUPRC 0.81", "AUPRC on S2", "S2-only … 0.8"
        expect(d.flat).not.toMatch(/\bS2\b(-only)?\s*(test\s*)?(AUPRC|AUROC)\s*[:=]?\s*0\.\d|(AUPRC|AUROC)\s*(for|on|in)\s*(the\s*)?S2\b|S2-only[^.]{0,15}0\.\d/);
      }
    }
  });

  it("prints scores with the precision they have, and the exact values in the appendix", () => {
    const d = docs.wfEn, m = (wf.report.data as PairReport).model;
    expect(d.flat).toMatch(new RegExp(`CALIBRATED SCORE\\s*${m.calibrated_model_score!.toFixed(2).replace(".", "\\.")}\\b`));
    expect(d.flat).not.toContain(m.raw_model_score!.toFixed(6));
    expect(nospace(d.text)).toContain(`"calibrated_score":${m.calibrated_model_score}`);
    expect(nospace(d.text)).toContain(`"raw_score":${m.raw_model_score}`);
  });

  it("quick report: 1–2 pages, the outcome view, sources' words verbatim, no hypothesis as an outcome", () => {
    for (const k of ["qSynRu", "qSynEn", "qWfEn", "qMwRu"] as const) {
      const d = docs[k];
      const r = (d.prep.input as Extract<ExportInput, { kind: "pair" }>).report.data;
      const lang = d.prep.ctx.lang;
      const o = r.outcomes!;
      expect(d.numPages, k).toBeLessThanOrEqual(2);
      expect(d.prep.fileBase, k).toContain("QuickReport");
      expect(d.flat, k).toContain(o.interaction_status_label[lang]);
      expect(d.flat, k).toContain(o.individual_limit[lang]);
      const shown = o.outcomes.filter((x) => !x.research_only);
      for (const x of shown) {
        expect(d.flat, `${k} ${x.id}`).toContain(x.label[lang]);
        expect(nospace(d.text), `${k} excerpt`).toContain(nospace(x.supports[0].excerpt));
      }
      for (const x of o.outcomes.filter((y) => y.research_only)) expect(d.flat, k).not.toContain(x.label[lang]);
      if (!shown.length) expect(d.flat, k).toContain(o.no_outcome_text![lang]);
    }
    expect(docs.qMwRu.flat).toContain("не означает, что сочетание безопасно");
    expect(docs.qWfEn.flat).toContain("Severity not established from available evidence.");
  });

  it("reference set: its own source document, MedDRA term quoted, severity grades not reproduced", () => {
    for (const k of ["rWfEn", "rWfRu", "qrWfRu"] as const) {
      const d = docs[k];
      const r = (d.prep.input as Extract<ExportInput, { kind: "pair" }>).report.data;
      const en = d.prep.ctx.lang === "en";
      const ref = r.evidence.filter((e) => e.category === "reference_set_outcome");
      expect(ref.length).toBeGreaterThan(0);
      expect(d.flat).toContain("CRESCENDDI");
      expect(d.flat).toContain("Haemorrhage");
      if (k !== "qrWfRu") {
        expect(d.flat).toContain(en ? "CRESCENDDI (reference set; BNF, Micromedex, ANSM, 2018–2019)" : "CRESCENDDI (справочный набор; BNF, Micromedex, ANSM, 2018–2019)");
        expect(d.flat).toContain(en ? "graded by the compendia, but those grades are not reproduced here" : "справочники её оценивают, но эти оценки здесь не воспроизводятся");
        for (const e of ref) expect(nospace(d.text)).toContain(nospace(e.source_record_id!));
      }
      for (const grade of ["Severe", "Contraindicated", "Not recommended"]) expect(d.flat).not.toContain(grade);
    }
  });

  it("full report: outcome table, per-outcome provenance with every excerpt, chains with link provenance", () => {
    for (const k of ["oSynEn", "oSynRu"] as const) {
      const d = docs[k];
      const r = (d.prep.input as Extract<ExportInput, { kind: "pair" }>).report.data;
      const lang = d.prep.ctx.lang;
      expect(d.flat).toContain(lang === "en" ? "Clinical outcomes (as the sources state them)" : "Клинические последствия (по источникам)");
      expect(d.flat).toContain(lang === "en" ? "From mechanism to outcome" : "От механизма к последствию");
      expect(d.flat).toContain(lang === "en" ? "verified biological annotation" : "проверенная аннотация");
      for (const x of r.outcomes!.outcomes) {
        expect(nospace(d.text), x.id).toContain(nospace(x.id));
        for (const s of x.supports) expect(nospace(d.text), `${x.id} support`).toContain(nospace(s.excerpt));
      }
      expect(nospace(d.text)).toContain(`"interaction_status":"${r.outcomes!.interaction_status}"`);
    }
  });
});
