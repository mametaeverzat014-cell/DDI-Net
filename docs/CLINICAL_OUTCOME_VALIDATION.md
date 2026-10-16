# DDI-Net 3.0 — Clinical Outcome Engine: validation against independent data

**Not a clinical validation.** It measures whether the engine's rules and sources agree with
independently annotated reference data, and how much the new evidence changes coverage. It does
**not** show that any combination is safe or harmful for a person, and it makes no claim about
real FDA labels: openFDA is unreachable from the build container.

Reproduce:
- `python scripts/67_v3_reference_validation.py` writes `reports/v3_reference_validation.{json,md}`.
  It needs network access to GitHub to fetch the pinned DDI Corpus the first time.
- `python scripts/66_v3_outcome_validation.py` runs the earlier constructed pilot sets, the
  pair-level checks and the adversarial cases. It writes `reports/v3_outcome_validation.*`;
  details are in `docs/DDINET_V3_CLINICAL_OUTCOMES_VALIDATION.md`.

Proportions carry Wilson 95% intervals.

## The validation datasets

| Dataset | Annotated by | Role | Development / evaluation separation |
|---|---|---|---|
| **DDI Corpus 2013**, DrugBank part (CC BY-NC 4.0; not committed) | Corpus authors (Herrero-Zazo et al.), independent of this project | Real interaction text: does the label rule assign an outcome only to pairs annotated as interacting? | Official split: **Train = development**, **Test = evaluation** |
| **CRESCENDDI** positive and negative controls | Reference-set authors (Kontsioti et al.), from BNF, Micromedex and ANSM | Does the DrugBank-derived outcome layer name the outcomes a clinical reference lists? Does it contradict negative controls? | Pairs split 50/50 by `sha256("drugA|drugB")[0] < 128` → development, else evaluation |
| Constructed pilot set (75) and hold-out set (40) | This project, rules in `validation/clinical_outcomes/ANNOTATION_RULES.md` | Rule behaviour on known and adversarial wording | Hold-out written after the rules were frozen |

**Annotation rules of the external sets are their authors'.**
- *DDI Corpus:* a mention pair is `ddi=true` when the sentence states an interaction between
  the two, typed mechanism / effect / advise / int. Otherwise it is `ddi=false`.
- *CRESCENDDI:* a positive control is a pair in all three compendia plus an event mapped from the
  compendium text. A negative control is a pair plus an event with no known association.

This project only maps them:
- **DDI Corpus unit:** one unit per sentence, document drug and partner drug name; it counts as
  interacting if any of its mention pairs is.
- **CRESCENDDI:** drug names are mapped exactly to DrugBank IDs, and MedDRA terms are grouped into
  effects by `meddra_effect_map/v1`.

**Evaluation discipline.**
- `label_lexicon/v2` was measured on **both** DDI Corpus splits before any change; that record is
  kept in `validation/clinical_outcomes/ddi_corpus_label_lexicon_v2.json`.
- The v3 change (wider "no effect" wording) used errors seen on **Train only**. Test was then
  scored once with v3.
- The CRESCENDDI comparisons involved no rule change.

## A. Label rule on the DDI Corpus

**Unit and scope:**
- The unit is a sentence of a DrugBank-part document, the document's drug (as the label owner)
  and a partner of type `drug`.
- Brands and drug classes are excluded, because the engine matches international names.
- The question is: would the rule (an outcome term in the clause naming the partner, and no
  no-effect wording) assign a documented outcome to this pair?

| Measure | v2, development | v2, evaluation | **v3, development** | **v3, evaluation** |
|---|---|---|---|---|
| Units (interacting / not) | 1,896 (1,044 / 852) | 397 (233 / 164) | 1,896 (1,044 / 852) | 397 (233 / 164) |
| Precision of an assigned outcome | 318/465 = 0.684 | 51/62 = 0.823 | 317/444 = **0.714** (0.670–0.754) | 51/61 = **0.836** (0.724–0.908) |
| Outcome assigned to a co-mentioned, non-interacting pair | 147/852 = 0.173 | 11/164 = 0.067 | 127/852 = **0.149** (0.127–0.175) | 10/164 = **0.061** (0.033–0.109) |
| Interacting pairs with an extracted outcome (coverage) | 318/1,044 = 0.305 | 51/233 = 0.219 | 317/1,044 = 0.304 (0.277–0.332) | 51/233 = **0.219** (0.171–0.276) |

Coverage by the corpus' interaction type (v3, evaluation):

| Type | Coverage |
|---|---|
| mechanism | 33/111 (0.22–0.39) |
| effect | 12/55 (0.13–0.34) |
| advise | 3/55 |
| int | 3/12 |

**Sensitivity check.** The owner is often named by brand (FACTIVE for gemifloxacin), and the
script cannot map brands. If a partner counts as interacting whenever any of its mention pairs is,
evaluation precision is 53/61 = 0.869, and 8/136 = 0.059 non-interacting pairs get an outcome.

**Reading:**
- On real interaction text the rule is **precise but low-coverage**. About 1 in 6 assigned
  outcomes (evaluation) to 1 in 3.5 (development) is for a pair the corpus does not annotate as
  interacting.
- Typical causes, seen on development text:
  - a partner named in an example list (e.g. "CYP3A4 inhibitors such as …"), which the corpus
    annotates at class level;
  - a sentence about another drug pair that names the partner;
  - no-effect wording the filter still misses.
- About 70–78% of interacting pairs get no outcome; their wording names no outcome or exposure
  term the rule knows. **Absence of an extracted outcome therefore says nothing about safety.**
  The site and PDF already say so.
- The development/evaluation gap (0.71 vs 0.84 precision) is larger than sampling error alone
  would suggest; the documents differ between splits. Use the wider range, not a single number.

## B. DrugBank-derived outcomes vs. CRESCENDDI controls

Engine with **DrugBank only** (reference set removed, labels off). Pairs: 3,952 positive-control
pairs and 3,663 negative-control pair–events in the 1,705-drug universe.

| Measure | Development | **Evaluation** |
|---|---|---|
| Positive-control pairs | 1,956 | 1,996 |
| DrugBank has any record for the pair | 1,704/1,956 = 0.871 | 1,742/1,996 = **0.873** (0.857–0.887) |
| DrugBank names **any** clinical outcome for the pair | 22/1,943 = 0.011 | 28/1,982 = **0.014** (0.010–0.020) |
| … in the same category as a reference event | 22/1,943 | 28/1,982 = 0.014 |
| DrugBank names an outcome **or a pharmacodynamic effect** in that category | 502/1,943 = 0.258 | 514/1,982 = **0.259** (0.241–0.279) |
| Reference events matched by the same DrugBank effect | 26/4,117 | 34/4,102 = 0.008 |
| Negative controls whose pair is documented in DrugBank | 334/1,819 | 400/1,844 = 0.217 |
| DrugBank outcome in a negative control's event category | 0/1,819 | **0/1,844** (0.000–0.002) |

**Reading:**
- DrugBank documents almost nine in ten of these clinically recognised pairs. But in the TDC
  export it **names a clinical outcome for about 1%**: most templates state a pharmacokinetic or
  pharmacodynamic change.
- Even counting pharmacodynamic effects, about three quarters of these pairs have no DrugBank
  outcome or effect in the category of their reference adverse event. This is the gap CRESCENDDI
  fills.
- No DrugBank outcome fell in a negative control's category. This test has **low power**, because
  DrugBank names so few outcomes.

## C. Coverage change from integrating CRESCENDDI

Whole 1,705-drug universe, documented **named clinical outcomes** (not PK/PD effects, not
hypotheses):

| | DrugBank only | + CRESCENDDI |
|---|---:|---:|
| Pairs with at least one documented named clinical outcome | 676 | **4,551** (+3,875) |
| Pair × outcome-category combinations | 676 | **7,463** |
| Pairs documented at all | 191,392 | 191,898 (+506 not in DrugBank) |

Selected categories (pairs, DrugBank only → + CRESCENDDI):

| Category | Pairs |
|---|---|
| Bleeding / clotting | 128 → 1,077 |
| Heart rhythm | 442 → 1,495 |
| Blood pressure | 47 → 1,059 |
| Electrolytes | 6 → 926 |
| Kidney | 0 → 638 |
| CNS sedation | 0 → 579 |
| Respiratory depression | 0 → 539 |

The full table is in the report.

Examples (local API, labels unavailable):
- **Warfarin + fluconazole:** "exposure change only" becomes **documented bleeding** (CRESCENDDI:
  Haemorrhage). The exposure-to-bleeding chain link stays *plausible, unconfirmed*.
- **Simvastatin + clarithromycin:** gains **myopathy / rhabdomyolysis**.
- **Warfarin + aspirin:** gains documented bleeding beside DrugBank's pharmacodynamic record. The
  DrugBank record still never becomes "bleeding" on its own.

## What is verified by tests

- Ingestion (`tests/test_v3_reference_sets.py`):
  - schema rejection with reasons;
  - exact-only mapping, with unmapped names reported;
  - unordered de-duplication; self-pair and positive/negative conflict removal;
  - no severity ratings carried over;
  - deterministic output;
  - checksum enforcement;
  - the committed index matching its manifest and pinned commit;
  - every MedDRA term mapped.
- Engine:
  - reference outcomes are pair-specific and cited, with no severity;
  - the outcome→chain link is never "documented";
  - DrugBank PD records never become bleeding;
  - a reference-only pair is documented;
  - pairs not listed gain nothing;
  - multi-drug counts are kept separately.
- Manifest (`tests/test_sources_manifest.py`): every source described; integrated sources have a
  directly read licence and a matching checksum; evaluation data is never committed.
- Site and PDF:
  - a separate CRESCENDDI document with the MedDRA term;
  - "grades not reproduced";
  - no compendium grade words;
  - geometry checks on the new reports.

## Limitations

1. **No real FDA label text.** The label rule has been measured on DrugBank interaction text
   (similar register) and on constructed sentences, not on labels.
2. **CRESCENDDI's own correctness is not assessed.** It would need the compendia. It is a
   2018–2019 snapshot of three European and US compendia, limited to pairs all three share, with
   events mapped by its authors (automated plus manual).
3. **Severity** stays "not established" for CRESCENDDI outcomes. The compendia grades exist but
   are proprietary and not reproduced.
4. **Mapping loss.** 62 of 454 CRESCENDDI drug names do not map to the universe. US names
   (Rifampin, Valproate) are left unmapped rather than guessed.
5. **MedDRA grouping.** `meddra_effect_map/v1` was written by this project's author and reviewed
   by no one else. The original term is always shown.
6. **DDI Corpus mapping.** The unit and owner mapping (file name) are this project's choices; the
   sensitivity analysis shows how much they move the numbers.
7. **No independent clinical review** of any output.
