#!/usr/bin/env python3
"""
Build the biomedical knowledge store from whatever sources are present, map it
onto the corpus, and audit it.

WHAT IT DOES WITH MISSING SOURCES
-----------------------------------
Runs on what is there and says plainly what is not. An absent source is
reported as absent - never as zero rows, and never fabricated. The summary
names every adapter and whether it ran, so a reader can tell "ChEMBL
contributed nothing" from "ChEMBL was not present".

OUTPUTS
-------
    reports/biomedical_data_quality.json    the audit (task 9)
    reports/chembl_drugbank_mapping.csv     per-drug mapping, when ChEMBL is
                                            present (task 6)
    reports/chembl_mapping_summary.json     match counts for the same

DOES NOT TOUCH the Phase A-2 experiment: it reads only data/raw and
data/processed and writes only the three files above.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ddinet.adapters import SourceUnavailable  # noqa: E402
from ddinet.adapters.chembl_adapter import ChemblAdapter  # noqa: E402
from ddinet.adapters.drugcentral_adapter import DrugCentralAdapter  # noqa: E402
from ddinet.adapters.faers_adapter import FaersAdapter  # noqa: E402
from ddinet.adapters.reactome_adapter import (  # noqa: E402
    ReactomeFIAdapter, ReactomeUniProtAdapter,
)
from ddinet.adapters.sider_adapter import SiderAdapter  # noqa: E402
from ddinet.adapters.uniprot_adapter import UniProtAdapter  # noqa: E402
from ddinet.data.tdc_drugbank import load_drugs  # noqa: E402
from ddinet.integration.identifiers import (  # noqa: E402
    IdentifierMap, Mapping, MatchQuality, build_compound_map,
    canonical_compound_id, normalise,
)
from ddinet.integration.quality import (  # noqa: E402
    audit_compounds, audit_identifier_map, audit_store,
)
from ddinet.integration.schema import EntityType, KnowledgeStore, Provenance  # noqa: E402

REPORTS = ROOT / "reports"
PROCESSED = ROOT / "data" / "processed"


def build_store(drugs: pd.DataFrame, *, include_activities: bool) -> tuple:
    """Run every adapter that can run; record why the others could not."""
    store = KnowledgeStore()
    status: dict[str, dict] = {}

    adapters = [
        ("drugcentral", DrugCentralAdapter(), {"drugs": drugs}),
        ("chembl", ChemblAdapter(), {"include_activities": include_activities}),
        ("reactome_uniprot", ReactomeUniProtAdapter(), {}),
        ("reactome_fi", ReactomeFIAdapter(), {}),
        ("sider", SiderAdapter(), {}),
        ("uniprot", UniProtAdapter(), {}),
        ("faers", FaersAdapter(), {}),
    ]

    for name, adapter, kwargs in adapters:
        desc = adapter.describe()
        before = len(store)
        entry = {"version": desc.version, "licence": desc.licence,
                 "is_placeholder": desc.is_placeholder,
                 "available": adapter.is_available()}
        # The protein networks are restricted to the accessions and genes the
        # drug-target layer actually reached. Everything else can never touch a
        # drug pair, so materialising it would cost memory for nothing.
        if name == "reactome_uniprot":
            kwargs = {"restrict_to": [e.canonical_id.split(":", 1)[1]
                                      for e in store.entities
                                      if e.canonical_id.startswith("PRO:")]}
        if name == "reactome_fi":
            kwargs = {"restrict_to": [e.name for e in
                                      store.entities_of(EntityType.GENE) if e.name]}
        try:
            adapter.extract(store, **kwargs)
            entry.update(ran=True, assertions_added=len(store) - before)
        except (SourceUnavailable, NotImplementedError, RuntimeError) as exc:
            entry.update(ran=False, assertions_added=0,
                         reason=str(exc).split("\n")[0][:200])
        status[name] = entry
        flag = "ok " if entry["ran"] else "-- "
        print(f"  {flag}{name:18s} +{entry['assertions_added']:>7,} утверждений"
              + ("" if entry["ran"] else f"   ({entry.get('reason','')[:60]})"))
    return store, status


def map_chembl_to_corpus(drugs: pd.DataFrame) -> tuple[pd.DataFrame, dict] | None:
    """Corpus drug <-> ChEMBL compound, by InChIKey only.

    Returns None when the ChEMBL extracts are absent. No name matching and no
    skeleton fallback: both are decisions, and this table is meant to be the
    exact one.
    """
    path = PROCESSED / "chembl_compounds.parquet"
    if not path.exists():
        return None

    chembl = pd.read_parquet(path, columns=["chembl_id", "standard_inchi_key",
                                            "pref_name", "max_phase"])
    chembl["key"] = chembl["standard_inchi_key"].map(
        lambda k: normalise("inchikey", k))
    chembl = chembl.dropna(subset=["key"])

    by_key: dict[str, list[str]] = {}
    for row in chembl.itertuples(index=False):
        by_key.setdefault(row.key, []).append(row.chembl_id)

    rows = []
    for row in drugs.itertuples(index=False):
        key = normalise("inchikey", row.inchikey)
        hits = by_key.get(key, []) if key else []
        rows.append({
            "drugbank_id": row.drugbank_id,
            "inchikey": key or "",
            "canonical_id": canonical_compound_id(key) if key else "",
            "chembl_ids": "|".join(sorted(hits)),
            "n_chembl_matches": len(hits),
            # One ChEMBL id is a clean match; several mean ChEMBL holds the same
            # structure under more than one entry, which is AMBIGUOUS and must
            # not be silently resolved to the first.
            "status": ("unmatched" if not hits
                       else "matched" if len(hits) == 1 else "ambiguous"),
        })
    table = pd.DataFrame(rows)

    counts = table["status"].value_counts().to_dict()
    matched = int(counts.get("matched", 0))
    ambiguous = int(counts.get("ambiguous", 0))
    summary = {
        "total_existing_drugs": int(len(table)),
        "matched_drugs": matched,
        "unmatched_drugs": int(counts.get("unmatched", 0)),
        "ambiguous_matches": ambiguous,
        "match_percentage": round(100.0 * matched / max(len(table), 1), 2),
        "match_percentage_including_ambiguous": round(
            100.0 * (matched + ambiguous) / max(len(table), 1), 2),
        "match_basis": "exact standard InChIKey; no name matching, no skeleton "
                       "fallback",
        "chembl_compounds_with_inchikey": int(len(chembl)),
    }
    return table, summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--include-activities", action="store_true",
                    help="also load ChEMBL bioactivities (millions of rows); "
                         "off by default so curated mechanisms are not "
                         "outnumbered by screening hits")
    args = ap.parse_args()
    REPORTS.mkdir(exist_ok=True)

    drugs = load_drugs()
    drugs = drugs[drugs["valid"]].reset_index(drop=True)
    print(f"Корпус: {len(drugs):,} препаратов\n")
    print("Адаптеры:")
    store, status = build_store(drugs, include_activities=args.include_activities)

    imap: IdentifierMap = build_compound_map(
        [("drugbank", r.drugbank_id, r.inchikey) for r in drugs.itertuples()],
        provenance=Provenance("tdc_drugbank", "1.1.15"))

    quality = {
        "corpus": audit_compounds(
            [(r.drugbank_id, r.canonical_smiles, r.inchikey)
             for r in drugs.itertuples(index=False)]),
        "store": audit_store(store),
        "identifier_map": audit_identifier_map(imap),
        "adapters": status,
    }
    out = REPORTS / "biomedical_data_quality.json"
    out.write_text(json.dumps(quality, indent=2, ensure_ascii=False, default=str))
    print(f"\nЗаписано {out}")

    mapped = map_chembl_to_corpus(drugs)
    if mapped is None:
        print("ChEMBL не извлечён - сопоставление с ним пропущено "
              "(scripts/extract_chembl.py)")
    else:
        table, summary = mapped
        table.to_csv(REPORTS / "chembl_drugbank_mapping.csv", index=False)
        (REPORTS / "chembl_mapping_summary.json").write_text(
            json.dumps(summary, indent=2))
        print(f"Записано {REPORTS / 'chembl_drugbank_mapping.csv'}")
        print(json.dumps(summary, indent=2, ensure_ascii=False))

    s = quality["store"]["summary"]
    print(f"\nХранилище: {s['n_entities']:,} сущностей, "
          f"{s['n_assertions']:,} утверждений, "
          f"{s['n_distinct_relations']:,} различных отношений, "
          f"из них с >1 источником: {s['n_relations_with_multiple_sources']:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
