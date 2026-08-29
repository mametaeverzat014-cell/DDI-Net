# CONTROL F: the pathway level is not degree-preserved

**Status:** discovered after the shuffle was frozen, before any V2 training run
**Frozen artefact:** `data/mechanism_v1_controls/shuffled_biology_seed20260829/`
**Discovered by:** `src/ddinet/data/biology.py`, when the loader first
materialised Q(d) for both arms
**Pinned by:** `tests/test_biology_bundle.py::test_control_f_does_not_preserve_pathway_count_and_inflates_it`

---

## 1. What the freeze guarantees, and what it does not

`SHUFFLE_VALIDATION.md` establishes that every drug- and protein-level degree
statistic is **exactly** identical between the true and shuffled drug-protein
graphs: row degree, distinct-pair degree, distinct-triple degree, on both sides
of the bipartite graph, and the stratum profile of every pair. That is verified
by 30 tests and it still holds.

It is a statement about the **protein** level only. The shuffle file is
`drug_protein_edges_shuffled.parquet`, and nothing else in the dataset was
touched — `protein_pathway_edges.parquet` is shared byte-for-byte by both arms,
exactly as the preregistration requires ("Pathways for shuffled assignments:
derive Q(d) from shuffled P(d) using the same protein_pathway_edges.parquet; do
not re-shuffle pathways").

But Q(d) is *derived*: it is the union of the pathway sets of the proteins in
P(d). Preserving |P(d)| does not preserve |Q(d)|, because the union of a
size-*k* protein set depends on **which** proteins are in it.

## 2. The measurement

M4 policy, all 1,705 drugs.

| Statistic | True | Shuffled |
|---|---:|---:|
| Total pathway items | 284,203 | 327,535 |
| Median per drug | 52 | 87 |
| Mean per drug | 166.7 | 192.1 |
| Max per drug | 1,078 | 1,193 |
| Drugs with 0 pathways | 91 | 74 |

Per-drug direction: shuffled is **larger for 68.0%** of drugs, equal for 6.3%,
smaller for 25.7%. Median change +13 pathways, mean +25.4, interquartile range
−1 to +50.

Set overlap between the arms, per drug:

| Level | Mean Jaccard | Median Jaccard |
|---|---:|---:|
| Protein set | 0.232 | 0.120 |
| Pathway set | 0.326 | 0.235 |

## 3. Why the direction is upward

Real drug target sets are **pathway-coherent**. A drug's targets tend to sit in
the same pathways — that is what having a mechanism means — so their pathway
sets overlap heavily and their union is small relative to the sum. A random set
of the same size draws proteins from unrelated parts of Reactome, the overlap
collapses, and the union grows toward the sum.

The annotated proteins carry a median of 3 pathways each (mean 5.9, n = 2,294
proteins with at least one Reactome edge). With 1,581 drugs holding two or more
proteins, that redundancy is exactly what the shuffle destroys.

This inflation is therefore not a defect in the shuffle algorithm. It is a
measurement *of* pathway coherence, produced as a side effect. A shuffle that
also preserved |Q(d)| would have to preserve pathway coherence, which is the
biological structure the control exists to remove.

## 4. Consequence for H-V2-3

H-V2-3 claims: true biology beats degree-preserving shuffled biology, therefore
protein *identity* matters and the model is not counting.

The asymmetry cuts two ways, and both must be stated.

**Conservative direction (helps the hypothesis).** If BIO-GINE were exploiting
pathway *count*, the shuffled arm has more of it — 15.2% more pathway items in
total, more for two drugs in three. A "true > shuffled" result therefore cannot
be explained by the control being starved of pathway signal. Under this failure
mode the control should *win*, not lose.

**Confounded direction (limits the hypothesis).** At the M4 (pathway-on) level,
the two arms differ in pathway set size as well as pathway identity. A "true >
shuffled" difference at M4 is therefore not attributable to identity alone: it
is attributable to identity *and* to coherence-driven set size, which are not
separable in this design.

## 5. What is done about it

Nothing is regenerated. The shuffle is frozen and the freeze is what makes it a
preregistered control; re-cutting it after seeing a property of it is exactly
the move this project exists to avoid.

Instead, **H-V2-3 is read from the M3 contrast as well as the M4 contrast**, and
both are reported:

- **M3 (protein level only, pathways off).** Protein degree is exactly
  preserved, at every one of the three granularities. The only difference
  between the arms is protein identity. This is the clean test of H-V2-3.
- **M4 (protein + pathway).** The preregistered primary. Reported with this
  document cited, and any positive result stated as "identity and pathway
  coherence" rather than "identity".

This is an addition to the reporting, not a change to the hypothesis or to its
thresholds (paired two-sided t-test, df = 4, p < 0.05, Cohen's d > 0.5). The M3
contrast was already a preregistered ablation cell; it is being read for a
second purpose, and this document is the record that the second purpose was
decided **before any V2 model was trained**.

## 6. What this does not affect

- `CONTROL A` (biological-degree RF): its `n_pathways` feature is derived from
  the materialised Q(d) for whichever arm it runs on, so it sees the true set
  size in the true arm and the inflated one in the shuffled arm. Correct in
  both, and the point of CONTROL A is precisely that counts are all it gets.
- The protein-level freeze: unchanged, still exact, still pinned by 30 tests.
- The frozen files: untouched. This document was added beside them, not to them.
