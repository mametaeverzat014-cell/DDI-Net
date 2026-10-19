# Real-label benchmark — development (label_lexicon/v4)

Historical FDA labels (TAC 2017), internally annotated. Not an independent or clinical validation.

Units: 50 ({'interaction': 20, 'advice_only': 10, 'not_applicable': 9, 'no_interaction': 11}); scored (not `not_applicable`): 41.

| Measure | Value |
|---|---|
| Outcome precision (micro) | 1.0 (12/12; 95% CI [0.757, 1.0]) |
| Outcome recall (micro) | 1.0 (12/12; 95% CI [0.757, 1.0]) |
| Outcome F1 micro / macro | 1.0 / 1.0 |
| Units given an outcome that the label states as an interaction | 1.0 (12/12; 95% CI [0.757, 1.0]) |
| Unsupported-claim rate (units with a concept neither gold nor acceptable) | 0.0 (0/12; 95% CI [0.0, 0.243]) |
| Interaction units with an extracted outcome (recall at pair level) | 0.6 (12/20; 95% CI [0.387, 0.781]) |
| Abstention on no-interaction / advice-only units | 1.0 (21/21; 95% CI [0.845, 1.0]) |
| Seriousness class correct (units given an outcome) | 1.0 (12/12; 95% CI [0.757, 1.0]) |
| Citation accuracy (matched words present in the quote) | 1.0 (17/17; 95% CI [0.816, 1.0]) |

| Concept | TP | FP | FN | P | R | F1 |
|---|---:|---:|---:|---:|---:|---:|
| hepatotoxicity | 1 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| qt_arrhythmia | 7 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| reduced_effect | 3 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| serotonin_syndrome | 1 | 0 | 0 | 1.0 | 1.0 | 1.0 |

Errors: 0 (listed in the JSON).
