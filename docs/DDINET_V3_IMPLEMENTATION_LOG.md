# DDI-Net 3.0 — Implementation Log

Session of 2026-10-14, branch `feature/ddinet-v3` (created from
`claude/ddi-net-drug-interaction-hxrqii` at `aa04493`). Commits are local; nothing
was pushed or deployed.

---

## Step 1 — Recovery and audit

* Read the README, `docs/CURRENT_STATE.md`, `paper/PAPER_FACTS.md`,
  `paper/FACTS.json`, `serving/`, `web/`, `data/mechanism_v1/` and the frozen
  tag (fetched; absent from the fresh clone).
* Downloaded the released checkpoint; SHA-256 matches the manifest.
* Installed the toolchain. `download.pytorch.org` is blocked by the container's
  network policy; torch 2.13.0 came from PyPI instead. RxNav, openFDA, DailyMed,
  UniProt, Reactome and ChEMBL hosts are blocked too.
* Baseline: web 66/66 tests, typecheck and lint clean; Python 613 passed,
  2 failed, 11 errors (details in the test report).
* Found a pre-existing break: commits `911bed9` and `aa04493` modified the
  hash-gated `src/ddinet/models/bio_gine.py`, so the integrity gate refused to
  load the model and `serving/Dockerfile.lean` could not build.
* Wrote `docs/DDINET_V3_REPOSITORY_AUDIT.md`.

## Step 2 — Smallest reliable end-to-end feature

Chosen: a **pair evidence report** that works offline from committed data —
resolution, the DrugBank record in the source's words, mechanism hypotheses from
documented roles, the model score with its regime, and a plain-language
explanation that labels every sentence — with external label evidence as an
optional layer that reports its own availability.

## Step 3 — Evidence engine (commit `f2c4a8b`)

| Change | Files |
|---|---|
| Deterministic evidence artifact builder and loader | `serving/evidence/build.py`, `store.py` |
| Drug resolver (IDs, INN, transliteration, salts, curated aliases, suggestions) | `lexicon.py` |
| Typed schemas | `schema.py` |
| DrugBank records, 86 Russian template translations, conflicts | `records.py` |
| **Finding:** TDC drug order is type-dependent; direction audit and neutral rendering | `direction.py` |
| Mechanism hypotheses, protein family texts, pathways, provenance graph | `mechanism.py` |
| HTTP client, RxNorm and openFDA adapters, label evidence | `adapters/`, `labels.py` |
| Status classification by precedence | `classify.py` |
| Model regime, abstention, measured performance | `model_context.py` |
| Deterministic RU/EN explanation and validator | `explain.py` |
| Engine and `/api/v3` router | `engine.py`, `serving/api_v3.py`, `serving/api.py` |
| Fix for the frozen-module break: vendored byte-identical `bio_gine.py` | `serving/frozen_model.py`, `serving/frozen_artifacts/bio_gine.py`, `serving/frozen_manifest.json`, `serving/engine.py` |
| Docker images build the evidence artifact | `serving/Dockerfile`, `serving/Dockerfile.lean` |
| Phase 4 measurements | `scripts/61_v3_seed_disagreement.py`, `scripts/62_v3_coverage_reliability.py` |

Issues found and fixed during this step:

* A validator test showed "Вы можете спокойно принимать" slipping past the
  forbidden-wording list; the Russian patterns were broadened.
* Mechanism-to-record consistency first used the export's drug order; after the
  direction audit it uses that order only for verified types.
* Transporter hypotheses first said "processed"; they now say "moved".
* "Not connected" and "unavailable" sources are worded differently.
* Common names (aspirin, acetaminophen, albuterol) failed offline; a labelled
  alias list was added, each target verified by a test.

## Step 4 — Simple-mode interface and the site (commit `09c8d55`)

* New views: Analyzer, Mechanisms, Multi-drug. The v2 Analyze page and the Drug
  Explorer are kept and linked.
* Shared `DrugPicker` and `BiologyPanel` extracted from `Analyze.tsx` (behaviour
  unchanged; existing tests still pass).
* Navigation reorganised into the eight requested sections; hash routes carry
  view and pair; compact menu under 1240 px.
* Research, Data and Limitations pages gained the 3.0 measurements, the
  evidence-source table and the evidence-layer limitations, all numbers from
  `web/src/data/v3facts.json` (generated, pinned by a test).
* `scripts/63_v3_direction_audit.py` writes the direction report.
* Browser check (Playwright, Chromium, 1360 px and 390 px): all views render,
  no console errors, no horizontal overflow. Fixes made after looking at the
  screenshots: the record-consistency caveat repeated per hypothesis
  (consolidated); the nav wrapped at 1360 px and the logo broke across lines;
  the graph was scaled too small in a two-column layout (now full width) and
  showed English names on the Russian page; the multi-drug network clipped
  names; English-only source details appeared in Simple mode (hidden there).

## Step 5 — Validated model explanation (commit `5d6c156`)

* `FrozenBioGineEngine.branch_zeroed_encodings()` reproduces the frozen
  modality analysis; the lean artifact carries the three tables.
* `scripts/64_v3_modality_parity.py`: max |Δ| 6.05e-06 against the frozen
  `seed0_modality_contribution.csv` on all 84,690 pairs. Exposed in research
  mode and on the Mechanisms page, with its interpretation limit and a
  saturation note.

## Step 6 — Exploratory research analysis

* `scripts/65_v3_mechanism_concordance.py`: pharmacokinetic role
  configurations vs labels (not independent) and vs model scores within label
  classes and annotation-volume strata. Result and limits in
  `docs/DDINET_V3_SCIENTIFIC_LIMITATIONS.md` §5.

## Step 7 — Documentation and tests

* `docs/DDINET_V3_ARCHITECTURE.md`, `DDINET_V3_SCIENTIFIC_LIMITATIONS.md`,
  `DDINET_V3_TEST_REPORT.md`, this log.

## Step 8 — Preparing a public research demonstration

* **Rate limiting** (`serving/ratelimit.py`): per-client and global sliding
  windows on `/api/v3`, strictest on multi-drug requests (4/min, 30/h per
  client); 429 with `Retry-After`; body-size cap; client key from the
  right-most `X-Forwarded-For` entry so a caller cannot choose their bucket.
  Daily per-source budgets for openFDA and RxNorm in `HttpClient`. The site
  shows a distinct "too many requests" state, never an empty report.
* **Docker**: allowlist `.dockerignore` (111 files, 16 MiB instead of the whole
  repository); `/api/health/ready`; `HEALTHCHECK` in both Dockerfiles;
  `DDINET_REQUIRE_EVIDENCE=1` in the images; Render health check path updated.
  Verified without a Docker daemon by running the build stage inside exactly
  the filtered context (artifacts identical to the full-tree build) and the
  runtime stage under Python 3.11 with only the lean requirements.
* **Drug-order integrity**: the mechanism graph no longer copied the DrugBank
  export order into `documented_interaction` edges for unverified types; edges
  now carry `directed` and the neutral statement. New integration tests check
  every record, 150 sampled unverified pairs through the engine and the HTTP
  API, in both languages and both request orders.
* `docs/DDINET_V3_DEPLOYMENT.md`.

## Step 9 — PDF report export

* Export PDF and JSON buttons on the Analyzer, Mechanisms and Multi-Drug pages,
  disabled until results exist, with loading, success and error states in both
  languages. The PDF is generated in the browser with `@react-pdf/renderer`
  from the response the page already holds; the API client now records each
  response's endpoint, request body and arrival time for the report's
  provenance. Nothing is re-requested; no server, service or key is involved.
* A4 report: cover, executive summary, drugs, documented interactions,
  mechanism schematic (vector), model analysis, the service's explanation,
  sources and reproducibility (payload SHA-256 shared with the JSON), limitations
  and a machine-readable appendix. Multi-drug: network, pair matrix, all pairs,
  coverage, no overall score. IBM Plex fonts embedded (Cyrillic).
* Three renderer problems found by the tests and handled (line height
  compounding across pages, font objects shared between documents, long-word
  splitting); see `docs/DDINET_V3_PDF_EXPORT.md` §3.
* 44 web tests; real-browser exports in both languages; samples in
  `docs/samples/pdf-export/`.

## Step 10 — Report quality pass

A real Preview PDF showed five weaknesses. Their causes:

* repeated label text counted as separate sources;
* a thin summary;
* an evidence card overlapping the footer on page 6;
* a pooled metric that read as an S2 figure;
* jargon.

Each cause was verified before it was changed:

* openFDA returns an older label's Drug Interactions subsection twice;
* react-pdf shrinks the content of a box split across pages;
* the frozen code pools test_S2 and test_S3.

The fixes:

* the backend merges repeated text within a label and counts documents;
* the site and the PDF group evidence by source document;
* the summary is deterministic and quotes the sources;
* the PDF is built from atomic page-level blocks, with geometry regression
  tests;
* metrics are labelled pooled, and scores are printed at the precision they
  have;
* a plain-language score explainer and a glossary were added.

Details: `docs/DDINET_V3_REPORT_QUALITY_PASS.md`.

## Step 11 — Clinical Outcome Engine

This step answers five questions per pair from the evidence records alone:
1. Is an interaction documented?
2. What consequences are documented?
3. Why could it happen?
4. How serious is it, and how strong is the evidence?
5. What is unknown?

The pieces:

* **Backend:** `serving/evidence/outcomes.py`, which contains:
  * a DrugBank type map with an effect level per type;
  * the label lexicon, with scoped negation, population and partner-clause
    guards;
  * evidence states, source-stated seriousness and qualitative evidence
    strength;
  * mechanism → outcome chains with a provenance class per link;
  * multi-drug outcome categories, with no combined score.
* **Site:** the Simple mode A–F layout, the chain explorer, the
  research-mode outcome table and the multi-drug outcome matrix.
* **PDF:** the Quick Report, the full-report outcome sections, and outcomes
  in the JSON.

**Validation** (`scripts/66_v3_outcome_validation.py`):
* A constructed pilot set exposed v1's errors: negation after the term, a
  second clause, and a case-sensitive "Prothrombin". These led to
  `label_lexicon/v2`.
* A hold-out set written after v2 was frozen gave precision 25/26 and recall
  25/32.
* The pair-level checks, mechanism-attribution check and adversarial cases
  are in `docs/DDINET_V3_CLINICAL_OUTCOMES_VALIDATION.md`.

**Found and fixed along the way:**
* a horizontal overflow at phone width, from long chain-node chips;
* a long Russian drug name running out of the PDF annotation table's column.
  This one was pre-existing and now has a geometry regression test.

## Step 12 — Evidence coverage: dataset audit and the CRESCENDDI reference set

* **Audit** (`docs/DATASET_AUDIT.md`, `data/sources_manifest.json`) of the sources already used
  and of DailyMed, DDInter, TWOSIDES, OnSIDES, CRESCENDDI, the DDI Corpus and others. Every
  official biomedical host is unreachable from the build container; GitHub (git and raw) is
  reachable.
* **Integrated: CRESCENDDI**, licence read directly (MIT, authors' repository).
  * The pipeline (`src/ddinet/data/git_fetch.py`, `crescenddi.py`,
    `scripts/data/ingest_crescenddi.py`) does a pinned git fetch, SHA-256 checks, schema
    validation, exact drug mapping (392/454), de-duplication and conflict removal, and writes a
    versioned manifest.
  * The derived index is committed; the raw files are not.
  * In the engine, its records are a separate evidence category (`reference_set_outcome`). MedDRA
    terms are grouped by `meddra_effect_map/v1`, and no severity is shown.
* **Evaluation only: the DDI Corpus** (CC BY-NC 4.0). It measured the label rule on independently
  annotated text. Errors seen on Train led to `label_lexicon/v3` (wider no-effect wording); Test
  was then scored once.
* **Results:** `docs/CLINICAL_OUTCOME_VALIDATION.md`.
* **Fixes found on the way:**
  * the status wording "the source gives no severity" became "no severity grade is shown in this
    report";
  * a PDF JSON appendix could leave its closing line alone on a page; the tail is now kept
    together.

---

## Step 13 — Scientific reliability audit (2026-10-18)

Full record: `docs/DDINET_V3_SCIENTIFIC_AUDIT.md`.

* **CRESCENDDI withdrawn from every public build (P0).**
  * MIT covers the authors' code, not the compendium-derived records.
  * The index moved to the git-ignored `data/restricted/` and is used only with
    `DDINET_ENABLE_CRESCENDDI=1`.
  * Docker, fixtures, sample PDFs and reports were cleaned. Tests use a SYNTHETIC reference set.
* **Real-label benchmark.**
  * 150 (label, partner) units from historical FDA labels (TAC 2017 via OnSIDES), split by
    TAC's own train and test.
  * Development led to `label_lexicon/v4`, which was frozen with a rule fingerprint.
  * The evaluation set was annotated blind and checksummed, then scored once: outcome
    precision 40/45, recall 40/43, citations 68/68.
* **Fixes:**
  * sentence splitter (abbreviations);
  * the excerpt window always contains the partner;
  * condition bullets and comparator arms no longer become outcomes;
  * `meddra_effect_map/v2`;
  * the exact no-specific-outcome sentence in the JSON, site, Quick and Full PDF;
  * a visible label-extraction caveat;
  * chain links no longer call an annotation-derived attribution "documented";
  * offline label search uses curated US names.

---

## What was not done, and why

| Item | Status | Reason |
|---|---|---|
| Live verification of openFDA / RxNorm | not done | blocked by this container's network policy; mocked tests only |
| Deployment of the API and the site | not done | requires your authorization; instructions in `docs/DDINET_V3_DEPLOYMENT.md` |
| An actual `docker build` | not done | no Docker daemon in this container; the steps were reproduced command by command |
| Per-protein model attribution for any pair | not done | the frozen method exists for 20 pairs; extending it needs per-drug re-encoding (torch at request time or a ~40 MB table) and a defensible validation plan |
| Calibrated clinical probabilities | not done, deliberately | no outcome data; the negative labels are sampled unlabelled pairs |
| Higher-order (3+ drug) modelling | not done, deliberately | no data or validated method |
| Scaffold-disjoint and temporal evaluation of BIO-GINE | not done | requires retraining; temporal data absent. Retraining only to show progress was explicitly out of scope |
| Pair-conditioned mechanism-aware model (research question B) | not started | needs a preregistered protocol and new training; the concordance analysis (§5 of the limitations) is the groundwork |
| Drugs outside the 1,705-drug universe | not supported | records, roles and the model are all universe-bound; labels alone could serve them later |
| User testing of the plain-language text | not done | no participants in this session |

## Remaining research tasks (proposed order)

1. Deploy the lean API with outbound access, then run the label adapters live on
   a fixed panel of pairs and record precision of name matching by hand.
2. Obtain an independent interaction source (e.g. DDInter or label text at
   scale) to test the open question in limitations §5: are high-scoring
   unlabelled pairs with a PK configuration enriched for documented
   interactions elsewhere?
3. Report the TDC orientation finding upstream and in the paper's threats to
   validity; extend the audit to pharmacodynamic types with a curated anchor
   set.
4. Only then consider a pair-conditioned, mechanism-aware model under a new
   preregistration, compared against M4 and M0 on S3 and a scaffold-disjoint
   split.
