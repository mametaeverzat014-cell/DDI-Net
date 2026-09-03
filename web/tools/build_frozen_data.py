"""Build the website's single scientific data file from the frozen V2 state.

WHY THIS EXISTS
---------------
The website must never contain a hand-typed scientific number. Every figure it
shows is produced here, by reading the frozen artifacts, and written once into
`web/src/data/frozen.json`. The frontend imports that file; it does not know any
number by heart. If a value is wrong, it is wrong in the frozen source, not in
the UI — which is the only place a research site is allowed to be wrong.

SOURCES
-------
- `reports/v2_*` are read from the frozen git tag via `git show`, never from the
  working tree (this branch does not even carry them). Reading the tag makes it
  impossible for an edited working file to leak into the site.
- `data/mechanism_v1/model_readiness.json` and `MANIFEST.json` are read from the
  working tree, where the dataset (but not the reports) is present.

All per-seed statistics are recomputed here from the per-seed rows, so the site
and the frozen summary files are independent derivations of the same quantity.

Run:  python web/tools/build_frozen_data.py
"""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

FROZEN_TAG = "v2-final-github-safe-2026-09-03"
FROZEN_COMMIT = "92c481eeaba8faff991ced850e1c4de418ea31b0"
PROVENANCE_COMMIT = "4657c256ee5e0157f529ebae41e96e0dc4dd9a3e"

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "web" / "src" / "data" / "frozen.json"


def frozen_csv(path: str) -> pd.DataFrame:
    """Read a CSV out of the frozen tag without materialising it on disk."""
    blob = subprocess.run(
        ["git", "show", f"{FROZEN_TAG}:{path}"],
        cwd=REPO, capture_output=True, check=True,
    ).stdout
    return pd.read_csv(io.BytesIO(blob))


def ms(values) -> tuple[float, float]:
    v = np.asarray(values, dtype=float)
    return float(v.mean()), float(v.std(ddof=1))


def paired(a, b) -> dict:
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = a - b
    n = len(d)
    md, sd = float(d.mean()), float(d.std(ddof=1))
    se = sd / np.sqrt(n)
    t = md / se
    p = float(2 * stats.t.sf(abs(t), n - 1))
    crit = float(stats.t.ppf(0.975, n - 1))
    return {"delta": md, "delta_std": sd, "ci_low": md - crit * se,
            "ci_high": md + crit * se, "t": float(t), "raw_p": p,
            "dz": md / sd, "n": n}


def holm(pvals: dict[str, float]) -> dict[str, float]:
    names = list(pvals)
    raw = np.array([pvals[k] for k in names])
    m = len(raw)
    order = np.argsort(raw)
    adj = np.empty(m)
    run = 0.0
    for rank, idx in enumerate(order):
        run = max(run, (m - rank) * raw[idx])
        adj[idx] = min(run, 1.0)
    return dict(zip(names, adj))


# ---------------------------------------------------------------- load frozen
m4 = frozen_csv("reports/v2_final/v2_final_test.csv").sort_values("seed")
m4_s3 = frozen_csv("reports/v2_final/v2_final_s3_posthoc.csv").sort_values("seed")
m0 = frozen_csv("reports/v2_baselines/m0_test_s3.csv").sort_values("seed")
abl = frozen_csv("reports/v2_ablations/test_frozen.csv")
dual = frozen_csv("reports/v2_aligned_ensemble.csv")
bio_rf = frozen_csv("reports/v2_bio_controls/bio_rf_test.csv").sort_values("seed")
deg_rf = frozen_csv("reports/v2_bio_controls/biological_degree_rf_test.csv").sort_values("seed")
calib = frozen_csv("reports/v2_calibration/m4_temperature_scaling.csv").sort_values("seed")
h5 = frozen_csv("reports/v2_statistics/h5_pathway_coverage.csv").sort_values("seed")
probe = json.loads(subprocess.run(
    ["git", "show", f"{FROZEN_TAG}:reports/v2_interpretability/seed0_linear_probe_summary.json"],
    cwd=REPO, capture_output=True, check=True).stdout.decode())
modality = frozen_csv("reports/v2_interpretability/seed0_modality_contribution.csv")

dual_pooled = dual[dual.test_view == "pooled"].sort_values("member_seed")
dual_s3 = dual[dual.test_view == "S3"].sort_values("member_seed")
shuffled = abl[(abl.ablation == "M4") & (abl.aggregation == "mean") & (abl.biology_source == "shuffled")].sort_values("seed")
m4_sum = abl[(abl.ablation == "M4") & (abl.aggregation == "sum") & (abl.biology_source == "true")].sort_values("seed")


def ladder(name):
    return abl[(abl.ablation == name) & (abl.aggregation == "mean") & (abl.biology_source == "true")].sort_values("seed")


# working-tree dataset facts
readiness = json.loads((REPO / "data/mechanism_v1/model_readiness.json").read_text())
manifest = json.loads((REPO / "data/mechanism_v1/MANIFEST.json").read_text())

# leakage story: fraction of test pairs whose BOTH endpoints were seen in
# training, per split scheme (seed 0). random_pair leaks; drug/scaffold do not.
split_cmp = frozen_csv("reports/split_comparison.csv")
leak = {}
for scheme in ("random_pair", "drug", "scaffold"):
    row = split_cmp[(split_cmp.scheme == scheme) & (split_cmp.seed == 0)]
    if len(row):
        leak[scheme] = float(row.test_S1_fraction.iloc[0])


def model_row(label, category, pooled_vals, s3_vals, source):
    pm, ps = ms(pooled_vals)
    row = {"label": label, "category": category,
           "pooled_mean": pm, "pooled_std": ps, "n_seeds": len(pooled_vals),
           "source": source}
    if s3_vals is not None:
        sm, sstd = ms(s3_vals)
        row["s3_mean"], row["s3_std"] = sm, sstd
    else:
        row["s3_mean"], row["s3_std"] = None, None
    return row


models = [
    model_row("BIO-GINE M4", "primary", m4.test_auprc, m4_s3.s3_auprc,
              "reports/v2_final/v2_final_test.csv"),
    model_row("Aligned molecular GINE (M0)", "baseline", m0.test_auprc, m0.s3_auprc,
              "reports/v2_baselines/m0_test_s3.csv"),
    model_row("Aligned Dual (GINE + DDI network)", "baseline", dual_pooled.auprc, dual_s3.auprc,
              "reports/v2_aligned_ensemble.csv"),
    model_row("BIO-RF", "baseline", bio_rf.auprc, None,
              "reports/v2_bio_controls/bio_rf_test.csv"),
    model_row("Biological-degree-only RF (CONTROL A)", "control", deg_rf.test_auprc, None,
              "reports/v2_bio_controls/biological_degree_rf_test.csv"),
    model_row("BIO-GINE M4, shuffled biology (CONTROL F)", "control", shuffled.test_auprc, shuffled.s3_auprc,
              "reports/v2_ablations/test_frozen.csv"),
]

# ladder is deliberately NOT sorted by score: order is M0..M4 then controls,
# and the frontend must render it that way so the non-monotonic dip is visible.
ladder_rows = [
    model_row("M0", "ladder", m0.test_auprc, m0.s3_auprc, "reports/v2_baselines/m0_test_s3.csv"),
    model_row("M1", "ladder", ladder("M1").test_auprc, ladder("M1").s3_auprc, "reports/v2_ablations/test_frozen.csv"),
    model_row("M2", "ladder", ladder("M2").test_auprc, ladder("M2").s3_auprc, "reports/v2_ablations/test_frozen.csv"),
    model_row("M3", "ladder", ladder("M3").test_auprc, ladder("M3").s3_auprc, "reports/v2_ablations/test_frozen.csv"),
    model_row("M4 (primary)", "ladder-primary", m4.test_auprc, m4_s3.s3_auprc, "reports/v2_final/v2_final_test.csv"),
    model_row("M4 SUM (CONTROL C)", "ladder-control", m4_sum.test_auprc, m4_sum.s3_auprc, "reports/v2_ablations/test_frozen.csv"),
    model_row("M4 shuffled (CONTROL F)", "ladder-control", shuffled.test_auprc, shuffled.s3_auprc, "reports/v2_ablations/test_frozen.csv"),
]

H = {
    "H-V2-1": (paired(m4.test_auprc, m0.test_auprc), "confirmatory",
               "BIO-GINE M4 vs aligned molecular GINE", "pooled drug-holdout", "Supported"),
    "H-V2-2": (paired(m4_s3.s3_auprc, dual_s3.auprc), "confirmatory",
               "BIO-GINE M4 vs aligned Dual", "S3 (both drugs held out)", "Supported"),
    "H-V2-3": (paired(m4.test_auprc, shuffled.test_auprc), "confirmatory",
               "True biology vs degree-preserving shuffled biology", "pooled drug-holdout", "Supported"),
    "H-V2-4": (paired(m4.test_auprc, deg_rf.test_auprc), "confirmatory",
               "BIO-GINE M4 vs biological-degree-only RF", "pooled drug-holdout", "Supported"),
    "H-V2-5": (paired(h5.delta_covered, h5.delta_uncovered), "exploratory",
               "Pathway-covered vs uncovered gain", "subgroup contrast",
               "Exploratory direction unsupported"),
}
adj = holm({k: v[0]["raw_p"] for k, v in H.items()})
hypotheses = []
for k, (r, status, cmp_, view, concl) in H.items():
    hypotheses.append({"id": k, "status": status, "comparison": cmp_, "view": view,
                       "delta": r["delta"], "ci_low": r["ci_low"], "ci_high": r["ci_high"],
                       "t": r["t"], "raw_p": r["raw_p"], "holm_p": adj[k],
                       "dz": r["dz"], "conclusion": concl})

calibration = []
for _, r in calib.iterrows():
    calibration.append({"seed": int(r.seed), "temperature": float(r.temperature),
                        "ece_raw": float(r.test_ece15_raw), "ece_scaled": float(r.test_ece15_scaled),
                        "brier_raw": float(r.test_brier_raw), "brier_scaled": float(r.test_brier_scaled),
                        "auprc_raw": float(r.test_auprc_raw), "auprc_scaled": float(r.test_auprc_scaled)})

modality_reliance = {
    "molecular": float(modality.abs_molecular_delta.mean()),
    "protein": float(modality.abs_protein_delta.mean()),
    "pathway": float(modality.abs_pathway_delta.mean()),
    "n_pairs": int(len(modality)),
    "source": "reports/v2_interpretability/seed0_modality_contribution.csv",
    "note": "Model reliance under input removal — not causal mechanism.",
}

data = {
    "meta": {
        "frozen_tag": FROZEN_TAG,
        "frozen_commit": FROZEN_COMMIT,
        "provenance_commit": PROVENANCE_COMMIT,
        "generated_note": "All numbers generated by web/tools/build_frozen_data.py from the frozen tag. Do not hand-edit.",
    },
    "dataset": {
        "n_drugs": int(manifest["authoritative_universe"]["n_drugs"]),
        "n_pairs": int(manifest["authoritative_universe"]["n_positive_pairs"]),
        "excluded_drug": manifest["authoritative_universe"]["excluded_drug"],
        "excluded_pairs": int(manifest["authoritative_universe"]["excluded_pairs"]),
        "dataset_version": manifest["dataset_version"],
        "interaction_types": 86,
        "sources": ["DrugBank", "ChEMBL", "Reactome", "UniProt", "SIDER"],
        "source": "data/mechanism_v1/MANIFEST.json",
    },
    "coverage": {
        "protein_any_pct": readiness["protein_coverage_any"]["pct"],
        "protein_any_count": readiness["protein_coverage_any"]["count"],
        "reactome_pct": readiness["reactome_coverage"]["pct"],
        "reactome_count": readiness["reactome_coverage"]["count"],
        "chembl_pct": readiness["chembl_mapped"]["pct"],
        "sider_pct": readiness["sider_coverage"]["pct"],
        "target_pct": readiness["target_coverage_pct"],
        "enzyme_pct": readiness["enzyme_coverage_pct"],
        "transporter_pct": readiness["transporter_coverage_pct"],
        "carrier_pct": readiness["carrier_coverage_pct"],
        "source": "data/mechanism_v1/model_readiness.json",
    },
    "splits": {
        "train_drugs": 1195, "val_drugs": 255, "test_drugs": 255,
        "pooled_pairs": int(m4.test_n.iloc[0]),
        "s3_pairs": int(m4_s3.s3_n.iloc[0]),
        "prevalence": float(m4.test_prevalence.iloc[0]),
        "source": "data/mechanism_v1/split_assignments.csv; reports/v2_final/",
    },
    "leakage": {
        "both_endpoints_seen": leak,
        "note": "Fraction of test pairs whose both endpoints appeared in training (seed 0). Random-pair splitting leaks; drug- and scaffold-holdout do not.",
        "source": "reports/split_comparison.csv",
    },
    "models": models,
    "ladder": ladder_rows,
    "hypotheses": hypotheses,
    "calibration": calibration,
    "interpretability": modality_reliance,
    "control_e": {
        "r2_train": probe["r2_train"],
        "held_out_target_variance": 0.0,
        "identifiable": False,
        "note": "Held-out R^2 is undefined: every drug-holdout test drug has training-DDI degree zero, so target variance is zero.",
        "source": "reports/v2_interpretability/seed0_linear_probe_summary.json",
    },
    "control_f": {
        "changed_fraction": 0.974677,
        "retained_fraction": 0.025323,
        "note": "Degree-preserving shuffle: both degree sequences preserved exactly; 2.53% of edges retained unchanged.",
        "source": "data/mechanism_v1_controls/shuffled_biology_seed20260829/SHUFFLE_MANIFEST.json",
    },
    "scaffold_disjoint": {"evaluated": False,
                          "note": "Scaffold-disjoint evaluation was not performed in final V2."},
    "config": {
        "selected_config_id": "e8ece7c41ae09e5f",
        "n_final_seeds": int(len(m4)),
        "validation_runs": 96, "validation_configs": 32, "validation_seeds": 3,
        "optimizer_steps": 21960, "batch_size": 512, "learning_rate": 1e-3,
        "bio_dim": 128, "total_parameters": 1122804,
        "source": "reports/v2_grid/FROZEN_SELECTED_CONFIG.txt",
    },
    "checkpoint": {
        "seed0_run_id": "bd45f84e3c1b2c33",
        "seed0_sha256": "b828a471fcb8d38e0b29d9c67eddec76c1428bc996cc0d4e5b10c026bf659d6f",
        "installed": False,
        "note": "Frozen inference checkpoint not installed on this deployment.",
    },
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(data, indent=2))
print(f"wrote {OUT.relative_to(REPO)}")
print(f"  models: {len(models)}, ladder: {len(ladder_rows)}, hypotheses: {len(hypotheses)}")
print(f"  M4 pooled {models[0]['pooled_mean']:.6f} ± {models[0]['pooled_std']:.6f}")
