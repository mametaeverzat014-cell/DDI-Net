#!/usr/bin/env python3
"""
Frozen V2 primary statistics.

H-V2-1:
    M4 true/mean vs aligned M0 GINE on pooled drug-disjoint test.
    Required: paired t-test p < .05 AND Cohen dz > .5.
    Also seed-0 pair bootstrap (1000 resamples).

H-V2-2:
    M4 true/mean vs aligned Dual on S3.
    Required: paired t-test p < .05.

H-V2-3:
    M4 true/mean vs degree-preserving shuffled M4 on pooled test.
    Required: paired t-test p < .05 AND Cohen dz > .5.
    Also seed-0 pair bootstrap (1000 resamples).

This script performs no training and no model inference.
It reads only already-frozen result/prediction CSV files.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import average_precision_score

ROOT = Path(__file__).resolve().parents[1]

M4_SUMMARY = ROOT / "reports/v2_final/v2_final_s3_posthoc.csv"
M4_PRED = ROOT / "reports/v2_final/v2_final_pair_predictions.csv"

M0_SUMMARY = ROOT / "reports/v2_baselines/m0_test_s3.csv"
M0_PRED = ROOT / "reports/v2_baselines/m0_test_pair_predictions.csv"

DUAL_SUMMARY = ROOT / "reports/v2_aligned_ensemble.csv"

ABLATION_SUMMARY = ROOT / "reports/v2_ablations/test_frozen.csv"
ABLATION_PRED = ROOT / "reports/v2_ablations/pair_predictions.csv"

OUT_DIR = ROOT / "reports/v2_statistics"
OUT_CSV = OUT_DIR / "primary_h1_h3.csv"
BOOT_CSV = OUT_DIR / "bootstrap_h1_h3_seed0.csv"
OUT_JSON = OUT_DIR / "primary_h1_h3.json"

SEEDS = [0, 1, 2, 3, 4]
BOOTSTRAP_SEED = 20260829
N_BOOTSTRAP = 1000


def paired_statistics(name, a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)

    if len(a) != 5 or len(b) != 5:
        raise RuntimeError(
            f"{name}: expected exactly five paired seeds"
        )

    if not np.all(np.isfinite(a)) or not np.all(np.isfinite(b)):
        raise RuntimeError(f"{name}: non-finite metric")

    d = a - b
    mean_d = float(np.mean(d))
    sd_d = float(np.std(d, ddof=1))

    if sd_d == 0:
        dz = np.inf if mean_d > 0 else (
            -np.inf if mean_d < 0 else 0.0
        )
    else:
        dz = mean_d / sd_d

    t_stat, p_value = stats.ttest_rel(a, b)

    sem = stats.sem(d)
    ci = stats.t.interval(
        0.95,
        df=len(d) - 1,
        loc=mean_d,
        scale=sem,
    )

    try:
        wilcoxon = stats.wilcoxon(
            a,
            b,
            alternative="two-sided",
            zero_method="wilcox",
        )
        wilcoxon_stat = float(wilcoxon.statistic)
        wilcoxon_p = float(wilcoxon.pvalue)
    except ValueError:
        wilcoxon_stat = np.nan
        wilcoxon_p = np.nan

    return {
        "hypothesis": name,
        "n_seeds": len(a),
        "model_a_mean": float(np.mean(a)),
        "model_a_std": float(np.std(a, ddof=1)),
        "model_b_mean": float(np.mean(b)),
        "model_b_std": float(np.std(b, ddof=1)),
        "delta_mean": mean_d,
        "delta_std": sd_d,
        "ci95_low": float(ci[0]),
        "ci95_high": float(ci[1]),
        "paired_t": float(t_stat),
        "paired_p": float(p_value),
        "cohen_dz": float(dz),
        "wilcoxon_stat": wilcoxon_stat,
        "wilcoxon_p": wilcoxon_p,
    }


def normalize_pairs(df):
    required = {
        "seed",
        "test_view",
        "drug_a",
        "drug_b",
        "label",
        "prediction",
    }
    missing = required - set(df.columns)
    if missing:
        raise RuntimeError(
            f"Prediction file missing columns: {sorted(missing)}"
        )

    df = df.copy()
    df["seed"] = pd.to_numeric(df["seed"], errors="raise").astype(int)
    df["label"] = pd.to_numeric(df["label"], errors="raise").astype(int)
    df["prediction"] = pd.to_numeric(
        df["prediction"], errors="raise"
    ).astype(float)

    # Canonical unordered pair key.
    a = df["drug_a"].astype(str)
    b = df["drug_b"].astype(str)
    df["pair_a"] = np.where(a <= b, a, b)
    df["pair_b"] = np.where(a <= b, b, a)

    return df


def select_predictions(
    df,
    seed,
    view,
    ablation=None,
    biology_source=None,
    aggregation=None,
):
    x = df[
        (df["seed"] == seed)
        & (df["test_view"].astype(str).str.lower() == view.lower())
    ].copy()

    if ablation is not None:
        x = x[x["ablation"].astype(str) == ablation]
    if biology_source is not None:
        x = x[x["biology_source"].astype(str) == biology_source]
    if aggregation is not None:
        x = x[x["aggregation"].astype(str) == aggregation]

    if len(x) == 0:
        raise RuntimeError(
            f"No predictions: seed={seed}, view={view}, "
            f"ablation={ablation}, biology={biology_source}, "
            f"aggregation={aggregation}"
        )

    if x.duplicated(["pair_a", "pair_b"]).any():
        raise RuntimeError("Duplicate drug pairs in prediction subset")

    return x[
        ["pair_a", "pair_b", "label", "prediction"]
    ].reset_index(drop=True)


def align_pair_predictions(a, b, name):
    merged = a.merge(
        b,
        on=["pair_a", "pair_b"],
        how="inner",
        suffixes=("_a", "_b"),
        validate="one_to_one",
    )

    if len(merged) != len(a) or len(merged) != len(b):
        raise RuntimeError(
            f"{name}: pair sets differ: "
            f"A={len(a)}, B={len(b)}, intersection={len(merged)}"
        )

    if not np.array_equal(
        merged["label_a"].to_numpy(),
        merged["label_b"].to_numpy(),
    ):
        raise RuntimeError(f"{name}: labels differ after pair alignment")

    return merged


def bootstrap_auprc_difference(
    merged,
    hypothesis,
    model_a,
    model_b,
):
    y = merged["label_a"].to_numpy(dtype=int)
    pa = merged["prediction_a"].to_numpy(dtype=float)
    pb = merged["prediction_b"].to_numpy(dtype=float)

    if len(np.unique(y)) != 2:
        raise RuntimeError(f"{hypothesis}: labels are not binary")

    observed_a = float(average_precision_score(y, pa))
    observed_b = float(average_precision_score(y, pb))
    observed_delta = observed_a - observed_b

    rng = np.random.default_rng(BOOTSTRAP_SEED)
    n = len(y)
    deltas = np.empty(N_BOOTSTRAP, dtype=float)

    for i in range(N_BOOTSTRAP):
        idx = rng.integers(0, n, size=n)
        yb = y[idx]

        # Extremely unlikely here, but fail closed rather than silently
        # computing an invalid AP bootstrap sample.
        if len(np.unique(yb)) != 2:
            raise RuntimeError(
                f"{hypothesis}: bootstrap sample {i} has one class"
            )

        deltas[i] = (
            average_precision_score(yb, pa[idx])
            - average_precision_score(yb, pb[idx])
        )

    low, high = np.percentile(deltas, [2.5, 97.5])

    return {
        "hypothesis": hypothesis,
        "seed": 0,
        "model_a": model_a,
        "model_b": model_b,
        "n_pairs": int(n),
        "n_bootstrap": N_BOOTSTRAP,
        "bootstrap_rng_seed": BOOTSTRAP_SEED,
        "model_a_auprc": observed_a,
        "model_b_auprc": observed_b,
        "observed_delta": float(observed_delta),
        "bootstrap_delta_mean": float(np.mean(deltas)),
        "bootstrap_delta_std": float(np.std(deltas, ddof=1)),
        "bootstrap_ci95_low": float(low),
        "bootstrap_ci95_high": float(high),
        "bootstrap_fraction_le_zero": float(np.mean(deltas <= 0)),
    }


def main():
    required = [
        M4_SUMMARY,
        M4_PRED,
        M0_SUMMARY,
        M0_PRED,
        DUAL_SUMMARY,
        ABLATION_SUMMARY,
        ABLATION_PRED,
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise RuntimeError(
            "Missing frozen inputs:\n" + "\n".join(missing)
        )

    m4 = pd.read_csv(M4_SUMMARY)
    m0 = pd.read_csv(M0_SUMMARY)
    dual = pd.read_csv(DUAL_SUMMARY)
    abl = pd.read_csv(ABLATION_SUMMARY)

    for df, name in [
        (m4, "M4"),
        (m0, "M0"),
        (abl, "ablations"),
    ]:
        df["seed"] = pd.to_numeric(
            df["seed"], errors="raise"
        ).astype(int)
        if sorted(df["seed"].unique()) != SEEDS:
            if name != "ablations":
                raise RuntimeError(
                    f"{name}: expected seeds 0..4"
                )

    m4_seed = m4.set_index("seed").sort_index()
    m0_seed = m0.set_index("seed").sort_index()

    if list(m4_seed.index) != SEEDS:
        raise RuntimeError("M4 seed alignment failure")
    if list(m0_seed.index) != SEEDS:
        raise RuntimeError("M0 seed alignment failure")

    # H1: primary pooled drug-disjoint comparison.
    h1 = paired_statistics(
        "H-V2-1",
        m4_seed["test_auprc"].to_numpy(),
        m0_seed["test_auprc"].to_numpy(),
    )
    h1.update({
        "comparison": "M4 true mean vs M0 GINE",
        "test_view": "pooled drug-disjoint",
        "required_p_lt_0_05": True,
        "required_dz_gt_0_5": True,
    })

    # H2: M4 vs aligned historical Dual, specifically S3.
    dual_s3 = dual[
        (dual["architecture"].astype(str) == "dual")
        & (dual["test_view"].astype(str).str.upper() == "S3")
    ].copy()

    dual_s3["seed"] = pd.to_numeric(
        dual_s3["member_seed"], errors="raise"
    ).astype(int)
    dual_s3 = dual_s3.sort_values("seed")

    if list(dual_s3["seed"]) != SEEDS:
        raise RuntimeError(
            f"Dual S3 seeds mismatch: {list(dual_s3['seed'])}"
        )

    h2 = paired_statistics(
        "H-V2-2",
        m4_seed["s3_auprc"].to_numpy(),
        dual_s3["auprc"].to_numpy(),
    )
    h2.update({
        "comparison": "M4 true mean vs aligned Dual",
        "test_view": "S3",
        "required_p_lt_0_05": True,
        "required_dz_gt_0_5": False,
    })

    # H3: true M4 vs degree-preserving shuffled M4, pooled.
    shuffled = abl[
        (abl["ablation"].astype(str) == "M4")
        & (abl["biology_source"].astype(str) == "shuffled")
        & (abl["aggregation"].astype(str) == "mean")
    ].copy()

    shuffled = shuffled.sort_values("seed")

    if list(shuffled["seed"]) != SEEDS:
        raise RuntimeError(
            f"Shuffled M4 seeds mismatch: {list(shuffled['seed'])}"
        )

    h3 = paired_statistics(
        "H-V2-3",
        m4_seed["test_auprc"].to_numpy(),
        shuffled["test_auprc"].to_numpy(),
    )
    h3.update({
        "comparison": "M4 true mean vs M4 shuffled biology",
        "test_view": "pooled drug-disjoint",
        "required_p_lt_0_05": True,
        "required_dz_gt_0_5": True,
    })

    primary = pd.DataFrame([h1, h2, h3])

    # Explicit preregistered pass/fail before multiplicity correction.
    primary["nominal_pass"] = (
        primary["paired_p"] < 0.05
    ) & (
        (~primary["required_dz_gt_0_5"])
        | (primary["cohen_dz"] > 0.5)
    )

    # Pair-level bootstrap: seed 0 only, exactly as preregistered.
    m4_pred = normalize_pairs(pd.read_csv(M4_PRED))
    m0_pred = normalize_pairs(pd.read_csv(M0_PRED))
    abl_pred = normalize_pairs(pd.read_csv(ABLATION_PRED))

    m4_seed0 = select_predictions(
        m4_pred,
        seed=0,
        view="pooled",
    )
    m0_seed0 = select_predictions(
        m0_pred,
        seed=0,
        view="pooled",
    )

    h1_pairs = align_pair_predictions(
        m4_seed0,
        m0_seed0,
        "H-V2-1",
    )
    boot_h1 = bootstrap_auprc_difference(
        h1_pairs,
        "H-V2-1",
        "M4 true mean",
        "M0 GINE",
    )

    shuffled_seed0 = select_predictions(
        abl_pred,
        seed=0,
        view="pooled",
        ablation="M4",
        biology_source="shuffled",
        aggregation="mean",
    )

    h3_pairs = align_pair_predictions(
        m4_seed0,
        shuffled_seed0,
        "H-V2-3",
    )
    boot_h3 = bootstrap_auprc_difference(
        h3_pairs,
        "H-V2-3",
        "M4 true mean",
        "M4 shuffled biology",
    )

    bootstrap = pd.DataFrame([boot_h1, boot_h3])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    primary.to_csv(OUT_CSV, index=False)
    bootstrap.to_csv(BOOT_CSV, index=False)

    payload = {
        "analysis": "Frozen V2 primary H1-H3 statistics",
        "training_performed": False,
        "inference_performed": False,
        "n_bootstrap": N_BOOTSTRAP,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "primary": primary.to_dict(orient="records"),
        "bootstrap": bootstrap.to_dict(orient="records"),
    }
    OUT_JSON.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )

    print("\n=== PRIMARY PAIRED TESTS ===")
    for _, r in primary.iterrows():
        print(
            f"\n{r['hypothesis']} — {r['comparison']}"
            f"\n  A = {r['model_a_mean']:.6f} ± {r['model_a_std']:.6f}"
            f"\n  B = {r['model_b_mean']:.6f} ± {r['model_b_std']:.6f}"
            f"\n  Δ = {r['delta_mean']:+.6f} ± {r['delta_std']:.6f}"
            f"\n  95% CI = [{r['ci95_low']:+.6f}, {r['ci95_high']:+.6f}]"
            f"\n  paired t = {r['paired_t']:.6f}"
            f"\n  p = {r['paired_p']:.8g}"
            f"\n  Cohen dz = {r['cohen_dz']:.6f}"
            f"\n  nominal prereg pass = {bool(r['nominal_pass'])}"
        )

    print("\n=== SEED-0 PAIR BOOTSTRAP ===")
    for _, r in bootstrap.iterrows():
        print(
            f"\n{r['hypothesis']} — {r['model_a']} vs {r['model_b']}"
            f"\n  n pairs = {int(r['n_pairs'])}"
            f"\n  observed ΔAUPRC = {r['observed_delta']:+.6f}"
            f"\n  bootstrap mean Δ = {r['bootstrap_delta_mean']:+.6f}"
            f"\n  bootstrap 95% CI = "
            f"[{r['bootstrap_ci95_low']:+.6f}, "
            f"{r['bootstrap_ci95_high']:+.6f}]"
            f"\n  fraction Δ <= 0 = "
            f"{r['bootstrap_fraction_le_zero']:.6f}"
        )

    print("\nWROTE:")
    print(OUT_CSV)
    print(BOOT_CSV)
    print(OUT_JSON)
    print("\nNo training or inference was performed.")


if __name__ == "__main__":
    main()
