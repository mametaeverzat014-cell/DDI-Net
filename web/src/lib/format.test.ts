import { describe, it, expect } from "vitest";
import { auprc, meanSd, delta, pValue, count, fixed } from "./format";

describe("scientific number formatting is deterministic", () => {
  it("auprc renders exactly 3 decimals, locale-independent", () => {
    expect(auprc(0.8117107056824635)).toBe("0.812");
    expect(auprc(0.65)).toBe("0.650");
  });

  it("meanSd renders mean ± sd at matched precision", () => {
    expect(meanSd(0.811711, 0.009671)).toBe("0.812 ± 0.010");
  });

  it("meanSd never invents an interval when sd is missing", () => {
    expect(meanSd(0.82, null)).toBe("0.820 ± not estimated");
  });

  it("delta carries an explicit sign with a real minus glyph", () => {
    expect(delta(0.0332657)).toBe("+0.033");
    expect(delta(-0.0233463)).toBe("−0.023");
  });

  it("pValue renders small p in scientific form", () => {
    expect(pValue(0.0001980830148)).toBe("1.98e-4");
    expect(pValue(0.157146)).toBe("0.157");
  });

  it("count always uses comma thousands separators", () => {
    expect(count(191392)).toBe("191,392");
    expect(count(1705)).toBe("1,705");
    // Russian groups with a no-break space; the digits are identical.
    expect(count(191392, "ru")).toBe("191\u00a0392");
    expect(count(1705, "ru")).toBe("1\u00a0705");
    expect(count(1705, "ru").replace(/\u00a0/g, "")).toBe(count(1705).replace(/,/g, ""));
  });

  it("fixed respects requested precision", () => {
    expect(fixed(0.5430199, 3)).toBe("0.543");
  });
});
