# DDI-Net 3.0 — Scientific reliability audit (clinical evidence verification)

Audit date: 2026-10-18. Branch `feature/ddinet-v3`. Scope: everything that decides what the site,
the Quick and Full PDFs and the JSON say about a drug pair.

That covers:
- **Outcome engine:** `serving/evidence/outcomes.py` and the schemas;
- **Sources:** DrugBank templates, label extraction, RxNorm names, annotations and Reactome;
- **Reference sets:** CRESCENDDI ingestion;
- **Reasoning and presentation:** chains, seriousness, provenance, the frontend and PDF
  renderers;
- **Measurement:** the validation scripts.

**What this audit is and is not.**
- It was done by the AI assistant that wrote the rules, with no clinical or independent reviewer.
- Every metric below is labelled with its kind of evidence:
  - **Synthetic:** sentences or fixtures written for tests.
  - **Internal consistency:** the engine against the same database it reads.
  - **Historical dataset:** independently annotated text (DDI Corpus 2013), or controls derived
    from compendia (CRESCENDDI).
  - **Real-label, internally annotated:** historical FDA label sentences, annotated by this
    project before scoring.
- **No result here is an independent clinical validation.**

Detail and numbers:
- `docs/CLINICAL_OUTCOME_VALIDATION.md` (metrics);
- `docs/DATASET_AUDIT.md` (licences, CRESCENDDI mapping, MedDRA review);
- `docs/DATA_PROVENANCE.md` (files and pins).

## 1. What the engine must be able to say, and how each is kept apart

| Class | Where it comes from | How it is shown | Never |
|---|---|---|---|
| A. Documented clinical outcome | A label sentence naming the partner and an outcome; a DrugBank template naming an outcome (7 of 86 types) | "What could happen?" card, quoted source, extraction note | Inferred from a PK or PD change |
| B. PK / PD change | DrugBank templates; label PK sentences | Card marked "change in exposure" or "change in effect", with "not, by itself, a documented clinical outcome" | Shown as harm |
| C. Verified mechanism | DrugBank 5.1 / ChEMBL drug–protein roles | Chain steps marked "verified biological annotation" | Shown as documented for the pair |
| D. Hypothesis | Roles only, nothing documented for the pair | Research mode only | In Simple mode |
| E. BIO-GINE prediction | Frozen model M4 | Block E, research note; never in "What could happen?" | Converted into a probability of harm |
| F. Insufficient evidence | Nothing documented | "No specific clinical outcome established from available evidence." + "This does not mean the combination is safe." | "Safe" |

## 2. Defects found, by priority

### P0 — fixed

**P0-1 · CRESCENDDI records were redistributed without clear rights.**
- **What it was:** The derived CRESCENDDI index was committed to git. It holds 11,882 pair–event
  records mapped from BNF and Micromedex interaction text.
- **Where it went from git:**
  - copied into both Docker images;
  - served by the API as outcome evidence;
  - embedded in web test fixtures and in four sample PDFs.
- **Why that is a problem:**
  - The MIT licence covers the authors' "software and associated documentation files".
  - The records derive from BNF (Nov 2018) and IBM Micromedex (Sep 2018), whose terms do not
    clearly permit redistributing derived records.
  - The ANSM Thésaurus terms and the figshare licence could not be read.
  - Details are in `docs/DATASET_AUDIT.md` §CRESCENDDI.
- **Fix:**
  - **Index:** moved to the git-ignored `data/restricted/crescenddi/`. It is used only with
    `DDINET_ENABLE_CRESCENDDI=1` and only if the file exists, so it is off by default.
  - **Images:** removed from both Dockerfiles and `.dockerignore`.
  - **Sources manifest:** status `restricted_local_only`.
  - **Engine tests:** use a labelled **SYNTHETIC** reference payload.
  - **Web fixtures:** relabelled SYNTHETIC; no CRESCENDDI-specific IDs or commit remain.
  - **Sample PDFs:** removed.
  - **Validation report:** aggregate counts only; the example pairs from negative controls were
    dropped.
- **Kept:**
  - the ingestion script;
  - the committed `MANIFEST.json` (checksums and counts only), so a local rebuild is verifiable;
  - the engine code path, for local research.
- **Tests that guard it:**
  - `tests/test_sources_manifest.py::test_restricted_sources_are_never_committed_or_shipped`;
  - `tests/test_docker_context.py::test_no_dockerfile_copies_restricted_data`;
  - `tests/test_v3_reference_sets.py::test_public_build_never_includes_crescenddi`.
- **Not fixed (your decision):** the file remains in the **git history** of commits
  `8a1e689`…`7ac6299` on this branch. Removing it needs a history rewrite and a force-push,
  which cannot be undone.

### P1 — fixed

| ID | Defect | Found by | Fix | Test |
|---|---|---|---|---|
| P1-1 | The sentence splitter broke after "St." (St. John's Wort) and similar abbreviations. The outcome half of a label sentence was then never read together with the partner. | Real-label development split | `ABBREVIATION_END` merge in `split_sentences` | `test_abbreviation_does_not_end_a_sentence` |
| P1-2 | Excerpts were cut at 600 characters from the sentence start. In long label sentences the quoted text did not contain the partner (citation failure; e.g. Coartem \| sotalol). | Real-label development | `excerpt_of`: sentence head plus a window around the partner | `test_long_sentence_excerpt_always_contains_the_partner`; benchmark check that every excerpt names its partner |
| P1-3 | Condition bullets ("risk factors * hypokalemia * hypomagnesemia * concomitant use of …") became documented electrolyte outcomes of the drug named in the last bullet. | Real-label development | Bullets and semicolons split clauses; wider population wording (`label_lexicon/v4`) | `test_condition_bullet_is_a_population_not_an_outcome` |
| P1-4 | Trial comparator arms ("…% of patients receiving X") became documented outcomes of the pair. | Real-label development (Inlyta \| sorafenib) | `comparator_arm()`: trial statistics plus an arm cue and no co-use word, then no outcome | `test_comparator_arm_is_not_an_interaction`, `test_co_use_wording_is_not_a_comparator_arm` |
| P1-5 | `meddra_effect_map/v1` grouped terms under broader or different outcomes: syncope → "low blood pressure"; raised creatinine → "kidney injury"; raised liver enzymes → "liver injury"; abnormal ECG → arrhythmia; cardiac output → heart failure. | MedDRA review (DATASET_AUDIT) | `meddra_effect_map/v2`; haemodynamic and ECG measures are pharmacodynamic | `test_meddra_map_v2_does_not_broaden_terms` |
| P1-6 | Pairs with only an exposure or effect change showed outcome cards but no statement that no clinical outcome was established. | Phase 4 requirement | `no_specific_outcome_text` (exact EN/RU wording) in the JSON, site, Quick and Full PDF | `test_no_specific_outcome_wording_is_exact`, `test_pk_record_with_unambiguous_roles_is_mechanistically_supported` |
| P1-7 | The label-extraction caveat sat inside a collapsed "show source" panel. It also still said "not measured on FDA labels". | Phase 7 | Visible note on each label-derived card (site and Quick PDF) with the real-label and DDI Corpus numbers | web tests, PDF geometry |
| P1-8 | Two chain problems. (a) When the affected drug was read off the protein roles, the exposure step was marked **documented**: circular, because the same annotations drew the chain. (b) Chains whose final exposure→outcome step is unconfirmed were listed under "Verified links". | Mechanism audit (§4) | (a) The step is `verified_annotation` and says the attribution comes from the roles. (b) The summary says the route is not confirmed; the heading says each step is marked separately. | `test_chain_never_presents_an_unconfirmed_route_as_established` |
| P1-9 | Offline, labels were searched only by the INN. A US label saying "acetaminophen" did not match paracetamol. | Pilot end-to-end recount (64/65 agreement) | The curated US/INN aliases (`lexicon.ALIASES`) are added to the label search terms | Pilot end to end: 65/65 agreement, partner found 65/65 (was 61/65) |

### P2 — open, documented (not fixed in this pass)

| ID | Issue | Evidence | Why not fixed now |
|---|---|---|---|
| P2-1 | PK wording missed: "approximately doubles the exposure to X"; "increase the exposure of A …; therefore … including X" (the partner sits in a later clause). | Evaluation errors eva-042, eva-045, eva-047 | Found on the held-out set. Fixing it there would tune on evaluation data. Next development round. |
| P2-2 | Comparator and history residue: "X plus Y-treated group" (the word "plus" counts as co-use); trial rates without an arm cue; "prior exposure to X" in a population list. | eva-029, eva-049, eva-070 | Same reason as P2-1. |
| P2-3 | Seriousness wording: "serious adverse reactions of dabrafenib … may occur" was not recognised (it is guarded). "Mortality" is not in `SERIOUS_WORDS`. | eva-055 (wrong class); eva-085 (no prediction) | Same reason as P2-1. |
| P2-4 | 62 of 454 CRESCENDDI names are unmapped. 7 are plain synonyms of in-universe drugs (dothiepin, fusidate, mefenamate, methotrimeprazine, valproate, chlorthalidone, tiaprofenate). Isosorbide, fluticasone, candesartan, azilsartan and the magnesium salts are ambiguous. | DATASET_AUDIT mapping table | CRESCENDDI is local-only now. New aliases need a reviewed decision, not a guess. |
| P2-5 | On the DDI Corpus Test split, v4 is slightly worse than v3: precision 50/61 vs 51/61; non-interacting pairs given an outcome 11/164 vs 10/164. | `reports/v3_reference_validation.md` | Disclosed. This was a second look at Test after development changes; the difference is one pair. |
| P2-6 | The real-label text is historical (TAC 2017 labels, about 2016–2017); current openFDA labels are unreachable here. | — | External access. |
| P2-7 | One annotator, the rule author; no second annotator; no clinical reviewer. | — | No reviewer available. The benchmark is labelled "internally annotated". |
| P2-8 | DrugBank drug order is unreliable for most PK types. Only types 4 and 75 are verified (`direction.py`). Mechanism attribution is consistency with the same database. | `reports/v3_tdc_direction_audit.md`; §4 | Inherent to the source. |

## 3. Reproduced metrics (independent recount on 2026-10-18)

| Previously reported | Recount | Note |
|---|---|---|
| DDI Corpus Test, v3: 51/61 precision, 10/164 co-mentions given an outcome, 51/233 coverage | Archived run reproduces it (`reports/archive/2026-10-16_label_lexicon_v3/`) | v4 now: 50/61, 11/164, 50/233 |
| DDI Corpus Train, v3: 317/444, 127/852 | v4: 315/440, 125/852 | Development split |
| Pairs with a named clinical outcome: 676 → 4,551 with CRESCENDDI | 676 → 4,551 (local research measurement only) | Public build: 676 (CRESCENDDI not served) |
| Pair × category: 676 → 7,463 | 676 → 7,539 | +76 from `meddra_effect_map/v2`: syncope is now its own outcome in `cardiovascular_other` (175 → 251) |
| Documented pairs 191,898 | 191,392 in DrugBank + 506 CRESCENDDI-only | Public build: 191,392 |
| Mechanism attribution, types 4/75: 595/606 | 595/606 = 0.982 (0.968–0.990); the rule names a drug in 606/1,000 | Consistency with the same database, not independent confirmation |
| Pilot rule level 42 TP / 0 FP / 13 FN | 43 / 0 / 12 (v4 adds liver enzymes) | Constructed sentences |

## 4. Mechanism attribution audit (Phase 5)

Each link type and what licenses it:

| Link | Provenance value | Licensed by | Status |
|---|---|---|---|
| Drug A → protein (inhibitor / inducer) | `verified_annotation` | DrugBank 5.1 / ChEMBL curated role | Verified pharmacology (single-drug fact) |
| Protein → drug B (substrate) | `verified_annotation` | Same | Verified pharmacology |
| Protein → exposure change of B | `documented` only when a source names B's change. `verified_annotation` when the change is documented but B was picked from the roles (fixed, P1-8). Otherwise `plausible_unconfirmed`. | DrugBank PK record with verified order, or a label sentence | Correct after P1-8 |
| Exposure change → outcome | `documented` only when **one** label sentence states both. Otherwise `plausible_unconfirmed`. | Label sentence | No other source can make it documented |
| Shared Reactome pathway | Not a link | — | Background only; never causal (`MECHANISM_ONTOLOGY.md`) |

**Checks run.**
- No chain is shown outside Research mode unless something in it is documented for the pair.
- No outcome link is ever `documented` from DrugBank or a reference set alone. This holds by
  construction and is tested.
- Direction is never taken from the DrugBank record order except for the two verified types.
- Ambiguous roles (both drugs inhibitor and substrate) name no affected drug (tested).
- A chain whose essential link is unconfirmed now says so in its own summary, in both languages.

**Attribution metric** (internal consistency):
- The "unique affected drug" rule agrees with the verified record order on 595 of 606 pairs where
  it names a drug (0.982, 95% CI 0.968–0.990).
- It abstains on 394 of 1,000: 76 ambiguous, 318 with no annotation.

## 5. Before → after (this pass)

| Aspect | Before | After |
|---|---|---|
| CRESCENDDI | Committed, in the image, served, in fixtures and PDFs | Local research only; not committed, not shipped, not served |
| Label rule | `label_lexicon/v3`, measured only on DrugBank text | `label_lexicon/v4`. Frozen; scored once on 100 held-out real FDA label units: outcome precision 40/45, recall 40/43, citations 68/68 |
| Real-label measurement | None ("not measured on FDA labels") | Development 50 + evaluation 100 units, annotated before scoring, checksummed |
| No-outcome wording | "No supported outcome could be identified…" | Exact required sentence (EN/RU) + "does not mean safe"; also shown when only PK/PD changes exist |
| Label caveat | Hidden in a collapsed panel | Visible on each label-derived card and in the Quick PDF |
| MedDRA grouping | v1, with five broadening errors | v2, review table in DATASET_AUDIT |
| Chain wording | Exposure step "documented" when attributed from roles; "Verified links" heading | Annotation-derived attribution marked as such; unconfirmed routes stated |
| Offline label search | INN only | INN + curated US names |

## 6. What was not done, and why

- **Independent clinical review.** No qualified reviewer was available. Everything is
  "internally annotated".
- **Current labels.** openFDA, DailyMed and RxNav are unreachable from the container. The
  real-label set is the TAC 2017 historical labels, redistributed on GitHub.
- **CRESCENDDI permission.** This needs the authors and the compendium owners. The engine keeps
  the code path, and the index can be rebuilt locally.
- **Git history rewrite.** It is irreversible and needs your decision (§2, P0-1).
