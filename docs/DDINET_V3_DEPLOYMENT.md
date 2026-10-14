# DDI-Net 3.0 — Deployment

How to run DDI-Net 3.0 as a public research demonstration: a free **test** API
on Render connected to a Vercel **Preview** first, production only after the
test passes. Nothing in this document has been executed against Render or
Vercel; §9 lists exactly what was verified locally and what was not.

---

## 1. What runs where

| Component | Host | Built from | Notes |
|---|---|---|---|
| Inference + evidence API | Render web service (Docker) | `serving/Dockerfile.lean`, context = repository root | one process; numpy + FastAPI at runtime |
| Research site | Vercel | `web/` (`web/vercel.json`) | static; reads `VITE_ANALYZE_API` at build time |
| RNPK static site | GitHub Pages | `site/` (`.github/workflows/pages.yml`) | unchanged; deploys only from `claude/ddi-net-drug-interaction-hxrqii` |

The API image is two-stage. The build stage installs torch, PyTorch Geometric
and RDKit, downloads the frozen checkpoint from the GitHub Release (SHA-256
checked), runs the integrity gate and `serving.precompute`, then
`serving.evidence.build`. The runtime stage holds only `serving/`, the 4 MB
lean model artifact and the 0.9 MB evidence artifact. The frozen model and all
scientific results are read, never modified.

## 2. Pre-flight checklist

- [ ] Branch to deploy: `feature/ddinet-v3` (the default branch is untouched).
- [ ] Optional but recommended: a free openFDA API key
      (https://open.fda.gov/apis/authentication/). Without it the service caps
      itself at 800 label lookups per day (openFDA allows 1,000 per IP per day
      without a key, and Render's outbound IPs are shared).
- [ ] Render account with GitHub access to `mametaeverzat014-cell/DDI-Net`.
- [ ] Vercel project linked to the same repository, Root Directory `web`.

## 3. Render: free test API

1. Render Dashboard → **New** → **Web Service** → connect
   `mametaeverzat014-cell/DDI-Net`.
2. Settings:

   | Field | Value |
   |---|---|
   | Name | `ddinet-api-test` (the URL becomes `https://ddinet-api-test.onrender.com` if the name is free) |
   | Language / Runtime | **Docker** |
   | Branch | `feature/ddinet-v3` |
   | Region | Frankfurt (EU Central) |
   | Root Directory | *(empty)* |
   | Dockerfile Path | `./serving/Dockerfile.lean` |
   | Docker Build Context Directory | `.` |
   | Instance Type | **Free** |
   | Health Check Path | `/api/health/ready` |
   | Auto-Deploy | Off (deploy manually while testing) |

3. Environment variables (Render → Environment):

   | Key | Value |
   |---|---|
   | `DDINET_ENGINE` | `lean` |
   | `DDINET_EXTERNAL_SOURCES` | `on` |
   | `DDINET_PROXY_HOPS` | `1` |
   | `OPENFDA_API_KEY` | your key (mark it secret), or leave unset |

   Leave unset: `PORT` (Render injects it), `DDINET_ALLOW_NO_MODEL`,
   `DDINET_RATE_LIMIT` (limits must stay on), `DDINET_REQUIRE_EVIDENCE` (already
   `1` in the image).
4. **Create Web Service.** The first build installs the scientific stack and
   runs precompute: expect roughly 10–20 minutes. It draws on the workspace's
   build minutes (Hobby: 500 per month at the time of writing).
5. When the deploy is live, run §5.

`render.yaml` describes the *production* service (Starter plan) with the same
settings; it is not needed for the test service.

## 4. Vercel: Preview connected to the test API

1. Vercel → Project → **Settings → Environment Variables** → Add:
   - Key `VITE_ANALYZE_API`, value `https://ddinet-api-test.onrender.com`
     (no trailing slash).
   - Environment: **Preview** only; Git branch: `feature/ddinet-v3`.
2. Vercel → **Deployments** → the latest deployment of `feature/ddinet-v3` →
   the three-dot menu → **Redeploy** (with the build cache off). `VITE_*`
   values are compiled into the bundle, so the variable takes effect only
   after a new build.
   If no deployment of the branch exists yet, push any commit to the branch or
   create one from the dashboard.
3. Open the Preview URL and check §5.4.

Production is not touched: the Production variable and the production branch
stay as they are.

## 5. Verification

### 5.1 API

```bash
API=https://ddinet-api-test.onrender.com
curl -s $API/api/health/ready
#   {"ready":true,"model_available":true,"evidence_available":true}   (HTTP 200)
curl -s $API/api/health
#   "engine":"lean", "evidence_available":true, checkpoint_sha256 b828a471…
curl -s -X POST $API/api/analyze -H 'content-type: application/json' \
  -d '{"drug_a":"DB00331","drug_b":"DB00682"}' | head -c 300
#   the v2 endpoint, unchanged
```

### 5.2 First live check of the external sources

These have never been exercised against the real services (the development
environment blocked them):

```bash
curl -s "$API/api/v3/resolve?q=Coumadin"
#   expected: "status":"resolved", "drug":{"id":"DB00682",…}, rxnorm block present
curl -s -X POST $API/api/v3/report -H 'content-type: application/json' \
  -d '{"drug_a":"warfarin","drug_b":"fluconazole"}' > report.json
python3 -c "import json; d=json.load(open('report.json')); print(d['evidence_status']); print(d['sources_checked'])"
#   openfda_label "ok" or "no_match"  = labels work
#   openfda_label "unavailable"       = see §8
```

Read two or three label excerpts in `report.json` (`evidence[*]` with
`statement_origin` `verbatim_excerpt`) against the DailyMed link in
`source_url`, to confirm the matching picks the right sentences.

### 5.3 Rate limiting and client identity

```bash
# The right-most X-Forwarded-For entry (added by Render) must be your address,
# not the fake one you prepend:
curl -s -H "X-Forwarded-For: 1.2.3.4" $API/api/v3/limits | python3 -m json.tool | grep your_client_key
#   your_client_key should be YOUR public IP, not 1.2.3.4
# Multi-drug: 4 per minute per client, the 5th is refused with Retry-After.
for i in 1 2 3 4 5; do curl -s -o /dev/null -w "%{http_code} " -X POST $API/api/v3/multi \
  -H 'content-type: application/json' -d '{"drugs":["warfarin","fluconazole"],"include_labels":false}'; done; echo
#   200 200 200 200 429
```

If `your_client_key` shows `1.2.3.4`, the proxy chain differs from what the
code assumes: set `DDINET_PROXY_HOPS` to the number of trusted proxies (see
`serving/ratelimit.py`) and repeat. If it shows the same Render-internal
address for everyone, every visitor shares one bucket; raise the hop count.

### 5.4 Site (Vercel Preview)

- `#/analyzer?a=DB00682&b=DB00196`: status banner, five sections, numbered
  sources, `sources_checked` shows the label source status.
- Research mode: model panel with regime, measured performance, reliance bars.
- `#/mechanisms?a=DB00641&b=DB01211`: graph, select CYP3A4, provenance panel.
- `#/multi`: 4 drugs, 6 pairs, network, scope note above results.
- Browser console: no CORS errors; repeated rapid clicking eventually shows the
  "too many requests" notice, not a blank or empty report.

## 6. Production (later, after §5 passes)

1. Review and merge the `feature/ddinet-v3` pull request into the production
   branch, or point the production services at `feature/ddinet-v3`.
2. Render production service (`render.yaml`, Starter plan): set the variables
   of §3.3, confirm Health Check Path `/api/health/ready`, deploy manually.
3. Vercel: set `VITE_ANALYZE_API` for **Production** to the production API URL
   and redeploy production.
4. Repeat §5 against production.

**Rollback.** Render → service → Events → the previous successful deploy →
Rollback. Vercel → Deployments → the previous production deployment →
Promote / Instant Rollback. The old site works with the new API (the v2
endpoint is unchanged) and the new site works with an old API (it reports the
evidence service as unavailable).

## 7. Reference

### 7.1 API environment variables

| Variable | Default | Set on Render | Meaning |
|---|---|---|---|
| `DDINET_ENGINE` | `lean` | `lean` | numpy serving path (the full torch path is not used on Render) |
| `DDINET_EXTERNAL_SOURCES` | `on` | `on` | `off` disables openFDA and RxNorm; reports then say so |
| `OPENFDA_API_KEY` | unset | recommended | raises the openFDA quota; never returned to clients |
| `DDINET_OPENFDA_DAILY_BUDGET` | 800 without key, 100,000 with | no | network calls to openFDA per UTC day before the source reports "unavailable" |
| `DDINET_RXNORM_DAILY_BUDGET` | 20,000 | no | same for RxNorm |
| `DDINET_PROXY_HOPS` | `1` | `1` | trusted proxies in front of the app, for the client key |
| `DDINET_RATE_LIMIT` | `on` | no | `off` disables rate limiting — never on a public service |
| `DDINET_REQUIRE_EVIDENCE` | `0` (`1` in the images) | no | a missing/stale evidence artifact stops startup |
| `DDINET_ALLOW_NO_MODEL` | `0` | no | development only |
| `DDINET_EVIDENCE_ARTIFACT` | `runtime/evidence/evidence_v1.json.gz` | no | artifact path |
| `PORT` | 8000 | injected | listening port |

### 7.2 Site environment variable

| Variable | Scope | Value |
|---|---|---|
| `VITE_ANALYZE_API` | Preview (branch `feature/ddinet-v3`) / Production | API base URL, no trailing slash; unset = the site says the service is not connected |

### 7.3 Rate limits (`serving/ratelimit.py`)

| Route class | Endpoints | Per client | All clients |
|---|---|---|---|
| resolve | `GET /api/v3/resolve` | 60/min, 600/h | 1,200/min |
| pair | `POST /api/v3/report`, `/graph` | 30/min, 300/h | 600/min |
| **multi** | `POST /api/v3/multi` | **4/min, 30/h** | 40/min, 600/h |
| meta | `/api/v3/sources`, `/limits`, unknown | 20/min | 300/min |

`/api/analyze` and `/api/health*` are not limited. POST bodies over 16 KiB are
refused (413); a POST without Content-Length gets 411. Refusals are 429 with
`Retry-After` and a JSON body; accepted requests carry `X-RateLimit-Limit` and
`X-RateLimit-Remaining`. State is in memory in the single worker: it resets on
restart (including every free-plan wake-up) and would not be shared across
several workers or instances.

### 7.4 Endpoints

`/api/health` (descriptive, always 200 once started), `/api/health/ready`
(200 only with model and evidence loaded — the health check), `/api/analyze`
(v2), `/api/v3/{resolve,report,graph,multi,sources,limits}`. Schemas:
`docs/DDINET_V3_ARCHITECTURE.md` §3.

## 8. Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| Build fails at `pip install` | PyTorch CPU index unreachable or a version yanked | retry; check the build log for the package; versions are pinned in `serving/requirements.txt` |
| Build fails at `sha256sum -c` | checkpoint download corrupted or the Release asset changed | retry; the hash is the frozen one and must not be edited |
| Build fails at `serving.precompute` with `IntegrityError` | a hash-gated file differs from the frozen tag | do not edit `serving/frozen_manifest.json`; restore the file named in the error |
| Build fails with out-of-memory | precompute peaked at 1.3 GB resident when measured; Hobby builds have 8 GB | unusual; retry, or build on a Professional workspace |
| Deploy fails, health check never passes | evidence artifact missing → startup stops by design | read the runtime log; the build must have run `serving.evidence.build` |
| `/api/v3/*` 503 | evidence layer not installed (only if `DDINET_REQUIRE_EVIDENCE` was changed to 0) | restore the default |
| `openfda_label: unavailable` | outbound blocked, openFDA down, quota or daily budget spent | `/api/v3/limits` → `external_daily_budget`; add `OPENFDA_API_KEY` |
| Everyone gets 429 quickly | all clients share one key | §5.3; adjust `DDINET_PROXY_HOPS` |
| First request after a pause takes ~1 minute | free plan sleeps after 15 minutes idle | expected on Free; Starter is always on |
| Site says "not connected" | `VITE_ANALYZE_API` unset for that environment or not rebuilt | set it for the right scope and redeploy |
| CORS error in the browser | API URL wrong (redirect) or trailing slash | use the exact `https://…onrender.com` origin |

## 9. What was verified before deployment, and what was not

Verified in the development environment (commit history of
`feature/ddinet-v3`):

* The Docker build context after `.dockerignore` (111 files, 16 MiB) contains
  every `COPY` source of both Dockerfiles and every integrity-checked file
  (`tests/test_docker_context.py`, matcher cross-checked against docker-py).
* The build-stage commands, run in a directory holding only that context with
  the checkpoint placed and hash-checked as the Dockerfile does: integrity gate,
  `serving.precompute` and `serving.evidence.build` succeed; the evidence
  artifact is byte-identical to the one built from the full tree and the model
  artifact's arrays are identical.
* The runtime stage under **Python 3.11.15** with only
  `serving/requirements-lean.txt` installed (numpy 2.4.6, fastapi 0.141.1,
  pydantic 2.14.1, uvicorn 0.54.0; pandas/torch/rdkit/sklearn/scipy absent):
  the Dockerfile's `HEALTHCHECK` command exits 0, `/api/health/ready` 200,
  `/api/analyze` 200, `/api/v3/report` 200 with the reliance readout, rate-limit
  headers present, spoofed `X-Forwarded-For` prefix ignored, the 5th multi
  request in a minute refused with 429, resident memory 219 MB.
* With the evidence artifact removed, the server refuses to start (exit 3).
* All 172 Python files of `serving/`, `src/`, `tests/`, `scripts/` and
  `web/tools/` compile under Python 3.11.
* Every pinned package of both requirement files exists as a CPython 3.11
  wheel on PyPI.

Not verified:

* An actual `docker build` (no Docker daemon was available); the steps were
  reproduced command by command instead.
* The PyTorch CPU index (`download.pytorch.org`) from Render.
* Live openFDA and RxNorm responses (§5.2 is the first live check).
* Render's proxy behaviour for `X-Forwarded-For` (§5.3 checks it).

## 10. Costs (at the time of writing — check the providers' pages)

| Item | Test | Production |
|---|---|---|
| Render web service | Free: $0 (512 MB, 0.1 CPU, sleeps after 15 min; 750 free instance-hours per workspace per month) | Starter: $7/month (512 MB, 0.5 CPU, always on) |
| Render builds | Hobby: 500 build minutes per month included | same |
| Vercel | Hobby: $0, personal non-commercial use | Hobby $0; Pro about $20 per seat per month if use becomes commercial |
| openFDA, RxNorm | free | free |

Measured memory (219 MB) fits 512 MB with margin.

## 11. Responsible public use

* Every page and every report states that this is a research prototype, not a
  medical device, and refers medication decisions to a doctor or pharmacist.
* The API accepts only drug names and DrugBank IDs and stores nothing to disk.
  Uvicorn's access log (client address, method, path including the `resolve`
  query) goes to the host's log stream; Render keeps it under its own retention
  policy. Request bodies (the drug pairs) are not logged.
* DrugBank-derived statements are shown per query for non-commercial research
  use; no endpoint returns the records in bulk (multi-drug is capped at 8 drugs
  and rate limited).
