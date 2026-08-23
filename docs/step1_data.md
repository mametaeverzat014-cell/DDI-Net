> # ⛔ ВСЕ ЧИСЛА В ЭТОМ ФАЙЛЕ АННУЛИРОВАНЫ / ALL NUMBERS IN THIS FILE ARE VOID
>
> Каждая метрика ниже посчитана на `data/curated/` — наборе, сгенерированном
> LLM по памяти, без цитируемого источника. Он перенесён в
> `tests/fixtures/synthetic_ddi/` и понижен до тестовой фикстуры.
> **Ни одно число ниже не является научным результатом.**
>
> Every metric below was computed on an LLM-generated fixture with no citable
> source. It has been moved to `tests/fixtures/synthetic_ddi/` and demoted to a
> unit-test fixture. **No number below is a scientific result.**
>
> Файл сохранён целиком, ничего не удалено — чтобы был виден исходный ход
> рассуждений. Методологические аргументы (почему сплит по препаратам, почему
> AUPRC, почему симметрия) остаются в силе; иллюстрирующие их числа — нет.
>
> Реальные результаты появятся только после загрузки данных через PyTDC.
> См. `DATA_PROVENANCE.md` и `LIMITATIONS.md`.
>
> Аннулировано: 2026-08-23.

# Step 1 — Data Collection and Preparation

## What this step produces

| File | Contents |
|---|---|
| `data/curated/drugs.csv` | 104 drugs: SMILES, formula, ATC code, CYP450 roles, transporter roles, pharmacodynamic classes |
| `data/curated/ddi_pairs.csv` | 467 documented interactions: severity, mechanism, mediator, clinical effect |
| `data/processed/drugs.csv` | Drug table with RDKit-derived InChIKey, canonical SMILES, MW |
| `data/processed/dataset.csv` | Labelled examples with `bucket` and `setting` (S1/S2/S3) |
| `data/processed/split.json` | Exactly which drugs went to train/val/test — reproducibility record |

## 1.1 Why these data sources

| Source | What it uniquely provides | Licence |
|---|---|---|
| **DrugBank Open Data** (vocabulary) | Identifier crosswalk: DrugBank ID ↔ name ↔ InChIKey | CC0 |
| **DrugBank full release** (XML) | Interaction pairs + free-text mechanisms + CYP450 enzyme annotations | Academic licence, manual |
| **PubChem** (PUG-REST) | SMILES resolved exactly by InChIKey | Public domain |
| **SIDER 4.1** | Side-effect profiles — a *phenotypic* view orthogonal to structure | CC BY-NC-SA |
| **DDInter 2.0** | **Clinical severity** (Major/Moderate/Minor) — this is what makes "dangerous" measurable | Free academic |
| **BioSNAP ChCh-Miner** | A public benchmark graph other papers report on — enables comparison | Research use |
| **TWOSIDES** | FAERS-mined pairs with adverse-event terms and reporting ratios | CC BY 4.0 |
| **openFDA FAERS** | Independent real-world validation signal (Step 4) | Public domain |

**The key architectural decision: DrugBank supplies the *mechanism*, DDInter supplies the *severity*.**
The project title claims to predict *dangerous* interactions. That word needs an operational
definition or the framing collapses. DrugBank tells you two drugs interact; it does not grade how
much you should care. DDInter grades each pair clinically. So **"dangerous" ≡ DDInter "Major"** —
a defensible definition we did not invent.

## 1.2 Why identifiers are joined by InChIKey, not by name

Drug-name matching is the most common silent-corruption bug in cheminformatics. "Aspirin",
"acetylsalicylic acid", "ASA", and "aspirin sodium" overlap but are not the same thing, and a name
lookup returns the wrong compound with a `200 OK` and no warning.

The InChIKey is computed *from the structure*, so it is exact. In the curated set the InChIKey is
computed by RDKit from our own SMILES — meaning it is verifiable with no external database at all.
DrugBank accession numbers are stored for convenience but are **not** the join key.

Salts are stripped to the largest organic fragment (`pubchem.strip_salts`). A fingerprint of
"atorvastatin calcium" is not a fingerprint of atorvastatin.

## 1.3 Why the curated seed set exists — and how to talk about it

The container this was built in blocks every biomedical host at the network layer (verified:
DrugBank, PubChem, SIDER, DDInter, BioSNAP and openFDA all return HTTP 403 from the egress proxy).
So the repository ships a **hand-curated, mechanism-annotated fixture** of 104 drugs and 467
interactions built from standard clinical pharmacology.

It exists for three reasons:
1. Anyone cloning the repo can run the whole pipeline in under a minute — no licence wait.
2. Tests need deterministic data that does not depend on a remote server.
3. Every SMILES is validated against an **independently stated molecular formula**, so structural
   errors are impossible to miss. This check caught 4 real errors during construction
   (valproic acid, oxycodone, moxifloxacin, digoxin).

### ⚠ The circularity warning — the most important paragraph in this document

Because the pairs were curated *with the mechanism in mind*, the labels are strongly determined by
the CYP450 annotation columns. **A model given those annotations and evaluated on this fixture is
re-deriving the rule that generated the labels.** Any AUC measured that way is meaningless.

Therefore:
- Headline performance numbers must come from DrugBank / DDInter / BioSNAP.
- The default feature configuration **excludes** CYP annotations; enabling them requires a flag.
- Step 4 includes a leakage audit that quantifies how much label information CYP features carry.

**Being able to explain this trap — and showing you built the instrument that detects it — is a
stronger result than a high number would be.** If a judge asks "isn't your dev data circular?",
the correct answer is "yes, by construction, and here is the audit that measures it and the
experimental design that avoids it."

## 1.4 Drug-level splitting — the central methodological decision

### The problem with the obvious split

The obvious thing is to shuffle the *pairs* 80/10/10. A large fraction of published DDI papers do
this and report AUC 0.98–0.99. Those numbers mean almost nothing.

Warfarin appears in ~30 interactions in our seed set. Under a pair-level shuffle ~24 land in train
and ~3 in test. At test time the model does not need to understand warfarin's chemistry — it has
already learned an embedding meaning "warfarin interacts with almost everything". **The model
memorised node identity, not interaction mechanism.**

This leak is invisible in the loss curve. Train and validation loss both look excellent. It is only
exposed by changing the split.

### The three settings (Pahikkala et al. 2015)

Let `D_train` be the drugs visible during training.

| Setting | Definition | Question it answers |
|---|---|---|
| **S1** warm start | Both test drugs ∈ `D_train` | *Can I fill gaps in an existing database?* |
| **S2** one new drug | Exactly one test drug ∉ `D_train` | *A new drug is entering the market — will it interact with my formulary?* ← **the clinically important question** |
| **S3** both new | Neither test drug ∈ `D_train` | *Can I reason from structure alone?* ← the honest test |

Expect a large drop S1 → S2 → S3. **That drop is a result, not a failure.** Reporting all three and
explaining why S1 is optimistic is what separates a serious project from one that quotes 0.99.

### How leakage is prevented mechanically

We partition **drugs**, not pairs, then route every pair by the membership of its endpoints. Pairs
straddling the validation and test drug groups are **discarded** — otherwise a drug tuned on during
validation reappears at test time. On the curated set this discards 16–19 pairs (~4%); `SplitReport`
records the exact number so you can state it.

Assignment is **stratified by interaction degree** so hub drugs (warfarin, amiodarone) and
peripheral drugs are spread across splits. Without this, a random split can put every hub in train,
leaving a test set that is both easy and unrepresentative.

### Scaffold splitting — the harder, better test

Even a drug-level split can flatter you. Simvastatin and lovastatin differ by one methyl group; if
one is in train and the other in test, an "unseen" drug is effectively a seen one.
`--group-by scaffold` uses the Bemis-Murcko scaffold as the grouping unit, forcing close analogues
into the same split. This is standard in molecular property prediction and **rarely applied to
DDI** — using it is a genuine methodological contribution.

Verified: the test suite asserts `simvastatin` and `lovastatin` always land in the same split.

## 1.5 Negative sampling — the open-world problem

Every DDI database lists interactions *someone documented*. **None lists non-interactions.** So we
must assume "not in the database" ⇒ "does not interact", which is false in an unknown fraction of
cases.

Consequences to state plainly:
- Measured **precision is a lower bound**. A "false positive" may be a real but undocumented
  interaction — which for a discovery tool is the desired outcome.
- Measured **recall is roughly unbiased**, because positives are real.
- This is formally **positive-unlabelled (PU) learning**. Naming the framing shows statistical
  literacy.

**Turn the limitation into a result:** take the model's highest-confidence "false positives" and
check them against openFDA FAERS (Step 4). A disproportionate real-world adverse-event signal is
evidence the model found genuine undocumented interactions.

### The degree shortcut (a subtler trap we measured)

With uniformly sampled negatives, a model can score pairs well above chance using only "is either
drug a hub?" — never looking at chemistry, and collapsing entirely in S2/S3.

Measured on the curated training bucket:

| Negative sampling | Mean endpoint degree, positives | …negatives | Gap |
|---|---|---|---|
| `uniform` | 13.02 | 8.85 | **4.17** ← exploitable |
| `degree_matched` | 13.02 | 12.34 | **0.68** |

`degree_matched` draws negative endpoints in proportion to positive degree, so the shortcut carries
almost no information. This makes the task harder and the numbers lower — that is the point. The
gap between the two settings *measures how much of a uniform-negative model's apparent skill was
degree memorisation*.

### Class prevalence must always be quoted

`neg_ratio` sets negatives per positive and therefore fixes the AUPRC of a random classifier
(= prevalence = 1/(1+ratio)). 1:1 is convenient for training; the true prevalence of documented
interactions among arbitrary drug pairs is far lower, so **evaluating at 1:10 is more faithful**.
Never quote precision/recall without the prevalence beside it.

### One rule that protects patients

With `--dangerous-only`, moderate and minor interactions are **dropped, not relabelled as
negatives**. They *are* interactions; calling them negative would train the model toward exactly the
error that hurts people. Same reason DDInter's "Unknown" severity rows are dropped: *"we don't know"
is not "it's safe."*

## 1.6 Limitations to state in the write-up

1. **The curated fixture is small and circular by construction.** 104 drugs, 467 pairs. It is a
   development fixture, not an evaluation corpus. Headline numbers come from DrugBank/DDInter.
2. **S3 buckets are tiny on the fixture** (6–14 pairs) — far too small for a stable estimate.
   Meaningful S3 evaluation needs the full DrugBank graph. Report S3 on the fixture as a smoke
   test only, with confidence intervals.
3. **Negatives are unlabelled, not negative** (PU learning; §1.5).
4. **SIDER coverage is ~1,400 drugs and is label-derived**, so it carries circularity risk and is
   unavailable exactly in the S3 setting where it would help most. Report with/without as an
   ablation: if SIDER helps hugely in S1 but not in S3, that is a leak, not a signal.
5. **DrugBank interaction typing is regex-based** over machine-generated template text. Accurate,
   but rule-based, not learned — report the unclassified rate.
6. **Databases are living resources.** "We used DrugBank" is not reproducible; "we used the release
   hashing to `a1b2c3…`" is. Every download is SHA-256 pinned in `data/raw/manifest.json`.
7. **Salts, stereochemistry, and prodrugs.** Codeine → morphine via CYP2D6 means the administered
   structure is not the active one. A structure-only model cannot see this. Clopidogrel (a prodrug)
   is the canonical case.

## 1.7 What you need to understand to answer ISEF judges

**"Why a drug-level split instead of a random split?"**
Because a random pair-level split lets the model memorise which drugs are promiscuous instead of
learning chemistry. Warfarin appears in ~30 pairs; under a random split most land in train, so the
model scores test pairs from node identity alone. That leak is invisible in the loss curve. We
partition drugs, report S1/S2/S3 separately, and discard val/test straddling pairs.

**"Where do your negative examples come from — how do you know they're really negative?"**
We don't, and that's the honest answer. No database records non-interactions, so absence is
*unlabelled*, not negative. This is positive-unlabelled learning. Precision is a lower bound;
recall is roughly unbiased. We use degree-matched sampling so hub-drug frequency can't be exploited
as a shortcut, and we validate top "false positives" against FAERS.

**"What makes an interaction 'dangerous'?"**
DDInter's clinical severity grade: Major. Not our judgement — a curated clinical classification.
Unknown-severity pairs are dropped, never treated as safe.

**"Isn't your curated dataset circular?"**
Yes, by construction, and we say so. It's a development fixture that makes the pipeline runnable
and testable offline. Headline numbers come from DrugBank/DDInter where labels were curated
independently of CYP annotations. We built a leakage audit to quantify it.

**"How do you know your molecular structures are right?"**
Every SMILES is validated against an independently stated molecular formula by RDKit, plus an
InChIKey uniqueness check. The test suite enforces it. This caught 4 real errors during
construction.

**"Why is your S3 performance so much worse than S1?"**
Because S3 is a genuinely harder and more honest question: predict interactions for two drugs the
model has never seen, from structure alone. S1 permits node memorisation. The gap quantifies how
much of an S1 number is memorisation rather than chemistry.

## 1.8 Reproducing this step

```bash
pip install -r requirements.txt

python scripts/00_data_report.py                 # provenance + licences + validation
python scripts/01_download_data.py               # fetch what the network allows
python scripts/02_build_dataset.py --source curated --group-by scaffold --neg-ratio 3
python -m pytest tests/ -q                       # 53 integrity tests
```

Once a DrugBank academic licence is approved, place `full database.xml` at
`data/raw/drugbank_full/drugbank_full_database.xml` and re-run with `--source drugbank`.
Nothing else changes — the split, sampling, and leakage checks are source-agnostic.
