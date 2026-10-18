# DDI-Net 3.0 — Data provenance of the evidence layer

This file covers the data behind the Clinical Outcome Engine:
- what is in the repository;
- what is fetched;
- how each file was produced and checked;
- how to regenerate it.

The older, Russian-language record of the research datasets (TDC download conditions, the frozen
BIO-GINE inputs, SIDER and Reactome files) stays in `/DATA_PROVENANCE.md` and is not repeated
here. Licence decisions are in `docs/DATASET_AUDIT.md`.

## Rules

1. **Raw downloads are never committed.** They are cached in `data/raw/<source>/<commit>/`, which
   is git-ignored. The single historical exception is `data/raw/drugbank.tab.gz`; see the root
   provenance file.
2. **Pinned and checksummed.** Every fetched file has a pinned commit and a SHA-256 in code
   (`src/ddinet/data/crescenddi.py`, `src/ddinet/data/ddi_corpus.py`). A mismatch raises; there is
   no warn-and-continue (`src/ddinet/data/git_fetch.py`).
3. **Only derived indexes whose redistribution is clearly permitted are committed.** Data whose
   rights are unclear (the CRESCENDDI index, 2026-10-18) live in the git-ignored
   `data/restricted/`. They are never copied into an image and are used only for local research,
   behind an explicit flag. Only their manifest (checksums and counts) is committed.
4. **Derived indexes have manifests.** Each has a versioned
   `MANIFEST.json` with the input checksums, the output checksum, the counts at each stage and the
   generator.
5. **Build-time check.** The evidence-artifact builder (`serving/evidence/build.py`) refuses an
   index whose checksum does not match its manifest.
6. **Evaluation data stays out of the app.** Evaluation-only data (DDI Corpus, TAC 2017 labels)
   is never read by the API.

## Files

| Path | Committed | What | Produced by |
|---|---|---|---|
| `data/sources_manifest.json` | yes | Every source considered: status, licence, how verified, pins | by hand; checked by `tests/test_sources_manifest.py` |
| `data/restricted/crescenddi/crescenddi_index_v1.json.gz` | **no** (git-ignored; restricted, local research only). It was committed from 2026-10-16 to 2026-10-18 and is still in branch history at `8a1e689`…`7ac6299`. | CRESCENDDI controls mapped to DrugBank IDs; no severity ratings | `scripts/data/ingest_crescenddi.py` |
| `data/reference_sets/crescenddi/MANIFEST.json` | yes | Inputs, output SHA-256, stage counts, unmapped names; no records | same |
| `data/raw/crescenddi/1734d7c…/data_records/*.xlsx` | **no** | Raw Data Records 1 and 2 | `ddinet.data.git_fetch.fetch` |
| `data/raw/ddi_corpus/819b0fa…/DDICorpus-2013.zip` | **no** | DDI Corpus (CC BY-NC 4.0) | same |
| `runtime/evidence/evidence_v1.json.gz` | no (built in the image) | Evidence artifact. The public build has **no** `reference_outcomes`; its metadata lists `restricted_sources_included: []` | `python -m serving.evidence.build` |
| `data/raw/onsides_tac/fe6a4a4…/database/annotations/demner-fushman-*-labels.json` | **no** | TAC 2017 label sections (via OnSIDES, CC BY 4.0) | `ddinet.data.git_fetch.fetch` |
| `validation/clinical_outcomes/real_label_benchmark/*_units.jsonl`, `UNITS_MANIFEST.json` | yes | 150 sampled (label, partner) units with the adapter's excerpts | `scripts/data/build_real_label_benchmark.py` |
| `validation/clinical_outcomes/real_label_benchmark/annotations_*.jsonl`, `ANNOTATION_RULES.md`, `FREEZE.json` | yes | Internal annotations; rule fingerprint and annotation checksum recorded before evaluation | by hand; `scripts/68_v3_real_label_benchmark.py freeze` |
| `reports/v3_real_label_benchmark_*.{json,md}` | yes | Real-label benchmark results | `scripts/68_v3_real_label_benchmark.py` |
| `reports/archive/2026-10-16_label_lexicon_v3/` | yes | The v3 validation reports, kept before the v4 re-run (record-level CRESCENDDI examples removed) | copied |
| `validation/clinical_outcomes/ddi_corpus_label_lexicon_v2.json` | yes | DDI Corpus measurement of the v2 rule, kept before the v3 change | `scripts/67_v3_reference_validation.py` (earlier run) |
| `reports/v3_reference_validation.{json,md}` | yes | Measurements against independent data | `scripts/67_v3_reference_validation.py` |

## CRESCENDDI ingestion (`scripts/data/ingest_crescenddi.py`)

| Stage | What happens | Result on 2026-10-16 |
|---|---|---|
| Fetch | Blob-less git fetch of commit `1734d7c12ac16e3df03c4a53cb40226f456c92c9`; checkout of the two Data Records | — |
| Checksums | `9e001a6e…` (positives), `0d264662…` (negatives) | both match |
| Schema | Required columns; non-empty names and event; MedDRA code an 8-digit integer; `EVENT_SOURCE` ∈ {BNF, Micromedex, BNF+Micromedex} | 10,286 + 4,544 rows read, **0 rejected** |
| Drug mapping | Exact INN match, salt-stripped INN, or an existing curated alias (`serving/evidence/lexicon.py`). **No fuzzy matching, no new aliases** | **392 of 454** names mapped (384 INN, 8 curated alias). The 62 unmapped (heparins, thrombolytics, some biologics, US names such as Rifampin and Valproate, drugs outside the universe) are listed in the manifest |
| Pair rules | Records with an unmapped drug dropped (2,067 positive, 877 negative); self-pairs after mapping dropped (0) | — |
| De-duplication | Key: set + unordered DrugBank pair + MedDRA code; original rows and names kept | 4 negative duplicates collapsed |
| Contradictions | The same pair and event as both positive and negative are removed from both | 0 |
| Output | Deterministic gzip JSON (sorted keys, mtime 0) | **8,219 positive records over 3,952 pairs** (168 events); 3,663 negative records |
| Not carried over | Severity and evidence ratings; Data Record 3 (single-drug, partly SIDER-derived); Records 4 and 5 | — |

Regenerate it **locally** with the commands below. The public evidence artifact must exist
first, for the name lexicon. The index is written to `data/restricted/crescenddi/`; the manifest
goes to `data/reference_sets/crescenddi/`, and its checksum must equal the committed one.

```bash
python -m serving.evidence.build                                   # public build, no CRESCENDDI
python scripts/data/ingest_crescenddi.py --date YYYY-MM-DD
git diff --exit-code data/reference_sets/crescenddi/MANIFEST.json   # same inputs give the same index
DDINET_ENABLE_CRESCENDDI=1 python -m serving.evidence.build         # local research artifact only
```

Never deploy an artifact built with the flag. Its metadata lists
`restricted_sources_included: ["crescenddi"]`.

To check a copy you downloaded yourself, run `--from-dir <dir with data_records/>`. The same
checksums are enforced.

## How CRESCENDDI reaches a report

**Only on a local research build** (`DDINET_ENABLE_CRESCENDDI=1`, and the file present):

- **Build:** `serving/evidence/build.py` reads the index (after the checksum check) and stores the
  positive controls as `[drug_index_a, drug_index_b, meddra_code, term, event_source]`. Negative
  controls are evaluation-only and are not in the runtime artifact.
- **Records:** `serving/evidence/reference_sets.py` turns them into `EvidenceRecord`s of category
  `reference_set_outcome`. Each record carries:
  - the source name, commit, URL and licence;
  - the MedDRA term and code;
  - which compendium the event came from;
  - fixed qualifiers (2018–2019 snapshot; severity graded by the compendia but not reproduced).
- **Outcomes:** `serving/evidence/outcomes.py` groups the MedDRA term into an outcome effect with
  `meddra_effect_map/v2` (review table in `docs/DATASET_AUDIT.md`). All 179 terms in the data are listed in the table, and there is no
  guessed fallback. These outcomes merge with DrugBank or label outcomes of the same effect, and
  their strength is reported as `reference_set_statement` or `reference_set_and_other`.
- **Status:** the pair counts as documented (`documented_no_severity`, interaction status
  `documented_interaction`). The status wording became "no severity grade is shown in this
  report", because the old "the source gives no severity" would be false for CRESCENDDI.
- **Display:** the site and the PDF show a separate source document, "CRESCENDDI (reference set;
  BNF, Micromedex, ANSM, 2018–2019)". Its severity row reads "graded by the compendia, but those
  grades are not reproduced here".

## DDI Corpus (evaluation only)

`src/ddinet/data/ddi_corpus.py` fetches and checks the zip and reads every annotated mention
pair. `scripts/67_v3_reference_validation.py` uses it. Nothing derived from it is committed except
aggregate counts and rates.

## Identifier mapping, summarised

| From | To | How | Coverage |
|---|---|---|---|
| CRESCENDDI drug concept name (RxNorm/OHDSI) | DrugBank ID (1,705-drug universe) | Project lexicon: exact INN, salt-stripped INN, curated alias | 392/454 names |
| MedDRA PT (CRESCENDDI) | Outcome effect group | `meddra_effect_map/v2`, fixed table | 179/179 terms in the data |
| TAC 2017 label | Owner ingredient(s) | By hand from the brand name (annotation field `owner`) | 72 labels |
| International name | Label search terms | INN + the project's curated US names (`lexicon.ALIASES`) + RxNorm ingredient names when reachable | — |
| DDI Corpus document | Owner drug | File name (`<Drug>_ddi.xml`), DrugBank part only | All DrugBank-part documents |

## Deployment note

Since 2026-10-18 the image build copies **neither** `data/reference_sets/` nor
`data/restricted/`. `tests/test_docker_context.py` fails if a Dockerfile or `.dockerignore` would
let them in. The Render test service still runs an image built from the earlier commit, which
**does** serve CRESCENDDI. It must be redeployed by hand to withdraw it; see
`docs/DDINET_V3_DEPLOYMENT.md`.
