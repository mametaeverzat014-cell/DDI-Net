# DDI-Net 3.0 — Clinical Outcome Engine: architecture and safety boundaries

Written before implementation, after reading:

* the evidence engine (`serving/evidence/`);
* the openFDA, RxNorm and DrugBank adapters;
* the mechanism module;
* the frozen model context;
* the explanation pipeline;
* the site (`web/src/`) and the PDF/JSON export (`web/src/pdf/`);
* `docs/DDINET_V3_SCIENTIFIC_LIMITATIONS.md`.

Branch `feature/ddinet-v3`, starting at `c330cf0`.

---

## 1. What exists and is reused unchanged

| Component | Where | Reused for |
|---|---|---|
| DrugBank interaction records (TDC export, 191,392 pairs, 86 types) | `records.py`, `store.py` | the main local structured source of interaction-specific statements |
| Direction audit (which types' drug order is verified) | `direction.py` | outcome direction: only verified or symmetric types name the affected drug |
| openFDA label excerpts, one per distinct sentence, partner named in the sentence | `adapters/openfda.py`, `labels.py` | label-based outcome extraction, from the excerpt text only |
| Drug–protein annotations and mechanism findings (inhibitor/inducer–substrate) | `mechanism.py` | the mechanism links of the outcome chains |
| Frozen BIO-GINE block | `model_context.py` | untouched; shown as a separate research layer |
| Report, multi-drug, graph endpoints; rate limits; cache | `api_v3.py`, `engine.py` | the new `outcomes` block rides on the existing responses |
| Site report parts, PDF and JSON export, evidence grouping | `web/src/` | extended, not rewritten |

The frozen model, checkpoint, predictions and metrics are not touched.

## 2. What the sources can and cannot say

**DrugBank (TDC export).** Every record is one of 86 standard sentences. They
fall into five kinds, and the engine keeps the kind:

| Kind (`effect_level`) | Example template | What it supports |
|---|---|---|
| `clinical_outcome` | "The risk or severity of **bleeding** can be increased when #Drug1 is combined with #Drug2." (66); QTc prolongation (33); hyperkalemia (42); hypotension (56); hypertension (31); heart failure (50); hypersensitivity reaction (86) | a named clinical outcome for the pair |
| `pharmacodynamic_effect` | "#Drug1 may increase the **anticoagulant activities** of #Drug2." (6); QTc-prolonging, CNS-depressant, respiratory-depressant, serotonergic, nephrotoxic, hepatotoxic … activities | a stronger (or weaker) pharmacological effect. **Not** a statement that the corresponding harm occurs: "anticoagulant activities increased" is not "bleeding" |
| `pharmacokinetic_change` | "The serum concentration of #Drug2 can be increased …" (73); metabolism (47, 4), excretion (72, 65), absorption, bioavailability | a change in exposure, **without** a documented clinical outcome |
| `reduced_effectiveness` | "The therapeutic efficacy of #Drug2 can be decreased …" (70); decreased antihypertensive, anticoagulant, diuretic … activities | a weaker intended effect |
| `unspecified_adverse` | "The risk or severity of **adverse effects** can be increased …" (49, a third of all records) | an interaction is documented, but its consequence is not named |

There are three more facts about these records:

* No DrugBank record carries a severity.
* The export does not state what a record is based on.
* For most types the drug order is unverified, so which drug is affected is not
  stated.

**FDA labels (openFDA).** A label excerpt is a sentence of drug A's label that
names drug B. It comes from Boxed Warning, Contraindications, Warnings
(and Precautions), Precautions, or Drug Interactions.

* An outcome is extracted only from **that same sentence**.
* It is extracted only when the sentence contains an outcome term from a fixed,
  versioned lexicon, the term is not negated, and the term is not a description
  of a patient population ("in patients with renal impairment").
* "No effect" sentences never yield an outcome.
* **Adverse Reactions is deliberately not scanned.** It lists a drug's general
  adverse reactions, and those must never be assigned to a pair.
* **Clinical Pharmacology** was investigated and deferred. Its sentences that
  name a partner are mostly pharmacokinetic study results. Using them would
  need a new evidence category and status. They could also not be tested
  against real labels from the development container, where openFDA is blocked.

**Annotations (DrugBank/ChEMBL drug–protein roles).** These are facts about
each drug alone. They can explain *how* a documented exposure change may arise
(A inhibits CYP2C9; B is a CYP2C9 substrate). They never create an outcome on
their own. A shared protein or pathway is never treated as a cause.

**BIO-GINE.** A research score of resemblance to documented pairs. It never
creates, removes, or grades an outcome, and it is never a probability of harm.

## 3. Evidence flow

```
DrugBank records ─┐   type → outcome map (86 rows, versioned)
FDA label excerpts ┼─► OutcomeSupport (verbatim excerpt / template, document, section,
                   │                    method, direction, source-stated seriousness)
                   │        │ group by (category, effect)            [one outcome, many supports;
                   │        ▼                                          documents counted, not excerpts]
                   │   ClinicalOutcome ── evidence_status: documented | mechanistically_supported
                   │        │                                          | hypothesized
annotations ───────┴─► MechanismChain: drug → protein → effect → outcome, each link classified
                            │
                            ▼
                   OutcomeReport: interaction_status, outcomes, chains, seriousness,
                                  evidence coverage, abstention reason
                            │
            ┌───────────────┼──────────────────────┐
         website         PDF (Quick, Full)       JSON (verbatim payload)
```

Each outcome's support carries:

* the exact words: a verbatim label excerpt, or DrugBank's template as it
  appears in the record;
* the evidence-record ID, document ID, source name, URL, section and
  retrieval date;
* the extraction method (`drugbank_type_map/v1:type=66`,
  `label_lexicon/v2:term=bleeding`; v1 was the first development round,
  see DDINET_V3_CLINICAL_OUTCOMES_VALIDATION.md).

The site, the PDF and the JSON all read the same `outcomes` block of the same
API response.

## 4. States, kept separate

**Outcome evidence status:**

| State | Meaning |
|---|---|
| `documented` | a source states this consequence for this pair |
| `mechanistically_supported` | a documented exposure change for which verified drug–protein roles identify which drug is affected. The direction comes from the annotations, not from the DrugBank order, and is labelled so |
| `hypothesized` | only annotations suggest it (e.g. inhibitor–substrate on an enzyme), with no documented outcome. Shown in Research mode only |

**Pair interaction status**, decided by evidence states alone and never by a
score threshold:

| State | Rule |
|---|---|
| `documented_interaction` | at least one documented outcome of kind clinical_outcome, pharmacodynamic_effect or reduced_effectiveness |
| `documented_outcome_unclear` | documented interaction evidence exists, but only exposure changes, "adverse effects" or label mentions without an extractable outcome |
| `research_prediction_only` | nothing documented; only mechanism hypotheses |
| `insufficient_evidence` | nothing documented and no hypothesis |
| `source_unavailable` | nothing documented, and a source that could have documented it was unavailable |

**Seriousness**, only as a source states it:

| Class | Source basis |
|---|---|
| `documented_contraindication` | the label sentence is in the CONTRAINDICATIONS section |
| `explicit_serious_warning` | the sentence is in a BOXED WARNING, or itself uses "fatal", "life-threatening", "death" or "serious" (not negated), quoted |
| `documented_no_standard_severity` | documented, but no source classifies severity: "Severity not established from available evidence." / «Степень серьёзности не установлена по доступным данным.» |
| `not_applicable` | for hypotheses and absent evidence |

**Evidence strength** is qualitative and separate from seriousness:

* "official label statement";
* "database standard sentence (basis not stated)";
* both;
* "annotation-based hypothesis".

No percentage is shown. Extraction confidence is reported only as measured on
the pilot set (§6), and is labelled pilot.

## 5. Mechanism-to-outcome chains

Chain: actor drug → protein (enzyme or transporter) → pharmacological effect
(exposure of the affected drug) → outcome. Each link carries one provenance
class:

| Link | Class |
|---|---|
| drug → protein, protein → drug | `verified_annotation` (DrugBank/ChEMBL role, with source and PMIDs) |
| protein → exposure change | `documented` if a documented exposure-change record exists for the pair (its direction from the annotations), else `plausible_unconfirmed` |
| exposure change → clinical outcome | `documented` only if one label sentence states both; `plausible_unconfirmed` if the outcome is documented separately; absent otherwise |

There are three further rules:

* An outcome with no chain is shown with the sentence "The available evidence
  does not establish a mechanism."
* A chain with no documented outcome is research-only.
* No link is drawn for a shared protein without an inhibitor/inducer–substrate
  configuration, or for a shared pathway.

## 6. Validation plan

* **Pilot annotation set of constructed label-style sentences**, marked as
  constructed (no real label text is reproduced from memory). It covers:
  * positives;
  * negated outcomes;
  * population phrases;
  * unrelated adverse effects in the same label;
  * two drugs in different sentences;
  * class lists;
  * "no effect" wording.

  Annotation rules are written down before scoring. Measured on it: precision,
  recall, unsupported-claim rate, citation accuracy, abstention, and RU/EN
  consistency. It is explicitly **not** an independently validated clinical
  benchmark.
* **End-to-end pair set from the local DrugBank export:**
  * documented outcomes;
  * exposure-only records;
  * unspecified adverse;
  * ambiguous order;
  * no evidence;
  * mocked unavailable openFDA;
  * synthetic duplicated labels.

  Checked on it: interaction status, abstention, direction errors, citation
  accuracy, and mechanism attribution against the store.
* **The DrugBank type map is a curated table.** Its 86 rows are reviewed against
  the template text, and a test checks that every type is mapped and that
  clinical-outcome rows name a term present in the template.

## 7. Safety boundaries

* No outcome without a source sentence supporting it for this pair.
* No general adverse reaction of one drug is assigned to a pair.
* Co-mention is not causation.
* No direction from the DrugBank order unless audited, and none from a label
  co-mention.
* No severity from section position alone, except Contraindications and Boxed
  Warning, which are the source's own classification. No severity from the
  model, and never "safe".
* No global or multi-drug risk score, and no additive or three-way inference.
* No advice, dosing, start or stop. A research and educational tool.
* Deterministic, no language model, and no paid service.
* No network call during PDF export.
