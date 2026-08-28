#!/usr/bin/env python3
"""
ChEMBL 36 SQLite -> compact Parquet extracts. Run ONCE.

WHY THIS EXISTS AS A SEPARATE STEP
------------------------------------
The database is several GB. Querying it during training would pay that cost on
every run and tie every experiment to a file that cannot be committed. This
script reads it once, applies the filters justified in
docs/CHEMBL_TABLE_MAP.md, and writes columnar files small enough to live beside
the code.

MEMORY
------
Nothing is loaded whole. `activities` is streamed in chunks and appended to a
Parquet writer, so peak memory is one chunk regardless of how many rows survive
the filters. The other tables are small enough to read at once, and the row
counts are printed so that assumption stays checkable rather than assumed.

BEFORE ANY ROW IS READ
-----------------------
`verify_schema` checks every table and column named in the table map. A ChEMBL
release that reorganised something produces a precise error instead of an
extraction that quietly returns less.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ddinet.adapters.chembl_adapter import (  # noqa: E402
    ACTIVITIES_SQL, ACTIVITY_TYPES, COMPOUNDS_SQL, MECHANISMS_SQL,
    MIN_ASSAY_CONFIDENCE, TARGETS_SQL, connect, load_uniprot_mapping_file,
    stream_query, verify_schema,
)

RAW = ROOT / "data" / "raw" / "chembl"
PROCESSED = ROOT / "data" / "processed"
REPORTS = ROOT / "reports"
HUMAN = "Homo sapiens"


def _write_streamed(conn, sql, params, path: Path, chunk_size: int) -> int:
    """Stream a query straight into one Parquet file.

    pyarrow's ParquetWriter is opened on the first chunk's schema, so an empty
    result writes no file at all rather than an empty one with a guessed
    schema - a file that exists but is empty is harder to diagnose than a
    missing one.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    writer = None
    total = 0
    try:
        for chunk in stream_query(conn, sql, params, chunk_size=chunk_size):
            table = pa.Table.from_pandas(chunk, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(path, table.schema, compression="zstd")
            writer.write_table(table)
            total += len(chunk)
            print(f"    {total:,} rows...", flush=True)
    finally:
        if writer is not None:
            writer.close()
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=RAW / "chembl_36.db")
    ap.add_argument("--uniprot-map", type=Path,
                    default=RAW / "chembl_36_uniprot_mapping.txt")
    ap.add_argument("--out", type=Path, default=PROCESSED)
    ap.add_argument("--organism", default=HUMAN)
    ap.add_argument("--chunk-size", type=int, default=200_000)
    ap.add_argument("--min-assay-confidence", type=int,
                    default=MIN_ASSAY_CONFIDENCE)
    ap.add_argument("--skip-activities", action="store_true",
                    help="mechanisms and targets only - much faster, and enough "
                         "for the first join experiments")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(exist_ok=True)
    started = time.time()
    conn = connect(args.db)

    print(f"Verifying schema of {args.db} ...", flush=True)
    schema_report = verify_schema(conn)
    print(f"  {len(schema_report['tables_checked'])} tables present with the "
          f"columns docs/CHEMBL_TABLE_MAP.md expects.\n")

    counts: dict[str, int] = {}

    # -- compounds: one row per structure, needed for the InChIKey join -----
    print("Extracting compounds ...", flush=True)
    path = args.out / "chembl_compounds.parquet"
    counts["compounds"] = _write_streamed(conn, COMPOUNDS_SQL, (), path,
                                          args.chunk_size)

    # -- targets: human single proteins with a UniProt accession -----------
    print("Extracting targets ...", flush=True)
    targets = pd.read_sql(TARGETS_SQL, conn, params=(args.organism,))
    targets.to_parquet(args.out / "chembl_targets.parquet", compression="zstd")
    counts["targets"] = len(targets)
    print(f"  {len(targets):,} rows, {targets['accession'].nunique():,} accessions")

    # -- mechanisms: the curated statements, the most valuable table -------
    print("Extracting mechanisms ...", flush=True)
    mechanisms = pd.read_sql(MECHANISMS_SQL, conn)
    mechanisms.to_parquet(args.out / "chembl_mechanisms.parquet", compression="zstd")
    counts["mechanisms"] = len(mechanisms)
    print(f"  {len(mechanisms):,} rows")

    # -- activities: the big one, streamed ---------------------------------
    if args.skip_activities:
        counts["activities"] = -1
        print("Skipping activities (--skip-activities).")
    else:
        print("Extracting activities (streamed) ...", flush=True)
        params = (*ACTIVITY_TYPES, args.min_assay_confidence, args.organism)
        counts["activities"] = _write_streamed(
            conn, ACTIVITIES_SQL, params,
            args.out / "chembl_activities.parquet", args.chunk_size)

    # -- the flat UniProt mapping, kept alongside the table-derived one -----
    if args.uniprot_map.exists():
        print("Extracting the flat UniProt mapping ...", flush=True)
        mapping = load_uniprot_mapping_file(args.uniprot_map)
        mapping.to_parquet(args.out / "chembl_uniprot_mapping.parquet",
                           compression="zstd")
        counts["uniprot_mapping"] = len(mapping)
        # Disagreement between the two routes is a signal, so measure it.
        via_tables = set(targets["accession"].dropna())
        via_file = set(mapping["accession"].dropna())
        counts["accessions_only_in_tables"] = len(via_tables - via_file)
        counts["accessions_only_in_flat_file"] = len(via_file - via_tables)
        print(f"  {len(mapping):,} rows; only-in-tables "
              f"{counts['accessions_only_in_tables']:,}, only-in-file "
              f"{counts['accessions_only_in_flat_file']:,}")
    else:
        counts["uniprot_mapping"] = -1
        print(f"  {args.uniprot_map} absent - skipped (the table route still works)")

    conn.close()
    summary = {
        "database": str(args.db),
        "organism": args.organism,
        "min_assay_confidence": args.min_assay_confidence,
        "activity_types": list(ACTIVITY_TYPES),
        "row_counts": counts,
        "output_files": sorted(p.name for p in args.out.glob("chembl_*.parquet")),
        "output_bytes": {p.name: p.stat().st_size
                         for p in sorted(args.out.glob("chembl_*.parquet"))},
        "elapsed_s": round(time.time() - started, 1),
        "schema_check": schema_report["tables_checked"],
    }
    out = REPORTS / "chembl_extraction_summary.json"
    out.write_text(json.dumps(summary, indent=2))
    print(f"\nWrote {out}")
    print(json.dumps(summary["row_counts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
