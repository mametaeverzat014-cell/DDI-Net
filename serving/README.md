# DDI-Net research inference API

Read-only scoring against the **frozen seed-0 BIO-GINE M4 checkpoint**
`bd45f84e3c1b2c33.pt`, released with tag `v2-final-github-safe-2026-09-03`.

> This is a computational research prototype. Its output is not medical advice
> and is not validated for clinical decision-making.

## What it does and does not do

It scores a pair of drugs **from the frozen 1,705-drug universe** and returns a
research model score. It does not train, fine-tune, recalibrate, or write to any
scientific artifact. Arbitrary SMILES are refused: the frozen evaluation
characterises this universe, and a score outside it would carry none of it.

The DDI label is never an input. Whether a pair is documented in the frozen
dataset is returned separately, in `dataset_record`, computed after scoring from
a lookup no representation code can reach.

## Running it

```bash
# 1. fetch the checkpoint (18 MB, not in git history)
mkdir -p runtime/model_assets
curl -sSL -o runtime/model_assets/bd45f84e3c1b2c33.pt \
  https://github.com/mametaeverzat014-cell/DDI-Net/releases/download/v2-final-github-safe-2026-09-03/bd45f84e3c1b2c33.pt

# 2. serve
pip install -r serving/requirements.txt
uvicorn serving.api:app --port 8000

# 3. or containerised (fetches and hash-checks the checkpoint itself)
docker build -f serving/Dockerfile -t ddinet-api .
docker run -p 8000:8000 ddinet-api
```

The frontend reads `VITE_ANALYZE_API`. Unset, the Analyze page says the API is
not connected and shows no score — it never invents one.

```bash
VITE_ANALYZE_API=https://your-api.example npx vite build
```

## Integrity

`serving/integrity.py` runs before the first score and refuses to serve if
anything has moved:

| checked | why |
|---|---|
| checkpoint SHA-256 | the weights must be the released ones |
| 6 source modules | the working branch is **not** a descendant of the frozen commit, so identity is verified rather than assumed |
| 5 `mechanism_v1` files | the model is keyed on this exact drug and annotation set |
| vendored calibration CSV | the temperature must be the one fitted for this checkpoint |

## Parity with the frozen predictions

Measured over **all 92,448** frozen seed-0 rows, on CPU:

| | probability space | logit space |
|---|---|---|
| max \|Δ\| | 8.37e-06 | 8.17e-02 |
| mean \|Δ\| | 1.05e-07 | 4.93e-04 |

The logit figure is above float32 round-off, so it was chased down. Running the
same weights in **float64** on CPU does not shrink the disagreement at all
(mean 4.922e-04 vs 4.930e-04), while float32-CPU and float64-CPU differ from
each other by 2.7e-06. A gap float64 cannot close is not this pipeline's
round-off — it is the frozen run's GPU arithmetic (TF32 carries a 10-bit
mantissa, ~5e-4 relative, which matches the magnitude).

Four checks say arithmetic rather than a preprocessing mismatch, which would
bias scores instead of scattering them:

- signed logit error is centred: mean +5.9e-05 against SD 3.3e-03;
- Brier reproduces to 1.7e-10, ECE15 to 1.3e-09;
- parameter count is exactly 1,122,804, the published figure;
- two independent batching paths agree with each other to 8.8e-08 while both
  sit 8.4e-06 from the stored values.

The served tolerance is therefore **1e-05 in probability space**, the quantity
the API returns and the site displays to three decimals.

### What parity does not claim

Recomputing the frozen AUPRC on CPU gives **0.821497** against the recorded
**0.823534**. 5.83% of the frozen seed-0 pooled predictions are exactly `1.0` in
float32 — one saturated tie block of 4,936 rows (4,564 positive, 372 negative)
at the top of the ranking, where average precision is most sensitive. Jitter of
±1e-09, far below the observed difference, already moves AUPRC by ±3.2e-04.
The 2.0e-03 gap is a numerical property of a saturated ranking metric, not a
correction: the published number stands on its own frozen predictions, and
2.0e-03 is 0.22× the across-seed SD of 9.1e-03 the hypothesis tests used.
Recorded in `LIMITATIONS.md`.

## Performance

| | |
|---|---|
| startup (load + encode all 1,705 drugs) | ~7.7 s |
| warm request, median | 2.3 ms |
| warm request, p95 | 2.8 ms |
| process RSS | ~1.15 GiB |

The checkpoint, drug index, molecular graphs, biological vocabularies and the
**full drug encoding** are built once at startup. A request is one decoder pass.
Caching the encoding is exact, not an approximation: the molecular encoder uses
LayerNorm rather than BatchNorm and dropout is inactive under `eval()`, so no
drug's vector depends on its batch.

RSS rules out Vercel/Lambda-style serverless (256 MB–1 GB). Any CPU container
host with **≥2 GB RAM** works: Fly.io, Render, Railway, Hugging Face Spaces.
