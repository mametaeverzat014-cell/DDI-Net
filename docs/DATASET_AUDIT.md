# DDI-Net 3.0 — Dataset audit for the Clinical Outcome Engine

Audit date: 2026-10-16. Machine-readable version: `data/sources_manifest.json`, which is checked by
`tests/test_sources_manifest.py`. Provenance of everything integrated: `docs/DATA_PROVENANCE.md`.

## How licences and access were checked

- **Network.** From the build container, every official biomedical host was unreachable. That
  includes:
  - api.fda.gov, dailymed / lhncbc / ftp.ncbi / download.nlm.nih.gov, rxnav;
  - ddinter.scbdd.com, nsides.io / tatonettilab.org, drugcentral.org, sideeffects.embl.de, reactome.org;
  - ebi.ac.uk (ChEMBL), pubchem, zenodo, figshare, huggingface, tdcommons.ai.

  GitHub was reachable over git and raw.githubusercontent.com, but not its release assets. PyPI
  and npm were reachable.
- **Licence quotes.** A licence marked **direct** was read in the provider's own file or page. A
  licence marked **search excerpt** was seen only as a search-engine excerpt of the official page,
  because the host itself was unreachable. Re-read those in a browser before relying on them
  legally. Nothing below is legal advice.
- **What "integrated" requires.** The licence was read directly, and the data was fetched
  reproducibly at a pinned version with checksums. Nothing with an unread licence was integrated.

## Summary: accepted, rejected and requiring permission

| Source | Decision | Why |
|---|---|---|
| DrugBank DDI via TDC | **already present** | Local export since 2026-08-24 (SHA-256 recorded) |
| DrugBank 5.1 / ChEMBL 36 drug–protein annotations | **already present** | Mechanism layer |
| Reactome | **already present** | Pathway background only |
| DrugCentral names | **already present** | INN names |
| openFDA drug label API | **already present** (live) | Label sentences; rules now `label_lexicon/v3` |
| RxNorm / RxNav API | **already present** (live) | Name normalisation |
| **CRESCENDDI** (Kontsioti et al., 2022) | **integrated (new)** | Licence read directly (MIT, authors' repository); pinned commit; pair-specific outcomes |
| **DDI Corpus 2013** | **evaluation only (new)** | CC BY-NC 4.0 (read directly); used to measure the label rule; never served or committed |
| OnSIDES v3 | accepted, **not integrated** | CC BY 4.0 (read directly), but release assets are unreachable here, and the data is single-drug only |
| DailyMed SPL services and mapping files | accepted, **not integrated** | Host unreachable, so no adapter could be verified; serves the same SPL text as openFDA |
| FDA Table of Substrates, Inhibitors and Inducers | accepted, **not integrated** | Public domain; host unreachable |
| DDInter 1.0 / 2.0 | **requires your decision and permission** | CC BY-NC-SA 4.0 (secondary source); host unreachable; severity and management text need review |
| DrugBank full release | **requires permission** | Account and licence approval; restricted redistribution |
| CredibleMeds QTdrugs | **requires permission** | Reproduction prohibited unless licensed |
| KEGG DDI | **requires permission** | Bulk / non-academic use licensed |
| TWOSIDES / OFFSIDES | **rejected** | Disproportionality signals, not causal evidence; data licence unverified; FAERS to 2014 |
| SIDER 4.1 | **rejected** | Single-drug, 2015, conflicting licence statements; superseded by OnSIDES |

## Resources already in the repository

| Resource | Provider / URL | How obtained | Licence | Format, size | IDs | Content type | Limitations |
|---|---|---|---|---|---|---|---|
| DrugBank DDI (TDC) | TDC, <https://tdcommons.ai/multi_pred_tasks/ddi/> | PyTDC 1.1.15, 2026-08-24; `data/raw/drugbank.tab.gz` | TDC CC BY 4.0; DrugBank content under DrugBank's non-commercial licence (search excerpt: "using or redistributing the DrugBank data requires a license") | TSV.gz, 4.3 MB; 191,808 rows, 86 types | DrugBank | **Pair-specific** interaction type as a template sentence. Only 7 types name a clinical outcome; most are PK or PD effects | No severity, no stated basis. The drug order is unreliable for most PK types (measured, `direction.py`). Only positives |
| Drug–protein annotations | DrugBank 5.1 (export 2025-01-02), ChEMBL 36 | Earlier phase; `data/mechanism_v1/` | DrugBank non-commercial; ChEMBL CC BY-SA 3.0 (not re-verified) | Parquet, 6.3 MB | DrugBank, UniProt | **Single-drug mechanism** | No inhibition strength or fraction metabolised |
| Reactome | <https://reactome.org/license> | UniProt2Reactome, 2026-08-28 | CC0 for data (search excerpt: "licensed under the Creative Commons Public Domain Dedication") | Parquet (in `mechanism_v1`) | UniProt, Reactome | Pathways (background) | A shared pathway is not a cause |
| DrugCentral names | <https://drugcentral.org> | Structures export, joined on InChIKey | CC BY-SA 4.0 per registries (official wording not read) | JSON (`web/public/data/drugs.json`) | InChIKey, INN | Names | Last release 2023 |
| openFDA labels | <https://open.fda.gov/apis/drug/label/> | Live API at request time | CC0 (search excerpt: "public domain and made available with a Creative Commons CC0 1.0 Universal dedication") | JSON | SPL set ID, RxCUI | Label text. **Pair-specific** only where a sentence names the partner | 240 requests/min and 1,000/day per IP without a key. Rule-based extraction (measured below). Unreachable from the build container |
| RxNav / RxNorm | <https://lhncbc.nlm.nih.gov/RxNav/> | Live API | No licence needed for the API. The full RxNorm download needs UMLS; SAB=RXNORM data is licence-free (search excerpt). ≤ 20 requests/s per IP | JSON | RxCUI | Name normalisation | — |
| SIDER, DrugCentral DB, DDInter parsers | `src/ddinet/data/*.py` (legacy) | **Not downloaded** | — | — | — | — | Legacy parsers from the first plan, unused |

## New resources investigated

### CRESCENDDI — **integrated**

- **Provider:** Kontsioti E, Maskell S, Dutta B, Pirmohamed M (University of Liverpool).
- **Citation:** Sci Data 9, 72 (2022), doi:10.1038/s41597-022-01159-y.
- **Canonical copies:** figshare collection doi:10.6084/m9.figshare.c.5481408, and the authors'
  repository <https://github.com/elpidakon/CRESCENDDI>.
- **Access:** git, commit `1734d7c12ac16e3df03c4a53cb40226f456c92c9`. Data Records 1 and 2 are
  xlsx files (411 KB and 129 KB), checked by SHA-256.
- **Licence:**
  - The repository holding the data records is **MIT** (read directly: "Permission is hereby
    granted, free of charge … to use, copy, modify, merge, publish, distribute"). The copyright
    and permission notice is kept in the derived manifest.
  - The figshare licence could not be read (host unreachable).
- **Content:**
  - 10,286 positive controls: a drug pair documented as interacting in BNF (Nov 2018), IBM
    Micromedex (Sep 2018) and the ANSM Thesaurus (Sep 2019), plus the adverse event (MedDRA
    preferred term) the authors mapped from the BNF and/or Micromedex description.
  - 4,544 negative controls (pair + unrelated event).
  - IDs: OHDSI RxNorm concept names, MedDRA PT codes.
- **Type of evidence:** **pair-specific outcome**, source-attributed. The data also contains
  **seriousness** (BNF / Micromedex / ANSM severity and evidence ratings). Those ratings are the
  proprietary editorial classifications of commercial compendia and are **deliberately not carried
  over**: not in the committed index, not shown.
- **Limitations and biases:**
  - Snapshots from 2018–2019.
  - Only pairs common to all three compendia (a selective subset).
  - Events come from an automated (OHDSI Usagi) plus manual mapping of free text.
  - European compendia.
  - A negative control means "not associated", not "safe".
- **Public web app:** allowed under MIT with the notice kept. The underlying compendium content
  is not reproduced: only the pair, the MedDRA term and which compendium the event came from.

### DDI Corpus 2013 — **evaluation only**

- **Provider:** HULAT group, Universidad Carlos III de Madrid, <https://github.com/isegura/DDICorpus>.
- **Access:** git, commit `819b0fa538ed83ab2a8b4f5417bba3c03249b7f3`; `DDICorpus-2013.zip`,
  1.5 MB, SHA-256 `87fc63e3…`.
- **Licence:** **CC BY-NC 4.0** (read directly: "The licence of this dataset is Creative Commons
  Attribution-NonCommercial 4.0 International").
- **Content:**
  - 792 DrugBank texts and 233 MEDLINE abstracts.
  - Annotated mention pairs: `ddi=true` with a type (mechanism / effect / advise / int), or
    `ddi=false`.
  - IDs: text spans.
- **Use:** to measure the label rule on independently annotated real text. **Not** served,
  **not** committed (non-commercial terms; it is a text-mining benchmark, not clinical evidence).
- **Limitations:**
  - Sentence-level interaction types, not clinical outcomes.
  - Annotated per mention, not per drug.
  - Class-level annotations ("CYP3A4 inhibitors") rather than each listed drug.

### OnSIDES v3 — accepted, not integrated

- **Provider:** Tatonetti Lab, <https://github.com/tatonetti-lab/onsides>.
- **Licence:** data **CC BY 4.0**, code MIT (read directly in `LICENSE-DATA`).
- **Content:** 7.1M drug–ADE pairs for 4,097 ingredients, extracted from 51,460 labels (US, EU,
  UK, JP) by a fine-tuned PubMedBERT. IDs: RxNorm, MedDRA.
- **Type:** **single-drug adverse events**, not pair-specific.
- **Not integrated because:** the v3.1.1 release zip (84.9 MB) is a GitHub release asset, which
  is unreachable from the build container. It could only ever be context ("also a known adverse
  reaction of drug A alone"), never evidence for the pair. Manual step in §"What you can do".

### DailyMed web services and RxNorm mapping files — accepted, not integrated

- **Provider:** NLM, <https://dailymed.nlm.nih.gov/dailymed/app-support-web-services.cfm>.
- **Access:** REST endpoints (search excerpts):
  - `/spls`, `/spls/{SETID}`, `/spls/{SETID}/ndcs`, `/rxcuis`, `/drugnames`, …;
  - `rxnorm_mappings.zip` (pipe-delimited SETID | SPL_VERSION | RXCUI | RXSTRING | RXTTY, about 6.65 MB).
- **Licence:** U.S. Government work. The NLM copyright page asks for acknowledgment. DailyMed's
  own terms page was not read.
- **Not integrated because:** the host is unreachable from the build container, so no adapter
  could be tested against real responses. It also serves the same SPL documents openFDA already
  provides.

### DDInter 1.0 / 2.0 — requires your decision

- **Provider:** SCBDD, Central South University. <https://ddinter.scbdd.com>,
  <https://ddinter2.scbdd.com>; DDInter 2.0 in NAR 2025;53:D1356.
- **Licence:** **CC BY-NC-SA 4.0** according to a secondary source (a GitHub mirror's README). The
  official terms page was not reachable.
- **Content:** about 0.24M (v1) / 302,516 (v2) pair records. Each has a severity level
  (Major / Moderate / Minor / Unknown, not verified from the official site), a mechanism, and
  management text.
- **Why not integrated:**
  - The host is unreachable.
  - ShareAlike would bind derived files to the same licence.
  - Its "management" recommendations conflict with the project rule of giving no clinical
    advice unless filtered out.
  - Its severity grades are DDInter's own classification, which would need an explicit policy.

### TWOSIDES / OFFSIDES (nSIDES) — rejected

- **Provider:** Tatonetti Lab, <https://github.com/tatonetti-lab/nsides-release>.
- **Licence:** no data licence found. The nSIDES **code** repository is CC BY-NC-SA 4.0 (read
  directly).
- **Content:** FAERS disproportionality (PRR on propensity-matched cohorts) for drug pairs and
  events, FAERS up to 2014; 5.73M significant triplets.
- **Why rejected:**
  - These are **spontaneous-report signals**: they cannot establish causality.
  - The data includes pairs where one drug alone explains the event.
  - The licence is unverified and the host unreachable.

### Others

- **FDA DDI table:** public domain; index substrates, inhibitors and inducers by CYP or
  transporter. It is useful for mechanism, but the host is unreachable.
- **CredibleMeds:** registration required; "commercial use or reproduction … prohibited unless
  licensed".
- **KEGG:** bulk use requires a licence.
- **PharmGKB:** CC BY-SA 4.0, but no general DDI outcome set.
- **Hetionet:** CC0, but no DDI edges.
- **SIDER 4.1:** single-drug, from 2015, with conflicting licence statements.

## What changed in the engine because of this audit

1. **CRESCENDDI positive controls are now pair-specific outcome evidence:**
   - category `reference_set_outcome`, source type `reference_set`;
   - MedDRA terms grouped by the fixed table `meddra_effect_map/v1`;
   - the MedDRA term, compendium and citation are shown;
   - no severity is shown.
2. **The label rule became `label_lexicon/v3`.** The no-effect filter was extended after its
   misses were seen on the DDI Corpus **development** split. The Test split was then scored once.
3. **DDI Corpus and CRESCENDDI give the first validation against independently annotated data:**
   `docs/CLINICAL_OUTCOME_VALIDATION.md`.

## What you can do (manual steps)

- **OnSIDES (optional, CC BY 4.0):** download `onsides-v3.1.1.zip` from the repository's
  Releases page in a browser and record its SHA-256. A single-drug context layer would need a new
  ingestion script; none was written, because the data could not be inspected here.
- **DDInter:** if you want it considered, read <https://ddinter2.scbdd.com> terms yourself, and
  decide whether a CC BY-NC-SA source and its severity and management text are acceptable for
  this app. Then share the download with the project. Nothing was downloaded.
- **CRESCENDDI figshare licence:** please confirm the licence shown on
  <https://doi.org/10.6084/m9.figshare.c.5481408> (expected CC BY 4.0). The integration relies on
  the MIT licence of the authors' GitHub copy.
- **Restricted sources** (DrugBank full, CredibleMeds, KEGG) need accounts or licences from their
  providers. They were not used.
