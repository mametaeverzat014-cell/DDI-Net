# V2 Architecture Plan: Mechanism-Aware DDI Prediction

**Version:** V2-DRAFT-1
**Status:** PREREGISTERED DESIGN — do not modify after experiments begin
**Dataset:** DDI_MECH_1705_V1 (data/mechanism_v1/)
**Date:** 2026-08-29
**Companion:** docs/V2_PREREGISTRATION.md, configs/v2_preregistered.yaml

---

## 1. Central Research Question

Can biologically grounded structure → protein → pathway representations
provide useful DDI context for unseen drugs, where known-DDI graph topology
fails to transfer?

Phase A-2 established that the DDI-network branch improves random-pair AUPRC
but hurts or fails to help on drug-disjoint and scaffold-disjoint splits — the
scientifically honest evaluation of generalisation to previously unseen drugs.
V2 replaces the DDI-network branch with inductive biological context derived
from the feature graph in data/mechanism_v1/.

---

## 2. Frozen Phase A-2 Baselines

These results are fixed. The models are not retrained for V2.

| Model | Split | AUPRC (approx) | Neg. sampling |
|-------|-------|-----------------|---------------|
| Degree-only | drug-disjoint | ~0.549 | degree-matched |
| RF ECFP4 | drug-disjoint | ~0.763 | degree-matched |
| GINE | drug-disjoint | ~0.754 | degree-matched |
| Dual (GINE + DDI-net) | drug-disjoint | ~0.730 | degree-matched |
| Dual (GINE + DDI-net) | S3 | < GINE | degree-matched |

Key finding: molecular GINE dominates the dual model on drug-disjoint and S3,
showing DDI-network topology hurts generalisation to unseen drugs. V2 must
beat GINE on drug-disjoint without relying on DDI-network adjacency.

---

## 3. Biological Encoder: Option Analysis

Three encoder families were evaluated before selecting the primary design.

### Option 1: Set Encoder / DeepSets

```
bio_prot(d) = rho( MEAN_{p in P(d)} phi( embed(p), embed(rel_type) ) )
bio_path(d) = rho( MEAN_{q in Q(d)} phi( embed(q) ) )
bio(d)      = [ bio_prot(d) | bio_path(d) ]
```

where phi and rho are MLPs.

Properties:
- Fully inductive: works for any drug without DDI graph adjacency at inference
- MEAN aggregation removes direct count information from the representation
- Permutation-invariant over the protein/pathway set
- Trivial to ablate by evidence source: filter which edges enter P(d) or Q(d)
- Leave-one-protein-out attribution is exact and cheap
- Parameter count comparable to the GINE molecular encoder
- Stable training on only 1,705 drug examples

Degree shortcut risk: MEDIUM
- MEAN normalises by set size, removing the direct degree signal
- But protein embedding magnitudes may still correlate with DDI degree if
  well-studied proteins concentrate in high-DDI drugs
- Controlled by: CONTROL C (sum vs mean), CONTROL F (permutation test)

### Option 2: Heterogeneous GNN (DRUG-PROTEIN-PATHWAY)

```
Layer 0: protein nodes aggregate from Reactome pathway neighbours
Layer 1: drug nodes aggregate from protein neighbours
h_drug = readout(drug node after 2 layers)
```

Properties:
- Captures higher-order structure: proteins sharing pathways influence each other
- Expressively models which specific pathway-protein combinations matter

Drawbacks:
- With only 1,705 drug nodes, GNN training is under-constrained
- Full message passing over 10,357 nodes and 406,526 edges is costly
- Standard SUM aggregation at GNN level re-introduces degree as a signal
- PPI layer (15,087 edges) would add a third level of degree correlation
- Interpretability requires attention or post-hoc attribution
- Evidence-type ablations require re-running graph construction each time
- Risk of overfitting biological graph topology to DDI labels

Degree shortcut risk: HIGH
- SUM aggregation in standard GNN is equivalent to counting neighbours
- Mean aggregation reduces this but does not eliminate it
- Node degree still enters via neighbour feature statistics

### Option 3: Precomputed Protein Sequence Embeddings (ESM2 / ProtTrans)

```
h_p = ESM2(sequence_p)   [fixed, not trained]
bio(d) = rho( MEAN_{p in P(d)} h_p )   [rho is trained]
```

Properties:
- Encodes protein sequence semantics at no DDI-task training cost
- Potentially captures function-relevant protein representations

Drawbacks:
- ESM2 embeddings are 480-1,280 dimensional — high-dimensional aggregation
  on 1,705 examples risks overfitting the aggregation layer
- Not end-to-end with the DDI objective
- Cannot be ablated by evidence type without additional engineering
- External model dependency: download, storage, version lock required
- Protein IDs must exactly match UniProt accessions used here

Degree shortcut risk: LOW for sequence shortcuts; but ESM2 representations
of highly studied proteins may correlate with DDI popularity through
indirect biological signals.

### Decision: Option 1 (DeepSets) as Primary

Justification:
1. Dataset scale: 1,705 drugs is small for a GNN; overfitting risk is real
2. Clean ablations: swap evidence sources by filtering edges only
3. Mean aggregation: clearest shortcut control (MEAN vs SUM experiment)
4. Permutation test: straightforward to implement and interpret
5. Interpretability: leave-one-protein-out is exact
6. Parameter parity: comparable to GINE baseline
7. Training stability: no graph convolution over a sparsely labelled drug set

Option 2 (Hetero-GNN) is retained as a secondary ablation after M4 to
test whether graph structure adds value beyond set aggregation.

---

## 4. Primary V2 Architecture: BIO-GINE

### 4.1 Overview

```
Drug A --> Molecular Encoder (GINE) ---------> mol_emb_A --|
       --> Biological Encoder (DeepSets) ----> bio_emb_A --|
                                                           +--> Fusion --> h_A --|
                                                                                  +--> Pair Decoder --> P(DDI|A,B)
Drug B --> Molecular Encoder (GINE) ---------> mol_emb_B --|                     |
       --> Biological Encoder (DeepSets) ----> bio_emb_B --|                     |
                                                           +--> Fusion --> h_B --|
```

Both encoders are trained jointly from random initialisation.
No weights are transferred from Phase A-2.

### 4.2 Molecular Encoder (same as Phase A-2 GINE)

- Input: molecular graph (atom features: atomic number, degree, aromaticity,
  hybridisation; bond features: bond type, ring membership)
- Architecture: 4-layer GINE with residual connections
- Global readout: mean pooling over atom representations
- Output: mol_emb(d) in R^128

### 4.3 Biological Encoder (DeepSets, two-level)

**Level 1 — Protein aggregation**

Input per protein p associated with drug d:
- embed_prot(p): learned protein embedding in R^64 (vocabulary: 2,778 UniProt IDs)
- embed_reltype(r): learned relation-type embedding in R^16
  (r in {target, enzyme, transporter, carrier})
- embed_evtype(e): learned evidence-type embedding in R^16
  (e in {DOCUMENTED_DATABASE_RELATION, CURATED_MOA, EXPERIMENTAL_BIOACTIVITY})

Per-protein representation:
```
h_p = phi_prot( concat(embed_prot(p), embed_reltype(r), embed_evtype(e)) )
    = phi_prot( R^96 ) --> R^64
```
phi_prot: 2-layer MLP [96 -> 128 -> 64], ReLU, no dropout in phi

Drug-level protein aggregation:
```
bio_prot(d) = rho_prot( MEAN_{p in P(d)} h_p )
```
rho_prot: 2-layer MLP [64 -> 128 -> 64], ReLU + Dropout(p_bio)

Missing biology: if |P(d)| = 0, bio_prot(d) = MISSING_PROT (learned vector in R^64)

**Level 2 — Pathway aggregation**

Input per pathway q associated with drug d (via protein-pathway edges):
- embed_path(q): learned pathway embedding in R^64 (vocabulary: 1,969 Reactome IDs)

Per-pathway representation:
```
h_q = phi_path( embed_path(q) ) --> R^64
```
phi_path: 2-layer MLP [64 -> 128 -> 64], ReLU

Drug-level pathway aggregation:
```
bio_path(d) = rho_path( MEAN_{q in Q(d)} h_q )
```
rho_path: 2-layer MLP [64 -> 128 -> 64], ReLU + Dropout(p_bio)

Q(d) = {pathways reachable from P(d) via protein_pathway_edges.parquet}

Missing pathways: if |Q(d)| = 0, bio_path(d) = MISSING_PATH (learned vector in R^64)

**Concatenation:**
```
bio(d) = concat( bio_prot(d), bio_path(d) )   in R^128
```

**Modality mask** (always passed through, not used to gate embeddings):
```
mask(d) = [ int(|P(d)| > 0), int(|Q(d)| > 0) ]   in {0,1}^2
```
The pair decoder receives the concatenated masks as auxiliary features.

### 4.4 Fusion

```
cat(d)  = concat( mol_emb(d), bio(d) )   in R^256
h(d)    = LayerNorm( W_fuse @ cat(d) + b_fuse )   in R^128
```

W_fuse in R^{128 x 256}. Simple linear projection + LayerNorm.
No gating in primary model — gating complicates ablation interpretation.

### 4.5 Pair Decoder

Symmetric by construction:
```
pair_feat = concat( h_A + h_B,
                    |h_A - h_B|,
                    h_A * h_B,
                    mask_A,
                    mask_B )     in R^{384 + 4}

score = sigmoid( MLP_pair( pair_feat ) )
```

MLP_pair: 3 hidden layers [388 -> 256 -> 128 -> 1], ReLU, Dropout(p_pair)

Symmetry: f(A,B) = f(B,A) is guaranteed because:
- h_A + h_B = h_B + h_A
- |h_A - h_B| = |h_B - h_A|
- h_A * h_B = h_B * h_A (element-wise)

### 4.6 Parameter Budget

| Component | Parameters |
|-----------|-----------|
| GINE molecular encoder | ~300,000 |
| Protein embeddings (2778 x 64) | 177,792 |
| Relation type embeddings (4 x 16) | 64 |
| Evidence type embeddings (3 x 16) | 48 |
| phi_prot MLP [96->128->64] | 24,832 |
| rho_prot MLP [64->128->64] | 24,832 |
| Pathway embeddings (1969 x 64) | 125,696 |
| phi_path MLP [64->128->64] | 16,640 |
| rho_path MLP [64->128->64] | 16,640 |
| MISSING tokens (2 x 64) | 128 |
| Fusion [256->128] + LN | 33,152 |
| Pair decoder MLP [388->256->128->1] | 133,249 |
| **Total** | **~853,000** |

V2 is approximately 2.8x the size of the GINE baseline (~300K).
If V2 significantly outperforms GINE, run a parameter-matched control:
reduce bio_dim from 64 to 32, giving ~550K total parameters.

---

## 5. Missing Biology Handling

| Gap | Count | % of 1,705 |
|-----|-------|-----------|
| No protein data (any source) | 67 | 3.9% |
| No Reactome pathway | 153 | 9.0% |
| No SIDER adverse events | 790 | 46.3% |

Strategy:
- UNKNOWN is not NEGATIVE. Missing annotation does not mean no biology.
- Two learned missing tokens: MISSING_PROT and MISSING_PATH, both in R^64.
  These are model parameters, trained jointly.
- The modality mask (has_protein, has_pathway) is always passed to the pair
  decoder, allowing it to learn different scoring behaviour for missing-data pairs.
- No imputation. Do not hallucinate protein or pathway assignments.

Evaluation note:
- Report AUPRC separately for pairs where BOTH drugs have full coverage vs.
  pairs where at least one drug has a missing modality.
- This quantifies the model's behaviour under missing data, not just average.

---

## 6. Non-GNN Biological Baseline (Required)

Before claiming any hetero-GNN or DeepSets advantage, implement:

### BIO-RF

Random Forest on per-drug biological features, evaluated on drug-disjoint test.

Per-drug features:
- Scalar counts from drugs.parquet:
  n_targets, n_enzymes, n_transporters, n_carriers, n_proteins, n_pathways,
  n_adverse_events (replaces n_chembl_proteins for simplicity)
- Binary protein membership: multi-hot vector over 2,778 UniProt IDs
  (dimensionality-reduced to 128 via SVD on training set only)
- Binary pathway membership: multi-hot vector over 1,969 Reactome IDs
  (dimensionality-reduced to 64 via SVD on training set only)
- ECFP4 fingerprint (same configuration as Phase A-2)

Pair features (for drug pair A, B):
- |feat_A - feat_B|
- feat_A * feat_B (element-wise product)
- feat_A + feat_B

Total pair feature dimension: ~3 x (7 + 128 + 64 + ECFP4_dim)

Model: RandomForest with n_estimators=500, max_features=sqrt, same as Phase A-2.

### BIO-MLP

Same pair features as BIO-RF, but with a 3-layer MLP. Verifies that BIO-RF's
performance is not an artefact of the RF's ability to handle high-dimensional
sparse features.

If BIO-RF or BIO-MLP matches V2 BIO-GINE AUPRC, the DeepSets encoder provides
no advantage over a simpler biological feature model.

---

## 7. Shortcut Controls

The Spearman correlations between DDI degree and biological feature counts
are HIGH (max |r| = 0.443). This is the central confound for V2.

### CONTROL A: Biological-Degree-Only Baseline

RF with only scalar biological count features per drug pair:
n_targets, n_enzymes, n_transporters, n_carriers, n_proteins, n_pathways,
n_adverse_events, n_chembl_proteins

Pair features: difference, product, sum.

This is the null model for biological popularity. If V2 does not
substantially exceed CONTROL A, all benefit is from counts, not identity.

### CONTROL B: Degree-Matched Negative Sampling

Already part of the frozen protocol. All primary results use degree-matched
negatives. This prevents the model from trivially separating by DDI degree.

### CONTROL C: Mean vs Sum Aggregation

Train two identical V2 M4 architectures: MEAN-V2 and SUM-V2.

If SUM-V2 substantially outperforms MEAN-V2 on drug-disjoint degree-matched:
-> degree (via sum aggregation) is the dominant signal.

If MEAN-V2 >= SUM-V2:
-> drug identity drives performance, not simple counting.

### CONTROL D: Degree-Stratified Analysis

Stratify drug-disjoint test drugs by DDI degree quartile.
Report AUPRC improvement (V2 over GINE) per quartile.

If improvement concentrates in the top DDI-degree quartile (most studied drugs),
the biological encoder may be exploiting popularity, not mechanism.

### CONTROL E: Linear Probe (bio_emb -> DDI_degree)

After training, fit a linear regression from bio_emb(d) -> DDI_degree(d)
on the training drugs. Evaluate R^2 on held-out drug-disjoint test drugs.

Report R^2. If R^2 > 0.4, the learned embeddings substantially encode degree.
This is a diagnostic, not a gate. Report regardless of result.

### CONTROL F: Degree-Preserving Protein Shuffle

Create drug_protein_edges_shuffled.parquet:
- For each drug d, draw |P(d)| proteins uniformly without replacement from
  the global protein pool, preserving the exact per-drug degree distribution.
- Pathways for shuffled assignments: derive Q(d) from shuffled P(d) using
  the same protein_pathway_edges.parquet (do not re-shuffle pathways).
- The shuffled graph has identical degree distribution but randomised identity.

Train V2 M4 from scratch on shuffled biology (same training set pairs,
same negative sampling, same hyperparameters as the true-biology model).

Compare on drug-disjoint test:
- If AUPRC(true) >> AUPRC(shuffled): model uses protein identity -> H-V2-3 supported
- If AUPRC(true) ~= AUPRC(shuffled): model uses degree -> H-V2-3 falsified

The shuffled dataset is created ONCE and frozen before any training begins.

---

## 8. Evidence-Type Ablations

All ablations use identical architecture. Only the biological input filter changes.

| ID | Molecular | DrugBank protein | ChEMBL MOA | ChEMBL Bioactivity | Reactome pathway |
|----|:---------:|:----------------:|:----------:|:------------------:|:----------------:|
| M0 | Y | - | - | - | - |
| M1 | Y | Y | - | - | - |
| M2 | Y | Y | Y | - | - |
| M3 | Y | Y | Y | Y | - |
| M4 | Y | Y | Y | Y | Y |
| M5* | Y | Y | Y | Y | Y |

*M5 adds SIDER drug-adverse-event edges as a third DeepSets level.
Run M5 only if M4 significantly improves over M3 on drug-disjoint validation.

M0 is the Phase A-2 GINE result (reused, not retrained).

The marginal contribution of each evidence source is:
- M1 - M0: DrugBank protein relations
- M2 - M1: ChEMBL curated mechanism of action
- M3 - M2: ChEMBL experimental bioactivity
- M4 - M3: Reactome pathway membership

---

## 9. Full Model Comparison Table

| # | Model | Bio encoder | Neg. sampling | Notes |
|---|-------|-------------|---------------|-------|
| 1 | Degree-only | None | degree-matched | Phase A-2, frozen |
| 2 | RF ECFP4 | None | degree-matched | Phase A-2, frozen |
| 3 | GINE (M0) | None | degree-matched | Phase A-2, frozen |
| 4 | Dual GINE+DDI-net | None | degree-matched | Phase A-2, frozen |
| 5 | Biological-degree RF | Scalar counts | degree-matched | CONTROL A |
| 6 | BIO-RF | Multi-hot+SVD+ECFP4 | degree-matched | Non-GNN biological baseline |
| 7 | V2 SUM-agg (M4) | DeepSets SUM | degree-matched | CONTROL C |
| 8 | V2 shuffled bio (M4) | DeepSets MEAN, shuffled | degree-matched | CONTROL F |
| 9 | V2 M1 | DrugBank only | degree-matched | Evidence ablation |
| 10 | V2 M2 | + ChEMBL MOA | degree-matched | Evidence ablation |
| 11 | V2 M3 | + ChEMBL bioactivity | degree-matched | Evidence ablation |
| 12 | V2 M4 (primary) | + Reactome | degree-matched | PRIMARY V2 |
| 13 | V2 M5 (optional) | + SIDER | degree-matched | If M4 >> M3 |

Models 1-4 are frozen baselines. Models 5-13 are V2 experiments.

---

## 10. Interpretability Plan

### 10.1 Leave-One-Protein-Out

For a predicted drug pair (A, B):
1. Compute baseline score s0 = model(A, B)
2. For each protein p in P(A) union P(B):
   a. Remove p from the protein set of the containing drug(s)
   b. Compute s_p = model(A_minus_p, B_minus_p)
   c. Attribution: delta_p = s0 - s_p
3. Report top-5 proteins by |delta_p|

### 10.2 Leave-One-Pathway-Out

Same procedure over pathway sets Q(A) union Q(B).

### 10.3 Modality Contribution

Set bio_emb(d) = MISSING_PROT and MISSING_PATH for one drug at a time.
Measure the score change. Quantifies how much each drug's biology contributes.

### 10.4 Linear Probe (CONTROL E)

Fit linear regression from bio_emb(d) to DDI_degree(d).
Report R^2, correlation, and scatter plot for the preregistration record.

### 10.5 Attribution Label

All interpretability outputs are labelled as "model reliance".
They indicate which features the model weights most, not which proteins
causally mediate the drug interaction. Do not overstate mechanistic claims.

---

## 11. Counterfactual Test (Future — not V2)

For a predicted DDI (A, B) with a reported pharmacological mechanism:
1. Remove the drug-protein edge corresponding to the known interaction site
2. Measure change in predicted probability: delta_target
3. Repeat for degree-matched random edges: delta_random (distribution)
4. Compare: is delta_target > median(delta_random)?

If yes: the model relies on the correct edge for this prediction.
This would make mechanistic explanations testable at the model level.

Design now; run post-V2. Not part of the preregistered V2 experiment.

---

## 12. Calibration

Continue Phase A-2 calibration protocol:
- Evaluation metrics: ECE (15 bins), Brier score, reliability curve
- Calibration method: temperature scaling
- Fit temperature parameter on validation set only
- Never fit or tune calibration on test set

---

## 13. Model Complexity Limit

With 1,705 drugs and ~191,000 training pairs per seed, avoid oversized models.

Guidelines:
- Embedding dimensions: max 128 per modality
- GNN layers (if used): max 3
- MLP hidden layers: max 3
- Total parameters: target < 1M (primary V2: ~853K)
- If V2 substantially outperforms GINE, run parameter-matched control at ~550K

Regularisation:
- Dropout on rho MLPs and pair decoder
- Weight decay (AdamW) on all parameters
- LayerNorm after fusion
- Early stopping on drug-disjoint validation AUPRC (patience = 30 epochs)

---

## 14. Validation-First Hyperparameter Selection

- All hyperparameter selection uses drug-disjoint validation AUPRC only
- Never inspect test AUPRC during tuning
- Grid is preregistered (see configs/v2_preregistered.yaml)
- After selecting configuration from grid (3-seed sweep), freeze it
- Final evaluation runs all 5 seeds once with the frozen configuration
- No re-tuning based on test observation

---

## 15. Implementation Steps

### Step 1: Biology shuffle (before any training)

```
scripts/create_biology_shuffle.py
  Input:  data/mechanism_v1/drug_protein_edges.parquet
  Output: data/mechanism_v1/drug_protein_edges_shuffled.parquet
  Method: per-drug uniform protein sampling, preserving degree distribution
```

Freeze the shuffled file. Do not regenerate.

### Step 2: Non-GNN biological baselines

```
scripts/train_bio_baseline.py
  Models: biological_degree_RF, BIO_RF, BIO_MLP
  Split: drug-disjoint, all 5 seeds
```

### Step 3: BIO-GINE model

```
src/models/bio_gine.py
  - DeepSetsEncoder (protein level)
  - DeepSetsEncoder (pathway level)
  - FusionLayer
  - SymmetricPairDecoder
```

### Step 4: Evidence ablation runs (M1 -> M4)

```
scripts/train_v2.py --ablation M1
scripts/train_v2.py --ablation M2
scripts/train_v2.py --ablation M3
scripts/train_v2.py --ablation M4   # primary
```

### Step 5: Shortcut control runs

```
scripts/train_v2.py --aggregation sum         # CONTROL C
scripts/train_v2.py --shuffled_bio            # CONTROL F
```

### Step 6: Linear probe

```
scripts/probe_bio_embeddings.py
  Input:  trained V2 M4 checkpoint
  Output: R^2(bio_emb -> ddi_degree) for train/val/test drugs
```

### Step 7: Statistical testing and reporting

```
scripts/v2_statistics.py
  Input:  AUPRC per model per seed per split
  Output: paired t-tests, Cohen's d, bootstrap CIs, comparison table
```
