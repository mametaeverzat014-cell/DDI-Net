# Mechanism Label Limitations
## Dataset: DDI_MECH_1705_V1 — Status: QUARANTINED

### 1. Provenance
Labels in `ddi_mechanisms.parquet` were produced by regex/keyword matching on free-text
DrugBank DDI description fields. They are NOT original structured DrugBank annotations.

### 2. Class Distribution (full 1,428,193 deduplicated pairs)
| Class | Count | % |
|-------|-------|---|
| UNKNOWN | 1,345,430 | 94.21% |
| TOXICITY | 70,011 | 4.90% |
| PHARMACOKINETIC | 12,752 | 0.89% |
| PHARMACODYNAMIC | 0 | 0.00% |

### 3. Why PHARMACODYNAMIC = 0 Indicates Classifier Failure
PD interactions are the most common type clinically. DrugBank descriptions contain PD
language ("may increase pharmacological activity", "additive CNS depression") but the
keyword classifier never matched any. This is a classifier design failure, not absence
of PD interactions in the data.

### 4. Why 94.21% UNKNOWN Makes Supervision Inadequate
- Binary PD vs other: 0 positives — infeasible.
- Binary PK vs other: 12,752 positives — tiny subset, high imbalance.
- Binary TOX vs other: 70,011 positives — feasible but not validated.
- Fine-grained multiclass: not feasible.

### 5. Excluded from DDI_MECH_1705_V1
1. Labels are regex-derived, not authoritative.
2. PD = 0 indicates classifier failure.
3. 94.21% UNKNOWN gives no reliable supervision signal.
4. Using them would misrepresent provenance.

### 6. Path Forward (not Phase 18)
Improvement requires structured extraction from DrugBank mechanism fields,
NLP classification with validated training data, or integration of a structured
pharmacology source (e.g., NDF-RT). Do NOT repair in Phase 18.
