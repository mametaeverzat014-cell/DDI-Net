# Sample PDF reports

These reports were generated on 2026-10-15, after the report quality pass
(`docs/DDINET_V3_REPORT_QUALITY_PASS.md`). Unless marked otherwise, they were
made by clicking **Export PDF** / **JSON** in Chromium (Playwright):

* on a production build of the site from `feature/ddinet-v3`, served locally;
* connected to a local DDI-Net 3.0 API (`uvicorn serving.api:app`, lean engine,
  frozen BIO-GINE checkpoint) running this branch's backend;
* with the browser time zone set to UTC.

| File | Page | Language |
|---|---|---|
| `DDI-Net_Report_Warfarin_Fluconazole_2026-10-15.pdf` | Analyzer | English |
| `DDI-Net_Report_Warfarin_Fluconazole_2026-10-15_RU.pdf` | Analyzer | Russian |
| `DDI-Net_Report_Warfarin_Fluconazole_2026-10-15.json` | Analyzer, companion JSON of the English PDF | — |
| `DDI-Net_Report_Simvastatin_Clarithromycin_2026-10-15_from-Mechanisms-page.pdf` | Mechanisms (full graph) | English |
| `DDI-Net_Report_Metformin_Warfarin_2026-10-15.pdf` | Analyzer; nothing documented, no label evidence | English |
| `DDI-Net_Report_Hydroxyprogesterone-caproate_Pentaerithrityl-tetranitrate_2026-10-15_RU.pdf` | Analyzer; two of the longest drug names in the dataset | Russian |
| `DDI-Net_MultiDrug_Report_Warfarin_Fluconazole_Simvastatin_and_3_more_2026-10-15.pdf` | Multi-Drug Explorer, 6 drugs, 15 pairs | English |
| `DDI-Net_MultiDrug_Report_Warfarin_Fluconazole_Simvastatin_and_3_more_2026-10-15_RU.pdf` | Multi-Drug Explorer, 6 drugs, 15 pairs | Russian |
| `DDI-Net_MultiDrug_Report_Warfarin_Fluconazole_Simvastatin_and_5_more_2026-10-15_RU.pdf` | Multi-Drug Explorer, 8 drugs, 28 pairs | Russian |
| `SYNTHETIC_TEST_DATA_duplicated-labels_Warfarin_Fluconazole_RU.pdf` | **Synthetic test data**, rendered by `web/tools/render_sample_reports.tsx` | Russian |

What to know when reading them:

* **openFDA was unreachable.** The local API could not reach openFDA (the build
  container's network policy blocks it), so "FDA labels (openFDA)" is reported
  as **unavailable** and the real reports contain no label excerpts. The
  reports say so; they do not fill the gap.
* **How label grouping looks: the SYNTHETIC file.** It carries the real
  DrugBank, mechanism and model blocks for warfarin + fluconazole, together
  with **synthetic** FDA label text (`tests/synthetic_labels.py`; every sentence
  marked "[synthetic]", set IDs all zeros). That text is structured like an
  older-format label that repeats its Drug Interactions subsection, and it is
  delivered the way the API version still on Render sends it: 6 label records.
  * The report shows 2 label documents and 4 distinct excerpts, and lists all
    7 records in Supplement S1.
  * Its cover and summary state that it is synthetic test data. Nothing in it
    may be cited as label text.
* **Local addresses.** "Site" is `http://127.0.0.1:4173` and "Service"
  `http://127.0.0.1:8765`. The site build commit is "not recorded" because the
  build ran outside Vercel.
* **The JSON and the English PDF belong together.** The `.json` file's
  `payload_sha256` equals the hash printed in the English two-drug PDF
  (section 7). Its report ID differs only in the time part, because the two
  files were generated a moment apart.
* **Checks run on every file:**
  * pypdf (strict) and poppler;
  * fonts embedded, IBM Plex only; Cyrillic extracted from the Russian files;
  * nothing in the margins, header or footer bands; no overlapping lines;
  * correct page numbers; no page but the last under 40 % filled.

Research use only. Not a medical device and not clinical decision support.
