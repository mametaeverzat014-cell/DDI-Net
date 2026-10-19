# DDI-Net 3.0 — Production release runbook (2026-10-19)

**Status when written:**
- Release PR #1 is open. It is **not merged**.
- **Production is unchanged.**
- The build container cannot reach Render, Vercel or the production URL (network policy). Every
  step marked **YOU** needs your browser or dashboard.

## 1. Pre-release audit findings

| Item | Finding |
|---|---|
| Production branch | `claude/ddi-net-drug-interaction-hxrqii` (the repository's default branch). Vercel builds Production from it. |
| Production commit | `aa04493` ("Baseline, изолирующий графовость молекулярного энкодера"), the v2 site |
| Current production deployment (rollback target) | Vercel deployment **`ddi-gazi4tk0v-yerzats-projects.vercel.app`** of `aa04493` (GitHub deployment `6453313532`, status of 2026-10-14). Earlier one of the same commit: `ddi-a9z80qx6b-yerzats-projects.vercel.app`. |
| Production API (GitHub deployment record) | `https://ddinet-api.onrender.com`, last recorded deploy from `6ddbee5` (2026-09-11). It serves only the v2 `/api/analyze`, with no `/api/v3`, unless it was redeployed since. **Not verified.** |
| Development branch | `feature/ddinet-v3` at `a52356f`: 12 commits ahead of production, 0 behind |
| Release branch | `release/ddinet-v3` at `67731a4`. One commit on top of `aa04493`, tree **identical** to `a52356f`. |
| Restricted data | The CRESCENDDI index is absent from the release tree, from the release commit's history and from both Docker images. It is still in the history of `feature/ddinet-v3` (`8a1e689`…`7ac6299`). That is why the release is a single clean commit and the PR comes from `release/ddinet-v3`, not from the feature branch. |
| CRESCENDDI in the API | Off by default; it needs `DDINET_ENABLE_CRESCENDDI=1` **and** a file that is not in the image. Tested. |
| CORS | `allow_origins=["*"]`, read-only, no credentials. `https://ddi-net.vercel.app` is allowed. |
| Secrets | None in tracked files or in the built bundle. No `.env` file is tracked. `OPENFDA_API_KEY` is a Render dashboard secret (`sync: false`). |
| GitHub Pages | The release changes nothing under `site/` or `.github/`; the Pages workflow is unaffected. |
| Tests on the release tree | Python 837 passed, 3 skipped, 1 failed. The failure is environmental and predates this release: `test_sider_refuses_…` needs SIDER raw files. Web 179 passed; `tsc`, ESLint and `vite build` clean. |
| API smoke script | 26/26 against a local API built from this tree. Production is still to be run. |
| Remaining P0 | None in what the site or API serves. The restricted file in the feature branch's git history is a repository-level issue (§6), separate from the website. |

## 2. Release steps

**Step 1 — YOU: deploy the production backend.** In Render, open service `ddinet-api`:
1. **Settings → Build & Deploy → Branch:** `release/ddinet-v3`. After step 4 you can switch it to
   the production branch, which will then hold the same tree.
2. **Dockerfile path:** `./serving/Dockerfile.lean`. **Docker context:** `.` (repository root).
3. **Health Check Path:** `/api/health/ready`.
4. **Environment:**
   - `DDINET_ENGINE=lean`;
   - `DDINET_EXTERNAL_SOURCES=on`;
   - `DDINET_PROXY_HOPS=1`;
   - `OPENFDA_API_KEY` (optional, recommended).
   - **Do not** set `DDINET_ENABLE_CRESCENDDI`.
5. **Manual Deploy → Deploy latest commit.** Confirm it shows `67731a4`, and wait until it is
   **Live** (10–20 minutes).
6. Before deploying, note the currently live deploy in **Events**. That is the backend rollback
   target.

**Step 2 — YOU: verify the backend** from your own computer:

```bash
git fetch origin release/ddinet-v3 && git checkout origin/release/ddinet-v3 -- scripts/release/smoke_api.py
python3 scripts/release/smoke_api.py https://ddinet-api.onrender.com
```

Every line must be `PASS`, and the last line must read `N/N checks passed`.
- With openFDA reachable from Render, the warfarin + fluconazole line may report a **documented
  clinical outcome with citations** instead of the "no specific outcome" sentence. Both pass.
- If anything fails, **stop** and send me the output.

**Step 3 — YOU: set the frontend variable.** In Vercel, open project `ddi-net` → **Settings →
Environment Variables**:
1. Set `VITE_ANALYZE_API` = `https://ddinet-api.onrender.com`. Use no trailing slash and scope it
   to the **Production** environment.
2. Leave the Preview variable (test backend) as it is.
3. Before changing anything, note the current Production value. It is the env rollback value.

**Step 4 — ME, after you tell me steps 1–3 passed:** merge PR #1
(`release/ddinet-v3` → production branch). Vercel then builds Production from `67731a4`.
- **Alternative:** merge it yourself in GitHub with **Create a merge commit**. Do not squash;
  either way the history stays clean.
- Then confirm in Vercel → Deployments that the new Production deployment is **Ready** and shows
  commit `67731a4` or the merge commit.

**Step 5 — YOU, or me if the network policy is opened: production smoke test** (§3).

## 3. Production smoke test (on https://ddi-net.vercel.app)

Open DevTools → Console before starting.

| # | Check | Expected |
|---|---|---|
| 1 | Homepage loads | "DDI-Net 3.0" header; navigation shows Overview, Analyzer, Mechanisms, Multi-drug, … |
| 2 | Drug search | Analyzer: type `warf` and pick **warfarin (DB00682)**. Typing `acetaminophen` resolves to paracetamol. |
| 3 | Warfarin + fluconazole | Status card A, plus "What could happen?". Either a cited outcome, or "No specific clinical outcome established from available evidence. This does not mean the combination is safe." |
| 4 | Warfarin + aspirin | Documented "Stronger anticoagulant (blood-thinning) effect", marked as a **change in effect**, not as harm. The limitation reads "A change in effect is described, not that harm occurs." |
| 5 | Simvastatin + clarithromycin | Increased exposure. The chain steps say the affected drug is not established, or is inferred from protein roles. |
| 6 | BIO-GINE | Block E shows a calibrated score (≈0.81 for W+F) and the text "not a probability of harm". The score does not change blocks A–D. |
| 7 | Citations | Each documented outcome has a quoted source (label sentence or DrugBank template) and a reference tag |
| 8 | Mechanisms qualified | Chain steps marked "verified biological annotation" or "plausible but unconfirmed"; none says the full route is documented |
| 9 | No safety claims | No sentence states that a combination is safe |
| 10 | No CRESCENDDI | The word "CRESCENDDI" appears nowhere on the page, in the PDFs or in the JSON |
| 11 | Simple mode | Default view, blocks A–F |
| 12 | Research mode | Click **Research mode**; the outcome table, explanation and identifiers appear |
| 13 | Multi-drug | Add warfarin, fluconazole, simvastatin, clarithromycin, acetylsalicylic acid, metformin → **Check pairs · 15**; network and matrix appear |
| 14 | English | Switch **EN**; all text in English |
| 15 | Russian | Switch **RU**; all text in Russian |
| 16 | Quick PDF | Analyzer → **Quick PDF** downloads; opens; 1–2 pages |
| 17 | Full PDF | **Export PDF** downloads; opens; several pages with sources |
| 18 | JSON | **JSON** downloads; contains `payload.report.outcomes` |
| 19 | Mobile | Phone, or DevTools 390 px wide: no horizontal scrolling; menu works |
| 20 | Console / network | No red console errors. Calls go to `https://ddinet-api.onrender.com/api/v3/...` with status 200, not `localhost` and not `ddinet-api-test`. |

If the site shows "the outcome view needs the updated service" or "evidence service unavailable",
the frontend is talking to an old or unreachable API. Recheck steps 1–3, then **Redeploy**
production in Vercel with the build cache off.

## 4. Rollback

1. **Frontend:** Vercel → Deployments → `ddi-gazi4tk0v-yerzats-projects.vercel.app` (commit
   `aa04493`) → **Promote to Production** / Instant Rollback. It takes effect at once, with no
   rebuild. If needed, restore the Production `VITE_ANALYZE_API` to the value noted in step 3.
2. **Backend:** Render → `ddinet-api` → Events → the deploy noted in step 1 → **Rollback**. The new
   backend still serves the v2 `/api/analyze`, so the old site keeps working even without a
   backend rollback.
3. **Git:** if wanted, revert the merge with a new commit (`git revert -m 1 <merge>`). Never
   force-push.
4. **Keep the evidence:** Vercel build log, Render deploy log, and a screenshot of the console
   errors.

## 5. Free-plan note

The test backend (`ddinet-api-test`) is on a plan that may sleep. Production uses `ddinet-api`
(Starter, always on, per `render.yaml`). If you fall back to the test backend for the
presentation, open the site about 5 minutes before you start.

## 6. Repository-level item for your decision (not a website issue)

The repository is public. The CRESCENDDI-derived index is reachable in the history of
`feature/ddinet-v3`:
- added in `8a1e689`;
- removed in `9a9bd50`.

Removing it needs a history rewrite and a force-push of that branch, then a GitHub support request
to purge cached objects. This was not done (no force-push, no history rewrite).

The release branch and PR #1 do not contain it.
