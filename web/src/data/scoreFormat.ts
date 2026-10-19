// How BIO-GINE scores are printed, on the site and in the PDF.
//
// The scores come from one checkpoint (seed 0) and carry no per-pair interval,
// so more digits than this would suggest a precision nobody measured:
//
//   * calibrated score — two decimals ("0.81"). Temperature scaling is monotone,
//     so it ranks pairs exactly as the raw score does; two decimals are enough to
//     read it.
//   * raw score — four decimals, and at the ends of the scale only a bound
//     ("> 0.9999", "< 0.0001"): the network's output bunches up near 0 and 1,
//     where further digits carry no meaning a reader could use.
//
// The exact values stay in the API response, in the PDF's machine-readable
// appendix and in the companion JSON.

const ok = (x: number | null | undefined): x is number => typeof x === "number" && Number.isFinite(x);

export function fmtCalibrated(x: number | null | undefined): string {
  return ok(x) ? x.toFixed(2) : "—";
}

export function fmtRaw(x: number | null | undefined): string {
  if (!ok(x)) return "—";
  if (x >= 0.99995) return "> 0.9999";
  if (x < 0.00005) return "< 0.0001";
  return x.toFixed(4);
}
