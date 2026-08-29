# V2 implementation notes: every deviation from the plan text

**Status:** written during implementation, **before any V2 training run**
**Covers:** `src/ddinet/data/biology.py`, `src/ddinet/models/bio_gine.py`,
`src/ddinet/models/bio_baselines.py`
**Companions:** `docs/V2_ARCHITECTURE_PLAN.md`, `docs/V2_PREREGISTRATION.md`,
`docs/V2_CONTROL_F_PATHWAY_ASYMMETRY.md`

The preregistration is locked. Where the implementation departs from the plan's
literal text, the departure is recorded here with its reason, before any number
exists that it could have been chosen to flatter. Nothing here changes a
hypothesis, a threshold, a split, or a negative-sampling scheme.

---

## 1. Molecular encoder: 3 layers at d=64, not 4 layers at d=128

**Plan text (section 4.2):** "GINE (4-layer, d=128, same as Phase A-2)".

**Problem:** the parenthetical contradicts the phrase. `scripts/15_phase_a2_gnn.py`
line 98 froze `hidden_dim=64, mol_layers=3`, and the tuned dropout for the `gine`
cell was 0.1 (`reports/phase_a2_hyperparameters.json`).

**Resolution:** follow the intent. M0 in the evidence ladder **is** the frozen
Phase A-2 GINE result, reused rather than retrained (preregistration section 11).
If V2's molecular branch differed from it, every M-minus-M0 difference would
confound "added biology" with "changed the chemistry encoder", and the primary
hypothesis H-V2-1 would be uninterpretable.

**Implemented:** `mol_dim=64, mol_layers=3, dropout_mol=0.1, pooling=sum,
pool_norm=True`.

## 2. Modality mask is combined commutatively, not concatenated

**Plan text (section 4.5):** `pair_feat = concat(..., mask_A, mask_B)`.

**Problem:** that breaks `f(A,B) = f(B,A)` for exactly the pairs where one drug
has biology and the other does not — 3.9% of drugs have no protein annotation
and 5.3% no pathway, and those are the pairs the missing-data analysis is about.
Symmetry-by-construction is a Phase A commitment, not a nicety
(`src/ddinet/models/ddinet.py`, "THE SYMMETRY CONSTRAINT").

**Implemented:** `min(mask_A, mask_B)` and `max(mask_A, mask_B)` — "both drugs
have this modality" and "at least one does". Same width (4 columns), same
information for an unordered pair, commutative. Pair decoder input is
`3h + 4 = 388` at `h=128`, matching the plan's stated width.

Pinned by `tests/test_bio_gine.py::test_symmetry_holds_when_only_one_drug_has_biology`.

## 3. Protein vocabulary is 2,893, not 2,778

**Plan text (section 4.3):** "vocabulary: 2,778 UniProt IDs".

**Cause:** 2,778 is the row count of `proteins.parquet`.
`drug_protein_edges.parquet` references 2,893 distinct accessions — 115 proteins
appear in edges without a row in the node table.

**Implemented:** the vocabulary is the **union** of the edge table and the node
table. Dropping the 115 would silently discard their edges; adding a placeholder
row would invent a protein. The union keeps every edge and adds no biology.

Pathway vocabulary is 1,969 as planned.

## 4. The set element is a triple, and assay duplicates are collapsed

`drug_protein_edges.parquet` has 146,743 rows but 94,088 distinct
`(drug, protein, relation, evidence)` triples. The difference is ChEMBL assay
rows, one per measurement.

**Implemented:** P(d) is the set of distinct triples. Keeping row multiplicity
would weight a protein by how often it was assayed — literature attention, which
is the confound this phase exists to control.

This also keeps the CONTROL F contrast exact: row degree, distinct-pair degree
and distinct-triple degree are all *identical* between the true and shuffled
edge tables (verified), so both arms see element-for-element matching set sizes.

## 5. Scalar counts are derived, not read from `drugs.parquet`

The frozen `n_targets` / `n_proteins` / `n_pathways` columns are **DrugBank-only**
counts. Under a DrugBank-only derivation `n_pathways` reproduces exactly
(1.000 of drugs); under the full evidence set it matches 0.229.

**Implemented:** all eight CONTROL A counts are derived from the same filtered
edges the model sees. Two reasons: an evidence ablation changes which sources
are active, and CONTROL F changes the pathway sets. Reading the frozen column
would feed CONTROL A a count describing biology the model was not shown.

`count_discrepancy_report()` records the gap; the DrugBank-only equivalence is
pinned by `tests/test_biology_bundle.py::test_frozen_drugs_parquet_counts_are_drugbank_only`.

`n_adverse_events` matches the frozen column exactly (1.000) and is unaffected.

## 6. CONTROL A applies `log1p` to counts before forming pair terms

**Plan text (section 7, CONTROL A):** "Pair features: difference, product, sum"
— scale unspecified.

**Problem:** a random forest is invariant to a monotone transform of a single
feature but not to one applied *before a product*: `a*b` and
`log1p(a)*log1p(b)` order pairs differently. Counts span 0 to >1,000 with a
heavy right tail.

**Implemented:** `log1p` by default, matching what Phase A-2's degree-only
baseline does with DDI degree, so the two null models are on the same footing.
`log_counts=False` restores the literal reading and is one argument away.

## 7. BIO-RF's ECFP4 block is off by default

**Plan text (section 6):** pair features over "~3 x (7 + 128 + 64 + ECFP4_dim)".

**Not a memory objection.** Measured for 380k training pairs: 1.70 GiB without
the fingerprint block, 2.01 GiB with it.

**The objection is dilution.** With `max_features='sqrt'` the forest samples ~69
of 4,696 columns per split, ~87% of them fingerprint columns. The rate at which
the biological features — the entire point of the model — get examined would be
set by how many fingerprint bits happen to sit beside them. A biological
baseline whose sensitivity to biology depends on the fingerprint width does not
answer H-V2-4.

**Implemented:** `use_fingerprints=True` builds the literal version for the
appendix; the default is the one the hypothesis is read from. When on, the
fingerprint half is bit-identical to Phase A-2's `RandomForestECFP` encoding, so
BIO-RF strictly contains that baseline.

## 8. `n_chembl_proteins` is derived; `n_adverse_events` is kept

Preregistration section 8 lists eight CONTROL A features including
`n_chembl_proteins`; plan section 6 says `n_adverse_events` "replaces
n_chembl_proteins for simplicity". Both are cheap to derive, so both are kept —
the feature set is the union, eight columns, and no choice between the two
documents was needed.

## 9. Parameter budget: measured, and `bio_dim=128` breaks the plan's own cap

Measured with the real vocabularies (2,893 proteins, 1,969 pathways), M4, full
model including the molecular branch:

| `bio_dim` | Total parameters |
|---:|---:|
| 32 | 378,228 |
| **64 (default)** | **593,652** |
| 128 | 1,122,804 |

Component breakdown at `bio_dim=64`: molecular encoder 54,275; protein
embedding 185,152; protein DeepSets 37,312; pathway embedding 126,016; pathway
DeepSets 33,216; fusion 24,704 + 256; pair decoder 132,609; relation and
evidence embeddings 112.

The plan's estimate of ~853,000 assumed a d=128 4-layer molecular encoder
(~300,000); at the actual Phase A-2 configuration that component is 54,275.

**Conflict to note before the grid runs:** section 13 sets a complexity
guideline of "< 1M total parameters", and the preregistered grid (section 10.2)
includes `bio_dim=128`, which is 1.12M. The grid is preregistered and the cap is
a guideline, so the grid runs as written and the `bio_dim=128` cells are
reported with their parameter count beside them. Dropping a preregistered cell
after seeing that it is large would be a post-hoc narrowing of the search.

## 10. CONTROL F does not preserve pathway degree

Separate document, because it changes what a result can be claimed to show:
**`docs/V2_CONTROL_F_PATHWAY_ASYMMETRY.md`**.

Summary: |P(d)| is exactly preserved, |Q(d)| is not — shuffled median 87 against
true 52, larger for 68.0% of drugs — because pathways are derived and real
target sets are pathway-coherent. H-V2-3 is therefore read from the M3 contrast
(protein degree exact, identity the only difference) as well as the
preregistered M4 contrast, and both are reported.

## 11. Dropout is in `rho` only, not in `phi`

Not a deviation from the plan, which places dropout in `rho`, but the reason is
worth recording: dropping features of individual set elements before a MEAN
makes the variance of the aggregate scale with `1/|P(d)|`. That is set size
re-entering as noise — degree through a side door — in a model whose entire
design is about not doing that.

## 12. What was NOT changed

- Splits, seeds, negative sampling: untouched, frozen, identical to Phase A-2.
- Hypotheses, thresholds, effect-size requirements, the Holm-Bonferroni
  correction: unchanged.
- The frozen CONTROL F files: not regenerated, not edited.
- `data/mechanism_v1/`: read-only throughout.
- No test AUPRC has been computed, inspected, or written by any code in this
  change. No V2 model has been trained.
