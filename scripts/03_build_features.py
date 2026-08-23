#!/usr/bin/env python3
"""
Build molecular features and the leakage-safe DDI graph, and run the
pathway-edge leakage audit.

    python scripts/03_build_features.py
    python scripts/03_build_features.py --group-by scaffold --include-cyp-features

The leakage audit is the important output. It answers "how much of the label
can be recovered from the mechanistic rules alone?" - which is the bar the GNN
has to clear to be worth anything.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from ddinet.data import assemble, synthetic_fixture, split as split_mod
from ddinet.features.build import FeatureConfig, build_feature_bundle
from ddinet.features.ddi_graph import leakage_audit

REPORTS = Path(__file__).resolve().parents[1] / "reports"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--group-by", choices=("drug", "scaffold"), default="drug")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--bits", type=int, default=2048)
    ap.add_argument("--radius", type=int, default=2)
    ap.add_argument("--neg-ratio", type=float, default=1.0)
    ap.add_argument("--include-cyp-features", action="store_true",
                    help="CIRCULAR on the curated fixture - see docs/step2_features.md")
    ap.add_argument("--no-pathway-edges", action="store_true")
    args = ap.parse_args()

    pd.set_option("display.width", 200)

    drugs, pairs = synthetic_fixture.load_drugs(), synthetic_fixture.load_pairs()
    sp = split_mod.build_split(drugs, pairs, seed=args.seed, group_by=args.group_by)
    print(sp.report())

    cfg = FeatureConfig(
        fingerprint_radius=args.radius,
        fingerprint_bits=args.bits,
        include_cyp_features=args.include_cyp_features,
        include_pathway_edges=not args.no_pathway_edges,
    )
    bundle = build_feature_bundle(drugs, sp, cfg)
    print()
    print(bundle.report())

    print("\nFingerprint sanity (Tanimoto similarity):")
    from ddinet.features.fingerprints import tanimoto
    fps = bundle.fingerprints
    for a, b in (("simvastatin", "lovastatin"), ("amitriptyline", "nortriptyline"),
                 ("simvastatin", "metformin"), ("warfarin", "aspirin")):
        print(f"  {a:15s} vs {b:15s} : {tanimoto(fps[a].bits, fps[b].bits):.3f}")

    from ddinet.features.fingerprints import _cached_mol
    rates = [
        bundle.fingerprints[n].collision_rate(_cached_mol(s))
        for n, s in zip(bundle.drugs["name"], bundle.drugs["smiles"])
    ]
    print(f"\n  mean TRUE bit-collision rate across {len(rates)} drugs: "
          f"{sum(rates)/len(rates):.4f}")
    print("  (fraction of set bits carrying two chemically distinct substructures;")
    print("   bounds how specific a Step 5 substructure attribution can be)")

    ds = assemble.build_supervised_dataset(
        sp, set(pairs["pair_key"]),
        assemble.AssemblyConfig(neg_ratio=args.neg_ratio, seed=args.seed),
    )
    audit = leakage_audit(drugs, ds)

    print("\n" + "=" * 78)
    print("PATHWAY-EDGE LEAKAGE AUDIT")
    print("=" * 78)
    print("How much of the label is recoverable from mechanistic rules alone?")
    print("This is the baseline the GNN must beat to be adding value.\n")
    for bucket in ("train", "val_S2", "test_S2", "test_S3"):
        sub = audit[audit["bucket"] == bucket]
        if len(sub):
            print(f"[{bucket}]")
            print(sub.drop(columns="bucket").to_string(index=False))
            print()

    REPORTS.mkdir(parents=True, exist_ok=True)
    audit.to_csv(REPORTS / "leakage_audit.csv", index=False)
    print(f"Wrote {REPORTS / 'leakage_audit.csv'}")

    any_row = audit[(audit.edge_type == "ANY_PATHWAY_EDGE") & (audit.bucket == "test_S2")]
    if len(any_row):
        ba = float(any_row.iloc[0]["balanced_accuracy"])
        print(f"\nHEADLINE: rules-only balanced accuracy on test_S2 = {ba:.3f}")
        print("Quote this next to the model's score. A GNN that does not clearly")
        print("exceed it has not earned its complexity.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
