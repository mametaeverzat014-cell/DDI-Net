# DDI-Net

**An interpretable graph neural network for predicting dangerous drug–drug interactions.**

Regeneron ISEF project — Computational Biology & Bioinformatics.

---

## The problem

Adverse drug–drug interactions (DDIs) are a major, partly preventable source of harm. The number of
possible pairs grows quadratically with the number of drugs, so exhaustive clinical testing is
impossible — which makes computational prediction genuinely useful rather than merely convenient.

DDI-Net predicts, for a pair of drugs, whether they interact and whether the interaction is
**clinically dangerous** (operationally: DDInter severity = *Major*), and explains **which molecular
substructures and metabolic pathways drove the prediction**.

## Project status

| Step | Status |
|---|---|
| 1. Data collection, parsing, leakage-free splits | **complete** |
| 2. Molecular features + interaction graph | in progress |
| 3. GNN with attention | pending |
| 4. Evaluation, CV, baselines, FAERS validation | pending |
| 5. Interpretability + visualisation | pending |
| 6. Streamlit demo | pending |

## Quick start

```bash
pip install -r requirements.txt

python scripts/00_data_report.py        # data provenance, licences, validation
python scripts/01_download_data.py      # fetch external sources (network permitting)
python scripts/02_build_dataset.py --source curated --group-by scaffold --neg-ratio 3
python -m pytest tests/ -q
```

The pipeline runs immediately against a committed, hand-curated seed dataset — no licence wait, no
network required.

## Two methodological commitments

These are the decisions the whole project rests on.

**1. Drug-level splits, always.** Shuffling *pairs* lets a model memorise which drugs are
promiscuous instead of learning chemistry, and produces AUCs around 0.99 that mean nothing. We
partition *drugs* (optionally *scaffolds*) and report three settings separately:

- **S1** both drugs seen in training — optimistic, database gap-filling
- **S2** one drug new — *the clinically important question*
- **S3** both drugs new — the honest structure-only test

The drop from S1 → S3 is a result, not a failure.

**2. Negatives are unlabelled, not negative.** No database records non-interactions, so this is
positive-unlabelled learning. Precision is a lower bound. We sample negatives *degree-matched* so
hub-drug frequency can't be exploited as a shortcut — measured to shrink the exploitable degree gap
from 4.17 to 0.68.

## Repository layout

```
data/
  curated/      committed seed set: 104 drugs, 467 interactions (formula-verified)
  raw/          downloads (gitignored — some sources are licence-restricted)
  processed/    built datasets (gitignored — reproducible from code)
src/ddinet/
  data/         sources registry, downloader, parsers, splits, assembly
  features/     fingerprints, molecular graphs        (Step 2)
  models/       GNN architectures                     (Step 3)
  eval/         metrics, CV, baselines, leakage audit (Step 4)
  explain/      attention → substructure attribution  (Step 5)
scripts/        numbered CLI entry points
tests/          integrity tests (no network required)
docs/           per-step write-up notes with ISEF talking points
app/            Streamlit demo                        (Step 6)
```

## Data sources and licences

Run `python scripts/00_data_report.py` for the full table with citations. Summary:

| Source | Provides | Licence | Access |
|---|---|---|---|
| DrugBank Open Data | ID ↔ name ↔ InChIKey crosswalk | CC0 | direct |
| DrugBank full (XML) | interactions, mechanisms, CYP450 roles | Academic | **manual licence** |
| PubChem PUG-REST | SMILES by InChIKey | Public domain | API |
| SIDER 4.1 | side-effect profiles | CC BY-NC-SA | direct |
| DDInter 2.0 | **clinical severity** | Free academic | direct |
| BioSNAP ChCh-Miner | benchmark DDI graph | Research use | direct |
| TWOSIDES | FAERS-mined pairs | CC BY 4.0 | direct |
| openFDA FAERS | real-world validation | Public domain | API |

Raw downloads are gitignored: several sources prohibit redistribution, and all are reproducible
from code. Every download is SHA-256 pinned in `data/raw/manifest.json`, because "we used DrugBank"
is not a reproducible statement but "we used the release hashing to `a1b2c3…`" is.

## About the curated seed set

`data/curated/` holds 104 drugs and 467 documented interactions, hand-assembled from standard
clinical pharmacology. Every SMILES is validated against an independently stated molecular formula
by RDKit — a check that caught 4 real structural errors during construction.

**It is a development fixture, not an evaluation corpus.** Because its pairs were curated with
mechanism in mind, its labels are strongly determined by the CYP450 annotation columns, so a model
given those features and evaluated here would be re-deriving the rule that made the labels.
Headline numbers come from DrugBank / DDInter / BioSNAP. See
[`docs/step1_data.md`](docs/step1_data.md) §1.3.

## Documentation

- [`docs/step1_data.md`](docs/step1_data.md) — data sources, splitting, negative sampling,
  limitations, and ISEF interview preparation

## Disclaimer

Research and educational software. **Not a medical device and not clinical decision support.** No
output should be used to make treatment decisions.
