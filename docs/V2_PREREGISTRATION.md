# V2 Preregistration: Mechanism-Aware DDI Prediction

**Registered:** 2026-08-29
**Status:** LOCKED — do not modify after experiments begin
**Version:** V2-PREREG-1
**Companion:** docs/V2_ARCHITECTURE_PLAN.md, configs/v2_preregistered.yaml

---

## 1. Preregistration Statement

This document pre-specifies all hypotheses, metrics, statistical tests, and
decision criteria for V2 experiments. It is locked before any training runs
commence. Post-hoc modification of hypotheses is not permitted.

Any analysis not described here must be explicitly labelled:
"EXPLORATORY — not preregistered".

---

## 2. Research Question

Can biologically grounded structure → protein → pathway representations
provide useful DDI context for unseen drugs, where known-DDI graph topology
fails to transfer?

Operationalisation: does the V2 BIO-GINE model (molecular + DeepSets biological
encoder) improve drug-disjoint AUPRC over the molecular-only GINE baseline,
after degree-matched negative sampling, when the improvement exceeds that of
a degree-preserving biological shuffle?

---

## 3. Dataset

DDI_MECH_1705_V1.
Location: data/mechanism_v1/.
1,705 drugs. 191,392 positive DDI pairs. DB11630 excluded.
16/16 validation tests pass. Dataset is frozen and not modified for V2.

Biological feature graph: 10,357 nodes, 406,526 edges.
Zero INTERACTS_WITH edges (verified).

---

## 4. Splits (FROZEN — identical to Phase A-2)

Split files:
- data/mechanism_v1/split_assignments.csv
- data/mechanism_v1/split_assignments_random_pair.csv.gz

| Scheme | Type | Seeds |
|--------|------|-------|
| random_pair | Pair-level | 0,1,2,3,4 |
| drug | Drug-disjoint | 0,1,2,3,4 |
| scaffold | Scaffold-disjoint | 0,1,2,3,4 |

Sub-splits (drug-disjoint):
- S1: test drugs that appear in the training DDI graph
- S2: test drug pairs where one drug is in training, one is not
- S3: test pairs where BOTH drugs have no training DDI adjacency

Primary evaluation: drug-disjoint, all seeds.
S3 is the key evaluation for the biological-transfer hypothesis.

---

## 5. Negative Sampling

PRIMARY: degree-matched negatives (identical protocol to Phase A-2).
SECONDARY: uniform negatives (reported for completeness).

Primary conclusions are always based on degree-matched results.

If degree-matched and uniform negatives give contradictory conclusions,
both are reported and the discrepancy is discussed as a key finding.
The primary conclusion is not changed to uniform because V2 performs
better under uniform sampling.

---

## 6. Primary Metric

AUPRC (Area Under Precision-Recall Curve), computed per seed.
Aggregated as mean +/- std over 5 seeds.

Secondary metrics (reported, not used for hypothesis decisions):
- AUROC
- F1 at threshold chosen from validation set
- ECE (15-bin)
- Brier score

---

## 7. Primary Model

V2 BIO-GINE, configuration M4:

- Molecular encoder: GINE (4-layer, d=128, same as Phase A-2)
- Biological encoder: DeepSets (protein level: MEAN aggregation, d=64;
  pathway level: MEAN aggregation, d=64)
- Biological input: DrugBank + ChEMBL CURATED_MOA + ChEMBL EXPERIMENTAL_BIOACTIVITY
  + Reactome pathways
- Fusion: linear projection + LayerNorm [256 -> 128]
- Pair decoder: symmetric MLP on [h_A+h_B | |h_A-h_B| | h_A*h_B]
- Missing biology: learned MISSING_PROT and MISSING_PATH tokens

Full architecture specification in docs/V2_ARCHITECTURE_PLAN.md.
Full hyperparameter grid in configs/v2_preregistered.yaml.

---

## 8. Preregistered Hypotheses

### H-V2-1: Biological model improves over molecular-only GINE

Claim:
V2 M4 mean AUPRC > GINE mean AUPRC on drug-disjoint, degree-matched,
averaged across 5 seeds.

Formal specification:
- Statistic: mean of (AUPRC_V2_M4_seed_k - AUPRC_GINE_seed_k) for k in {0..4}
- Test: paired two-sided t-test, df=4
- Significance: p < 0.05
- Effect size: Cohen's d > 0.5 (medium or larger)

Both conditions (p < 0.05 AND d > 0.5) must hold for a positive conclusion.

Positive outcome: biological context reliably improves unseen-drug performance.
Negative outcome: V2 M4 <= GINE or difference is small or uncertain.

### H-V2-2: Biological model improves over dual DDI-network model on S3

Claim:
V2 M4 mean AUPRC > Dual GINE+DDI-net mean AUPRC on S3, degree-matched.

S3 definition: drug-disjoint test pairs where BOTH drugs have zero DDI
adjacency in the training graph. This is where the DDI-network branch
is most impaired.

Formal specification:
- Statistic: mean of (AUPRC_V2_M4_S3_seed_k - AUPRC_Dual_S3_seed_k) for k in {0..4}
- Test: paired two-sided t-test, df=4
- Significance: p < 0.05

(No minimum effect size threshold for H-V2-2 — any significant improvement
on S3 is meaningful given the expected difficulty.)

Positive outcome: biological context helps specifically where DDI topology fails.
Negative outcome: V2 M4 <= Dual on S3 despite no DDI adjacency in Dual.

### H-V2-3: True biological assignments outperform degree-preserving shuffled assignments

Claim:
V2 M4 (true biology) mean AUPRC > V2 shuffled (degree-preserving protein shuffle,
CONTROL F) mean AUPRC on drug-disjoint, degree-matched.

This is the anti-shortcut test. The shuffled model preserves protein count
per drug but randomises protein identity. If performance is unchanged,
the model learns degree, not biology.

Formal specification:
- Statistic: mean of (AUPRC_true_seed_k - AUPRC_shuffled_seed_k) for k in {0..4}
- Test: paired two-sided t-test, df=4
- Significance: p < 0.05
- Effect size: Cohen's d > 0.5

Both conditions must hold for a positive conclusion.

Note: V2 shuffled is trained from scratch on the shuffled graph with identical
hyperparameters. It is not zero-shot. If V2 shuffled performs similarly to V2
true, the model is learning degree.

Positive outcome: true biology significantly exceeds shuffled (identity matters).
Negative outcome: shuffled approximates true (degree dominates -> H-V2-3 falsified).

### H-V2-4: Biological encoder provides benefit beyond scalar biological-degree features

Claim:
V2 M4 mean AUPRC > biological-degree-only RF mean AUPRC on drug-disjoint,
degree-matched.

The biological-degree-only RF uses only scalar counts
(n_targets, n_enzymes, n_transporters, n_carriers, n_proteins, n_pathways,
n_adverse_events, n_chembl_proteins) as pair features.

Formal specification:
- Statistic: mean of (AUPRC_V2_M4_seed_k - AUPRC_biodegree_RF_seed_k) for k in {0..4}
- Test: paired two-sided t-test, df=4
- Significance: p < 0.05

Positive outcome: V2 M4 significantly exceeds count-only RF (protein identity matters).
Negative outcome: RF with counts matches V2 M4 (count features explain the gain).

### H-V2-5: Biological benefit is larger for pathway-resolved drugs

Claim:
The AUPRC improvement of V2 M4 over GINE is larger for pairs where BOTH
drugs have Reactome pathway coverage than for pairs where at least one drug
lacks pathway coverage.

Sub-analysis:
- covered: pairs where both drugs have >= 1 Reactome pathway
- uncovered: pairs where at least one drug has 0 Reactome pathways

Metric: delta_covered = mean(AUPRC_V2_covered - AUPRC_GINE_covered)
        delta_uncovered = mean(AUPRC_V2_uncovered - AUPRC_GINE_uncovered)

Claim: delta_covered > delta_uncovered (directional only, no strict threshold)

This is labelled EXPLORATORY. It is preregistered as a direction to examine,
not a hypothesis with a significance threshold.

---

## 9. Statistical Analysis Plan

### 9.1 Paired comparisons

All primary comparisons are paired by seed (same seed k compared across models).
Five paired differences -> mean and std of differences, t-statistic, p-value, CI.

Never use independent-sample tests when runs share the same seeds/splits.

### 9.2 Paired t-test specification

- Two-sided test
- df = 4 (five seeds)
- Compute t = mean(differences) / (std(differences) / sqrt(5))
- Report: t-statistic, p-value, 95% CI on mean difference

### 9.3 Bootstrap confidence intervals

For H-V2-1 and H-V2-3 additionally compute:
- Bootstrap CI at the PAIR level (over individual drug pairs, not seeds)
- Seed: seed 0 only, selected before observing test results
- 1,000 bootstrap samples with replacement over test pairs
- Report: 95% bootstrap CI on AUPRC

### 9.4 Effect size

Report Cohen's d for all paired comparisons:
  d = mean(differences) / std(differences)

Interpret: d < 0.2 negligible, 0.2-0.5 small, 0.5-0.8 medium, > 0.8 large.

Primary hypotheses H-V2-1 and H-V2-3 require d > 0.5 for a positive conclusion.

### 9.5 Multiple comparisons

Five primary hypotheses (H-V2-1 through H-V2-5). Apply Holm-Bonferroni
correction to the five p-values when stating joint conclusions.
Individual hypothesis reports use uncorrected p < 0.05 as threshold.

### 9.6 Seed reporting

Report AUPRC per seed for all models in appendix tables.
Primary tables report mean +/- std.
Do not select the best seed post-hoc.

---

## 10. Hyperparameter Selection Protocol

### 10.1 Validation criterion

Model selection metric: drug-disjoint validation AUPRC.

Do NOT use:
- Test AUPRC at any point during hyperparameter search
- Random-pair validation AUPRC as the selection criterion (this would bias
  toward random-pair performance and undermine the transfer evaluation)
- Scaffold-disjoint validation as the primary selection metric

### 10.2 Preregistered search grid

| Hyperparameter | Values |
|----------------|--------|
| bio_dim | {64, 128} |
| mol_dim | 128 (frozen from Phase A-2) |
| dropout_bio | {0.1, 0.3} |
| dropout_pair | {0.1, 0.2} |
| lr | {1e-3, 3e-4} |
| batch_size | {256, 512} |
| max_epochs | 400 |
| patience | 30 epochs on val AUPRC |

Total: 2^5 = 32 configurations.

### 10.3 Grid search protocol

1. Run each of 32 configurations with seeds {0, 1, 2}
2. Select configuration with best mean drug-disjoint validation AUPRC
3. Freeze the selected configuration
4. Run the frozen configuration with all 5 seeds {0,1,2,3,4}
5. Evaluate test AUPRC only at this point, exactly once

### 10.4 Frozen configuration

After step 3, the configuration is locked.
No further tuning based on any performance observation is permitted.

---

## 11. Ablation Sequence

Run ablations after the primary V2 M4 model is selected and frozen.
All ablations use the same frozen hyperparameter configuration.

Order:
1. M1: DrugBank protein only
2. M2: + ChEMBL CURATED_MOA
3. M3: + ChEMBL EXPERIMENTAL_BIOACTIVITY
4. M4: + Reactome (primary — may already be trained during grid search)
5. CONTROL A: biological-degree-only RF
6. BIO-RF: non-GNN biological baseline
7. CONTROL C: V2 with SUM aggregation
8. CONTROL F: V2 with shuffled biology
9. CONTROL E: linear probe (post-hoc, no training)
10. M5: + SIDER (only if M4 >> M3 on drug-disjoint validation)

---

## 12. Falsification Criteria

The biological-transfer hypothesis is falsified if ANY of the following holds:

F1: H-V2-1 fails
- V2 M4 AUPRC <= GINE AUPRC on drug-disjoint (biological context provides no benefit)

F2: H-V2-3 fails
- Shuffled biology AUPRC is not significantly lower than true biology AUPRC
- Conclusion: model exploits protein/pathway count (degree), not identity

F3: H-V2-4 fails
- Biological-degree-only RF matches V2 M4 AUPRC
- Conclusion: scalar counts from biological annotations explain all the gain

F4: Linear probe R^2 > 0.6 and H-V2-1 effect size d < 0.2
- Biological embeddings substantially encode DDI degree and the gain is small
- Conclusion: V2 has learned a glorified degree feature, not biological mechanism

F5: V2 M4 improves on random_pair but NOT on drug-disjoint or scaffold-disjoint
- Conclusion: model learns DDI topology via biological proxy rather than
  transferable drug-level biology

Joint falsification: if F1 and F2 both hold, the conclusion is:
"The model exploits biological annotation popularity rather than mechanism.
The biological-transfer hypothesis is not supported at this dataset scale."

---

## 13. Reporting Requirements

For every model comparison:
- Mean AUPRC +/- std (5 seeds)
- Per-seed AUPRC in appendix
- Paired differences (V2 - baseline): mean +/- std
- 95% CI on mean difference
- t-statistic and p-value (paired t-test)
- Cohen's d
- Bootstrap CI (for H-V2-1 and H-V2-3 only)

Required table dimensions:
- Rows: at least models 1-12 from the comparison table
- Columns: random_pair, drug-disjoint, scaffold-disjoint, S3
- Negative sampling: degree-matched (primary), uniform (secondary appendix)

Do not report ONLY the best seed.
Do not report ONLY random-pair AUPRC.
Primary conclusions must cite drug-disjoint and S3 results.

---

## 14. Calibration

Evaluation metrics per model:
- ECE (15 equally-spaced bins)
- Brier score
- Reliability diagram (visual, not a hypothesis)

Calibration method: temperature scaling.
Temperature parameter is fit on drug-disjoint validation set only.
The test set is never used during calibration fitting.

---

## 15. Interpretability

Attribution outputs are generated post-hoc on the drug-disjoint test set, seed 0.

Methods:
- Leave-one-protein-out: for top-20 predicted pairs (by confidence)
- Leave-one-pathway-out: same pairs
- Modality contribution: for all test pairs
- Linear probe: for all training + test drugs

All results are labelled: "model reliance" not "causal mechanism".
The model's reliance on a protein does not establish that protein as the
pharmacological mediator of the DDI.

---

## 16. Timeline Constraint

This preregistration document must be committed to the repository
BEFORE any V2 training run begins.

Commit SHA of this preregistration serves as the temporal anchor.
Any result computed before this commit is Phase A-2.
Any result computed after this commit is V2 (or exploratory if unlabelled).
