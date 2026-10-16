#!/usr/bin/env python3
"""Build data/reference_sets/crescenddi/ from the pinned CRESCENDDI data records.

    python scripts/data/ingest_crescenddi.py                # fetch (git, pinned commit) + build
    python scripts/data/ingest_crescenddi.py --from-dir D   # use a local copy (same checksums enforced)

The raw spreadsheets are cached under data/raw/crescenddi/<commit>/ (git-ignored).
Only the derived index (DrugBank-keyed pairs, MedDRA event, which compendium
text the event came from; no severity ratings) and its manifest are committed.
Drug names are mapped with the evidence layer's own lexicon, so the evidence
artifact must exist (python -m serving.evidence.build).
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from ddinet.data import crescenddi as cr
from ddinet.data.git_fetch import fetch, verify
from serving.evidence.store import EvidenceStore

OUT = ROOT / "data" / "reference_sets" / "crescenddi"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-dir", type=Path, help="directory holding data_records/*.xlsx at the pinned commit")
    ap.add_argument("--date", default=dt.date.today().isoformat(), help="generation date for the manifest")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    src_dir = args.from_dir or fetch(cr.SPEC)
    inputs = verify(cr.SPEC, src_dir)
    store = EvidenceStore.load()

    def lookup(name: str):
        e, how = store.lexicon.lookup_name(name)
        return (e.id, how) if e else (None, None)

    payload = cr.build_index(cr.read_xlsx(src_dir / f"data_records/{cr.POSITIVE}"),
                             cr.read_xlsx(src_dir / f"data_records/{cr.NEGATIVE}"), lookup)
    m = cr.write(payload, args.out, inputs, args.date)
    s = m["stats"]
    print(f"rows read {s['rows_read']}, rejected {s['rows_rejected_by_schema']}; "
          f"drug names mapped {s['drug_names_mapped']}/{s['drug_names']}; dropped {s['dropped']}; "
          f"conflicts removed {s['positive_negative_conflicts_removed']}; records {s['records']}; "
          f"positive pairs {s['distinct_pairs_positive']}")
    print(f"wrote {args.out / m['output']['file']} ({m['output']['bytes']} bytes, sha256 {m['output']['sha256'][:16]}…)")


if __name__ == "__main__":
    main()
