#!/usr/bin/env python3
"""Общие мишени по ChEMBL — артефакт скрининговых панелей, а не биология.

ЗАЧЕМ. Проект показал, что «насколько препарат изучен» подменяет собой химию
через степень узла в графе DDI (scripts/23) и через число биологических
аннотаций (CONTROL F). Здесь измеряется третий канал того же явления.

ChEMBL хранит результаты биоактивности: соединения прогоняют через наборы
анализов, и наборы у разных препаратов во многом совпадают. Поэтому два
произвольных препарата «делят мишени» просто потому, что их тестировали на
одних и тех же белках. Курированные отношения DrugBank такого не дают: там
записана роль белка для конкретного препарата, а не факт постановки анализа.

Сценарий обнаружения был буквальным: при сборке блока «общая биология» на сайте
метформин и варфарин разделили 95 мишеней. Метформин выводится почками и не
делит с варфарином ни одного метаболического пути; по DrugBank у них ноль
общих белков. Отсюда и вопрос, насколько это общее явление.

ЧТО СЧИТАЕТСЯ. На случайной выборке неупорядоченных пар:
  * доля пар, у которых есть хотя бы одна общая мишень, по каждому источнику;
  * ранговая корреляция числа общих мишеней по ChEMBL с тем, насколько мало
    аннотирован менее изученный препарат пары — если связь сильная, перекрытие
    объясняется объёмом скрининга, а не общей биологией;
  * какая доля «общих по ChEMBL» пар подтверждается DrugBank.

Выборка, а не полное пространство: 1 452 660 пар считались бы долго, а
доверительный интервал доли на 6000 пар и так уже ±1,3 %. Сид зафиксирован.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
EDGES = ROOT / "data" / "mechanism_v1" / "drug_protein_edges.parquet"
OUT_CSV = ROOT / "reports" / "chembl_panel_artifact.csv"
OUT_MD = ROOT / "reports" / "chembl_panel_artifact.md"

SEED = 0
N_PAIRS = 6000
DRUGBANK = "DrugBank_v5.1"


def main() -> int:
    edges = pd.read_parquet(EDGES).drop_duplicates(
        ["drugbank_id", "uniprot_id", "relation_type", "evidence_source"]
    )
    chembl = edges[edges.evidence_source.str.startswith("ChEMBL")]
    drugbank = edges[edges.evidence_source == DRUGBANK]

    # Мишени по каждому источнику. У DrugBank берётся именно relation_type
    # target: сравнивать надо сопоставимые роли, а не всё подряд.
    ch = {d: set(g.uniprot_id) for d, g in chembl.groupby("drugbank_id")}
    db = {
        d: set(g[g.relation_type == "target"].uniprot_id)
        for d, g in drugbank.groupby("drugbank_id")
    }
    ids = sorted(set(ch) | set(db))

    rng = random.Random(SEED)
    pairs = [tuple(rng.sample(ids, 2)) for _ in range(N_PAIRS)]

    sh_ch, sh_db, min_annot = [], [], []
    for a, b in pairs:
        A, B = ch.get(a, set()), ch.get(b, set())
        sh_ch.append(len(A & B))
        min_annot.append(min(len(A), len(B)))
        sh_db.append(len(db.get(a, set()) & db.get(b, set())))

    sh_ch = np.array(sh_ch)
    sh_db = np.array(sh_db)
    min_annot = np.array(min_annot)

    frac_ch = float((sh_ch > 0).mean())
    frac_db = float((sh_db > 0).mean())
    rho = float(spearmanr(sh_ch, min_annot).statistic)
    overlap = sh_ch > 0
    confirmed = float((sh_db[overlap] > 0).mean())

    rows = [
        {"metric": "pairs_sampled", "value": N_PAIRS},
        {"metric": "seed", "value": SEED},
        {"metric": "frac_pairs_sharing_target_chembl", "value": round(frac_ch, 6)},
        {"metric": "frac_pairs_sharing_target_drugbank", "value": round(frac_db, 6)},
        {"metric": "mean_shared_targets_chembl", "value": round(float(sh_ch.mean()), 4)},
        {"metric": "mean_shared_targets_drugbank", "value": round(float(sh_db.mean()), 4)},
        {"metric": "median_shared_targets_chembl", "value": float(np.median(sh_ch))},
        {"metric": "median_shared_targets_drugbank", "value": float(np.median(sh_db))},
        {"metric": "spearman_shared_chembl_vs_min_annotation_count", "value": round(rho, 6)},
        {"metric": "frac_chembl_overlaps_confirmed_by_drugbank", "value": round(confirmed, 6)},
        {"metric": "n_chembl_target_edges", "value": int(len(chembl))},
        {"metric": "n_drugbank_target_edges",
         "value": int((drugbank.relation_type == "target").sum())},
    ]
    pd.DataFrame(rows).to_csv(OUT_CSV, index=False)

    inflation = frac_ch / frac_db if frac_db else float("nan")
    OUT_MD.write_text(f"""# Общие мишени по ChEMBL — артефакт панелей

Считается `scripts/50_chembl_panel_artifact.py`. Выборка {N_PAIRS} случайных
неупорядоченных пар, сид {SEED}.

| | ChEMBL | DrugBank |
|---|---|---|
| доля пар с ≥1 общей мишенью | **{100 * frac_ch:.1f} %** | **{100 * frac_db:.1f} %** |
| в среднем общих мишеней на пару | {sh_ch.mean():.1f} | {sh_db.mean():.2f} |
| медиана | {np.median(sh_ch):.0f} | {np.median(sh_db):.0f} |
| рёбер препарат–мишень в источнике | {len(chembl)} | {int((drugbank.relation_type == 'target').sum())} |

**Завышение доли пар с «общей биологией»: в {inflation:.0f} раз.**

**Spearman(число общих мишеней по ChEMBL, число аннотаций у менее изученного
препарата пары) = {rho:+.3f}.** Перекрытие почти полностью объясняется тем,
насколько препараты скринировали, а не тем, что у них общего в организме.

Из пар, «делящих мишени» по ChEMBL, DrugBank подтверждает **{100 * confirmed:.1f} %**.

## Почему это тот же артефакт, что и остальные

Три независимых канала, по которым «насколько препарат изучен» подменяет собой
биологию:

| канал | измерение | где |
|---|---|---|
| степень узла в графе DDI | R² 0,885–0,954 | `reports/degree_shortcut_probe.csv` |
| число биологических аннотаций | 0,812 → 0,692 при перемешивании с сохранением степеней | CONTROL F |
| перекрытие панелей ChEMBL | ρ = {rho:+.3f} | этот файл |

## Следствие для практики

Модель, которая считает признаком «сколько общих мишеней у пары», не отличив
источник, выучит объём скрининга. Блок общей биологии на сайте использует
только курированные отношения DrugBank именно по этой причине
(`serving/shared_biology.py`); отбор источника там закреплён тестом.

## Оговорки

Выборка, а не полное пространство из 1 452 660 пар: доверительный интервал
доли на {N_PAIRS} парах — около ±1,3 %.

Это не упрёк ChEMBL. База честно хранит то, что в ней хранится: результаты
анализов. Ошибка возникает, когда факт постановки анализа читают как факт
биологического отношения.
""", encoding="utf-8")

    print(f"ChEMBL: {100 * frac_ch:.1f}% пар с общей мишенью | DrugBank: {100 * frac_db:.1f}%")
    print(f"завышение в {inflation:.0f} раз | rho = {rho:+.3f} | подтверждено {100 * confirmed:.1f}%")
    print(f"записано: {OUT_CSV.relative_to(ROOT)}, {OUT_MD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
