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

# Step 2 — Graph Construction and Feature Engineering

## What this step produces

| Object | Shape / size | Purpose |
|---|---|---|
| Morgan/ECFP fingerprints | 104 × 2048 | Interpretable structural features **with bit→atom provenance** |
| Physicochemical descriptors | 104 × 12 | Pharmacokinetically meaningful properties |
| Molecular graphs | 104 graphs, 2,410 atoms | Raw input for the learned GNN encoder |
| DDI interaction graph | 104 nodes, 2,904 edges, 7 relation types | Relational context for message passing |
| Leakage audit | `reports/leakage_audit.csv` | Quantifies rule-only predictability |

## 2.1 Morgan / ECFP fingerprints — and why interpretability drove the choice

### What the algorithm actually does

1. Each atom gets an integer ID from its own properties (element, degree, charge, H count, ring membership).
2. Repeat `radius` times: replace each atom's ID with a hash of its ID plus its neighbours' IDs. After iteration *r*, an atom's ID encodes the whole substructure within *r* bonds — its **circular environment**.
3. Hash every ID generated at every iteration into a fixed-width bit vector.

ECFP4 = `radius=2`. (The 4 is the *diameter*; the radius is 2. The naming trips everyone up once.)

### Why we use them alongside a learned encoder

A learned GNN embedding generally beats fingerprints on raw accuracy. We use fingerprints anyway for one decisive reason:

> **Every bit is traceable back to specific atoms.**

RDKit's `AdditionalOutput.GetBitInfoMap()` returns, for each set bit, the `(central_atom, radius)` pairs that produced it. That lets us walk backwards from *"the model used bit 1057"* to *"these atoms in this molecule"* and draw it on the structure (Step 5). A 512-dimensional learned embedding cannot do that. **Interpretability is in the project title, so a representation with built-in provenance is worth real accuracy.**

### The collision caveat — measured, not hand-waved

There are vastly more possible substructures than bits, so distinct substructures collide onto the same bit. A bit is therefore *evidence about* a substructure, not proof of one.

**We measured this properly.** A naive implementation counts any bit with multiple `(atom, radius)` entries as "collided" — but three methyl groups setting one bit is the *same* substructure occurring three times, not a collision. Canonicalising each environment to a fragment SMILES and counting only bits carrying **chemically distinct** fragments gives:

| Statistic | Naive (wrong) | Correct |
|---|---|---|
| Warfarin | 24.3% | **8.1%** |
| Mean across 104 drugs | ~24% | **2.4%** |

The naive number would have gone into the write-up as a fake limitation an order of magnitude too large. This is why `collision_rate()` requires the molecule as an argument.

### Chemistry sanity checks (these should be in your logbook)

| Pair | Tanimoto | Expected |
|---|---|---|
| simvastatin / lovastatin | 0.742 | high — differ by one methyl ✓ |
| amitriptyline / nortriptyline | high | differ by one N-methyl ✓ |
| simvastatin / metformin | 0.042 | unrelated ✓ |

## 2.2 The 12 descriptors — and why not 200

RDKit exposes ~200 descriptors. We use 12, each individually defensible:

| Descriptor | Pharmacological meaning |
|---|---|
| MolWt, TPSA, MolLogP, HBD, HBA | Lipinski/Veber absorption and distribution |
| NumRotatableBonds | Conformational flexibility, oral availability |
| NumAromaticRings, RingCount | Scaffold rigidity; **aromatics dominate CYP450 binding** |
| FractionCSP3 | Saturation; correlates with metabolic stability |
| HeavyAtomCount, MolMR, NumHeteroatoms | Size and polarisability |

With ~100 drugs, dumping 200 heavily-correlated descriptors is a direct route to overfitting. Twelve interpretable ones is the statistically correct call *and* the explainable one.

## 2.3 Molecular graphs — 50 atom features, 11 bond features

Atom features are one-hot with an explicit **"other" bucket**. Without it, an unseen element at inference time produces an all-zero block, indistinguishable from a legitimate zero. With it, "unusual atom" is an explicit learnable signal — which matters in S3, where test drugs are unseen by definition.

**Bonds are stored in both directions.** PyG message passing is directional; a single `(i,j)` entry sends messages one way only. Omitting the reverse is a near-silent bug — the model still trains, just on half a molecule. The test suite asserts `edge_index.shape[1] == 2 × num_bonds`.

**No 3-D coordinates, deliberately.** Drugs are flexible; a single conformer is arbitrary, and conformer ensembles are expensive and add variance. 2-D topology also keeps the graph branch comparable to the fingerprint branch.

## 2.4 Why a graph beats a table — the honest four-part argument

**1. The label is a property of a pair, not a drug.** Tabular forces you to flatten the pair into one row, making an arbitrary choice (concatenate? subtract?) and discarding relational structure.

**2. Higher-order structure carries real pharmacology.** ← *the strongest argument*
If ketoconazole inhibits CYP3A4, and simvastatin, midazolam and colchicine are CYP3A4 substrates, then knowing *ketoconazole–simvastatin* interacts is evidence about *ketoconazole–midazolam*. Message passing propagates exactly this. Independent table rows cannot represent it at all. **This is mechanistically grounded, not hand-waving.**

**3. Sparsity.** Documented interactions cover a few percent of possible pairs. "Represent a node by its neighbourhood" is well matched to sparse relational data; a flat model must learn the relational structure from scratch.

**4. Symmetry comes free.** Interaction is symmetric. Undirected edges + a symmetric decoder enforce *f(A,B) = f(B,A)* architecturally, rather than hoping the model learns it.

### State the counter-argument too

For **S1** warm-start prediction, a well-tuned gradient-boosted model on concatenated fingerprints is genuinely strong and sometimes wins. The graph's advantage should appear in **S2/S3**. Step 4 *tests* this rather than assuming it. Volunteering the counter-argument is far more persuasive than pretending it doesn't exist.

## 2.5 ⚠ The single most dangerous bug in link prediction

**When you predict edges in a graph, the graph itself is an input feature.**

Build the message-passing graph from *all* known interactions, then evaluate on a held-out subset of those same interactions, and the model reads the answer off its own input. A 2-layer GNN doesn't need to be clever — the test edge is literally in the adjacency it aggregates over. This produces near-perfect metrics and is completely invalid.

It's easy to write by accident, because *"build the graph, then split the edges"* is the natural order to think in.

**DDI-Net enforces the correct order:**

```
1. Split DRUGS                                    (Step 1)
2. Route pairs into buckets by drug membership    (Step 1)
3. Build message-passing graph from TRAINING-bucket edges ONLY
4. Predict val/test edges against that graph
```

- `build_ddi_graph(drugs, train_pairs, ...)` — the argument is *named* `train_pairs` so a reader of the call site can see whether it's correct.
- `assert_no_evaluation_edges(graph, eval_pairs)` — verifies the invariant, costs milliseconds, runs before every training run.
- A test **deliberately builds a leaky graph** and asserts the guard fires.

**Consequence worth understanding:** under a drug-level split, a test drug appears in *no* training pair, so it has **zero `known_ddi` edges**. Its representation must come from chemistry and pathway edges. That is exactly the intended difficulty of S2/S3 — and it's why a model leaning entirely on graph topology collapses there.

## 2.6 The seven relation types

| Relation | Edges (curated) | Meaning |
|---|---|---|
| `known_ddi` | 229 | Observed interaction — **train only** |
| `cyp_inhibitor_substrate` | 737 | A inhibits an enzyme B is metabolised by ← *most common PK mechanism* |
| `cyp_inducer_substrate` | 267 | A induces an enzyme B is metabolised by |
| `cyp_shared_substrate` | 1,249 | Competition for the same enzyme |
| `transporter_inhibitor_substrate` | 95 | e.g. P-gp inhibition → digoxin toxicity |
| `transporter_shared_substrate` | 78 | Transporter competition |
| `same_atc_class` | 249 | Same ATC level-3 pharmacological subgroup |

Roles are kept **separate**, not collapsed into "involved with CYP3A4". The entire mechanism is that an *inhibitor* raises a *substrate*'s exposure; two substrates merely competing is a much weaker effect.

Inhibitor→substrate is mechanistically *directional*, but stored undirected: the clinical consequence is a property of the combination, and the prediction target is symmetric by definition. Direction is recorded in the explanation layer (Step 5), where it matters for the narrative.

## 2.7 The leakage audit — turning a hidden trap into a result

Pathway edges derive from drug *annotations*, not labels, so in general they're legitimate features. **But the curated fixture's labels were curated from these same mechanisms**, so there the relationship is circular.

Rather than hide this, we measured it. Treating "this pathway edge exists" as a one-bit classifier:

**test_S2 bucket, curated fixture:**

| Rule | Precision | Recall | Balanced accuracy |
|---|---|---|---|
| `cyp_inhibitor_substrate` | 0.714 | 0.339 | 0.602 |
| `cyp_inducer_substrate` | 0.944 | 0.144 | 0.568 |
| `cyp_shared_substrate` | 0.659 | 0.458 | 0.610 |
| `transporter_inhibitor_substrate` | 1.000 | 0.076 | 0.538 |
| `same_atc_class` | 0.923 | 0.203 | 0.593 |
| **ANY pathway edge** | **0.709** | **0.763** | **0.725** |

### How to read this

The circularity is **real but not total**. A rules-only model gets 0.725 balanced accuracy — well above chance, well below solved. Individual rules are *high precision, low recall*: when `cyp_inducer_substrate` fires it's right 94% of the time, but it only catches 14% of interactions.

**This gives you a hard, quantified bar: the GNN must clearly exceed 0.725 balanced accuracy on test_S2 to have earned its complexity.** Reporting the model's score next to this baseline is far more convincing than reporting the model's score alone.

Run on DrugBank, this number should be substantially lower, and whatever remains is genuine mechanistic signal. **Report both side by side.**

## 2.8 Guards that make the defaults safe

- `include_cyp_features` defaults to **False** — circular on the fixture. Enabling requires an explicit flag, so it's a visible act, not a silent default.
- Descriptor standardisation uses **training-drug statistics only**. Fitting a scaler on all drugs carries test-molecule information into training. Small effect, free to avoid, impossible to defend if spotted. Test-asserted.

## 2.9 Limitations to state

1. **Fingerprint collisions** cap attribution specificity (measured: 2.4% mean).
2. **2-D only** — no conformational or 3-D pharmacophore information.
3. **Pathway edges depend on annotation completeness.** DrugBank's CYP coverage is incomplete; a missing annotation is indistinguishable from a real absence. This is why `same_atc_class` is included as a coarse fallback.
4. **`same_atc_class` is a weak proxy.** Same class ⇏ interaction; it mostly encodes "similar drugs".
5. **A test drug has no `known_ddi` edges at all.** By design — but it means graph-topology features are unavailable exactly where they'd help most.
6. **Circularity on the fixture is quantified but not eliminated** — which is why headline numbers must come from DrugBank.

## 2.10 What you need to understand to answer ISEF judges

**"Why a graph and not just a table of features?"**
Four reasons — the strongest is higher-order mechanism: if ketoconazole inhibits CYP3A4 and three drugs are CYP3A4 substrates, knowing one pair interacts is evidence about the others. Message passing propagates that; independent rows can't represent it. Also: the label is a pair property, the data is sparse, and undirected edges give interaction symmetry for free. *And* — for warm-start S1, a tuned GBM on fingerprints is genuinely competitive; the graph should win in S2/S3, and Step 4 tests that rather than assuming it.

**"How do you know your graph isn't leaking test labels?"**
Because in link prediction the graph *is* an input feature. We build the message-passing graph from training-bucket edges only, and `assert_no_evaluation_edges` verifies it before every run. There's a test that deliberately builds a leaky graph to prove the guard fires. Under a drug-level split, test drugs have zero `known_ddi` edges by construction.

**"Why Morgan fingerprints when learned embeddings work better?"**
Because each bit traces back to specific atoms via RDKit's bit-info map, so I can show *which substructure* drove a prediction. That's the project's whole point. I use both: fingerprints for the interpretable branch, a learned GNN encoder for capacity, and Step 4 ablates them separately.

**"Aren't your CYP pathway edges just encoding the answer?"**
Partly, on the curated fixture — and I measured exactly how much. A rules-only classifier gets 0.725 balanced accuracy on test_S2. That's the bar my model must beat. CYP *node features* are off by default for that reason, and the same audit run on DrugBank separates genuine mechanistic signal from circularity.

**"What does ECFP4 mean?"**
Extended-connectivity fingerprint, diameter 4 — so radius 2. Each atom's identifier iteratively absorbs its neighbours' identifiers, so after 2 rounds it encodes everything within 2 bonds. Those identifiers are hashed into a 2048-bit vector.

## 2.11 Reproducing this step

```bash
python scripts/03_build_features.py                          # default: safe config
python scripts/03_build_features.py --group-by scaffold      # harder split
python scripts/03_build_features.py --include-cyp-features   # deliberately circular
python -m pytest tests/test_features.py -q                   # 24 tests
```
