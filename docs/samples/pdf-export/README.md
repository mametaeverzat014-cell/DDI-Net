# Sample PDF reports

**Dates.** The warfarin + fluconazole reports were regenerated on 2026-10-16, after the
CRESCENDDI reference set was integrated (`docs/DATASET_AUDIT.md`). The other reports are from
2026-10-15, before that, so they show no CRESCENDDI source even where the current API would list
one.

These reports were generated after the Clinical Outcome Engine
was added (`docs/DDINET_V3_CLINICAL_OUTCOMES_ARCHITECTURE.md`).

**How they were generated.** Unless marked SYNTHETIC, each one was made by
clicking **Quick PDF** or **Export PDF** in Chromium (Playwright):

* on a production build of the site from `feature/ddinet-v3`, served locally;
* connected to a local DDI-Net 3.0 API (`uvicorn serving.api:app`, lean engine,
  frozen BIO-GINE checkpoint) running this branch's backend;
* with the browser time zone set to UTC.

**Quick Reports** are one or two pages and use blocks A–F:
* A — interaction status;
* B — what could happen, quoting the sources' words;
* C — why it could happen;
* D — how certain the information is;
* E — what BIO-GINE adds;
* F — the important limitation.

**Full reports** add the outcome table, the provenance of every outcome, a
chain figure, and every record.

| File | Page | Language |
|---|---|---|
| `DDI-Net_QuickReport_Warfarin_Fluconazole_2026-10-16.pdf` / `_RU` | Analyzer, Quick; **with the CRESCENDDI reference set** (documented bleeding, "Haemorrhage") | EN / RU |
| `DDI-Net_Report_Warfarin_Fluconazole_2026-10-16.pdf` / `_RU` | Analyzer, Full; CRESCENDDI shown as its own source document, severity grades not reproduced | EN / RU |
| `DDI-Net_QuickReport_Warfarin_Acetylsalicylic-acid_2026-10-15.pdf` / `_RU` | Analyzer, Quick; a documented pharmacodynamic effect | EN / RU |
| `DDI-Net_Report_Warfarin_Acetylsalicylic-acid_2026-10-15.pdf` / `_RU` | Analyzer, Full | EN / RU |
| `DDI-Net_QuickReport_Metformin_Warfarin_2026-10-15.pdf` | Analyzer, Quick; nothing documented | English |
| `DDI-Net_Report_Metformin_Warfarin_2026-10-15.pdf` | Analyzer, Full | English |
| `DDI-Net_Report_Simvastatin_Clarithromycin_2026-10-15_from-Mechanisms-page.pdf` | Mechanisms (full graph) | English |
| `DDI-Net_Report_Hydroxyprogesterone-caproate_Pentaerithrityl-tetranitrate_2026-10-15_RU.pdf` | Analyzer; two of the longest drug names | Russian |
| `DDI-Net_MultiDrug_Report_Warfarin_Fluconazole_Simvastatin_and_3_more_2026-10-15.pdf` / `_RU` | Multi-Drug Explorer, 6 drugs (with acetylsalicylic acid and metformin), 15 pairs | EN / RU |
| `DDI-Net_MultiDrug_Report_Warfarin_Fluconazole_Simvastatin_and_5_more_2026-10-15_RU.pdf` | Multi-Drug Explorer, 8 drugs, 28 pairs | Russian |
| `SYNTHETIC_TEST_DATA_merged-labels_Warfarin_Fluconazole_{EN,RU}.pdf` | **Synthetic test data**, Full | EN / RU |
| `SYNTHETIC_TEST_DATA_merged-labels_Warfarin_Fluconazole_QuickReport_{EN,RU}.pdf` | **Synthetic test data**, Quick | EN / RU |
| `SYNTHETIC_TEST_DATA_duplicated-labels_old-API_Warfarin_Fluconazole_RU.pdf` | **Synthetic test data** as the old API (without `outcomes`) sends it | Russian |

The SYNTHETIC files were rendered by `web/tools/render_sample_reports.tsx`.

What to know when reading them:

* **openFDA was unreachable.**
  * The build container's network policy blocks it, so "FDA labels (openFDA)"
    is reported as **unavailable**. The real reports therefore contain no
    label excerpts and no label-documented outcomes.
  * Warfarin + fluconazole shows the DrugBank exposure change, "mechanistically
    supported" by the protein roles. Warfarin + acetylsalicylic acid shows
    DrugBank's "anticoagulant activities increased" as a pharmacodynamic
    effect, not as bleeding. Metformin + warfarin shows that nothing is
    documented, without any claim of safety.
* **How a label-documented outcome looks: the SYNTHETIC merged-labels files.**
  * They carry the real DrugBank, mechanism and model blocks for warfarin +
    fluconazole, together with **synthetic** FDA label text from
    `tests/synthetic_labels.py`. Every sentence is marked "[synthetic]" and the
    set IDs are all zeros.
  * The engine finds two things in that text: "bleeding" as a documented
    clinical outcome, and a prothrombin-time change as a pharmacodynamic
    effect. Each is quoted verbatim with its method
    (`label_lexicon/v2:term=…`).
  * Nothing in these files may be cited as label text.
* **Old API.** The duplicated-labels file shows how the report reads an API
  response without the `outcomes` block. It states that the outcome view needs
  the updated service.
* **Local addresses.** "Site" is `http://127.0.0.1:4173` and "Service"
  `http://127.0.0.1:8765`. The site build commit is "not recorded" because the
  build ran outside Vercel.
* **Checks run on every file:**
  * pypdf (strict) and poppler;
  * fonts embedded, IBM Plex only; Cyrillic extracted from the Russian files;
  * no replacement characters, no "NaN" or "undefined";
  * no "safe combination" wording;
  * nothing in the margins, header or footer bands, and no overlapping lines;
  * correct page numbers;
  * no page but the last under 40 % filled;
  * Quick Reports at most 2 pages.

Research use only. Not a medical device and not clinical decision support.
