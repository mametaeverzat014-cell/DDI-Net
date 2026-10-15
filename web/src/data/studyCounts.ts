// Test-set sizes the plain-language notes cite, read from the frozen study data
// (frozen.json is generated from the frozen tag; v3facts.json from the v3
// reports). The S2 count is the pooled count minus the S3 count — the pooled
// test is exactly the S2 and S3 pairs together.
import { frozen } from "./frozen";
import { v3facts } from "./v3facts";
import type { StudyCounts } from "./plainLanguage";

export function studyCounts(): StudyCounts {
  const pooled = frozen.splits.pooled_pairs, s3 = frozen.splits.s3_pairs;
  return {
    pooled, s3, s2: pooled - s3,
    seeds: Number(frozen.config.n_final_seeds),
    bothAnnotated: v3facts.coverage_reliability.views.pooled.both_annotated.n_pairs,
  };
}
