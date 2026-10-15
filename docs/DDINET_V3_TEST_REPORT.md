# DDI-Net 3.0 — Test Report

All results below were produced in this session's container (Linux, Python
3.13, Node 22, CPU only) on branch `feature/ddinet-v3`. Nothing is reported as
passing that was not run. Commands are given so each line can be reproduced.

---

## 1. Summary

| Check | Before (baseline at `aa04493`) | After |
|---|---|---|
| Python test suite (`pytest tests/`) | 613 passed, 21 skipped, **2 failed, 11 errors** | **743 passed, 3 skipped, 1 failed** |
| Web unit tests (`npx vitest run`) | 66 passed | **128 passed** (44 of them for the PDF export) |
| TypeScript (`npx tsc --noEmit`) | clean | clean |
| ESLint (`--max-warnings 0`) | clean | clean |
| Production build (`npm run build`) | — | succeeds; regenerating `frozen.json` from the tag gives no diff |
| Repository text hygiene (`tests/test_repo_hygiene.py`) | pass | pass (includes all new docs) |
| Browser end-to-end (Playwright, Chromium) | — | pass, 0 console errors (§5) |

The remaining Python failure is pre-existing and environmental (§3).

## 2. Baseline failures and what happened to them

| Baseline result | Cause | Now |
|---|---|---|
| `test_serving.py::test_integrity_covers_sources_and_data` failed; 11 `test_serving.py` tests errored at the `engine` fixture | commits `911bed9`/`aa04493` changed the hash-gated `src/ddinet/models/bio_gine.py`; the integrity gate refused to load the model | **fixed**: serving imports a byte-identical vendored copy of the frozen module; all 33 `test_serving.py` tests pass, including parity on every frozen seed-0 prediction |
| `test_adapter_contract.py::test_sider_refuses_without_a_cid_bridge_even_though_its_files_exist` failed | the test assumes raw SIDER files in `data/raw/sider/`, which are gitignored and not in a fresh clone | **unchanged**, environmental; not touched |
| 18 of the 21 skips | the 14 `@lean_only` tests in `test_serving.py` and the 4 in `test_lean_runtime.py` skip when the lean artifact is absent, and it could not be built because of the integrity break | they now run and pass; 3 skips remain (Reactome FI / DrugCentral raw files, gitignored) |

## 3. Remaining failure

```
FAILED tests/test_adapter_contract.py::test_sider_refuses_without_a_cid_bridge_even_though_its_files_exist
ddinet.adapters.SourceUnavailable: sider: missing data/raw/sider/meddra_all_se.tsv.gz, data/raw/sider/drug_names.tsv
```

Pre-existing (identical in the baseline run before any change), unrelated to
DDI-Net 3.0, and caused by data the repository deliberately does not track.

## 4. New tests (DDI-Net 3.0)

### Python — 100 new tests

| File | Tests | What they establish |
|---|---|---|
| `tests/test_v3_evidence.py` | 42 | artifact determinism and counts (1,705 drugs, 191,798 records over 191,392 pairs, 86 types, 1,638 annotated drugs, 1,195 training drugs); ChEMBL bioactivity excluded; resolution of IDs, INN, transliteration, salts, aliases; suggestions never auto-picked; invalid input refused; every alias targets a real INN and shadows none; Russian templates keep their slots; neutral rendering leaves no slot; the measured direction audit (type 4 > 0.99, 47 < 0.10, 73 < 0.15) is pinned; unverified records name no affected drug; opposing records become a conflict, not a consensus; inhibitor/inducer–substrate and target patterns; the real warfarin–fluconazole CYP2C9 configuration; the graph has no model-derived edge; regimes; abstention for training labels; status precedence; quoted numbers equal `paper/FACTS.json` and `reports/v3_*.json`; **explanations validate for 150 real pairs** (75 documented, 75 random); the validator rejects unreferenced claims, phantom references and advice/safety wording (four phrasings, both languages); reliance withheld when the label was seen |
| `tests/test_v3_adapters.py` | 14 | network failure, 403/429/5xx → `unavailable` with cooldown; disabled client never calls out; caching; label choice prefers single-ingredient over a newer combination product; section categories and no-effect wording; whole-word matching; API key never leaves in returned URLs; RxNorm brand → ingredient, multi-ingredient, not-in-universe; full report with mocked labels → `warning_in_label`; unreachable labels → `unavailable`, local records still count |
| `tests/test_v3_api.py` | 14 | HTTP contract of `/api/v3/*`; 422 with candidates for unresolved drugs; input validation; same drug refused; multi-drug bounds; `/api/analyze` unchanged; validated modality reliance in the report; **lean-image probe**: v3 request path runs with torch, torch_geometric, rdkit, pandas, sklearn, scipy and pyarrow blocked at import |
| `tests/test_v3_frozen_vendor.py` | 3 | vendored module hash = manifest hash; bytes = the tag's `bio_gine.py`; the engine builds the model from the vendored module |
| `tests/test_v3_site_facts.py` | 2 | `web/src/data/v3facts.json` equals a fresh regeneration; the direction report equals the audit the API applies |
| `tests/test_serving.py` (one added) | 1 | lean branch-zeroed rescoring equals the torch path |
| `tests/test_v3_ratelimit.py` | 16 | route classes, multi-drug strictest; sliding windows and `Retry-After`; a refused request does not consume quota; the global window spans clients; client table bounded; a prepended `X-Forwarded-For` cannot change the client key; HTTP 429 keeps CORS headers; 411/413 body limits; `/api/analyze` and health not limited; daily external-source budget; `/api/health/ready` 200/503; `DDINET_REQUIRE_EVIDENCE=1` stops startup without the artifact |
| `tests/test_v3_direction_integrity.py` | 4 | every one of the 191,798 records: the exported order is used only for verified types (counts pinned: 115,920 not verified, 14,481 verified, 61,397 symmetric); for 150 sampled unverified pairs plus two reference pairs, reports and graphs in both request orders and both languages contain no orientation-filled statement; verified types give directed edges; the same through HTTP for report, graph and multi. Mutation-checked: reverting the graph fix makes the tests fail |
| `tests/test_docker_context.py` | 4 | `.dockerignore` applied with Docker's matching rules to the tracked files: every `COPY` source of both Dockerfiles survives; every integrity-checked file and every evidence-build input is in the context; nothing outside `serving/`, `src/`, `data/mechanism_v1/` and two input files is sent; context under 25 MiB (16 MiB) |

External sources were tested only against recorded response **shapes** with
synthetic content (all-zero set IDs, "SYNTHETIC TEST FIXTURE" manufacturer,
fictional drug names in logic fixtures). No live call to openFDA or RxNorm was
possible from this container (network policy; see the audit).

### Web — 18 new tests

| File | Tests | What they establish |
|---|---|---|
| `src/data/v3.test.ts` | 8 | unconfigured build never calls the network; 200/503/404/422/429 map to distinct states; an older API without `/api/v3` is "unavailable", not an empty report; 429 carries the server's retry delay (body, then `Retry-After`, then 60 s) |
| `src/lib/route.test.ts` | 3 | hash routes round-trip; malformed IDs, unknown views and same-drug pairs are ignored |
| `src/components/v3/evidence.test.tsx` | 7 | no evidence tier token has a green hue; no green literal in v3 views; "nothing found" says it is not safe in both languages; no advice or safety wording in v3 copy and the Limitations page; every tier labelled in both languages; the banner never shows the model score; five sections render and a statement links to its numbered source |

### Web — PDF export, 44 tests

| File | Tests | What they establish |
|---|---|---|
| `src/pdf/units.test.ts` | 20 | SHA-256 (standard vectors, equal to WebCrypto), key-order-independent payload hash and report ID; ASCII file names with local date and `_RU`; time with zone and offset; Russian noun forms; control and bidi characters removed, markup kept literal; only http(s) links; mono wrapping loses nothing; the JSON appendix parses back to the same value; summary counts and machine summary equal the payload; companion JSON hash; diagram labels inside the frame and never overlapping (4 graphs × 2 languages), no trunk through a pill, documented link present exactly when a record exists and never directed; network labels for 2–8 drugs; no green evidence colour; no advice wording in the PDF sources; every string in both languages with the same placeholders |
| `src/pdf/render.test.ts` | 17 | ten PDFs generated through the browser's code path and read back with pdfjs-dist: valid, A4, ≥ 5 pages; no drawing coordinate above 10,000 pt; every font embedded and IBM Plex; every extracted character present in the font files (rendering several reports in one process); no text outside the margins; no blank page; required sections and values; every source URL, record ID, retrieval date, PMID and UniProt ID cited; no 2–6-decimal number absent from the payload; no orientation-filled DrugBank template; "nothing found ≠ safe"; missing model, meta and INN handled; multi-drug covers all 28 pairs, no overall score; long names wrap; markup printed literally and no `javascript:`/`data:` link; no advice wording in either language |
| `src/components/v3/ExportReport.test.tsx` | 7 | disabled with a reason before results; Russian by default; exports the given analysis in the page language and announces the file; loading state blocks a second export; failure explained as an alert, nothing downloaded; companion JSON; message cleared for a new analysis |

Two of these were mutation-checked: re-adding a line height to the page style
makes the suite fail (renderer overflow), and removing the per-document font
reset makes the glyph test fail (`Clarithromycin` extracts as `\u0016larithromycin`).

## 5. Browser end-to-end

Playwright (Chromium 1194) against `vite preview` of a production build pointed
at a local `uvicorn serving.api:app` (lean model + evidence artifact; external
sources enabled but unreachable from the container):

| Scenario | Result |
|---|---|
| Analyzer, warfarin + fluconazole, Russian, Simple mode | status `documented_no_severity`; five sections; 1 numbered source; labels reported "unavailable" |
| Research mode | model panel with regime S2, measured AUPRC/AUROC, reliance bars (protein −0.154, others ≈ 0; saturation note); 3 hypothesis rows (CYP2C19, CYP2C9, CYP3A4) |
| Mechanisms, simvastatin + clarithromycin | graph with 29 interactive nodes; selecting CYP3A4 shows roles, PubMed IDs and the hypothesis |
| Multi-drug, 4 drugs | 6 pairs; network and review table; scope note above results; fluconazole + simvastatin shown as "not counted" (S1 training label) |
| metformin + warfarin | "No documentation found … This does not mean the combination is safe" |
| 390 px wide, English | no horizontal overflow; menu button replaces the nav |
| Default build without `VITE_ANALYZE_API` | "evidence service not connected" notice, no status banner, static per-drug data shown, no API requests |
| Console errors across all scenarios | 0 |
| After rate limiting (second run): Multi-drug, repeated clicks | 5th request within a minute shows "Слишком много запросов … через 59 с." (`role=alert`), never an empty report; the only console message is the browser's own 429 resource error |
| After the edge-direction fix: Mechanisms, simvastatin + clarithromycin and fluconazole + warfarin | documented arc has no arrowhead; its tooltip is the label in Russian and the direction-neutral statement in English |
| PDF export (EN and RU): Analyzer warfarin + fluconazole | button disabled while loading, enabled with the report; Enter on the focused button downloads `DDI-Net_Report_Warfarin_Fluconazole_2026-10-15.pdf` (`_RU` in Russian) in about 6 s; status "File saved: …"; JSON companion downloads, its hash equals the one printed in the PDF |
| PDF export: Mechanisms simvastatin + clarithromycin; Multi-drug with 4 and 6 drugs | files download with descriptive names; Multi-drug button disabled until "Check pairs" returns; 0 console errors |
| Exported files | poppler `pdfinfo`/`pdffonts`/`pdftotext`: no errors, all fonts embedded; `pypdf` strict mode reads every file; pages inspected at 40, 60, 110 and 220 dpi; samples in `docs/samples/pdf-export/` |

## 6. Reproducing

```bash
git fetch origin tag v2-final-github-safe-2026-09-03
# checkpoint as in serving/README.md, then:
python -m serving.precompute && python -m serving.evidence.build
python -m pytest tests/ -q                     # ~8 min on CPU
cd web && npm ci && npx vitest run && npx tsc --noEmit \
  && npx eslint . --ext ts,tsx --max-warnings 0 && npm run build
```

## 7. Not tested

* Live openFDA and RxNorm responses (blocked here).
* An actual `docker build` (`docker` is not available in this container). The
  build stage was reproduced inside a directory holding exactly the
  `.dockerignore`-filtered context (111 files): integrity gate, precompute
  (peak 1.3 GB resident) and evidence build succeed, and the artifacts equal
  those built from the full tree. The runtime stage was reproduced under Python
  3.11.15 with only `serving/requirements-lean.txt`: the `HEALTHCHECK` command
  exits 0, `/api/health/ready` 200, v2 and v3 endpoints answer, resident memory
  219 MB; without the evidence artifact the server refuses to start. Details:
  `docs/DDINET_V3_DEPLOYMENT.md` §9.
* Usability of the plain-language text with real readers.
