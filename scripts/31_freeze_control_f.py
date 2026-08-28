#!/usr/bin/env python3
"""
CONTROL F: freeze a degree-preserving shuffled biological graph.

WHAT IT DOES
------------
Randomises drug->protein assignments while preserving every nuisance statistic
the model could otherwise use to tell the control apart from real biology, then
writes the result once and records a manifest that makes it immutable.

Trains nothing. Evaluates nothing. Reads no DDI labels.

DEVIATION FROM THE PREREGISTERED TEXT - STATED UP FRONT
---------------------------------------------------------
docs/V2_ARCHITECTURE_PLAN.md, section CONTROL F, specifies:

    "For each drug d, draw |P(d)| proteins uniformly without replacement from
     the global protein pool, preserving the exact per-drug degree
     distribution."

This script implements a STRICTER control instead: a stratified
degree-preserving double-edge swap. The difference matters:

  * uniform resampling preserves DRUG degree but destroys PROTEIN degree. A
    heavily studied target loses its popularity, and the shuffled graph becomes
    distinguishable from the true one by protein-side statistics alone. A
    performance gap would then be attributable to that difference rather than
    to identity.
  * uniform resampling also ignores strata: a DrugBank TARGET edge could become
    a ChEMBL BIOACTIVITY edge, changing the evidence composition the model sees.

The swap preserves drug degree, protein degree AND stratum. It is therefore
harder for a model to distinguish from true biology, which is the safe
direction for a deviation: the control becomes more demanding, not less. The
deviation is recorded in the manifest so it cannot be discovered later as a
surprise.

TWO PROPERTIES OF THE DATA THAT DETERMINED THE DESIGN
--------------------------------------------------------
1. `drug_protein_edges.parquet` is an ASSERTION list, not an edge list:
   146,743 rows over 89,049 distinct (drug, protein) pairs. Shuffling rows
   directly would not preserve distinct degree.
2. `protein_id` (a DrugBank BE-accession) is null in 91% of rows - it exists
   only for DrugBank-sourced edges. `uniprot_id` is filled in 100%. The shuffle
   therefore keys on uniprot_id; keying on protein_id would have silently
   dropped 133,593 rows from the procedure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ddinet.integration.shuffle import shuffle_bipartite  # noqa: E402

SOURCE = ROOT / "data" / "mechanism_v1"
#: Seed for the preregistered PRIMARY control. The preregistration names no
#: shuffle seed, so this is fixed here and becomes immutable on commit.
PRIMARY_SEED = 20260829

#: Columns describing the PROTEIN. After a swap the edge points at a different
#: protein, so these must be re-derived from the new endpoint rather than
#: carried over - otherwise the row would claim the old protein's organism.
PROTEIN_COLUMNS = ("protein_id", "organism")

#: Columns describing the ASSERTION (which assay, which paper, what action).
#: These travel with the edge slot: they are what gives the drug its annotation
#: density, and that is the statistic being preserved.
ASSERTION_COLUMNS = ("action", "known_action", "pmids", "confidence")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _degree(frame: pd.DataFrame, by: str, of: str) -> pd.Series:
    return frame.groupby(by)[of].nunique()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=PRIMARY_SEED)
    ap.add_argument("--swaps-per-edge", type=int, default=20)
    ap.add_argument("--mixing-curve", type=int, nargs="*",
                    default=[1, 3, 10, 20],
                    help="swap budgets to probe for convergence; the frozen "
                         "graph uses --swaps-per-edge regardless")
    ap.add_argument("--out-root", type=Path,
                    default=ROOT / "data" / "mechanism_v1_controls")
    args = ap.parse_args()

    out_dir = args.out_root / f"shuffled_biology_seed{args.seed}"
    out_dir.mkdir(parents=True, exist_ok=True)
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # --- inputs. No DDI labels are read. --------------------------------
    true_edges = pd.read_parquet(SOURCE / "drug_protein_edges.parquet")
    drugs = pd.read_parquet(SOURCE / "drugs.parquet", columns=["drugbank_id"])
    proteins = pd.read_parquet(SOURCE / "proteins.parquet",
                               columns=["uniprot_accession"])
    pathways = pd.read_parquet(SOURCE / "protein_pathway_edges.parquet")
    bio = pd.read_parquet(SOURCE / "biological_edges.parquet")

    print(f"вход: {len(true_edges):,} строк-утверждений, "
          f"{len(drugs):,} препаратов, {len(proteins):,} белков\n")

    # --- the unit of shuffling: a (drug, protein) PAIR with its stratum
    # --- profile ---------------------------------------------------------
    # An earlier version shuffled each stratum independently, and that was
    # WRONG in a way only measurement revealed: 4,381 pairs (4.92%) appear in
    # more than one stratum - a target documented by both DrugBank and a ChEMBL
    # assay. In the true graph those collapse to ONE distinct protein; shuffled
    # independently they land on two, so 63.6% of drugs gained proteins (median
    # +2, up to +29). Systematically upward, and visible to any model that
    # counts a drug's proteins.
    #
    # Making the PAIR the unit, and swapping only within a class of identical
    # stratum profile, preserves exactly: distinct proteins per drug, distinct
    # drugs per protein, per-stratum edge counts per drug, and assertion row
    # counts per drug.
    true_edges = true_edges.copy()
    true_edges["stratum"] = (true_edges["relation_type"].astype(str) + "|"
                             + true_edges["evidence_type"].astype(str))
    pair_key = ["drugbank_id", "uniprot_id"]
    profile = (true_edges.drop_duplicates(pair_key + ["stratum"])
               .groupby(pair_key)["stratum"]
               .apply(lambda x: "+".join(sorted(x))).rename("profile"))
    edges = profile.reset_index()
    print(f"различных пар (препарат, uniprot): {len(edges):,}")
    print(f"классов профилей страт: {edges['profile'].nunique()}")

    drug_codes, drug_index = pd.factorize(edges["drugbank_id"], sort=True)
    prot_codes, prot_index = pd.factorize(edges["uniprot_id"], sort=True)

    new_prot_codes, report = shuffle_bipartite(
        drug_codes, prot_codes, edges["profile"].to_numpy(),
        seed=args.seed, swaps_per_edge=args.swaps_per_edge)
    edges["uniprot_shuffled"] = prot_index[new_prot_codes]

    print(f"перестановок: попыток {report.attempted:,}, "
          f"принято {report.successful:,} "
          f"({report.acceptance_rate:.1%}); сохранено исходных рёбер "
          f"{report.retained:,} = {report.retained_fraction:.2%}\n")

    # --- carry assertion rows onto the shuffled edge slots ----------------
    shuffled = true_edges.merge(
        edges[["drugbank_id", "uniprot_id", "uniprot_shuffled"]],
        on=pair_key, how="left", validate="many_to_one")
    assert shuffled["uniprot_shuffled"].notna().all(), "edge slot lost in merge"

    # Protein-side columns are re-derived from the NEW endpoint. Any uniprot
    # with no DrugBank record gets a null protein_id, which is already the case
    # for 91% of true rows and so introduces no new missingness pattern.
    protein_attrs = (true_edges.dropna(subset=["protein_id"])
                     .drop_duplicates("uniprot_id")
                     .set_index("uniprot_id")[list(PROTEIN_COLUMNS)])
    shuffled = shuffled.drop(columns=list(PROTEIN_COLUMNS)).join(
        protein_attrs, on="uniprot_shuffled")
    shuffled["uniprot_id"] = shuffled["uniprot_shuffled"]
    shuffled = shuffled.drop(columns=["uniprot_shuffled", "stratum"])[
        list(true_edges.columns.drop("stratum"))]
    shuffled.to_parquet(out_dir / "drug_protein_edges_shuffled.parquet",
                        compression="zstd", index=False)

    # --- rebuild the combined edge table ---------------------------------
    # Only the DRUG->PROTEIN block is replaced. Protein->pathway and
    # protein->protein biology stays intact by design: the control tests
    # whether drug->protein IDENTITY matters, so the organisation downstream of
    # proteins must remain real.
    mask = (bio["source_type"] == "DRUG") & (bio["target_type"] == "PROTEIN")
    replaced = bio.loc[mask].copy()
    replaced["target_node"] = shuffled["uniprot_id"].to_numpy()
    bio_shuffled = pd.concat([bio.loc[~mask], replaced]).sort_index()
    bio_shuffled.to_parquet(out_dir / "biological_edges_shuffled.parquet",
                            compression="zstd", index=False)

    # --- is the chain converged, or just under-mixed? ---------------------
    # The pair-set overlap is what matters, and it is NOT the slot-level
    # retention the swap report gives: a protein can leave a drug's slot and
    # return to a different slot of the same drug. Slot retention therefore
    # overstates randomisation badly (2.5% vs 57.4% here).
    #
    # Running the same shuffle at increasing budgets shows whether the residual
    # overlap is under-mixing or the stationary value of the degree sequence.
    # If it flattens, no amount of further swapping will destroy more, and that
    # is a property of the graph rather than a tuning failure.
    true_pairs = set(map(tuple, true_edges[pair_key].drop_duplicates().to_numpy()))

    def pair_overlap(new_codes) -> float:
        mapped = dict(zip(edges["drugbank_id"], prot_index[new_codes]))
        got = {(d, mapped[d]) for d in mapped}
        # rebuild properly: one entry per edge row
        got = set(zip(edges["drugbank_id"], prot_index[new_codes]))
        return len(got & true_pairs) / len(true_pairs)

    mixing_curve = []
    for budget in sorted(set(args.mixing_curve + [args.swaps_per_edge])):
        codes, rep = shuffle_bipartite(
            drug_codes, prot_codes, edges["profile"].to_numpy(),
            seed=args.seed, swaps_per_edge=budget)
        mixing_curve.append({
            "swaps_per_edge": budget,
            "successful_swaps": rep.successful,
            "slot_retention": round(rep.retained_fraction, 4),
            "pair_set_overlap": round(pair_overlap(codes), 4),
        })
        print(f"  обменов/ребро {budget:>4}: пересечение пар "
              f"{mixing_curve[-1]['pair_set_overlap']:.2%}")
    frozen_overlap = next(c["pair_set_overlap"] for c in mixing_curve
                          if c["swaps_per_edge"] == args.swaps_per_edge)
    print()

    # --- validation -------------------------------------------------------
    t_pairs = true_edges.drop_duplicates(["drugbank_id", "uniprot_id"])
    s_pairs = shuffled.drop_duplicates(["drugbank_id", "uniprot_id"])

    def compare(name, a, b):
        joined = pd.concat([a.rename("true"), b.rename("shuffled")],
                           axis=1).fillna(0)
        identical = bool((joined["true"] == joined["shuffled"]).all())
        rho = (float(joined["true"].corr(joined["shuffled"], method="spearman"))
               if joined["true"].nunique() > 1 else float("nan"))
        return {"metric": name, "identical": identical,
                "spearman": None if pd.isna(rho) else round(rho, 4),
                "max_abs_diff": int((joined["true"] - joined["shuffled"]).abs().max())}

    validation = {"drug_level": [], "protein_level": [], "pathway_level": [],
                  "coverage": {}, "strata": {}}

    validation["drug_level"].append(compare(
        "n_proteins_per_drug",
        _degree(t_pairs, "drugbank_id", "uniprot_id"),
        _degree(s_pairs, "drugbank_id", "uniprot_id")))
    validation["drug_level"].append(compare(
        "n_assertion_rows_per_drug",
        true_edges.groupby("drugbank_id").size(),
        shuffled.groupby("drugbank_id").size()))
    for rel in sorted(true_edges["relation_type"].dropna().unique()):
        validation["drug_level"].append(compare(
            f"n_{rel}_per_drug",
            _degree(true_edges[true_edges.relation_type == rel],
                    "drugbank_id", "uniprot_id"),
            _degree(shuffled[shuffled.relation_type == rel],
                    "drugbank_id", "uniprot_id")))
    for ev in sorted(true_edges["evidence_source"].dropna().unique()):
        validation["drug_level"].append(compare(
            f"n_edges_{ev}_per_drug",
            true_edges[true_edges.evidence_source == ev].groupby("drugbank_id").size(),
            shuffled[shuffled.evidence_source == ev].groupby("drugbank_id").size()))

    validation["protein_level"].append(compare(
        "n_drugs_per_protein",
        _degree(t_pairs, "uniprot_id", "drugbank_id"),
        _degree(s_pairs, "uniprot_id", "drugbank_id")))
    validation["protein_level"].append(compare(
        "n_assertion_rows_per_protein",
        true_edges.groupby("uniprot_id").size(),
        shuffled.groupby("uniprot_id").size()))

    # Pathway counts follow the shuffled proteins by design; measured, not forced.
    p2w = pathways.groupby("uniprot_accession")["reactome_pathway_id"].apply(set)

    def pathway_counts(frame):
        out = {}
        for drug, group in frame.groupby("drugbank_id")["uniprot_id"]:
            acc: set = set()
            for u in group.unique():
                acc |= p2w.get(u, set())
            out[drug] = len(acc)
        return pd.Series(out)

    tw, sw = pathway_counts(true_edges), pathway_counts(shuffled)
    validation["pathway_level"].append(compare("n_pathways_per_drug", tw, sw))
    validation["pathway_level"].append({
        "metric": "n_pathways_per_drug_distribution",
        "true_mean": round(float(tw.mean()), 3), "shuffled_mean": round(float(sw.mean()), 3),
        "true_median": float(tw.median()), "shuffled_median": float(sw.median()),
        "spearman": round(float(tw.corr(sw, method="spearman")), 4),
    })

    validation["coverage"] = {
        "drugs_with_ge1_protein_true": int(t_pairs["drugbank_id"].nunique()),
        "drugs_with_ge1_protein_shuffled": int(s_pairs["drugbank_id"].nunique()),
        "drugs_with_ge1_pathway_true": int((tw > 0).sum()),
        "drugs_with_ge1_pathway_shuffled": int((sw > 0).sum()),
        "proteins_used_true": int(t_pairs["uniprot_id"].nunique()),
        "proteins_used_shuffled": int(s_pairs["uniprot_id"].nunique()),
    }
    for col in ("relation_type", "evidence_source", "evidence_type"):
        t = true_edges[col].value_counts(dropna=False).to_dict()
        s = shuffled[col].value_counts(dropna=False).to_dict()
        validation["strata"][col] = {
            "true": {str(k): int(v) for k, v in t.items()},
            "shuffled": {str(k): int(v) for k, v in s.items()},
            "identical": {str(k): int(v) for k, v in t.items()}
                         == {str(k): int(v) for k, v in s.items()},
        }

    manifest = {
        "control": "F",
        "purpose": ("test whether the model benefits from biological IDENTITY "
                    "rather than biological degree or annotation density"),
        "created_utc": created,
        "generator": "scripts/31_freeze_control_f.py",
        "algorithm": "stratified degree-preserving bipartite double-edge swap",
        "shuffle_seed": args.seed,
        "swaps_per_edge": args.swaps_per_edge,
        "stratification": ("stratum profile of the (drug, protein) pair, where "
                           "the profile is the sorted set of relation_type|"
                           "evidence_type combinations that pair appears in; "
                           "25 classes"),
        "unit_of_shuffling": "(drug, protein) pair, not the assertion row",
        "why_pair_level": ("4,381 pairs (4.92%) appear in more than one stratum. "
                           "Shuffling strata independently sent them to different "
                           "proteins, raising distinct-protein count for 63.6% of "
                           "drugs (median +2, max +29) - systematically upward and "
                           "visible to the model. Pair-level shuffling makes drug "
                           "and protein distinct degree exactly preserved."),
        "edge_key": "uniprot_id",
        "edge_key_rationale": ("protein_id is null in 91% of rows - it exists "
                               "only for DrugBank-sourced edges - so keying on "
                               "it would silently exclude 133,593 rows"),
        "preregistration_deviation": {
            "preregistered": ("uniform resampling of |P(d)| proteins per drug "
                              "(docs/V2_ARCHITECTURE_PLAN.md, CONTROL F)"),
            "implemented": "stratified degree-preserving double-edge swap",
            "reason": ("resampling preserves drug degree but destroys protein "
                       "degree and ignores evidence strata, leaving the control "
                       "distinguishable from true biology by statistics other "
                       "than identity. The swap preserves both degree sequences "
                       "and the stratum, making the control STRICTER."),
            "direction": "stricter than preregistered",
        },
        "pathways": ("protein->pathway edges are NOT shuffled; drug->pathway "
                     "context changes only through the randomised proteins"),
        "labels_read": "none - ddi_positive_labels.parquet is never opened",
        "swap_report": report.summary(),
        "pair_set_overlap": frozen_overlap,
        "pair_set_overlap_note": (
            "fraction of TRUE (drug, protein) pairs still present after the "
            "shuffle. This - not the swap report's slot retention - is the "
            "measure of how much biological identity survives: a protein can "
            "leave one slot of a drug and return to another."),
        "mixing_curve": mixing_curve,
        "mixing_curve_note": (
            "pair-set overlap as a function of swap budget. A flat tail means "
            "the chain has converged and the residual overlap is the stationary "
            "value forced by the degree sequence, not under-mixing."),
        "validation": validation,
        "input_files": {p.name: {"sha256": sha256_of(p), "bytes": p.stat().st_size}
                        for p in sorted(SOURCE.glob("*.parquet"))},
        "output_files": {},
    }
    for p in sorted(out_dir.glob("*.parquet")):
        frame = pd.read_parquet(p)
        manifest["output_files"][p.name] = {
            "sha256": sha256_of(p), "bytes": p.stat().st_size,
            "rows": int(len(frame)), "columns": list(frame.columns)}
    (out_dir / "SHUFFLE_MANIFEST.json").write_text(json.dumps(manifest, indent=2))

    print(f"записано в {out_dir}")
    print(json.dumps({"coverage": validation["coverage"],
                      "pathway": validation["pathway_level"][1]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
