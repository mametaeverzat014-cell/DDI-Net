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
3. **Only derived, licence-compatible indexes are committed.** Each has a versioned
   `MANIFEST.json` with the input checksums, the output checksum, the counts at each stage and the
   generator.
4. **Build-time check.** The evidence-artifact builder (`serving/evidence/build.py`) refuses an
   index whose checksum does not match its manifest.
5. **Evaluation data stays out of the app.** Evaluation-only data (DDI Corpus) is never read by the
   API.

## Files

| Path | Committed | What | Produced by |
|---|---|---|---|
| `data/sources_manifest.json` | yes | Every source considered: status, licence, how verified, pins | by hand; checked by `tests/test_sources_manifest.py` |
| `data/reference_sets/crescenddi/crescenddi_index_v1.json.gz` | yes (177 KB) | CRESCENDDI controls mapped to DrugBank IDs; no severity ratings | `scripts/data/ingest_crescenddi.py` |
| `data/reference_sets/crescenddi/MANIFEST.json` | yes | Inputs, output SHA-256, stage counts, unmapped names | same |
| `data/raw/crescenddi/1734d7c…/data_records/*.xlsx` | **no** | Raw Data Records 1 and 2 | `ddinet.data.git_fetch.fetch` |
| `data/raw/ddi_corpus/819b0fa…/DDICorpus-2013.zip` | **no** | DDI Corpus (CC BY-NC 4.0) | same |
| `runtime/evidence/evidence_v1.json.gz` | no (built in the image) | Evidence artifact; now includes `reference_outcomes` and `sources.crescenddi` | `python -m serving.evidence.build` |
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

Regenerate it with the following commands. The evidence artifact must exist first, for the name
lexicon.

```bash
python -m serving.evidence.build
python scripts/data/ingest_crescenddi.py --date YYYY-MM-DD
python -m serving.evidence.build          # rebuild with the new index
```

To check a copy you downloaded yourself, run `--from-dir <dir with data_records/>`. The same
checksums are enforced.

## How CRESCENDDI reaches a report

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
  `meddra_effect_map/v1`. All 179 terms in the data are listed in the table, and there is no
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
| MedDRA PT (CRESCENDDI) | Outcome effect group | `meddra_effect_map/v1`, fixed table | 179/179 terms in the data |
| DDI Corpus document | Owner drug | File name (`<Drug>_ddi.xml`), DrugBank part only | All DrugBank-part documents |

## Deployment note

The image build copies `data/reference_sets/` (`serving/Dockerfile`, `serving/Dockerfile.lean`,
`.dockerignore`). The Render test service must be redeployed by hand to pick it up; see
`docs/DDINET_V3_DEPLOYMENT.md` §3.1.
