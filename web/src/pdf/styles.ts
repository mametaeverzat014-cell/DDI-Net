// Shared style values of the PDF report (no components here, so the
// component files stay fast-refresh friendly).
import { StyleSheet } from "@react-pdf/renderer";
import { C, CONTENT_WIDTH, FONT, PAGE, SIZE } from "./theme";

export const st = StyleSheet.create({
  page: {
    fontFamily: FONT.sans,
    fontSize: SIZE.body,
    color: C.ink,
    // No lineHeight here: react-pdf re-resolves a page's unitless line height on
    // every page it splits into, multiplying it by the font size each time, and
    // everything inheriting it (running header and footer, links) grows with it.
    // Each text style sets its own line height instead.
    paddingTop: PAGE.marginTop,
    paddingBottom: PAGE.marginBottom,
    paddingHorizontal: PAGE.marginX,
    backgroundColor: C.white,
  },
  p: { fontSize: SIZE.body, color: C.slate, lineHeight: 1.48 },
  small: { fontSize: SIZE.small, color: C.slate2, lineHeight: 1.42 },
  tiny: { fontSize: SIZE.tiny, color: C.muted, lineHeight: 1.38 },
  mono: { fontFamily: FONT.mono, fontSize: SIZE.tiny, color: C.slate2 },
  eyebrow: { fontFamily: FONT.mono, fontSize: SIZE.micro, textTransform: "uppercase", color: C.teal },
  h3: { fontFamily: FONT.sans, fontWeight: 600, fontSize: SIZE.h3, color: C.navy, marginBottom: 5 },
});

/** Hex colour blended toward white: a light tint for backgrounds. */
export function tint(hex: string, amount: number): string {
  const n = parseInt(hex.slice(1), 16);
  const mix = (c: number) => Math.round(c + (255 - c) * (1 - amount));
  const r = mix((n >> 16) & 255), g = mix((n >> 8) & 255), b = mix(n & 255);
  return `#${[r, g, b].map((x) => x.toString(16).padStart(2, "0")).join("")}`;
}

export interface Col { title: string; width: number; align?: "left" | "right" | "center" }

/** Column width in points, for wrapping mono text inside a table cell. */
export function colPoints(cols: Col[], index: number): number {
  const total = cols.reduce((s, c) => s + c.width, 0);
  return (cols[index].width / total) * CONTENT_WIDTH - 8;
}

// Characters IBM Plex Mono draws (Latin, Cyrillic, punctuation, arrows, minus).
// A line with anything else (e.g. Greek) is set in Plex Sans instead, so no
// glyph ever falls back to a font that is not embedded.
// eslint-disable-next-line no-control-regex
const MONO_SAFE = /^[\u0000-\u024F\u0400-\u04FF\u2010-\u2027\u2030-\u205E\u2190-\u21FF\u2212]*$/;
export const monoFont = (s: string) => (MONO_SAFE.test(s) ? FONT.mono : FONT.sans);
