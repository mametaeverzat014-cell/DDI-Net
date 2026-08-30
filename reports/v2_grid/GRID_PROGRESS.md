# V2 validation grid — progress

**Updated:** 2026-08-30T00:59:04.282289+00:00

`[........................................]` **2 / 96**

| | |
|---|---|
| Completed | 2 |
| Failed | 1 |
| Currently running | b42cc4930da045d0 bio64 db0.1 dp0.1 lr0.0003 bs256 seed0 |
| Elapsed | 0.85 h |
| Estimated remaining | 39.76 h |
| Mean per run | 0.423 h |

**Test set:** sealed. Every run is `validation_only`; the test buckets are
removed before negatives are sampled, so no test label exists in any run's
process. No test metric has been computed.

**No scientific interpretation while the grid is incomplete.** Intermediate
validation metrics are recorded but must not be used to modify the search
(docs/V2_PREREGISTRATION.md section 10.4).

## Failed runs

- `eb90dbceae741375`: exit 1, row absent
