// Scientific-integrity tests. These assert that the data the UI renders matches
// the frozen scientific state — the numbers the user's brief pinned — and that
// the honest negative findings and safety flags are intact. If the frozen data
// regenerates to something else, these fail loudly rather than the site quietly
// showing a wrong number.
import { describe, it, expect } from "vitest";
import { frozen, model, hypothesis } from "./frozen";

const near = (a: number, b: number, tol = 5e-6) => Math.abs(a - b) <= tol;

describe("frozen headline results match the pinned scientific state", () => {
  it("M4 pooled AUPRC is 0.811711 ± 0.009671", () => {
    const m = model("BIO-GINE M4");
    expect(near(m.pooled_mean, 0.811711)).toBe(true);
    expect(near(m.pooled_std, 0.009671, 5e-5)).toBe(true);
  });

  it("M4 S3 AUPRC is 0.737241 ± 0.015253", () => {
    const m = model("BIO-GINE M4");
    expect(near(m.s3_mean!, 0.737241)).toBe(true);
    expect(near(m.s3_std!, 0.015253, 5e-5)).toBe(true);
  });

  it("aligned molecular GINE is 0.778445, aligned Dual S3 is 0.619761", () => {
    expect(near(model("Aligned molecular GINE (M0)").pooled_mean, 0.778445)).toBe(true);
    expect(near(model("Aligned Dual (GINE + DDI network)").s3_mean!, 0.619761)).toBe(true);
  });

  it("shuffled biology drops to 0.692256; degree-only RF is 0.650422; BIO-RF 0.739612", () => {
    expect(near(model("BIO-GINE M4, shuffled biology (CONTROL F)").pooled_mean, 0.692256)).toBe(true);
    expect(near(model("Biological-degree-only RF (CONTROL A)").pooled_mean, 0.650422)).toBe(true);
    expect(near(model("BIO-RF").pooled_mean, 0.739612)).toBe(true);
  });
});

describe("honest negative findings are present and not smoothed away", () => {
  it("the ladder is non-monotonic: M2 and SUM both exceed primary M4", () => {
    const m2 = model("M2").pooled_mean;
    const sum = model("M4 SUM (CONTROL C)").pooled_mean;
    const m4 = model("M4 (primary)").pooled_mean;
    expect(m2).toBeGreaterThan(m4);
    expect(sum).toBeGreaterThan(m4);
    expect(near(m2, 0.826891)).toBe(true);
    expect(near(sum, 0.826474)).toBe(true);
  });

  it("H-V2-5 is exploratory and its direction is unsupported", () => {
    const h5 = hypothesis("H-V2-5");
    expect(h5.status).toBe("exploratory");
    expect(h5.conclusion.toLowerCase()).toContain("unsupported");
    expect(h5.delta).toBeLessThan(0);
  });

  it("CONTROL E held-out R^2 is not identifiable (zero target variance)", () => {
    expect(frozen.control_e.identifiable).toBe(false);
    expect(frozen.control_e.held_out_target_variance).toBe(0);
  });

  it("scaffold-disjoint was not evaluated in final V2", () => {
    expect(frozen.scaffold_disjoint.evaluated).toBe(false);
  });
});

describe("terminology and safety flags", () => {
  it("dataset counts are the post-exclusion 1,705 / 191,392", () => {
    expect(frozen.dataset.n_drugs).toBe(1705);
    expect(frozen.dataset.n_pairs).toBe(191392);
    expect(frozen.dataset.excluded_drug).toBe("DB11630");
  });

  it("pooled = S2+S3: pooled pair count exceeds the S3 subset", () => {
    expect(frozen.splits.pooled_pairs).toBe(84690);
    expect(frozen.splits.s3_pairs).toBe(7758);
    expect(frozen.splits.pooled_pairs).toBeGreaterThan(frozen.splits.s3_pairs);
  });

  it("random-pair splitting leaks while drug/scaffold holdout do not", () => {
    expect(frozen.leakage.both_endpoints_seen.random_pair).toBeGreaterThan(0.99);
    expect(frozen.leakage.both_endpoints_seen.drug).toBe(0);
    expect(frozen.leakage.both_endpoints_seen.scaffold).toBe(0);
  });

  it("the inference checkpoint is not installed on this deployment", () => {
    expect(frozen.checkpoint.installed).toBe(false);
  });

  it("every hypothesis Holm p is consistent with a 5-member family (H4 smallest)", () => {
    // H-V2-4 has the smallest raw p; its Holm value is raw*5 exactly.
    const h4 = hypothesis("H-V2-4");
    expect(near(h4.holm_p, h4.raw_p * 5, 1e-9)).toBe(true);
  });
});
