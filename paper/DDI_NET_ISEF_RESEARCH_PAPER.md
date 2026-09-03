# Biologically Grounded Drug Representations as Transferable Context for Drug–Drug Interaction Prediction in Previously Unseen Drugs

**A preregistered study with degree-preserving falsification controls**

Regeneron ISEF — Computational Biology & Bioinformatics

*Frozen scientific state: git tag `v2-final-github-safe-2026-09-03`, commit
`92c481eeaba8faff991ced850e1c4de418ea31b0` (snapshot of frozen commit
`4657c256ee5e0157f529ebae41e96e0dc4dd9a3e`). Every number in this manuscript was
generated from that tag by `paper/build_tables.py` and checked by
`paper/audit_consistency.py`.*

---

## ABSTRACT

Patients taking several medicines at once can experience drug–drug interactions
(DDIs), in which one drug changes the effect or handling of another. Because the
number of possible drug pairs grows quadratically with the number of drugs,
computational screening is attractive — but its usefulness depends entirely on
whether a model still works for a drug it has never seen. Many DDI benchmarks
split data at the level of *pairs*, which allows the same drug to appear in both
training and test pairs. A model can then score highly by recognising familiar
drugs and their known interaction neighbourhoods, a form of context that does not
exist for a genuinely new compound.

We asked whether biologically grounded representations — the proteins a drug is
annotated against and the pathways those proteins belong to — can supply
transferable context in place of that missing interaction neighbourhood, and
whether any resulting improvement reflects biological *identity* rather than the
simpler fact that well-studied drugs carry more annotations. We built BIO-GINE, a
model combining a GINE encoder over molecular graphs with permutation-invariant
Deep Sets encoders over each drug's protein and pathway annotations, fused into a
symmetric pair decoder. Evaluation used a fixed drug-disjoint split (1,195 train /
255 validation / 255 test drugs), degree-matched negatives, hyperparameters chosen
on validation across 96 runs, and a test set opened once.

On 84,690 held-out drug-disjoint pairs, BIO-GINE reached 0.8117 ± 0.0097 AUPRC
across five seeds, against 0.7784 ± 0.0059 for an aligned molecular-only model
(paired Δ = +0.0333, Holm-adjusted *p* = 1.98 × 10⁻⁴). On the S3 subset, in which
*both* drugs have zero interaction adjacency in the training graph, BIO-GINE
reached 0.7372 ± 0.0153 while an aligned model with a DDI-network branch fell to
0.6198 ± 0.0278 (Δ = +0.1175, Holm *p* = 6.56 × 10⁻⁴). Two shortcut controls
argue against an annotation-count explanation: rewiring which specific proteins
each drug is annotated against, while preserving both degree sequences exactly,
reduced performance to 0.6923 ± 0.0054 (Δ = +0.1195, Holm *p* = 1.83 × 10⁻⁴), and
a random forest on annotation counts alone reached only 0.6504 ± 0.0006
(Δ = +0.1613, Holm *p* = 1.67 × 10⁻⁵). An exploratory analysis testing whether
the gain concentrates in pathway-covered pairs was *not* supported in the
predicted direction (Δ = −0.0233, *p* = 0.157).

Under this experimental setting, biological identity carried predictive
information that survived removal of the interaction neighbourhood. The evidence
ladder was non-monotonic, and the preregistered primary configuration was not the
best-performing variant. These are research predictions on a curated
1,705-drug subset; the system is not clinically validated.

**Word count: 331.**

---

# 1. INTRODUCTION

## 1.1 Drug–drug interactions as a biological problem

When two drugs are taken together, one can alter what the other does. The
mechanisms are varied. One drug may inhibit or induce an enzyme that metabolises
the other, changing how quickly it is cleared. One may compete for a transporter
that moves the other across a membrane. Two drugs may act on the same target, or
on different proteins that participate in the same biological pathway, so that
their effects add or oppose. These are pharmacological categories, not a single
phenomenon, and this variety matters for what follows: a model that predicts "an
interaction is documented" is not identifying a mechanism.

The practical problem is combinatorial. With *n* drugs there are *n*(*n*−1)/2
pairs, and laboratory or clinical characterisation of every pair is impossible.
Documented interaction databases are therefore incomplete by construction, and
the gap grows fastest for newly approved compounds, which have had the least time
to accumulate reports.

## 1.2 Computational prediction of DDIs

Computational work on DDI prediction falls into a few families. **Structure-based**
methods represent each drug by its chemistry and learn a function of the two
representations; DeepDDI [ryu2018deepddi] predicts 86 DrugBank interaction types
from structural similarity profiles, and SSI-DDI [nyamabo2021ssiddi] models
interactions between substructures of the two molecular graphs.
**Network-based** methods treat the known interactions themselves as a graph and
predict missing edges. **Multimodal** methods add biological entities: Decagon
[zitnik2018decagon] builds a graph of drugs, proteins and side effects and
predicts which polypharmacy side effect a pair will show, demonstrating that
protein information improves prediction over a drug-graph-only model.

## 1.3 The generalization and leakage problem

These families differ in an important way that reported accuracy can hide.

Consider splitting a set of documented interaction *pairs* at random into
training and test sets. Aspirin might appear in 400 training pairs and 100 test
pairs. A model evaluated this way is asked: *given that you have seen aspirin
interact with 400 drugs, does it also interact with this one?* That is a
reasonable question, and network-based methods answer it well — a drug's position
in the interaction graph is highly informative about further edges.

It is not, however, the question posed by a newly approved drug, for which the
count of known interactions is zero. Under a random pair-level split, the same
drug appears on both sides, and information about it flows from training into
test. Kapoor and Narayanan [kapoor2023leakage] catalogue this class of problem
across 17 scientific fields, affecting 294 papers: a split that does not respect
the unit of generalisation the paper claims to address yields performance
estimates that do not transfer.

The fix is to split by **drug**, not by pair. Every test drug is then absent from
training entirely. This is strictly harder, and it changes which sources of
information remain available.

## 1.4 Biological context as transferable information

Under a drug-disjoint split, a transductive interaction-graph branch has nothing
to work with for a test drug, because that drug has no training edges. Molecular
structure, by contrast, transfers: a molecule's atoms and bonds are properties of
the compound itself, computable for any structure.

But structure alone omits a great deal. Two molecules with quite different
scaffolds may inhibit the same cytochrome P450 enzyme; two similar molecules may
not. What a drug *does* biologically — the proteins it targets, the enzymes that
metabolise it, the transporters that move it, the pathways those proteins sit in —
is exactly the information a pharmacologist would use, and it is recorded in
curated databases: DrugBank [wishart2018drugbank], ChEMBL [mendez2019chembl],
Reactome [gillespie2022reactome].

Crucially, this information is a property of the drug, not of its position in the
interaction graph. It is therefore *available* for a drug with zero known
interactions — which is what makes it a candidate substitute for the missing
neighbourhood.

There is an obvious way this could go wrong, and it is the reason for most of
this paper's design. Curated annotations are not a neutral measurement of
biology; they are a record of what has been studied. A drug approved in 1960 and
prescribed to millions has more annotations than one approved last year, and it
also appears in more documented interactions. A model given annotation data could
appear to use biology while actually reading a proxy for **annotation
popularity**. Any claim that biology helps must be defended against that
alternative.

EmerGNN [zhang2023emergnn] addresses the same cold-start motivation, propagating
along paths through a biomedical network to reach emerging drugs. Our approach is
deliberately more restrictive — a per-drug set representation with no propagation —
because restricting the information source is what makes the shortcut controls
interpretable.

## 1.5 Research question and contributions

> **Can biologically grounded protein- and pathway-level representations improve
> drug–drug interaction prediction under drug-disjoint generalization, and does
> the improvement reflect biological identity rather than simple
> annotation-degree shortcuts?**

Contributions:

1. **BIO-GINE**, combining a molecular GINE encoder with Deep Sets encoders over
   per-drug protein and pathway annotation sets, fused through a symmetric pair
   decoder (Section 3.11).
2. **A drug-disjoint evaluation** reporting both the pooled test set and the S3
   subset in which both drugs are unseen (Section 3.9, 4.1, 4.3).
3. **Falsification controls for the annotation-popularity explanation** — a
   degree-preserving biological-identity shuffle, an annotation-count-only
   baseline, and an aggregation control (Sections 3.13, 4.4–4.6).
4. **A preregistered protocol** with hypotheses, effect-size thresholds and
   falsification criteria fixed before any run, Holm correction across all five
   hypotheses, and one unsupported exploratory result reported as such
   (Sections 3.14, 3.20, 4.8).
5. **Honest reporting of a non-monotonic ablation ladder** in which the
   preregistered primary model is not the best test performer (Section 4.7).

---

# 2. RELATED WORK

## 2.1 Molecular approaches
DeepDDI [ryu2018deepddi] established that structural information alone predicts
DrugBank interaction types at high reported accuracy. SSI-DDI
[nyamabo2021ssiddi] operates directly on molecular graphs and decomposes the
prediction into substructure-level interactions. Both are stronger molecular
models than the encoder used here. Our molecular branch is intentionally modest
and held fixed between conditions, because its role is to be a *constant* against
which the biological branch is measured, not to be optimised.

## 2.2 DDI graph and knowledge graph approaches
Treating known interactions as a graph and predicting missing edges is effective
when test drugs are already in the graph. Decagon [zitnik2018decagon] extends
this to a multimodal graph including proteins and side effects. The dependence on
graph position is the property this study examines: it is an asset under
pair-level evaluation and unavailable under drug-disjoint evaluation.

## 2.3 Multimodal biological approaches
Decagon's use of drug–protein and protein–protein edges is the direct ancestor of
our biological branch. The difference is architectural and evaluative rather than
conceptual: we encode each drug's annotations as a *set* belonging to that drug,
with no message passing between drugs, and we evaluate on drugs absent from
training.

## 2.4 Cold-start and unseen-drug generalization
EmerGNN [zhang2023emergnn] explicitly targets emerging drugs with little known
interaction data, using a flow-based GNN over a biomedical network, and reports
strong results at larger scale than this study. It is the most closely related
prior work.

## 2.5 Gap addressed by this work
Across the methods above, biological information is used and reported to help.
What we did not find in this literature is a control that **preserves annotation
degree exactly while destroying annotation identity**. Without such a control, a
reported biological gain is compatible with the model having learned annotation
popularity. This study is organised around supplying that control, and around
reporting what happens when it is applied. Our reading of the cited work is
summarised in `NOVELTY_MATRIX.md`; no conclusion here depends on the absence of
prior work.

---

# 3. MATERIALS AND METHODS

## 3.1 Study design

The study was preregistered in `configs/v2_preregistered.yaml` before any model
was trained. That file fixes the hypotheses (H-V2-1 … H-V2-5), the statistical
tests, the alpha level, minimum effect sizes where applicable, the falsification
criteria (F1 … F5), and the evidence ladder. Two amendments exist as separate
documents that do not modify the original: a training-budget amendment
(Section 3.15) and a control-implementation note (Section 3.13). The test set was
evaluated once, after hyperparameters were frozen.

## 3.2 DDI dataset

Labels come from Therapeutics Data Commons [huang2021tdc]
(`tdc.multi_pred.DDI(name='DrugBank')`, PyTDC 1.1.15, CC BY-NC 4.0), which
redistributes DrugBank interaction records [wishart2018drugbank]. The frozen
universe, identifier `DDI_MECH_1705_V1`, contains **1,705 drugs and 191,392
positive interaction pairs**. One drug, `DB11630`, was excluded because its SMILES
string in the export contains invalid ring-closure syntax that RDKit cannot parse;
this removed 10 pairs (0.0052% of the corpus) and is performed by a visible,
mandatory step rather than a silent filter.

Two properties of this dataset shape everything downstream.

**The label column is not binary.** The source `Y` field is an interaction *type*,
an integer from 1 to 86 [ryu2018deepddi]. Every row is a documented interaction.
We collapse the types to a single binary "documented interaction" label; type
prediction is not attempted.

**There are no negative examples at all.** The source contains only documented
interactions. Approximately 86.8% of the pair space is *unlabelled*, not
negative. Every negative used in this study is generated by us, which makes the
sampling scheme a first-class methodological choice (Section 3.10) rather than a
preprocessing detail.

The 1,705 drugs are a TDC-selected subset of DrugBank, which contains on the
order of 15,000 drugs and over 1.4 million interaction assertions. **This subset
must not be treated as a representative sample of DrugBank.**

## 3.3 Drug identity mapping

DrugBank accession numbers are the canonical drug identifier throughout. Proteins
are identified by UniProt accession [uniprot2023], which is what allows DrugBank
and ChEMBL protein references to be joined and what maps proteins to Reactome
pathways.

One property of the export deserves explicit statement because it affects what a
demonstration of this system can display: the `name` column is a byte-identical
copy of `drugbank_id`. Verified directly, `(drugs.name == drugs.drugbank_id)` is
true for all rows. **No human-readable drug names exist anywhere in this
dataset.** Any join that appears to match on drug names would in fact be matching
accession numbers against accession numbers.

## 3.4 Molecular representation

Each drug's SMILES string is parsed with RDKit into an atom-level graph. Atoms
carry **50** features (element one-hot, degree, formal charge, hybridisation,
aromaticity, ring membership, hydrogen count); bonds carry **11** (bond type,
stereochemistry, conjugation, ring membership).

The encoder is GINE — the Graph Isomorphism Network [xu2019gin] in the
edge-feature form of Hu et al. [hu2020pretraining] — with **3 message-passing
layers, hidden dimension 64, and sum pooling with normalisation**, dropout 0.1.

These are the values in the code, and they differ from the architecture plan
document, which reads "GINE (4-layer, d=128, same as Phase A-2)". The two halves
of that phrase contradict each other: the earlier phase froze `hidden_dim=64,
mol_layers=3`. The implementation follows the *measured* earlier configuration,
because the M0 baseline in the evidence ladder is that earlier frozen result,
reused rather than retrained. Had the literal 4/128 been used, the molecular
branch would have changed at the same time as the biological branch was added,
and every M-minus-M0 difference would confound the two. The deviation is recorded
in the source file.

## 3.5 Protein and biological evidence

Drug–protein relationships come from **146,743 edge rows** spanning four relation
types: **target** (139,988), **enzyme** (3,972), **transporter** (2,185) and
**carrier** (598). Each edge also carries an evidence type recording *how* the
relationship is known:

| Evidence type | Source | Ladder rung |
|---|---|---|
| `DOCUMENTED_DATABASE_RELATION` | DrugBank curation | M1 |
| `CURATED_MOA` | ChEMBL curated mechanism of action | M2 |
| `EXPERIMENTAL_BIOACTIVITY` | ChEMBL measured activity | M3 |

**Duplicate collapse.** The same (drug, protein) relationship can be asserted by
several source rows. Edges are reduced to distinct
(drug, protein, relation_type, evidence_type) quadruples, taking 146,743 rows to
**94,088 distinct triples**. Collapsing on identity rather than counting rows
prevents a heavily re-asserted relationship from dominating a set-mean.

## 3.6 Reactome pathway integration

Proteins are mapped to Reactome pathways [gillespie2022reactome] through
UniProt-to-Reactome mappings, giving **14,576 protein–pathway edges** over a
vocabulary of **1,969 pathways**. Composing drug→protein with protein→pathway
yields each drug's pathway set. Only membership is used: no reaction topology,
direction or stoichiometry enters the model.

## 3.7 Biological feature graph construction

Under the full M4 policy the representation contains **94,088 drug–protein set
elements** and **284,203 drug–pathway set elements** over a protein embedding
vocabulary of **2,893** and a pathway vocabulary of **1,969**.

The protein vocabulary is built from the accessions that actually appear in
drug–protein edges. Of those 2,893 accessions, only **2,778 have a descriptive
row** in the protein table; the remaining 115 are referenced by edges but carry
no name, gene symbol or EC number. They are still usable as embedding indices —
identity is all the encoder needs — but they cannot be described to a reader.

Coverage is high but not complete: **1,638 of 1,705 drugs (96.07%)** have at
least one protein annotation and **1,614 (94.66%)** at least one pathway
annotation. The distribution is heavily skewed — the median drug has 19 proteins
and 52 pathways, the maximum 627 and 1,078. This skew is precisely the annotation
popularity the controls in Section 3.13 are designed to test.

## 3.8 Leakage prevention

Three guarantees, each enforced in code rather than by convention:

1. **No interaction edges in the biological representation.** The biology loader
   never opens `ddi_positive_labels.parquet` and never reads a split assignment.
   The number of DDI edges available to the biological branch is **zero**.
2. **No test drug in training.** The split is over drugs; a leakage auditor
   verifies that the training and test drug sets are disjoint.
3. **Negative-sampling degree comes from training pairs only** (Section 3.10).

## 3.9 Dataset splitting

Drugs — not pairs — are partitioned. For the frozen seed-0 drug-disjoint split:
**1,195 training, 255 validation, 255 test drugs**.

Test pairs are then classified by how many endpoints are unseen:

| Setting | Definition |
|---|---|
| **S1** | both drugs seen in training |
| **S2** | exactly one drug unseen |
| **S3** | **both** drugs unseen |

Under a drug-level split S1 is empty by construction. The **pooled** drug-disjoint
test set contains **84,690 pairs** at prevalence 0.5; the **S3** subset contains
**7,758 pairs**, also at prevalence 0.5.

A scaffold-disjoint scheme (Bemis–Murcko frameworks [bemis1996scaffold]) is
implemented and its assignments exist in the frozen data, but **no
scaffold-disjoint evaluation was performed in the final study** (Section 6).

## 3.10 Negative sampling

Because the source has no negatives, they are generated. Two schemes are
implemented; the study uses **degree-matched** sampling throughout.

Under **uniform** sampling, endpoints are drawn with equal probability. This is
common in the literature and leaves a degree shortcut: hub drugs are
over-represented among positives but appear among negatives only in proportion to
their share of the drug list, so a model can score well above chance by asking
"are both of these drugs promiscuous?" without examining chemistry at all.

Under **degree-matched** sampling, endpoints are drawn in proportion to
interaction degree, so the marginal degree distribution of negatives matches that
of positives and the shortcut carries little information. This makes the task
harder and the reported numbers lower, which is the intent.

**Degree is computed from training pairs only.** Weighting by degree in the full
graph would let the sampler consult test edges, and information about which drugs
are promiscuous in the test set would enter the training distribution.

A scope invariant is enforced: negatives for a bucket are drawn from the same
drug scope as that bucket's positives, so that S3 negatives are pairs of two
unseen drugs.

## 3.11 BIO-GINE architecture

```
   molecular graph ──► GINE encoder (3 layers, d=64, sum pool) ──┐
                                                                 │
   protein set     ──► Deep Sets encoder (embed + relation       │
   {(protein, relation, evidence)}   + evidence, MEAN) ──────────┤──► fusion
                                                                 │    Linear→LayerNorm
   pathway set     ──► Deep Sets encoder (embed, MEAN) ──────────┘    (d=128)
                                                                          │
                                                                    drug vector
                       drug A ─┐                                          │
                               ├─► symmetric pair decoder ──► P(interaction)
                       drug B ─┘
```

**Biological encoder.** A drug's annotations are an unordered set of varying size,
so the encoder is a Deep Sets architecture [zaheer2017deepsets]: embed each
element, apply a shared φ network, aggregate over the set, apply ρ. Each protein
element is the sum of a protein embedding (vocabulary 2,893, dimension 128), a
relation-type embedding (dimension 16) and an evidence-type embedding (dimension
16), so that a target, an enzyme and a transporter are distinguishable, as are a
curated and an experimental assertion. Pathway elements carry a pathway embedding
only.

**Mean aggregation is a deliberate commitment, not a default.** Sum aggregation is
strictly more expressive for multisets [xu2019gin] — and that is exactly the
problem: a sum over a set is a count in disguise, which is the shortcut this study
exists to exclude. Mean normalises by set size, so a drug with 4 annotations and
one with 400 differ in *content* rather than in magnitude. Set size is not thereby
erased — it re-enters through which proteins are common enough to be annotated
often — but it is no longer the path of least resistance. Sum is retained as
CONTROL C (Section 3.13).

**Missing annotations.** Drugs with an empty set receive a learned MISSING token
rather than a zero vector, because zero is a point in embedding space that a real
drug could occupy, and "no annotation" must not be representable as "annotated
with nothing in particular".

**Symmetric pair decoder.** Interaction is an unordered relation, so the model
must satisfy *f*(A, B) = *f*(B, A) exactly rather than approximately. Every pair
term is commutative: the sum of the two drug vectors, their absolute difference,
their elementwise product, and the elementwise minimum and maximum of the two
modality-presence masks. Concatenating [mask_A | mask_B] in argument order would
break symmetry precisely for pairs where one drug has biology and the other does
not. The resulting **388-dimensional** pair vector passes through
388 → 256 → 128 → 1 with ReLU and dropout.

**Total parameters: 1,122,804** under the selected configuration (molecular
encoder 54,275; protein embedding 370,304; protein encoder 140,160; pathway
embedding 252,032; pathway encoder 131,968; fusion 41,344; pair MLP 132,609;
relation and evidence embeddings 112).

## 3.12 Baselines

All baselines use the identical split, identical negatives and identical seeds,
so comparisons are paired.

| Baseline | Description |
|---|---|
| **Aligned molecular GINE (M0)** | The same molecular encoder with the biological branch switched off. Isolates the contribution of biology. |
| **Aligned Dual (GINE + DDI network)** | Adds a branch that aggregates over the known interaction graph. Represents the transductive family. |
| **BIO-RF** | Non-neural: random forest over ECFP4 fingerprints [rogers2010ecfp] (radius 2, 2,048 bits) plus biological components. Tests whether a neural encoder is needed. |

## 3.13 Biological controls

**CONTROL A — biological-degree-only random forest.** Features are *only* scalar
counts of a drug's annotations. It has access to annotation popularity and to
nothing else. If it matches BIO-GINE, the biological branch is a counter.

**CONTROL C — SUM aggregation.** The identical model trained with sum instead of
mean. Preregistered interpretation, fixed in advance: *if SUM wins, counting was
the signal.* It is never selected on validation; it is reported as a control.

**CONTROL E — linear probe.** Ridge regression from the frozen biological
embedding to a drug's training-interaction degree, to test whether the embedding
still encodes popularity. Its held-out arm proved non-identifiable (Section 4.10).

**CONTROL F — degree-preserving biological shuffle.** This is the central control.
Which specific proteins each drug is annotated against is randomised while the
*amount* of annotation is held exactly fixed, using a stratified degree-preserving
bipartite double-edge swap (seed 20260829, 150 swap attempts per edge). Swapping
occurs within 25 strata defined by the sorted set of relation|evidence
combinations of each (drug, protein) pair, and the unit of shuffling is the
(drug, protein) pair rather than the individual assertion row, so that **both the
drug degree sequence and the protein degree sequence are preserved exactly**.
89,049 edges underwent 2,487,716 successful swaps at an 18.62% acceptance rate.
A model is then trained from scratch on the shuffled biology.

Two honesty notes. First, this deviates from the preregistration, which specified
uniform resampling of |P(d)| proteins per drug; the implemented swap preserves
*both* degree sequences and the evidence stratum, which makes the control
**stricter** than preregistered, and the deviation is documented with that
direction stated. Second, **the shuffle is not perfect: 2,255 edges (2.53%)
were retained unchanged**. Protein→pathway edges are not shuffled either; a
drug's pathway context changes only through its randomised proteins. Both facts
temper the control and are carried into the limitations.

## 3.14 Hyperparameter selection

A grid of **32 configurations** (bio_dim ∈ {64, 128}, dropout_bio ∈ {0.1, 0.3},
dropout_pair ∈ {0.1, 0.2}, learning rate ∈ {1e-3, 3e-4}, batch size ∈ {256, 512})
was run at **3 seeds each**, for **96 validation runs**. Selection used **mean
validation AUPRC only**; the test set was not consulted. The winning
configuration, frozen as `e8ece7c41ae09e5f`, is bio_dim 128, dropout_bio 0.1,
dropout_pair 0.1, learning rate 1e-3, batch size 512, with validation AUPRC
0.816207 ± 0.007187. The frozen configuration file records in writing that the
test set was not used for selection.

## 3.15 Training protocol

The budget is denominated in **optimizer steps, not epochs**: 21,960 steps, with
validation every 366 steps (60 checks) and early stopping after 30 checks without
improvement. This matters because an epoch-denominated cap would give batch size
256 twice the parameter updates of batch size 512, and per-epoch validation would
give batch size 512 twice the checkpoint-selection opportunities. Step
denomination removes both confounds by construction: every configuration receives
21,960 updates and exactly 60 checks.

**Five seeds** were run for the final model. Seeds vary parameter initialisation,
batch ordering and negative sampling; they do **not** create independent datasets.
The reported standard deviation therefore estimates sensitivity to training
stochasticity on one fixed split, not sampling variability over drug universes.
This is a real limit on what the error bars mean.

## 3.16 Evaluation metrics

The primary metric is **AUPRC**, preregistered, because it is sensitive to
performance on the positive class [saito2015prc]. AUROC, Brier score and expected
calibration error are reported alongside. Evaluation sets are constructed at
prevalence 0.5, so the class-imbalance argument for AUPRC is weaker here than in
its usual setting; AUPRC remains primary because it was preregistered.

## 3.17 Statistical analysis

Each comparison is **paired by seed**: seed *k* of one model against seed *k* of
the other, trained on the same split with the same negatives, differing only in
the factor under test. We report the mean ± sample standard deviation (ddof = 1)
across five seeds, the paired mean difference, its 95% confidence interval from
the *t* distribution with 4 degrees of freedom, the paired *t* statistic, the raw
two-sided *p*-value, the Holm-adjusted *p*-value and Cohen's *dz*.

**Holm–Bonferroni correction** [holm1979] controls the family-wise error rate: with
five tests, the probability that at least one nominally significant result is a
false positive is much higher than 5%. The procedure sorts the raw *p*-values,
multiplies the smallest by 5, the next by 4, and so on, taking a running maximum
to keep the sequence monotonic. **The family is all five preregistered
hypotheses, including the exploratory H5.** Including it makes the correction
*stricter* for the four confirmatory hypotheses than a family of four would be.

For H-V2-1 and H-V2-3 a bootstrap over test pairs (1,000 resamples, RNG seed
20260829) was also computed on seed 0.

With five seeds the *t* test rests on an approximate normality assumption that
cannot be checked at that sample size. The effect sizes here are large enough
that this is unlikely to change any conclusion, but it is a genuine limitation.

## 3.18 Calibration

A model can rank well while its probabilities are badly scaled. **Temperature
scaling** [guo2017calibration] divides the logits by a single scalar *T*, fitted
by minimising negative log-likelihood **on validation predictions only** (93,610
validation pairs) and then applied unchanged to the frozen test predictions. One
temperature was fitted per seed. Because dividing by a positive constant is
monotonic, it cannot change the ordering of examples, so ranking metrics must be
unchanged — a property used below as an internal consistency check.

## 3.19 Interpretability

All interpretability is **post-hoc on the frozen seed-0 checkpoint**
(`bd45f84e3c1b2c33`). Three analyses:

- **Leave-one-protein-out**: remove one protein annotation from one drug, re-run
  inference, record the change in predicted probability (4,031 ablations).
- **Leave-one-pathway-out**: the same for pathways (13,192 ablations).
- **Modality contribution**: remove an entire modality (molecular, protein or
  pathway) for all 84,690 test pairs.

The quantity measured is **model reliance**: how much the frozen model's output
moves when an input is withheld. It is not a pharmacological mechanism, and no
statement of the form "this protein causes this interaction" is supportable from
it.

## 3.20 Falsification criteria

Five criteria were fixed in advance, each stating a result that would count as
evidence *against* the hypothesis:

| ID | Preregistered condition |
|---|---|
| F1 | H-V2-1 fails: M4 does not improve over molecular GINE on drug-disjoint |
| F2 | H-V2-3 fails: shuffled biology is not significantly worse than true |
| F3 | H-V2-4 fails: the degree-count RF matches M4 |
| F4 | Linear probe R² > 0.6 **and** H-V2-1 Cohen's *d* < 0.2 |
| F5 | M4 improves on random_pair but **not** on drug-disjoint or scaffold-disjoint |

H-V2-1 and H-V2-3 additionally carried `requires_both: true` — significance *and*
an effect size above *d* = 0.5 were required, so a statistically detectable but
negligible effect would not have counted as support.

---

# 4. RESULTS

Results are stated first and interpreted separately. All values are mean ± sample
standard deviation over five seeds on the frozen test set, evaluated once.

## 4.1 Main drug-disjoint performance

**Result.** On 84,690 pooled drug-disjoint test pairs, BIO-GINE M4 achieved
**0.8117 ± 0.0097 AUPRC**. Per-seed values were 0.8235, 0.8121, 0.8070, 0.7984
and 0.8176. Context from Table 3: aligned molecular GINE 0.7784 ± 0.0059; BIO-RF
0.7396 ± 0.0017; aligned Dual 0.7147 ± 0.0067; biological-degree-only RF
0.6504 ± 0.0006; M4 with shuffled biology 0.6923 ± 0.0054.

**Interpretation.** The primary model outperforms every baseline and control on
this view. The number is meaningful only relative to that spread — an AUPRC of
0.81 at prevalence 0.5 is not interpretable in isolation.

## 4.2 Effect of biological information — H-V2-1

**Result.** Paired per-seed differences between M4 and the aligned molecular GINE
were +0.0397, +0.0319, +0.0298, +0.0295, +0.0355, giving a mean
**Δ = +0.0333 AUPRC**, 95% CI [0.0279, 0.0386], paired *t*(4) = 17.27, raw
*p* = 6.60 × 10⁻⁵, **Holm-adjusted *p* = 1.98 × 10⁻⁴**, Cohen's *dz* = 7.72. The
bootstrap on seed 0 gave Δ = 0.0397, CI [0.0356, 0.0433], with 0 of 1,000
resamples at or below zero.

**Interpretation.** This supports H-V2-1. Both preregistered conditions are met:
*p* < 0.05 and *d* > 0.5. Adding biological annotation to an otherwise identical
molecular model improved held-out performance on drugs absent from training. The
difference is small in absolute terms (about 3.3 AUPRC points) but highly
consistent — all five seeds moved the same way, which is what drives the large
*dz*. **F1 is not triggered.**

## 4.3 Generalization without DDI neighbours — S3 and H-V2-2

**Result.** On the 7,758 S3 pairs, where both drugs have zero interaction
adjacency in the training graph:

| Model | S3 AUPRC |
|---|---|
| BIO-GINE M4 | **0.7372 ± 0.0153** |
| Aligned molecular GINE | 0.7145 ± 0.0065 |
| Aligned Dual (GINE + DDI network) | 0.6198 ± 0.0278 |
| M4 shuffled biology | 0.6305 ± 0.0105 |

M4 versus aligned Dual on S3: **Δ = +0.1175**, 95% CI [0.0891, 0.1459],
*t*(4) = 11.49, raw *p* = 3.28 × 10⁻⁴, **Holm *p* = 6.56 × 10⁻⁴**, *dz* = 5.14.

**Interpretation.** This supports H-V2-2. The pattern across the two views is the
informative part. Moving from pooled to S3, BIO-GINE falls by 0.075 AUPRC and the
molecular model by 0.064, while the Dual model falls by 0.095 — from 0.7147 to
0.6198 — and its seed-to-seed variability more than quadruples (0.0067 → 0.0278).
The DDI-network branch is being asked to aggregate over a neighbourhood that does
not exist, and it degrades most where that neighbourhood is most completely
absent.

S3 is an **experimental generalization condition**, not a model of clinical
novelty. It says: both of these drugs were withheld from training. It does not
say that these are new drugs in clinical use, and results here should not be read
as a statement about newly approved medicines.

## 4.4 Biological identity shuffle — H-V2-3

**Result.** Training the identical architecture on degree-preserving shuffled
biology gave 0.6923 ± 0.0054 pooled, against 0.8117 ± 0.0097 with true biology:
**Δ = +0.1195**, 95% CI [0.1020, 0.1370], *t*(4) = 18.95, raw
*p* = 4.56 × 10⁻⁵, **Holm *p* = 1.83 × 10⁻⁴**, *dz* = 8.48. Bootstrap on seed 0:
Δ = 0.1322, CI [0.1274, 0.1367], 0 of 1,000 resamples at or below zero. On S3 the
shuffled model reached 0.6305 ± 0.0105 against 0.7372 ± 0.0153.

**Interpretation.** This supports H-V2-3 and both preregistered conditions.
Because the shuffle preserves each drug's annotation count and each protein's
annotation count exactly, a model that improved only by counting annotations
should have been almost unaffected. Performance instead fell by roughly 0.12
AUPRC — a larger drop than the entire gain over the molecular baseline. This
**supports** the conclusion that *which* proteins a drug is annotated against
carries information beyond *how many*, and **argues against** the
annotation-popularity explanation. **F2 is not triggered.**

Two limits on this control. The shuffle left 2.53% of edges unchanged, so it is
not a perfect randomisation. And the shuffled model still reached 0.6923, well
above the 0.6504 of the count-only control — residual structure survives the
shuffle, through the retained edges, through preserved degree sequences, and
through the unshuffled protein→pathway layer. This result does **not** show that
the model learned true pharmacological mechanisms; it shows that biological
identity carried information the model used.

## 4.5 Annotation-degree shortcut control — H-V2-4

**Result.** The biological-degree-only random forest reached 0.6504 ± 0.0006
pooled. Against M4: **Δ = +0.1613**, 95% CI [0.1490, 0.1735], *t*(4) = 36.54, raw
*p* = 3.35 × 10⁻⁶, **Holm *p* = 1.67 × 10⁻⁵**, *dz* = 16.34.

**Interpretation.** This supports H-V2-4. Scalar annotation counts alone reach
0.6504, which is well above the 0.5 of a random ranker — annotation popularity
*is* genuinely predictive, and a study that omitted this control could have
mistaken part of that for biological insight. But it falls 0.16 AUPRC short of
the full model, so counts alone do not explain BIO-GINE's performance. Its
extremely small standard deviation (0.0006) reflects that a random forest on
eight scalar features is nearly deterministic. **F3 is not triggered.**

## 4.6 The BIO-RF control

**Result.** BIO-RF — a random forest over ECFP4 fingerprints plus biological
components — reached 0.7396 ± 0.0017 pooled, below BIO-GINE (0.8117) but above
the aligned Dual model (0.7147).

**Interpretation.** A non-neural model with access to structure and biology is a
strong baseline, and it exceeds a neural model that relies on interaction-graph
context. This is worth stating plainly because it constrains the claim: the
advantage reported here is not "deep learning beats classical methods", it is
"per-drug biological information transfers where interaction-graph context does
not". The 0.072 gap between BIO-RF and BIO-GINE is the part attributable to the
learned encoder.

## 4.7 Evidence-source ablations — non-monotonic

**Result.** Table 5, both test views:

| Variant | Pooled AUPRC | S3 AUPRC |
|---|---|---|
| M0 — no biology | 0.7784 ± 0.0059 | 0.7145 ± 0.0065 |
| M1 — DrugBank only | 0.8186 ± 0.0017 | 0.7468 ± 0.0078 |
| M2 — + ChEMBL curated MoA | **0.8269 ± 0.0060** | **0.7594 ± 0.0114** |
| M3 — + ChEMBL bioactivity | 0.8177 ± 0.0042 | 0.7466 ± 0.0053 |
| **M4 — + Reactome pathways (primary)** | 0.8117 ± 0.0097 | 0.7372 ± 0.0153 |
| M4 SUM (CONTROL C) | 0.8265 ± 0.0092 | 0.7485 ± 0.0127 |
| M4 shuffled (CONTROL F) | 0.6923 ± 0.0054 | 0.6305 ± 0.0105 |

**Interpretation.** Two facts here run against the study's own expectations and
are reported without softening.

**The ladder is not monotonic, and the primary model is the weakest of M1–M4.**
Every biological variant beats the no-biology baseline, so the headline
conclusion is unaffected. But performance peaks at M2 and then *declines* as
more evidence is added: adding ChEMBL experimental bioactivity (M2 → M3) cost
0.009 AUPRC pooled, and adding Reactome pathways (M3 → M4) cost a further 0.006,
with the same ordering on S3. M4 was fixed as primary by the validation protocol
before the test set was opened; it is the preregistered model, not the best test
performer. Constructing a rising narrative from M0 to M4 would misrepresent the
data.

Additional evidence is not automatically additional signal. Experimental
bioactivity is noisier than curated mechanism-of-action assignment, and pathway
membership is highly redundant — the median drug maps to 52 pathways, many
nested — so both can dilute a set-mean rather than sharpen it. We did not
preregister a prediction about the *shape* of the ladder, so this reading is
post-hoc and should be treated as a hypothesis for future work.

**CONTROL C outperformed the primary model.** M4 with SUM aggregation reached
0.8265 pooled and 0.7485 on S3, above MEAN's 0.8117 and 0.7372. The
preregistration fixed the interpretation in advance: *if SUM wins, counting was
the signal.* Taken alone this is evidence that set size carries usable
information the mean-aggregated model discards. It has to be read alongside
CONTROL F, which shows that destroying identity at fixed degree costs 0.12 AUPRC.
The consistent reading is that **both** annotation count and annotation identity
carry signal, and mean aggregation trades away some of the former to make the
latter testable. That was the design intent, and the cost of the choice is now
measured: about 0.015 AUPRC pooled. This does not overturn H-V2-3, whose
comparison holds aggregation fixed, but it is a genuine qualification of the
architectural argument for MEAN and we do not present the choice as vindicated.

## 4.8 Exploratory pathway-coverage analysis — H-V2-5

**Result.** Pairs were divided by whether both drugs have Reactome pathway
coverage (79,163 covered vs 5,527 uncovered pairs per seed). The M4-minus-M0 gain
was +0.0317 on covered pairs and +0.0550 on uncovered pairs, giving a contrast of
**Δ = −0.0233**, 95% CI [−0.0606, +0.0139], *t*(4) = −1.74, *p* = 0.157, Holm
*p* = 0.157, *dz* = −0.78.

**Interpretation.** H-V2-5 was preregistered as **exploratory**, with
`alpha: exploratory` and an explicit instruction to label it exploratory in all
reports. The predicted direction — a larger gain on pathway-covered pairs — was
**not supported**: the point estimate runs the other way, and the confidence
interval includes zero.

This is an **exploratory direction unsupported**, not a failed confirmatory
hypothesis. No claim in this paper depended on it. Reported plainly, it also
sits consistently with Section 4.7: if the pathway level had been carrying
substantial independent signal, one would expect both a larger gain where
pathways are present and an improvement from M3 to M4. Neither occurred. The
uncovered subgroup is small (5,527 pairs) and the confidence interval is
correspondingly wide, so this analysis has limited power and should not be read
as evidence that pathways are useless.

## 4.9 Calibration

**Result.** Temperature scaling, fitted only on validation predictions:

| Seed | T | ECE₁₅ raw → scaled | Brier raw → scaled |
|---|---|---|---|
| 0 | 7.200 | 0.1911 → 0.0539 | 0.2128 → 0.1732 |
| 1 | 5.881 | 0.1960 → 0.0623 | 0.2197 → 0.1790 |
| 2 | 6.265 | 0.1925 → 0.0479 | 0.2216 → 0.1812 |
| 3 | 7.584 | 0.2147 → 0.0563 | 0.2340 → 0.1843 |
| 4 | 10.119 | 0.2085 → 0.0611 | 0.2220 → 0.1752 |

All five fits converged. AUPRC changed only in the seventh decimal place — seed 0
went from 0.8235342392 to 0.8235341519.

**Interpretation.** Expected calibration error fell by roughly a factor of three
and the Brier score improved consistently, so the raw model was substantially
overconfident and a single scalar per seed corrects most of it. The temperatures
are large (5.9 to 10.1), indicating strong overconfidence in the raw logits.

Ranking is unchanged, and necessarily so: dividing logits by a positive constant
is monotonic and cannot reorder examples. The seventh-decimal movement is
floating-point noise, and its absence would have indicated a bug. **Calibration
improves the interpretability of the probability, not the quality of the
ranking.** A calibrated probability from this model remains a research
prediction, not a clinically validated risk estimate.

## 4.10 Model-reliance analysis

**Result.** On the frozen seed-0 checkpoint, removing an entire modality from all
84,690 test pairs changed the predicted probability by these mean absolute
amounts: **protein 0.313**, **molecular 0.192**, **pathway 0.107** (medians
0.150, 0.011 and 0.004). Signed means, where a positive value means removal
lowered the prediction, were +0.067, +0.092 and −0.016.

Single-annotation ablations behave very differently. Across 4,031
leave-one-protein-out ablations the mean absolute change was 0.000274 with a
median of exactly zero — yet the maximum was 0.985, a case where removing one
protein annotation from one drug moved the prediction from 1.000 to 0.015.
Across 13,192 leave-one-pathway-out ablations the maximum change was 0.00078.

**Interpretation.** Three observations, all statements about model reliance.

First, the model relies most on the protein modality, then the molecular
modality, then pathways — consistent with the ablation ladder, where the pathway
rung did not improve held-out performance.

Second, reliance on individual proteins is extremely concentrated. Almost every
single-protein removal changes nothing, while a small number are decisive. A
mean of 0.000274 against a maximum of 0.985 describes a model that has learned
sparse dependence on particular annotations rather than diffuse dependence on
all of them.

Third, no individual pathway matters much: the largest single-pathway effect
across 13,192 ablations was 0.00078, while removing the whole pathway modality
moved predictions by 0.107 on average. Pathway information is used, but
redundantly — no single pathway is load-bearing because many encode overlapping
membership.

**These perturbations indicate which biological inputs influence the model's
predictions. They do not establish causal pharmacological mechanisms.** A protein
whose removal changes a prediction is a protein the model relied on, which may
reflect a real pharmacological relationship, a correlate of one, or an artefact of
annotation practice. Distinguishing these requires experiments this study did not
perform.

### CONTROL E and its identifiability failure

**Result.** The preregistered probe fits Ridge regression from the frozen
biological embedding to a drug's positive training-interaction degree. On the
1,195 training drugs it achieved R² = 0.5430, with target variance 18,934 (range
0–646). On the 255 held-out test drugs the target had **minimum 0, maximum 0,
variance exactly 0.0** — every test drug has training-interaction degree zero, by
the definition of the drug-disjoint split.

**Interpretation.** R² is a ratio of explained to total variance. With zero total
variance the quantity is **undefined**, not zero. The `r2_test: 0.0` recorded in
the frozen output is a placeholder produced by the implementation, and the
accompanying Pearson and Spearman correlations are `NaN` — the signature of a
constant target.

The correct statement is: **the held-out diagnostic was not identifiable, because
the target had zero variance under the strict drug-disjoint definition.** It
would be wrong to report this as evidence that the embedding does not encode
degree. The design contained a latent contradiction — a strict drug-disjoint split
guarantees the probe's target is constant on the held-out set — which was not
noticed until the result was produced. The training R² of 0.543 is reported
descriptively: the embedding does carry substantial information about training
degree among training drugs, which is precisely why CONTROL F rather than
CONTROL E is the load-bearing control here.

**F4 cannot trigger.** Its condition is a conjunction: probe R² > 0.6 **and**
H-V2-1 Cohen's *d* < 0.2. The second conjunct fails decisively (*dz* = 7.72), so
the criterion is unsatisfiable regardless of the probe. The frozen output records
`f4_probe_component_r2_gt_0_6: false`.

## 4.11 Falsification summary

| ID | Outcome |
|---|---|
| F1 | **Not triggered** — H-V2-1 supported, Δ +0.0333, Holm *p* 1.98 × 10⁻⁴ |
| F2 | **Not triggered** — shuffled biology worse by 0.1195, Holm *p* 1.83 × 10⁻⁴ |
| F3 | **Not triggered** — count-only RF worse by 0.1613, Holm *p* 1.67 × 10⁻⁵ |
| F4 | **Cannot trigger** — effect-size conjunct fails; probe arm non-identifiable |
| F5 | **Drug-disjoint component not triggered; not fully resolved** — scaffold-disjoint was not evaluated in the final study |
| joint (F1 ∧ F2) | Not triggered |

F5 deserves care. Its condition requires that M4 improve on random_pair but *not*
on drug-disjoint or scaffold-disjoint. M4 clearly improves on drug-disjoint, so
the conjunction is already false. But because no scaffold-disjoint evaluation was
run, we cannot report the criterion as fully examined, and we do not claim to
have ruled it out in its entirety.

---

# 5. DISCUSSION

## 5.1 Main finding

Under this experimental setting, biologically grounded per-drug representations
provided predictive information that transferred to drugs held out of training,
and that information was not explained by annotation counts. The improvement over
an aligned molecular model is modest (+0.0333 AUPRC) but consistent across all
five seeds; the margin over controls designed to preserve annotation degree while
destroying identity is much larger (+0.1195).

The finding worth carrying away is not the headline number. It is the
*relationship* between the model and its controls: a system with access to
biological identity outperformed one with the same annotation quantity but
scrambled identity by more than it outperformed a model with no biology at all.

## 5.2 Why transductive DDI context transfers poorly

The Dual model, which adds a branch over the known interaction graph, was the
weakest neural model on the pooled view (0.7147) and fell furthest on S3 (0.6198),
with seed variability quadrupling. This is structural rather than incidental. A
neighbourhood aggregation computes a function of a node's neighbours; for an S3
test drug that set is empty, so the branch contributes a constant, and whatever
capacity was devoted to it is wasted. Its usefulness under pair-level evaluation
and its failure under drug-disjoint evaluation are the same fact seen from two
directions — which is precisely why the choice of split determines what a reported
number means.

## 5.3 What the shuffle experiment tells us

CONTROL F is the strongest evidence in the study, because it isolates identity
from quantity. Preserving both degree sequences exactly while randomising which
proteins go with which drugs removed 0.12 AUPRC — more than the entire benefit of
adding biology in the first place.

What this supports: the model used information about *which* proteins a drug is
associated with. What it does not support: that the model learned pharmacological
mechanisms. A model could rely on protein identity because those proteins mark
drug classes, because they correlate with therapeutic area, or because annotation
practice differs systematically across protein families. All of these are
identity-dependent and none is a mechanism. The 2.53% retained edges and the
unshuffled pathway layer further mean this is a strong control, not an airtight
one.

## 5.4 Biological identity versus annotation popularity

The count-only control reaching 0.6504 is a result in its own right: annotation
popularity alone predicts documented interactions well above chance. This is
unsurprising on reflection — a drug studied enough to have many annotations has
also been studied enough for its interactions to be documented — and it is exactly
the confound that makes an uncontrolled biological gain uninterpretable. Our gain
survives this control with a wide margin, but the control's own performance is a
caution for the field.

## 5.5 What the ablations suggest

The non-monotonic ladder and the SUM result together complicate the simple
story. Performance peaked at M2 (DrugBank plus curated mechanism of action), and
both additional evidence layers cost held-out accuracy. Meanwhile the SUM control
outperformed the primary MEAN model on both views.

We take three lessons. First, evidence quality matters more than evidence
quantity: curated mechanism-of-action assignments helped, while experimental
bioactivity — noisier, threshold-dependent, assay-heterogeneous — did not.
Second, redundancy has a cost under mean aggregation: 52 median pathways per drug,
many hierarchically nested, dilute rather than sharpen a mean. Third, and least
comfortable for our own design, the MEAN-versus-SUM decision has a measurable
price of about 0.015 AUPRC. We chose MEAN so that the counting shortcut would be
excluded by construction and therefore testable; the ablation shows that choice
cost accuracy. We think that trade was correct for a study whose purpose is to
determine *why* a model works, but it is a trade, and presenting it otherwise
would be dishonest.

All three readings are post-hoc. None was preregistered.

## 5.6 Interpretation of S3

S3 is the most demanding condition here and the one closest in spirit to the
motivating problem, but the distance remains large. It is an experimental
construct: pairs of drugs that this particular split withheld. Those drugs are
not new — they are well-documented compounds whose records were hidden from the
model. A genuinely new compound differs in ways S3 does not capture: its
annotations are sparse and provisional rather than merely withheld, and its
chemistry may fall outside the training distribution. Performance on S3 is
therefore an upper bound on what should be expected for a truly novel drug, not
an estimate of it.

## 5.7 Meaning of the unsupported H5 result

H5 asked whether the benefit of biology concentrates where pathway annotation is
present. It does not, in these data; the point estimate runs the other way,
though the interval is wide and includes zero.

We report it for two reasons. The first is that it was preregistered, and a
preregistration that only publishes its successes provides no protection at all.
The second is that it is informative in combination: H5's null and the M3 → M4
decline and the tiny single-pathway reliance values all point the same way — the
pathway level contributed little in this study. Any one of those alone would be
weak; together they form a consistent picture that a future design should act on.

## 5.8 Scientific significance

The architecture is an assembly of published components: GINE
[xu2019gin, hu2020pretraining], Deep Sets [zaheer2017deepsets], temperature
scaling [guo2017calibration]. We do not claim novelty for them.

What we believe is contributed is the **control design**. Reports that biological
information improves DDI prediction are common; a control that holds annotation
degree exactly fixed while destroying annotation identity, so that the popularity
explanation can be excluded rather than assumed away, is what this study adds. The
result is a claim narrower than "biology helps" and considerably more defensible:
*biological identity, not merely annotation quantity, carried information that
transferred to unseen drugs in this dataset.*

The secondary contribution is methodological. Hypotheses and falsification
criteria were fixed before running; the test set was opened once; the primary
model turned out not to be the best test performer and is reported as such; one
hypothesis is unsupported; one control outperformed the primary model; and one
planned diagnostic was found to be non-identifiable and is reported as undefined
rather than as a convenient zero. A study that reports only its successes cannot
be distinguished from one that searched until something worked.

---

# 6. LIMITATIONS

**Incomplete biological annotation.** 3.93% of drugs have no protein annotation
and 5.34% none for pathways. For these the model falls back to a learned MISSING
token — the architecture handles the case, but no biological information is
available.

**Database and literature bias.** Annotations record what has been studied.
Older, widely prescribed drugs are better annotated, and the same bias plausibly
affects which interactions are documented. Controls A and F address the
*count* dimension of this bias; they do not address the possibility that
annotation *identity* is itself distributed non-randomly with respect to how well
studied a drug is.

**Annotation popularity is genuinely predictive.** The count-only control reached
0.6504 AUPRC. Popularity is a real signal in these data, and any study using
curated annotations without such a control risks attributing it to biology.

**Negative sampling assumptions.** The source contains no negatives; all were
generated. About 86.8% of the pair space is unlabelled rather than negative, so
some sampled negatives are almost certainly undocumented true interactions. This
depresses apparent performance and the magnitude is unknown. Degree-matched
sampling was chosen to suppress the degree shortcut, but it is an assumption, and
a different scheme defines a different task.

**DDI dataset limitations.** 1,705 drugs is a TDC-selected subset of DrugBank's
~15,000 drugs and ~1.4M assertions, chosen by upstream criteria unknown to us. It
must not be treated as a representative sample. Labels are binary presence of a
documented interaction, discarding all 86 type distinctions and any notion of
severity, direction or clinical importance.

**S3 remains below pooled performance.** 0.7372 versus 0.8117. Removing
interaction-graph adjacency costs real accuracy; biology narrows the gap without
closing it.

**Five seeds on one split.** Seeds vary initialisation, batch order and negative
sampling — not the drug universe or the split. The reported standard deviations
estimate training stochasticity on one fixed partition, not sampling variability
over datasets. With *n* = 5 the *t*-test's normality assumption cannot be checked.

**The ablation ladder is non-monotonic and the primary model is not the best.**
M2 and the SUM control both exceed M4 on both views. M4 was fixed by the
validation protocol before test evaluation; explanations for the shape of the
ladder are post-hoc.

**CONTROL F is not a perfect randomisation.** 2.53% of edges were retained
unchanged, and protein→pathway edges were not shuffled at all.

**CONTROL E is non-identifiable on held-out drugs.** Training-interaction degree
is zero for every drug-disjoint test drug, so held-out R² is undefined. Only the
training-side R² (0.543) is interpretable, and only descriptively.

**Scaffold-disjoint evaluation was not performed in the final study.** Falsification
criterion F5 is therefore only partially resolved. Drug-disjoint splitting does
not prevent a test drug from sharing a Bemis–Murcko scaffold with a training drug,
so the reported generalization is to unseen *drugs*, not to unseen *chemotypes*.

**No prospective or external validation.** All results come from one frozen
retrospective dataset. No external DDI database was used to check whether the
conclusions transfer.

**No clinical validation.** This system has not been evaluated against clinical
outcomes in any form. Nothing here supports a clinical claim.

**No patient-level features.** Age, sex, dose, renal function, hepatic function,
genotype and comedication are not inputs. The model has no representation of a
patient. It cannot make age-specific predictions, and no result here applies
differently to children, adults or elderly people, because no such variable exists
in the model.

**No dose or pharmacokinetic modelling.** Metabolism appears only indirectly,
through enzyme, transporter and pathway annotations. This is not a
pharmacokinetic simulator, a dose–response model, or a physiologically based
model.

**Interpretability is not causality.** Perturbation analyses measure model
reliance. They do not establish that a protein mediates an interaction.

**Single-architecture study.** One architecture family under one preregistered
protocol. Whether the conclusion generalises to other biological encoders is
untested.

---

# 7. FUTURE WORK

**External and prospective validation.** Evaluate the frozen model on an
independent interaction resource, and prospectively on interactions documented
after the data snapshot — the closest available approximation to a real
unseen-drug test.

**Scaffold-disjoint evaluation.** Complete the F5 arm. Scaffold assignments
already exist in the frozen data, so this requires evaluation rather than new
data collection, and it directly tests whether the gain survives holding out whole
chemotypes.

**Redesign CONTROL E.** The probe target must have variance on the evaluation
set. Predicting degree among *training* drugs with a held-out subset, or using a
target defined for unseen drugs, would restore identifiability.

**Explain the non-monotonic ladder.** Test directly whether evidence quality
(curated vs experimental) or set-size dilution drives the M2 → M4 decline, for
instance by weighting elements by evidence type or by pruning redundant nested
pathways. The M2-versus-M4 gap is a concrete, testable target.

**Revisit aggregation.** CONTROL C's advantage suggests a representation carrying
both normalised content and an explicit, separately controlled size feature might
outperform either alone — while keeping the counting channel testable.

**Error analysis and biological case studies.** Characterise which pairs the model
fails on, and examine high-reliance protein annotations against known
pharmacology — as hypothesis generation, not validation.

**Patient context.** Age, dose, sex, renal and hepatic function and
pharmacokinetic parameters would be required for any clinically oriented
successor. These are absent here and would demand different data, a different
model and a different validation standard. They are listed as future directions,
not as capabilities.

---

# 8. CONCLUSION

We asked whether biologically grounded drug representations can supply
transferable context for drug–drug interaction prediction when the known
interaction neighbourhood is unavailable, and whether any improvement reflects
biological identity rather than annotation counts.

Under a preregistered drug-disjoint protocol with degree-matched negatives and a
test set opened once, BIO-GINE reached 0.8117 ± 0.0097 AUPRC against 0.7784 ±
0.0059 for an aligned molecular model (Holm *p* = 1.98 × 10⁻⁴). Where both drugs
were unseen, it reached 0.7372 ± 0.0153 while a model relying on
interaction-graph context fell to 0.6198 ± 0.0278 (Holm *p* = 6.56 × 10⁻⁴).
Preserving annotation degree exactly while randomising annotation identity cost
0.1195 AUPRC (Holm *p* = 1.83 × 10⁻⁴), and a count-only baseline fell 0.1613
short (Holm *p* = 1.67 × 10⁻⁵). An exploratory prediction that the gain would
concentrate in pathway-covered pairs was not supported.

Under this experimental setting, biological identity carried predictive
information that transferred to unseen drugs and was not explained by annotation
quantity. The evidence ladder was non-monotonic, the preregistered primary
configuration was not the best-performing variant, and one planned diagnostic was
non-identifiable — all reported here rather than omitted.

These are research predictions on a curated 1,705-drug subset. The system is not
clinically validated, incorporates no patient-level information, and its
interpretability analyses identify model reliance rather than pharmacological
mechanism.

---

# REFERENCES

Full BibTeX in `paper/references.bib`. Every entry was verified against the
publisher record or an authoritative index; unverifiable references were excluded.

1. Bemis, G. W. & Murcko, M. A. (1996). The Properties of Known Drugs. 1. Molecular Frameworks. *J. Med. Chem.* 39(15):2887–2893. doi:10.1021/jm9602928
2. Gillespie, M. *et al.* (2022). The reactome pathway knowledgebase 2022. *Nucleic Acids Res.* 50(D1):D687–D692. doi:10.1093/nar/gkab1028
3. Guo, C., Pleiss, G., Sun, Y. & Weinberger, K. Q. (2017). On Calibration of Modern Neural Networks. *ICML*, PMLR 70:1321–1330.
4. Holm, S. (1979). A Simple Sequentially Rejective Multiple Test Procedure. *Scand. J. Statist.* 6(2):65–70.
5. Hu, W. *et al.* (2020). Strategies for Pre-training Graph Neural Networks. *ICLR*.
6. Huang, K. *et al.* (2021). Therapeutics Data Commons: Machine Learning Datasets and Tasks for Drug Discovery and Development. *NeurIPS Datasets and Benchmarks Track*. arXiv:2102.09548
7. Kapoor, S. & Narayanan, A. (2023). Leakage and the reproducibility crisis in machine-learning-based science. *Patterns* 4(9):100804. doi:10.1016/j.patter.2023.100804
8. Mendez, D. *et al.* (2019). ChEMBL: towards direct deposition of bioassay data. *Nucleic Acids Res.* 47(D1):D930–D940. doi:10.1093/nar/gky1075
9. Nyamabo, A. K., Yu, H. & Shi, J.-Y. (2021). SSI–DDI: substructure–substructure interactions for drug–drug interaction prediction. *Brief. Bioinform.* 22(6):bbab133. doi:10.1093/bib/bbab133
10. Rogers, D. & Hahn, M. (2010). Extended-Connectivity Fingerprints. *J. Chem. Inf. Model.* 50(5):742–754. doi:10.1021/ci100050t
11. Ryu, J. Y., Kim, H. U. & Lee, S. Y. (2018). Deep learning improves prediction of drug–drug and drug–food interactions. *PNAS* 115(18). doi:10.1073/pnas.1803294115
12. Saito, T. & Rehmsmeier, M. (2015). The Precision-Recall Plot Is More Informative than the ROC Plot When Evaluating Binary Classifiers on Imbalanced Datasets. *PLOS ONE* 10(3):e0118432. doi:10.1371/journal.pone.0118432
13. The UniProt Consortium (2023). UniProt: the Universal Protein Knowledgebase in 2023. *Nucleic Acids Res.* 51(D1):D523–D531. doi:10.1093/nar/gkac1052
14. Wishart, D. S. *et al.* (2018). DrugBank 5.0: a major update to the DrugBank database for 2018. *Nucleic Acids Res.* 46(D1):D1074–D1082. doi:10.1093/nar/gkx1037
15. Xu, K., Hu, W., Leskovec, J. & Jegelka, S. (2019). How Powerful are Graph Neural Networks? *ICLR*. arXiv:1810.00826
16. Zaheer, M. *et al.* (2017). Deep Sets. *NeurIPS 30*, 3391–3401.
17. Zhang, Y. *et al.* (2023). Emerging drug interaction prediction enabled by a flow-based graph neural network with biomedical network. *Nat. Comput. Sci.* 3:1023–1033. doi:10.1038/s43588-023-00558-4
18. Zitnik, M., Agrawal, M. & Leskovec, J. (2018). Modeling polypharmacy side effects with graph convolutional networks. *Bioinformatics* 34(13):i457–i466. doi:10.1093/bioinformatics/bty294

---

# SUPPLEMENTARY INFORMATION OVERVIEW

| File | Contents |
|---|---|
| `paper/PAPER_FACTS.md` | Every claim with its frozen source file and preregistered/post-hoc status |
| `paper/tables/table1_dataset_and_biological_graph.csv` | Dataset and biological graph characteristics |
| `paper/tables/table2_architecture_and_configuration.csv` | Architecture, parameter counts, training configuration |
| `paper/tables/table3_main_model_comparison.csv` | Main comparison, both test views |
| `paper/tables/table4_hypotheses.csv` | H1–H5 with CIs, Holm-adjusted *p*, effect sizes |
| `paper/tables/table5_ablation_ladder.csv` | Evidence ladder M0–M4 plus CONTROL C and F |
| `paper/tables/table6_calibration.csv` | Per-seed temperatures, Brier, ECE |
| `paper/tables/table7_threats_to_validity.csv` | Threats to validity and mitigations |
| `paper/FIGURES.md` | Figure specifications and captions |
| `paper/CLAIM_EVIDENCE_MATRIX.csv` | Each manuscript claim mapped to its artifact |
| `paper/NOVELTY_MATRIX.md` | Feature-by-feature comparison against prior work |
| `paper/LITERATURE_NOTES.md` | Per-reference notes and the claim each supports |
| `paper/DEFENSE_GUIDE.md` | Plain-language explanation of each section |
| `paper/JUDGE_QUESTIONS.md` | 34 anticipated questions with answers |
| `paper/build_tables.py` | Regenerates every table from the frozen tag |
| `paper/audit_consistency.py` | Verifies every number in this manuscript against frozen sources |

**Reproducibility.** All artifacts are read from git tag
`v2-final-github-safe-2026-09-03`. `paper/build_tables.py` reads through
`git show` rather than the working tree, so no edited file can enter the tables.
`paper/audit_consistency.py` re-extracts every numeric claim from this manuscript
and compares it against the frozen values.
