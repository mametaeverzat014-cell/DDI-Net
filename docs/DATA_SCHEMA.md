# DATA_SCHEMA.md — каноническая внутренняя схема

Схема **не зависит** ни от одного внешнего источника. Адаптеры приводят к ней
любой источник; модель читает только её. Это единственный способ не переписывать
модель при смене источника — а источники уже менялись (DrugBank закрыл выгрузки).

Формат хранения: **Parquet** в `data/processed/`. PostgreSQL не вводится, пока
не понадобится API — см. `DATA_PIPELINE.md`.

---

## 1. Общее правило провенанса

**У каждой связи, пришедшей извне, обязательны поля провенанса.** Связь без
провенанса не принимается — это отличает внешний факт от предположения.

```python
@dataclass(frozen=True)
class Provenance:
    source: str            # 'drugbank' | 'ddinter' | 'drugcentral' | ...
    source_id: str         # идентификатор записи В ИСТОЧНИКЕ
    source_version: str    # релиз/дата версии, не дата скачивания
    evidence_type: str     # см. EVIDENCE_MODEL.md
    reference: str | None  # DOI / PMID, если есть
    confidence: float | None
    retrieval_date: str    # ISO-8601
```

`source_version` и `retrieval_date` — разные вещи. Первое отвечает «какая версия
данных», второе «когда мы её взяли». Для воспроизводимости нужно первое.

---

## 2. Сущности

### Молекулярный уровень

| Сущность | Ключ | Обязательные поля | Источник |
|---|---|---|---|
| `Drug` | `drug_id` (DrugBank ID) | `name` | TDC / DrugBank |
| `Compound` | `inchikey` | `smiles`, `canonical_smiles`, `formula` | TDC |
| `Molecule` | `inchikey` | атомный граф (производное) | RDKit |
| `Substructure` | `(inchikey, scheme, index)` | `scheme` ∈ {murcko, brics, ecfp_bit} | RDKit |

`Drug` и `Compound` разделены намеренно: один препарат может иметь несколько
солевых форм с разными `inchikey`, а одна структура — принадлежать нескольким
торговым наименованиям.

### Биологический уровень

| Сущность | Ключ | Обязательные поля | Статус данных |
|---|---|---|---|
| `Protein` | `uniprot_id` | `name`, `organism` | **нет источника** |
| `Enzyme` | `uniprot_id` | `name`, `family` (напр. CYP3A4) | **нет источника** |
| `Transporter` | `uniprot_id` | `name`, `family` | **нет источника** |
| `Target` | `uniprot_id` | `name` | DrugCentral (кандидат) |
| `Pathway` | `pathway_id` | `name`, `ontology` (Reactome/KEGG) | Reactome (кандидат) |
| `Metabolite` | `inchikey` | `name` | **нет источника** |
| `BiologicalSystem` | `system_id` | `name`, `ontology` | **не решено** |

`Enzyme` и `Transporter` — подтипы `Protein`, а не независимые сущности:
у них тот же ключ `uniprot_id`. Разделены, потому что участвуют в разных
механизмах.

### Уровень взаимодействия

| Сущность | Ключ | Обязательные поля | Статус |
|---|---|---|---|
| `Interaction` | `pair_key` (упорядоченная пара `drug_id`) | `label` | **есть** (TDC) |
| `Mechanism` | `mechanism_id` | `category`, `subcategory` | см. `MECHANISM_ONTOLOGY.md` |
| `Evidence` | `evidence_id` | `level`, `Provenance` | см. `EVIDENCE_MODEL.md` |
| `Severity` | — | `level` ∈ {Major, Moderate, Minor, Unknown} | DDInter (кандидат) |

**`pair_key` упорядочен лексикографически.** Взаимодействие симметрично,
поэтому (A,B) и (B,A) — одна запись. Хранение обеих привело бы к тому, что одна
пара попала бы и в обучение, и в тест.

---

## 3. Связи

| Связь | Кардинальность | Провенанс | Данные |
|---|---|---|---|
| `Drug HAS_STRUCTURE Compound` | N:1 | обязателен | **есть** |
| `Compound CONTAINS Atom` | 1:N | производное | **есть** (RDKit) |
| `Drug TARGETS Protein` | N:M | обязателен | нет |
| `Drug INHIBITS Enzyme` | N:M | обязателен | нет |
| `Drug INDUCES Enzyme` | N:M | обязателен | нет |
| `Drug SUBSTRATE_OF Enzyme` | N:M | обязателен | нет |
| `Drug TRANSPORTED_BY Transporter` | N:M | обязателен | нет |
| `Drug AFFECTS Pathway` | N:M | обязателен | нет |
| `Drug INTERACTS_WITH Drug` | N:M, **симметрична** | обязателен | **есть** |
| `Interaction HAS_MECHANISM Mechanism` | N:M | обязателен + `mapping_confidence` | нет |
| `Mechanism INVOLVES Protein/Enzyme/Transporter` | N:M | обязателен | нет |
| `Mechanism AFFECTS Pathway` | N:M | обязателен | нет |
| `Evidence SUPPORTS Interaction` | N:M | сам является провенансом | нет |
| `Evidence SUPPORTS Mechanism` | N:M | сам является провенансом | нет |

**Три роли по ферменту разделены намеренно.** `INHIBITS`, `INDUCES`,
`SUBSTRATE_OF` нельзя схлопывать в «связан с CYP3A4»: весь механизм в том, что
*ингибитор* поднимает экспозицию *субстрата*. Два субстрата одного фермента лишь
конкурируют, и эффект много слабее. Схлопывание уничтожает механизм.

---

## 4. Инварианты, проверяемые при сборке

1. `pair_key` лексикографически упорядочен; дубликатов нет.
2. Каждый `Compound` имеет валидный SMILES, парсящийся RDKit.
3. Каждая внешняя связь имеет непустой `Provenance.source` и `source_version`.
4. `Drug INTERACTS_WITH Drug` не содержит петель (A,A).
5. Идентификаторы белков — UniProt; отображение из других систем протоколируется.
6. `Mechanism` без `mapping_confidence` не принимается.
7. Ни одна связь, выведенная моделью, не попадает в таблицы внешних фактов.

Инварианты 1–4 покрываются существующими тестами; 5–7 — новые.

---

## 5. Разделение выведенного и внешнего

**Строгое разделение таблиц:**

```
data/knowledge_graph/external/    # только внешние факты с провенансом
data/knowledge_graph/inferred/    # только выводы модели
```

Их **нельзя** объединять в одну таблицу с колонкой-флагом: слишком легко
потерять флаг при join. Разные каталоги делают смешение видимым.

---

## 6. Чего схема сознательно НЕ содержит

* **Дозировок и режимов приёма** — их нет в источниках, а без них «опасность»
  взаимодействия неопределена.
* **Пациентских данных** — проект их не использует.
* **Клинических рекомендаций** — система не даёт указаний к действию.
* **Вероятностей взаимодействия как фактов** — предсказания живут отдельно от
  графа знаний, в `Prediction`, и никогда не записываются в `external/`.
