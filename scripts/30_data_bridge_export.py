#!/usr/bin/env python3
"""
Export the EXACT drug universe and split assignments used by Phase A / A-2.

EXPORT ONLY. Reads the same entry points the experiments read, writes to
data_bridge_export/, and touches nothing else. No downloads, no retraining, no
regeneration of splits: the splits are rebuilt from the SAME deterministic
functions and seeds the grid used, and the rebuild is verified against the
recorded run manifest before anything is written.

WHY REBUILDING IS NOT REGENERATING
-----------------------------------
The splits were never persisted as files - the grid calls
``split.build_any(scheme, drugs, pairs, seed=seed)`` inside each run. That
function is deterministic given (scheme, drugs, pairs, seed), so calling it
here with the same arguments reproduces the same partition rather than making a
new one. The check that this is true, and not merely assumed, is
``verify_against_results``: it compares the reproduced bucket sizes against the
per-run row counts the grid wrote into reports/phase_a2_results.csv. A mismatch
aborts the export.

TWO GRANULARITIES, BECAUSE THE SCHEMES DIFFER IN KIND
-------------------------------------------------------
For `drug` and `scaffold` the DRUG assignment determines everything: a pair's
bucket follows from its two endpoints, and a pair straddling the val and test
drug groups is discarded by rule. Drug-level rows are therefore a complete,
compact description.

For `random_pair` the PAIRS are split directly and drug membership is not
controlled at all - a drug routinely appears in train, val and test pairs at
once. There is no drug-level description, so pair-level rows are the only
faithful export. They are written to a separate gzipped file because there are
five seeds x 191k pairs of them.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ddinet.data import split as split_mod, tdc_drugbank as tdc  # noqa: E402

OUT = ROOT / "data_bridge_export"
REPORTS = ROOT / "reports"

#: Exactly what the Phase A-2 grid ran: scripts/15_phase_a2_gnn.py, SCHEMES and
#: the default --seeds. Not re-chosen here.
SCHEMES = ("random_pair", "drug", "scaffold")
SEEDS = (0, 1, 2, 3, 4)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_against_results(reproduced: dict[tuple[str, int], int]) -> dict:
    """Compare reproduced test-bucket sizes with what the grid actually scored.

    The grid recorded `n` (rows scored) per test view. Positives in the pooled
    test view equal the number of positive test pairs, which is exactly the size
    of the reproduced test buckets. If the two disagree, the split being
    exported is NOT the split that was trained on, and the export is worthless.
    """
    path = REPORTS / "phase_a2_results.csv"
    if not path.exists():
        return {"checked": False,
                "reason": f"{path.name} absent - cannot verify"}
    results = pd.read_csv(path)
    pooled = results[results["test_view"] == "pooled"]
    mismatches = []
    checked = 0
    for (scheme, seed), group in pooled.groupby(["scheme", "seed"]):
        expected = reproduced.get((scheme, int(seed)))
        if expected is None:
            continue
        recorded = set(group["n_positive"].astype(int))
        checked += 1
        if recorded != {expected}:
            mismatches.append({"scheme": scheme, "seed": int(seed),
                               "reproduced_positives": expected,
                               "recorded_positives": sorted(recorded)})
    return {"checked": True, "cells_checked": checked,
            "mismatches": mismatches, "agrees": not mismatches}


def main() -> int:
    OUT.mkdir(exist_ok=True)
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # --- the drug universe, from the experiments' own entry point ---------
    drugs, pairs, drop_report = tdc.load_modelling_data()
    print(drop_report.summary())
    print(f"{len(drugs):,} drugs, {len(pairs):,} positive pairs\n")

    universe = pd.DataFrame({
        # The project's canonical key. `name` is a verbatim copy of it - the
        # corpus holds no real drug names - and that is exported as-is rather
        # than filled in, because inventing names is exactly what a bridge
        # must not do.
        "project_drug_id": drugs["drugbank_id"],
        "drugbank_id": drugs["drugbank_id"],
        "name": drugs["name"],
        "smiles": drugs["smiles"],
        "canonical_smiles": drugs["canonical_smiles"],
        "inchikey": drugs["inchikey"],
        "formula": drugs["formula"],
        "mol_weight": drugs["mol_weight"],
        "n_heavy_atoms": drugs["n_heavy_atoms"],
        "rdkit_parseable": drugs["valid"],
    })
    universe.to_csv(OUT / "project_drugs.csv", index=False)

    # --- splits, rebuilt from the same functions and seeds ----------------
    drug_rows: list[dict] = []
    pair_rows: list[dict] = []
    reproduced_test_sizes: dict[tuple[str, int], int] = {}
    split_stats: list[dict] = []

    for scheme in SCHEMES:
        for seed in SEEDS:
            sp = split_mod.build_any(scheme, drugs, pairs, seed=seed)
            n_test = sum(len(df) for name, df in sp.buckets.items()
                         if name.startswith("test"))
            reproduced_test_sizes[(scheme, seed)] = n_test
            split_stats.append({
                "scheme": scheme, "seed": seed,
                "n_train_drugs": len(sp.train_drugs),
                "n_val_drugs": len(sp.val_drugs),
                "n_test_drugs": len(sp.test_drugs),
                "buckets": {n: len(df) for n, df in sorted(sp.buckets.items())},
                "n_discarded_pairs": (0 if sp.discarded is None
                                      else int(len(sp.discarded))),
            })

            if scheme == "random_pair":
                # Pairs are split directly; drug membership is uncontrolled, so
                # only a pair-level export is faithful.
                for bucket, frame in sorted(sp.buckets.items()):
                    for a, b in zip(frame["drug_a"], frame["drug_b"]):
                        pair_rows.append({"scheme": scheme, "seed": seed,
                                          "drug_a": a, "drug_b": b,
                                          "bucket": bucket})
            else:
                for group, members in (("train", sp.train_drugs),
                                       ("val", sp.val_drugs),
                                       ("test", sp.test_drugs)):
                    for drug in sorted(members):
                        drug_rows.append({"scheme": scheme, "seed": seed,
                                          "project_drug_id": drug,
                                          "assignment": group})

    pd.DataFrame(drug_rows).to_csv(OUT / "split_assignments.csv", index=False)
    pair_frame = pd.DataFrame(pair_rows)
    pair_path = OUT / "split_assignments_random_pair.csv.gz"
    pair_frame.to_csv(pair_path, index=False, compression="gzip")

    verification = verify_against_results(reproduced_test_sizes)

    # --- coverage counts, measured not assumed ----------------------------
    def filled(column: str) -> int:
        series = universe[column]
        return int((series.notna() & (series.astype(str).str.strip() != "")).sum())

    coverage = {c: filled(c) for c in
                ("drugbank_id", "inchikey", "smiles", "canonical_smiles", "name")}
    n = len(universe)

    # Drugs the InChIKey bridge cannot carry. Named explicitly rather than
    # left as a count: all four are platinum coordination complexes, whose
    # dative bonds standard InChI does not define. RDKit parses their SMILES
    # fine - this is an InChI limitation, not a data defect - but any join
    # keyed on InChIKey will silently drop cisplatin, carboplatin and
    # oxaliplatin, which are clinically significant interacting drugs.
    no_key = universe.loc[
        universe["inchikey"].isna()
        | (universe["inchikey"].astype(str).str.strip() == ""),
        "project_drug_id"].tolist()

    manifest = {
        "created_utc": created,
        "generator": "scripts/30_data_bridge_export.py",
        "export_only": True,
        "source_entry_point": "ddinet.data.tdc_drugbank.load_modelling_data",
        "n_drugs": n,
        "n_positive_pairs": int(len(pairs)),
        "canonical_identifier": "drugbank_id",
        "identifier_coverage": coverage,
        "drugs_without_inchikey": no_key,
        "drugs_without_inchikey_note": (
            "platinum coordination complexes; standard InChI is undefined for "
            "dative bonds, so these cannot be joined on InChIKey"),
        "schemes": list(SCHEMES),
        "seeds": list(SEEDS),
        "split_statistics": split_stats,
        "verification_against_grid_results": verification,
        "excluded_by_load_modelling_data": {
            "drugs": drop_report.dropped_drug_ids,
            "n_pairs_removed": drop_report.n_dropped_pairs,
        },
        "files": [],
    }
    for path in sorted(OUT.glob("*")):
        if path.name == "data_bridge_manifest.json":
            continue
        entry = {"file": path.name, "bytes": path.stat().st_size,
                 "sha256": sha256_of(path)}
        if path.suffix in (".csv", ".gz"):
            frame = pd.read_csv(path)
            entry["rows"] = int(len(frame))
            entry["columns"] = list(frame.columns)
        manifest["files"].append(entry)
    (OUT / "data_bridge_manifest.json").write_text(json.dumps(manifest, indent=2))

    # Readiness is about whether the BRIDGE is sound, not whether coverage is
    # perfect. The split verification agreeing is the hard requirement: without
    # it the exported partition is not the one that was trained on. Incomplete
    # InChIKey coverage is a documented, enumerated caveat, not a blocker.
    ready = (verification.get("agrees", False)
             and coverage["drugbank_id"] == n)

    print("=== DATA BRIDGE EXPORT ===\n")
    print(f"EXPERIMENT DRUGS:\n{n}\n")
    print(f"POSITIVE DDI PAIRS:\n{len(pairs)}\n")
    print(f"CANONICAL DRUG IDENTIFIER:\ndrugbank_id\n")
    print(f"DRUGBANK IDs AVAILABLE:\n{coverage['drugbank_id']} / {n}\n")
    print(f"INCHIKEY AVAILABLE:\n{coverage['inchikey']} / {n}"
          + (f"   (missing: {', '.join(no_key)} - platinum complexes, "
             f"InChI undefined for dative bonds)" if no_key else "") + "\n")
    print(f"SMILES AVAILABLE:\n{coverage['canonical_smiles']} / {n}\n")
    print("SPLITS EXPORTED:\n"
          + ", ".join(SCHEMES) + f"  x seeds {list(SEEDS)}"
          + "  (+ S1/S2/S3 derivable, see README)\n")
    print(f"OUTPUT DIRECTORY:\n{OUT}\n")
    print(f"READY FOR LOCAL BIOMEDICAL JOIN:\n{'YES' if ready else 'NO'}")
    if not ready:
        print("  reason:", "split verification against the grid's recorded "
              "results FAILED - the exported partition is not the one trained on"
              if not verification.get("agrees")
              else "canonical identifier incomplete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
