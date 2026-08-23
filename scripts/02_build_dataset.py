#!/usr/bin/env python3
"""
Build the labelled, split, leakage-checked supervised dataset.

    python scripts/02_build_dataset.py --source fixture
    python scripts/02_build_dataset.py --source fixture --group-by scaffold
    python scripts/02_build_dataset.py --source drugbank --neg-ratio 10

Writes to data/processed/:
    drugs.csv        one row per drug, with structure + annotations
    dataset.csv      one row per labelled example, with bucket and setting
    split.json       exactly which drugs went where (so it is reproducible)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from ddinet.data import assemble, synthetic_fixture, split as split_mod
from ddinet.data.download import RAW_DIR

PROCESSED = Path(__file__).resolve().parents[1] / "data" / "processed"


def load_fixture() -> tuple[pd.DataFrame, pd.DataFrame]:
    report = synthetic_fixture.validate()
    print(report.summary())
    if not report.ok:
        raise SystemExit("Fixture failed self-consistency check.")
    print("\n  *** WARNING: this is the SYNTHETIC test fixture, not data. ***")
    print("  Metrics computed from it are meaningless and must not be reported.")
    return synthetic_fixture.load_drugs(), synthetic_fixture.load_pairs()


def load_drugbank() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Assemble drugs+pairs from the licensed DrugBank XML, graded by DDInter."""
    from ddinet.data import ddinter as ddinter_mod
    from ddinet.data.drugbank import build_tables

    xml = RAW_DIR / "drugbank_full" / "drugbank_full_database.xml"
    if not xml.exists():
        raise SystemExit(
            f"DrugBank XML not found at {xml}\n"
            "It requires a free academic licence; see scripts/01_download_data.py."
        )
    print(f"Parsing {xml} (streaming; this takes a few minutes)...")
    drugs, inter = build_tables(xml)
    print(f"  parsed {len(drugs)} small molecules, {len(inter)} unique interactions")

    drugs = drugs.rename(columns={"name": "raw_name"})
    drugs["name"] = drugs["raw_name"].str.strip().str.lower()
    id_to_name = dict(zip(drugs["drugbank_id"], drugs["name"]))

    pairs = pd.DataFrame(
        {
            "drug_a": inter["drug_a_id"].map(id_to_name),
            "drug_b": inter["drug_b_id"].map(id_to_name),
            "mechanism": inter["mechanism"],
            "mediator": inter["direction"],
            "clinical_effect": inter["adverse_effect"],
        }
    ).dropna(subset=["drug_a", "drug_b"])

    # Severity comes from DDInter, joined by lower-cased drug name.
    try:
        grades = ddinter_mod.load_ddinter()
        key = {(r.drug_a, r.drug_b): r.severity for r in grades.itertuples()}
        pairs["severity"] = [
            key.get(tuple(sorted((a, b))), "ungraded")
            for a, b in zip(pairs["drug_a"], pairs["drug_b"])
        ]
        n_graded = int((pairs["severity"] != "ungraded").sum())
        print(f"  DDInter graded {n_graded}/{len(pairs)} pairs "
              f"({100*n_graded/max(len(pairs),1):.1f}%)")
    except FileNotFoundError:
        print("  [warn] DDInter not present - no severity grades. "
              "Binary interaction prediction only.")
        pairs["severity"] = "ungraded"

    keys = [tuple(sorted((a, b))) for a, b in zip(pairs["drug_a"], pairs["drug_b"])]
    pairs["drug_a"] = [k[0] for k in keys]
    pairs["drug_b"] = [k[1] for k in keys]
    pairs["pair_key"] = keys
    pairs["severity_rank"] = pairs["severity"].map(
        {s: i for i, s in enumerate(synthetic_fixture.SEVERITY_ORDER)}
    ).fillna(-1).astype(int)
    pairs["is_dangerous"] = (pairs["severity"] == "major").astype(int)
    pairs["mechanism_family"] = pairs["mechanism"].str.split("_").str[0]
    pairs = pairs.drop_duplicates(subset=["drug_a", "drug_b"]).reset_index(drop=True)

    keep = set(pairs["drug_a"]) | set(pairs["drug_b"])
    drugs = drugs.loc[drugs["name"].isin(keep)].drop_duplicates("name").reset_index(drop=True)
    return drugs, pairs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", choices=("fixture", "drugbank"), default="fixture")
    ap.add_argument("--group-by", choices=("drug", "scaffold"), default="drug")
    ap.add_argument("--generic-scaffold", action="store_true",
                    help="strictest split: erase atom types in the scaffold")
    ap.add_argument("--neg-ratio", type=float, default=1.0)
    ap.add_argument("--strategy", choices=("uniform", "degree_matched"),
                    default="degree_matched")
    ap.add_argument("--dangerous-only", action="store_true",
                    help="binary target = MAJOR severity; drops moderate/minor")
    ap.add_argument("--val-fraction", type=float, default=0.15)
    ap.add_argument("--test-fraction", type=float, default=0.15)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=PROCESSED)
    args = ap.parse_args()

    print("=" * 78)
    print(f"BUILDING DATASET  (source={args.source})")
    print("=" * 78 + "\n")

    drugs, pairs = load_fixture() if args.source == "fixture" else load_drugbank()

    print(f"\nSplitting by {args.group_by} (seed={args.seed})...")
    sp = split_mod.build_split(
        drugs, pairs,
        val_fraction=args.val_fraction,
        test_fraction=args.test_fraction,
        seed=args.seed,
        group_by=args.group_by,
        generic_scaffold=args.generic_scaffold,
    )
    print(sp.report())

    cfg = assemble.AssemblyConfig(
        neg_ratio=args.neg_ratio,
        strategy=args.strategy,
        seed=args.seed,
        dangerous_only=args.dangerous_only,
    )
    print(f"\nSampling negatives (strategy={cfg.strategy}, ratio=1:{cfg.neg_ratio:g})...")
    all_keys = set(pairs["pair_key"])
    dataset = assemble.build_supervised_dataset(sp, all_keys, cfg)
    assemble.verify_no_negative_is_positive(dataset, all_keys)
    print(assemble.dataset_summary(dataset))

    args.out.mkdir(parents=True, exist_ok=True)
    drug_cols = [c for c in drugs.columns if c != "mol"]
    drugs[drug_cols].to_csv(args.out / "drugs.csv", index=False)
    dataset.to_csv(args.out / "dataset.csv", index=False)
    (args.out / "split.json").write_text(json.dumps(
        {
            "source": args.source,
            "group_by": args.group_by,
            "generic_scaffold": args.generic_scaffold,
            "seed": args.seed,
            "val_fraction": args.val_fraction,
            "test_fraction": args.test_fraction,
            "assembly": {
                "neg_ratio": cfg.neg_ratio,
                "strategy": cfg.strategy,
                "dangerous_only": cfg.dangerous_only,
            },
            "train_drugs": sorted(sp.train_drugs),
            "val_drugs": sorted(sp.val_drugs),
            "test_drugs": sorted(sp.test_drugs),
            "n_discarded_pairs": int(len(sp.discarded)) if sp.discarded is not None else 0,
        },
        indent=2,
    ))

    print(f"\nWrote:\n  {args.out/'drugs.csv'}\n  {args.out/'dataset.csv'}\n  {args.out/'split.json'}")
    print("\nLeakage checks passed: drug partitions disjoint, no negative is a "
          "documented interaction.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
