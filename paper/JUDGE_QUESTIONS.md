# JUDGE_QUESTIONS.md

Thirty-four questions, ordered roughly from most likely to hardest. Every answer
uses only what this study actually measured. Where the honest answer is "we
don't know" or "that's a real weakness", it says so — a judge who catches an
evasion stops believing everything else.

---

## Metrics and evaluation

### 1. Why AUPRC rather than accuracy?

Accuracy depends on a decision threshold, and a threshold is an application
choice we have no basis to make. AUPRC summarises performance across all
thresholds and is sensitive to how well the model ranks true interactions above
non-interactions. It was preregistered as primary. We also report AUROC, Brier
score and calibration error.

One honest caveat: the usual argument for AUPRC over AUROC is class imbalance
[saito2015prc], and our evaluation sets are balanced at 50% prevalence, so that
argument is weaker here. We kept AUPRC primary because it was preregistered, not
because the imbalance argument applies.

### 2. What does an AUPRC of 0.81 actually mean?

It is the area under the precision–recall curve. At 50% positive prevalence, a
random ranker scores 0.5 and a perfect one scores 1.0. It is **not** "81%
correct". And the number is not interpretable alone — the comparison is what
matters: 0.81 against 0.78 for a molecular-only model, 0.69 for the same model
with scrambled biology, and 0.65 for annotation counts alone.

### 3. Why drug-disjoint splitting?

Because the question we care about is what happens with a drug the model has
never seen. If you split interaction *pairs* at random, a drug with 500 known
interactions appears in both training and test, and the model can score highly by
recognising it. That measures memorisation of familiar drugs, not generalisation.
Kapoor and Narayanan [kapoor2023leakage] document this failure across 17 fields.
We hold out drugs, so every test drug is entirely absent from training.

### 4. Why degree-matched negatives?

The dataset has no negatives at all, so we generate them. If we sampled uniformly,
highly connected drugs would be common among positives and rare among negatives,
and a model could score well above chance by detecting "both of these drugs
interact with a lot of things" — with no chemistry involved. Degree matching makes
the negative degree distribution match the positive one, removing that shortcut.
It makes our numbers lower, which is the intent. Degree is computed from training
pairs only, so the sampler never consults test edges.

### 5. What is S3?

The subset of drug-disjoint test pairs in which **both** drugs are test drugs, so
both have zero adjacency in the training interaction graph. It is the hardest
condition here: 7,758 pairs. A model with a known-interaction branch has literally
nothing to aggregate for either drug.

### 6. Why does the Dual model collapse on S3?

Structurally, not incidentally. A neighbourhood aggregation computes a function of
a node's neighbours. For an S3 drug that set is empty, so the branch outputs a
constant and the capacity assigned to it is wasted. It drops from 0.7147 to
0.6198, and its seed-to-seed standard deviation more than quadruples (0.0067 →
0.0278) — the model becomes unstable as well as weaker. That is the same property
that makes it *useful* under pair-level evaluation, seen from the other side.

### 7. Was the test set used more than once?

The primary model's configuration was selected on validation across 96 runs and
frozen before the test set was opened — the frozen configuration file states this
in writing. Ablations and controls were then evaluated on that same test set,
which is genuine multiplicity, and it is why we applied Holm correction across the
five preregistered hypotheses. Analyses we did not preregister — the shape of the
ablation ladder, the modality reliance ranking — are labelled post-hoc and are not
corrected. We do not claim the test set was touched exactly once in total.

### 8. Why five seeds?

To estimate how much the result depends on training randomness — parameter
initialisation, batch ordering, negative sampling draws. Five is enough to pair
comparisons seed-by-seed and compute an effect size; it is not many.

Important limitation: seeds do **not** create independent datasets. They all use
the same split and the same drug universe. So our standard deviations describe
training stochasticity, not variability across drug populations. With n = 5 we
also cannot verify the t-test's normality assumption.

---

## Statistics

### 9. What does the Holm correction do?

With five hypotheses tested at α = 0.05, the chance that at least one nominally
significant result is a false positive is well above 5%. Holm [holm1979] sorts the
raw p-values, multiplies the smallest by 5, the next by 4, and so on, taking a
running maximum so the sequence stays monotonic. It controls the family-wise error
rate and is uniformly more powerful than plain Bonferroni.

We applied it across **all five** hypotheses, including the exploratory H5. That
makes the correction stricter for the four confirmatory ones than a family of four
would have been.

### 10. Your effect sizes are enormous — dz of 16. Is something wrong?

It is a real number and it needs the right interpretation. Cohen's *dz* for paired
data is the mean difference divided by the standard deviation *of the
differences*. When five seeds all move the same direction by a similar amount, the
denominator is tiny and dz becomes very large. It says the effect is extremely
consistent across seeds — not that it is large in absolute terms. H-V2-1's actual
gap is 0.033 AUPRC, which is modest. Reporting dz without the raw difference would
be misleading, so we always give both.

### 11. Why report bootstrap results too?

The seed-level t-test and the bootstrap address different sources of variability.
The t-test asks whether the difference is consistent across training runs; the
bootstrap (1,000 resamples on seed 0) asks whether it is stable under resampling
of the test pairs. Both supported H1 and H3, with zero of 1,000 resamples at or
below zero. Neither substitutes for the other.

### 12. Isn't n = 5 too small for a t-test?

It is small, and we say so in the limitations. The normality assumption cannot be
checked at that sample size. Two things mitigate it: the effects are far from the
significance boundary (the largest Holm-adjusted p among the confirmatory
hypotheses is 6.6 × 10⁻⁴), and the bootstrap gives an independent check for H1 and
H3. If the effects had been marginal, we would not defend them on five seeds.

---

## Controls and the central claim

### 13. How do you know biology isn't just annotation popularity?

This is the question the study is built around, and we have two answers.

First, a model given **only** annotation counts reaches 0.6504 — well above chance,
so popularity genuinely is predictive — but 0.16 AUPRC below the full model.

Second, and more decisively: we randomised *which* proteins each drug is annotated
against while holding the number of annotations per drug and per protein **exactly
fixed**, then retrained from scratch. Performance fell from 0.8117 to 0.6923. If
counting were the signal, that shuffle should have changed almost nothing.

### 14. Why does shuffled biology still reach 0.69?

Three reasons, and we do not think we can fully separate them. The shuffle
preserves both degree sequences exactly, so all count-based signal survives by
design. The protein→pathway layer was not shuffled, so some pathway-level
structure persists. And 2.53% of edges were retained unchanged because the swap
algorithm could not move them within their stratum. The shuffled model is a model
with real annotation counts and scrambled identities — 0.69 is roughly what
count-level signal plus residual structure is worth.

### 15. Isn't 2.53% retained overlap a problem?

It weakens the control, and we report it rather than rounding it to "the biology
was randomised". The direction of the bias matters: retained edges make the
shuffled model *better* than a perfect shuffle would, so the true identity effect
is if anything slightly larger than the 0.1195 we report. It is a conservative
imperfection, but it is an imperfection.

### 16. Your shuffle differs from what you preregistered. Why?

We preregistered uniform resampling of |P(d)| proteins per drug. We implemented a
stratified degree-preserving double-edge swap instead. Uniform resampling
preserves each drug's count but destroys the *protein* degree distribution, so the
shuffled data would be distinguishable from real data by statistics other than
identity — the control would be too easy to beat. The swap preserves both degree
sequences and the evidence stratum, making the control **stricter**. The deviation
and its direction are recorded in the shuffle manifest, written before the results
were known.

### 17. Why did M2 outperform M4, your primary model?

It did — 0.8269 versus 0.8117 pooled, and the same ordering on S3. M4 is the
*worst* of M1 through M4. We report this rather than hiding it.

M4 was selected on validation across 96 runs and frozen before the test set was
opened. Switching to M2 after seeing test results would make the test score
meaningless — that is precisely the practice that produces irreproducible
literature.

As for *why*: our post-hoc reading is that evidence quality matters more than
quantity. M2 adds curated mechanism-of-action assignments; M3 adds experimental
bioactivity, which is noisier and threshold-dependent; M4 adds pathway membership,
which is highly redundant (median 52 pathways per drug, many nested) and can
dilute a set-mean. We did not preregister a prediction about the ladder's shape,
so that explanation is a hypothesis, not a finding.

### 18. Your SUM control beat your primary model. Doesn't that undermine the whole design?

It is a real qualification and we report it in the results, the discussion and the
limitations. SUM reached 0.8265 pooled against MEAN's 0.8117. Our own
preregistration fixed the reading in advance: "if SUM wins, counting was the
signal."

The complete picture is that both count and identity carry signal. SUM shows count
is worth about 0.015 AUPRC that MEAN discards. CONTROL F shows identity is worth
about 0.12. We chose MEAN so the counting shortcut would be excluded by
construction and therefore *testable* — and the ablation now tells us what that
choice cost. We think the trade was right for a study about *why* a model works,
but it was a trade, and H-V2-3 is unaffected because that comparison holds
aggregation fixed.

### 19. Why is CONTROL E's test R² undefined?

Because our own split guarantees it. The probe predicts a drug's
training-interaction degree from its learned biological embedding. Under a strict
drug-disjoint split, every test drug has training-interaction degree of exactly
zero — we verified minimum 0, maximum 0, variance 0 across all 255 test drugs.

R² is explained variance over total variance. With zero total variance the
quantity is undefined, not zero. The `0.0` in our output file is a placeholder,
and the Pearson and Spearman fields are `NaN`, which is the signature of a
constant target. Reporting "R² = 0, so the embedding doesn't encode degree" would
be claiming evidence from a measurement that could not be made.

On training drugs the R² is 0.543, so the embedding *does* carry degree
information there. That is why CONTROL F, not CONTROL E, is our load-bearing
control.

### 20. So one of your planned controls simply failed?

Yes. The design contained a contradiction we did not notice until the result came
back: a strict drug-disjoint split makes the probe's target constant on the test
set. We report it as non-identifiable rather than reporting the convenient zero,
and we say what would fix it — a target with variance among held-out drugs, or
predicting degree among training drugs with a held-out subset.

### 21. Why is H5 unsupported, and does that hurt your conclusion?

H5 predicted that biology would help more for pairs where both drugs have pathway
coverage. The contrast went the other way (−0.0233) and was not distinguishable
from zero (p = 0.157).

It does not hurt the main conclusion, because no other result depended on it. It
was registered as **exploratory** with no significance threshold, so the correct
description is "exploratory direction unsupported" — not a failed confirmatory
hypothesis. It is also informative in combination: H5's null, the M3 → M4 decline,
and the near-zero single-pathway reliance values all point the same way — the
pathway level contributed little here.

### 22. What would have falsified your hypothesis?

Five criteria were written down before we ran anything:

- **F1** — M4 fails to beat the molecular-only model on drug-disjoint test.
- **F2** — shuffled biology is not significantly worse than true biology.
- **F3** — the annotation-count-only random forest matches M4.
- **F4** — the linear probe reaches R² > 0.6 *and* H1's effect size is below 0.2.
- **F5** — M4 improves on random-pair splits but not on drug-disjoint or
  scaffold-disjoint.

F1–F3 were not triggered. F4 cannot trigger: its second condition fails outright
(dz = 7.72 ≫ 0.2). F5's drug-disjoint half is decisively not triggered, but we
never ran the scaffold-disjoint evaluation, so we report it as not fully resolved
rather than claiming to have ruled it out.

H-V2-1 and H-V2-3 also required *both* significance and an effect size above
d = 0.5, so a statistically detectable but negligible effect would not have counted
as support.

### 23. Why didn't you run the scaffold-disjoint evaluation?

We did not, and it is a genuine gap. The scaffold assignments already exist in the
frozen data, so it is an evaluation we could run — not new data collection. It
matters because drug-disjoint splitting does not stop a test drug from sharing a
Bemis–Murcko framework [bemis1996scaffold] with a training drug, so what we
demonstrate is generalization to unseen *drugs*, not unseen *chemotypes*. It is
the first item in our future work.

---

## Interpretability

### 24. Why can't interpretability prove mechanism?

Our analysis removes an annotation and measures how far the prediction moves.
That tells you what the *model* relied on. It cannot tell you why the interaction
happens in a patient.

A protein whose removal changes a prediction could reflect a genuine
pharmacological relationship, or could be a marker for a drug class, a therapeutic
area, or a pattern in how databases are curated. All of these depend on protein
identity, and none is a mechanism. Distinguishing them requires experiments we did
not do. The correct phrasing is always "removing this annotation changed the
model's prediction by X", never "this protein causes the interaction".

### 25. Some proteins had almost no effect and one had a huge effect. Why?

Across 4,031 single-protein ablations the median change was exactly zero and the
mean 0.000274 — yet the maximum was 0.985, where removing one annotation moved a
prediction from 1.000 to 0.015. The model has learned sparse dependence: a small
number of annotations are decisive and most are redundant. For pathways even the
maximum was tiny (0.00078), so no single pathway is load-bearing, even though
removing the whole pathway modality shifts predictions by 0.107 on average.

### 26. Does calibration make the model better?

No, and this is worth being precise about. Temperature scaling
[guo2017calibration] divides the logits by one positive constant. That cannot
change the *order* of predictions, so ranking metrics are unchanged — our AUPRC
moved only in the seventh decimal place, which is floating-point noise and would
have indicated a bug if absent. Calibration makes the probability values more
honest (calibration error dropped roughly threefold). It does not make the model
more accurate.

---

## Scope and clinical questions

### 27. Can a doctor use this system clinically?

No. It has never been evaluated against clinical outcomes, it has no patient
information of any kind, and its labels are "an interaction is documented in a
database" — not severity, not direction, not clinical importance. It is a research
prediction system, and its outputs should be read as hypotheses for further
investigation.

### 28. Can it predict effects for an elderly patient? Or a child?

No. Age is not an input to the model. Neither is sex, weight, renal function,
hepatic function, genotype, nor any other patient variable. The model has no
representation of a patient at all, so it cannot produce a different answer for
different people, and no result in this study applies differently to any age
group.

### 29. Does it model drug dosage?

No. There is no dose input and no dose–response relationship anywhere in the
model. Interactions are dose-dependent in reality; this model does not represent
that.

### 30. Does it model metabolism?

Only indirectly and only as annotation. The model knows which enzymes and
transporters a drug is *annotated* against, and which pathways those proteins
belong to. It has no representation of reaction kinetics, clearance, half-life,
concentration over time, or tissue distribution. It is not a pharmacokinetic
simulator.

### 31. What about interactions your training data doesn't document?

That is a real limitation with two faces. Roughly 86.8% of the pair space is
unlabelled rather than negative, so some of our generated negatives are almost
certainly undocumented true interactions — which pushes our measured performance
*down* by an unknown amount. And a model trained on documented interactions
inherits the biases in what gets documented: older, widely used drugs are better
characterised.

---

## Positioning and next steps

### 32. How does this differ from Decagon or other DDI GNNs?

Decagon [zitnik2018decagon] showed that protein information helps DDI-type
prediction, and it is the ancestor of our biological branch. The difference is
what happens under evaluation. Decagon is transductive: every drug is a node in
the training graph and its representation is built by message passing over
neighbours, including known interaction edges. A drug with no edges has no
neighbourhood.

We deliberately remove that. Our biological representation is a per-drug set with
no message passing between drugs, so nothing can reach a test drug through the
interaction graph, and we evaluate on drugs absent from training.

EmerGNN [zhang2023emergnn] is closer in motivation — it explicitly targets
emerging drugs — and works at larger scale than we do. Our distinguishing element
is not the architecture but the controls: we are not aware of a published DDI
method that reports a degree-preserving biological-identity shuffle. If one
exists, we would narrow that claim.

### 33. What is genuinely novel here?

Not the architecture. GINE, Deep Sets and temperature scaling are all published
methods used as published, and stronger molecular DDI models exist.

The contribution is the **control design**: treating "biology helps" as a
hypothesis that could be right for an uninteresting reason, and building an
experiment that can detect that reason. The degree-preserving identity shuffle is
the specific instrument. The result is a narrower and more defensible claim than
"biology helps": *biological identity, not merely annotation quantity, carried
information that transferred to unseen drugs in this dataset*.

The secondary contribution is methodological discipline: preregistered hypotheses
and falsification criteria, a primary model that turned out not to be the best
performer and is reported as such, one unsupported hypothesis, one control that
beat the primary model, and one diagnostic reported as undefined rather than as a
convenient zero.

### 34. What experiment would you run next?

Three, in priority order.

**Scaffold-disjoint evaluation.** It closes the open half of F5, the assignments
already exist, and it tests whether the gain survives holding out whole chemotypes
rather than individual drugs.

**A redesigned CONTROL E.** The probe needs a target with variance on the
evaluation set. Predicting degree among training drugs with a held-out subset
would restore identifiability and answer the question we actually wanted answered.

**Explain the M2-to-M4 decline.** Test directly whether it is evidence quality or
set-size dilution, by weighting set elements by evidence type or pruning redundant
nested pathways. If dilution is the cause, a representation carrying both
normalised content and an explicit, separately controlled size feature might beat
both MEAN and SUM — which would also address the CONTROL C result.

Beyond those: prospective evaluation on interactions documented after our data
snapshot, which is the closest available approximation to a genuine unseen-drug
test.
