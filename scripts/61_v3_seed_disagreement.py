#!/usr/bin/env python3
"""Does across-seed disagreement tell us when BIO-GINE is wrong?

DDI-Net 3.0, Phase 4. Only the seed-0 checkpoint was released, so a live
ensemble cannot run. What does exist is the frozen per-seed test predictions:
five independently trained M4 models scored the same 84,690 pooled test pairs
(``reports/v2_final/v2_final_pair_predictions.csv`` at the frozen tag). This
script asks the question that decides whether disagreement may be shown to a
user as "uncertainty": on held-out pairs, is the spread between seeds larger
where the ensemble is wrong?

Read from the tag with ``git show``; nothing is written into the frozen tree.
No model is run, trained or selected. Labels are used only to score the
diagnostic, never to choose anything that is later evaluated on them.

Outputs: reports/v3_seed_disagreement.{json,md}
"""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
TAG = "v2-final-github-safe-2026-09-03"
SRC = "reports/v2_final/v2_final_pair_predictions.csv"
OUT_JSON = ROOT / "reports" / "v3_seed_disagreement.json"
OUT_MD = ROOT / "reports" / "v3_seed_disagreement.md"
N_BINS = 5
BOOT = 1000
RNG_SEED = 20261014


def load() -> pd.DataFrame:
    blob = subprocess.run(["git", "show", f"{TAG}:{SRC}"], cwd=ROOT,
                          capture_output=True, check=True).stdout
    df = pd.read_csv(io.BytesIO(blob))
    return df


def per_pair(df: pd.DataFrame, view: str) -> pd.DataFrame:
    d = df[df["test_view"] == view]
    wide = d.pivot_table(index=["drug_a", "drug_b"], columns="seed",
                         values="prediction", aggfunc="first")
    labels = d.groupby(["drug_a", "drug_b"])["label"].first()
    if wide.shape[1] != 5 or wide.isna().any().any():
        raise RuntimeError(f"{view}: expected exactly 5 seeds per pair")
    if d.groupby(["drug_a", "drug_b"])["label"].nunique().max() != 1:
        raise RuntimeError(f"{view}: label differs across seeds for some pair")
    out = pd.DataFrame({
        "mean": wide.mean(axis=1),
        "sd": wide.std(axis=1, ddof=1),
        "seed0": wide[0],
        "label": labels.loc[wide.index].astype(int),
    })
    return out.reset_index()


def analyse(t: pd.DataFrame) -> dict:
    y = t["label"].to_numpy()
    mean = t["mean"].to_numpy()
    sd = t["sd"].to_numpy()
    wrong = ((mean >= 0.5).astype(int) != y).astype(int)
    abs_err = np.abs(mean - y)

    # Does SD rank the ensemble's mistakes above its correct calls?
    auroc_sd_wrong = roc_auc_score(wrong, sd)
    # The obvious competitor: closeness of the mean score to 0.5.
    margin = -np.abs(mean - 0.5)
    auroc_margin_wrong = roc_auc_score(wrong, margin)

    rng = np.random.default_rng(RNG_SEED)
    boots = []
    n = len(t)
    for _ in range(BOOT):
        i = rng.integers(0, n, n)
        if wrong[i].min() == wrong[i].max():
            continue
        boots.append(roc_auc_score(wrong[i], sd[i]))
    ci = [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))]

    # Within a band of similar mean scores, does SD still separate errors?
    # This removes the trivial link (SD is necessarily small near 0 and 1).
    t = t.assign(wrong=wrong, abs_err=abs_err)
    t["mean_bin"] = pd.qcut(t["mean"].rank(method="first"), N_BINS, labels=False)
    within = []
    for b, g in t.groupby("mean_bin"):
        if g["wrong"].nunique() < 2:
            within.append({"mean_bin": int(b), "n": int(len(g)), "auroc_sd_wrong": None})
            continue
        within.append({
            "mean_bin": int(b), "n": int(len(g)),
            "mean_range": [float(g["mean"].min()), float(g["mean"].max())],
            "error_rate": float(g["wrong"].mean()),
            "auroc_sd_wrong": float(roc_auc_score(g["wrong"], g["sd"])),
        })

    t["sd_bin"] = pd.qcut(t["sd"].rank(method="first"), N_BINS, labels=False)
    by_sd = []
    for b, g in t.groupby("sd_bin"):
        by_sd.append({
            "sd_bin": int(b), "n": int(len(g)),
            "sd_range": [float(g["sd"].min()), float(g["sd"].max())],
            "error_rate": float(g["wrong"].mean()),
            "auprc_mean_score": float(average_precision_score(g["label"], g["mean"]))
            if g["label"].nunique() == 2 else None,
        })

    return {
        "n_pairs": int(n),
        "prevalence": float(y.mean()),
        "ensemble_error_rate_at_0_5": float(wrong.mean()),
        "auroc_sd_detects_error": float(auroc_sd_wrong),
        "auroc_sd_detects_error_ci95": ci,
        "auroc_margin_detects_error": float(auroc_margin_wrong),
        "spearman_sd_abs_error": float(pd.Series(sd).corr(pd.Series(abs_err), method="spearman")),
        "within_mean_score_bins": within,
        "by_sd_quintile": by_sd,
        "sd_median": float(np.median(sd)),
        "sd_p90": float(np.percentile(sd, 90)),
    }


def main() -> None:
    df = load()
    res = {
        "question": "On held-out pairs, does across-seed SD of BIO-GINE M4 predictions rank the 5-seed ensemble's errors?",
        "source": f"{SRC} @ {TAG}",
        "error_definition": "5-seed mean prediction >= 0.5 disagrees with the frozen label (prevalence 0.5 test set; negatives are sampled unlabelled pairs).",
        "bootstrap": {"n": BOOT, "rng_seed": RNG_SEED},
        "views": {v: analyse(per_pair(df, v)) for v in ("pooled", "S3")},
    }
    OUT_JSON.write_text(json.dumps(res, indent=2) + "\n")

    lines = [
        "# Seed disagreement as an uncertainty signal (DDI-Net 3.0, Phase 4)",
        "",
        "Generated by `scripts/61_v3_seed_disagreement.py` from the frozen per-seed test",
        f"predictions (`{SRC}` at `{TAG}`). No model was run or trained.",
        "",
        "Error = the 5-seed mean prediction, thresholded at 0.5, disagrees with the frozen",
        "label. Negatives are sampled unlabelled pairs, so an 'error' on a negative may be an",
        "undocumented true interaction.",
        "",
        "| view | pairs | ensemble error rate | AUROC: SD detects error (95% CI) | AUROC: closeness to 0.5 detects error | Spearman(SD, abs error) |",
        "|---|---|---|---|---|---|",
    ]
    for v, r in res["views"].items():
        lo, hi = r["auroc_sd_detects_error_ci95"]
        lines.append(
            f"| {v} | {r['n_pairs']:,} | {r['ensemble_error_rate_at_0_5']:.3f} | "
            f"{r['auroc_sd_detects_error']:.3f} ({lo:.3f}–{hi:.3f}) | "
            f"{r['auroc_margin_detects_error']:.3f} | {r['spearman_sd_abs_error']:.3f} |")
    for v, r in res["views"].items():
        lines += ["", f"## {v}: does SD still separate errors among pairs with similar mean scores?", "",
                  "| mean-score quintile | pairs | mean range | error rate | AUROC: SD detects error |",
                  "|---|---|---|---|---|"]
        for w in r["within_mean_score_bins"]:
            if w["auroc_sd_wrong"] is None:
                lines.append(f"| {w['mean_bin']} | {w['n']:,} | — | — | not defined |")
                continue
            lines.append(f"| {w['mean_bin']} | {w['n']:,} | {w['mean_range'][0]:.3f}–{w['mean_range'][1]:.3f} | "
                         f"{w['error_rate']:.3f} | {w['auroc_sd_wrong']:.3f} |")
    OUT_MD.write_text("\n".join(lines) + "\n")
    print(json.dumps({v: {k: r[k] for k in ("n_pairs", "auroc_sd_detects_error", "auroc_sd_detects_error_ci95", "auroc_margin_detects_error", "spearman_sd_abs_error")} for v, r in res["views"].items()}, indent=2))


if __name__ == "__main__":
    main()
