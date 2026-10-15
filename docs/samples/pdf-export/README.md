# Sample PDF reports

Generated on 2026-10-15 by clicking **Export PDF** / **JSON** in Chromium
(Playwright) on a production build of the site (`feature/ddinet-v3`), served
locally and connected to a local DDI-Net 3.0 API (`uvicorn serving.api:app`,
lean engine, frozen BIO-GINE checkpoint). Browser time zone: UTC.

| File | Page | Language |
|---|---|---|
| `DDI-Net_Report_Warfarin_Fluconazole_2026-10-15.pdf` | Analyzer | English |
| `DDI-Net_Report_Warfarin_Fluconazole_2026-10-15_RU.pdf` | Analyzer | Russian |
| `DDI-Net_Report_Warfarin_Fluconazole_2026-10-15.json` | Analyzer, companion JSON of the English PDF | — |
| `DDI-Net_Report_Simvastatin_Clarithromycin_2026-10-15_from-Mechanisms-page.pdf` | Mechanisms (full graph) | English |
| `DDI-Net_MultiDrug_Report_Warfarin_Fluconazole_Simvastatin_and_3_more_2026-10-15.pdf` | Multi-Drug Explorer, 6 drugs, 15 pairs | English |
| `DDI-Net_MultiDrug_Report_Warfarin_Fluconazole_Simvastatin_and_3_more_2026-10-15_RU.pdf` | Multi-Drug Explorer, 6 drugs, 15 pairs | Russian |

What to know when reading them:

* The local API could not reach openFDA (the build container's network policy
  blocks it), so "FDA labels (openFDA)" is reported as **unavailable** and no
  label excerpts appear. The reports say so; they do not fill the gap.
* "Site" is `http://127.0.0.1:4173` and "Service" `http://127.0.0.1:8765`; the
  site build commit is "not recorded" because the build ran outside Vercel.
* The `.json` file's `payload_sha256` equals the hash printed in the English
  two-drug PDF (section 7); its report ID differs only in the time part, since
  the two files were generated a moment apart.

Research use only. Not a medical device and not clinical decision support.
