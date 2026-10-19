# DDI-Net 3.0 — Presentation demo (October 20)

**What it is.** DDI-Net 3.0 is a **research and educational prototype**. It is not a medical device
and not clinically validated, so do not present it as clinical decision support.

**Backup files** are in `docs/presentation/backup/`:
- screenshots `01`–`08`;
- PDFs and a JSON export.

These were made on 2026-10-18/19 from **the same code**, run locally in the build container with
FDA labels unreachable. They are **not** screenshots of the production site. Retake them from
production after the release smoke test, if time allows.

## Before you start (about 10 minutes before)

1. Open https://ddi-net.vercel.app, then the Analyzer with warfarin + fluconazole. This wakes the
   backend; the first request can take up to a minute if it slept.
2. Keep the backup folder open in a second window.
3. Language: switch with **RU / EN**, top right.

## Three demonstration pairs

| # | Pair | What it shows | Expected result (FDA labels unavailable) | If FDA labels answer (production) |
|---|---|---|---|---|
| 1 | **Warfarin + fluconazole** (DB00682 + DB00196) | A well-known PK interaction. The system separates "exposure changes" from "harm" | Status "interaction-specific evidence found, clinical outcome unclear". **Higher serum concentration of warfarin**, with the affected drug inferred from protein roles (CYP2C9 / CYP2C19 / CYP3A4). Exact sentence: "No specific clinical outcome established from available evidence. This does not mean the combination is safe." | A label sentence may add **bleeding** as a documented outcome, quoted, with the extraction caveat |
| 2 | **Warfarin + aspirin** (DB00682 + DB00945) | A PD interaction | "Stronger anticoagulant (blood-thinning) effect", marked as a **change in effect, not harm**. The no-specific-outcome sentence is shown | Label sentences may add bleeding, quoted |
| 3 | **Simvastatin + clarithromycin** (DB00641 + DB01211) | Honest uncertainty | Increased exposure is documented, but **which** drug is not established: both drugs are CYP3A4 substrates. Chain steps are "plausible but unconfirmed" | Labels may add myopathy / rhabdomyolysis, quoted |

Optional: **multi-drug.** Use warfarin, fluconazole, simvastatin, clarithromycin, acetylsalicylic
acid and metformin, which gives 15 pairs.
- In the matrix, "Bleeding and blood clotting" is a **category**. For warfarin + aspirin and
  warfarin + simvastatin it holds a DrugBank **effect** record (stronger anticoagulant effect), not
  documented bleeding.
- Say so if asked.

## Click-by-click

1. **Home.** One sentence: "DDI-Net separates three kinds of statement: what sources document,
   what drug biology could explain, and what a research model predicts."
2. **Analyzer.**
   1. Enter `warfarin` and `fluconazole`, then **Analyze**.
   2. Walk the blocks in order:
      - **A:** is there a documented interaction?
      - **B:** what could happen, with the quoted source;
      - **C:** why: the mechanism chain, where each step is labelled *verified annotation* or
        *plausible, unconfirmed*;
      - **D:** how certain;
      - **E:** what BIO-GINE adds: a research score, *not* a probability of harm;
      - **F:** the limitation.
   3. Point at the exact "No specific clinical outcome…" sentence.
3. Click **Research mode**. Show the outcome table, identifiers and provenance. Click a chain step
   to reveal its basis.
4. **Quick PDF**, and open it. Then **Export PDF** (full report), and scroll to the sources section.
5. Switch **RU**. The same report is shown in Russian.
6. Change the second drug to `aspirin`. Show "change in effect, not harm".
7. Change to simvastatin + clarithromycin. Show that the system **abstains** from naming the
   affected drug when the biology is ambiguous.
8. *(Optional)* **Multi-drug** with the six drugs → **Check pairs · 15**. Show the network and the
   matrix. "Pairwise only; nothing is claimed about three or more drugs together."

**If the live site fails:** switch to the backup screenshots and PDFs, and say they are from the
same code run locally.

## Short scientific explanation (about 60 seconds)

**Problem.** Interaction databases mostly say *that* two drugs interact, often as
pharmacokinetic or pharmacodynamic template sentences. They rarely say *what clinically happens*,
or how sure we are.

**DDI-Net 3.0 keeps evidence types apart:**
- **A.** Documented clinical outcomes, quoted from a source.
- **B.** PK/PD changes, which are not harm by themselves.
- **C.** Mechanisms verified from curated drug–protein annotations.
- **D.** Hypotheses, in Research mode only.
- **E.** The BIO-GINE graph neural network's research score, which never turns into a risk.
- **F.** Insufficient evidence, which is never called "safe".

**The rules:**
- No step of a mechanism chain is called documented unless a source states it.
- A shared pathway is never treated as a cause.
- The DrugBank record's drug order is used only where it was verified.

## Two kinds of numbers — keep them apart

| | What it measures | Number | Type of evidence |
|---|---|---|---|
| **BIO-GINE (research model, frozen M4)** | Ranking documented DrugBank interaction pairs against sampled negatives on a drug-disjoint test split | AUPRC **0.812 ± 0.010** pooled (5 seeds); 0.737 ± 0.015 on S3 (both drugs unseen) | Historical benchmark (DrugBank via TDC). **Not** clinical accuracy and **not** a probability of harm |
| **Clinical outcome extraction (`label_lexicon/v4`)** | Whether rules extract the right outcome from FDA label sentences | Held-out, 100 (label, partner) units from historical FDA labels (TAC 2017): precision **40/45** (0.89, 95% CI 0.77–0.95); recall 40/43; unsupported claims 3/42 units; citations 68/68 | **Internally annotated** by the project (one annotator, who also wrote the rules). Not independent, not clinical |
| DDI Corpus 2013 (independent annotation) | The same rules on DrugBank interaction text | Precision 50/61; outcome found for 50/233 interacting pairs | Historical dataset; low coverage |

## Say / do not say

- **Say:**
  - "research prototype";
  - "documented in a source";
  - "plausible but unconfirmed";
  - "research model score";
  - "absence of evidence is not evidence of safety".
- **Do not say:**
  - "clinically validated";
  - "predicts the risk / probability of harm";
  - "safe combination";
  - "replaces a pharmacist";
  - "uses CRESCENDDI". It was withdrawn for licensing reasons and is not served.

## Limitations to state if asked

- Label text comes live from openFDA when reachable. The benchmark labels are historical
  (2016–2017).
- The extraction rules miss about 3 in 10 label-stated interactions. A missing outcome says
  nothing about safety.
- There has been no independent clinical review.
- Only 1,705 drugs, and pairs only.
- BIO-GINE's score reflects resemblance to documented pairs, not mechanism or severity.
