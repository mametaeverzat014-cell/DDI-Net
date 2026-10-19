// Visual system of the PDF report: A4 portrait, navy / slate / teal on white.
//
// Teal is a structural accent only (rules, eyebrows, the cover band). Evidence
// kinds keep the site's rule: colour names a KIND of statement, never a level of
// danger, and nothing is green — a reassuring colour on "nothing found" is the
// misreading the whole evidence layer exists to prevent (theme.test.ts checks
// the hues).

export const PAGE = {
  width: 595.28,
  height: 841.89,
  marginX: 52,
  marginTop: 66,
  marginBottom: 60,
};
export const CONTENT_WIDTH = PAGE.width - 2 * PAGE.marginX;

export const C = {
  navy: "#0B1E3F",
  navy2: "#16305A",
  navy3: "#24497F",
  ink: "#1B2534",
  slate: "#334155",
  slate2: "#4A5A70",
  muted: "#66768C",
  faint: "#97A3B5",
  rule: "#CDD5E0",
  hair: "#E3E8EF",
  tint: "#F5F7FA",
  tint2: "#EDF1F6",
  white: "#FFFFFF",
  teal: "#0F766E",
  tealLine: "#5FA8A1",
};

/** Evidence kinds — print versions of the site's --ev-* tokens. */
export const EV = {
  label: "#B0482E",       // official label text names the partner drug
  documented: "#5A47AE",  // database interaction record
  annotation: "#7062B8",  // documented fact about one drug
  hypothesis: "#0B6390",  // mechanism hypothesis
  model: "#5B6B82",       // BIO-GINE research signal
  missing: "#A5650E",     // missing / unavailable
  none: "#8B97A8",        // nothing documented found
};

/** Drug–protein relation colours in the mechanism graph. */
export const REL = {
  enzyme: "#0F766E",
  transporter: "#2F5DA8",
  carrier: "#7A5BC2",
  target: "#8792A2",
} as const;

export const DRUG_COLOR = { a: "#24497F", b: "#0F766E" };

export const FONT = {
  sans: "PlexSans",
  serif: "PlexSerif",
  mono: "PlexMono",
};

export const SIZE = {
  body: 9.2,
  small: 8.2,
  tiny: 7.2,
  micro: 6.6,
  h1: 27,
  h2: 15.5,
  h3: 10.6,
  lead: 10.4,
};
