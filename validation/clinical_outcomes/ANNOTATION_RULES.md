# Pilot annotation set for label outcome extraction — rules

`pilot_label_sentences.jsonl` holds 75 **constructed** label-style sentences.
They were written for this project and are not quoted from any real label: no
label text is reproduced from memory. Each sentence is taken as if it appeared
in the owner drug's label and names the partner drug (`partner`).

**What it is not.** It is a pilot set written by the same author as the
extraction rules (`serving/evidence/outcomes.py`, `label_lexicon/v1` then `v2`). It
checks whether those rules behave as intended on known cases, including cases
written to defeat them. It is **not** an independent or clinical validation.
Measured numbers on it describe the rules on this set, not their accuracy on
real labels.

## Rules, fixed before scoring

1. **Annotate an outcome concept** when the sentence states it as a
   consequence of using the owner drug with the named partner. That includes a
   consequence that occurred ("has been reported"), one that may occur ("may
   result in", "increases the risk of"), and one to watch for ("monitor for
   signs of bleeding").
2. **Do not annotate** a concept that the sentence states as absent, unchanged,
   not increased, or unknown ("bleeding risk was not increased", "the risk …
   is unknown").
3. **Do not annotate** a concept that describes a patient population or
   history ("patients with renal failure", "history of bleeding").
4. **Do not annotate** an effect the sentence attributes to one drug alone.
5. **Exposure.** Annotate `exposure_increase` or `exposure_decrease` when the
   sentence states a change in concentration, level, AUC or exposure with the
   partner. A sentence stating both directions for different partners is
   annotated for the named partner only.
6. **Class statements** that name the partner count, in a list or as an
   example.
7. **Concepts.** There are 21 concepts, named as the extraction terms:
   * bleeding, coagulation_measure, qt_arrhythmia, bradycardia_block;
   * serotonin_syndrome, respiratory_depression, sedation;
   * hypotension, hypertension;
   * hyperkalemia, hypokalemia, hyponatremia, hypomagnesemia, hypoglycemia;
   * myopathy, nephrotoxicity, hepatotoxicity, myelosuppression;
   * reduced_effect, exposure_increase, exposure_decrease.

   A paraphrase is annotated with the concept it expresses ("drowsiness" →
   sedation, "kidney damage" → nephrotoxicity), whether or not the lexicon
   knows the word.

## Case types

| Case | Sentences | Purpose |
|---|---:|---|
| positive (incl. serious, monitoring, PK, class list) | 37 | concepts the lexicon is meant to find |
| paraphrase | 11 | concepts in words the lexicon may not know (recall test) |
| negated / no effect / unchanged / unknown / negated after the term | 13 | must not be extracted |
| population | 4 | must not be extracted |
| single-drug effect, unrelated | 3 | must not be assigned to the pair |
| mechanism only, no outcome | 5 | must not be extracted |
| ambiguous or mixed exposure | 2 | abstention vs recall |

These groups sum to 75, the number of sentences. The exact case of each
sentence is in its `case` field.

## Hold-out set

`holdout_label_sentences.jsonl` holds 40 further constructed sentences.

* They were written after `label_lexicon/v2` was frozen, under the same rules.
* They were scored once, and no rule was changed afterwards. The SHA-256 of
  the file is recorded in `reports/v3_outcome_validation.json`.
* The development set above was used to find v1's errors. Scores on it after
  the v2 changes are not held out.

The results are in `docs/DDINET_V3_CLINICAL_OUTCOMES_VALIDATION.md`.
