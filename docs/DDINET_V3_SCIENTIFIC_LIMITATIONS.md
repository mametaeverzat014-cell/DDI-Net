# DDI-Net 3.0 — Scientific Limitations

The limitations of the frozen V2 study (`LIMITATIONS.md`,
`paper/DDI_NET_ISEF_RESEARCH_PAPER.md`) all still apply. This file adds what is
specific to the 3.0 evidence layer: what its statements can and cannot mean, and
what was measured rather than assumed. Every number here is in a file under
`reports/` produced by a script under `scripts/`.

---

## 1. What DDI-Net 3.0 is not

* **Not a clinical decision-support system.** It is not validated for clinical
  use, gives no medication instructions, and does not assess a particular
  patient. Every report says so and refers decisions to a doctor or pharmacist.
* **Not a severity classifier.** No component assigns a severity. The DrugBank
  export has none; a label section is a structural fact of the document; the
  model score is not a severity and is never converted into one.
* **Not a safety checker.** "No documented interaction found" means only that
  the sources consulted hold no record under the names searched. It is
  displayed in grey with the sentence "This does not mean the combination is
  safe", and never in a reassuring colour.
* **Not a model of three or more drugs.** The multi-drug mode is pairwise; the
  page states that above its results.

## 2. Documented evidence

### 2.1 DrugBank via TDC

* **Coverage is a snapshot** (PyTDC 1.1.15, retrieved 2026-08-24) restricted to
  the 1,705-drug research universe. Drugs outside it cannot be analysed.
* **No basis per record.** The export does not say whether a record comes from
  a clinical study, label text, or inference from pharmacological properties.
* **Drug order is unreliable for most directional types** (measured,
  `reports/v3_tdc_direction_audit.md`). Against DrugBank's own enzyme roles, the
  export order matches the template for types 4 (99.6%) and 75 (97.0%) but is
  reversed for most rows of types 47 (8.0% consistent) and 73 (10.3%), and is
  mixed for 11, 72 and 77. Pharmacodynamic types cannot be checked this way.
  115,920 of 191,798 records are therefore rendered without saying which drug
  is affected. Anchor-drug checks on pharmacodynamic types point the same way
  (anticoagulants sit in the `#Drug1` slot of "may increase the anticoagulant
  activities of #Drug2" far more often than in `#Drug2`), but were exploratory
  and are not used by the API.
  *The frozen BIO-GINE results are unaffected:* the model trains on unordered
  pairs.
* **Russian sentences are project translations** of DrugBank's 86 templates,
  shown with the English original.

### 2.2 FDA labels (openFDA)

* **Name matching only.** Labels very often describe interactions for classes
  ("strong CYP3A4 inhibitors", "NSAIDs"). No class membership is inferred, so a
  label that addresses the combination at class level produces no match.
* **One label per ingredient**: the most recent single-ingredient human
  prescription label. Other manufacturers' labels, combination products and
  older versions are not consulted.
* **US labels only**, in English; excerpts are not translated.
* **One sentence, one excerpt.** A sentence that one label repeats in several
  of its sections (older-format labels repeat their Drug Interactions
  subsection, and openFDA returns it twice) is one excerpt with all its section
  names. Several excerpts of one label are one source, not separate
  confirmations. The rule is lexical: paraphrases stay separate excerpts of the
  same document.
* **No-effect detection is a word list.** Sentences such as "did not
  significantly alter" are categorised separately; a sentence reporting no
  effect in other words may stay in the warning category (the safer error).
* **Not live-tested in this session.** The development container's network
  policy blocked `api.fda.gov` and `rxnav.nlm.nih.gov`; the adapters were tested
  against recorded response shapes with synthetic content
  (`tests/test_v3_adapters.py`). Their first live use will be on the deployed
  API host.

### 2.3 Names

* 208 of 1,705 drugs have no DrugCentral INN (e.g. rifampicin, DB01045) and are
  findable only by DrugBank ID offline.
* US and international names differ (acetaminophen / paracetamol). A
  project-curated list of 40 aliases covers common cases; RxNorm, when
  reachable, covers brands. Russian names are transliterations, not sourced.

## 3. Mechanism hypotheses

* **Assembled, not observed.** A hypothesis combines each drug's separately
  documented roles. DrugBank does not record inhibitor/inducer strength or the
  fraction of a drug's clearance a protein handles, so a configuration can be
  pharmacologically negligible.
* **Prodrugs.** For a prodrug, slower processing can mean less active drug. The
  text therefore says "may be broken down more slowly", never "levels rise".
* **Not independent of the labels.** Agreement between a hypothesis and a
  DrugBank record is reported as consistency; DrugBank may have derived the
  record from the same annotations. On the frozen test pairs the configuration
  occurs in 41.4% of documented pairs and 15.9% of sampled unlabelled pairs
  (`reports/v3_mechanism_concordance.md`) — consistency, not validation.
* **Shared pathways are background.** Reactome "all levels" membership places
  many unrelated proteins in broad pathways; ranking by specificity is a
  presentation choice.
* **Protein descriptions** for lay readers are general family texts written by
  the project, labelled as such.

## 4. Model signal

* **One checkpoint.** Only seed 0 of the final M4 run was released. Live
  ensembles are impossible.
* **Seed disagreement is not shown as uncertainty**, because it was measured
  and found uninformative beyond the score: on held-out pairs it detects
  ensemble errors with AUROC 0.686 (pooled) and 0.626 (S3), against 0.698 and
  0.634 for the score's own distance from 0.5; within score bands it adds
  little (`reports/v3_seed_disagreement.md`).
* **Reliability depends on annotation coverage** (measured, 5 seeds,
  `reports/v3_coverage_reliability.md`): AUROC 0.818 ± 0.010 when both drugs
  have protein annotations vs 0.750 ± 0.023 when at least one has none (pooled);
  0.735 ± 0.018 vs 0.654 ± 0.037 in S3. Reported per pair as a note and a
  measured figure, not as a confidence percentage.
* **Regime.** Pairs of two training drugs (S1) were never evaluated on held-out
  data; when such a pair is documented, the model was trained on its label and
  its score is withheld from the status and the explanation.
  Validation-split drugs influenced configuration selection and calibration.
* **Pooled test metric.** M4's frozen test metrics exist for the pooled
  drug-disjoint test (S2 and S3 together: 84,690 pairs, 7,758 of them S3) and
  for S3. No S2-only figure exists, so an S2 pair is shown the pooled figure,
  labelled as pooled. Test-set metrics describe many pairs, not one prediction.
* **Calibration.** Temperature scaling (T = 7.20) was fitted on validation pairs
  at prevalence 0.5 against sampled unlabelled negatives. The calibrated score
  is not a probability of interaction in practice, nor of harm. The
  `model_signal_only` threshold of 0.5 is a stated convention.
* **Model reliance is not mechanism.** The modality readout reproduces the
  frozen analysis exactly (max |Δ| 6.05e-06 over 84,690 pairs,
  `reports/v3_modality_parity.md`), but a zeroed branch is an input the model
  never saw in training, and changes are compressed when the raw score is
  saturated near 0 or 1 (flagged in the UI). Per-protein attribution exists in
  the frozen study for 20 pairs only and is not extrapolated.

## 5. Exploratory research result and its limits

On the 84,690 frozen test pairs (`reports/v3_mechanism_concordance.md`):
BIO-GINE, which never sees drug roles, scores **unlabelled** pairs that carry a
pharmacokinetic configuration markedly higher than those that do not (mean
0.298 vs 0.137; AUROC 0.668), and the gap persists within strata of annotation
volume (AUROC 0.50 → 0.68 from the lowest to the highest stratum). Among
**documented** pairs the difference is negligible (AUROC 0.506).

Two readings remain open: such unlabelled pairs are more often undocumented
true interactions (the negatives are unlabelled, not confirmed), or residual
confounding by how well studied the drugs are. No independent source (labels,
pharmacovigilance, literature) was available in this environment to separate
them. 1,737 unlabelled test pairs combine a configuration with a score ≥ 0.5;
they are hypotheses, not findings.

## 6. Engineering facts that bound the claims

* External sources were unreachable from the development container; all
  external-adapter behaviour shown in tests is against mocks.
* The deployed site and API were not updated from this session; nothing was
  pushed or deployed.
* The evidence layer was not evaluated with users. Whether lay readers
  understand the five-section explanation as intended is untested.


## 7. Clinical outcome engine

The design is in `docs/DDINET_V3_CLINICAL_OUTCOMES_ARCHITECTURE.md` and the
measurements in `docs/DDINET_V3_CLINICAL_OUTCOMES_VALIDATION.md`.

* **Outcomes come only from sources that state them for the pair:**
  * a DrugBank record, read through a fixed 86-row type map;
  * or a label sentence that names the partner drug together with an outcome
    term (`label_lexicon/v2`).

  General adverse reactions are never assigned to a pair, and the Adverse
  Reactions section is not read.
* **DrugBank outcomes are template-level.** The record names the effect
  ("risk or severity of bleeding"), but gives no frequency, severity or basis.
* **Label extraction is rule-based and partial.** On a 40-sentence
  constructed hold-out set it found 25 of 32 annotated outcomes, with 1
  unsupported extraction. Paraphrases are missed, and a sentence about the
  partner's own effect can be taken as a pair outcome. The excerpt is always
  shown verbatim.
* **No validation on real label text has been possible yet.** openFDA is
  unreachable from the build container.
* **The affected drug of an exposure change** is named only from a verified
  record order, or from unambiguous inhibitor/inducer–substrate annotations.
  The annotation rule agreed with a verified order in 595 of 606 checks on the
  same database. That is consistency, not confirmation.
* **Seriousness is never estimated.** It is stated only from a
  CONTRAINDICATIONS section, a BOXED WARNING, or explicit "fatal /
  life-threatening / serious" wording in the quoted sentence. Otherwise:
  "Severity not established from available evidence."
* **Mechanism chains** connect protein annotations to a documented exposure
  change. A link to a clinical outcome is "documented" only when one label
  sentence states both. Shared proteins or pathways are never treated as
  causes.
* **The interaction status and the outcomes do not depend on the BIO-GINE
  score.** This was checked with scores 0.01 and 0.99 on 89 pairs.
* **No documented outcome is not evidence of safety.** The text says so
  wherever it applies.

### 7.1 Reference-set evidence (CRESCENDDI) and the label rule on real text

* **CRESCENDDI positive controls** (BNF, Micromedex and ANSM, 2018–2019) are shown as
  pair-specific documented outcomes. Coverage of named clinical outcomes rises from 676 to 4,551
  pairs. Limits:
  * They are a snapshot, limited to pairs common to all three compendia.
  * Their correctness is not assessed here.
  * The compendia's severity grades are not reproduced, so severity remains "not established".
* **The label rule (`label_lexicon/v3`) on the DDI Corpus** (independent annotation, held-out
  part):
  * 51/61 assigned outcomes are for pairs annotated as interacting;
  * 10 of 164 merely co-mentioned pairs get an outcome;
  * an outcome is found for only 51 of 233 interacting pairs.

  A label outcome is therefore a quoted lead, not a verified fact, and a missing one says nothing.
* **DrugBank (TDC export) names a clinical outcome for about 1% of the pairs that CRESCENDDI
  documents.** Most DrugBank records are PK or PD templates.
* Details: `docs/CLINICAL_OUTCOME_VALIDATION.md`, `docs/DATASET_AUDIT.md`.
