#!/usr/bin/env python3
"""
Fetch every automatically-downloadable source, and print precise instructions
for the ones that need a human.

    python scripts/01_download_data.py            # fetch what is fetchable
    python scripts/01_download_data.py --force    # re-download even if cached

Network-restricted environments (school networks, managed cloud runners, CI)
commonly block academic hosts. When that happens this script reports the
blocked host and moves on rather than dying - so you always learn the full
picture in one run instead of one host at a time.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ddinet.data import ddinter as ddinter_mod
from ddinet.data.download import (
    DownloadError,
    ManualDownloadRequired,
    NetworkPolicyError,
    ensure_source,
)
from ddinet.data.sources import SOURCES, directly_downloadable, manual_sources


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="re-download cached files")
    ap.add_argument("--skip-ddinter", action="store_true")
    args = ap.parse_args()

    ok, blocked, failed = [], [], []

    print("Fetching automatically-downloadable sources...\n")
    for src in directly_downloadable():
        try:
            result = ensure_source(src, force=args.force)
            print(f"  OK      {result}")
            ok.append(src.key)
        except NetworkPolicyError as exc:
            print(f"  BLOCKED {src.key}: host refused by network policy")
            blocked.append((src.key, str(exc).splitlines()[0]))
        except (DownloadError, ManualDownloadRequired) as exc:
            print(f"  FAILED  {src.key}: {str(exc).splitlines()[0]}")
            failed.append((src.key, str(exc).splitlines()[0]))

    if not args.skip_ddinter:
        print("\nFetching DDInter severity tables (one CSV per ATC letter)...")
        try:
            paths = ddinter_mod.download_all(force=args.force)
            print(f"  OK      ddinter: {len(paths)} files")
            ok.append("ddinter")
        except NetworkPolicyError:
            print("  BLOCKED ddinter: host refused by network policy")
            blocked.append(("ddinter", "network policy"))
        except DownloadError as exc:
            print(f"  FAILED  ddinter: {str(exc).splitlines()[0]}")
            failed.append(("ddinter", str(exc).splitlines()[0]))

    print("\n" + "=" * 78)
    print("SOURCES REQUIRING MANUAL ACTION")
    print("=" * 78)
    for src in manual_sources():
        print(f"\n{src.name}")
        print(f"  Licence : {src.licence}")
        print(f"  Get it  : {src.landing_page}")
        print(f"  Place at: data/raw/{src.key}/{src.filename}")
        print(f"  Why     : {src.notes}")

    print("\n" + "=" * 78)
    print(f"SUMMARY: {len(ok)} fetched, {len(blocked)} blocked, {len(failed)} failed")
    print("=" * 78)
    if blocked:
        print(
            "\nBlocked hosts are a NETWORK POLICY decision, not a bug. Retrying will\n"
            "not help. Run this script from an unrestricted network and copy the\n"
            "resulting data/raw/ directory across. In the meantime the entire\n"
            "pipeline still runs against the curated seed set:\n"
            "    python scripts/02_build_dataset.py --source fixture\n"
        )
        for key, reason in blocked:
            print(f"    - {key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
