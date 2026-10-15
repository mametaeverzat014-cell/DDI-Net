// Renders the PDF report for the recorded API responses in src/pdf/__fixtures__
// (real responses of the DDI-Net 3.0 API, captured from a local server, except
// the files marked SYNTHETIC). Used to produce the sample reports and to inspect
// the layout.
//
//   npx vite-node tools/render_sample_reports.tsx -- <out-dir> [ru|en|both]
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { prepareExport } from "../src/pdf/format";
import { renderPdf } from "../src/pdf/exportReport";
import type { ExportContext, ExportInput } from "../src/pdf/types";

const root = resolve(__dirname, "..");
const fx = (name: string) => JSON.parse(readFileSync(join(root, "src/pdf/__fixtures__", name), "utf8"));
const font = (f: string) => join(root, "public/fonts/pdf", f);

const args = process.argv.slice(2).filter((a) => a !== "--");
const out = resolve(args[0] ?? "samples");
const langs = (args[1] ?? "both") === "both" ? (["en", "ru"] as const) : [args[1] as "en" | "ru"];
mkdirSync(out, { recursive: true });

const cases: [string, ExportInput][] = [
  ["pair-warfarin-fluconazole-analyzer", { kind: "pair", origin: "analyzer", report: fx("pair_warfarin_fluconazole.json").report }],
  ["pair-simvastatin-clarithromycin-mechanisms", { kind: "pair", origin: "mechanisms", report: fx("pair_simvastatin_clarithromycin.json").report, graph: fx("pair_simvastatin_clarithromycin.json").graph }],
  ["pair-metformin-warfarin-mechanisms", { kind: "pair", origin: "mechanisms", report: fx("pair_metformin_warfarin.json").report, graph: fx("pair_metformin_warfarin.json").graph }],
  ["SYNTHETIC-labels-warfarin-fluconazole", { kind: "pair", origin: "analyzer", report: fx("pair_synthetic_duplicated_labels.json").report }],
  ["pair-long-names-analyzer", { kind: "pair", origin: "analyzer", report: fx("pair_long_names.json").report }],
  ["multi-5", { kind: "multi", report: fx("multi_5.json") }],
  ["multi-6", { kind: "multi", report: fx("multi_6.json") }],
  ["multi-8", { kind: "multi", report: fx("multi_8.json") }],
];

for (const lang of langs) {
  for (const [name, input] of cases) {
    const ctx: ExportContext = { lang, now: new Date(), timeZone: "Europe/Moscow", siteOrigin: null, siteCommit: null };
    const prep = await prepareExport(input, ctx);
    const blob = await renderPdf(prep, font);
    const file = join(out, `${name}-${lang}.pdf`);
    writeFileSync(file, Buffer.from(await blob.arrayBuffer()));
    console.log(file, prep.fileBase, prep.reportId, blob.size);
  }
}
