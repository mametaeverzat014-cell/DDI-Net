# FIGURES.md — specifications and captions

Figures marked **[frozen]** were produced by the frozen study and copied
unchanged into `paper/figures/`. Figures marked **[to render]** are specified
here but not yet rendered; the data behind each is already in `paper/tables/`,
so rendering requires plotting only, no new computation.

Every caption is written to be understood without the main text.

Two rules apply to all figures:

- **No truncated axes on performance comparisons.** AUPRC panels start at 0.5,
  the value of a random ranker at prevalence 0.5, not at the minimum bar height.
  Truncating to the data range visually multiplies small differences.
- **Uncertainty is always shown.** Every bar or point carries the sample
  standard deviation across the five seeds, or the individual seed values.

---

## Figure 1 — DDI-Net architecture **[to render]**

**Specification.** Schematic, left to right. Two identical drug columns feeding
one decoder. Each column: (a) molecular graph → GINE encoder, 3 layers, hidden
64, sum pooling; (b) protein set {(protein, relation, evidence)} → Deep Sets
encoder with mean aggregation; (c) pathway set → Deep Sets encoder with mean
aggregation. The three outputs concatenate into a fusion layer (Linear →
LayerNorm, dimension 128) producing one drug vector. The two drug vectors enter
the symmetric pair decoder, where the four commutative terms (sum, absolute
difference, elementwise product, min/max of modality masks) form a
388-dimensional vector, then 388 → 256 → 128 → 1 → sigmoid. Annotate the total
parameter count, 1,122,804. Mark clearly that no edge of the DDI graph enters
any branch.

**Caption.** *BIO-GINE architecture. Each drug is encoded three ways: its
molecular graph through a GINE network with edge features; the set of proteins
it is annotated against (as target, enzyme, transporter or carrier, each with
its evidence type) through a Deep Sets encoder; and the set of Reactome pathways
those proteins belong to, likewise. Mean rather than sum aggregation is used for
both sets so that set size does not dominate the representation — sum is
retained as a control. The three representations are fused into a single drug
vector. Because a drug interaction is an unordered relation, the pair decoder
uses only commutative combinations of the two drug vectors, making the model
exactly symmetric: f(A,B) = f(B,A). No information from the known drug
interaction graph enters any branch, which is what allows the model to be
evaluated on drugs absent from training. Total parameters: 1,122,804.*

---

## Figure 2 — Evaluation design **[to render]**

**Specification.** Three panels sharing a small illustrative drug set. Panel A,
*random pair split*: pairs assigned at random, with one drug highlighted
appearing in both training and test pairs — the leakage path drawn as an arrow.
Panel B, *drug-disjoint split*: drugs partitioned 1,195 / 255 / 255, so no test
drug appears in training. Panel C, *S3 subset*: the subset of drug-disjoint test
pairs in which both endpoints are test drugs, with each shown to have zero edges
into the training graph. Label pair counts: 84,690 pooled, 7,758 S3.

**Caption.** *Three ways to split drug interaction data, and why the choice
determines what a reported score means. (A) Splitting pairs at random lets the
same drug appear in both training and test pairs; a model can then score well by
recognising a familiar drug and its known interaction neighbourhood. (B)
Splitting by drug places every test drug entirely outside training (1,195 / 255
/ 255 drugs). (C) The S3 subset contains the drug-disjoint test pairs in which
both drugs are unseen, so neither has any adjacency in the training interaction
graph — a model relying on that graph has nothing to aggregate. All results in
this paper use (B), with (C) reported separately. Test pairs: 84,690 pooled,
7,758 in S3, both at 50% positive prevalence.*

---

## Figure 3 — Main pooled drug-disjoint performance **[to render]**

**Data.** `paper/tables/table3_main_model_comparison.csv`.

**Specification.** Horizontal bars, y-axis ordered by mean AUPRC, x-axis from
0.50 to 0.85 (never truncated above 0.5). Error bars = sample SD over five
seeds; overlay the five individual seed points. Colour by category: full model,
baselines, shortcut controls — three colours, not six.

**Caption.** *Predictive performance on 84,690 held-out drug-disjoint test pairs,
mean ± sample standard deviation over five training seeds; individual seeds shown
as points. BIO-GINE M4 (0.8117 ± 0.0097) is compared with an aligned
molecular-only model (0.7784 ± 0.0059), a non-neural random forest over
fingerprints and biology (0.7396 ± 0.0017), an aligned model with a known-DDI
network branch (0.7147 ± 0.0067), the same architecture trained on
degree-preserving shuffled biology (0.6923 ± 0.0054), and a random forest using
only annotation counts (0.6504 ± 0.0006). The axis begins at 0.50, the
performance of a random ranker at this prevalence. The comparison that matters is
not the height of the top bar but the gap between the full model and the two
shortcut controls, which preserve annotation quantity while removing biological
identity.*

---

## Figure 4 — S3 generalization **[frozen: `s3_auprc_per_seed.png`, `s3_delta_m4_m0.png`]**

**Caption (`s3_auprc_per_seed.png`).** *Performance on the 7,758 S3 test pairs, in
which both drugs are absent from training and therefore have zero adjacency in the
training interaction graph, shown per training seed. BIO-GINE M4 reaches
0.7372 ± 0.0153 and the aligned molecular model 0.7145 ± 0.0065, while the model
with a known-DDI network branch falls to 0.6198 ± 0.0278 — its seed-to-seed
variability more than quadrupling relative to the pooled setting. A network
branch asked to aggregate over an empty neighbourhood degrades exactly where that
neighbourhood is most completely absent. S3 is an experimental generalization
condition, not a model of clinical novelty: these are well-documented drugs whose
records were withheld, not newly approved medicines.*

**Caption (`s3_delta_m4_m0.png`).** *Per-seed difference between BIO-GINE M4 and
the aligned molecular model on the S3 subset. All seeds move in the same
direction, which is what produces the large paired effect size despite a modest
absolute difference.*

---

## Figure 5 — True biology versus shuffled biology and degree-only control **[to render]**

**Data.** `table3_main_model_comparison.csv`, `table4_hypotheses.csv`.

**Specification.** Three bars — M4 true biology, M4 degree-preserving shuffled
biology, biological-degree-only random forest — with the H-V2-3 and H-V2-4 paired
differences and Holm-adjusted p-values annotated as brackets above. Axis from
0.50. Include an inset stating exactly what the shuffle preserves.

**Caption.** *The central falsification control. If the model's use of biological
annotation were simply a proxy for how much a drug has been studied, then
randomising which specific proteins each drug is annotated against — while
holding the number of annotations per drug and per protein exactly fixed — should
leave performance largely intact. It does not: performance falls from
0.8117 ± 0.0097 to 0.6923 ± 0.0054 (paired Δ = 0.1195, Holm-adjusted
p = 1.83 × 10⁻⁴), a larger drop than the entire benefit of adding biology in the
first place. A random forest given only annotation counts reaches 0.6504 ± 0.0006
(Δ = 0.1613, Holm p = 1.67 × 10⁻⁵) — well above chance, confirming that
annotation popularity is genuinely predictive, but far short of the full model.
Together these support the conclusion that biological identity carried
information beyond annotation quantity. They do not show that the model learned
pharmacological mechanisms. Caveat: the shuffle left 2.53% of edges unchanged and
did not shuffle protein-to-pathway edges.*

---

## Figure 6 — Evidence-source ablation ladder **[to render]**

**Data.** `paper/tables/table5_ablation_ladder.csv`.

**Specification.** Grouped bars, pooled and S3 side by side, in ladder order M0,
M1, M2, M3, M4, then M4 SUM and M4 shuffled set apart as controls. Mark M4 as the
preregistered primary. **Do not** connect the bars with a rising trend line —
the sequence is not monotonic and a line would imply otherwise.

**Caption.** *Adding biological evidence sources one at a time, on both test
views. Every biological variant exceeds the no-biology baseline (M0), but the
ladder is not monotonic: performance peaks at M2 (DrugBank relations plus ChEMBL
curated mechanism-of-action evidence, 0.8269 pooled) and then declines as ChEMBL
experimental bioactivity (M3, 0.8177) and Reactome pathways (M4, 0.8117) are
added. M4 is the preregistered primary configuration, fixed on validation before
the test set was opened; it is not the best-performing variant, and it is shown
here as such. Two controls are shown apart: SUM aggregation (0.8265), which
exceeds the primary mean-aggregated model and indicates that annotation count
carries usable signal the primary model deliberately discards; and shuffled
biology (0.6923). Explanations for the shape of this ladder were not
preregistered and are post-hoc.*

---

## Figure 7 — Calibration reliability **[frozen: `m4_reliability_diagram.png`]**

**Caption.** *Reliability diagram for BIO-GINE M4 before and after temperature
scaling. Predicted probability is binned on the x-axis and the observed fraction
of positives plotted on the y-axis; a perfectly calibrated model lies on the
diagonal. The raw model is substantially overconfident, with expected calibration
error around 0.19–0.21 across seeds. A single temperature parameter per seed
(5.9–10.1), fitted only on validation predictions and applied unchanged to the
frozen test predictions, reduces calibration error to roughly 0.05–0.06 and
improves the Brier score from about 0.22 to about 0.18. Ranking is unaffected —
AUPRC changes only in the seventh decimal place — because dividing logits by a
positive constant cannot reorder examples. Calibration makes the probability more
interpretable; it does not make the model more accurate, and a calibrated
probability from this research model is not a clinically validated risk estimate.*

**Also available [frozen]:** `s3_calibration_metrics.png`, calibration metrics
restricted to the S3 subset; `s3_auroc_per_seed.png`, the AUROC counterpart to
Figure 4.

---

## Figure 8 — Model-reliance example **[to render]**

**Data.** `reports/v2_interpretability/seed0_modality_contribution.csv`,
`seed0_leave_one_protein_out.csv`, `seed0_leave_one_pathway_out.csv`.

**Specification.** Two panels. Panel A: distribution (violin or ECDF) of absolute
change in predicted probability when each whole modality is withheld across all
84,690 test pairs — protein, molecular, pathway. Panel B: for one example pair,
a ranked bar chart of the largest single-annotation reliance values, with the
protein or pathway identifier on the axis. **Panel B must carry the disclaimer
text inside the figure**, not only in the caption.

**Caption.** *Model reliance measured by withholding inputs from the frozen
seed-0 model and recording how far the predicted probability moves. (A) Removing
an entire modality across all 84,690 test pairs changes the prediction by a mean
absolute 0.313 for proteins, 0.192 for molecular structure and 0.107 for
pathways, so the model relies most on protein annotation. (B) Reliance on
individual annotations is highly concentrated: across 4,031 single-protein
ablations the median change is exactly zero and the mean 0.000274, yet the
maximum is 0.985 — a single protein annotation whose removal moved one prediction
from 1.000 to 0.015. Across 13,192 single-pathway ablations the largest change
was 0.00078, so no individual pathway is load-bearing even though the pathway
modality as a whole is used. **These perturbations indicate which biological
inputs influence the model's predictions. They do not establish causal
pharmacological mechanisms.***

---

## Supplementary figure — evaluation-scheme degradation **[frozen: `phase_a_degradation.png`]**

**Caption.** *Performance under the three splitting schemes measured in an
earlier phase of this project, illustrating the leakage effect that motivates the
drug-disjoint protocol used throughout this paper. This figure describes earlier
experiments and is included as context; it is not part of the frozen V2 results.*
