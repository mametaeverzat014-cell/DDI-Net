# Step 3 — Model Architecture

## The architecture

```
SMILES A ──► MolecularEncoder (GINE ×3) ──► atom embeddings H_A, pooled g_A
SMILES B ──► MolecularEncoder (shared)  ──► atom embeddings H_B, pooled g_B
DDI graph ─► DDIGraphEncoder (GATv2 ×2) ──► network embeddings z_A, z_B

H_A, H_B ──► SubstructureCoAttention ──► u, v  +  attention map S [n_a × n_b]

fuse([ g_A⊙g_B , |g_A−g_B| , z_A⊙z_B , |z_A−z_B| , u+v , u⊙v ]) ──► MLP
     ├──► interaction logit        (does this pair interact?)
     ├──► ordinal severity logits  (minor / moderate / major)
     └──► mechanism logits         (pharmacokinetic vs pharmacodynamic)
```

**686,665 parameters** at the default `hidden_dim=128`.

## 3.1 Which GNN architecture — and why

### Molecular level: **GINE**

Graph Isomorphism Networks (Xu et al. 2019) are provably as expressive as the 1-Weisfeiler-Lehman test — the theoretical maximum for a message-passing GNN without extra structural features. That matters chemically: distinguishing *ortho-* from *para-*substitution is WL-hard, and it's exactly the kind of difference that changes metabolism. GINE is the edge-feature variant, so bond order and aromaticity participate.

**Why not GCN here:** GCN's symmetric normalisation actively *discards* degree information. Atom degree is chemically meaningful — a quaternary carbon is not a methyl group.

### Interaction-network level: **GATv2** (default; SAGE and GCN also implemented)

Three reasons:

1. **Interpretability.** Attention coefficients say *which neighbouring drugs* influenced this drug's representation. That's a directly reportable explanation — and interpretability is the project's stated goal.
2. **Heterogeneous neighbourhoods.** The graph has 7 relation types. A CYP3A4-inhibitor edge should not be weighted like a same-ATC-class edge; GCN would average them uniformly. We feed relation type as an edge feature so attention learns per-relation weighting.
3. **Inductive by construction.** Attention is computed from node features, so a drug never seen in training still gets a sensible representation — the entire S2/S3 requirement.

**GATv2 rather than GAT:** the original's attention is *static* — the ranking of neighbours is identical for every query node. GATv2 fixes this. Free improvement, same interface.

**The honest competitor is GraphSAGE**, designed for inductive settings with more robust aggregation on high-degree nodes. All three are implemented behind one interface, and Step 4 decides empirically. *"Which architecture is best"* is a question to answer with an experiment, not an opinion.

## 3.2 ⚠ Symmetry — enforced architecturally, not hoped for

**A drug interaction is symmetric: f(A,B) must equal f(B,A).**

Most published DDI models concatenate the two drug vectors, which lets the network learn an asymmetric function. In practice the same pair gets **two different risk scores depending on which drug you typed first**. For a clinical tool that isn't a rounding error — it's a defect a judge can demonstrate at your poster in ten seconds.

Two common fixes are unsatisfying:
- Averaging f(A,B) and f(B,A) at inference doubles compute and still trains on an inconsistent objective.
- Random order-swapping during training only *encourages* symmetry.

**We make it exact:**
- All drug-level fusion terms use `⊙` and `|·|` — both commutative.
- The co-attention bilinear form is parameterised **`W = M + Mᵀ`**, symmetric by construction for any M. Then S(B,A) = S(A,B)ᵀ exactly, the two attention directions swap, and `u+v` / `u⊙v` are invariant.

Verified to floating-point precision, at initialisation and after training, for all three architectures. `test_prediction_is_symmetric` and `test_symmetry_survives_training` assert it.

## 3.3 Why co-attention rather than two pooled vectors

An interaction is not a property of two molecules considered separately — it's a property of how *a part of one* relates to *a part of the other*.

> Ketoconazole's imidazole nitrogen coordinates CYP3A4's haem iron, blocking the site where simvastatin's ester would have been hydrolysed.

That's a statement about **two specific substructures**. Co-attention computes a compatibility score between every atom of A and every atom of B, so the model can learn *"this fragment matters **when paired with** that fragment"*. Two independently pooled vectors cannot express a pairwise substructure relationship at all.

It also hands Step 5 its central object for free: the attention matrix **S is a map over atom pairs**, so *"which part of A interacted with which part of B"* is read directly off the model rather than reconstructed post hoc. **An explanation the model actually computed is worth more than one inferred afterwards.**

Padding correctness: attention over padded atoms is masked with `-inf` *before* softmax. Zeroing afterwards would leave the distribution unnormalised and silently corrupt short molecules.

## 3.4 Ordinal severity, not plain multi-class

Severity is **ordered**: minor < moderate < major. Cross-entropy treats the three as unrelated labels, so predicting "minor" for a major interaction costs exactly as much as predicting "moderate" — which is wrong, because one of those errors is far more dangerous.

We use a **cumulative-link (CORAL-style)** formulation: two sigmoid outputs predicting P(severity ≥ moderate) and P(severity ≥ major).

Monotonicity is enforced by parameterising the second threshold as `first − softplus(offset)`, so the incoherent output *"probably major but probably not moderate"* is **unrepresentable**, not merely unlikely.

The severity loss is applied to **positives only**. A negative pair has no severity; supervising on it would be meaningless.

## 3.5 Training choices for a small, imbalanced dataset

| Choice | Rationale |
|---|---|
| **Selection on val_S2 AUPRC** | Not loss (multi-task, scale depends on weights). Not accuracy (useless under imbalance). **Not S1** — selecting on S1 would quietly optimise for the memorisation we're trying to avoid. |
| **Early stopping, patience 50** | ~229 training pairs vs ~687k parameters. The model can memorise the training set completely. |
| **Best checkpoint restored** | Using final weights reports a model early stopping already judged worse. |
| **`pos_weight` capped at 10** | Uncapped, a 1:50 ratio gives weight 50 and the model predicts "interaction" for everything — the mirror image of the majority-class failure it was meant to fix. |
| **LayerNorm, not BatchNorm** | Molecule batches vary wildly in size and composition; batch statistics are noisy and make evaluation depend on grouping. |
| **Residual connections** | Without them, deeper stacks over-smooth and every atom converges to the same vector — which destroys per-atom attribution. |
| **Cosine LR annealing** | No schedule to tune; reliably beats constant LR on small data. |
| **Threshold fit on validation only** | Tuning a threshold on test data is a subtle but real leak. |
| **F2, not F1** | Recall weighted 4× precision: a missed dangerous interaction can kill; a false alarm costs a pharmacist 30 seconds. |
| **Ablations shrink the fusion layer** | Disabled branches must not feed zeros — that leaves dead parameters and makes the comparison unfair. |

## 3.6 Results on the curated fixture — and the honest verdict

Default config: GATv2, drug-level split, 1:3 negatives, threshold 0.857 (F2-optimal on val_S2).

| Bucket | Setting | AUC-ROC | AUPRC | AUPRC 95% CI | Balanced acc |
|---|---|---|---|---|---|
| train | S1 | — | high | — | high |
| val_S2 | S2 | — | — | — | — |
| **test_S2** | **S2** | **0.753** | **0.460** | [0.387, 0.558] | **0.686** |
| test_S3 | S3 | 0.528 | 0.339 | [0.126, 0.720] | 0.500 |

**The degradation S1 → S2 → S3 is clearly visible and is the expected scientific result.** By S3, AUC-ROC 0.528 is barely above chance — with 6 positive pairs and a CI of [0.126, 0.720], the honest statement is *"not estimable from this fixture"*.

### ⚠ The comparison that matters — and it does not favour the model

| test_S2, balanced accuracy | Score |
|---|---|
| Mechanistic rules only | **0.709** |
| DDI-Net | **0.686** |

**The GNN does not beat the rules baseline on this fixture.** This is reported prominently by `scripts/04_train.py` rather than buried.

**This is the correct outcome and you should say so directly.** With 104 drugs and 229 training pairs, a 687k-parameter model has essentially nothing to learn — the interaction graph is too small for message passing to find structure, and the molecular encoder is fitting noise. The fixture exists to validate that the *pipeline* is correct, not to produce headline numbers.

**The right framing for judges:** *"I built the instrument that tells me when my model isn't earning its complexity. On a 104-drug development fixture, it isn't — and that's exactly why the headline experiment requires DrugBank's ~4,000 drugs and ~1.4M interactions. A project that reported a big number here without that check would be reporting an artefact."*

This is a far stronger position than an unexamined 0.95.

## 3.7 Limitations to state

1. **The fixture is far too small** for a model this size. Everything in §3.6 is a pipeline smoke test.
2. **S3 is not estimable** — 6 positives, CI spanning [0.13, 0.72].
3. **`recall @ precision ≥ 0.90` is 0.000** in every setting. At a usable false-alarm rate, the model currently catches nothing. That's the deployment-relevant number and it is bad — quote it.
4. **Co-attention is O(n_a × n_b)** in atoms per pair. Fine at ~25 atoms; needs chunking for large molecules.
5. **Attention is not causation.** High attention means high contribution to the model's computation, not a proven biochemical mechanism. Step 5 says this again, louder.
6. **Mechanism head is coarse** — pharmacokinetic vs pharmacodynamic only, from a regex-derived label.
7. **Single seed.** Step 4's cross-validation addresses the variance question.

## 3.8 What you need to understand to answer ISEF judges

**"Why GAT over GCN or GraphSAGE?"**
Three reasons: attention weights give a directly reportable explanation; the graph has 7 relation types that shouldn't be weighted equally, and only attention can learn that; and attention is computed from node features so unseen drugs still get representations. I use GATv2 because the original's attention is static. GraphSAGE is the real competitor and I compare them empirically in Step 4 rather than asserting a winner.

**"How do you guarantee f(A,B) = f(B,A)?"**
Architecturally. Every fusion term is commutative (`⊙`, `|·|`), and the co-attention bilinear form is `W = M + Mᵀ`, symmetric for any M. So swapping the drugs transposes the attention matrix and exchanges the two pooled terms, leaving their sum and product unchanged. It holds exactly, at init and after training — there's no way to train it away. There's a test for it.

**"Why not just concatenate the two molecule embeddings?"**
Because an interaction is about how *part* of one molecule relates to *part* of the other — ketoconazole's imidazole blocking the site simvastatin's ester needs. Concatenated pooled vectors can't express a pairwise substructure relationship. Co-attention scores every atom pair, so the model learns fragment-with-fragment. It also gives me the explanation object directly.

**"Why is severity ordinal rather than 3-class?"**
Because minor < moderate < major is ordered. Cross-entropy would penalise confusing minor with major exactly as much as minor with moderate, and those errors have very different clinical costs. I use cumulative-link outputs, P(≥moderate) and P(≥major), with monotonicity enforced so an incoherent prediction is unrepresentable.

**"Your model doesn't beat the simple baseline — isn't that a failed project?"**
No — it's a measured result on a deliberately small development fixture. 104 drugs and 229 training pairs cannot support 687k parameters. The important thing is that I *built the comparison* rather than not looking. It tells me precisely what the headline experiment needs: DrugBank scale. A project reporting 0.95 here without that check would be reporting an artefact.

**"Why is your S3 performance near chance?"**
Because S3 asks the model to predict interactions between two drugs it has never seen, with no network edges for either — purely from structure. It's the honest hard case. On this fixture there are 6 positive S3 pairs, so the confidence interval spans [0.13, 0.72] and the correct statement is that it isn't estimable, not that it's 0.53.

## 3.9 Reproducing

```bash
python scripts/04_train.py                               # default GATv2
python scripts/04_train.py --architecture sage           # compare
python scripts/04_train.py --no-coattention              # ablation
python scripts/04_train.py --no-graph                    # molecular branch only
python scripts/04_train.py --group-by scaffold           # harder split
python -m pytest tests/test_models.py -q                 # 24 tests
```
