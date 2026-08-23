# DATA_PROVENANCE.md

Провенанс всех источников данных проекта DDI-Net.

**Правило: ни один файл не попадает в `data/raw/` без строки в этой таблице.**
Заполняется в момент загрузки, а не задним числом. Столбцы «версия» и «дата
загрузки» заполняются вручную — их невозможно восстановить позже, а без них
утверждение «мы использовали DrugBank» невоспроизводимо.

Последняя ревизия: 2026-08-23.

---

## 0. Статус на текущий момент

**Реальных данных в репозитории нет.** `data/raw/` пуст (0 непустых файлов).

Причина: egress-политика окружения, в котором писался код, блокирует все
биомедицинские хосты. Проверено 2026-08-23 — HTTP 403 на CONNECT от прокси для
`go.drugbank.com`, `pubchem.ncbi.nlm.nih.gov`, `sideeffects.embl.de`,
`ddinter.scbdd.com`, `snap.stanford.edu`, `api.fda.gov`,
`dataverse.harvard.edu`. Доступны только `pypi.org` и
`raw.githubusercontent.com`.

Загрузка выполняется вручную вне этого окружения.

## 1. Первичный источник (Фаза A)

| Поле | Значение |
|---|---|
| Название | Therapeutics Data Commons — `tdc.multi_pred.DDI` |
| Датасеты | `DrugBank` (~191k пар, 86 классов взаимодействий), `TWOSIDES` (~4.6M пар, побочные эффекты) |
| Способ доступа | пакет `PyTDC` с PyPI; данные тянутся с `dataverse.harvard.edu` |
| URL | <https://tdcommons.ai/multi_pred_tasks/ddi/> |
| Версия | **заполнить при загрузке** (`tdc.__version__` + дата снапшота датасета) |
| Дата загрузки | **заполнить при загрузке** |
| Лицензия | CC BY 4.0 (TDC); подлежащий DrugBank — под собственной лицензией, см. ниже |
| Можно распространять | **нет** — сырые файлы не коммитим |
| SHA-256 | **заполнить при загрузке** |
| Статус | **не загружено** |

Цитирование:

> Huang K, Fu T, Gao W, et al. Therapeutics Data Commons: Machine Learning
> Datasets and Tasks for Drug Discovery and Development. NeurIPS Datasets and
> Benchmarks, 2021.

> Zitnik M, Sosic R, Leskovec J. BioSNAP Datasets: Stanford Biomedical Network
> Dataset Collection, 2018. (для TWOSIDES-производных)

**Оговорка о лицензии, которую нужно проверить перед публикацией.** TDC
распространяет производные от DrugBank. Собственная лицензия DrugBank
некоммерческая и ограничивает перераспределение. Для ISEF-работы
(некоммерческое исследование) это допустимо, но в тексте работы источник должен
цитироваться как DrugBank *через* TDC, а сырые файлы не выкладываются.

### Процедура загрузки

```bash
pip install PyTDC
python -c "
from tdc.multi_pred import DDI
DDI(name='DrugBank', path='data/raw/tdc')
DDI(name='TWOSIDES', path='data/raw/tdc')
"
sha256sum data/raw/tdc/*        # значения внести в таблицу выше
```

После загрузки заполнить версию, дату и хеши в разделе 1 и закоммитить
изменение этого файла отдельным коммитом.

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

**Замечание.** Этот реестр писался под первоначальный план (DrugBank XML +
DDInter + SIDER + BioSNAP). После перехода на TDC часть источников может стать
ненужной. Записи сохранены, потому что парсеры к ним написаны и оттестированы;
решение об их судьбе принимается отдельно. Записи для TDC в реестре пока нет —
это задача Фазы A.

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

