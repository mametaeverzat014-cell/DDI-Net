# NOVELTY_MATRIX.md

The purpose of this document is to make a *defensible* novelty claim, not a
promotional one. Where a component of DDI-Net already exists in the literature,
that is stated plainly. The claim we are prepared to defend is narrow and is
stated at the bottom.

## Comparison matrix

Legend: **Yes** = a central, reported feature · **Partial** = present but not
central, or in a weaker form · **No** = absent · **n/a** = not applicable.
Entries describe the cited papers as published; they are not judgements of
quality, and all four comparison systems are stronger than DDI-Net on axes that
DDI-Net does not attempt (scale, label granularity, molecular modelling).

| Axis | Decagon (2018) | DeepDDI (2018) | SSI-DDI (2021) | EmerGNN (2023) | **DDI-Net (this work)** |
|---|---|---|---|---|---|
| Molecular structure representation | No | Partial (structural similarity profiles) | **Yes** (substructure graphs) | Partial | **Yes** (GINE over atom graphs) |
| Known DDI-network context used | **Yes** (central) | No | No | **Yes** (central) | **No — deliberately excluded** |
| Protein / target information | **Yes** | No | No | **Yes** | **Yes** |
| Pathway-level information | No | No | No | Partial (biomedical network relations) | **Yes** (Reactome, explicit level) |
| Evidence-provenance typing of biological edges | No | n/a | n/a | Partial | **Yes** (3 evidence types, 4 relation types, as embeddings) |
| Unseen-drug (cold-start) evaluation | No | No | No | **Yes** (central) | **Yes** (central) |
| Drug-disjoint splitting | No | No | No | **Yes** | **Yes** |
| Both-drugs-unseen condition reported separately | No | No | No | Partial | **Yes** (S3, reported as its own view) |
| Degree-matched negative sampling | No | n/a | No | No | **Yes** |
| Shuffled-biological-identity control | No | No | No | No | **Yes** (CONTROL F) |
| Annotation-degree-only baseline | No | No | No | No | **Yes** (CONTROL A) |
| Aggregation-as-counter control | No | No | No | No | **Yes** (CONTROL C, SUM vs MEAN) |
| Embedding-encodes-degree probe | No | No | No | No | **Attempted** (CONTROL E, non-identifiable on held-out drugs) |
| Probability calibration reported | No | No | No | No | **Yes** (temperature scaling, validation-fitted) |
| Model-reliance / perturbation interpretation | Partial | No | **Yes** (substructure attention) | **Yes** (path weights) | **Yes** (leave-one-annotation-out) |
| Preregistered hypotheses with falsification criteria | No | No | No | No | **Yes** (H1–H5, F1–F5, fixed before running) |
| Multiple-testing correction across hypotheses | No | No | No | No | **Yes** (Holm over 5) |
| Seed-level uncertainty on every reported number | Partial | No | Partial | Partial | **Yes** (5 seeds, sample SD, paired tests) |

## What is *not* novel here — stated explicitly

These ideas exist in the literature and DDI-Net does not claim them:

1. **Using protein/target information for DDI prediction.** Decagon established
   this in 2018. DDI-Net's biological branch is a descendant of that idea.
2. **Cold-start / emerging-drug DDI prediction as a problem.** EmerGNN targets
   exactly this and does so at larger scale, with a biomedical network.
3. **Graph neural networks on molecular graphs.** GIN, GINE and SSI-DDI predate
   and outperform DDI-Net's molecular encoder, which is deliberately frozen at a
   modest configuration so it does not confound the biological comparison.
4. **Deep Sets for unordered inputs.** Zaheer et al. (2017), used as published.
5. **Temperature scaling for calibration.** Guo et al. (2017), used as published.
6. **Holm–Bonferroni correction.** Holm (1979), used as published.
7. **Drug-disjoint splitting.** Used by EmerGNN and others; DDI-Net did not
   invent it, though it does report the both-unseen subset separately.

## What we do claim

**The contribution is the control design, not the architecture.**

DDI-Net's architecture is an assembly of published components. Its distinctive
element is that it treats "biological information helps" as a hypothesis that
could be *wrong for an uninteresting reason*, and builds the experiment to catch
that reason.

Specifically, the concern is **annotation popularity**. Well-studied drugs
accumulate more database annotations, and they are also disproportionately
represented among documented interactions. A model given biological annotations
could therefore appear to use biology while actually reading a proxy for "how
much has this drug been studied". Every axis in the lower half of the matrix
exists to test that alternative explanation:

- **CONTROL A** asks whether eight scalar annotation counts alone reach the
  model's performance. They do not (0.650 vs 0.812).
- **CONTROL F** rewires which specific proteins each drug is annotated against
  while preserving both degree sequences exactly and the evidence stratum. If
  counting were the signal, performance should survive. It falls to 0.692.
- **CONTROL C** trains the identical model with SUM aggregation, which is a
  counter by construction, as a check on whether MEAN was doing anything.
- **CONTROL E** was designed to probe whether the learned embedding still
  linearly predicts interaction degree. It turned out to be non-identifiable on
  held-out drugs, and we report that rather than the placeholder value.

We are not aware of a published DDI method that reports a degree-preserving
biological-identity shuffle as a control. If one exists, this claim should be
narrowed accordingly — the matrix above is our reading of the cited papers, not
an exhaustive survey, and no claim here depends on the absence of prior work.

**Secondary contribution: methodological discipline as a reportable object.**
Hypotheses, falsification criteria and metric thresholds were fixed in
`configs/v2_preregistered.yaml` before any run; amendments are separate
documents that never rewrite the original; the test set was evaluated once; the
ablation ladder is reported non-monotonically with the primary model *not* the
best-performing variant; and one hypothesis (H5) is reported as unsupported.
A study that only reports what worked cannot be distinguished from one that
searched until something did.
