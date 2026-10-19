// Font registration for the PDF renderer.
//
// IBM Plex Sans / Serif / Mono, SIL Open Font License 1.1 (licence next to the
// files in public/fonts/pdf/). The WOFF files are the unmodified files of the
// official @ibm/plex-* packages; the renderer embeds only the glyphs a report
// uses, so the PDF carries its own fonts and reads the same offline on any
// machine. All three families cover Latin and Cyrillic; Mono has no Greek, so
// Greek letters are never set in Mono.
import { Font } from "@react-pdf/renderer";
import { FONT } from "./theme";

export const FONT_FILES = {
  sans: [
    ["IBMPlexSans-Regular.woff", 400, "normal"],
    ["IBMPlexSans-Italic.woff", 400, "italic"],
    ["IBMPlexSans-Medium.woff", 500, "normal"],
    ["IBMPlexSans-SemiBold.woff", 600, "normal"],
    ["IBMPlexSans-Bold.woff", 700, "normal"],
  ],
  serif: [
    ["IBMPlexSerif-Regular.woff", 400, "normal"],
    ["IBMPlexSerif-Italic.woff", 400, "italic"],
    ["IBMPlexSerif-SemiBold.woff", 600, "normal"],
  ],
  mono: [
    ["IBMPlexMono-Regular.woff", 400, "normal"],
    ["IBMPlexMono-Medium.woff", 500, "normal"],
  ],
} as const;

let registered: string | null = null;

export function splitLongWord(word: string): string[] {
  if (word.length <= 24) return [word];
  const parts = word.split(/(?<=[./_\-=,:;)(])/).filter(Boolean);
  return parts.flatMap((p) => (p.length <= 16 ? [p] : p.match(/.{1,12}/gu) ?? [p]));
}

/** Register the families once. `resolve` maps a file name to a URL (browser) or
 *  a file path (Node tests). */
export function registerPdfFonts(resolve: (file: string) => string): void {
  const key = resolve("");
  if (registered === key) return;
  for (const [family, files] of [[FONT.sans, FONT_FILES.sans], [FONT.serif, FONT_FILES.serif], [FONT.mono, FONT_FILES.mono]] as const) {
    Font.register({
      family,
      fonts: files.map(([file, fontWeight, fontStyle]) => ({ src: resolve(file), fontWeight, fontStyle })),
    });
  }
  // No dictionary hyphenation: the default patterns are English and would
  // break Russian words wrongly. Only an unbroken run longer than a line can
  // be (a long name or identifier) is given break points — after punctuation
  // where it has some, else every 12 characters — so it wraps inside its box
  // instead of running past the margin.
  Font.registerHyphenationCallback(splitLongWord);
  registered = key;
}

/** Drop the loaded font objects of our three families so the next document
 *  loads its own. Reusing them across documents lets glyph state from one
 *  report leak into the next one's text map (a glyph then extracts as the wrong
 *  character). Font.reset() cannot be used: in @react-pdf/renderer 4.9.0 it also
 *  clears the built-in fonts and leaves their load promise cached, so they never
 *  reload. Depends on that version's FontSource fields (pinned in package.json;
 *  render.test.ts renders many reports in one process and checks every glyph).
 */
export function freshPdfFonts(): void {
  const store = Font as unknown as { getRegisteredFonts(): Record<string, { sources: { data: unknown; loadResultPromise: unknown }[] } | undefined> };
  for (const family of [FONT.sans, FONT.serif, FONT.mono]) {
    for (const src of store.getRegisteredFonts()[family]?.sources ?? []) {
      src.data = null;
      src.loadResultPromise = null;
    }
  }
}
