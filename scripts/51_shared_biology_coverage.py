#!/usr/bin/env python3
"""Покрытие блока «общая биология»: как часто он вообще что-то показывает.

ЗАЧЕМ. На странице «Анализ» есть блок, который показывает, какие белки у пары
препаратов общие по курированным отношениям DrugBank. Источник выбран
осознанно: перекрытие по результатам скрининга ChEMBL измеряет объём
скрининга, а не биологию (scripts/50, reports/chembl_panel_artifact.md).

Цена этого выбора — покрытие. DrugBank хранит на порядок меньше рёбер, поэтому
у большинства пар блок оказывается пустым. Это надо знать числом, а не на
глаз: пустой блок легко прочитать как «взаимодействия нет», тогда как на деле
это «в справочнике нет записи». Формулировка пустого состояния на сайте
опирается на измеренную здесь долю.

ЧТО СЧИТАЕТСЯ.
  * сколько препаратов вселенной не имеют ни одной аннотации DrugBank ни в
    одной из четырёх ролей — у таких блок пуст всегда, с любым партнёром;
  * доля пар с полностью пустым блоком;
  * доля пар, делящих хотя бы один белок, по каждой роли отдельно.

Выборка, а не полное пространство: 1 452 660 пар считались бы долго, а
доверительный интервал доли на 6000 парах — около ±1,3 %. Сид и размер
выборки те же, что в scripts/50, чтобы числа двух отчётов были сопоставимы.

Замороженные артефакты не читаются и не меняются: это свойство источника
данных, к обученной модели отношения не имеющее.
"""

from __future__ import annotations

import random
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EDGES = ROOT / "data" / "mechanism_v1" / "drug_protein_edges.parquet"
DRUGS = ROOT / "data" / "mechanism_v1" / "drugs.parquet"
OUT_CSV = ROOT / "reports" / "shared_biology_coverage.csv"
OUT_MD = ROOT / "reports" / "shared_biology_coverage.md"

# Те же четыре роли и тот же источник, что использует serving/shared_biology.py.
RELATIONS: tuple[str, ...] = ("target", "enzyme", "transporter", "carrier")
DRUGBANK = "DrugBank_v5.1"

SEED = 0
N_PAIRS = 6000

# Человекочитаемые названия ролей — те же, что показывает интерфейс.
RU = {
    "target": "мишени",
    "enzyme": "ферменты",
    "transporter": "переносчики",
    "carrier": "транспортные белки",
}


def main() -> int:
    edges = pd.read_parquet(EDGES).drop_duplicates(
        ["drugbank_id", "uniprot_id", "relation_type", "evidence_source"]
    )
    db = edges[(edges.evidence_source == DRUGBANK)
               & (edges.relation_type.isin(RELATIONS))]
    drugs = pd.read_parquet(DRUGS).drugbank_id.tolist()
    n_drugs = len(drugs)

    # Препараты без единой записи: у них блок пуст при любом партнёре, поэтому
    # они задают нижнюю границу пустых пар независимо от выборки.
    annotated = set(db.drugbank_id)
    n_unannotated = sum(1 for d in drugs if d not in annotated)

    # Множества белков отдельно по каждой роли: сравнивать надо сопоставимые
    # роли, а не «любой общий белок» — фермент и мишень значат разное.
    by_relation = {
        rel: {d: set(g.uniprot_id)
              for d, g in db[db.relation_type == rel].groupby("drugbank_id")}
        for rel in RELATIONS
    }

    rng = random.Random(SEED)
    pairs: set[tuple[str, str]] = set()
    while len(pairs) < N_PAIRS:
        a, b = rng.sample(drugs, 2)
        pairs.add((a, b) if a < b else (b, a))

    shares = {rel: 0 for rel in RELATIONS}
    empty = 0
    for a, b in pairs:
        hit = False
        for rel in RELATIONS:
            sets = by_relation[rel]
            if sets.get(a, frozenset()) & sets.get(b, frozenset()):
                shares[rel] += 1
                hit = True
        if not hit:
            empty += 1

    rows = [
        ("drugs_total", n_drugs),
        ("drugs_without_any_drugbank_annotation", n_unannotated),
        ("pairs_sampled", N_PAIRS),
        ("seed", SEED),
        ("frac_pairs_with_empty_block", empty / N_PAIRS),
    ]
    rows += [(f"frac_pairs_sharing_{rel}", shares[rel] / N_PAIRS)
             for rel in RELATIONS]

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=["metric", "value"]).to_csv(OUT_CSV, index=False)

    pct = lambda x: f"{x * 100:.1f}".replace(".", ",")
    table = "\n".join(
        f"| {RU[rel]} | {pct(shares[rel] / N_PAIRS)} % |" for rel in RELATIONS
    )
    OUT_MD.write_text(f"""# Покрытие блока «общая биология»

Считается `scripts/51_shared_biology_coverage.py`. Источник — только
курированные отношения DrugBank ({DRUGBANK}), четыре роли:
{", ".join(RU[r] for r in RELATIONS)}. Выборка {N_PAIRS} случайных
неупорядоченных пар, сид {SEED}.

**У {pct(empty / N_PAIRS)} % пар блок пуст** — ни одного общего белка ни в одной
из четырёх ролей.

**{n_unannotated} препаратов из {n_drugs}** не имеют ни одной аннотации DrugBank
нужного типа. У них блок пуст с любым партнёром, независимо от выборки.

Доля пар, делящих хотя бы один белок, по ролям:

| роль | доля пар |
|---|---|
{table}

## Почему покрытие такое низкое — и почему это принято

Перекрытие по результатам скрининга ChEMBL дало бы 54,7 % вместо 3,0 %, но
измеряло бы объём скрининга, а не биологию: `reports/chembl_panel_artifact.md`.
Низкое покрытие — цена за то, что показанное перекрытие означает то, что
написано.

## Следствие для формулировок

Пустой блок — это **отсутствие записи в справочнике**, а не заключение об
отсутствии взаимодействия и тем более не заключение о безопасности. Так он и
подписан в интерфейсе (`web/src/components/sharedBiologyContent.ts`), и эта
формулировка закреплена тестом.

## Оговорка

Выборка, а не полное пространство из 1 452 660 пар: доверительный интервал доли
на {N_PAIRS} парах — около ±1,3 %.
""", encoding="utf-8")

    print(f"пустой блок {pct(empty / N_PAIRS)} % | без аннотаций "
          f"{n_unannotated}/{n_drugs} | " +
          " ".join(f"{rel} {pct(shares[rel] / N_PAIRS)}%" for rel in RELATIONS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
