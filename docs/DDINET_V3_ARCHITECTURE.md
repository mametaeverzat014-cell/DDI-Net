# DDI-Net 3.0 — Architecture

DDI-Net 3.0 adds an **evidence layer** around the frozen BIO-GINE model. The
model is unchanged; what changes is what a reader is told, and how each part of
the answer is labelled.

The design rests on one rule: **three kinds of statement are never mixed.**

| Kind | What it is | Where it lives |
|---|---|---|
| Documented evidence | a source states that the two drugs interact | `PairReport.evidence` |
| Mechanism hypothesis | documented facts about each drug *separately*, arranged into a configuration that could explain an interaction | `PairReport.mechanism` |
| Model signal | the BIO-GINE research score and the diagnostics that say how much it can be trusted for this pair | `PairReport.model` |

The plain-language explanation is generated from these three blocks and tags
every sentence with its kind and the IDs of the records it rests on.

---

## 1. System overview

```
                 committed repository files                     GitHub Release
  data/mechanism_v1/*.parquet  data/raw/drugbank.tab.gz          bd45f84e3c1b2c33.pt
  web/public/data/drugs.json   split_assignments.csv                    │
              │                                                          │
              ▼                                                          ▼
  serving/evidence/build.py ─────────────┐          serving/precompute.py (torch, once)
  (pandas, build time)                   │          integrity gate + frozen module
              │                          │                       │
              ▼                          │                       ▼
  runtime/evidence/evidence_v1.json.gz   │      runtime/model_assets/lean_decoder_v1.npz
  (stdlib-loadable, hashed)              │      (encodings, decoder, branch-zeroed
              │                          │       encodings, shared-biology index)
              ▼                          │                       │
  ┌──────────────────────────────────────┴───────────────────────┴──────────┐
  │ FastAPI app (serving/api.py)  — lean image: numpy + pydantic only        │
  │                                                                          │
  │  /api/analyze  (v2, unchanged)          /api/v3/*  (serving/api_v3.py)   │
  │        │                                        │                        │
  │   LeanEngine ◄──────────── optional ─────── EvidenceEngine               │
  │                                                 │                        │
  │      lexicon ─ records/direction ─ mechanism ─ labels ─ classify         │
  │                         model_context ─ explain/validate                 │
  │                                                 │                        │
  │                          adapters/http ─► RxNorm, openFDA (network)      │
  └──────────────────────────────────────────────────────────────────────────┘
                                   │ JSON
                                   ▼
  web/ (Vite + React, static): Analyzer · Mechanisms · Multi-drug · Research ·
  Methods · Data · Limitations       — reads VITE_ANALYZE_API at build time
```

Everything the request path needs is either inside `serving/` or inside one of
the two built artifacts. The lean runtime image has no `src/`, no `data/`, and
no pandas; `tests/test_v3_api.py::test_v3_runs_in_the_lean_image_shape` runs the
v3 request path with pandas, torch, rdkit, sklearn, scipy and pyarrow blocked.

---

## 2. Components

### 2.1 Evidence artifact — `serving/evidence/build.py`

Deterministic (gzip `mtime=0`, sorted keys): the same inputs give byte-identical
output, asserted by `test_artifact_is_deterministic`. Contents:

| Block | Source | Notes |
|---|---|---|
| Drug lexicon | `drugs.parquet`, `drugs.json` | DrugBank ID, DrugCentral INN (1,497 of 1,705), Russian transliteration (flagged as a UI label), seed-0 split, protein-coverage flag |
| DrugBank interaction records | `data/raw/drugbank.tab.gz` (TDC) | 191,798 ordered (Drug1, Drug2, type) rows over the 191,392 documented pairs; 86 templates |
| Drug–protein annotations | `drug_protein_edges.parquet` | DrugBank v5.1 (with role and PubMed IDs) and ChEMBL curated MOA. **ChEMBL bioactivity excluded** (shared assay panels; `reports/chembl_panel_artifact.md`) |
| Reactome membership | `protein_pathway_edges.parquet` | with evidence codes and pathway size (specificity) |
| Direction audit | computed from the above | see §2.3 |

`evidence_v1.meta.json` records the SHA-256 of every input and of the artifact;
`EvidenceStore.load()` refuses an artifact whose hash does not match.

### 2.2 Resolution — `serving/evidence/lexicon.py`

Order of attempts: DrugBank ID → exact INN → Russian transliteration →
salt-stripped INN ("warfarin sodium") → a **project-curated** USAN/INN alias
list (40 entries such as acetaminophen → paracetamol, each target verified by a
test to be an INN in the data; matches are reported as `curated_alias`) →
RxNorm, when reachable (brand → ingredient; multi-ingredient products return
`multiple_ingredients`, never a silent pick). A near miss returns suggestions
only. Inputs are restricted to `[\w\s\-.,'()/+]{1,100}`.

### 2.3 DrugBank records and the direction audit — `records.py`, `direction.py`

Records are rendered with DrugBank's own template. A finding made in this
project changes how they are worded: **the TDC export's drug order does not
consistently follow the template's `#Drug1/#Drug2` slots.** Checked against
DrugBank's own enzyme roles (`scripts/63_v3_direction_audit.py`,
`reports/v3_tdc_direction_audit.md`):

| type | template (abridged) | consistency of export order |
|---|---|---|
| 4 | metabolism of #Drug2 increased | 0.996 |
| 75 | serum concentration of #Drug2 decreased | 0.970 |
| 47 | metabolism of #Drug2 decreased | 0.080 |
| 73 | serum concentration of #Drug2 increased | 0.103 |

Each type is classified `symmetric` (meaning independent of order: 7 types),
`consistent` (checkable and ≥ 0.95 consistent with ≥ 30 informative rows:
types 4 and 75), or `unverified` (everything else). Unverified records are
rendered **without naming which drug is affected** ("The metabolism of one of
the two drugs can be decreased when combined with the other drug"), in English
and in the project's Russian translation. No row is flipped. Of 191,798 records,
61,397 are symmetric, 14,481 verified, 115,920 rendered neutrally.

Opposing records about the same quantity of the same drug (e.g. types 73 and
75) are reported as a `Conflict`; no combined conclusion is formed.

### 2.4 Mechanism hypotheses — `mechanism.py`

For every protein both drugs are annotated against, the documented roles are
arranged into one of:

| pattern | rule | reading offered |
|---|---|---|
| `inhibitor_substrate` | A inhibits enzyme/transporter P, B is a substrate of P | B may be broken down / moved more slowly |
| `inducer_substrate` | A induces P, B is a substrate | B may be handled faster |
| `opposing_target_action` | activating vs inhibiting action at one target | effects may cancel |
| `same_direction_target_action` | same direction at one target | effects may add up |
| `shared_substrate` | both substrates only | weak; stated as weak |
| `shared_annotation` | shared protein, roles unspecified | no reading offered |

A finding is linked to DrugBank records whose PK direction matches
(`consistent_with_records`), using the export order only for verified types.
The explanation then says, once, that this agreement is **not independent**:
DrugBank may have derived the record from the same annotations.

Protein descriptions for lay readers are **project-written family texts**
(cytochrome P450, UGT, P-glycoprotein, OATP, OAT/OCT, MATE, albumin, hERG, …),
labelled in the UI as general background, never as a statement about the pair.

Shared Reactome pathways are ranked by "reached through a protein both drugs
act on" and then by pathway size (smaller = more specific). The ranking is
presentational; the text calls shared pathways background, not cause.

The **mechanism graph** (`mechanism_graph`) contains only documented edges:
drug–protein annotations (with role, source, PubMed IDs), protein–pathway
membership (with Reactome evidence codes) and the documented-interaction arc.
Hypotheses are an overlay on proteins, never an edge. No model-derived edge
exists in the graph.

### 2.5 External sources — `adapters/`

`HttpClient`: standard-library HTTPS, 6 s timeout, 24 h TTL cache (2,048
entries), 60 s per-source cooldown after a failure, injectable transport for
tests. HTTP 403/407/429/5xx and network errors raise `SourceUnavailable`, which
becomes a `sources_checked` entry with status `unavailable` — never an empty
result. `DDINET_EXTERNAL_SOURCES=off` disables all external calls.

`OpenFdaLabelAdapter`: picks the most recent single-ingredient human
prescription label for an ingredient (`openfda.generic_name`, falling back to
`substance_name`), scans BOXED WARNING, CONTRAINDICATIONS, WARNINGS AND
PRECAUTIONS, WARNINGS, PRECAUTIONS and DRUG INTERACTIONS for whole-word mentions
of the partner, and returns the containing sentence verbatim (≤ 600 chars, ≤ 3
per section) with set ID, SPL version, effective date and a DailyMed link.
Sentences with explicit no-effect wording ("did not significantly alter", "no
clinically significant …") go to `label_mention_no_effect_reported`, which never
raises the status. An `OPENFDA_API_KEY` is used server-side only and is stripped
from every URL returned to clients.

`RxNormAdapter`: `rxcui.json?search=2` → `properties.json` →
`related.json?tty=IN+PIN`. Names only.

### 2.6 Classification — `classify.py`

One status per pair, by explicit precedence; never a blended severity:

```
label contraindication  >  label warning / interaction  >  database record
  >  conflicting records  >  model-only signal  >  nothing documented found
```

`model_signal_only` requires: no documented record, model available, the pair
not a training positive, calibrated score ≥ 0.5 (the decision boundary of a
temperature-scaled classifier at the evaluation prevalence of 0.5 — a stated
convention, not a clinical threshold). "Nothing documented found" is labelled
"This does not mean the combination is safe".

### 2.7 Model context — `model_context.py`

| field | how it is decided | why |
|---|---|---|
| `regime` | seed-0 drug split: S1 both train, S2 one, S3 neither | the frozen study characterised S2/S3 only |
| `training_label_seen` | S1 and documented | the score is then a recollection; `abstain=True`, score not counted |
| `measured_performance` | M4 pooled AUPRC (S2) or S3 AUPRC from `paper/FACTS.json`; AUROC for the pair's annotation-coverage group from `reports/v3_coverage_reliability.json` | quote measured averages, never a per-pair confidence |
| `notes` | validation-split drug; missing protein annotation; calibration caveat | |
| `modality_reliance` | branch-zeroed rescoring (§2.8) | validated against the frozen analysis |

Deliberately absent: confidence percentages; seed-disagreement "uncertainty"
(only one checkpoint was released, and on the frozen per-seed predictions seed
spread detects errors no better than the score's distance from 0.5 —
`reports/v3_seed_disagreement.md`).

### 2.8 Model reliance by modality — `engine.py`, `precompute.py`, `lean.py`

`FrozenBioGineEngine.branch_zeroed_encodings()` reproduces the frozen post-hoc
analysis (`scripts/49_v2_interpretability.py` at the tag): one branch zeroed
immediately before the frozen fusion layer, mask unchanged. The three resulting
encoding tables ship in the lean artifact (adds ~2.5 MB). Parity with the frozen
`seed0_modality_contribution.csv` on all 84,690 test pairs: max |Δ| 6.05e-06
(`reports/v3_modality_parity.md`). Withheld when the model saw the pair's label.

### 2.9 Explanation — `explain.py`

Deterministic templates, no language model. Five sections — *What is known*,
*Why this may happen*, *What the AI found*, *How certain is this?*, *What is
missing* — each statement tagged `documented | annotation | hypothesis | model |
missing | caveat` and carrying reference IDs. `validate()` runs on every report
and raises if a factual statement has no reference, a reference is not in the
report, a model statement appears while the model is unavailable, or any text
matches the forbidden list (safety claims, "take/stop/combine/re-dose"
instructions, in English and Russian). Every report ends by referring medication
decisions to a doctor or pharmacist.

Russian drug names are transliterations used with the word "препарат", which
keeps them in the nominative (a transliterated name cannot be declined
reliably). Label excerpts are never translated; the Russian text points to the
English quotation.

### 2.10 Frozen-model vendoring — `serving/frozen_model.py`

Commits `911bed9` and `aa04493` added research flags to
`src/ddinet/models/bio_gine.py`, a hash-gated frozen module; the integrity gate
then (correctly) refused to serve, and `Dockerfile.lean` failed at
`precompute`. Serving now imports a byte-identical copy of the module from the
tag (`serving/frozen_artifacts/bio_gine.py`), loaded under
`ddinet.models.bio_gine_frozen` so its relative imports resolve to the other
hash-checked frozen modules. The manifest still checks six modules with the
frozen hashes. All parity tests pass again.

---

## 3. API

All endpoints are read-only and accept only drug names or DrugBank IDs. Nothing
about the person asking is accepted or stored; the rate limiter keeps a request
count per client address in memory only, and the host's access log (uvicorn)
records address and path.

| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/api/health` | — | model and evidence availability, artifact hashes |
| GET | `/api/health/ready` | — | 200 only when model and evidence are loaded, else 503 (the health check) |
| POST | `/api/analyze` | `{drug_a, drug_b}` (DrugBank IDs) | v2 response, unchanged |
| GET | `/api/v3/resolve` | `q` | `ResolveOut` |
| POST | `/api/v3/report` | `{drug_a, drug_b, include_labels=true}` | `PairReport` |
| POST | `/api/v3/graph` | `{drug_a, drug_b}` | `MechanismGraph` |
| POST | `/api/v3/multi` | `{drugs: [2..8], include_labels=true}` | `MultiReport` |
| GET | `/api/v3/sources` | — | source metadata, artifact hash, direction audit |
| GET | `/api/v3/limits` | — | rate-limit policy, the caller's client key, external-source daily budget |

Errors: `422` with `{"detail": {"message", "resolutions": [ResolveOut…]}}` when a
drug cannot be identified (candidates included, nothing guessed); `422` for
invalid input or the same drug twice; `503` when the evidence artifact is
missing; `429` with `Retry-After` and `{"detail": {"message",
"retry_after_seconds", "scope", "route_class"}}` when a rate limit is reached;
`411`/`413` for a POST without `Content-Length` or with a body over 16 KiB.

**Rate limiting** (`serving/ratelimit.py`, ASGI middleware inside CORS so
refusals stay readable by the browser): sliding windows per client and for all
clients together, by route class — `resolve` 60/min, `pair` (report, graph)
30/min, `multi` 4/min and 30/h per client, 40/min for all clients. The client
is the right-most `X-Forwarded-For` entry at `DDINET_PROXY_HOPS` (default 1:
the entry Render's proxy appends), so a prefix the caller writes is ignored.
State is in memory in the single worker. Separately, `HttpClient` caps network
calls per external source per UTC day (openFDA 800 without a key, RxNorm
20,000), so a public deployment stays inside those services' quotas.

**Edge direction.** A `documented_interaction` edge carries `directed`. It is
`true` only for the DrugBank types whose drug order the audit verified; for all
others the edge runs in request order, `directed` is `false`, the site draws no
arrowhead, and the statement is the direction-neutral rendering. Schemas: `serving/evidence/schema.py`; TypeScript mirror:
`web/src/data/v3.ts`.

---

## 4. Data sources evaluated

| Source | Used for | Access | Coverage / update | Licence | Limits |
|---|---|---|---|---|---|
| DrugBank via TDC (PyTDC 1.1.15) | interaction records | local file, retrieved 2026-08-24 | 191,808 rows, 86 types, snapshot | TDC CC BY 4.0; DrugBank non-commercial | no severity, no basis per record, unreliable order for many types |
| DrugBank 5.1 drug–protein | roles, PubMed IDs | local | 13,150 edges | DrugBank non-commercial | no strength, no fraction metabolised |
| ChEMBL 36 curated MOA | target roles | local | 2,255 edges | CC BY-SA 3.0 (ChEMBL terms) | target-centric |
| Reactome | pathway membership | local | 14,576 edges | CC0 1.0 (`DATA_PROVENANCE.md`) | membership is not mechanism |
| DrugCentral | English INN names (via InChIKey) | local, snapshot 2021_09_01 | 1,497 of 1,705 drugs named | CC BY-SA 4.0 (`DATA_PROVENANCE.md`) | 208 drugs unnamed (e.g. rifampicin, DB01045) |
| openFDA drug labels | label sections | network | US SPL, updated weekly | public domain (CC0) | US market; class statements not matched by name; no grading |
| DailyMed | human-readable label links | link only | same SPL documents | public | — |
| RxNorm (RxNav REST) | names, brands | network | monthly releases | public domain | US naming (USAN); no interaction data |
| RxNav Drug Interaction API | **not used** | — | — | — | discontinued by NLM on 2024-01-02 |
| DDInter, TWOSIDES, FAERS, SIDER | **not used for evidence** | — | — | — | not downloadable in this environment, or pharmacovigilance signals unsuitable as interaction claims without disproportionality analysis; SIDER is mono-therapy side effects |

---

## 5. Frontend (`web/`)

Vite + React + TypeScript, no router or UI library (unchanged policy). New:

| File | Role |
|---|---|
| `src/data/v3.ts` | typed client; states `unconfigured / loading / ok / unresolved / unavailable / rate_limited / error`; an `ok` response carries its provenance (endpoint, request body, time received) |
| `src/views/Analyzer.tsx` | Simple mode (default) and Research mode |
| `src/views/Mechanisms.tsx` | graph explorer with provenance panel and reliance readout |
| `src/views/MultiDrug.tsx` | up to 8 drugs, pairwise network and review table, scope note |
| `src/components/v3/*` | report parts, graph, evidence styles, reliance bars, findings, source table |
| `src/lib/route.ts` | hash routes `#/analyzer?a=DB…&b=DB…` |
| `src/data/v3facts.json` | generated by `tools/build_v3_facts.py` from `reports/v3_*.json` |
| `src/components/v3/ExportReport.tsx`, `src/pdf/*` | Export PDF / JSON of the analysis on screen, generated in the browser from the response the page holds (`docs/DDINET_V3_PDF_EXPORT.md`) |

Evidence tiers have their own colour tokens (`--ev-*`); none is green, enforced
by `evidence.test.tsx`, which also scans v3 copy for advice or safety wording.

---

## 6. Running locally

```bash
# Python side
pip install -r serving/requirements.txt           # torch etc., to build the model artifact
git fetch origin tag v2-final-github-safe-2026-09-03
curl -sSL -o runtime/model_assets/bd45f84e3c1b2c33.pt \
  https://github.com/mametaeverzat014-cell/DDI-Net/releases/download/v2-final-github-safe-2026-09-03/bd45f84e3c1b2c33.pt
python -m serving.precompute                      # lean artifact (+ branch-zeroed encodings)
python -m serving.evidence.build                  # evidence artifact
uvicorn serving.api:app --port 8000               # DDINET_EXTERNAL_SOURCES=off to stay offline

# evidence-only, without building the model artifact
DDINET_ALLOW_NO_MODEL=1 uvicorn serving.api:app --port 8000

# site
cd web && npm ci
VITE_ANALYZE_API=http://127.0.0.1:8000 npm run dev
```

Reports are regenerated with `scripts/61`–`65` (they read the frozen tag with
`git show`; nothing is written into frozen trees).

## 7. Deployment considerations

* **API (Render, `render.yaml`)**: `serving/Dockerfile.lean` now also builds
  the evidence artifact in the build stage and copies `runtime/evidence/` into
  the runtime stage, sets `DDINET_REQUIRE_EVIDENCE=1` (a missing artifact stops
  startup) and declares a `HEALTHCHECK` on `/api/health/ready`. The build
  context is an allowlist (`.dockerignore`, checked by
  `tests/test_docker_context.py`). Step-by-step instructions:
  `docs/DDINET_V3_DEPLOYMENT.md`. Nothing was deployed from this session.
* **Outbound network**: the API host must reach `api.fda.gov` and
  `rxnav.nlm.nih.gov` for label evidence and brand names. Without it, reports
  are complete from local sources and say that labels were not checked.
* **openFDA quota**: 240 requests/minute and 1,000/day per IP without a key;
  set `OPENFDA_API_KEY` (server-side) for 120,000/day. A pair report costs at
  most 4 label requests, cached for 24 h.
* **Frontend (Vercel)**: set `VITE_ANALYZE_API` to the API URL and rebuild.
  `vercel.json` builds with `npx vite build`, so the committed
  `src/data/frozen.json` and `src/data/v3facts.json` are used as-is.
* **CORS** stays `*` with no credentials: the API is read-only and stateless.
* **Licensing**: DrugBank-derived statements are shown per query for
  non-commercial research use; no bulk endpoint exposes them (multi-drug is
  capped at 8 drugs, 28 pairs).
