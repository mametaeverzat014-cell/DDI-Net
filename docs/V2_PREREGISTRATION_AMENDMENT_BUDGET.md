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

*Written after the pilot. See section 8 for the measured curves.*

<!-- FILLED IN AFTER THE PILOT RUNS -->

## 8. Results

*Filled in after the pilot. Raw curves:
`reports/v2_budget_adequacy/budget_adequacy_curves.csv`.*

<!-- FILLED IN AFTER THE PILOT RUNS -->

## 9. Test seal

No test DataLoader was constructed, no test prediction written, no test metric
computed, and no decision in this document was informed by test data. Verified
by audit at the end of the study and by
`tests/test_v2_runner.py` (the validation-only guard removes the test buckets
before negatives are sampled, so no test label exists in the process).
