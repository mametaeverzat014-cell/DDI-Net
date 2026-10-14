# DDI-Net 3.0 — Repository Audit

Compiled 2026-10-14 by inspecting the repository, the frozen tag and the local
toolchain. Nothing here is recalled from earlier conversations; every claim
points at a file or a command that was run. Where a fact could not be verified
in this session, it says so.

---

## 0. Summary

DDI-Net is not a prototype that needs rebuilding. It is a mature research
codebase with an unusually strict integrity culture: a preregistered V2 study,
a frozen and tagged scientific state, integrity-gated serving, and a bilingual
site whose every number is generated from the frozen tag and asserted by tests.

What DDI-Net 3.0 actually lacks is narrow and well defined:

1. **No evidence layer.** The site and API report a model score, a
   "documented in the frozen dataset" flag and shared DrugBank proteins. They
   never show *what* is documented. The interaction statement itself
   ("The metabolism of #Drug2 can be decreased when combined with #Drug1")
   is in `data/raw/drugbank.tab.gz` and has never been surfaced.
2. **No drug-role reasoning.** `drug_protein_edges.parquet` records whether a
   drug is a *substrate*, *inhibitor* or *inducer* of an enzyme or transporter
   (DrugBank, with PubMed IDs). The shared-biology block ignores these roles and
   says only "both use the same enzyme", which is the weakest possible reading.
3. **No external sources.** No label (openFDA / DailyMed) or RxNorm adapter
   exists. Brand names are not resolvable.
4. **No structured explanation, mechanism graph, multi-drug mode, or
   uncertainty diagnostics.**

Everything else — model, data, evaluation, serving, site — is reusable.

---

## 1. Git state

| | |
|---|---|
| Working branch | `claude/ddi-net-drug-interaction-hxrqii`, clean, up to date with origin |
| Commits on branch | 50 (latest `aa04493`, 2026-09-15) |
| Remote branches | `claude/ddi-net-drug-interaction-hxrqii`, `feature/coattention-phase-b`, `v2-final-artifacts`, `vast-5090-compute` |
| Frozen tag | `v2-final-github-safe-2026-09-03` → commit `92c481e` (fetched in this session; was absent from the fresh clone) |
| Release asset | `bd45f84e3c1b2c33.pt` (18,064,518 bytes) — the **only** released checkpoint |
| Checkpoint hash | downloaded in this session; SHA-256 `b828a471…59d6f` matches `serving/frozen_manifest.json` |

The working branch is **not** a descendant of the frozen commit (documented in
`serving/frozen_manifest.json`). Frozen result files (`reports/v2_final/`,
`reports/v2_interpretability/`, …) exist only on the tag and are read with
`git show`, never copied into the working tree. That convention is kept.

The last three commits (`8902fd7`, `911bed9`, `aa04493`) add research code
behind flags (Candidate A evidence-type aggregation; a fingerprint encoder
baseline) without training anything. They are unfinished research threads, not
results.

---

## 2. Stack

| Layer | Technology | Location |
|---|---|---|
| Research code | Python 3, PyTorch 2.13, PyTorch Geometric 2.8, RDKit, pandas, scikit-learn | `src/ddinet/` (~15k lines), `scripts/` (49 entry points) |
| Model | BIO-GINE (`src/ddinet/models/bio_gine.py`) | frozen seed-0 M4 checkpoint |
| Serving | FastAPI + pydantic v2; two engines (full torch / lean numpy) | `serving/` |
| Frontend | Vite 5 + React 18 + TypeScript, no router, no UI library, hand-written canvas engine | `web/` |
| Static site | plain HTML + CSS (RNPK competition site) | `site/` |
| Deploy | Vercel (web, `web/vercel.json`), Render blueprint (API, `render.yaml`), GitHub Pages (`site/`, `.github/workflows/pages.yml`) |
| CI | Only the Pages deploy workflow. **No test CI.** |

---

## 3. Data (verified in this session)

| Fact | Value | Source |
|---|---|---|
| Drugs | 1,705 | `data/mechanism_v1/drugs.parquet` |
| Positive DDI pairs (unordered) | 191,392 | `ddi_positive_labels.parquet` |
| Raw DrugBank DDI rows (TDC) | 191,808, of which 191,798 inside the universe | `data/raw/drugbank.tab.gz` |
| Pairs with more than one record | 406 | same |
| Interaction types / text templates | 86 | `reports/interaction_types.csv` |
| Drug–protein edge rows | 146,743 (DrugBank 13,150; ChEMBL MOA 2,255; ChEMBL activities 131,338) | `drug_protein_edges.parquet` |
| DrugBank edges with PubMed IDs | 88.9% | same, `pmids` column |
| DrugBank enzyme roles | substrate 2,170; inhibitor 839; substrate+inhibitor 425; inducer 277; … | same, `action` column |
| DrugBank transporter roles | inhibitor 842; substrate 814; substrate+inhibitor 305; inducer 48; … | same |
| Proteins / pathways | 2,778 / 1,969 | `proteins.parquet`, `pathways.parquet` |
| Protein–pathway edges | 14,576 (Reactome, with evidence codes) | `protein_pathway_edges.parquet` |
| Drug names | 1,497 / 1,705 have an INN (DrugCentral, joined on InChIKey); all unique | `web/public/data/drugs.json` |
| Russian names | rule-based transliteration, explicitly **not** data | `web/tools/drug_names.py` |
| Brand names, synonyms | **none** in the repository | — |
| Drug-level split, seed 0 | 1,195 train / 255 val / 255 test | `split_assignments.csv` |

The `drugs.parquet` `name` column holds the DrugBank ID, not a name. The only
real names are the DrugCentral INNs in `drugs.json`.

Mechanism labels derived from the interaction text by regex are **quarantined**
(`data/mechanism_v1/MECHANISM_LABEL_LIMITATIONS.md`: 94.2% UNKNOWN, 0.00% PD).
The raw text itself is not quarantined — it is the source statement — but it
must not be turned back into a mechanism classifier without fixing that.

---

## 4. BIO-GINE (read from code)

- Molecular branch: GINE, 3 layers, hidden 64, SUM pooling, LayerNorm.
- Biological branch: DeepSets over (protein, relation, evidence) triples and
  over pathways, MEAN aggregation, bio_dim 128.
- Fusion: Linear → LayerNorm (128). Pair decoder: commutative terms
  (sum, |diff|, product, mask min/max) → MLP 388 → … → 1.
- 1,122,804 parameters; the pair decoder is 132,609 of them.
- The DDI label is never an input (`biology.py` never reads labels or splits;
  `serving/api.py` documents and enforces this).
- The `action` column (substrate/inhibitor/inducer) is **not** a model input.

Headline frozen results (`paper/FACTS.json`, recomputed from per-seed values):

| Model | Pooled AUPRC | S3 AUPRC |
|---|---|---|
| BIO-GINE M4 | 0.8117 ± 0.0097 | 0.7372 ± 0.0153 |
| Molecular GINE M0 | 0.7784 ± 0.0059 | 0.7145 ± 0.0065 |
| M4, degree-preserving shuffled biology | 0.6923 ± 0.0054 | 0.6305 ± 0.0105 |
| Biological-degree-only RF | 0.6504 ± 0.0006 | — |

The ablation ladder is non-monotonic (M2 0.8269 and M4-SUM 0.8265 beat M4);
the paper reports this, and the site renders it unsorted.

---

## 5. Serving (`serving/`)

| Component | State |
|---|---|
| `POST /api/analyze` | Functional. Frozen-universe drugs only; returns raw + temperature-scaled score, dataset-record flag, DrugBank-only shared proteins, provenance |
| `GET /api/health` | Functional |
| Integrity gate | Checkpoint, 6 source modules, 5 data files, calibration CSV hash-checked before first score |
| Lean engine | numpy-only, ~158 MiB RSS; reads `runtime/model_assets/lean_decoder_v1.npz`, built by `python -m serving.precompute` (needs torch) |
| Parity | Lean vs frozen predictions max \|Δ\| 6.05e-06 over 92,448 rows (documented) |
| Lean runtime image | contains `serving/` + the artifact only — **no `src/`, no `data/`, no pandas** |

Constraint carried forward: anything the API needs at request time must work
with the standard library and numpy, and must be either inside `serving/` or
inside a built artifact.

---

## 6. Frontend (`web/`)

Views: Home, Analyze, Model, Research, Data, Drug Explorer, Limitations.
Bilingual RU/EN, Russian default (`i18n.tsx`). Integrity components (`Metric`
requires a source path, `Badge` for demo/pending values). Analyze already has:
drug search by ID/INN/transliteration, per-drug biology from `drugs.json`, a
live score panel with honest unconfigured/unavailable/error states, a
plain-language explainer, and a shared-biology block written for lay readers.

Baseline in this session: **66/66 vitest tests pass, `tsc --noEmit` clean,
eslint clean (max-warnings 0).**

Missing: evidence report, simple/research toggle, mechanism graph, multi-drug
view, a navigation that matches the requested information architecture.

---

## 7. Tests and toolchain in this container

| Check | Result |
|---|---|
| Python tests not needing torch/rdkit | **248 passed, 10 skipped, 1 failed** |
| The failure | `test_adapter_contract.py::test_sider_refuses_without_a_cid_bridge_even_though_its_files_exist` — needs raw SIDER files in `data/raw/sider/`, which are not in git. Pre-existing, environmental |
| Modules needing torch/rdkit | 15 test modules cannot be collected until torch, torch_geometric and rdkit are installed |
| `download.pytorch.org` | **blocked** by this container's network policy (403 at the proxy); PyPI reachable |
| Web tests / typecheck / lint | pass (see §6) |

---

## 8. Network reachability (decisive for Phase 1)

Measured with `curl` from this container:

| Host | Result |
|---|---|
| github.com (git, release assets), pypi.org, registry.npmjs.org | reachable |
| rxnav.nlm.nih.gov (RxNorm) | **blocked** |
| api.fda.gov (openFDA labels) | **blocked** |
| dailymed.nlm.nih.gov | **blocked** |
| rest.uniprot.org, reactome.org, ebi.ac.uk (ChEMBL) | **blocked** |

Consequence: external adapters can be implemented and tested against recorded
response shapes (mocks), but **no live external query was made or verified in
this session.** The deployed API host (Render) is not subject to this policy;
the adapters are designed to work there and to report "source unavailable"
rather than silently returning nothing when they cannot.

Also relevant: NLM retired the RxNav **Drug Interaction API** on 2024-01-02. It
must not be used or cited as a current interaction source. RxNorm remains the
right source for name normalisation only.

---

## 9. Reusable as-is

- Frozen model, lean engine, integrity gate, parity tests.
- `SharedBiologyIndex` and its rationale (DrugBank only; ChEMBL bioactivity
  excluded because shared assay panels create spurious overlap — measured in
  `reports/chembl_panel_artifact.md`).
- TDC DrugBank raw records with the original DrugBank sentence templates.
- DrugBank drug–protein roles with PubMed IDs; Reactome pathway mapping.
- Drug-level split (seed 0) — lets every pair be placed in S1/S2/S3.
- Frozen interpretability on the tag: modality contribution for all 84,690
  seed-0 test pairs; leave-one-protein/pathway-out for the top-20 pairs.
- Frozen per-seed test predictions (5 seeds × 92,448 rows) on the tag.
- i18n, design tokens, Badge/Metric integrity components, plain-language copy.

## 10. Requires new development

| Need | Why it is new |
|---|---|
| Evidence schemas and engine | nothing structured exists |
| Drug resolver | the frontend has a substring filter; there is no server-side normaliser, no synonyms, no brands |
| Label and RxNorm adapters | none exist; must tolerate a blocked network |
| Role-aware mechanism reasoning | roles are in the data, unused |
| Deterministic explanation generator | none exists |
| Mechanism graph, multi-drug mode | none exist |
| Uncertainty diagnostics | the API reports a single seed-0 score and nothing about the regime the pair belongs to |

## 11. Limitations that shape DDI-Net 3.0

1. **Only one checkpoint is available.** Seeds 1–4 of the final M4 run were
   never released, and the other five manifests in `reports/v2_checkpoints/`
   are grid/budget runs with no released weights. Live ensemble disagreement
   is impossible. Per-seed predictions exist only for the frozen test pairs.
2. **The score is not a clinical probability.** Temperature scaling was fitted
   on a validation set with sampled negatives at prevalence 0.5. The existing
   site already says so; DDI-Net 3.0 must not weaken it.
3. **Label circularity risk for mechanism "validation".** DrugBank derives many
   of its interaction sentences from the same enzyme/transporter annotations
   that a role-based explanation would use. Agreement between the two is
   consistency, not independent confirmation.
4. **Training-pair leakage in displayed scores.** For a pair whose drugs were
   both in the training split and which is a documented positive, the model
   was fitted on that label. Its score there is not a prediction. The current
   UI does not say this.
5. **No severity anywhere in the local data.** TDC/DrugBank records carry an
   interaction type and a sentence, never a severity grade. DDI-Net 3.0 must
   not invent one.
6. **Network policy of this container.** See §8.
