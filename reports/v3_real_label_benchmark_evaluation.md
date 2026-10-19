# Real-label benchmark — evaluation (label_lexicon/v4)

Historical FDA labels (TAC 2017), internally annotated. Not an independent or clinical validation.

Units: 100 ({'interaction': 55, 'advice_only': 7, 'not_applicable': 19, 'no_interaction': 19}); scored (not `not_applicable`): 81.

| Measure | Value |
|---|---|
| Outcome precision (micro) | 0.889 (40/45; 95% CI [0.765, 0.952]) |
| Outcome recall (micro) | 0.93 (40/43; 95% CI [0.814, 0.976]) |
| Outcome F1 micro / macro | 0.909 / 0.856 |
| Units given an outcome that the label states as an interaction | 0.905 (38/42; 95% CI [0.779, 0.962]) |
| Unsupported-claim rate (units with a concept neither gold nor acceptable) | 0.071 (3/42; 95% CI [0.025, 0.19]) |
| Interaction units with an extracted outcome (recall at pair level) | 0.691 (38/55; 95% CI [0.56, 0.797]) |
| Abstention on no-interaction / advice-only units | 0.846 (22/26; 95% CI [0.665, 0.939]) |
| Seriousness class correct (units given an outcome) | 0.929 (39/42; 95% CI [0.81, 0.975]) |
| Citation accuracy (matched words present in the quote) | 1.0 (68/68; 95% CI [0.947, 1.0]) |

| Concept | TP | FP | FN | P | R | F1 |
|---|---:|---:|---:|---:|---:|---:|
| bleeding | 4 | 2 | 0 | 0.667 | 1.0 | 0.8 |
| bradycardia_block | 3 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| coagulation_measure | 1 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| exposure_decrease | 2 | 1 | 0 | 0.667 | 1.0 | 0.8 |
| exposure_increase | 4 | 0 | 3 | 1.0 | 0.571 | 0.727 |
| hepatotoxicity | 5 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| hypertension | 0 | 1 | 0 | 0.0 | 0.0 | 0.0 |
| myelosuppression | 2 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| myopathy | 2 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| qt_arrhythmia | 8 | 1 | 0 | 0.889 | 1.0 | 0.941 |
| reduced_effect | 2 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| serotonin_syndrome | 7 | 0 | 0 | 1.0 | 1.0 | 1.0 |

Errors: 8 (listed in the JSON).
