# DATA_PROVENANCE.md

Провенанс всех источников данных проекта DDI-Net.

**Правило: ни один файл не попадает в `data/raw/` без строки в этой таблице.**
Заполняется в момент загрузки, а не задним числом. Столбцы «версия» и «дата
загрузки» заполняются вручную — их невозможно восстановить позже, а без них
утверждение «мы использовали DrugBank» невоспроизводимо.

Последняя ревизия: 2026-08-24.

---

## 0. Статус на текущий момент

**Загружено: TDC DrugBank DDI (2026-08-24).** См. раздел 1.
**Не загружено: TWOSIDES** — отложен до конца Фазы A как вторая база для
проверки устойчивости выводов.

Загрузка выполняется вручную вне рабочего окружения: его egress-политика
блокирует все биомедицинские хосты. Проверено 2026-08-23 — HTTP 403 на CONNECT
для `go.drugbank.com`, `pubchem.ncbi.nlm.nih.gov`, `sideeffects.embl.de`,
`ddinter.scbdd.com`, `snap.stanford.edu`, `api.fda.gov`,
`dataverse.harvard.edu`. Доступны только `pypi.org` и
`raw.githubusercontent.com`.

## 1. Первичный источник (Фаза A) — ЗАГРУЖЕНО

| Поле | Значение |
|---|---|
| Название | Therapeutics Data Commons — `tdc.multi_pred.DDI(name='DrugBank')` |
| Файл | `data/raw/drugbank.tab.gz` |
| Версия загрузчика | **PyTDC 1.1.15** |
| Дата загрузки | **2026-08-24** |
| Размер (gzip) | 4 480 481 байт (4.27 МБ) |
| Размер (распакованный) | 44 381 882 байта (42.3 МБ) |
| SHA-256 | `cd2c99aa483a9917356047477ddbd1f8d792017be3d66fc8415af8b7dfeff883` |
| Формат | TSV в gzip; колонки `ID1, ID2, Y, Map, X1, X2` |
| URL | <https://tdcommons.ai/multi_pred_tasks/ddi/> |
| Лицензия | CC BY 4.0 (TDC); подлежащий DrugBank — под собственной некоммерческой лицензией |
| Можно распространять | сырые данные DrugBank — нет; файл хранится в репозитории как выгрузка TDC для воспроизводимости учебной работы |

**Почему файл закоммичен в gzip.** Веб-загрузчик GitHub ограничен 25 МБ,
распакованный файл — 42.3 МБ. `pandas.read_csv(..., compression="gzip")` читает
его напрямую, распаковка на диск не нужна.

### Измеренное содержимое

Проверено `scripts/08_dataset_report.py`, полный отчёт — `reports/dataset_report.md`.

| Величина | Значение |
|---|---|
| Строк в файле | 191 808 |
| Уникальных **неупорядоченных пар** | 191 402 |
| Уникальных препаратов | 1 706 |
| Типов взаимодействий (`Y`) | 86 |
| Пар с несколькими типами | 406 |
| Самопетель | 0 |
| Валидных SMILES по RDKit | 1 705 / 1 706 (99.94%) |
| Несогласованных SMILES для одного ID | 0 |
| Дублирующихся структур (InChIKey) | 0 |
| Плотность графа | 13.16% |

Расхождение 191 808 против 191 402 объяснено: 406 неупорядоченных пар записаны
дважды с **разными** `Y`. Точных дублей нет — пара может нести несколько
документированных механизмов одновременно.

**`Y` — это тип взаимодействия, а не бинарная метка. Отрицательных примеров в
датасете нет вообще.** См. `LIMITATIONS.md`, L1.3.

### Условия воспроизводимости

| Поле | Значение |
|---|---|
| Python | 3.11.16 |
| Платформа загрузки | macOS arm64 |
| PyTDC | 1.1.15 |
| **setuptools** | **< 81 — обязательно** |

**Про setuptools.** PyTDC импортирует `pkg_resources`, который был удалён в
setuptools 84. С более новым setuptools загрузка падает на импорте, а не на
сетевой ошибке, поэтому диагностируется не сразу. Требуется:

```bash
pip install "setuptools<81" PyTDC==1.1.15
```

Рабочее окружение этого репозитория несёт setuptools 84, то есть PyTDC здесь
установить нельзя — ещё одна причина, по которой загрузка выполняется вне его.

### Процедура повторной загрузки

```bash
pip install "setuptools<81" PyTDC==1.1.15
python -c "from tdc.multi_pred import DDI; DDI(name='DrugBank', path='data/raw')"
gzip -9 data/raw/drugbank.tab
sha256sum data/raw/drugbank.tab.gz   # сверить с таблицей выше
```

Цитирование:

> Huang K, Fu T, Gao W, et al. Therapeutics Data Commons: Machine Learning
> Datasets and Tasks for Drug Discovery and Development. NeurIPS Datasets and
> Benchmarks, 2021.

> Wishart DS, Feunang YD, Guo AC, et al. DrugBank 5.0: a major update to the
> DrugBank database for 2018. Nucleic Acids Res. 2018;46(D1):D1074-D1082.

**Оговорка о лицензии.** TDC распространяет производные от DrugBank, чья
лицензия некоммерческая и ограничивает перераспространение. Для ISEF-работы
(некоммерческое исследование) это допустимо; в тексте работы источник
цитируется как DrugBank *через* TDC.

### TWOSIDES — не загружен

Отложен до конца Фазы A. Назначение: вторая база для проверки устойчивости
выводов о влиянии схемы разбиения. Строки таблицы заполнить при загрузке.

## 2. Внешний код (Фаза A)

| Репозиторий | Назначение | Лицензия | Статус |
|---|---|---|---|
| SSI-DDI | Baseline из литературы, авторская реализация | см. репозиторий | **не клонирован** |
| MHCADDI | Baseline из литературы, авторская реализация | см. репозиторий | **не клонирован** |

Кладутся в `external/`, адаптируются под наши сплиты, не переписываются с нуля.
`github.com` из рабочего окружения недоступен — клонирование вручную.

## 3. Источники, заведённые в `src/ddinet/data/sources.py`

Таблица сгенерирована из реестра. Ни один не загружен.

| Ключ | Название | Доступ | Локально | Версия | Дата загрузки | Лицензия | Распространяем |
|---|---|---|---|---|---|---|---|
| `biosnap_chch` | BioSNAP ChCh-Miner - drug-drug interaction network | прямая ссылка | **не загружено** | — | — | Freely available for research (Stanford SNAP BioSNAP collection) | нет |
| `ddinter` | DDInter 2.0 | прямая ссылка | **не загружено** | — | — | Free for academic research (see site terms) | нет |
| `drugbank_full` | DrugBank full database release (XML) | нужна лицензия | **не загружено** | — | — | DrugBank Academic (non-commercial) Licence - free for academic use, requires account approval; redistribution prohibited | нет |
| `drugbank_vocabulary` | DrugBank Open Data - drug vocabulary | прямая ссылка | **не загружено** | — | — | CC0 1.0 Universal (public domain dedication) | да |
| `openfda_faers` | openFDA - FAERS adverse event reports | API | **не загружено** | — | — | Public domain (US Government work); see openFDA disclaimer | да |
| `pubchem` | PubChem PUG-REST | API | **не загружено** | — | — | Public domain (US Government work) | да |
| `sider` | SIDER 4.1 - Side Effect Resource | прямая ссылка | **не загружено** | — | — | CC BY-NC-SA 4.0 (non-commercial, share-alike) | нет |
| `sider_atc` | SIDER 4.1 - ATC codes | прямая ссылка | **не загружено** | — | — | CC BY-NC-SA 4.0 | нет |
| `sider_drug_names` | SIDER 4.1 - drug names | прямая ссылка | **не загружено** | — | — | CC BY-NC-SA 4.0 | нет |
| `twosides` | TWOSIDES (nSides) - FAERS-derived polypharmacy side effects | прямая ссылка | **не загружено** | — | — | CC BY 4.0 | нет |

**Статус: НЕ ИСПОЛЬЗУЮТСЯ.** Реестр и парсеры к нему
(`drugbank.py`, `sider.py`, `ddinter.py`, `biosnap.py`, `pubchem.py`,
`download.py`) писались под первоначальный план. После перехода на TDC ни один
из них не участвует в конвейере.

Не удалены намеренно: решение принимается после того, как будет видно, покрывает
ли TDC все потребности Фаз A–C. Конкретно под вопросом две вещи, которых в
TDC-выгрузке нет:

- аннотации CYP450 (субстрат/ингибитор/индуктор) — нужны для Фазы B, в
  DrugBank XML они есть;
- клиническая тяжесть взаимодействия — есть в DDInter, в TDC-выгрузке нет.

Записи для TDC в реестре `sources.py` пока нет: загрузка выполняется вручную,
и провенанс ведётся здесь, в разделе 1.

## 4. Синтетическая фикстура — НЕ источник данных

| Поле | Значение |
|---|---|
| Путь | `tests/fixtures/synthetic_ddi/` |
| Содержание | 104 препарата, 467 «взаимодействий» |
| Происхождение | **сгенерировано LLM (Claude) по памяти 2026-08-23** |
| URL | **отсутствует** |
| Версия | **отсутствует** |
| Лицензия | **отсутствует** |
| Статус | тестовая фикстура; **расчёт и публикация метрик запрещены** |

Перенесена из `data/curated/` 2026-08-23. Каждый CSV несёт запрещающий заголовок
в первых строках. Все ранее посчитанные по ней числа аннулированы — см.
`reports/ANNULLED.md`.

## 5. Контроль целостности

`src/ddinet/data/download.py` при каждой загрузке пишет SHA-256 в
`data/raw/manifest.json` и предупреждает при расхождении с записанным ранее.

Обоснование: базы — живые ресурсы, DrugBank обновляется примерно ежеквартально.
«Мы использовали DrugBank» — невоспроизводимое утверждение; «мы использовали
релиз с хешем `a1b2c3…`» — воспроизводимое.

## 6. Цитирования

**BioSNAP ChCh-Miner - drug-drug interaction network**  
Zitnik M, Sosic R, Maheshwari S, Leskovec J. BioSNAP Datasets: Stanford Biomedical Network Dataset Collection. 2018.  
<https://snap.stanford.edu/biodata/datasets/10001/10001-ChCh-Miner.html>

**DDInter 2.0**  
Xiong G, et al. DDInter: an online drug-drug interaction database towards improving clinical practice and patient safety. Nucleic Acids Res. 2022;50(D1):D1200-D1207.  
<http://ddinter.scbdd.com/download/>

**DrugBank full database release (XML)**  
Knox C, et al. DrugBank 6.0: the DrugBank Knowledgebase for 2024. Nucleic Acids Res. 2024;52(D1):D1265-D1275.  
<https://go.drugbank.com/releases/latest>

**DrugBank Open Data - drug vocabulary**  
Wishart DS, et al. DrugBank 5.0: a major update to the DrugBank database for 2018. Nucleic Acids Res. 2018;46(D1):D1074-D1082.  
<https://go.drugbank.com/releases/latest#open-data>

**openFDA - FAERS adverse event reports**  
U.S. Food and Drug Administration. openFDA drug/event endpoint.  
<https://open.fda.gov/apis/drug/event/>

**PubChem PUG-REST**  
Kim S, et al. PubChem 2023 update. Nucleic Acids Res. 2023;51(D1):D1373-D1380.  
<https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest>

**SIDER 4.1 - Side Effect Resource**  
Kuhn M, Letunic I, Jensen LJ, Bork P. The SIDER database of drugs and side effects. Nucleic Acids Res. 2016;44(D1):D1075-D1079.  
<http://sideeffects.embl.de/download/>

**SIDER 4.1 - ATC codes**  
Kuhn M, et al. Nucleic Acids Res. 2016;44(D1):D1075-D1079.  
<http://sideeffects.embl.de/download/>

**SIDER 4.1 - drug names**  
Kuhn M, et al. Nucleic Acids Res. 2016;44(D1):D1075-D1079.  
<http://sideeffects.embl.de/download/>

**TWOSIDES (nSides) - FAERS-derived polypharmacy side effects**  
Tatonetti NP, Ye PP, Daneshjou R, Altman RB. Data-driven prediction of drug effects and interactions. Sci Transl Med. 2012;4(125):125ra31.  
<https://nsides.io/>

