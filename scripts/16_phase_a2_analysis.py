#!/usr/bin/env python3
"""
Phase A-2 analysis: the 2x3 table, the ablation ladder, the ensemble, calibration.

    python scripts/16_phase_a2_analysis.py

Reads `reports/phase_a2_results.csv` (the grid), `reports/phase_a2_ensemble.csv`
and `reports/phase_a2_predictions/*.npz` (the ensemble members), plus Phase A's
`reports/phase_a_results.csv` and `reports/phase_a_full_rf.csv` for the bar the
GNN has to clear. Writes `reports/phase_a2_summary.md`.

This script computes nothing new about the models - it only reads run outputs.
It is separate from the runner so that re-tabulating a result can never
accidentally re-fit one, and so a reader can check the tables against the raw
CSV without following training code.

WHAT THE TABLES ARE FOR
-----------------------
1. **Architecture x split.** `dual` minus `gine` on `random_pair` versus on
   `drug`/`scaffold`. Under a drug-level split the test drugs have no training
   edges, so whatever the network branch was contributing on `random_pair` has
   to go somewhere. How much goes is the number this project exists to report.
2. **The ablation ladder** on the honest cell: degree-only, full random forest,
   `gine`, `dual`, ensemble. Each rung adds one thing.
3. **Epoch-limit fraction.** Runs stopped by the budget rather than by patience
   were possibly still improving, so their scores are lower bounds. Addendum 2
   of the protocol commits to reporting this, whichever way it comes out.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd

from ddinet.eval.calibration import evaluate_calibration
from ddinet.eval.metrics import compute_binary_metrics, format_ci
from ddinet.eval.paired_stats import paired_compare

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
PREDICTIONS = REPORTS / "phase_a2_predictions"

SCHEMES = ("random_pair", "drug", "scaffold")
NEGATIVES = ("uniform", "degree_matched")
ARCHITECTURES = ("gine", "dual")
HONEST_CELL = ("drug", "degree_matched")

#: Equivalence margin for TOST, as in Phase A: 0.02 AUPRC. Chosen as the
#: smallest difference that would change a practical decision about which model
#: to deploy, and fixed before the comparison rather than after seeing it.
EQUIVALENCE_MARGIN = 0.02


def load(path: Path, what: str) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"Missing {path}. Run {what} first.")
    return pd.read_csv(path)


def pooled_view(results: pd.DataFrame) -> pd.DataFrame:
    return results.loc[results["test_view"] == "pooled"]


def cell_series(results: pd.DataFrame, scheme: str, negatives: str,
                architecture: str, metric: str = "auprc") -> pd.Series:
    """One value per seed for a single grid cell, indexed by seed."""
    sub = pooled_view(results)
    sub = sub[(sub["scheme"] == scheme) & (sub["negatives"] == negatives)
              & (sub["architecture"] == architecture)]
    if sub["seed"].duplicated().any():
        raise ValueError(f"Duplicate seeds in {scheme}/{negatives}/{architecture}")
    return sub.set_index("seed")[metric].sort_index()


def main_table(results: pd.DataFrame, out: list[str]) -> None:
    """Architecture x split x negative scheme, mean +/- 95% CI over seeds."""
    out.append("## 1. Основная таблица: архитектура x сплит x негативы\n")
    out.append("Pooled test AUPRC, mean +/- 95% ДИ (Student-t по сидам). "
               "Prevalence 0.5, поэтому 0.5 - это случайный классификатор.\n")
    for negatives in NEGATIVES:
        out.append(f"\n**Негативы: {negatives}**\n")
        out.append("| Архитектура | " + " | ".join(SCHEMES) + " |")
        out.append("|---|" + "---|" * len(SCHEMES))
        for architecture in ARCHITECTURES:
            cells = []
            for scheme in SCHEMES:
                series = cell_series(results, scheme, negatives, architecture)
                cells.append(format_ci(series.to_numpy()) if len(series) else "-")
            out.append(f"| `{architecture}` | " + " | ".join(cells) + " |")

        # The row this whole table exists for.
        out.append("")
        out.append("| Разница `dual` - `gine` | " + " | ".join(
            _paired_cell(results, scheme, negatives) for scheme in SCHEMES) + " |")
        out.append("|---|" + "---|" * len(SCHEMES))


def _paired_cell(results: pd.DataFrame, scheme: str, negatives: str) -> str:
    """Paired difference between architectures within a scheme, seed by seed.

    Paired, not two independent means: both architectures ran on the same split
    at the same seed, so the seed-to-seed variance - which Phase A found to be
    the dominant term - cancels. Comparing unpaired means here would hide a real
    difference behind variance that the design already controls for.
    """
    a = cell_series(results, scheme, negatives, "dual")
    b = cell_series(results, scheme, negatives, "gine")
    seeds = sorted(set(a.index) & set(b.index))
    if len(seeds) < 2:
        return "-"
    cmp = paired_compare(a.loc[seeds].to_numpy(), b.loc[seeds].to_numpy(),
                         name_a="dual", name_b="gine",
                         equivalence_margin=EQUIVALENCE_MARGIN)
    star = "*" if cmp.t_p_value < 0.05 else ""
    return f"{cmp.mean_difference:+.4f}{star} (p={cmp.t_p_value:.3f})"


def network_level_table(results: pd.DataFrame, out: list[str]) -> None:
    """How much of the network branch's advantage survives an honest split.

    This is the pre-registered expectation from protocol section 6, tested
    rather than asserted. Whichever way it comes out, it goes in as measured.
    """
    out.append("\n\n## 2. Сколько преимущества сетевого уровня переживает честный сплит\n")
    out.append("`dual` минус `gine`, парно по сидам. При drug- и scaffold-сплите "
               "у тестового препарата ноль рёбер в обучающем графе, поэтому "
               "сетевой уровень для него вырождается во вторую копию его "
               "собственных признаков (протокол, п. 7).\n")
    out.append("| Негативы | Сплит | dual - gine | 95% ДИ | p (парный t) | Эквивалентность |")
    out.append("|---|---|---|---|---|---|")
    for negatives in NEGATIVES:
        for scheme in SCHEMES:
            a = cell_series(results, scheme, negatives, "dual")
            b = cell_series(results, scheme, negatives, "gine")
            seeds = sorted(set(a.index) & set(b.index))
            if len(seeds) < 2:
                continue
            cmp = paired_compare(a.loc[seeds].to_numpy(), b.loc[seeds].to_numpy(),
                                 name_a="dual", name_b="gine",
                                 equivalence_margin=EQUIVALENCE_MARGIN)
            verdict = ("эквивалентны" if cmp.equivalent else
                       "не доказана" if cmp.tost_p_value is not None else "-")
            out.append(f"| {negatives} | {scheme} | {cmp.mean_difference:+.4f} | "
                       f"[{cmp.ci_low:+.4f}, {cmp.ci_high:+.4f}] | "
                       f"{cmp.t_p_value:.4f} | {verdict} |")
    out.append(f"\nМаржа эквивалентности {EQUIVALENCE_MARGIN} AUPRC, зафиксирована "
               "до сравнения. При n=5 минимально достижимое p критерия Уилкоксона "
               "равно 0.0625, поэтому основной тест - парный t.")


def ablation_table(results: pd.DataFrame, out: list[str]) -> None:
    """The ladder on the honest cell, with Phase A's rungs read from its CSVs."""
    scheme, negatives = HONEST_CELL
    out.append(f"\n\n## 3. Ablation на честной конфигурации ({scheme} + {negatives})\n")
    out.append("Каждая ступень добавляет ровно одну вещь. Числа Фазы A взяты из "
               "её CSV без перезапуска.\n")
    out.append("| Модель | Что добавляет | Pooled test AUPRC |")
    out.append("|---|---|---|")

    rungs: list[tuple[str, str, np.ndarray | None]] = []
    phase_a = REPORTS / "phase_a_results.csv"
    if phase_a.exists():
        a = pd.read_csv(phase_a)
        a = a[(a["scheme"] == scheme) & (a["negatives"] == negatives)
              & (a["test_view"] == "pooled")]
        deg = a[a["model"] == "degree_only"]["auprc"].to_numpy()
        rungs.append(("degree-only", "ничего, кроме топологии обучающего графа", deg))
    full_rf = REPORTS / "phase_a_full_rf.csv"
    if full_rf.exists():
        f = pd.read_csv(full_rf)
        f = f[(f["scheme"] == scheme) & (f["negatives"] == negatives)]
        if "test_view" in f.columns:
            f = f[f["test_view"] == "pooled"]
        rungs.append(("random forest [symmetric], без ограничения глубины",
                      "химию через ECFP4, без обучаемого представления",
                      f["auprc"].to_numpy()))
    for architecture, adds in (("gine", "обучаемое молекулярное представление"),
                               ("dual", "сетевой уровень поверх молекулярного")):
        series = cell_series(results, scheme, negatives, architecture)
        rungs.append((f"`{architecture}`", adds, series.to_numpy()))

    ens = REPORTS / "phase_a2_ensemble.csv"
    if ens.exists():
        e = pd.read_csv(ens)
        e = e[(e["test_view"] == "pooled") & (e["architecture"] == "dual")]
        rungs.append(("`dual`, члены ансамбля (фиксированный сплит)",
                      "разброс от инициализации и негативов при одном тесте",
                      e["auprc"].to_numpy()))

    for name, adds, values in rungs:
        cell = format_ci(values) if values is not None and len(values) else "-"
        out.append(f"| {name} | {adds} | {cell} |")

    out.append("\nВНИМАНИЕ при чтении последней строки: члены ансамбля обучены на "
               "ОДНОМ фиксированном разбиении, поэтому их разброс не сравним с "
               "остальными строками, где сид меняет и разбиение тоже. Их ДИ уже "
               "по построению, а не потому, что модель устойчивее.")


def ensemble_section(out: list[str]) -> None:
    """Average member probabilities, then score and calibrate the average.

    Averaging is done on probabilities, not on metrics: the mean of five AUPRCs
    is not the AUPRC of the mean prediction, and only the latter is an ensemble.
    """
    out.append("\n\n## 4. Deep ensemble\n")
    if not PREDICTIONS.exists():
        out.append("_Предсказания членов ансамбля не найдены - запустите "
                   "`--stage ensemble`._")
        return

    out.append("Пять моделей на ОДНОМ разбиении (drug + degree_matched, split seed 0), "
               "различаются инициализацией и выборкой негативов. Усредняются "
               "вероятности, а не метрики: среднее пяти AUPRC - это не AUPRC "
               "среднего предсказания, и ансамблем является только второе.\n")
    out.append("| Модель | Test AUPRC | Test AUC-ROC | Brier |")
    out.append("|---|---|---|---|")

    calibration_rows = []
    for architecture in ARCHITECTURES:
        files = sorted(PREDICTIONS.glob(f"{architecture}_member*.npz"))
        if not files:
            continue
        members = [np.load(f) for f in files]
        y_test = members[0]["y_test"]
        y_val = members[0]["y_val"]
        if not all(np.array_equal(m["y_test"], y_test) for m in members):
            out.append(f"\n**{architecture}: члены оценены на РАЗНЫХ тестовых "
                       "множествах - усреднение невозможно, ансамбль пропущен.**")
            continue
        for f, m in zip(files, members):
            met = compute_binary_metrics(y_test, m["s_test"], threshold=float(m["threshold"]))
            out.append(f"| {f.stem} | {met.auprc:.4f} | {met.auc_roc:.4f} | {met.brier:.4f} |")

        s_test = np.mean([m["s_test"] for m in members], axis=0)
        s_val = np.mean([m["s_val"] for m in members], axis=0)
        met = compute_binary_metrics(y_test, s_test,
                                     threshold=float(np.mean([m["threshold"] for m in members])))
        out.append(f"| **{architecture} ensemble ({len(files)})** | **{met.auprc:.4f}** | "
                   f"{met.auc_roc:.4f} | {met.brier:.4f} |")

        # Calibration by the Phase A protocol: temperature fitted on validation,
        # applied unchanged to test.
        for label, sv, st in ((f"{architecture} single (member 0)",
                               members[0]["s_val"], members[0]["s_test"]),
                              (f"{architecture} ensemble", s_val, s_test)):
            report, _, _ = evaluate_calibration(label, y_val, sv, y_test, st)
            calibration_rows.append(report)

    if calibration_rows:
        out.append("\n### Калибровка\n")
        out.append("Температура подобрана на validation и применена к test без "
                   "изменений. Стрелка - до -> после масштабирования.\n")
        out.append("| Модель | Brier | ECE (квантильные бины) | ECE (равномерные) | T |")
        out.append("|---|---|---|---|---|")
        for r in calibration_rows:
            out.append(f"| {r.model} | {r.brier:.4f} -> {r.brier_scaled:.4f} | "
                       f"{r.ece_quantile:.4f} -> {r.ece_quantile_scaled:.4f} | "
                       f"{r.ece_uniform:.4f} -> {r.ece_uniform_scaled:.4f} | "
                       f"{r.temperature:.3f} |")
        out.append("\nКак читать: Brier, упавший до ровно 0.250 при prevalence 0.5, "
                   "означает не откалиброванную модель, а константный предсказатель "
                   "0.5 - именно это случилось с degree-only в Фазе A. Смотрите на "
                   "Brier и ECE вместе, а не на ECE отдельно.")


def budget_section(results: pd.DataFrame, out: list[str]) -> None:
    """Addendum 2's commitment, honoured whichever way the number comes out."""
    out.append("\n\n## 5. Бюджет эпох\n")
    runs = pooled_view(results)
    capped = (runs["stopped_by"] == "epoch_limit")
    frac = float(capped.mean()) if len(runs) else float("nan")
    out.append(f"Прогонов, остановленных лимитом эпох, а не patience: "
               f"**{capped.sum()} из {len(runs)} ({frac:.0%})**.\n")
    out.append(f"Медиана пройденных эпох: {runs['epochs_run'].median():.0f}, "
               f"медиана лучшей эпохи: {runs['best_epoch'].median():.0f}.\n")
    if frac > 0.25:
        out.append("> Эта доля велика. Значит, часть моделей на момент остановки "
                   "ещё улучшалась, и их числа - нижняя оценка, а не сошедшийся "
                   "результат. Это ограничение работы, а не вывод о моделях.")
    else:
        out.append("Доля мала, поэтому лимит эпох не является ограничивающим "
                   "фактором для большинства ячеек.")


def bar_section(results: pd.DataFrame, out: list[str]) -> None:
    """Did the GNN clear the pre-registered bar? Stated plainly, either way."""
    scheme, negatives = HONEST_CELL
    out.append("\n\n## 6. Планка, зафиксированная до запуска\n")
    bars = {"random_pair/uniform": (("random_pair", "uniform"), 0.915),
            "drug/degree_matched": ((scheme, negatives), 0.763)}
    out.append("| Конфигурация | Планка (полный RF, Фаза A) | Лучший GNN | Итог |")
    out.append("|---|---|---|---|")
    for label, ((sch, negs), bar) in bars.items():
        best_name, best_mean = None, -np.inf
        for architecture in ARCHITECTURES:
            series = cell_series(results, sch, negs, architecture)
            if not len(series):
                continue
            m = float(series.mean())
            if m > best_mean:
                best_name, best_mean = architecture, m
        if best_name is None:
            continue
        verdict = "GNN выше" if best_mean > bar else "GNN ниже - принято как результат"
        out.append(f"| {label} | {bar:.3f} | `{best_name}` {best_mean:.3f} | {verdict} |")
    out.append("\nПравило из п. 3 протокола: если GNN не обгоняет полный Random "
               "Forest, это результат работы, а не повод менять архитектуру. "
               "Правило записано до получения первого числа.")


def main() -> int:
    results = load(REPORTS / "phase_a2_results.csv", "`--stage grid`")
    out: list[str] = ["# Фаза A-2: графовые сети при честной оценке\n"]
    out.append("Сгенерировано `scripts/16_phase_a2_analysis.py` из выходов "
               "прогонов. Протокол зафиксирован в `docs/PHASE_A2_PROTOCOL.md` "
               "ДО первого прогона.\n")
    hyper = REPORTS / "phase_a2_hyperparameters.json"
    if hyper.exists():
        out.append(f"Гиперпараметры (подобраны на validation, "
                   f"{HONEST_CELL[0]} + {HONEST_CELL[1]}): "
                   f"`{hyper.read_text().strip()}`\n")

    main_table(results, out)
    network_level_table(results, out)
    ablation_table(results, out)
    ensemble_section(out)
    budget_section(results, out)
    bar_section(results, out)

    path = REPORTS / "phase_a2_summary.md"
    path.write_text("\n".join(out) + "\n")
    print("\n".join(out))
    print(f"\nWrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
