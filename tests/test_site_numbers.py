"""Каждое число на site/index.html обязано совпадать со своим файлом-источником.

ЗАЧЕМ ЭТОТ ФАЙЛ. Правило проекта для сайта РНПК: число либо взято из наших
измерений (и тогда рядом стоит ссылка на файл в reports/ или paper/tables/),
либо из опубликованной литературы (и тогда ссылка на статью). Третьего варианта
нет. До этого файла правило держалось только на внимательности: при первой
вёрстке ширины двух столбиков из девяти разошлись со значениями, а в лестнице
абляций на сайте оказались показаны две конфигурации из четырёх, которые
превосходят пререгистрированную, — обе ошибки нашлись ручной сверкой, то есть
случайно.

Тест дешёвый и намеренно тупой: он берёт числа из замороженных CSV, а не
пересчитывает их, и требует, чтобы на странице стояла строка с тем же
округлением. Он ломается, когда меняют число на сайте, не тронув источник, —
ровно тот случай, который правило и запрещает.

Зависимостей, кроме стандартной библиотеки, нет: файл должен собираться в любом
окружении, включая слим-образ без pandas.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site" / "index.html"

pytestmark = pytest.mark.skipif(not SITE.exists(), reason="site/ не собран")


def _html() -> str:
    # &nbsp; в разметке и U+00A0 в исходнике — одно и то же для читателя,
    # поэтому сравниваем после разворачивания сущности.
    return SITE.read_text(encoding="utf-8").replace("&nbsp;", "\u00a0")


def _rows(rel: str) -> list[dict]:
    with (ROOT / rel).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _ru(value: float, digits: int) -> str:
    """Русское оформление числа: десятичная запятая, как на странице."""
    return f"{value:.{digits}f}".replace(".", ",")


def _assert_on_page(needle: str, source: str) -> None:
    assert needle in _html(), (
        f"на site/index.html нет строки {needle!r}, "
        f"хотя {source} даёт именно это значение"
    )


# ── лестница абляций ────────────────────────────────────────────────────────
# Секция «Отчёт против себя». Здесь важна не только точность каждого числа, но и
# полнота: пропуск строки превратил бы «основная модель — самая слабая из
# четырёх» в более лестное «две конфигурации оказались лучше».

ABLATION = "paper/tables/table5_ablation_ladder.csv"


# Ярлык на сайте написан по-русски и подробнее, чем ключ в CSV, поэтому
# сверка идёт по признаку, который обязан в ярлыке присутствовать. Проверять
# наличие числа «где-нибудь на странице» недостаточно: 0,812 встречается в трёх
# разных местах, и подмена его в таблице такую проверку проходит — именно так
# первая версия этого теста и пропустила мутацию.
LADDER_MARKS = {
    "M0": "M0",
    "M1": "M1",
    "M2": "M2",
    "M3": "M3",
    "M4 (primary)": "пререгистрирована",
    "M4 SUM (CONTROL C)": "CONTROL C",
    "M4 shuffled (CONTROL F)": "CONTROL F",
}


def _ladder_rows_on_page() -> list[tuple[str, list[str]]]:
    """Строки таблицы абляций со страницы: (ярлык, числа в порядке столбцов)."""
    html = _html()
    table = next(
        t for t in re.findall(r"<table>.*?</table>", html, re.S)
        if "Конфигурация" in t
    )
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S):
        cells = [re.sub(r"<.*?>", "", c).strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if cells:
            out.append((cells[0], cells[1:]))
    return out


def test_ablation_ladder_values_match_the_frozen_table() -> None:
    """Каждое число сверяется внутри своей строки, а не «где-то на странице»."""
    page = _ladder_rows_on_page()
    frozen = _rows(ABLATION)
    assert len(page) == len(frozen), (
        f"на сайте {len(page)} строк лестницы, в {ABLATION} — {len(frozen)}; "
        "неполная лестница делает результат выгоднее, чем он есть"
    )
    for (label, values), row in zip(page, frozen):
        mark = LADDER_MARKS[row["variant"]]
        assert mark in label, (
            f"строка {label!r} не соответствует конфигурации {row['variant']}: "
            "порядок строк на сайте разошёлся с порядком в файле"
        )
        expected = [
            f"{_ru(float(row['pooled_auprc_mean']), 3)} ± "
            f"{_ru(float(row['pooled_auprc_std']), 3)}",
            f"{_ru(float(row['s3_auprc_mean']), 3)} ± "
            f"{_ru(float(row['s3_auprc_std']), 3)}",
        ]
        assert values == expected, (
            f"строка {row['variant']}: на сайте {values}, "
            f"а {ABLATION} даёт {expected}"
        )


def test_every_ablation_variant_is_shown() -> None:
    """Ни одну ступень нельзя убрать со страницы: именно полнота ряда
    показывает, что пререгистрированная конфигурация — не лучшая."""
    labels = [label for label, _ in _ladder_rows_on_page()]
    for row in _rows(ABLATION):
        mark = LADDER_MARKS[row["variant"]]
        assert any(mark in label for label in labels), (
            f"конфигурация {row['variant']} не показана на сайте — "
            "неполная лестница делает результат выгоднее, чем он есть"
        )


def test_primary_model_is_not_presented_as_the_best() -> None:
    """Страница обязана оставлять пререгистрированную M4 отмеченной как
    основную, а не как лучшую: лучших по числам четыре, и она не из них."""
    table = {r["variant"]: float(r["pooled_auprc_mean"]) for r in _rows(ABLATION)}
    primary = table["M4 (primary)"]
    better = [v for v, x in table.items() if x > primary]
    assert len(better) == 4, (
        f"источник изменился: лучше основной теперь {len(better)} конфигураций "
        f"({better}), а текст на сайте говорит о четырёх ступенях биологии"
    )
    assert "самая слабая из четырёх ступеней" in _html()


# ── артефакт панелей ChEMBL ─────────────────────────────────────────────────

CHEMBL = "reports/chembl_panel_artifact.csv"


def _chembl() -> dict[str, float]:
    return {r["metric"]: float(r["value"]) for r in _rows(CHEMBL)}


def test_chembl_shares_match_the_measurement() -> None:
    m = _chembl()
    _assert_on_page(_ru(m["frac_pairs_sharing_target_chembl"] * 100, 1),
                    f"{CHEMBL}:frac_pairs_sharing_target_chembl")
    _assert_on_page(_ru(m["frac_pairs_sharing_target_drugbank"] * 100, 1),
                    f"{CHEMBL}:frac_pairs_sharing_target_drugbank")
    _assert_on_page(_ru(m["frac_chembl_overlaps_confirmed_by_drugbank"] * 100, 1),
                    f"{CHEMBL}:frac_chembl_overlaps_confirmed_by_drugbank")
    _assert_on_page(_ru(m["spearman_shared_chembl_vs_min_annotation_count"], 3),
                    f"{CHEMBL}:spearman")


def test_the_inflation_factor_is_the_ratio_it_claims_to_be() -> None:
    m = _chembl()
    ratio = (m["frac_pairs_sharing_target_chembl"]
             / m["frac_pairs_sharing_target_drugbank"])
    shown = re.search(r'<span class="n">(\d+)&times;</span>|<span class="n">(\d+)×</span>',
                      _html())
    assert shown, "на странице нет числа завышения вида «18×»"
    claimed = int(shown.group(1) or shown.group(2))
    assert abs(claimed - ratio) < 1.0, (
        f"сайт заявляет завышение в {claimed}×, файл даёт {ratio:.2f}×"
    )


# ── доля пар со знакомыми препаратами ───────────────────────────────────────

SPLITS = "reports/split_comparison.csv"


def test_leaky_split_counts_match_the_split_report() -> None:
    row = next(r for r in _rows(SPLITS)
               if r["scheme"] == "random_pair" and r["seed"] == "0")
    unseen = int(float(row["test_S2"])) + int(float(row["test_S3"]))
    total = int(float(row["test_pairs"]))
    _assert_on_page(f"{unseen} <span class=\"muted\">из</span> "
                    f"{total:,}".replace(",", " "),
                    f"{SPLITS}: S2+S3 из test_pairs")
    _assert_on_page(_ru(float(row["test_S1_fraction"]) * 100, 2),
                    f"{SPLITS}:test_S1_fraction")


# ── покрытие блока общей биологии ───────────────────────────────────────────
# Эти два числа на сайте изначально были поставлены по памяти («примерно 71 %»),
# и измерение дало 72,9 %. Поэтому они тоже под сверкой.

COVERAGE = "reports/shared_biology_coverage.csv"


def test_shared_biology_coverage_matches_the_measurement() -> None:
    m = {r["metric"]: float(r["value"]) for r in _rows(COVERAGE)}
    _assert_on_page(_ru(m["frac_pairs_with_empty_block"] * 100, 1),
                    f"{COVERAGE}:frac_pairs_with_empty_block")
    for key in ("drugs_without_any_drugbank_annotation", "drugs_total"):
        shown = f"{int(m[key]):,}".replace(",", "\u00a0")
        assert shown in _html(), (
            f"на сайте нет числа {shown}, хотя {COVERAGE}:{key} даёт именно его"
        )


# ── ярлык шага, а не только число ───────────────────────────────────────────

def test_no_number_is_shown_without_a_source_line() -> None:
    """У каждого блока .stat должна быть строка источника: правило сайта не
    допускает числа «просто так»."""
    html = _html()
    stats = re.findall(r'<div class="stat">(.*?)</div>\s*(?=<div|</div>)',
                       html, re.S)
    assert stats, "разметка .stat изменилась — тест надо переписать под неё"
    for block in stats:
        assert 'class="src"' in block, (
            "блок с числом без ссылки на источник:\n"
            + re.sub(r"\s+", " ", block)[:200]
        )
