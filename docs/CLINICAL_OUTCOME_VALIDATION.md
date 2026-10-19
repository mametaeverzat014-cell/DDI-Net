# DDI-Net 3.0 — Clinical Outcome Engine: validation

Revised 2026-10-18. The earlier version (2026-10-16, `label_lexicon/v3`) is preserved in git
history and in `reports/archive/2026-10-16_label_lexicon_v3/`.

**Not a clinical validation.**
- These measurements check whether the engine's rules and sources agree with annotated data.
- They do **not** show that any combination is safe or harmful for a person.
- No qualified independent reviewer was available. Every annotation made by this project was
  made by the AI assistant that also wrote the rules.

**Proportions carry Wilson 95% intervals.**

## Kinds of evidence, kept apart

| Kind | What it is | Where |
|---|---|---|
| **Synthetic** | Sentences, labels and fixtures written for tests | `tests/`, `web/src/pdf/__fixtures__/*synthetic*` |
| **Internal consistency** | The engine against the same database it reads (DrugBank order, annotations) | §E |
| **Historical dataset, independent annotation** | DDI Corpus 2013 (Herrero-Zazo et al.) | §B |
| **Historical dataset, compendium-derived** | CRESCENDDI controls: restricted, local research measurement only | §C |
| **Real-label, internally annotated** | 150 (label, partner) units from historical FDA labels (TAC 2017), annotated by this project before scoring | §A |
| Independent clinical validation | — | **None exists** |

## A. Real-label benchmark (historical FDA labels) — new

**Data.**
- **Source:** the TAC 2017 ADR-track labels (Demner-Fushman et al., Sci Data 2018), from the
  OnSIDES repository at a pinned commit with SHA-256.
- **Dates:** about 2016–2017; **not current labelling**.
- **Sections:** the two the engine reads, Boxed Warning and Warnings and Precautions.

**Unit.**
- One unit is one (label drug, partner drug) pair. The partner is any international name of the
  1,705-drug universe that the engine's label adapter finds in the label.
- The excerpts are exactly what the adapter retrieves: at most 3 sentences per section, with the
  window containing the partner.

**Split** (`scripts/data/build_real_label_benchmark.py`, seed 20261018):
- **Development:** 50 units sampled from 216 candidate pairs in TAC's *train* labels.
- **Evaluation:** 100 units sampled from 209 candidate pairs in TAC's *test* labels.
- The two splits share no label (tested).

**Annotation** (`validation/clinical_outcomes/real_label_benchmark/ANNOTATION_RULES.md`):
- For each unit:
  - the relation: interaction / advice only / no interaction / not applicable (self or
    component);
  - the outcome concepts stated (21 concepts), plus "acceptable" implicit ones;
  - outcomes outside the list;
  - the source-stated seriousness.
- Paraphrases map to concepts.

**Discipline.**
1. **Development and freeze.** `label_lexicon/v3` was run on the development units, its errors
   read, and the rules changed to `label_lexicon/v4` (§F). The rules were then **frozen**:
   `FREEZE.json` holds a SHA-256 over every pattern and constant that decides extraction.
2. **Blind annotation.** The 100 evaluation units were annotated without running the rules.
   The annotation file's SHA-256 (`10df8974…`) was recorded in `FREEZE.json` **before** scoring.
3. **One scoring.** Evaluation was scored once. `scripts/68_v3_real_label_benchmark.py` refuses
   to score evaluation if the rule fingerprint has changed. Nothing was changed after it.

**Results.** `reports/v3_real_label_benchmark_{development,evaluation}.{json,md}`.

| Measure | Development, v3 (before) | Development, v4 (tuned on it) | **Evaluation, v4 (held out)** |
|---|---|---|---|
| Units (interaction / advice / none / n.a.) | 50 (20/10/11/9) | same | 100 (55/7/19/19) |
| Outcome precision, micro | 10/13 | 12/12 | **40/45 = 0.889** (0.765–0.952) |
| Outcome recall, micro | 10/12 | 12/12 | **40/43 = 0.930** (0.814–0.976) |
| Outcome F1, micro / macro | 0.80 / — | 1.0 / 1.0 | **0.909 / 0.856** |
| Units given an outcome where the label states an interaction (pair precision) | 10/11 | 12/12 | **38/42 = 0.905** (0.779–0.962) |
| Unsupported-claim rate (units with a concept neither gold nor acceptable) | — | 0/12 | **3/42 = 0.071** (0.025–0.190) |
| Interaction units given any outcome (pair recall) | 10/20 | 12/20 | **38/55 = 0.691** (0.560–0.797) |
| Abstention on no-interaction and advice-only units | 20/21 | 21/21 | **22/26 = 0.846** (0.665–0.939) |
| Seriousness class correct (units given an outcome) | 11/11 | 12/12 | **39/42 = 0.929** (0.810–0.975) |
| Citation accuracy (matched words present in the quoted excerpt) | 18/18 | 17/17 | **68/68 = 1.0** (0.947–1.0) |

Per concept, evaluation:

| Concept | TP | FP | FN |
|---|---:|---:|---:|
| QT / arrhythmia | 8 | 1 | 0 |
| Serotonin syndrome | 7 | 0 | 0 |
| Hepatotoxicity / raised enzymes | 5 | 0 | 0 |
| Bleeding | 4 | 2 | 0 |
| Exposure increase | 4 | 0 | 3 |
| Bradycardia / block | 3 | 0 | 0 |
| Exposure decrease | 2 | 1 | 0 |
| Reduced effect | 2 | 0 | 0 |
| Myopathy | 2 | 0 | 0 |
| Myelosuppression | 2 | 0 | 0 |
| Coagulation measure | 1 | 0 | 0 |
| Hypertension | 0 | 1 | 0 |

**Reading.**
- On held-out real label text the rules are **precise**: about 9 in 10 extracted outcomes match
  the annotation. Every quoted excerpt contains the matched words.
- About **3 in 10 interactions the label states get no outcome.**
  - Their wording names an outcome outside the 21 concepts ("cardiac valvulopathy", "increased
    cardiovascular adverse effects", "infections").
  - Or it is a class definition ("serotonergic drugs comprise … tramadol").
  - Or it is PK phrasing the rules do not know.
- **The absence of an extracted outcome says nothing about safety.** The site and PDFs say so
  with the exact sentence (§G).
- The development numbers are optimistic by construction (the rules were tuned on them). Only
  the evaluation column is an estimate.

### Correct extractions (evaluation)

| Unit | Label \| partner | Source words | Extracted | Seriousness |
|---|---|---|---|---|
| eva-030 | Effient (prasugrel) \| warfarin | Boxed Warning: "concomitant use of medications that increase the risk of bleeding (e.g., warfarin, …)" | bleeding | boxed ✓ |
| eva-036 | Harvoni \| amiodarone | "Serious symptomatic bradycardia may occur in patients taking amiodarone …" | bradycardia / block | serious wording ✓ |
| eva-016 | Belviq (lorcaserin) \| dextromethorphan | "potentially life-threatening serotonin syndrome … serotonergic drugs, including … dextromethorphan" | serotonin syndrome | serious wording ✓ |
| eva-073 | Samsca (tolvaptan) \| carbamazepine | "can lead to a reduction in the plasma concentration of tolvaptan and decreased effectiveness" | exposure decrease + reduced effect | none ✓ |

### Incorrect extractions (all 8 evaluation errors)

| Unit | Label \| partner | Gold | Extracted | Cause |
|---|---|---|---|---|
| eva-029 | Effient \| clopidogrel | no interaction (comparator arm) | bleeding | Trial-arm rates without an arm cue the rule knows ("in the Effient group and … in the clopidogrel group") |
| eva-049 | Kadcyla \| lapatinib | no interaction (comparator arm) | bleeding | "lapatinib **plus** capecitabine-treated group": "plus" counts as co-use, so the comparator test is skipped |
| eva-070 | Perjeta \| doxorubicin | no interaction (prior exposure) | QT, hypertension, exposure decrease | A population list ("conditions … such as uncontrolled hypertension, … serious cardiac arrhythmia … or a cumulative prior anthracycline exposure to > 360 mg/m² of doxorubicin") read as outcomes |
| eva-055 | Mekinist \| dabrafenib | bleeding, serious wording | bleeding, *none* | "serious adverse reactions of dabrafenib … may occur" is guarded and not counted as serious |
| eva-066 | Olysio \| sofosbuvir | bradycardia acceptable, seriousness none | bradycardia, *serious wording* | Annotation judgement: the serious bradycardia is stated for the three-drug use *with amiodarone*, so the annotator gave the sofosbuvir pair no seriousness of its own. The rule reads the sentence's "serious". Arguably an annotation call, not a rule error. |
| eva-042 | Juxtapid \| atorvastatin | exposure increase | — | "increase the exposure of lomitapide …; therefore … including atorvastatin": the partner is in the clause after the semicolon |
| eva-045, eva-047 | Juxtapid \| lovastatin, simvastatin | exposure increase + myopathy | myopathy only | "approximately doubles the exposure" is not in the PK wording |

These errors are recorded for the next **development** round. Changing the rules now and
re-scoring this set would make it no longer held out.

## B. Label rule on the DDI Corpus 2013 (independent annotation)

- **Data:** the corpus' DrugBank part (CC BY-NC 4.0; evaluation only; not committed).
- **Unit:** sentence × document drug × partner name. A unit counts as interacting if any of its
  mention pairs is annotated `ddi=true`.
- **Split:** Train = development, Test = evaluation.
- **Second look at Test.** The v4 changes were made on real-label development text, not on the
  DDI Corpus. Test has been scored before (v2, v3), so v4 on Test is a **repeated** look. It is
  reported as such, not as a fresh hold-out.

| Measure | v3 dev | v3 eval | **v4 dev** | **v4 eval** |
|---|---|---|---|---|
| Units (interacting / not) | 1,896 (1,044 / 852) | 397 (233 / 164) | same | same |
| Precision of an assigned outcome | 317/444 = 0.714 | 51/61 = 0.836 | 315/440 = 0.716 (0.672–0.756) | **50/61 = 0.820** (0.705–0.896) |
| Non-interacting pairs given an outcome | 127/852 = 0.149 | 10/164 = 0.061 | 125/852 = 0.147 (0.125–0.172) | **11/164 = 0.067** (0.038–0.116) |
| Interacting pairs given an outcome | 317/1,044 = 0.304 | 51/233 = 0.219 | 315/1,044 = 0.302 | **50/233 = 0.215** (0.167–0.272) |

**v4 is not better than v3 on this corpus:** one fewer correct and one more unsupported
assignment on Test, within sampling error. The v4 changes target label-specific layout (bullets,
trial arms, long sentences), which DrugBank text rarely has.

## C. CRESCENDDI comparisons — restricted, local research measurement

CRESCENDDI is **not served** (licence, `docs/DATASET_AUDIT.md`). These numbers come from a
locally rebuilt index and are published as **aggregates only**. `meddra_effect_map/v2` was used.

**DrugBank-derived outcomes vs. CRESCENDDI positive and negative controls** (engine with
DrugBank only; pairs split 50/50 by hash):

| Measure | Development | Evaluation |
|---|---|---|
| Positive-control pairs | 1,956 | 1,996 |
| DrugBank documents the pair | 1,704/1,956 = 0.871 | 1,742/1,996 = 0.873 (0.857–0.887) |
| DrugBank names any clinical outcome | 22/1,943 = 0.011 | 28/1,982 = 0.014 (0.010–0.020) |
| DrugBank outcome or PD effect in the reference event's category | 502/1,943 = 0.258 | 514/1,982 = 0.259 (0.241–0.279) |
| DrugBank outcome in a negative control's category | 0/1,819 | 0/1,844 (0.000–0.002) |

**What CRESCENDDI would add if permission were obtained** (whole universe, named clinical
outcomes):

| | Public build (DrugBank only) | + CRESCENDDI (local) |
|---|---:|---:|
| Pairs with a documented named clinical outcome | **676** | 4,551 |
| Pair × outcome-category combinations | 676 | 7,539 (was 7,463 with map v1) |
| Pairs documented at all | 191,392 | 191,898 |

## D. Constructed pilot and hold-out sets (synthetic)

Run by `scripts/66_v3_outcome_validation.py`; report `reports/v3_outcome_validation.md`.

- **Pilot set, rule level** (75 sentences written by the rules' author): v3 42 TP / 0 FP / 13 FN;
  **v4 43 / 0 / 12**. The extra TP is raised liver enzymes.
- **End to end** (engine plus a mocked label service):
  - before the alias fix, rule and engine agreed on 64/65 sentences; the one miss was
    "acetaminophen" not searched offline;
  - after the fix (P1-9 in the audit), they agree on **65/65**, and the label matcher finds the
    partner in 65/65 (was 61/65). End-to-end TP/FP/FN is 37/0/10.
- **Pair level** (real DrugBank records):
  - **citation accuracy:** 69/69;
  - **unsupported documented outcomes:** 0/69;
  - **RU/EN structural consistency:** 1,636/1,636 bilingual texts (both sides non-empty,
    Cyrillic only in RU, same numerals).

## E. Mechanism attribution (internal consistency)

- **Method:** the rule "unique affected drug of an inhibitor/inducer–substrate finding" is
  computed without the record order. It is compared with the verified drug order of DrugBank
  types 4 and 75.
- **Result:** of 1,000 sampled pairs, the rule names an affected drug in 606. It agrees in
  **595/606 = 0.982** (0.968–0.990). It abstains on 76 ambiguous pairs and 318 with no
  annotation.
- **Caveat:** same database for rule and reference. This shows consistency, not independent
  confirmation.

The chain display rules and their audit are in `docs/DDINET_V3_SCIENTIFIC_AUDIT.md` §4.

## F. What changed from v3 to v4 (development split only)

| Change | Development error that motivated it |
|---|---|
| Sentence splitter keeps "St.", "e.g.", "i.e." … inside the sentence | Outcome halves of St. John's Wort sentences were lost |
| Excerpt window always contains the partner (head plus window around the match) | Coartem \| sotalol: the quoted excerpt lacked the partner |
| Bullets and semicolons split clauses; wider population wording | Coartem \| sotalol: condition bullets became hypokalaemia/hypomagnesaemia |
| `comparator_arm()` | Inlyta \| sorafenib: comparator-arm hypertension |
| "effect … on the QT interval" | Fanapt \| paroxetine missed |
| "increases in transaminases", as its own outcome "Raised liver enzymes" | Yervoy \| vemurafenib missed |

## G. Wording checks

- **No specific outcome.** When no specific clinical outcome is documented (no outcome, or only
  exposure or effect changes), the API sets `no_specific_outcome_text`. It reads exactly:
  - EN: "No specific clinical outcome established from available evidence. This does not mean
    the combination is safe."
  - RU: "По доступным данным конкретное клиническое последствие не установлено. Это не означает,
    что сочетание безопасно."

  The site, Quick PDF and Full PDF show it. A browser test confirmed that all four and the JSON
  agree for warfarin + fluconazole, warfarin + aspirin, simvastatin + clarithromycin and
  metformin + warfarin, in RU and EN.
- **Label-extraction caveat.** Every label-derived outcome carries a note with the §A and §B
  numbers. It is visible on the card and in the Quick PDF.

## Limitations

1. **One annotator,** who also wrote the rules. No inter-annotator agreement and no clinical
   reviewer. The benchmark is an internally annotated research benchmark.
2. **Historical labels** (about 2016–2017): 27 development and 45 evaluation labels. Current labels (openFDA) are
   unreachable from the build container.
3. **Small evaluation set.** The intervals are wide; for example, precision is 0.77–0.95.
4. **Unit sampling.** Partners are limited to the 1,705-drug universe's international names, so
   class-only statements ("CYP3A4 inhibitors") without a named drug are not units.
5. **CRESCENDDI** numbers are local research measurements of data that is not served.
6. The DDI Corpus Test split has now been looked at three times (v2, v3, v4).
