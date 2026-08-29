# V2 Preregistration Amendment 1: training budget

**Status:** AMENDMENT — the original `docs/V2_PREREGISTRATION.md` is unchanged
**Registered:** 2026-08-29
**Amends:** section 10.2, `max_epochs` and `patience` only
**Scope:** the training-budget ceiling. Nothing else.
**Written:** before the adequacy pilot was run. Section 4 (the adequacy rule)
was committed before any convergence curve existed.

---

## 1. What is being amended, and what is not

**Amended:** the training-budget ceiling — `max_epochs`, `patience`, and the
unit in which both are expressed.

**Not amended, and not touchable by this study:**

- the 32-configuration search space (`bio_dim`, `dropout_bio`, `dropout_pair`,
  `lr`, `batch_size`) — frozen;
- the architecture — frozen;
- the evidence ladder M0–M4 — frozen;
- the splits, the negative sampling, the seeds — frozen;
- every hypothesis, threshold, effect-size requirement and falsification
  criterion — frozen;
- the test set — sealed, and untouched by everything below.

The original preregistration is not rewritten. This document sits beside it.

## 2. The problem, discovered before any grid run

**Original preregistration:** `max_epochs: 400`, `patience: 30`
(`configs/v2_preregistered.yaml`, `hparam_search.fixed`).

**What was discovered:** "epoch" does not mean the same thing in Phase A-2 and
in V2.

Phase A-2 trained **full-batch**: one optimiser step per epoch, justified in its
protocol section 9 because cost was dominated by encoding all molecules rather
than by the pair count. Its 800-epoch cap was **800 optimiser steps**.

The V2 preregistration specifies `batch_size: [256, 512]`. With 187,260 training
pairs that is **732 or 366 optimiser steps per epoch**. The 400-epoch cap is
therefore between **146,400 and 292,800 optimiser steps** — two to three orders
of magnitude more optimisation than any Phase A-2 model received.

The `max_epochs: 400` figure was carried over from the Phase A-2 sense of the
word. Against a minibatch loop it is not a comparable budget.

**Measured runtime**, drug-disjoint split seed 0, degree-matched negatives,
4 cores, 2 torch threads, after an exact optimisation that cut epoch cost from
194 s to 102 s (`tests/test_bio_gine.py::test_unique_element_path_equals_the_naive_path`
pins the exactness):

| | |
|---|---:|
| Epoch at `batch_size=512` (366 steps) | **102 s** |
| Epoch at `batch_size=256` (732 steps, estimated) | ~117 s |
| 400 epochs, one run | **12.2 h** |
| 96 runs, no early stopping | **48.7 days** |
| 96 runs, early stop ~60 epochs | 7.3 days |

Phase A-2's whole grid, for scale: 70 runs in 18 h 14 m — 0.26 h per run.

**No V2 test metric has been observed.** This amendment is made for
computational feasibility only, before hyperparameter selection and before any
test evaluation.

## 3. The adequacy pilot

One configuration, two seeds, validation only. No test DataLoader is
constructed, no test prediction is written, no test metric is computed.

| | |
|---|---|
| Model | BIO-GINE, M4, true biology, MEAN aggregation |
| Split | drug-disjoint, split seed 0 |
| Negatives | degree-matched (validation negatives pinned at `eval_seed=0`) |
| Seeds | 0 and 1 |
| Cap | 40 epochs, validation every epoch |
| Early stopping | unchanged: `patience=30` |

### Why this configuration

The preregistered grid is a 2-level full factorial. **It has no centre point** —
every axis takes one of two values — so "a central configuration" does not
exist and something else has to be chosen on stated grounds.

The purpose here is to set a **hard maximum**. A cap chosen from a
fast-converging configuration would silently truncate the slow ones, and
truncation is invisible in the metric: it looks like a worse model, not like a
budget problem. So the pilot runs the **slowest-converging corner** on the axes
that govern convergence *speed*:

| Axis | Value | Why |
|---|---|---|
| `lr` | **3e-4** | the smaller of the two — slower convergence |
| `batch_size` | **512** | 366 steps/epoch, the *fewer* updates per epoch |
| `dropout_bio` | **0.3** | the larger — more regularisation, slower fit |
| `dropout_pair` | **0.2** | the larger, same reason |
| `bio_dim` | 64 | see below |

`bio_dim` is set to the smaller value rather than the slower-looking larger one
because it governs **capacity**, not step efficiency: a wider embedding does not
need more steps to reach its own plateau, it reaches a different plateau. Fixing
it at 64 also keeps the diagnostic cheap. The risk this leaves open — that
`bio_dim=128` needs a larger cap — is **detectable in the grid itself**: every
run records `stopped_by`, and a cap that binds shows up as a high fraction of
`epoch_limit` stops. That fraction will be reported.

This configuration was selected from these properties alone, before any curve
was inspected. It is deliberately **not** the configuration used in the earlier
smoke run (which was `lr=1e-3`, `dropout 0.1/0.1` — the *fastest* corner).

### What the earlier smoke run may not be used for

The 4-epoch smoke run produced validation AUPRC 0.7115 → 0.7376 → 0.7538 →
0.7609. It proves the pipeline trains. It is four points on a still-rising
curve and **must not** be used to choose a budget. It is not reused here.

## 4. Adequacy rule — FIXED BEFORE THE CURVES WERE SEEN

A candidate budget is **adequate** if all three hold:

- **A.** The best validation checkpoint occurs before the final 20% of the
  allowed budget, for **both** seeds. (At a 40-epoch cap: best epoch ≤ 32.)
- **B.** Validation AUPRC improvement over the final 5 epochs is **< 0.005
  absolute**, for **both** seeds.
- **C.** Neither seed shows a clear sustained upward trend at the budget
  boundary. Operationalised, so it is not a matter of opinion: the ordinary
  least-squares slope of validation AUPRC over the final 5 epochs is
  **< 0.001 per epoch** for both seeds.

If the criteria fail at 40 epochs, the budget is **not** invented from the
curve. The same runs are **extended by resume** to 60 epochs, and if still
inadequate to 80. **80 is a hard stop**: beyond it the result is reported and
the decision returns to the principal investigator.

`patience` is not tuned from the observed curves. It stays at the preregistered
30 for the duration of this study.

## 5. Budget unit: epochs or optimiser steps

`batch_size` is itself a preregistered hyperparameter, and 256 and 512 imply
732 and 366 steps per epoch. **An epoch-denominated cap therefore hands
`batch_size=256` exactly twice the optimisation of `batch_size=512`**, which
confounds batch size with training budget: a win for 256 could not be
attributed to the batch size rather than to the extra updates.

A step-denominated cap removes that confound by construction. The trade-off is
that a step cap gives the two batch sizes different numbers of *passes over the
data*, which is a different fairness notion.

The pilot records both `epoch` and `cumulative_optimizer_steps` for every
validation check so the choice can be made against measured numbers. The
recommendation is in section 7, written after the pilot; it is **not** to be
made on which unit yields a better validation AUPRC.

## 6. Early stopping semantics

`patience` counts **validation checks**, not raw optimiser steps. In this study
validation runs once per epoch, so a check is an epoch and the two readings
coincide. If the grid later validates on a step interval rather than per epoch,
patience must stay denominated in checks — otherwise changing the validation
interval would silently change the stopping rule.

This is a semantic clarification of the existing mechanism, not a change to it,
and `patience` is not tuned from performance anywhere in this study.

## 7. Recommendation

**Budget unit: OPTIMISER STEPS, not epochs.**

**Hard cap: 21,960 optimiser steps** (the validated 60-epoch budget at
`batch_size=512`).

**Validation interval: every 366 optimiser steps** (one `batch_size=512` epoch),
so both batch sizes receive the same 60 validation checks inside the cap.

**Early stopping: patience 30 validation checks** — unchanged from the
preregistration, and not tuned here.

### Why steps rather than epochs

An epoch-denominated cap of 60 gives `batch_size=256` **21,960 more optimiser
updates than `batch_size=512`** — exactly twice as many, since 732 steps per
epoch against 366. A win for `batch_size=256` under that budget could not be
attributed to the batch size rather than to the extra optimisation, and batch
size is one of the five searched hyperparameters. The confound is structural,
not incidental.

A step cap removes it by construction: both batch sizes take 21,960 updates,
which is 60 passes over the data at 512 and 30 at 256. The cost of that choice
is that the two batch sizes see the data a different number of times; measured
against the alternative — a budget that is not comparable across the very axis
being searched — it is the lesser problem.

It is also cheaper: 6.4 days for the 96-run grid instead of 9.2.

The recommendation is **not** based on which unit yields a better validation
AUPRC. It is based on removing a confound between a searched hyperparameter and
the training budget.

### Why 21,960 and not less

21,960 is the budget that **passed the rule in section 4**, which was fixed
before any curve existed. Smaller budgets were not tested against the rule and
are not being selected on their metrics. For the record, and as description
only, what smaller budgets would have bought in the pilot:

| Steps | Epochs @512 | Epochs @256 | val AUPRC | % of pilot best | 96-run days |
|---:|---:|---:|---:|---:|---:|
| 7,686 | 21 | 10 | 0.7830 | 99.3% | 2.2 |
| 10,980 | 30 | 15 | 0.7835 | 99.4% | 3.2 |
| 14,640 | 40 | 20 | 0.7882 | 100.0% | 4.3 |
| **21,960** | **60** | **30** | **0.7882** | **100.0%** | **6.4** |

14,640 steps already reaches the pilot's best, because both seeds peaked before
it (11,346 and 13,176). It nevertheless **fails criterion A** — seed 1's peak
sits at 90% of that budget — and criterion A is what the rule says to apply.
Choosing 14,640 because the table shows it is sufficient would be selecting a
budget from the curve, which section 4 forbids in those words.

### Early stopping is inert at this cap, and that is reported, not fixed

With the best checkpoint at check 31 and 36 and patience at 30, stopping would
trigger at check 61 and 66 — beyond the 60-check cap. **Early stopping never
fires**, so every grid run costs the full budget and expected time equals
worst-case time.

Patience is **not** retuned here: section 4 forbids tuning it from the observed
curves, and this is exactly the situation that rule exists for. The consequence
is stated so the cost estimate is honest rather than optimistic.

## 8. Results

Raw curves: `reports/v2_budget_adequacy/budget_adequacy_curves.csv` (both caps,
200 rows). Summaries: `budget_adequacy_summary.json` (cap 60) and
`budget_adequacy_summary_cap40.json`. Plots beside them.

Configuration: BIO-GINE M4, true biology, MEAN aggregation, drug-disjoint split
seed 0, degree-matched negatives, `bio_dim=64`, `dropout_bio=0.3`,
`dropout_pair=0.2`, `lr=3e-4`, `batch_size=512` — 366 optimiser steps per epoch.
Validation only throughout.

### First attempt: cap 40 — NOT ADEQUATE

| | seed 0 | seed 1 |
|---|---:|---:|
| Best epoch | 27 (step 9,882) | **36** (step 13,176) |
| Best val AUPRC | 0.7788 | 0.7833 |
| Improvement, last 5 epochs | −0.0000 | +0.0016 |
| Trailing slope, last 5 | +0.00023 | −0.00034 |
| 99% of best at epoch | 12 | 13 |
| **A** (best before final 20%, ≤32) | PASS | **FAIL** |
| **B** (last-5 improvement < 0.005) | PASS | PASS |
| **C** (last-5 slope < 0.001) | PASS | PASS |

The rule fired: extend to 60. It was followed.

### Second attempt: cap 60 — ADEQUATE

| | seed 0 | seed 1 |
|---|---:|---:|
| Best epoch | 31 (step 11,346) | 36 (step 13,176) |
| Best val AUPRC | 0.7892 | 0.7873 |
| Final val AUPRC | 0.7852 | 0.7852 |
| val AUROC / Brier / ECE at best | 0.7964 / 0.2184 / 0.1746 | 0.7914 / 0.2239 / 0.1861 |
| Improvement, last 3 / 5 / 10 | +0.0001 / +0.0003 / +0.0001 | −0.0006 / +0.0006 / +0.0032 |
| Trailing slope, last 5 | +0.00000 | −0.00026 |
| 95% / 99% of best at epoch | 5 / 21 | 3 / 21 |
| Mean epoch runtime | 111.2 s | 109.2 s |
| **A** (best before final 20%, ≤48) | **PASS** | **PASS** |
| **B** | **PASS** | **PASS** |
| **C** | **PASS** | **PASS** |

**All three criteria pass on both seeds. 60 epochs / 21,960 steps is adequate.**

### A recorded reservation about criterion A

Criterion A passed at cap 60, so the rule is satisfied and nothing here changes
the decision. It is recorded because it affects how much weight A deserves in
future studies.

**A measures where the argmax of a noisy plateau fell, not whether training
converged.** Measured on the cap-40 curves: the plateau (from the epoch reaching
99% of best) has a standard deviation of 0.0034 and a width of 0.014 on both
seeds. Within one plateau standard deviation of the "best" epoch there are
**12 epochs on seed 0 (21–40) and 10 on seed 1 (23–40)**. Which of those is the
argmax is noise.

The same configuration and seed bears this out directly: seed 0's argmax was
epoch 27 at cap 40 and epoch 31 at cap 60. The peak moved because it is noise,
not because the model converged later.

A second effect pushes the same way: `T_max` of the cosine schedule equals the
cap, so the learning rate anneals to zero exactly at the boundary and late
epochs are quieter — mildly favouring a late argmax. Phase A-2's runner
docstring already records this property.

Criteria B and C, which measure whether the curve is still *moving*, passed at
both caps and by margins of 3x to 15x. They are the criteria that answered the
question. A future adequacy study should prefer a stability-of-plateau
criterion — for instance "the epoch reaching 99% of best lies in the first half
of the budget", which both seeds satisfy at 21 of 60 — over the position of an
argmax.

This is written after the fact and changes no decision taken here.

### Note on "extend the SAME runs using resume"

Section 4 says to extend by resume. That is not literally executable:
`max_epochs` sets `T_max` of the cosine schedule, so a 60-epoch run follows a
different learning-rate trajectory **from its first epoch** and is a different
run — the runner's own identity hash says so, and its sibling-checkpoint
notice reported exactly that (`2339302d73825656 is the same run except
max_epochs: 40 -> 60`).

Resuming the 40-epoch checkpoint under a `T_max=60` schedule would produce a
hybrid trajectory matching no configuration in the grid. Fresh 60-epoch runs
were executed instead. This follows the intent of section 4 (obtain curves at a
larger cap) rather than its letter, and the deviation is recorded here.

### Grid cost under the amended budget

Measured: 0.3010 s per optimiser step at `batch_size=512` (110.2 s per epoch,
averaged over 120 epochs).

| | per run | 96 runs |
|---|---:|---:|
| `batch_size=512` (21,960 steps = 60 epochs) | 1.84 h | — |
| `batch_size=256` (21,960 steps = 30 epochs) | 1.38 h | — |
| **Grid, half of each** | — | **154 h = 6.4 days** |

Expected equals worst case, because early stopping never fires at this cap.

**6.4 days of continuous compute is a decision for the principal investigator,
not for this document.** The runner survives interruption — periodic
checkpointing, deterministic run ids, resume that does not duplicate rows — so
the wall-clock is survivable on a container that has already restarted three
times. Whether it is worth spending is not a methodological question.

## 9. Test seal

No test DataLoader was constructed, no test prediction written, no test metric
computed, and no decision in this document was informed by test data. Verified
by audit at the end of the study and by
`tests/test_v2_runner.py` (the validation-only guard removes the test buckets
before negatives are sampled, so no test label exists in the process).
