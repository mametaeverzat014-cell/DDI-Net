// @vitest-environment node
// Geometry of rendered PDFs: nothing the report body draws may enter the
// running header or footer, no two lines may be drawn on top of each other,
// page numbers must be right, no page may be blank, and no page but the last
// may be left mostly empty.
//
// Regression for the page-6 overlap of a real 14-page Russian report: an
// evidence card that split across pages had its last rows squeezed into the
// bottom margin, over the footer (react-pdf gives the first part of a split
// View a fixed height and shrinks its children to it; components.tsx, PAGE
// BREAKS). Reproduced with the synthetic duplicated-label fixture and a sweep
// of excerpt lengths that moves the page break through every part of the card.
//
// Every PDF is rendered by the browser's code path (renderPdf) and read back
// with pdfjs-dist, independently of the renderer (testing/geometry.ts).
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { MultiReport } from "../data/v3";
import { headerRightText, t } from "./content";
import { renderPdf } from "./exportReport";
import { prepareExport } from "./format";
import { bandViolations, furnitureIntruders, overlappingText, pageGeometry, type Rect } from "./testing/geometry";
import { PAGE } from "./theme";
import type { ExportInput } from "./types";

const FONT_DIR = join(__dirname, "..", "..", "public", "fonts", "pdf");
const fx = (n: string) => JSON.parse(readFileSync(join(__dirname, "__fixtures__", n), "utf8"));
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x));

/** Page bands in PDF coordinates (origin bottom left). The running footer's
 *  rule sits at about y = 38 and its text below it; the header's rule at about
 *  y = 802 and its text above it. */
const BANDS = {
  contentBottom: PAGE.marginBottom,
  contentTop: PAGE.height - PAGE.marginTop,
  footerTop: 45,
  headerBottom: 790,
};

const show = (p: number, r: Rect) => `p${p} ${r.kind} y ${r.y0.toFixed(1)}–${r.y1.toFixed(1)} ${JSON.stringify(r.text ?? "")}`;

async function check(name: string, input: ExportInput, lang: "ru" | "en") {
  const prep = await prepareExport(input, { lang, now: new Date("2026-10-15T08:00:00Z"), timeZone: "Europe/Moscow", siteOrigin: null, siteCommit: null });
  const bytes = new Uint8Array(await (await renderPdf(prep, (f) => join(FONT_DIR, f))).arrayBuffer());
  if (process.env.DDINET_PDF_DUMP) writeFileSync(join(process.env.DDINET_PDF_DUMP, `layout-${name}-${lang}.pdf`), bytes);
  const pages = await pageGeometry(bytes);
  const problems: string[] = [];
  for (const g of pages.slice(1)) {             // page 1 is the cover, laid out on its own
    const furniture = {
      header: t("headerLeft", lang).toUpperCase() + headerRightText(input, lang),
      footer: t("footerLeft", lang) + prep.reportId + t("page", lang, { n: g.page, t: pages.length }),
    };
    for (const r of bandViolations(g, BANDS)) problems.push(`into the margin: ${show(g.page, r)}`);
    for (const r of furnitureIntruders(g, BANDS, furniture)) problems.push(`in header/footer: ${show(g.page, r)}`);
    for (const [a, b] of overlappingText(g)) problems.push(`overlap: ${show(g.page, a)} × ${show(g.page, b)}`);
    const pageNo = g.items.filter((r) => r.kind === "text" && r.y1 <= BANDS.footerTop).map((r) => r.text).join(" ");
    if (!pageNo.includes(t("page", lang, { n: g.page, t: pages.length }))) problems.push(`page ${g.page}: footer reads "${pageNo}"`);
    const body = g.items.filter((r) => r.kind === "text" && r.y0 >= BANDS.contentBottom - 1 && r.y1 <= BANDS.contentTop + 1).map((r) => r.text).join("");
    const lowest = Math.min(...g.items.filter((r) => r.y0 >= BANDS.contentBottom - 1 && r.y1 <= BANDS.contentTop + 1).map((r) => r.y0));
    // A page left mostly empty before the next one means a block was moved
    // instead of split (the glossary of a six-drug report once left 70% of a
    // page blank). An indivisible figure can still move whole, so the bar is 40%.
    const fill = (BANDS.contentTop - lowest) / (BANDS.contentTop - BANDS.contentBottom);
    if (g.page < pages.length && fill < 0.4) problems.push(`page ${g.page} is only ${Math.round(fill * 100)}% filled`);
    if (body.replace(/\s/g, "").length < 150) problems.push(`page ${g.page} is (nearly) blank`);
  }
  return { pages: pages.length, problems };
}

const dup = fx("pair_synthetic_duplicated_labels.json");
const pair = (report: unknown, graph?: unknown): ExportInput =>
  ({ kind: "pair", origin: graph ? "mechanisms" : "analyzer", report, ...(graph ? { graph } : {}) }) as ExportInput;

function longNames(m: { data: MultiReport }): ExportInput {
  const c = clone(m);
  c.data.drugs = c.data.drugs.map((d, i) => ({
    ...d,
    inn: `supercalifragilisticexpialidociousamycin-hydrochloride-monohydrate-${i}`,
    name_ru: `сверхдлинноеназваниепрепаратадляпроверкипереноса строки-${i}`,
  }));
  return { kind: "multi", report: c };
}

/** The synthetic duplicated-label report with its first excerpt lengthened, so
 *  the page break falls at a different place in the evidence cards each time. */
function lengthened(k: number): ExportInput {
  const c = clone(dup.report);
  c.data.evidence[0].statement += " filler words to move the break".repeat(k * 2);
  return pair(c);
}

describe("PDF geometry: no overlap with header or footer, no collapsed text, right page numbers", () => {
  const wf = fx("pair_warfarin_fluconazole.json");
  const sc = fx("pair_simvastatin_clarithromycin.json");
  const mw = fx("pair_metformin_warfarin.json");
  const cases: [string, ExportInput, "ru" | "en"][] = [
    ["warfarin-fluconazole", pair(wf.report), "ru"],
    ["warfarin-fluconazole", pair(wf.report), "en"],
    ["simvastatin-clarithromycin-graph", pair(sc.report, sc.graph), "en"],
    ["metformin-warfarin-no-label", pair(mw.report, mw.graph), "ru"],
    ["synthetic-duplicated-labels", pair(dup.report), "ru"],
    ["synthetic-duplicated-labels", pair(dup.report), "en"],
    ["synthetic-merged-labels", pair(fx("pair_synthetic_merged_labels.json").report), "ru"],
    ["long-names-pair", pair(fx("pair_long_names.json").report, fx("pair_long_names.json").graph), "ru"],
    ["multi-5", { kind: "multi", report: fx("multi_5.json") }, "en"],
    ["multi-6", { kind: "multi", report: fx("multi_6.json") }, "ru"],
    ["multi-6", { kind: "multi", report: fx("multi_6.json") }, "en"],
    ["multi-8", { kind: "multi", report: fx("multi_8.json") }, "ru"],
    ["multi-8", { kind: "multi", report: fx("multi_8.json") }, "en"],
    ["multi-8-long-names", longNames(fx("multi_8.json")), "ru"],
  ];
  for (const [name, input, lang] of cases) {
    it(`${name} (${lang})`, async () => {
      const { problems } = await check(name, input, lang);
      expect(problems).toEqual([]);
    }, 120_000);
  }

  // The real report broke at RU lengths 7–13 of this sweep (page 6 → 7).
  for (const [lang, ks] of [["ru", [3, 7, 9, 11, 13]], ["en", [4, 9, 13]]] as const) {
    it(`page breaks inside evidence cards (${lang}, excerpt lengths ${ks.join(", ")})`, async () => {
      for (const k of ks) {
        const { problems } = await check(`sweep-${k}`, lengthened(k), lang);
        expect(problems, `k = ${k}`).toEqual([]);
      }
    }, 300_000);
  }
});
