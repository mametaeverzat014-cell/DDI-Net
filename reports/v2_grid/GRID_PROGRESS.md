# V2 validation grid — progress

**Updated:** 2026-08-30T00:08:29.329970+00:00

`[........................................]` **1 / 96**

| | |
|---|---|
| Completed | 1 |
| Failed | 1 |
| Currently running | 6531bc4096b173aa bio64 db0.1 dp0.1 lr0.001 bs256 seed2 |
| Elapsed | 0.00 h |
| Estimated remaining | 0.28 h |
| Mean per run | 0.003 h |

**Test set:** sealed. Every run is `validation_only`; the test buckets are
removed before negatives are sampled, so no test label exists in any run's
process. No test metric has been computed.

**No scientific interpretation while the grid is incomplete.** Intermediate
validation metrics are recorded but must not be used to modify the search
(docs/V2_PREREGISTRATION.md section 10.4).

## Failed runs

- `eb90dbceae741375`: exit 1, row absent
