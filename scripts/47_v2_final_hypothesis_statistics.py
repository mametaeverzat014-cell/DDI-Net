#!/usr/bin/env python3
"""
Final V2 H1-H5 statistical synthesis.

No model fitting and no new test inference.
Reads only frozen result files.

H1-H4:
  preregistered paired 5-seed tests.

H5:
  preregistered EXPLORATORY directional analysis.
  No strict significance threshold was preregistered.
  Its two-sided descriptive paired-t p-value is used conservatively as
  the fifth p-value for Holm-Bonferroni because section 9.5 requests
  correction across H-V2-1 through H-V2-5.

Holm implementation follows the standard step-down procedure.
"""

from pathlib import Path
import json

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]

PRIMARY = ROOT / "reports/v2_statistics/primary_h1_h3.csv"
M4 = ROOT / "reports/v2_final/v2_final_test.csv"
H4_RF = ROOT / "reports/v2_bio_controls/biological_degree_rf_test.csv"
H5_JSON = ROOT / "reports/v2_statistics/h5_pathway_coverage.json"

OUT = ROOT / "reports/v2_statistics"
CSV_OUT = OUT / "final_h1_h5_holm.csv"
JSON_OUT = OUT / "final_h1_h5_holm.json"

ALPHA = 0.05


def paired_stats(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)

    if len(a) != 5 or len(b) != 5:
        raise RuntimeError(
            f"Expected 5 paired seeds, got {len(a)} and {len(b)}"
        )

    d = a - b
    mean = float(d.mean())
    std = float(d.std(ddof=1))
    se = std / np.sqrt(len(d))

    t_stat, p = stats.ttest_rel(a, b)

    crit = stats.t.ppf(0.975, len(d) - 1)
    ci_low = mean - crit * se
    ci_high = mean + crit * se

    dz = mean / std if std > 0 else float("inf")

    return {
        "n_seeds": 5,
        "model_a_mean": float(a.mean()),
        "model_a_std": float(a.std(ddof=1)),
        "model_b_mean": float(b.mean()),
        "model_b_std": float(b.std(ddof=1)),
        "delta_mean": mean,
        "delta_std": std,
        "ci95_low": float(ci_low),
        "ci95_high": float(ci_high),
        "paired_t": float(t_stat),
        "paired_p": float(p),
        "cohen_dz": float(dz),
    }


def holm_adjust(pvalues):
    """
    Return Holm adjusted p-values and step-down rejection decisions.
    """
    pvalues = np.asarray(pvalues, dtype=float)
    m = len(pvalues)

    order = np.argsort(pvalues)
    sorted_p = pvalues[order]

    adjusted_sorted = np.empty(m, dtype=float)
    running_max = 0.0

    for rank, p in enumerate(sorted_p):
        adj = (m - rank) * p
        running_max = max(running_max, adj)
        adjusted_sorted[rank] = min(running_max, 1.0)

    adjusted = np.empty(m, dtype=float)
    adjusted[order] = adjusted_sorted

    # Holm step-down rejection.
    rejected = np.zeros(m, dtype=bool)
    still_rejecting = True

    for rank, idx in enumerate(order):
        threshold = ALPHA / (m - rank)

        if still_rejecting and pvalues[idx] <= threshold:
            rejected[idx] = True
        else:
            still_rejecting = False
            rejected[idx] = False

    return adjusted, rejected


def main():
    if CSV_OUT.exists() or JSON_OUT.exists():
        raise RuntimeError(
            "Final H1-H5 outputs already exist; refusing overwrite"
        )

    primary = pd.read_csv(PRIMARY)

    expected = {"H-V2-1", "H-V2-2", "H-V2-3"}
    found = set(primary["hypothesis"])

    if found != expected:
        raise RuntimeError(
            f"Unexpected H1-H3 set: {sorted(found)}"
        )

    rows = []

    # H1-H3: copy exact frozen statistics.
    for _, r in primary.iterrows():
        rows.append({
            "hypothesis": r["hypothesis"],
            "status": "CONFIRMATORY",
            "comparison": r["comparison"],
            "test_view": r["test_view"],
            "n_seeds": int(r["n_seeds"]),
            "model_a_mean": float(r["model_a_mean"]),
            "model_a_std": float(r["model_a_std"]),
            "model_b_mean": float(r["model_b_mean"]),
            "model_b_std": float(r["model_b_std"]),
            "delta_mean": float(r["delta_mean"]),
            "delta_std": float(r["delta_std"]),
            "ci95_low": float(r["ci95_low"]),
            "ci95_high": float(r["ci95_high"]),
            "paired_t": float(r["paired_t"]),
            "paired_p": float(r["paired_p"]),
            "cohen_dz": float(r["cohen_dz"]),
            "nominal_pass": bool(r["nominal_pass"]),
            "holm_p_source": "two-sided paired t-test",
        })

    # H4: reconstruct exact paired comparison from frozen M4 and
    # biological-degree RF per-seed test AUPRC.
    m4 = pd.read_csv(M4)
    rf = pd.read_csv(H4_RF)

    m4 = m4.sort_values("seed")
    rf = rf.sort_values("seed")

    if list(m4["seed"]) != list(range(5)):
        raise RuntimeError(
            f"Unexpected M4 seeds: {list(m4['seed'])}"
        )

    if list(rf["seed"]) != list(range(5)):
        raise RuntimeError(
            f"Unexpected biological-degree RF seeds: {list(rf['seed'])}"
        )

    h4 = paired_stats(
        m4["test_auprc"].to_numpy(),
        rf["test_auprc"].to_numpy(),
    )

    rows.append({
        "hypothesis": "H-V2-4",
        "status": "CONFIRMATORY",
        "comparison":
            "M4 true mean vs biological-degree-only RF",
        "test_view": "pooled drug-disjoint",
        **h4,
        "nominal_pass": bool(h4["paired_p"] < 0.05),
        "holm_p_source": "two-sided paired t-test",
    })

    # H5: already frozen exploratory analysis.
    h5 = json.loads(H5_JSON.read_text())

    rows.append({
        "hypothesis": "H-V2-5",
        "status": "EXPLORATORY",
        "comparison":
            "M4-GINE gain: pathway-covered vs pathway-uncovered",
        "test_view": "pooled drug-disjoint subgroup contrast",
        "n_seeds": int(h5["n_seeds"]),
        "model_a_mean": float(h5["mean_delta_covered"]),
        "model_a_std": np.nan,
        "model_b_mean": float(h5["mean_delta_uncovered"]),
        "model_b_std": np.nan,
        "delta_mean": float(h5["mean_contrast"]),
        "delta_std": float(h5["std_contrast"]),
        "ci95_low": float(h5["ci95_two_sided"][0]),
        "ci95_high": float(h5["ci95_two_sided"][1]),
        "paired_t": float(h5["paired_t"]),
        # Conservative choice for Holm.
        "paired_p": float(h5["p_two_sided_descriptive"]),
        "cohen_dz": float(h5["cohen_dz"]),
        # H5 has no preregistered strict threshold.
        "nominal_pass": np.nan,
        "holm_p_source":
            "two-sided descriptive paired t-test; "
            "H5 remains exploratory",
    })

    out = pd.DataFrame(rows).sort_values("hypothesis").reset_index(drop=True)

    if list(out["hypothesis"]) != [
        "H-V2-1",
        "H-V2-2",
        "H-V2-3",
        "H-V2-4",
        "H-V2-5",
    ]:
        raise RuntimeError("H1-H5 ordering/integrity failure")

    adjusted, rejected = holm_adjust(out["paired_p"].to_numpy())

    out["holm_adjusted_p"] = adjusted
    out["holm_reject_0_05"] = rejected

    # H1 and H3 additionally require d > 0.5.
    conclusions = []

    for _, r in out.iterrows():
        h = r["hypothesis"]

        if h in {"H-V2-1", "H-V2-3"}:
            supported = bool(
                r["holm_reject_0_05"]
                and r["cohen_dz"] > 0.5
                and r["delta_mean"] > 0
            )
        elif h in {"H-V2-2", "H-V2-4"}:
            supported = bool(
                r["holm_reject_0_05"]
                and r["delta_mean"] > 0
            )
        else:
            # H5 is never promoted to confirmatory pass/fail.
            supported = None

        conclusions.append(supported)

    out["joint_conclusion_supported"] = conclusions

    OUT.mkdir(parents=True, exist_ok=True)
    out.to_csv(CSV_OUT, index=False)

    payload = {
        "alpha": ALPHA,
        "correction": "Holm-Bonferroni across H-V2-1 through H-V2-5",
        "h5_handling": {
            "status": "EXPLORATORY",
            "strict_threshold": None,
            "holm_p":
                "two-sided descriptive paired t-test p-value",
            "directional_p":
                float(h5["p_directional_descriptive"]),
            "direction_supported":
                bool(h5["direction_supported"]),
            "reason":
                "Preregistration requests five p-values for Holm while "
                "also specifying H5 as exploratory with no strict "
                "significance threshold. The two-sided descriptive "
                "paired-t p-value is therefore used conservatively for "
                "the multiplicity calculation without converting H5 "
                "into a confirmatory hypothesis.",
        },
        "results": out.replace({np.nan: None}).to_dict(
            orient="records"
        ),
    }

    JSON_OUT.write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n"
    )

    print("=== FINAL V2 H1-H5 + HOLM-BONFERRONI ===\n")

    for _, r in out.iterrows():
        print(
            f"{r['hypothesis']}: "
            f"delta={r['delta_mean']:+.6f} | "
            f"p={r['paired_p']:.10g} | "
            f"Holm p={r['holm_adjusted_p']:.10g} | "
            f"Holm reject={bool(r['holm_reject_0_05'])} | "
            f"status={r['status']}"
        )

    print("\nJoint confirmatory conclusions:")
    for _, r in out[out["status"] == "CONFIRMATORY"].iterrows():
        print(
            f"  {r['hypothesis']}: "
            f"{'SUPPORTED' if r['joint_conclusion_supported'] else 'NOT SUPPORTED'}"
        )

    h5r = out[out["hypothesis"] == "H-V2-5"].iloc[0]
    print(
        "\nH-V2-5: EXPLORATORY; "
        f"direction supported = {bool(h5['direction_supported'])}; "
        f"contrast={h5r['delta_mean']:+.6f}"
    )

    print(f"\nWROTE {CSV_OUT}")
    print(f"WROTE {JSON_OUT}")


if __name__ == "__main__":
    main()
