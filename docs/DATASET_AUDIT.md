# DDI-Net 3.0 — Dataset audit for the Clinical Outcome Engine

Audit date: 2026-10-16; **revised 2026-10-18**: the CRESCENDDI licensing audit, its status
changed to restricted local use, the mapping audit, the MedDRA map v2 review, and the TAC 2017
real-label benchmark source. Machine-readable version: `data/sources_manifest.json`, which is checked by
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
| openFDA drug label API | **already present** (live) | Label sentences; rules now `label_lexicon/v4` |
| RxNorm / RxNav API | **already present** (live) | Name normalisation |
| **CRESCENDDI** (Kontsioti et al., 2022) | **restricted, local research only** (was "integrated" 2026-10-16) | MIT covers the authors' code and documentation; the records derive from BNF and Micromedex, whose terms do not clearly permit redistribution. Not committed, not shipped, not served (§CRESCENDDI) |
| **TAC 2017 ADR labels** (via OnSIDES repository) | **evaluation only (new)** | CC BY 4.0 (OnSIDES data) and U.S. Government label text; source of the real-label benchmark |
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

### CRESCENDDI — **restricted: local research use only**

**Identity.**
- **Authors:** Kontsioti E, Maskell S, Dutta B, Pirmohamed M (University of Liverpool).
- **Article:** Sci Data 9, 72 (2022), doi:10.1038/s41597-022-01159-y.
- **Exact version used:** the authors' GitHub repository <https://github.com/elpidakon/CRESCENDDI>
  at commit `1734d7c12ac16e3df03c4a53cb40226f456c92c9`.
  - Data Record 1 (positive controls, xlsx): SHA-256 `9e001a6e…`.
  - Data Record 2 (negative controls, xlsx): SHA-256 `0d264662…`.
- **Canonical deposit:** figshare collection doi:10.6084/m9.figshare.c.5481408, v1. It could not
  be opened from the build environment.

**Licensing findings (2026-10-18).**

| Question | Finding | How verified |
|---|---|---|
| What does the repository licence cover? | MIT: "Permission is hereby granted … to any person obtaining a copy of this **software and associated documentation files** (the "Software")". It is a software licence. It does not mention data, and it cannot grant rights the authors do not hold. | Read directly (`LICENSE` at the pinned commit) |
| Licence of the article | CC BY 4.0. This covers the article text, not third-party content behind the data. | Search excerpt (nature.com unreachable) |
| Licence of the figshare deposit | **Not verified.** Figshare data are usually CC BY 4.0 or CC0; the page could not be opened. | Not verified |
| Where the records come from | The article: interaction descriptions **scraped from the BNF** (Nov 2018) and **IBM Micromedex** (Sep 2018); the ANSM Thésaurus (Sep 2019) contributed the pair list and severity. Every positive control's event was mapped from BNF and/or Micromedex text (OHDSI Usagi plus manual). The code confirms that pairs are the intersection of all three compendia (`intersection/generate_common.sql`). | Read directly (repository code); article via search excerpt |
| BNF terms | BNF content is licensed by the BNF Partners (BMJ / RPS). The published terms seen as excerpts restrict derivative use, incorporation into third-party systems, and text and data mining without a licence. | Search excerpts only |
| Micromedex terms | Proprietary (Merative, formerly IBM). The article states the authors' access was under licence. | Search excerpt |
| ANSM Thésaurus | French public-agency document. Reuse is probably governed by the CRPA public-information regime (attribution, no distortion); not verified. Its contribution (severity) is not carried over anyway. | Not verified |
| Does MIT cover the data records? | **Not established.** A code licence does not automatically cover datasets, and the records are derived from proprietary compendia the authors licensed. | Conclusion |
| Redistribution rights for the derived records | **Unclear.** | Conclusion |

**Decision.** Following the rule "if redistribution rights remain unclear, do not publish
restricted records":
- **Index and image:** the derived index (11,882 pair–event records) was removed from git
  tracking and from both Docker images.
- **Fixtures and samples:** test fixtures were replaced with labelled SYNTHETIC ones; sample PDFs
  holding CRESCENDDI records were deleted.
- **Kept, unchanged:**
  - the ingestion pipeline (`scripts/data/ingest_crescenddi.py`, `src/ddinet/data/crescenddi.py`);
  - its checksums;
  - the committed `MANIFEST.json` (counts and checksums only);
  - the engine code path.

  A researcher who has the files can rebuild the index into the git-ignored `data/restricted/`
  and use it locally with `DDINET_ENABLE_CRESCENDDI=1`.
- **Aggregate statistics** (counts and rates) are still reported; record-level examples are not.
- **Unresolved, needs the owners' permission:** written permission from the CRESCENDDI authors
  *and* from the BNF Partners and Merative (Micromedex) for a public derived index, or a
  statement from them that the derived records may be redistributed.
- **Git history:** the index is still in the history of `feature/ddinet-v3` (commits
  `8a1e689`…`7ac6299`). Removing it requires rewriting history, which is your decision.

**Data audit (on the locally rebuilt index; same checksums as 2026-10-16).**

| Check | Result |
|---|---|
| Rows read / rejected by schema | 10,286 positive + 4,544 negative / 0 |
| Distinct drug names | 454. Mapped: **392** (384 exact INN, 8 curated alias). Unmapped: **62** |
| Curated-alias mappings (all reviewed) | Acetaminophen → paracetamol; Aspirin → acetylsalicylic acid; Chlorpheniramine → chlorphenamine; Cyclosporine → ciclosporin; Glyburide → glibenclamide; Meperidine → pethidine; Nitroglycerin → glyceryl trinitrate; valacyclovir → valaciclovir. All are standard USAN/INN pairs; none is fuzzy. |
| Mapped IDs with more than one source name | 0 |
| Duplicates (set + unordered pair + MedDRA code) | 0 after collapsing 4 negative duplicates |
| Self-pairs after mapping | 0 |
| Same pair and event both positive and negative | 0 |
| Pair orientation | Stored unordered (`drug_a < drug_b`). CRESCENDDI states no direction, and none is shown. |

The 62 unmapped names were reviewed, not guessed:

| Group | Names | Why left unmapped |
|---|---|---|
| Not in the 1,705-drug universe | heparins (heparin, dalteparin, enoxaparin, tinzaparin, danaparoid); thrombolytics (alteplase, tenecteplase, streptokinase, urokinase); biologics (abciximab, anakinra, golimumab, brentuximab vedotin); aminophylline, asenapine, ataluren, atracurium, bleomycin, carboplatin, cisplatin, clopamide, colchicine, delamanid, eptifibatide, eribulin, fludarabine, fludrocortisone, gentamicin, itraconazole, lithium, mefloquine, methylene blue, nadolol, nefopam, olmesartan, olsalazine, pasireotide, piperaquine, polystyrene sulfonate, sodium oxybate, succinylcholine, tacrolimus, tetrabenazine, trimeprazine, ciprofibrate, Rifampin (rifampicin also absent), aluminium hydroxide, canrenoate, flupenthixol | No target exists |
| **Synonym of an in-universe drug** (candidate aliases, need review) | Chlorthalidone → chlortalidone; Dothiepin → dosulepin; Fusidate → fusidic acid; Mefenamate → mefenamic acid; Methotrimeprazine → levomepromazine; Tiaprofenate → tiaprofenic acid; Valproate → valproic acid | Not added: a curated alias needs a reviewed decision. CRESCENDDI is local-only now, so this changes nothing public. |
| **Ambiguous** (must not be guessed) | Isosorbide (dinitrate or mononitrate); fluticasone (propionate or furoate); candesartan / azilsartan (the universe has the prodrug esters, cilexetil and medoxomil); magnesium carbonate / trisilicate (only magnesium hydroxide in the universe) | Different DrugBank entities |

**MedDRA grouping review (`meddra_effect_map/v1` → `v2`, 2026-10-18).**
- All 179 MedDRA preferred terms in the data were re-read against the outcome each is grouped
  under.
- A term may be grouped only under an outcome that is **the same or narrower** in meaning. It
  must never be grouped under a broader or different clinical outcome.

Changes:

| Term(s) | v1 group | v2 group | Reason |
|---|---|---|---|
| Syncope | Low blood pressure | **Fainting (syncope)**, own group | Syncope has causes other than hypotension (arrhythmia, reflex) |
| Blood creatinine increased | Kidney injury | **Raised blood creatinine** | A laboratory change, not established injury |
| Hepatic enzyme increased; Alanine aminotransferase increased | Liver injury | **Raised liver enzymes (transaminases)** (shared with the label rule) | Same reason |
| Electrocardiogram abnormal; Atrioventricular conduction time shortened | Other rhythm disturbance | **ECG change** (pharmacodynamic) | An ECG finding is not an arrhythmia |
| Cardiac output decreased | Heart failure | **Haemodynamic measure** (pharmacodynamic) | A measurement, not a diagnosis |
| Vascular resistance systemic decreased | Low blood pressure | **Haemodynamic measure** (pharmacodynamic) | Same reason |
| Pyrexia (group name only) | "High body temperature (hyperthermia)" | "High body temperature (fever or hyperthermia)" | Pyrexia is fever |
| Anxiety, Insomnia, Irritability (group name only) | "Change in mental state (confusion, delirium, agitation, psychosis)" | "Change in mental state or behaviour (e.g. confusion, delirium, agitation, anxiety, insomnia)" | The label named only severe examples |

**Reviewed and kept**, each judged the same or narrower:
- INR and prothrombin terms → coagulation measure (pharmacodynamic);
- Blood potassium increased → hyperkalaemia;
- Heart rate decreased → slow heart rate;
- Mean arterial pressure decreased and orthostatic terms → low blood pressure;
- Megaloblastic anaemia and haematotoxicity → suppressed blood cell production;
- Musculoskeletal stiffness, hyperreflexia → movement disorder;
- Brain injury → neurotoxicity;
- Cholestasis → liver injury;
- "Toxicity to various agents" → unspecified toxicity.

The table remains the work of one author. The original MedDRA term is always shown beside the
group.

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

### TAC 2017 ADR labels — **evaluation only (new, 2026-10-18)**

- **Source:** the 200 structured product labels of the TAC 2017 Adverse Drug Reaction track
  (Demner-Fushman D et al., Sci Data 5, 180001, 2018), with section text. They are redistributed
  in the OnSIDES repository (`database/annotations/demner-fushman-{train,test}-labels.json`) at
  commit `fe6a4a4e3415d93d02245692df9fd8277c6177e4`. SHA-256 values are pinned in
  `scripts/data/build_real_label_benchmark.py`.
- **Licence:**
  - OnSIDES data: CC BY 4.0 (read directly in `LICENSE-DATA`).
  - The label text is FDA labelling, a U.S. Government work.
- **Dates:** historical labels from about 2016–2017, not current labelling. Three sections only
  (Boxed Warning, Warnings and Precautions, Adverse Reactions); the engine reads the first two.
- **Use:** source text of the real-label benchmark. Only the sampled excerpts (150 units) are
  committed, in `validation/clinical_outcomes/real_label_benchmark/`. Never served.

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

1. **CRESCENDDI positive controls became pair-specific outcome evidence on 2026-10-16.** On
   2026-10-18 they were **withdrawn from every public build**: licence findings above. The code
   path stays for local research (`meddra_effect_map/v2`).
2. **The label rule became `label_lexicon/v3`.** The no-effect filter was extended after its
   misses were seen on the DDI Corpus **development** split. The Test split was then scored once.
3. **DDI Corpus and CRESCENDDI give the first validation against independently annotated data:**
   `docs/CLINICAL_OUTCOME_VALIDATION.md`.
4. **2026-10-18: `label_lexicon/v4`.** It was developed on the real-label development split
   (TAC 2017 train labels), frozen, then scored once on the evaluation split (TAC 2017 test
   labels).

## What you can do (manual steps)

- **OnSIDES (optional, CC BY 4.0):** download `onsides-v3.1.1.zip` from the repository's
  Releases page in a browser and record its SHA-256. A single-drug context layer would need a new
  ingestion script; none was written, because the data could not be inspected here.
- **DDInter:** if you want it considered, read <https://ddinter2.scbdd.com> terms yourself, and
  decide whether a CC BY-NC-SA source and its severity and management text are acceptable for
  this app. Then share the download with the project. Nothing was downloaded.
- **CRESCENDDI:** public use needs permission. Ask the authors (Kontsioti et al.) and the
  compendium owners (BNF Partners: BMJ / Royal Pharmaceutical Society; Merative for Micromedex)
  whether the derived pair–event records may be redistributed in a public web application. Also
  confirm the figshare licence. Until then, the data stay local (`DDINET_ENABLE_CRESCENDDI=1`).
- **Git history:** decide whether to purge
  `data/reference_sets/crescenddi/crescenddi_index_v1.json.gz` from the branch history. That
  needs `git filter-repo` or BFG plus a force-push of `feature/ddinet-v3`, and it is
  irreversible.
- **Restricted sources** (DrugBank full, CredibleMeds, KEGG) need accounts or licences from their
  providers. They were not used.
