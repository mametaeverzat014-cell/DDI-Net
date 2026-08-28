# CHEMBL_TABLE_MAP.md — какие таблицы ChEMBL 36 нужны и зачем

**Статус: составлено по опубликованной схеме ChEMBL, база на диск ещё не
получена.** Проверить утверждения этого документа против настоящего файла
нельзя, поэтому экстрактор (`scripts/extract_chembl.py`) **сам проверяет схему
перед извлечением** и отказывается работать, если таблица или колонка
отсутствует. Расхождение будет обнаружено при первом запуске, а не молча
пропущено.

Ожидаемый файл: `data/raw/chembl/chembl_36.db` (после распаковки
`chembl_36_sqlite.tar.gz`), плюс `chembl_36_uniprot_mapping.txt`.

---

## Принцип отбора

ChEMBL — база **биоактивности**, а не механизмов лекарственных взаимодействий.
Из неё берётся ровно три вещи:

1. **структуры и идентификаторы** — чтобы соединить с корпусом по InChIKey;
2. **связь соединение → белок** — второй независимый источник к DrugCentral,
   что впервые даст измеримое *согласие между источниками*;
3. **происхождение утверждения** — тип анализа, уровень доверия, ссылка на
   публикацию, чтобы уровень доказательства не был выдуман.

Таблицы, не служащие ни одной из трёх целей, не читаются вовсе. Это не
экономия места, а требование к воспроизводимости: чем меньше прочитано, тем
меньше можно случайно внести.

---

## A. Соединения

### `molecule_dictionary`
| | |
|---|---|
| Назначение | реестр соединений; отсюда `chembl_id` |
| Первичный ключ | `molregno` |
| Нужные колонки | `molregno`, `chembl_id`, `pref_name`, `max_phase`, `molecule_type`, `therapeutic_flag` |
| Внешние ключи | — (родитель для всего остального) |
| Зачем | `molregno` — внутренний ключ ChEMBL, `chembl_id` — внешний. Оба нужны: первый для соединений внутри базы, второй для провенанса |

`max_phase` фиксируется, но **не используется как фильтр по умолчанию**:
отбор только одобренных препаратов сузил бы источник до того же смещения по
изученности, которое проект измеряет.

## B. Структуры

### `compound_structures`
| | |
|---|---|
| Назначение | канонический SMILES и **стандартный InChIKey** |
| Первичный ключ | `molregno` |
| Нужные колонки | `molregno`, `canonical_smiles`, `standard_inchi_key` |
| Внешние ключи | `molregno` → `molecule_dictionary` |
| Зачем | **единственный путь соединения с корпусом.** `standard_inchi_key` сравнивается с InChIKey корпуса напрямую |

Соединение по названию не рассматривается: в корпусе названий нет.

### `molecule_synonyms` (необязательно)
| | |
|---|---|
| Назначение | торговые названия и INN |
| Нужные колонки | `molregno`, `synonyms`, `syn_type` |
| Зачем | только как справочные синонимы сущности. **Не как ключ соединения** |

## C. Препараты

Отдельной «таблицы препаратов» не читаем. Признак «это лекарство» —
`molecule_dictionary.max_phase` и `therapeutic_flag`, они уже взяты в A.

## D. Мишени

### `target_dictionary`
| | |
|---|---|
| Первичный ключ | `tid` |
| Нужные колонки | `tid`, `chembl_id`, `pref_name`, `target_type`, `organism` |
| Зачем | мишень как объект. `target_type` = `SINGLE PROTEIN` — единственный тип, дающий однозначный белок |

Фильтр `organism = 'Homo sapiens'` обязателен: мишень, измеренная на крысе, —
свидетельство о крысиной фармакологии.

## E. Компоненты мишени

### `target_components`
| | |
|---|---|
| Нужные колонки | `tid`, `component_id`, `homologue` |
| Внешние ключи | `tid` → `target_dictionary`, `component_id` → `component_sequences` |
| Зачем | мишень может быть комплексом из нескольких белков; связь «многие-ко-многим» |

### `component_sequences`
| | |
|---|---|
| Первичный ключ | `component_id` |
| Нужные колонки | `component_id`, `accession`, `component_type`, `organism` |
| Зачем | **`accession` — это UniProt.** Отсюда цепочка к Reactome и к DrugCentral |

Путь соединения:
```
molecule_dictionary.molregno
  -> compound_structures.standard_inchi_key      (в корпус)
  -> drug_mechanism/activities.tid
  -> target_components.component_id
  -> component_sequences.accession               (в UniProt, далее в Reactome)
```

## F. Механизмы

### `drug_mechanism`
| | |
|---|---|
| Первичный ключ | `mec_id` |
| Нужные колонки | `molregno`, `tid`, `mechanism_of_action`, `action_type`, `direct_interaction`, `molecular_mechanism`, `disease_efficacy` |
| Внешние ключи | `molregno`, `tid`, `action_type` → `action_type` |
| Зачем | **самая ценная таблица.** Курированный механизм действия со знаком (INHIBITOR / AGONIST / …), а не измеренная активность |

Это прямой аналог `MOA=1` у DrugCentral и главный кандидат на измерение
согласия двух источников.

### `action_type`
| | |
|---|---|
| Первичный ключ | `action_type` |
| Нужные колонки | `action_type`, `description`, `parent_type` |
| Зачем | словарь знаков действия; `parent_type` группирует до POSITIVE / NEGATIVE MODULATOR |

## G. Анализы

### `assays`
| | |
|---|---|
| Первичный ключ | `assay_id` |
| Нужные колонки | `assay_id`, `doc_id`, `tid`, `assay_type`, `confidence_score`, `assay_organism` |
| Зачем | связывает активность с мишенью и с публикацией; `confidence_score` (0–9) говорит, насколько уверенно активность приписана именно этой мишени |

**`confidence_score` — не вероятность.** Это порядковая шкала ChEMBL. В
`Evidence.confidence` она не кладётся; идёт в `metadata`. Порог по умолчанию —
`>= 8` (прямая единственная белковая мишень).

## H. Активности

### `activities`
| | |
|---|---|
| Первичный ключ | `activity_id` |
| Нужные колонки | `activity_id`, `assay_id`, `molregno`, `standard_type`, `standard_relation`, `standard_value`, `standard_units`, `pchembl_value`, `data_validity_comment`, `potential_duplicate` |
| Зачем | количественная биоактивность |

Обязательные фильтры, каждый со своей причиной:

| Фильтр | Причина |
|---|---|
| `standard_type IN ('IC50','Ki','Kd','EC50')` | сопоставимые величины связывания |
| `standard_relation = '='` | `>` и `<` — это границы, а не измерения |
| `data_validity_comment IS NULL` | ChEMBL сам помечает подозрительные строки |
| `potential_duplicate = 0` | иначе одно измерение считается дважды |
| `pchembl_value IS NOT NULL` | единая шкала −log10(M) |

Это самая большая таблица базы (десятки миллионов строк). Она читается
**потоково**, с фильтрами в SQL, и никогда целиком в память.

## I. Документы

### `docs`
| | |
|---|---|
| Первичный ключ | `doc_id` |
| Нужные колонки | `doc_id`, `pubmed_id`, `doi`, `year` |
| Зачем | `Evidence.reference`. Утверждение без ссылки на источник не отличимо от догадки |

## J. Сопоставление с UniProt

### `chembl_36_uniprot_mapping.txt`
Плоский файл, не таблица. Ожидаемые колонки: UniProt accession, ChEMBL target
id, название, тип мишени.

Он **дублирует** путь через `target_components` → `component_sequences`.
Оба извлекаются, и расхождение между ними — проверка целостности: если
курированный файл и путь по таблицам расходятся, доверять нельзя ни одному без
разбора.

---

## Таблицы, которые НЕ читаются

| Таблица | Почему нет |
|---|---|
| `compound_properties` | дескрипторы уже считаются RDKit из SMILES |
| `binding_sites`, `site_components` | нужна структурная биология, её тут нет |
| `predicted_binding_domains` | предсказания модели, `EvidenceType.COMPUTATIONAL`; при добавлении — только с флагом |
| `metabolism`, `metabolism_refs` | понадобятся для PK-ветви, но требуют отдельного разбора ролей; отложено осознанно |
| `drug_indication`, `indication_refs` | показания к применению, не механизм |
| `cell_dictionary`, `tissue_dictionary` | контекст анализа, не используется |
| `compound_records`, `formulations` | регуляторные записи |

---

## Оценка объёмов

| Выжимка | Ожидаемый порядок строк |
|---|---|
| `chembl_compounds.parquet` | ~2.4 млн |
| `chembl_targets.parquet` | ~15 тыс (человек, SINGLE PROTEIN) |
| `chembl_mechanisms.parquet` | ~40 тыс |
| `chembl_activities.parquet` | ~2–5 млн после фильтров |
| `chembl_uniprot_mapping.parquet` | ~15 тыс |

Числа взяты из порядков величин публичных релизов ChEMBL и **подлежат замене
измеренными** при первом запуске экстрактора. Он печатает фактические счётчики
и пишет их в `reports/chembl_extraction_summary.json`.
