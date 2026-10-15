// Entry point of the export, loaded on demand (dynamic import from
// components/v3/ExportReport.tsx) so the PDF library never enters the main
// bundle. Runs entirely in the browser: no server call, no third-party service.
import { pdf } from "@react-pdf/renderer";
import type { Lang } from "../i18n";
import { companionJson } from "./content";
import { freshPdfFonts, registerPdfFonts } from "./fonts";
import { browserTimeZone, payloadOf, prepareExport } from "./format";
import { ReportDocument } from "./ReportDocument";
import type { ExportContext, ExportInput, PreparedExport } from "./types";

declare const __DDINET_COMMIT__: string;

export interface ExportFile { blob: Blob; filename: string; reportId: string }

export function browserContext(lang: Lang, now = new Date()): ExportContext {
  const commit = typeof __DDINET_COMMIT__ === "string" && __DDINET_COMMIT__ ? __DDINET_COMMIT__ : null;
  return {
    lang,
    now,
    timeZone: browserTimeZone(),
    siteOrigin: typeof window !== "undefined" ? window.location.origin : null,
    siteCommit: commit,
  };
}

/** Fonts are served next to the site (public/fonts/pdf); the PDF embeds them. */
function fontUrl(file: string): string {
  const base = new URL(`${import.meta.env.BASE_URL}fonts/pdf/`, window.location.href);
  return new URL(file, base).href;
}

/** Render a prepared export to PDF bytes. Shared by the browser and the tests. */
export async function renderPdf(prep: PreparedExport, resolveFont: (file: string) => string): Promise<Blob> {
  registerPdfFonts(resolveFont);
  // Fresh font objects for every document (see fonts.ts); after the first
  // export the files themselves come from the browser cache.
  freshPdfFonts();
  return pdf(<ReportDocument prep={prep} />).toBlob();
}

export async function exportPdf(input: ExportInput, lang: Lang): Promise<ExportFile> {
  const prep = await prepareExport(input, browserContext(lang));
  const blob = await renderPdf(prep, fontUrl);
  return { blob, filename: `${prep.fileBase}.pdf`, reportId: prep.reportId };
}

export async function exportJson(input: ExportInput, lang: Lang): Promise<ExportFile> {
  const prep = await prepareExport(input, browserContext(lang));
  const body = JSON.stringify(companionJson(prep, payloadOf(input)), null, 2);
  return { blob: new Blob([body], { type: "application/json" }), filename: `${prep.fileBase}.json`, reportId: prep.reportId };
}

/** Save a file through a temporary object URL. */
export function download(file: ExportFile): void {
  const url = URL.createObjectURL(file.blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = file.filename;
  a.rel = "noopener";
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
