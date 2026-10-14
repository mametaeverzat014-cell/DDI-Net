"""What the BIO-GINE score means for *this* pair, using only measured facts.

The earlier API returned one number per pair. Whether that number deserves any
weight depends on things the number does not show:

* REGIME. The model was trained on the seed-0 drug-level split (1,195 train /
  255 validation / 255 test drugs). A pair of two training drugs is S1: the
  frozen study never evaluated that regime, and if the pair is documented the
  model was fitted on its label — its score is then a memory, not a
  prediction. S2 (one drug outside training) and S3 (neither) are what the
  frozen test set characterises.
* ANNOTATION COVERAGE. When either drug has no protein annotation the model
  falls back on structure, and measured AUROC drops (pooled 0.818 → 0.750, S3
  0.735 → 0.654; reports/v3_coverage_reliability.md).

Deliberately absent:

* A confidence percentage. Nothing measured supports one per pair.
* Seed disagreement. Only the seed-0 checkpoint exists; and on the frozen
  test predictions, across-seed spread detected errors no better than the
  score's own distance from 0.5 (reports/v3_seed_disagreement.md).
* A risk reading of the score. Temperature scaling was fitted on validation
  pairs at prevalence 0.5, against sampled unlabelled negatives.

Every number below is copied from a file in the repository and asserted equal
to it by tests/test_v3_evidence.py.
"""

from __future__ import annotations

from .schema import Bi, MeasuredPerformance, ModelBlock

#: paper/FACTS.json -> models.M4_pooled / models.M4_s3
FROZEN_AUPRC = {
    "pooled": {"mean": 0.8117107056824635, "sd": 0.009671090046444024, "n": 5,
               "source": "paper/FACTS.json models.M4_pooled (v2_final_test.csv @ frozen tag)"},
    "S3": {"mean": 0.7372412574502945, "sd": 0.015253024558550193, "n": 5,
           "source": "paper/FACTS.json models.M4_s3 (v2_final_s3_posthoc.csv @ frozen tag)"},
}

#: reports/v3_coverage_reliability.json -> views.<view>.<group>.auroc_*
COVERAGE_AUROC = {
    ("pooled", "both_annotated"): (0.8176889406938518, 0.009571260994343847),
    ("pooled", "at_least_one_unannotated"): (0.7504442338947166, 0.023303662945911758),
    ("S3", "both_annotated"): (0.7354349608962428, 0.01792476158231145),
    ("S3", "at_least_one_unannotated"): (0.6543828715365239, 0.03741580548526296),
}
COVERAGE_SOURCE = "reports/v3_coverage_reliability.json"

#: Presentational bands, identical to web/src/components/explainerContent.ts.
BAND_HIGH, BAND_MODERATE = 0.66, 0.40

#: Above this calibrated score, and with no documented evidence, a pair is
#: reported as carrying a model-only research signal. 0.5 is the decision
#: boundary of a temperature-scaled classifier at the evaluation prevalence of
#: 0.5 — a stated convention, not a validated clinical threshold.
MODEL_SIGNAL_THRESHOLD = 0.5


def band(calibrated: float) -> str:
    if calibrated >= BAND_HIGH:
        return "high"
    if calibrated >= BAND_MODERATE:
        return "moderate"
    return "low"


def regime(split_a: str, split_b: str) -> str:
    n_train = (split_a == "train") + (split_b == "train")
    return {2: "S1", 1: "S2", 0: "S3"}[n_train]


CALIBRATION_NOTE = Bi(
    ru="Калиброванная оценка подобрана на проверочных парах, где задокументированных и случайно набранных пар поровну. Это не вероятность вреда и не частота взаимодействий в реальной практике.",
    en="The calibrated score was fitted on validation pairs with equal numbers of documented and randomly drawn pairs. It is not a probability of harm, nor how often interactions happen in practice.",
)


def model_block(*, score, split_a: str, split_b: str, documented: bool,
                has_protein_a: bool, has_protein_b: bool,
                unavailable_reason: str | None = None) -> ModelBlock:
    reg = regime(split_a, split_b)
    seen = reg == "S1" and documented
    reliability = ("training_label_seen" if seen
                   else "not_evaluated_regime" if reg == "S1" else "held_out_like")
    group = "both_annotated" if (has_protein_a and has_protein_b) else "at_least_one_unannotated"

    perf: list[MeasuredPerformance] = []
    notes: list[Bi] = []
    if reg in ("S2", "S3"):
        view = "S3" if reg == "S3" else "pooled"
        f = FROZEN_AUPRC[view]
        perf.append(MeasuredPerformance(
            view="S3 (both drugs unseen in training)" if view == "S3"
            else "pooled drug-disjoint test (S2 and S3; 91% S2)",
            metric="AUPRC", mean=f["mean"], sd=f["sd"], n_seeds=f["n"], source=f["source"]))
        m, sd = COVERAGE_AUROC[(view, group)]
        perf.append(MeasuredPerformance(
            view=f"{view}, {group.replace('_', ' ')}", metric="AUROC", mean=m, sd=sd,
            n_seeds=5, source=COVERAGE_SOURCE))

    if seen:
        notes.append(Bi(
            ru="Оба препарата были в обучающей выборке, и эта пара задокументирована — модель обучалась именно на этой записи. Её оценка здесь не независимое предсказание, а воспроизведение уже известного.",
            en="Both drugs were in the training set and this pair is documented — the model was trained on this very record. Its score here is not an independent prediction but a recollection of what is already known.",
        ))
    elif reg == "S1":
        notes.append(Bi(
            ru="Оба препарата были в обучающей выборке. Для таких пар в замороженном исследовании не было отложенной проверки, поэтому точность модели здесь не измерена.",
            en="Both drugs were in the training set. The frozen study held out no pairs of this kind, so the model's accuracy here was never measured.",
        ))
    if "val" in (split_a, split_b):
        notes.append(Bi(
            ru="Один из препаратов входил в проверочную выборку: модель на нём не обучалась, но по нему выбирали конфигурацию и калибровку.",
            en="One drug was in the validation set: the model was not trained on it, but it was used to choose the configuration and the calibration.",
        ))
    if group == "at_least_one_unannotated":
        notes.append(Bi(
            ru="Хотя бы у одного препарата нет записей о белках, и модель опирается только на строение молекулы. На отложенных парах такого рода её точность заметно ниже.",
            en="At least one drug has no protein records, so the model relies on molecular structure alone. On held-out pairs of this kind its accuracy is noticeably lower.",
        ))
    notes.append(CALIBRATION_NOTE)

    common = dict(regime=reg, split_a=split_a, split_b=split_b, training_label_seen=seen,
                  reliability=reliability, measured_performance=perf,
                  biology_available_a=has_protein_a, biology_available_b=has_protein_b, notes=notes)
    if score is None:
        return ModelBlock(available=False, unavailable_reason=unavailable_reason, abstain=True, **common)
    cal = float(score.calibrated_model_score)
    return ModelBlock(
        available=True,
        raw_model_score=float(score.raw_model_score),
        calibrated_model_score=cal,
        band=band(cal),
        abstain=seen,
        **common,
    )
