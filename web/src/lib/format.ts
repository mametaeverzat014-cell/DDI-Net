// Deterministic scientific formatting. One place, so a metric never renders
// with a browser-locale surprise or a floating-point tail.

/** Fixed-decimal, locale-independent. auprc(0.8117107) -> "0.812" at 3 dp. */
export function fixed(x: number, dp = 3): string {
  return x.toFixed(dp);
}

/** AUPRC-style value, 3 decimals. */
export function auprc(x: number): string {
  return x.toFixed(3);
}

/** mean ± sd, both at the same precision. Returns the ± glyph. */
export function meanSd(mean: number, sd: number | null, dp = 3): string {
  if (sd === null || Number.isNaN(sd)) return `${mean.toFixed(dp)} ± not estimated`;
  return `${mean.toFixed(dp)} ± ${sd.toFixed(dp)}`;
}

/** Signed delta, e.g. "+0.033". */
export function delta(x: number, dp = 3): string {
  return (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(dp);
}

/** p-value in a compact scientific form a judge can read: "1.98e-4". */
export function pValue(p: number): string {
  if (p >= 0.001) return p.toFixed(3);
  const exp = Math.floor(Math.log10(p));
  const mant = p / 10 ** exp;
  return `${mant.toFixed(2)}e${exp}`;
}

/** Percent from a 0–100 number already in percent units. */
export function pct(x: number, dp = 1): string {
  return `${x.toFixed(dp)}%`;
}

/** Thousands separators. English groups with a comma, Russian with a no-break
 *  space, which is the Russian typographic convention. Only the GROUPING is
 *  language-dependent — decimal values (AUPRC, p-values, deltas) keep the dot
 *  everywhere, because that is how they appear in the artifacts and the
 *  manuscript, and a decimal comma would be a different-looking number. */
export function count(n: number, lang: "ru" | "en" = "en"): string {
  return lang === "ru"
    ? n.toLocaleString("en-US").replace(/,/g, "\u00a0")
    : n.toLocaleString("en-US");
}
