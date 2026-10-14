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

---

## What was not done, and why

| Item | Status | Reason |
|---|---|---|
| Live verification of openFDA / RxNorm | not done | blocked by this container's network policy; mocked tests only |
| Deployment of the API and the site | not done | requires your authorization; images must be rebuilt (`Dockerfile.lean` changed) |
| Push of `feature/ddinet-v3` | not done | requires your authorization |
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
