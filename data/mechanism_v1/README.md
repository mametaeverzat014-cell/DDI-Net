# DDI_MECH_1705_V1 — Compact Biological Dataset

**Status:** FROZEN / MODEL-READY
**Validation:** 16/16 PASS
**Created:** 2026-08-28

## Authoritative Universe

| Property | Value |
|----------|-------|
| Drugs | 1,705 |
| Positive DDI pairs | 191,392 |
| Excluded drug | DB11630 (10 pairs removed) |
| Positive pairs source | `split_assignments_random_pair.csv.gz` seed 0 (TDC bridge) |

## Files

| File | Rows | Size | Description |
|------|------|------|-------------|
| `drugs.parquet` | 1,705 | 207.7 KB | Drug table with coverage flags and counts |
| `drug_protein_edges.parquet` | 146,743 | 376.9 KB | Drug→protein edges (DrugBank + ChEMBL MOA + ChEMBL activities) |
| `proteins.parquet` | 2,778 | 102.6 KB | Protein table (UniProt/SwissProt) |
| `protein_pathway_edges.parquet` | 14,576 | 122.3 KB | Protein→pathway edges (Reactome) |
| `pathways.parquet` | 1,969 | 64.6 KB | Pathway table |
| `protein_protein_edges.parquet` | 15,087 | 181.6 KB | PPI induced subgraph (Reactome Homo sapiens) |
| `drug_adverse_event_edges.parquet` | 230,120 | 571.0 KB | Drug→adverse event edges (SIDER 4.1, 915 drugs) |
| `biological_edges.parquet` | 406,526 | 1,113.3 KB | Combined feature graph (all layers, no DDI edges) |
| `ddi_positive_labels.parquet` | 191,392 | 284.3 KB | Positive DDI labels (label=1) |
| `split_assignments.csv` | 17,050 | 375.3 KB | Drug/scaffold split assignments (2 schemes × 5 seeds) |
| `split_assignments_random_pair.csv.gz` | 956,960 | 2,903.1 KB | Random-pair split assignments (5 seeds) |
| `MANIFEST.json` | — | — | SHA-256 hashes, coverage stats, validation results |
| `MODEL_READINESS.md` | — | — | Human-readable readiness summary |
| `model_readiness.json` | — | — | Machine-readable readiness summary |
| `MECHANISM_LABEL_LIMITATIONS.md` | — | — | Why mechanism labels are QUARANTINED |

**Total: ~6.16 MB**

## Biological Feature Graph

- **Nodes:** 10,357 (drugs + proteins + pathways + adverse events)
- **Edges:** 406,526
- **Layers:** drug→protein (146,743) | protein→pathway (14,576) | PPI (15,087) | drug→AE (230,120)
- **INTERACTS_WITH edges:** 0 (hard assertion, verified)

## Drug-Protein Edge Sources

| Source | Edges | Evidence type |
|--------|-------|---------------|
| DrugBank v5.1 | 13,150 | DOCUMENTED_DATABASE_RELATION |
| ChEMBL 36 drug_mechanism | 2,255 | CURATED_MOA |
| ChEMBL 36 activities | 131,338 | EXPERIMENTAL_BIOACTIVITY |

## Coverage (1,705-drug universe)

| Feature | Drugs | % |
|---------|-------|---|
| Valid SMILES structure | 1,705 | 100.0% |
| Any protein (any source) | 1,638 | 96.1% |
| Reactome pathway | 1,552 | 91.0% |
| SIDER adverse events | 915 | 53.7% |

## Positive Pair Coverage

| Feature | Pairs | % |
|---------|-------|---|
| Both have structure | 191,392 | 100.0% |
| Both have protein (any) | 185,492 | 96.9% |
| Both have pathway | 181,255 | 94.7% |
| Shared protein | 159,186 | 83.2% |
| Shared pathway | 148,508 | 77.6% |

## Biological Shortcut Risk: HIGH

Spearman correlation between DDI degree and biological feature counts:

| Feature | r |
|---------|---|
| n_enzymes | +0.4433 |
| n_pathways | +0.4255 |
| n_proteins | +0.4072 |
| n_adverse_events | +0.3436 |
| n_chembl_proteins | +0.2981 |
| n_targets | +0.2532 |
| n_carriers | +0.2055 |
| n_transporters | +0.1879 |

Max |r| = 0.4433. Features are NOT altered — this is informational.
A model using raw biological counts as node features risks learning degree
rather than mechanism. Use structural/graph-level representations.

## Mechanism Labels: QUARANTINED

See `MECHANISM_LABEL_LIMITATIONS.md`. Summary:
- 94.21% UNKNOWN, 4.90% TOXICITY, 0.89% PK, **0.00% PD**
- Labels are regex-derived from free text, not authoritative annotations
- PHARMACODYNAMIC = 0 indicates classifier failure, not absence of PD interactions
- Do NOT use as supervision signal

## Leakage Safety

- `biological_edges.parquet` contains **zero** INTERACTS_WITH / DDI edges
- No DDI description text in any feature file
- No FAERS pair signals in feature graph (FAERS excluded; use for post-hoc validation only)
- Mechanism labels quarantined and not included in any feature file

## Split Schemes

| Scheme | File | Note |
|--------|------|------|
| random_pair | `split_assignments_random_pair.csv.gz` | Pair-level, 5 seeds |
| drug | `split_assignments.csv` | Drug-disjoint, 5 seeds |
| scaffold | `split_assignments.csv` | Scaffold-disjoint, 5 seeds |

## Data Sources

| Source | Version | Notes |
|--------|---------|-------|
| DrugBank | 5.1 (2025-01-02) | DDI + drug-protein relations |
| ChEMBL | 36 | Drug-target relations (SQLite, 29.74 GB local) |
| UniProt/SwissProt | 2026-06-10 | Protein annotations |
| Reactome | — | Protein-pathway + PPI (Homo sapiens) |
| SIDER | 4.1 | Drug adverse events |
| TDC bridge | DDI-Net master | Authoritative 1,705-drug / 191,392-pair universe |

Raw source files are NOT stored in this repository.
