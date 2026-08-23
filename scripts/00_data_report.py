#!/usr/bin/env python3
"""
Print the data-provenance report: every source, its licence, its citation,
whether we have it locally, and the validation status of the curated seed set.

Run this first, and paste its output into your ISEF logbook. It is the answer
to "where did your data come from and are you allowed to use it?".

    python scripts/00_data_report.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ddinet.data import curated
from ddinet.data.download import RAW_DIR, _load_manifest
from ddinet.data.sources import SOURCES, citation_block


def main() -> int:
    print("=" * 78)
    print("DDI-Net  -  DATA PROVENANCE REPORT")
    print("=" * 78)

    manifest = _load_manifest()

    print("\n[1] EXTERNAL SOURCES\n")
    header = f"{'source':24s} {'access':13s} {'local?':8s} redistributable"
    print(header)
    print("-" * len(header))
    for key in sorted(SOURCES):
        src = SOURCES[key]
        if src.filename:
            present = (RAW_DIR / src.key / src.filename).exists()
        elif src.key == "ddinter":
            present = any((RAW_DIR / src.key).glob("*.csv")) if (RAW_DIR / src.key).exists() else False
        else:
            present = (RAW_DIR / src.key).exists()
        print(
            f"{src.key:24s} {src.access:13s} {'yes' if present else 'NO':8s} "
            f"{'yes' if src.redistributable else 'no (licence)'}"
        )

    if manifest:
        print("\n[2] DOWNLOAD MANIFEST (content hashes pin the exact release)\n")
        for key, entry in sorted(manifest.items()):
            print(
                f"  {key:24s} {entry['sha256'][:16]}...  "
                f"{entry['n_bytes']/1e6:8.2f} MB  fetched {entry['fetched_at']}"
            )
    else:
        print("\n[2] DOWNLOAD MANIFEST: empty - no external files fetched yet.")
        print("    Run scripts/01_download_data.py on an unrestricted network.")

    print("\n[3] CURATED SEED SET (offline fixture, always available)\n")
    report = curated.validate()
    for line in report.summary().splitlines():
        print("  " + line)

    drugs = curated.load_drugs()
    pairs = curated.load_pairs()
    print(f"\n  CYP enzymes represented : {', '.join(curated.cyp_vocabulary())}")
    print(f"  Transporters represented: {', '.join(curated.transporter_vocabulary())}")
    print(f"  Pharmacodynamic classes : {len(curated.pd_class_vocabulary())}")
    print(f"  Molecular weight range  : "
          f"{drugs['mol_weight'].min():.1f} - {drugs['mol_weight'].max():.1f} Da")
    n = len(drugs)
    print(f"  Interaction graph density: {len(pairs)}/{n*(n-1)//2} "
          f"= {100*len(pairs)/(n*(n-1)/2):.2f}% of all possible pairs")
    print("\n  Severity distribution:")
    for sev, count in pairs["severity"].value_counts().items():
        print(f"    {sev:10s} {count:4d}  ({100*count/len(pairs):.1f}%)")
    print("\n  Mechanism distribution:")
    for mech, count in pairs["mechanism"].value_counts().items():
        print(f"    {mech:22s} {count:4d}")

    print("\n" + "=" * 78)
    print(citation_block())
    print("=" * 78)

    print(
        "\nREMINDER: the curated set is a development fixture. Because its pairs\n"
        "were curated with mechanism in mind, headline performance numbers must\n"
        "come from DrugBank / DDInter / BioSNAP, not from this fixture.\n"
    )
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
