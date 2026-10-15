# DDI-Net 3.0 — Clinical Outcome Engine: pilot validation

**What this is.** It checks whether the outcome engine does what its rules
say it does:
* on constructed label sentences with rule-based annotations;
* on real DrugBank records from the local export;
* on adversarial cases.

**What this is not.**
* It is **not a clinical validation** and not an independently validated
  benchmark.
* Every sentence set was written by the same author as the extraction rules.
* No real FDA label text was used: openFDA and DailyMed are not reachable
  from the build container, and no label text was reproduced from memory.
* The numbers describe the rules on these sets, not their accuracy on real
  labels. They also say nothing about how often an interaction harms anyone.

**How to reproduce.**
* Script: `scripts/66_v3_outcome_validation.py`, with seed 20261015. It is
  deterministic and needs no network.
* Output: `reports/v3_outcome_validation.json` and `reports/v3_outcome_validation.md`.
* Sentence sets and annotation rules are in `validation/clinical_outcomes/`:
  * `ANNOTATION_RULES.md`;
  * `pilot_label_sentences.jsonl` (development set, 75 sentences);
  * `holdout_label_sentences.jsonl` (hold-out set, 40 sentences);
  * `dev_round1_label_lexicon_v1.json` (the first measurement, kept as
    measured).

Proportions are given with Wilson 95% intervals. Extraction precision and
recall also have a sentence-level bootstrap with 2,000 resamples, because
(sentence, concept) units cluster within sentences. Intervals this wide are
the honest reading of samples this small.

---

## 1. Label outcome extraction

**Task.** A label sentence names the partner drug. Which documented
consequences does it state for the combination? There are 21 concepts:
bleeding, coagulation measure, QT/arrhythmia, bradycardia/block, serotonin
syndrome, respiratory depression, sedation, hypo-/hypertension, five
electrolyte or glucose disturbances, myopathy, kidney, liver, bone marrow,
reduced effect, and exposure increase or decrease. The full list is in
`ANNOTATION_RULES.md`.

**Units.** A unit is a (sentence, concept) pair.
* Precision is the share of extracted concepts that are annotated.
* Recall is the share of annotated concepts that are extracted.
* The unsupported-claim rate is the share of sentences with any extraction
  that carry at least one concept not annotated.
* Abstention is the share of sentences with no annotated outcome that get no
  extraction. These are negated, population, single-drug, mechanism-only and
  mixed sentences.

**Two ways of scoring.**
* *Rule level*: the rule function the engine uses, including the
  "no effect reported" filter.
* *End to end*: each sentence is placed in a constructed openFDA label and
  served by a mocked transport. The full engine then runs, including
  partner-name matching, sentence splitting and outcome assembly.
* End-to-end scoring needs the partner drug to resolve offline. Names such as
  rifampin or insulin need RxNorm, which is unreachable here, so those
  sentences are skipped and listed in the report.

### 1.0 Development round 1 — `label_lexicon/v1` (kept as measured)

Development set, 75 sentences, rule level:

| Measure | Value |
|---|---|
| Precision | 42/48 = 0.875 (Wilson 95% 0.753–0.941) |
| Recall | 42/55 = 0.764 (0.637–0.856) |
| Unsupported-claim rate | 6/46 sentences = 0.13 (0.061–0.257) |
| Abstention on no-outcome sentences | 17/23 = 0.739 (0.535–0.875) |

The six unsupported claims fell into three groups:
* Negation or uncertainty placed **after** the term: "Bleeding risk was not
  increased with clopidogrel", "Hypotension was not observed with amlodipine",
  "Bleeding time was unchanged…", "Hypoglycemia was not more frequent…" and
  "The risk of QT prolongation with ondansetron is unknown".
* A single-drug effect in a second clause: "Warfarin is an anticoagulant; this
  drug alone has caused hepatitis".

The adversarial label case (§4) also exposed a bug: the coagulation term was
case-sensitive. A sentence starting with "Prothrombin time increased…" was
therefore missed.

### Changes in `label_lexicon/v2`

All three changes favour abstention:
1. **Negation or uncertainty after the term.** Within 40 characters and the
   same clause (`was/were/is/are/has/have … not|unchanged|unaffected|unknown|uncertain|similar`),
   the occurrence is skipped.
2. **Partner clause.** In a sentence with semicolons, only the clauses naming
   the partner are read. If the partner is named in none of them, the whole
   sentence is read.
3. **Case.** "Prothrombin time / international normalized ratio /
   anticoagulant effect" are case-insensitive; "INR" stays case-sensitive.

The method identifier changed to `label_lexicon/v2:term=…`, so every support
records which rules produced it.

### 1a. Development set with v2 — NOT held out

v2 was written after seeing v1's errors on this set. The figures below are
therefore not an estimate of anything and are reported only for
completeness.

| Measure | Rule level | End to end |
|---|---|---|
| Sentences | 75 | 65 |
| Precision | 42/42 = 1.0 (0.916–1.0) | 36/36 = 1.0 (0.904–1.0) |
| Recall | 42/55 = 0.764 (0.637–0.856) | 36/47 = 0.766 (0.628–0.864) |
| Unsupported-claim rate | 0/40 (0–0.088) | 0/34 (0–0.102) |
| Abstention on no-outcome sentences | 23/23 (0.857–1.0) | 21/21 (0.845–1.0) |

### 1b. Hold-out set with v2 — scored once

The 40 sentences were written after v2 was frozen; the file's SHA-256 is
recorded in the report. They were scored once, and no rule was changed
afterwards.

| Measure | Rule level | End to end |
|---|---|---|
| Sentences | 40 | 38 |
| Precision | 25/26 = 0.962 (Wilson 0.811–0.993; bootstrap 0.875–1.0) | 25/26 = 0.962 (0.811–0.993) |
| Recall | 25/32 = 0.781 (Wilson 0.612–0.890; bootstrap 0.636–0.909) | 25/32 = 0.781 (0.612–0.890) |
| Unsupported-claim rate | 1/24 sentences = 0.042 (0.007–0.202) | 1/24 = 0.042 (0.007–0.202) |
| Abstention on no-outcome sentences | 11/12 = 0.917 (0.646–0.985) | 9/10 = 0.90 (0.596–0.982) |
| Rule and engine agree | — | 38/38 sentences |

**The unsupported claim (h13).** "Citalopram causes dose-dependent QT interval
prolongation" states the partner's own effect, not an effect of the
combination. The rules cannot tell the two apart. The excerpt is shown
verbatim, so the reader sees what the source actually says. The case is
listed under §5 as a known limitation.

**The 7 missed concepts:**
* "Digoxin concentrations" and "serum lithium levels": the exposure noun does
  not follow the expected word pattern.
* "digoxin levels".
* "graft rejection" and "loss of virologic response" are paraphrases of
  reduced effect.
* "diminish the antihypertensive effect".
* "…azathioprine; severe myelosuppression has been reported": v2's partner
  clause rule drops the second clause.

Because recall is partial, a label can state an outcome that the engine does
not extract. The site and the PDF therefore never treat an absent extraction
as absence of risk. "No documented outcome" is always worded as a statement
about the sources and rules, never about safety.

**Development and hold-out together (v2, rule level).** The development
figures are not held out, so the combined numbers are only an upper-side
summary. Precision is 67/68 and recall is 67/87. The hold-out row above is
the one to quote.

---

## 2. Pair level on the local DrugBank export

**Sample.** The sample has two parts:
* 3 documented pairs for each of 23 DrugBank interaction types, 69 pairs in
  all. The types cover every effect level: named clinical outcome,
  pharmacodynamic effect, exposure change, reduced effectiveness, and
  unspecified.
* 20 random pairs with no record.

The pairs were seeded and sampled at random from pairs where both drugs have
an INN. Labels are off. The engine's output is compared with the source
record it cites, so no gold labels are needed.

| Check | Result |
|---|---|
| Interaction status and outcome set match what the pair's records state | 89/89 (Wilson 0.959–1.0) |
| Citation accuracy: excerpt equal to the cited record's template or statement, and the outcome is the one its record type names | 69/69 (0.947–1.0) |
| Documented outcomes with no record of this pair behind them | 0 of 69 |
| Direction errors: affected drug named without a verified record order or an unambiguous annotation | 0 of 9 claims |
| Abstention on undocumented pairs (no documented outcome shown) | 20/20 (0.839–1.0); all `insufficient_evidence` |
| RU/EN structural consistency of every bilingual text (both present, Cyrillic only in RU, same numerals) | 1568/1568 texts |
| Outcomes changed when the model score is 0.01 vs 0.99 | 0 of 89 pairs |
| Label source down (mocked outage): stated in coverage, DrugBank outcomes unchanged, undocumented pairs `source_unavailable` | 89/89 |

**What these checks establish.** The engine reports what the records say and
nothing more, and the BIO-GINE score has no influence on outcomes, status or
seriousness.

**What they do not establish.** They say nothing about whether DrugBank's
records are clinically correct. The type map that reads each record type
(86 rows) was written by the same author. A unit test checks each row against
DrugBank's template wording, and named-outcome rows are only those whose
template says "risk of…".

**RU/EN consistency.** The check is structural only. Meaning was not compared
by an independent bilingual reviewer.

---

## 3. Mechanism attribution

**The rule.** For an exposure change whose record order is not verified, the
engine names the affected drug only when the inhibitor/inducer–substrate
annotations single out one drug (`mechanistically_supported`).

**How it was checked.** The rule was compared with the two
exposure-decrease types whose drug order **was** verified: type 4 (metabolism
increased, consistency 0.996) and type 75 (serum concentration decreased,
0.970); see `direction.py`. The rule was applied without the record order.

The sample was 1,000 pairs, each with a single reference direction:

| Measure | Result |
|---|---|
| Rule names an affected drug | 606/1000 = 0.606 (0.575–0.636) |
| Rule agrees with the verified order when it names one | 595/606 = 0.982 (0.968–0.990) |
| Rule abstains: both drugs qualify | 76 |
| Rule abstains: no annotation | 318 |

**Caveats:**
* Rule and reference come from the same database. DrugBank may have written
  these records from the same annotations, so this is consistency, not
  independent confirmation.
* The check covers the inducer patterns of verified types. Applying it to the
  inhibitor patterns of unverified types (73, 47) is an assumption.
* About 1 in 55 named drugs disagreed with the reference. That is why the
  status is labelled *mechanistically supported*, not *documented*, and why
  the direction note says the attribution comes from annotations.

---

## 4. Adversarial cases

Each case uses constructed labels marked "[synthetic]" or real local records.

| Case | Result |
|---|---|
| Unrelated adverse effect in the same label (hepatotoxicity sentence without the partner) | not assigned ✔ |
| Outcome and partner in separate sections | no outcome ✔ |
| Plausible but undocumented mechanism (inhibitor–substrate annotations, no record) | hypothesis only, research mode, status `research_prediction_only` ✔ |
| Outdated label next to a current one | only the most recent label is read ✔ |
| Several excerpts from one document | two excerpts, one source document ✔ |
| Contradictory sources (DrugBank exposure increase vs a label "did not significantly alter") | both kept, disagreement stated, no combined conclusion ✔ |
| Ambiguous DrugBank drug order (simvastatin + clarithromycin, both inhibitor and substrate) | no affected drug named ✔ |
| Label names both drugs without asserting an outcome | no label outcome ✔ |

The same cases, and more, are unit tests in `tests/test_v3_outcomes.py`.

---

## 5. Limitations of this validation

1. **No real label text.** All label-level figures come from constructed
   sentences. Real labels are longer and use tables, class statements ("strong
   CYP3A4 inhibitors"), cross-references and section-specific wording. Recall
   on real labels is expected to be lower than on these sets.
2. **Same author.** The same person wrote the rules, the annotation rules, the
   sentences and the gold labels. The hold-out set limits tuning, but not the
   author's knowledge of the rules.
3. **Small samples.** The hold-out set has 40 sentences and 32 annotated
   concepts. The upper interval for the unsupported-claim rate is 0.20.
4. **Single-drug statements naming the partner** (h13) are a known source of
   false outcomes. The verbatim excerpt is the safeguard; the rules are not.
5. **Paraphrase.** Recall depends on a fixed vocabulary of 19 outcome terms
   plus the exposure wording.
6. **DrugBank correctness is not assessed.** The engine is checked to cite
   records faithfully, not to check that the records are right.
7. **Seriousness** comes only from what the source states: a CONTRAINDICATIONS
   section, a BOXED WARNING, or explicit "fatal / life-threatening / serious"
   wording. This was tested on constructed labels only.
8. **No independent clinical review** of any output.
9. **RU/EN meaning** was not compared by an independent bilingual reviewer.

## 6. What would be needed for a real validation

* A sample of current FDA SPL sections for documented pairs, annotated by two
  independent pharmacists with an adjudication step, with agreement measured
  (Cohen's κ).
* Precision and recall per concept on real labels, with class statements
  scored separately.
* A sample of DrugBank records compared against primary sources.
* Independent bilingual review of the user-facing text.
