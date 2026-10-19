# Real-label benchmark — annotation rules

## Status

**Internally annotated research benchmark.** One annotator wrote these rules and annotated every
unit: the same AI assistant that wrote the extraction rules. There was no second annotator and no
clinical reviewer. This is **not** an independent or clinical validation.

The annotations were written **before** the extraction rules were run on the units. The
evaluation file was annotated and checksummed before its first scoring.

## Unit

A unit is one *(label drug, partner drug)* pair:
- **Label drug:** the drug whose FDA label it is.
- **Partner drug:** a drug from the project's universe named in that label.
- **Excerpts:** the sentences the engine's label adapter retrieves for the partner, from the Boxed
  Warning and Warnings and Precautions sections. That is at most three per section, with an excerpt
  window that always contains the partner's name.

**Source text:**
- TAC 2017 ADR labels (Demner-Fushman et al., Sci Data 2018), as redistributed in the OnSIDES
  repository, commit `fe6a4a4…`.
- These are historical labels, about 2016–2017, not current labelling.

## Fields annotated

| Field | Values | Rule |
|---|---|---|
| `owner` | international name | The label drug's active ingredient(s), from the brand name. Annotator-supplied, and printed in every label. |
| `relation` | `interaction`, `advice_only`, `no_interaction`, `not_applicable` | See below. |
| `outcomes` | concepts from the list below | Consequences of using the two together that the excerpts state. |
| `acceptable` | concepts | Defensible but implicit, e.g. an anaphoric "this risk". Not required for recall; not counted as unsupported if predicted. |
| `other_outcomes` | free text | Stated consequences outside the concept list, e.g. "increased corticosteroid effects". |
| `seriousness` | `contraindication`, `boxed`, `serious_wording`, `none` | Applies only when the relation is `interaction` or `advice_only`. It is the strongest of: the sentence is in a CONTRAINDICATIONS section; it is in a BOXED WARNING; it states the interaction's consequence as fatal, life-threatening or serious. |

### Relation

- **`interaction`:** the excerpts state that using the two together changes an effect or
  exposure, or causes, risks or worsens a consequence. This includes:
  - a class statement naming the partner as an example ("strong CYP3A4 inhibitors (e.g.
    ritonavir) … may increase …");
  - avoidance justified by a named effect of the partner's class ("avoid with other drugs known to
    prolong QTc (e.g. sotalol)"). By rule A1 that effect, here QT prolongation, is the outcome.
- **`advice_only`:** the excerpts advise against the combination, or adjust the dose for it, but
  state no consequence. Examples: "do not use with strong CYP3A4 inhibitors"; "not studied …
  therefore not recommended".
- **`no_interaction`:** the partner is named for another reason. Examples:
  - comparator or trial arms;
  - premedication or rescue treatment;
  - the history or population of patients;
  - excipient lists;
  - a different drug pair in the same sentence;
  - switching between drugs;
  - nitric oxide named only as "a nitric oxide donor" of another drug.
- **`not_applicable`:** the partner is the label drug itself, its prodrug or active moiety, or a
  component of a combination product. The engine never pairs a drug with itself, so these units
  are reported but excluded from the metrics.

### Outcome concepts

The 21 concepts of `validation/clinical_outcomes/ANNOTATION_RULES.md`:

| Group | Concepts |
|---|---|
| Bleeding and clotting | bleeding, coagulation_measure |
| Heart rhythm | qt_arrhythmia, bradycardia_block |
| CNS and breathing | serotonin_syndrome, respiratory_depression, sedation |
| Blood pressure | hypotension, hypertension |
| Electrolytes and glucose | hyperkalemia, hypokalemia, hyponatremia, hypomagnesemia, hypoglycemia |
| Organ toxicity | myopathy, nephrotoxicity, hepatotoxicity, myelosuppression |
| Effect and exposure | reduced_effect, exposure_increase, exposure_decrease |

A paraphrase is annotated with the concept it expresses: "increases in transaminases" →
hepatotoxicity; "decreased contraceptive efficacy" / "loss of efficacy" → reduced_effect.

## Metrics computed from these annotations (script 68)

Units with `not_applicable` are excluded. A unit's prediction is the set of outcome concepts the
engine extracts from its excerpts (label rule, no-effect filter).

- **Outcome precision / recall / F1:**
  - micro: over (unit, concept);
  - macro: over concepts that occur in the gold or the predictions.
  - Predicted concepts in `acceptable` are neither true nor false positives.
- **Pair-level precision:**
  - The share of units the engine gives a documented outcome where the relation is `interaction`.
  - **Unsupported-claim rate:** the share of units with any prediction that carry a concept which
    is neither gold nor acceptable.
- **Abstention:** on `no_interaction` and `advice_only` units, the share with no prediction.
- **Seriousness accuracy:** on units the engine gives an outcome, its seriousness class compared
  with the annotation.
- **Citation accuracy:** every predicted concept's matched words appear in the quoted excerpt.
