#!/usr/bin/env python3
"""
The full evaluation study: cross-validated baselines, architecture comparison,
ablations, and (network permitting) FAERS external validation.

    python scripts/05_evaluate.py                     # everything
    python scripts/05_evaluate.py --skip-ablations    # faster
    python scripts/05_evaluate.py --folds 10

Everything is cross-validated over drug-disjoint folds, because the dominant
source of variance is WHICH DRUGS were held out - not weight initialisation.
Every model in a fold sees the identical split, negatives and features.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from ddinet.data import synthetic_fixture
from ddinet.eval.baselines import default_baselines
from ddinet.eval.crossval import CVResult, make_gnn_factory, run_cross_validation

REPORTS = Path(__file__).resolve().parents[1] / "reports"


def section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def _fixture_warning() -> None:
    """Print the prohibition banner when running against the synthetic fixture.

    Without this the code contradicts the documentation: LIMITATIONS.md and
    reports/ANNULLED.md say metrics from the fixture are void, while the script
    would happily print a results table that looks authoritative. Anything that
    prints a metric has to say what it was computed on.
    """
    print("\n" + "!" * 78)
    print("!! SYNTHETIC FIXTURE - EVERY NUMBER BELOW IS VOID")
    print("!! Source: tests/fixtures/synthetic_ddi/ (LLM-generated, no citable source)")
    print("!! These outputs exercise code paths only. Reporting them is prohibited.")
    print("!! See LIMITATIONS.md and reports/ANNULLED.md")
    print("!" * 78 + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--neg-ratio", type=float, default=3.0)
    ap.add_argument("--group-by", choices=("drug", "scaffold"), default="drug")
    ap.add_argument("--epochs", type=int, default=200)
    ap.add_argument("--patience", type=int, default=50)
    ap.add_argument("--dangerous-only", action="store_true")
    ap.add_argument("--skip-architectures", action="store_true")
    ap.add_argument("--skip-ablations", action="store_true")
    ap.add_argument("--skip-faers", action="store_true")
    args = ap.parse_args()

    _fixture_warning()

    pd.set_option("display.width", 220)
    REPORTS.mkdir(parents=True, exist_ok=True)
    drugs, pairs = synthetic_fixture.load_drugs(), synthetic_fixture.load_pairs()

    common = dict(
        n_folds=args.folds, seed=args.seed, group_by=args.group_by,
        neg_ratio=args.neg_ratio, dangerous_only=args.dangerous_only,
    )
    gnn_kwargs = dict(epochs=args.epochs, patience=args.patience)
    all_rows: list[pd.DataFrame] = []

    # ---- 1. Baselines vs the default model -------------------------------
    section(f"1. BASELINES vs DDI-Net  ({args.folds}-fold drug-disjoint CV)")
    main_result = run_cross_validation(
        drugs, pairs,
        gnn_factory=make_gnn_factory(architecture="gat", **gnn_kwargs),
        verbose=True, **common,
    )
    all_rows.append(main_result.rows)

    for bucket in ("test_S2", "test_S3"):
        print(f"\n--- {bucket}: AUPRC, mean +/- SD over folds ---")
        print(main_result.formatted(bucket, "auprc").to_string(index=False))
        print(f"\n--- {bucket}: AUC-ROC ---")
        print(main_result.formatted(bucket, "auc_roc").to_string(index=False))

    section("2. PAIRED COMPARISONS (same folds, so shared difficulty cancels)")
    comparisons = []
    model_name = "DDI-Net[gat]"
    for other in ("rules", "similarity",
                  "random_forest[symmetric]", "random_forest[concat]",
                  "logistic_regression[symmetric]", "logistic_regression[concat]",
                  "degree"):
        for bucket in ("test_S2", "test_S3"):
            c = main_result.paired_comparison(model_name, other,
                                              bucket=bucket, metric="auprc")
            if "error" in c:
                continue
            comparisons.append(c)
            p = f" wilcoxon p={c['wilcoxon_p']:.4f}" if "wilcoxon_p" in c else ""
            print(f"  [{bucket}] vs {other:20s} mean diff {c['mean_difference']:+.3f}  "
                  f"wins {c['folds_a_wins']}/{c['n_folds']}{p}")
    print("\n  NOTE: at 5 folds the smallest attainable Wilcoxon p is 0.0625, so no")
    print("  result can reach p<0.05. These are DESCRIPTIVE, not confirmatory.")

    # ---- 3. Architecture comparison --------------------------------------
    if not args.skip_architectures:
        section("3. ARCHITECTURE COMPARISON (GAT vs GraphSAGE vs GCN)")
        for arch in ("sage", "gcn"):
            print(f"\n>>> {arch}")
            res = run_cross_validation(
                drugs, pairs,
                baselines=[],
                gnn_factory=make_gnn_factory(architecture=arch, **gnn_kwargs),
                verbose=True, **common,
            )
            all_rows.append(res.rows)

    # ---- 4. Ablations ----------------------------------------------------
    if not args.skip_ablations:
        section("4. ABLATIONS (what is each component actually contributing?)")
        ablations = [
            ("molecular branch only", dict(use_graph_branch=False)),
            ("graph branch only", dict(use_molecular_branch=False)),
        ]
        for label, flags in ablations:
            print(f"\n>>> {label}")
            res = run_cross_validation(
                drugs, pairs,
                baselines=[],
                gnn_factory=make_gnn_factory(architecture="gat", **gnn_kwargs, **flags),
                verbose=True, **common,
            )
            all_rows.append(res.rows)

    # ---- 5. Consolidated table -------------------------------------------
    combined = CVResult(pd.concat(all_rows, ignore_index=True))
    section("5. CONSOLIDATED RESULTS")
    for bucket in ("test_S2", "test_S3"):
        print(f"\n--- {bucket}: AUPRC ---")
        print(combined.formatted(bucket, "auprc").to_string(index=False))

    combined.rows.to_csv(REPORTS / "cv_results.csv", index=False)
    (REPORTS / "paired_comparisons.json").write_text(
        json.dumps(comparisons, indent=2, default=float)
    )
    print(f"\nWrote {REPORTS/'cv_results.csv'} and {REPORTS/'paired_comparisons.json'}")

    # ---- 6. FAERS --------------------------------------------------------
    if not args.skip_faers:
        section("6. EXTERNAL VALIDATION: openFDA FAERS")
        from ddinet.eval.faers import FAERSClient

        client = FAERSClient()
        probe = client.count_reports('patient.drug.medicinalproduct:"warfarin"')
        if probe is None:
            print("  openFDA is not reachable from this machine.")
            print("  This is a network-policy limitation, not a code failure - the")
            print("  harness and its statistics are implemented and unit-tested.")
            print("\n  To run it from an unrestricted network:")
            print("      python scripts/06_faers_validation.py --top 50")
            print("  Results cache to data/raw/openfda_faers/cache/, so the analysis")
            print("  becomes reproducible offline once the cache is warm.")
        else:
            print(f"  openFDA reachable: {probe:,} reports mention warfarin.")
            print("  Run scripts/06_faers_validation.py for the full analysis.")

    section("HEADLINE")
    top = combined.formatted("test_S2", "auprc")
    if len(top):
        print(f"\nBest on test_S2 (AUPRC): {top.iloc[0]['model']} = {top.iloc[0]['auprc']}")
        print("\nQuote AUPRC with the prevalence beside it "
              f"(= {1/(1+args.neg_ratio):.3f} here), and quote the")
        print("cross-validated SD. A single-split number is not a result.")
    _fixture_warning()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
