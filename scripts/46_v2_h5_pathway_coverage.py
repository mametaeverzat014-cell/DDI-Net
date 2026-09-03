#!/usr/bin/env python3
"""H-V2-5 exploratory pathway-coverage analysis.

Preregistered definition:
  covered   = BOTH drugs have >=1 Reactome pathway
  uncovered = at least one drug has 0 Reactome pathways

For each seed:
  delta_covered   = AUPRC(M4 covered) - AUPRC(M0/GINE covered)
  delta_uncovered = AUPRC(M4 uncovered) - AUPRC(M0/GINE uncovered)

Primary H5 quantity:
  contrast = delta_covered - delta_uncovered

H5 remains EXPLORATORY: direction was preregistered, no strict
significance threshold. A paired t-test across seeds is reported
descriptively and can supply the fifth p-value requested by the
multiple-comparisons section of the preregistration.
"""

from pathlib import Path
import json

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import average_precision_score

ROOT = Path(__file__).resolve().parents[1]

M4_FILE = ROOT / "reports/v2_final/v2_final_pair_predictions.csv"
M0_FILE = ROOT / "reports/v2_baselines/m0_test_pair_predictions.csv"

DP_FILE = ROOT / "data/mechanism_v1/drug_protein_edges.parquet"
PP_FILE = ROOT / "data/mechanism_v1/protein_pathway_edges.parquet"

OUT = ROOT / "reports/v2_statistics"
OUT.mkdir(parents=True, exist_ok=True)

CSV_OUT = OUT / "h5_pathway_coverage.csv"
JSON_OUT = OUT / "h5_pathway_coverage.json"


def canonicalise(df):
    df = df.copy()
    a = df["drug_a"].astype(str)
    b = df["drug_b"].astype(str)
    df["pair_a"] = np.where(a <= b, a, b)
    df["pair_b"] = np.where(a <= b, b, a)
    return df


def main():
    if CSV_OUT.exists() or JSON_OUT.exists():
        raise RuntimeError("H5 outputs already exist; refusing overwrite")

    m4 = pd.read_csv(M4_FILE)
    m0 = pd.read_csv(M0_FILE)

    m4 = m4[m4["test_view"] == "pooled"].copy()
    m0 = m0[m0["test_view"] == "pooled"].copy()

    m4 = canonicalise(m4)
    m0 = canonicalise(m0)

    # Build direct drug -> Reactome coverage through UniProt.
    dp = pd.read_parquet(
        DP_FILE,
        columns=["drugbank_id", "uniprot_id"],
    ).dropna()

    pp = pd.read_parquet(
        PP_FILE,
        columns=["uniprot_accession", "reactome_pathway_id"],
    ).dropna()

    reactome_proteins = set(pp["uniprot_accession"].astype(str))

    covered_drugs = set(
        dp.loc[
            dp["uniprot_id"].astype(str).isin(reactome_proteins),
            "drugbank_id",
        ].astype(str)
    )

    print("=== H-V2-5 PATHWAY COVERAGE ===")
    print(f"Reactome-covered drugs: {len(covered_drugs):,}")
    print("Definition: BOTH drugs covered = covered pair")
    print("H5 status: EXPLORATORY / directional")

    rows = []

    for seed in range(5):
        a = m4[m4["seed"] == seed][
            ["pair_a", "pair_b", "label", "prediction"]
        ].rename(columns={"prediction": "m4_prediction"})

        b = m0[m0["seed"] == seed][
            ["pair_a", "pair_b", "label", "prediction"]
        ].rename(columns={
            "label": "m0_label",
            "prediction": "m0_prediction",
        })

        x = a.merge(
            b,
            on=["pair_a", "pair_b"],
            how="inner",
            validate="one_to_one",
        )

        if len(x) != len(a) or len(x) != len(b):
            raise RuntimeError(
                f"Seed {seed}: M4/M0 pair sets do not align exactly: "
                f"M4={len(a)}, M0={len(b)}, merged={len(x)}"
            )

        if not np.array_equal(
            x["label"].to_numpy(),
            x["m0_label"].to_numpy(),
        ):
            raise RuntimeError(f"Seed {seed}: label mismatch")

        x["covered"] = (
            x["pair_a"].isin(covered_drugs)
            & x["pair_b"].isin(covered_drugs)
        )

        vals = {"seed": seed}

        for group, flag in [("covered", True), ("uncovered", False)]:
            q = x[x["covered"] == flag]
            y = q["label"].to_numpy()

            m4_ap = average_precision_score(
                y, q["m4_prediction"].to_numpy()
            )
            m0_ap = average_precision_score(
                y, q["m0_prediction"].to_numpy()
            )

            vals[f"n_{group}"] = len(q)
            vals[f"positives_{group}"] = int(y.sum())
            vals[f"m4_auprc_{group}"] = float(m4_ap)
            vals[f"m0_auprc_{group}"] = float(m0_ap)
            vals[f"delta_{group}"] = float(m4_ap - m0_ap)

        vals["contrast"] = (
            vals["delta_covered"] - vals["delta_uncovered"]
        )

        rows.append(vals)

        print(
            f"seed {seed}: "
            f"covered Δ={vals['delta_covered']:+.6f} "
            f"(n={vals['n_covered']:,}) | "
            f"uncovered Δ={vals['delta_uncovered']:+.6f} "
            f"(n={vals['n_uncovered']:,}) | "
            f"contrast={vals['contrast']:+.6f}"
        )

    out = pd.DataFrame(rows)
    contrast = out["contrast"].to_numpy(float)

    mean = float(contrast.mean())
    std = float(contrast.std(ddof=1))
    se = std / np.sqrt(len(contrast))

    t_stat, p_two = stats.ttest_1samp(contrast, 0.0)
    df = len(contrast) - 1
    crit = stats.t.ppf(0.975, df)
    ci = (mean - crit * se, mean + crit * se)

    # Directional claim is positive. Report one-sided p descriptively.
    if t_stat >= 0:
        p_directional = float(p_two / 2)
    else:
        p_directional = float(1 - p_two / 2)

    dz = float(mean / std) if std > 0 else float("inf")

    out.to_csv(CSV_OUT, index=False)

    summary = {
        "hypothesis": "H-V2-5",
        "status": "EXPLORATORY",
        "preregistered_direction":
            "delta_covered > delta_uncovered",
        "n_seeds": 5,
        "mean_delta_covered":
            float(out["delta_covered"].mean()),
        "mean_delta_uncovered":
            float(out["delta_uncovered"].mean()),
        "mean_contrast": mean,
        "std_contrast": std,
        "ci95_two_sided": [float(ci[0]), float(ci[1])],
        "paired_t": float(t_stat),
        "df": df,
        "p_two_sided_descriptive": float(p_two),
        "p_directional_descriptive": p_directional,
        "cohen_dz": dz,
        "direction_supported": bool(mean > 0),
        "strict_significance_threshold": None,
        "note":
            "Exploratory preregistered directional analysis. "
            "No strict significance threshold was preregistered."
    }

    JSON_OUT.write_text(json.dumps(summary, indent=2) + "\n")

    print("\n=== H-V2-5 SUMMARY ===")
    print(
        f"mean delta covered   = "
        f"{out['delta_covered'].mean():+.6f}"
    )
    print(
        f"mean delta uncovered = "
        f"{out['delta_uncovered'].mean():+.6f}"
    )
    print(f"contrast             = {mean:+.6f} ± {std:.6f}")
    print(f"95% CI               = [{ci[0]:+.6f}, {ci[1]:+.6f}]")
    print(f"paired t             = {t_stat:.6f}")
    print(f"two-sided p          = {p_two:.10g}")
    print(f"directional p        = {p_directional:.10g}")
    print(f"Cohen dz             = {dz:.6f}")
    print(f"DIRECTION SUPPORTED  = {mean > 0}")
    print("STATUS                = EXPLORATORY")
    print(f"WROTE {CSV_OUT}")
    print(f"WROTE {JSON_OUT}")


if __name__ == "__main__":
    main()
