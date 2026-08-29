# The preregistered V2 grid does not fit the available compute

**Status:** measured during V2 phase 2, **before any grid run**
**Decision required from the principal investigator.** This is a
preregistration question, not an engineering one.

---

## 1. The measurement

One BIO-GINE M4 epoch, drug-disjoint split seed 0, degree-matched negatives,
187,260 training pairs, on this container (4 cores, `torch.set_num_threads(2)`):

| | before the phi optimisation | after |
|---|---:|---:|
| Per training step (batch 512) | 0.516 s | **0.270 s** |
| Training portion of an epoch (366 steps) | 189 s | **99 s** |
| Validation pass (93,610 pairs) | 5.4 s | **2.9 s** |
| **Epoch total** | **194 s** | **102 s** |

The optimisation (running `phi` on distinct element values and gathering) is
exact and is pinned by `tests/test_bio_gine.py::test_unique_element_path_equals_the_naive_path`.
It bought 1.9x. There is no comparable second win available.

Batch 256 doubles the step count without halving per-step cost; estimated
~117 s/epoch. Grid average across the two batch sizes: **~110 s/epoch**.

## 2. What that costs for 96 runs

| Epochs actually run | Per run | 96 runs |
|---|---:|---:|
| 400 (preregistered cap, no early stop) | 12.2 h | **48.7 days** |
| ~150 | 4.6 h | 18.3 days |
| ~100 | 3.0 h | 12.2 days |
| ~60 | 1.8 h | 7.3 days |

For scale, the Phase A-2 grid was 70 runs in 18 h 14 m — **0.26 h per run**.

## 3. Why V2 is ~50x more expensive per run than Phase A-2

Phase A-2 trained **full-batch**: one optimiser step per epoch, justified in
its protocol section 9 because the cost was dominated by encoding all molecules
rather than by the pair count.

The V2 preregistration specifies `batch_size: [256, 512]`. That is 366 or 732
optimiser steps per epoch instead of one. The model is not slower; it is being
asked to take roughly 500x as many steps.

**This makes "epoch" mean two different things in the two phases.** Phase A-2's
800-epoch cap was 800 optimiser steps. The V2 400-epoch cap is ~146,000. The
preregistered `max_epochs: 400` was written against the Phase A-2 sense of the
word, and against a minibatch loop it is not a comparable budget — it is two
orders of magnitude more optimisation than any Phase A-2 model received.

The 4-epoch smoke run reached validation AUPRC 0.761 and was still improving
(0.7115 → 0.7376 → 0.7538 → 0.7609). Four epochs is already 1,464 optimiser
steps. Where it converges is unknown and must not be guessed at from four
points — Phase A-2's Addendum 12 established that the architectures plateau at
different budgets and that the LR schedule pushes them in opposite directions.

## 4. Options

Each is a deviation from something. None is free. **The choice is not mine to
make**, and it must be made before any grid run, not after seeing results.

### A. Reduce `max_epochs` for V2, keeping everything else
Rationale: corrects the unit mismatch in section 3 rather than weakening the
protocol. 40 epochs is 14,640 optimiser steps, still ~18x Phase A-2's entire
budget.

Cost at 40 epochs: 1.2 h/run, **4.9 days** for 96 runs.
Cost at 30 epochs: 0.9 h/run, **3.7 days**.

Deviation: `max_epochs` and `patience` change. Both are preregistered, and
`max_epochs` sets `T_max` of the cosine schedule, so this changes the
learning-rate trajectory — every configuration is affected identically, so the
comparison between configurations stays fair.

Risk: a cap that stops models before they converge makes every number a lower
bound. Phase A-2 already reports this caveat for its own runs (Addendum 2), so
it is a known and disclosable limitation rather than a hidden one.

**This is my recommendation**, with a budget-adequacy probe run first: train one
configuration to a large cap, plot validation AUPRC against epoch, and set the
cap where the curve flattens. That probe is validation-only and costs one run.
Phase A-2 did exactly this (`cap600_adequacy_curves.json`) and it is the reason
its budget choice is defensible.

### B. Train full-batch, as Phase A-2 did
Cost: roughly 7 minutes per run, ~11 h for the grid.

Deviation: `batch_size` leaves the preregistered set entirely.

Risk, and it is a serious one: **this project has already invalidated a grid for
precisely this reason.** Full-batch means one optimiser step per epoch, which
was the root cause of the invalidated 150-step Phase A-2 run
(`reports/*_BROKEN_150steps.*`). Repeating it deliberately would be
indefensible.

### C. Reduce the grid
Fewer configurations or fewer selection seeds. Directly contradicts the
preregistered `n_configurations: 32` and `selection_seeds: [0,1,2]`. Narrowing a
preregistered search is the move the whole protocol exists to prevent.

### D. Accept the cost
7–49 days of continuous compute on a container that has already been restarted
three times mid-run. The resume infrastructure now makes that survivable, but it
is still weeks.

### E. More compute
A GPU would change these numbers by an order of magnitude. Not available in this
environment; listed for completeness.

## 5. What is NOT in question

- The runner works. The smoke run trained, validated, checkpointed, and resumed.
- The test set is sealed and stays sealed regardless of which option is chosen.
- The 32 x 3 = 96 enumeration matches the preregistration exactly.
- No hypothesis, threshold, split, or negative-sampling rule is affected by any
  option above.
