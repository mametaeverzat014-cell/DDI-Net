#!/usr/bin/env python3
"""
Analysis of the adversarial degree-debiasing experiment.

This script implements the outcome table of docs/DEBIAS_PROTOCOL.md section 4
literally. It exists so that the verdict is READ OFF a rule fixed before the
experiment ran, rather than composed after seeing the numbers.

THE RULE, RESTATED
------------------
Three numbers decide, and they must be read together:

    r2_probe        cross-validated R^2 of an INDEPENDENT linear probe from the
                    network embedding onto log1p(training degree). Originally
                    0.885-0.954 (scripts/23).
    auprc           per test view, never pooled alone.
    embedding_var   mean per-dimension variance of the embedding.

    collapse        embedding_var < COLLAPSE_FRACTION of the same seed's `base`
    R^2 fell        r2_probe < R2_SUPPRESSED

    | R^2      | AUPRC   | variance | verdict                                  |
    |----------|---------|----------|------------------------------------------|
    | fell     | holds   | holds    | model did not rely on degree             |
    | fell     | falls   | holds    | model relied on degree, and this is how  |
    |          |         |          | much of its performance that was worth   |
    | fell     | any     | COLLAPSE | NOT debiasing - result does not count    |
    | held     | any     | any      | adversary failed - report the failure    |

WHY `adv0` AND NOT `base` IS THE COMPARISON FOR THE VERDICT
-------------------------------------------------------------
`adv0` has the adversary head built and trained but lambda = 0. It therefore
carries the same parameters, the same optimiser state and the same extra loss
term as `adv1`, and differs from it in exactly one float. `base` differs in
several things at once. So:

    adv1 vs adv0   isolates the reversal          <- the verdict rests on this
    adv0 vs base   the cost of the head alone     <- reported, must be ~0
    adv1 vs base   the whole change end to end    <- reported for completeness

If `adv0` differs materially from `base`, the control is not doing its job and
that must be said before any verdict is drawn.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ddinet.eval.paired_stats import paired_compare  # noqa: E402

REPORTS = ROOT / "reports"
RESULTS = REPORTS / "debias_results.csv"
OUT = REPORTS / "debias_summary.md"

#: Pre-registered thresholds (DEBIAS_PROTOCOL.md section 4). Not tunable here:
#: changing them after seeing results is exactly what pre-registration forbids.
R2_SUPPRESSED = 0.30
COLLAPSE_FRACTION = 0.10
EQUIVALENCE_MARGIN = 0.02
#: The originally measured range, for context in the report.
R2_BASELINE_RANGE = (0.885, 0.954)


def series(df: pd.DataFrame, scheme: str, negatives: str, condition: str,
           column: str, view: str = "pooled") -> pd.Series:
    sub = df[(df["scheme"] == scheme) & (df["negatives"] == negatives)
             & (df["condition"] == condition) & (df["test_view"] == view)]
    if sub["seed"].duplicated().any():
        raise ValueError(f"Duplicate seeds in {scheme}/{negatives}/{condition}")
    return sub.set_index("seed")[column].sort_index()


def _compare(a: pd.Series, b: pd.Series, name_a: str, name_b: str):
    seeds = sorted(set(a.index) & set(b.index))
    if len(seeds) < 2:
        return None, seeds
    return paired_compare(a.loc[seeds].to_numpy(), b.loc[seeds].to_numpy(),
                          name_a=name_a, name_b=name_b,
                          equivalence_margin=EQUIVALENCE_MARGIN), seeds


def control_check(df: pd.DataFrame, out: list[str]) -> None:
    """adv0 must behave like base. If it does not, nothing below is readable."""
    out.append("\n## 1. Проверка контроля: `adv0` против `base`\n")
    out.append("`adv0` строит голову и обучает её, но lambda = 0. Он обязан "
               "совпадать с `base` с точностью до шума. Если не совпадает, "
               "контроль не работает и вердикт ниже недействителен.\n")
    out.append("| Сплит | Негативы | adv0 - base | 95% ДИ | p | Эквивалентность |")
    out.append("|---|---|---|---|---|---|")
    for scheme, negatives in cells(df):
        cmp, seeds = _compare(series(df, scheme, negatives, "adv0", "auprc"),
                              series(df, scheme, negatives, "base", "auprc"),
                              "adv0", "base")
        if cmp is None:
            continue
        verdict = "эквивалентны" if cmp.equivalent else "НЕ доказана"
        out.append(f"| {scheme} | {negatives} | {cmp.mean_difference:+.4f} | "
                   f"[{cmp.ci_low:+.4f}, {cmp.ci_high:+.4f}] | "
                   f"{cmp.t_p_value:.4f} | {verdict} |")


def collapse_check(df: pd.DataFrame, out: list[str]) -> dict:
    """Did the encoder win by collapsing? Returns {(cell): collapsed?}."""
    out.append("\n\n## 2. Проверка на коллапс\n")
    out.append(f"Кодировщик может победить голову дёшево, схлопнувшись к "
               f"константе. Порог зафиксирован до эксперимента: дисперсия "
               f"эмбеддинга ниже {COLLAPSE_FRACTION:.0%} от значения `base` на "
               f"том же сиде считается коллапсом, и такой прогон НЕ "
               f"засчитывается как подавление.\n")
    out.append("| Сплит | Негативы | var(base) | var(adv1) | доля | вердикт |")
    out.append("|---|---|---|---|---|---|")
    collapsed = {}
    for scheme, negatives in cells(df):
        b = series(df, scheme, negatives, "base", "embedding_var")
        a = series(df, scheme, negatives, "adv1", "embedding_var")
        seeds = sorted(set(a.index) & set(b.index))
        if not seeds:
            continue
        ratio = (a.loc[seeds] / b.loc[seeds].replace(0, np.nan))
        worst = float(ratio.min())
        bad = worst < COLLAPSE_FRACTION
        collapsed[(scheme, negatives)] = bad
        out.append(f"| {scheme} | {negatives} | {b.loc[seeds].mean():.4f} | "
                   f"{a.loc[seeds].mean():.4f} | {worst:.3f} | "
                   f"{'КОЛЛАПС' if bad else 'нет'} |")
    return collapsed


def suppression_check(df: pd.DataFrame, out: list[str]) -> dict:
    """Did the probe's R^2 actually fall? Returns {(cell): suppressed?}."""
    out.append("\n\n## 3. Упала ли восстановимость степени\n")
    out.append(f"R^2 независимого зонда, не потери самой адверсариальной "
               f"головы: её ломают намеренно, её потери ничего не измеряют. "
               f"Исходно измерено {R2_BASELINE_RANGE[0]}-{R2_BASELINE_RANGE[1]} "
               f"(scripts/23). Порог «упала» зафиксирован до эксперимента: "
               f"R^2 < {R2_SUPPRESSED}.\n")
    out.append("| Сплит | Негативы | R2 base | R2 adv0 | R2 adv1 | вердикт |")
    out.append("|---|---|---|---|---|---|")
    suppressed = {}
    for scheme, negatives in cells(df):
        vals = {c: series(df, scheme, negatives, c, "r2_probe") for c in
                ("base", "adv0", "adv1")}
        if vals["adv1"].empty:
            continue
        r2 = float(vals["adv1"].mean())
        ok = r2 < R2_SUPPRESSED
        suppressed[(scheme, negatives)] = ok
        out.append(f"| {scheme} | {negatives} | {vals['base'].mean():+.4f} | "
                   f"{vals['adv0'].mean():+.4f} | {r2:+.4f} | "
                   f"{'упала' if ok else 'НЕ упала'} |")
    return suppressed


def cost_table(df: pd.DataFrame, out: list[str]) -> dict:
    """What did suppression cost in AUPRC, per test view? Returns the verdicts."""
    out.append("\n\n## 4. Цена подавления в AUPRC\n")
    out.append("`adv1` минус `adv0`, парно по сидам, по каждому бакету "
               "отдельно. Агрегат pooled без разбивки не приводится: он на "
               "91 % состоит из S2 и скрывает S3.\n")
    out.append("| Сплит | Негативы | Бакет | adv1 - adv0 | 95% ДИ | p |")
    out.append("|---|---|---|---|---|---|")
    effects = {}
    for scheme, negatives in cells(df):
        views = sorted(df[(df["scheme"] == scheme)
                          & (df["negatives"] == negatives)]["test_view"].unique())
        for view in views:
            cmp, _ = _compare(series(df, scheme, negatives, "adv1", "auprc", view),
                              series(df, scheme, negatives, "adv0", "auprc", view),
                              "adv1", "adv0")
            if cmp is None:
                continue
            effects[(scheme, negatives, view)] = cmp
            out.append(f"| {scheme} | {negatives} | {view} | "
                       f"{cmp.mean_difference:+.4f} | [{cmp.ci_low:+.4f}, "
                       f"{cmp.ci_high:+.4f}] | {cmp.t_p_value:.4f} |")
    return effects


def verdicts(collapsed: dict, suppressed: dict, effects: dict,
             out: list[str]) -> None:
    """Read the pre-registered outcome table. No new judgement enters here."""
    out.append("\n\n## 5. Вердикт по пререгистрированной таблице исходов\n")
    out.append("| Сплит | Негативы | Вердикт |")
    out.append("|---|---|---|")
    for cell in sorted(set(collapsed) | set(suppressed)):
        scheme, negatives = cell
        if collapsed.get(cell):
            v = ("**КОЛЛАПС.** Кодировщик схлопнулся, а не подавил степень. "
                 "AUPRC этого прогона НЕ сообщается как «после подавления».")
        elif not suppressed.get(cell):
            v = ("**Адверсарий не сработал** - R^2 зонда не опустился ниже "
                 f"{R2_SUPPRESSED}. Сообщается как неудача метода; AUPRC "
                 "нельзя подавать так, будто подавление произошло.")
        else:
            pooled = effects.get((scheme, negatives, "pooled"))
            if pooled is None:
                v = "R^2 упал, коллапса нет; данных по AUPRC не хватает."
            elif pooled.equivalent:
                v = ("**Модель не опиралась на степень для предсказаний.** "
                     "R^2 упал, качество удержалось (TOST в пределах "
                     f"{EQUIVALENCE_MARGIN}). Shortcut присутствовал в "
                     "эмбеддинге, но не был несущим.")
            elif pooled.mean_difference < 0 and pooled.t_p_value < 0.05:
                v = (f"**Модель опиралась на степень.** Подавление стоило "
                     f"{pooled.mean_difference:+.4f} AUPRC (p="
                     f"{pooled.t_p_value:.4f}) - это и есть измеренная доля "
                     "качества, которая держалась на степени.")
            else:
                v = (f"R^2 упал, коллапса нет, изменение AUPRC "
                     f"{pooled.mean_difference:+.4f} не значимо и не "
                     "признано эквивалентным - мощности не хватает, "
                     "заявлять ни то, ни другое нельзя.")
        out.append(f"| {scheme} | {negatives} | {v} |")

    out.append("\n**Чего этот эксперимент не показывает**, независимо от "
               "исхода: клинической применимости, причинности, устранения "
               "позитивно-немеченности. Подавление степени не переносится "
               "автоматически на смещение биологического покрытия - оно "
               "коррелирует со степенью (r = 0.392), но не тождественно ей.")


def cells(df: pd.DataFrame) -> list[tuple[str, str]]:
    return sorted({(r.scheme, r.negatives) for r in df.itertuples()})


def main() -> int:
    if not RESULTS.exists():
        raise SystemExit(
            f"{RESULTS} is missing. Run scripts/25_debias_experiment.py first "
            "(it refuses to start while the Phase A-2 grid is running)."
        )
    df = pd.read_csv(RESULTS)
    out = ["# Адверсариальное подавление степени: результаты\n",
           "Сгенерировано `scripts/27_debias_analysis.py`. Пороги и таблица "
           "исходов зафиксированы в `docs/DEBIAS_PROTOCOL.md` ДО прогонов; "
           "этот скрипт их только применяет.\n"]
    n_seeds = df["seed"].nunique()
    out.append(f"Сидов в данных: {n_seeds}. "
               + ("" if n_seeds >= 5 else
                  "**Меньше пяти - результаты предварительные.**") + "\n")

    control_check(df, out)
    collapsed = collapse_check(df, out)
    suppressed = suppression_check(df, out)
    effects = cost_table(df, out)
    verdicts(collapsed, suppressed, effects, out)

    OUT.write_text("\n".join(out) + "\n")
    print("\n".join(out))
    print(f"\nWrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
