# PAPER_FACTS.md — evidence base for the DDI-Net manuscript

Every claim the manuscript makes must appear here first, with the file it comes
from. If a claim is not in this table, it does not go in the paper.

**Frozen scientific state**

| | |
|---|---|
| Tag | `v2-final-github-safe-2026-09-03` (annotated, immutable) |
| Commit | `92c481eeaba8faff991ced850e1c4de418ea31b0` |
| Provenance commit | `4657c256ee5e0157f529ebae41e96e0dc4dd9a3e` (local frozen state) |
| Branch | `v2-final-artifacts` |
| Excluded from snapshot | `reports/v2_ablations/pair_predictions.csv` (>100 MB GitHub limit); SHA256 `97918852932816954c70cf26cc6f77440472d5bb35b7608a252cd610ed5c5d45`. Aggregate ablation metrics are complete, so no reported number depends on it. |

All statistics below were **independently recomputed** from per-seed values by
`paper/build_tables.py`, which reads the tag through `git show` and never the
working tree. Agreement with the frozen statistics files was verified to ≤1e-16.

---

## 1. Dataset and biological graph

| Claim | Value | Source | Status |
|---|---|---|---|
| Dataset identifier | `DDI_MECH_1705_V1` | `data/mechanism_v1/MANIFEST.json` | preregistered |
| DDI source | TDC DrugBank DDI, PyTDC 1.1.15, CC BY-NC 4.0 | `DATA_PROVENANCE.md` | preregistered |
| Drugs | 1,705 | `MANIFEST.json` | preregistered |
| Positive DDI pairs | 191,392 | `MANIFEST.json` | preregistered |
| Interaction types in source | 86 | `reports/dataset_report.md` | context |
| Excluded drug | `DB11630`, 10 pairs (0.0052%), unparseable SMILES | `MANIFEST.json` | preregistered |
| Negatives in source | **none** — the source is positive-only | `ddinet/data/negatives.py` | preregistered |
| Drug-protein edge rows | 146,743 | `drug_protein_edges.parquet` | measured |
| Distinct (drug, protein, relation, evidence) triples | 94,088 | `biology.py::_distinct_triples` | measured |
| Relation-type counts | target 139,988; enzyme 3,972; transporter 2,185; carrier 598 | `drug_protein_edges.parquet` | measured |
| Relation types | target, enzyme, transporter, carrier | `biology.py::RELATION_TYPES` | preregistered |
| Evidence types | DOCUMENTED_DATABASE_RELATION, CURATED_MOA, EXPERIMENTAL_BIOACTIVITY | `biology.py::EVIDENCE_TYPES` | preregistered |
| Protein embedding vocabulary | 2,893 | `BiologyBundle` | measured |
| Proteins in `proteins.parquet` | 2,778 | `proteins.parquet` | measured |
| Pathway vocabulary | 1,969 | `pathways.parquet` | measured |
| Protein-pathway edges | 14,576 | `protein_pathway_edges.parquet` | measured |
| M4 drug-protein set elements | 94,088 | `BiologyBundle(M4)` | measured |
| M4 drug-pathway set elements | 284,203 | `BiologyBundle(M4)` | measured |
| Drugs with ≥1 protein | 1,638 / 1,705 (96.07%) | `BiologyBundle(M4)` | measured |
| Drugs with ≥1 pathway | 1,614 / 1,705 (94.66%) | `BiologyBundle(M4)` | measured |
| Proteins per drug, median / max | 19 / 627 | `BiologyBundle(M4)` | measured |
| Pathways per drug, median / max | 52 / 1,078 | `BiologyBundle(M4)` | measured |
| Drug-disjoint split, seed 0 | 1,195 train / 255 val / 255 test drugs | `split_assignments.csv` | preregistered |
| Pooled test pairs | 84,690, prevalence 0.5 | `v2_final_test.csv` | preregistered |
| S3 test pairs | 7,758, prevalence 0.5 | `v2_final_s3_posthoc.csv` | preregistered |
| **DDI edges used as biological features** | **zero** | `biology.py` line 78: never reads `ddi_positive_labels.parquet` or a split file | preregistered |

**Evidence ladder set sizes** (protein elements / pathway elements):
M1 13,043 / 0 · M2 15,291 / 0 · M3 94,088 / 0 · M4 94,088 / 284,203.
Source: `BiologyBundle` under each policy.

## 2. Architecture (read from code, not from the plan document)

| Claim | Value | Source | Status |
|---|---|---|---|
| Selected config ID | `e8ece7c41ae09e5f` | `reports/v2_grid/FROZEN_SELECTED_CONFIG.txt` | preregistered protocol |
| Atom / bond feature dims | 50 / 11 | `features/molgraph.py` | measured |
| Molecular encoder | GINE, **3 layers, hidden 64, SUM pooling** | `BioGineConfig` defaults | measured |
| bio_dim | 128 | `FROZEN_SELECTED_CONFIG.txt` | selected on validation |
| Relation / evidence embedding dims | 16 / 16 | `BioGineConfig` | preregistered |
| Biological aggregation | MEAN | `BioGineConfig` | preregistered (SUM = CONTROL C) |
| dropout_bio / dropout_pair | 0.1 / 0.1 | `FROZEN_SELECTED_CONFIG.txt` | selected on validation |
| Fusion | Linear → LayerNorm, hidden 128 | `BioGine.__init__` | measured |
| Pair decoder input dim | 388 | `BioGine.pair_input_dim` | measured |
| Pair terms | sum, \|difference\|, elementwise product, min/max of modality masks — all commutative | `BioGine.score_pairs` | preregistered |
| Total parameters | 1,122,804 | `BioGine.n_parameters()` | measured |
| Learning rate / batch size | 1e-3 / 512 | `FROZEN_SELECTED_CONFIG.txt` | selected on validation |

> **Documented deviation.** `docs/V2_ARCHITECTURE_PLAN.md` §4.2 says the molecular
> branch is "GINE (4-layer, d=128, same as Phase A-2)". The code comment in
> `bio_gine.py` records that those numbers contradict the phrase: Phase A-2 froze
> `hidden_dim=64, mol_layers=3`. The implementation follows the *measured* Phase
> A-2 configuration so that every M-minus-M0 difference is attributable to the
> biological branch alone. **Methods must state 3 layers / hidden 64.**

## 3. Training and model selection

| Claim | Value | Source | Status |
|---|---|---|---|
| Validation grid | **32 configurations × 3 seeds = 96 runs** | `v2_validation_grid_96_COMPLETE_BACKUP.csv` (96 rows, 32 unique config_id, seeds 0–2) | preregistered |
| Selection criterion | highest mean validation AUPRC across the 3 grid seeds | `FROZEN_SELECTED_CONFIG.txt` | preregistered |
| Winning validation AUPRC | 0.816207 ± 0.007187 | `FROZEN_SELECTED_CONFIG.txt` | measured |
| Test used for selection | **no** — stated in the frozen config file | `FROZEN_SELECTED_CONFIG.txt` | preregistered |
| Final training seeds | 5 (0–4) | `v2_final_test.csv` | preregistered |
| Optimizer-step budget | 21,960 steps | `configs/v2_budget_frozen.yaml` | preregistered amendment |
| Validation interval | every 366 steps → 60 checks | `configs/v2_budget_frozen.yaml` | preregistered amendment |
| Early stopping | patience 30 checks | `configs/v2_budget_frozen.yaml` | preregistered amendment |
| Step budget rationale | identical updates and identical number of checks for batch 256 and 512, removing two confounds | `configs/v2_budget_frozen.yaml` | preregistered amendment |
| Negative sampling | degree-matched; **degree from training pairs only** | `ddinet/data/negatives.py` | preregistered |

> **Superseded.** `docs/V2_PREREGISTRATION_AMENDMENT_FRACTION.md` (an 8×3
> fractional replicate) exists on a working branch but was **not** used by the
> frozen study. Methods must not mention it.

## 4. Evaluation settings

| Setting | Definition | Source |
|---|---|---|
| S1 | both drugs seen in training | `data/leakage.py` |
| S2 | exactly one drug unseen | `data/assemble.py` |
| S3 | **both** drugs unseen — zero DDI adjacency in the training graph | `assemble.py`: `test_S3 = ("test", "test")` |
| pooled drug-disjoint | all test pairs under the drug-disjoint split | `v2_final_test.csv` |
| scaffold-disjoint | **not evaluated in final V2** | absent from the frozen tree |

## 5. Headline results (recomputed from per-seed values, ddof=1)

| Model | Pooled AUPRC | S3 AUPRC | Source |
|---|---|---|---|
| **BIO-GINE M4 (primary)** | **0.811711 ± 0.009671** | **0.737241 ± 0.015253** | `v2_final_test.csv`, `v2_final_s3_posthoc.csv` |
| Aligned molecular GINE (M0) | 0.778445 ± 0.005892 | 0.714502 ± 0.006465 | `v2_baselines/m0_test_s3.csv` |
| Aligned Dual (GINE + DDI network) | 0.714683 ± 0.006681 | 0.619761 ± 0.027842 | `v2_aligned_ensemble.csv` |
| BIO-RF | 0.739612 ± 0.001683 | — | `v2_bio_controls/bio_rf_test.csv` |
| Biological-degree-only RF (CONTROL A) | 0.650422 ± 0.000589 | — | `v2_bio_controls/biological_degree_rf_test.csv` |
| M4 shuffled biology (CONTROL F) | 0.692256 ± 0.005441 | 0.630512 ± 0.010462 | `v2_ablations/test_frozen.csv` |

M4 pooled per-seed: 0.8235342392, 0.8120650668, 0.8070405308, 0.7983598423, 0.8175538494.
M4 S3 per-seed: 0.7536425173, 0.7382629539, 0.7345199317, 0.7133813650, 0.7463995194.

## 6. Ablation ladder — **non-monotonic, report as such**

| Variant | Pooled | S3 |
|---|---|---|
| M0 (no biology) | 0.778445 ± 0.005892 | 0.714502 ± 0.006465 |
| M1 (DrugBank only) | 0.818609 ± 0.001726 | 0.746849 ± 0.007804 |
| M2 (+ ChEMBL curated MoA) | **0.826891 ± 0.005995** | **0.759362 ± 0.011407** |
| M3 (+ ChEMBL bioactivity) | 0.817672 ± 0.004187 | 0.746562 ± 0.005264 |
| **M4 (+ Reactome pathways) — primary** | 0.811711 ± 0.009671 | 0.737241 ± 0.015253 |
| M4 SUM (CONTROL C) | 0.826474 ± 0.009234 | 0.748494 ± 0.012681 |
| M4 shuffled (CONTROL F) | 0.692256 ± 0.005441 | 0.630512 ± 0.010462 |

**Two facts that must not be softened:**

1. **M4 is the lowest-scoring of M1–M4 on both test views.** Every biological
   variant beats M0, but adding ChEMBL bioactivity (M2→M3) and Reactome pathways
   (M3→M4) each *reduced* held-out AUPRC. M4 was fixed by the validation
   protocol before any test evaluation; it is the preregistered primary model,
   not the best test model.
2. **CONTROL C (SUM) outperformed the primary MEAN model** on pooled
   (0.826474 vs 0.811711) and S3 (0.748494 vs 0.737241). The preregistration
   states the interpretation in advance: *"CONTROL C trains the identical model
   with SUM, and if SUM wins, counting was the signal."* This must be reported
   and discussed, alongside CONTROL F, which shows identity also carries large
   signal beyond counting. Both are true simultaneously.

## 7. Hypotheses (Holm family size = **5**, H5 included)

| ID | Status | Δ AUPRC | 95% CI | paired t | raw p | Holm p | Cohen dz | Conclusion |
|---|---|---|---|---|---|---|---|---|
| H-V2-1 | CONFIRMATORY | +0.033266 | [0.027917, 0.038615] | 17.2661 | 6.603e-05 | 1.981e-04 | 7.7216 | Supported |
| H-V2-2 | CONFIRMATORY | +0.117481 | [0.089088, 0.145873] | 11.4881 | 3.277e-04 | 6.555e-04 | 5.1376 | Supported |
| H-V2-3 | CONFIRMATORY | +0.119455 | [0.101957, 0.136953] | 18.9542 | 4.564e-05 | 1.825e-04 | 8.4766 | Supported |
| H-V2-4 | CONFIRMATORY | +0.161289 | [0.149034, 0.173544] | 36.5411 | 3.349e-06 | 1.674e-05 | 16.3417 | Supported |
| H-V2-5 | **EXPLORATORY** | −0.023346 | [−0.060635, +0.013942] | −1.7383 | 1.571e-01 | 1.571e-01 | −0.7774 | **Exploratory direction unsupported** |

Source: `reports/v2_statistics/final_h1_h5_holm.csv`, independently reproduced.

**Holm family.** The correction was applied over all five hypotheses: the
smallest raw p is multiplied by 5, the next by 4, and so on, with a running
maximum to keep the sequence monotonic. Including the exploratory H5 makes the
confirmatory adjustments *stricter*. Methods must say "five", not "four".

**H5 wording.** Preregistered as `type: exploratory`, `alpha: exploratory`, with
the note *"No strict significance threshold. Labelled EXPLORATORY in all
reports."* It is **not** a failed confirmatory hypothesis. Correct phrase:
*exploratory direction unsupported*. Subgroup sizes: 79,163 covered vs 5,527
uncovered pairs per seed (`h5_pathway_coverage.csv`).

**Bootstrap (seed 0, 1,000 resamples, rng 20260829)**, `bootstrap_h1_h3_seed0.csv`:
H-V2-1 observed Δ 0.0396863, bootstrap CI [0.0356170, 0.0432844], fraction ≤ 0 = 0.0;
H-V2-3 observed Δ 0.1321992, bootstrap CI [0.1274428, 0.1367460], fraction ≤ 0 = 0.0.

## 8. Controls

**CONTROL A — biological-degree-only RF.** Random forest on scalar annotation
counts only. 0.650422 ± 0.000589 pooled. Source: `biological_degree_rf_test.csv`.

**CONTROL C — SUM aggregation.** See §6.2. Not a tuning knob; never selected on
validation; reported as a control.

**CONTROL E — linear probe.** Ridge(α=1.0) from the frozen seed-0 biological
embedding to positive training-DDI degree.

| Field | Value |
|---|---|
| n_train_drugs / n_test_drugs | 1,195 / 255 |
| Train R² | 0.5430199338679731 |
| Train target variance | 18,934.24 (range 0–646) |
| **Held-out target variance** | **exactly 0.0** — min = max = 0, unique value {0.} |
| `r2_test` in JSON | 0.0 — **a placeholder, not a measurement** |
| `pearson_test`, `spearman_test` | NaN — the signature of a constant target |

Source: `seed0_linear_probe_summary.json`, `seed0_linear_probe_drugs.csv`
(verified directly by grouping on the `split` column).

Correct reporting: *"The held-out diagnostic was not identifiable because the
target had zero variance under the strict drug-disjoint definition."* It is
**wrong** to write "R² = 0 shows the embedding does not encode degree."

**CONTROL F — degree-preserving biological shuffle.** From
`SHUFFLE_MANIFEST.json`:

| Field | Value |
|---|---|
| Algorithm | stratified degree-preserving bipartite double-edge swap |
| Shuffle seed / swaps per edge | 20260829 / 150 |
| Stratification | 25 classes by the sorted set of `relation_type\|evidence_type` combinations of each (drug, protein) pair |
| Unit | the (drug, protein) pair, so **drug and protein distinct degree are exactly preserved** |
| Edges | 89,049; successful swaps 2,487,716; acceptance 18.62% |
| **Edges retained (unchanged)** | **2,255 = 2.53%** — so 97.47% changed |
| Pathways | protein→pathway edges **not** shuffled; drug→pathway context changes only via the randomised proteins |
| Labels read | none |
| Deviation | preregistered as uniform resampling; implemented as a stratified swap, which preserves *both* degree sequences and the evidence stratum — documented as **stricter than preregistered** |

The 2.53% retained overlap is a real limitation: the control is not a perfect
randomisation and the manuscript must say so.

## 9. Calibration

Temperature scaling, one scalar per seed, **fitted on validation predictions
only** (93,610 validation pairs) and applied unchanged to frozen test
predictions. Source: `v2_calibration/m4_temperature_scaling.csv`.

| Seed | T | ECE₁₅ raw → scaled | Brier raw → scaled |
|---|---|---|---|
| 0 | 7.2003 | 0.19111 → 0.05394 | 0.21282 → 0.17325 |
| 1 | 5.8811 | 0.19597 → 0.06225 | 0.21974 → 0.17901 |
| 2 | 6.2651 | 0.19249 → 0.04786 | 0.22158 → 0.18117 |
| 3 | 7.5842 | 0.21474 → 0.05625 | 0.23399 → 0.18431 |
| 4 | 10.1186 | 0.20850 → 0.06106 | 0.22198 → 0.17524 |

All five converged. AUPRC changes only in the 7th decimal
(e.g. seed 0: 0.8235342392 → 0.8235341519) because temperature scaling is a
monotonic transform of the logits and therefore cannot change ranking.

## 10. Interpretability (frozen seed-0, post-hoc)

Source: `reports/v2_interpretability/`, checkpoint `bd45f84e3c1b2c33`
(SHA256 `b828a471fcb8…59d6f`).

| Analysis | Rows |
|---|---|
| Leave-one-protein-out | 4,031 |
| Leave-one-pathway-out | 13,192 |
| Modality contribution (all test pairs) | 84,690 |
| Protein ablations / pathway ablations | 4,031 / 13,192 over the top 20 pairs |

The frozen summary carries its own interpretation rule, which the manuscript
adopts verbatim in spirit: *"Attribution values describe frozen-model reliance
under post-hoc perturbation. They are not causal biological mechanisms or
clinical recommendations."*

## 11. Falsification criteria (exact preregistered wording)

| ID | Preregistered condition | Outcome |
|---|---|---|
| F1 | "H-V2-1 fails (V2 M4 does not improve over GINE on drug-disjoint)" | **Not triggered** — H1 supported, Δ +0.0333, Holm p 1.98e-04 |
| F2 | "H-V2-3 fails (shuffled biology AUPRC not significantly lower than true)" | **Not triggered** — Δ +0.1195, Holm p 1.83e-04 |
| F3 | "H-V2-4 fails (degree-count RF matches V2 M4)" | **Not triggered** — Δ +0.1613, Holm p 1.67e-05 |
| F4 | "Linear probe R² > 0.6 **AND** H-V2-1 Cohen's d < 0.2" | **Cannot trigger** — the second conjunct fails outright (dz = 7.72 ≫ 0.2). Separately, the held-out probe is non-identifiable; `f4_probe_component_r2_gt_0_6` is `false` |
| F5 | "V2 M4 improves on random_pair but NOT on drug-disjoint or scaffold-disjoint" | **Drug-disjoint component not triggered.** Scaffold-disjoint was not evaluated in final V2, so the criterion is not fully resolved. |
| joint | "F1 AND F2 both hold" | Not triggered |

Hypothesis H-V2-1 also carried `requires_both: true` (p < 0.05 **and** d > 0.5):
both conditions are met (Holm p 1.98e-04; dz 7.72). H-V2-3 likewise.

## 12. Scope limits that must appear in the manuscript

- Age is **not** a model input. No age-stratified claim is supportable.
- No dose, sex, renal or hepatic function, or any patient-level variable is an input.
- Metabolism enters only indirectly, through enzyme/transporter/pathway annotations.
- The system is a research prediction tool. It is not clinically validated, and
  no output may be described as a clinical recommendation.
- Interpretability identifies **model reliance**, never pharmacological causation.

## 13. Open items marked [VERIFY] in the manuscript

None. Every number used in the manuscript resolved to a frozen source.
