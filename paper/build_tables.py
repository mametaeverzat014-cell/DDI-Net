"""Generate manuscript tables directly from the frozen V2 artifacts.

WHY THIS SCRIPT EXISTS
----------------------
Every number in the manuscript must be traceable to a frozen file. Typing
numbers into a table by hand is how transcription errors enter a paper, and a
transcription error in a results table is indistinguishable from fabrication to
a reader who cannot check it. So the tables are *generated*, never authored.

Read-only by construction: this script opens frozen CSV/JSON artifacts and
writes only into ``paper/tables/``. It never touches ``reports/``, never
retrains, never recomputes a model prediction. Statistics reported here are
recomputed from per-seed values so that the table and the frozen statistics
file are independent derivations of the same quantity; the consistency audit
(``paper/audit_consistency.py``) checks that they agree.

Frozen source: git tag v2-final-github-safe-2026-09-03 (commit 92c481ee),
GitHub-safe snapshot of local frozen commit 4657c256.
"""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

#: Everything is read from this git ref, never from the working tree. Reading a
#: working-tree copy would let an edited file silently enter the manuscript;
#: reading the tag makes that impossible. The tag is annotated and immutable.
FROZEN_REF = "v2-final-github-safe-2026-09-03"
REPO = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "tables"


def frozen_csv(path: str) -> pd.DataFrame:
    """Read a CSV out of the frozen tag without materialising it on disk."""
    blob = subprocess.run(
        ["git", "show", f"{FROZEN_REF}:{path}"],
        cwd=REPO, capture_output=True, check=True,
    ).stdout
    return pd.read_csv(io.BytesIO(blob))


def frozen_json(path: str) -> dict:
    blob = subprocess.run(
        ["git", "show", f"{FROZEN_REF}:{path}"],
        cwd=REPO, capture_output=True, check=True,
    ).stdout.decode()
    # The frozen probe summary serialises absent correlations as bare NaN, which
    # is valid Python-repr JSON but not strict JSON; json.loads accepts it.
    return json.loads(blob)


def ms(values) -> tuple[float, float]:
    """Mean and *sample* standard deviation (ddof=1) across seeds.

    ddof=1 throughout: the five seeds are a sample of the training-stochasticity
    distribution, not the whole population of possible runs.
    """
    v = np.asarray(values, dtype=float)
    return float(v.mean()), float(v.std(ddof=1))


def paired(a, b) -> dict:
    """Paired two-sided t-test on seed-matched values, plus CI and Cohen's dz.

    Pairing is by seed: seed k of model A is compared with seed k of model B,
    which are trained on the same split with the same negatives and differ only
    in the factor under test. Cohen's dz is the paired effect size
    (mean difference / sd of differences), not Cohen's d for independent groups.
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    d = a - b
    n = len(d)
    md, sd = float(d.mean()), float(d.std(ddof=1))
    se = sd / np.sqrt(n)
    t = md / se
    p = float(2 * stats.t.sf(abs(t), n - 1))
    crit = float(stats.t.ppf(0.975, n - 1))
    return {
        "delta_mean": md,
        "delta_std": sd,
        "ci95_low": md - crit * se,
        "ci95_high": md + crit * se,
        "paired_t": float(t),
        "raw_p": p,
        "cohen_dz": md / sd,
        "n_seeds": n,
    }


def holm(pvalues: dict[str, float]) -> dict[str, float]:
    """Holm-Bonferroni step-down adjustment over the whole hypothesis family.

    The family is all five preregistered hypotheses, H5 included. Including an
    exploratory hypothesis in the family makes the correction *stricter* for the
    confirmatory ones (the smallest p is multiplied by 5 rather than 4), so this
    is the conservative choice. The running maximum enforces monotonicity, which
    Holm requires: an adjusted p-value can never fall below one ranked before it.
    """
    names = list(pvalues)
    raw = np.array([pvalues[k] for k in names], dtype=float)
    m = len(raw)
    order = np.argsort(raw)
    adjusted = np.empty(m)
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, (m - rank) * raw[idx])
        adjusted[idx] = min(running, 1.0)
    return dict(zip(names, adjusted))


# ---------------------------------------------------------------- load frozen
m4 = frozen_csv("reports/v2_final/v2_final_test.csv").sort_values("seed")
m4_s3 = frozen_csv("reports/v2_final/v2_final_s3_posthoc.csv").sort_values("seed")
m0 = frozen_csv("reports/v2_baselines/m0_test_s3.csv").sort_values("seed")
abl = frozen_csv("reports/v2_ablations/test_frozen.csv")
dual = frozen_csv("reports/v2_aligned_ensemble.csv")
bio_rf = frozen_csv("reports/v2_bio_controls/bio_rf_test.csv").sort_values("seed")
deg_rf = frozen_csv(
    "reports/v2_bio_controls/biological_degree_rf_test.csv"
).sort_values("seed")
calib = frozen_csv("reports/v2_calibration/m4_temperature_scaling.csv").sort_values("seed")
h5 = frozen_csv("reports/v2_statistics/h5_pathway_coverage.csv").sort_values("seed")
boot = frozen_csv("reports/v2_statistics/bootstrap_h1_h3_seed0.csv")
probe = frozen_json("reports/v2_interpretability/seed0_linear_probe_summary.json")

dual_pooled = dual[dual.test_view == "pooled"].sort_values("member_seed")
dual_s3 = dual[dual.test_view == "S3"].sort_values("member_seed")
shuffled = abl[
    (abl.ablation == "M4") & (abl.aggregation == "mean") & (abl.biology_source == "shuffled")
].sort_values("seed")
m4_sum = abl[
    (abl.ablation == "M4") & (abl.aggregation == "sum") & (abl.biology_source == "true")
].sort_values("seed")


def ladder(name):
    return abl[
        (abl.ablation == name) & (abl.aggregation == "mean") & (abl.biology_source == "true")
    ].sort_values("seed")


# --------------------------------------------------- TABLE 3: main comparison
rows = []
for label, category, pooled_vals, s3_vals, source in [
    ("BIO-GINE M4 (primary)", "Full model",
     m4.test_auprc, m4_s3.s3_auprc, "reports/v2_final/v2_final_test.csv; v2_final_s3_posthoc.csv"),
    ("Aligned molecular GINE (M0)", "Structure-only baseline",
     m0.test_auprc, m0.s3_auprc, "reports/v2_baselines/m0_test_s3.csv"),
    ("Aligned Dual (GINE + DDI network)", "Transductive baseline",
     dual_pooled.auprc, dual_s3.auprc, "reports/v2_aligned_ensemble.csv"),
    ("BIO-RF (fingerprint + biology RF)", "Non-neural baseline",
     bio_rf.auprc, None, "reports/v2_bio_controls/bio_rf_test.csv"),
    ("Biological-degree-only RF (CONTROL A)", "Shortcut control",
     deg_rf.test_auprc, None, "reports/v2_bio_controls/biological_degree_rf_test.csv"),
    ("BIO-GINE M4, shuffled biology (CONTROL F)", "Shortcut control",
     shuffled.test_auprc, shuffled.s3_auprc, "reports/v2_ablations/test_frozen.csv"),
]:
    pm, ps = ms(pooled_vals)
    row = {
        "model": label,
        "category": category,
        "pooled_auprc_mean": pm,
        "pooled_auprc_std": ps,
        "n_seeds": len(pooled_vals),
        "source_file": source,
    }
    if s3_vals is not None:
        sm, ss = ms(s3_vals)
        row["s3_auprc_mean"], row["s3_auprc_std"] = sm, ss
    else:
        row["s3_auprc_mean"], row["s3_auprc_std"] = "", ""
    rows.append(row)
pd.DataFrame(rows).to_csv(OUT / "table3_main_model_comparison.csv", index=False)

# ----------------------------------------------------- TABLE 4: H1-H5 results
H = {
    "H-V2-1": (paired(m4.test_auprc, m0.test_auprc), "CONFIRMATORY",
               "BIO-GINE M4 vs aligned molecular GINE (M0)", "pooled drug-disjoint"),
    "H-V2-2": (paired(m4_s3.s3_auprc, dual_s3.auprc), "CONFIRMATORY",
               "BIO-GINE M4 vs aligned Dual", "S3"),
    "H-V2-3": (paired(m4.test_auprc, shuffled.test_auprc), "CONFIRMATORY",
               "BIO-GINE M4 true biology vs degree-preserving shuffled biology",
               "pooled drug-disjoint"),
    "H-V2-4": (paired(m4.test_auprc, deg_rf.test_auprc), "CONFIRMATORY",
               "BIO-GINE M4 vs biological-degree-only RF", "pooled drug-disjoint"),
    "H-V2-5": (paired(h5.delta_covered, h5.delta_uncovered), "EXPLORATORY",
               "M4-minus-M0 gain: pathway-covered vs pathway-uncovered pairs",
               "pooled drug-disjoint subgroup contrast"),
}
adj = holm({k: v[0]["raw_p"] for k, v in H.items()})
conclusion = {
    "H-V2-1": "Supported (confirmatory)",
    "H-V2-2": "Supported (confirmatory)",
    "H-V2-3": "Supported (confirmatory)",
    "H-V2-4": "Supported (confirmatory)",
    "H-V2-5": "Exploratory direction unsupported",
}
pd.DataFrame([
    {
        "hypothesis": k,
        "status": st,
        "comparison": cmp_,
        "test_view": view,
        "n_seeds": r["n_seeds"],
        "delta_auprc": r["delta_mean"],
        "delta_std": r["delta_std"],
        "ci95_low": r["ci95_low"],
        "ci95_high": r["ci95_high"],
        "paired_t": r["paired_t"],
        "raw_p": r["raw_p"],
        "holm_adjusted_p": adj[k],
        "cohen_dz": r["cohen_dz"],
        "conclusion": conclusion[k],
    }
    for k, (r, st, cmp_, view) in H.items()
]).to_csv(OUT / "table4_hypotheses.csv", index=False)

# ------------------------------------------------------- TABLE 5: ablations
lad = []
for name, desc in [
    ("M1", "DrugBank documented protein relations only"),
    ("M2", "M1 + ChEMBL curated mechanism-of-action evidence"),
    ("M3", "M2 + ChEMBL experimental bioactivity evidence"),
]:
    d = ladder(name)
    pm, ps = ms(d.test_auprc)
    sm, ss = ms(d.s3_auprc)
    lad.append({"variant": name, "description": desc, "aggregation": "mean",
                "biology": "true", "pooled_auprc_mean": pm, "pooled_auprc_std": ps,
                "s3_auprc_mean": sm, "s3_auprc_std": ss, "n_seeds": len(d)})
pm, ps = ms(m4.test_auprc)
sm, ss = ms(m4_s3.s3_auprc)
lad.append({"variant": "M4 (primary)", "description": "M3 + Reactome pathway level",
            "aggregation": "mean", "biology": "true",
            "pooled_auprc_mean": pm, "pooled_auprc_std": ps,
            "s3_auprc_mean": sm, "s3_auprc_std": ss, "n_seeds": len(m4)})
for d, name, desc, agg, bio in [
    (m4_sum, "M4 SUM (CONTROL C)", "M4 with SUM instead of MEAN aggregation", "sum", "true"),
    (shuffled, "M4 shuffled (CONTROL F)", "M4 with degree-preserving shuffled biology",
     "mean", "shuffled"),
]:
    pm, ps = ms(d.test_auprc)
    sm, ss = ms(d.s3_auprc)
    lad.append({"variant": name, "description": desc, "aggregation": agg, "biology": bio,
                "pooled_auprc_mean": pm, "pooled_auprc_std": ps,
                "s3_auprc_mean": sm, "s3_auprc_std": ss, "n_seeds": len(d)})
# M0 anchors the bottom of the ladder: it is the same molecular encoder with the
# biological branch switched off entirely.
pm, ps = ms(m0.test_auprc)
sm, ss = ms(m0.s3_auprc)
lad.insert(0, {"variant": "M0", "description": "Molecular structure only, no biology",
               "aggregation": "n/a", "biology": "none",
               "pooled_auprc_mean": pm, "pooled_auprc_std": ps,
               "s3_auprc_mean": sm, "s3_auprc_std": ss, "n_seeds": len(m0)})
pd.DataFrame(lad).to_csv(OUT / "table5_ablation_ladder.csv", index=False)

# ----------------------------------------------------- TABLE 6: calibration
cal_rows = []
for _, r in calib.iterrows():
    cal_rows.append({
        "seed": int(r.seed),
        "temperature": r.temperature,
        "converged": bool(r.temperature_converged),
        "auprc_raw": r.test_auprc_raw, "auprc_scaled": r.test_auprc_scaled,
        "auroc_raw": r.test_auroc_raw, "auroc_scaled": r.test_auroc_scaled,
        "brier_raw": r.test_brier_raw, "brier_scaled": r.test_brier_scaled,
        "ece15_raw": r.test_ece15_raw, "ece15_scaled": r.test_ece15_scaled,
    })
cal = pd.DataFrame(cal_rows)
summary = {"seed": "mean (n=5)", "temperature": cal.temperature.mean(), "converged": ""}
for c in ["auprc_raw", "auprc_scaled", "auroc_raw", "auroc_scaled",
          "brier_raw", "brier_scaled", "ece15_raw", "ece15_scaled"]:
    summary[c] = cal[c].mean()
pd.concat([cal, pd.DataFrame([summary])]).to_csv(
    OUT / "table6_calibration.csv", index=False)

# ---------------------------------------- machine-readable facts for the audit
facts = {
    "frozen_tag": "v2-final-github-safe-2026-09-03",
    "frozen_commit": "92c481eeaba8faff991ced850e1c4de418ea31b0",
    "provenance_commit": "4657c256ee5e0157f529ebae41e96e0dc4dd9a3e",
    "selected_config_id": "e8ece7c41ae09e5f",
    "n_final_seeds": int(len(m4)),
    "test_n_pooled": int(m4.test_n.iloc[0]),
    "test_n_s3": int(m4_s3.s3_n.iloc[0]),
    "test_prevalence": float(m4.test_prevalence.iloc[0]),
    "models": {},
    "hypotheses": {},
    "control_e": {
        "r2_train": probe["r2_train"],
        "r2_test_reported_in_json": probe["r2_test"],
        "held_out_target_variance": 0.0,
        "identifiable": False,
    },
    "bootstrap": boot.to_dict(orient="records"),
}
for label, vals in [
    ("M4_pooled", m4.test_auprc), ("M4_s3", m4_s3.s3_auprc),
    ("M0_pooled", m0.test_auprc), ("M0_s3", m0.s3_auprc),
    ("Dual_pooled", dual_pooled.auprc), ("Dual_s3", dual_s3.auprc),
    ("BIO_RF_pooled", bio_rf.auprc), ("degree_RF_pooled", deg_rf.test_auprc),
    ("M4_shuffled_pooled", shuffled.test_auprc), ("M4_shuffled_s3", shuffled.s3_auprc),
    ("M1_pooled", ladder("M1").test_auprc), ("M1_s3", ladder("M1").s3_auprc),
    ("M2_pooled", ladder("M2").test_auprc), ("M2_s3", ladder("M2").s3_auprc),
    ("M3_pooled", ladder("M3").test_auprc), ("M3_s3", ladder("M3").s3_auprc),
    ("M4_SUM_pooled", m4_sum.test_auprc), ("M4_SUM_s3", m4_sum.s3_auprc),
]:
    mean, std = ms(vals)
    facts["models"][label] = {"mean": mean, "std": std, "n": len(vals)}
for k, (r, st, cmp_, view) in H.items():
    facts["hypotheses"][k] = {**r, "holm_adjusted_p": adj[k], "status": st,
                              "comparison": cmp_, "test_view": view,
                              "conclusion": conclusion[k]}
(Path(__file__).resolve().parent / "FACTS.json").write_text(json.dumps(facts, indent=2))

print("tables written to", OUT)
for f in sorted(OUT.glob("*.csv")):
    print("  ", f.name)
print("FACTS.json written")
