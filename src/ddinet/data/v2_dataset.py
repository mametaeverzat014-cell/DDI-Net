"""
The V2 modelling universe: DDI_MECH_1705_V1, loaded rather than reconstructed.

WHY THIS EXISTS SEPARATELY FROM ``tdc_drugbank``
-------------------------------------------------
Phase A-2 built its universe by parsing the TDC DrugBank export, excluding the
one drug RDKit cannot parse, and splitting the survivors. That produced
1,705 drugs and 191,392 positive pairs, and those numbers are now frozen as
``DDI_MECH_1705_V1`` in ``data/mechanism_v1/``.

V2 reads the frozen artefact. It does not re-run the derivation, for three
reasons:

  1. the preregistration names the dataset by version and freezes it
     (``docs/V2_PREREGISTRATION.md`` section 3);
  2. re-deriving means the universe depends on the TDC package version
     installed today, which is exactly the kind of silent drift a frozen
     dataset exists to prevent;
  3. the exclusion of DB11630 is a recorded decision with a stated reason.
     Re-running the exclusion logic would make it a side effect again.

``verify_matches_phase_a2()`` checks the two agree, and it is a test rather
than a runtime step: agreement is a property to assert once, not a dependency
to carry.

SPLITS ARE LOADED, NOT RECOMPUTED
----------------------------------
``data/mechanism_v1/split_assignments.csv`` holds the drug -> train/val/test
assignment for both drug-disjoint and scaffold-disjoint schemes at seeds 0-4.
All ten reproduce exactly what ``split.build_any`` computes, verified. V2 reads
the file and routes pairs through ``split.assemble_split``, the same function
``build_split`` uses, so the bucket definitions cannot drift apart.

The alternative - calling ``build_any`` again - would work today and would
silently stop working the day anything in the stratification changes. The
frozen file is the contract.

WHAT V2 IS NOT ALLOWED TO SEE
------------------------------
The model gets molecular structure and biology. It does not get:

  * the DDI graph's topology in any form - no adjacency, no node degree, no
    neighbourhood aggregation. This is the whole point: Phase A-2 measured the
    DDI-network branch encoding training degree at R^2 0.885-0.954 and hurting
    every honest split, and V2 exists to replace it with something a
    never-before-seen drug actually has;
  * ``INTERACTS_WITH`` edges (the biological graph has zero of them, verified);
  * DDI descriptions or the quarantined mechanism labels;
  * FAERS pair signals.

The positive labels are used for exactly two things: defining which pairs are
positive, and being the target of the loss. They never become a feature.
``assert_no_ddi_features`` states that as a runnable check.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import split as split_mod

#: The frozen dataset. Named as a constant because every V2 artefact records
#: which dataset version it came from, and a literal path in five places is
#: five chances to point one run at something else.
MECHANISM_V1 = Path("data/mechanism_v1")
DATASET_VERSION = "DDI_MECH_1705_V1"

#: Authoritative counts, from docs/V2_PREREGISTRATION.md section 3. Asserted on
#: load rather than trusted: a silently truncated Parquet is a plausible failure
#: and would show up only as slightly worse numbers.
N_DRUGS = 1705
N_POSITIVE_PAIRS = 191392

#: Excluded upstream because RDKit cannot parse its SMILES (an upstream defect
#: in the TDC export). Recorded here so that its absence is a checked property
#: rather than an accident nobody would notice.
EXCLUDED_DRUG = "DB11630"


@dataclass
class V2Universe:
    """The frozen drug set and positive pairs, plus a provenance record.

    ``drugs`` carries a ``name`` column holding the DrugBank ID. That is the
    Phase A-2 convention - its splits, its negative sampler and its prediction
    files all key on ``name`` - and V2 keeps it so the frozen split file and the
    existing sampler can be used unchanged rather than through a translation
    layer that could quietly mis-map one drug.
    """

    drugs: pd.DataFrame
    pairs: pd.DataFrame
    manifest: dict
    manifest_hash: str

    @property
    def drug_names(self) -> list[str]:
        return list(self.drugs["name"])

    @property
    def positive_keys(self) -> set[tuple[str, str]]:
        """Every documented interaction, order-normalised.

        Consumed by the negative sampler, which must never draw a documented
        interaction as a negative. Built from the FULL label set, not from one
        bucket: a pair that is positive in test is still not a valid negative
        for train, and treating it as one would be a label error that flatters
        the model.
        """
        return set(zip(self.pairs["drug_a"], self.pairs["drug_b"]))


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_universe(root: Path | str = MECHANISM_V1) -> V2Universe:
    """Load the frozen drug set and positive pairs, asserting the known counts."""
    root = Path(root)
    drugs = pd.read_parquet(root / "drugs.parquet")
    labels = pd.read_parquet(root / "ddi_positive_labels.parquet")

    if len(drugs) != N_DRUGS:
        raise ValueError(
            f"{root/'drugs.parquet'} holds {len(drugs)} drugs, expected {N_DRUGS}. "
            f"This is not {DATASET_VERSION}."
        )
    if len(labels) != N_POSITIVE_PAIRS:
        raise ValueError(
            f"{root/'ddi_positive_labels.parquet'} holds {len(labels)} pairs, "
            f"expected {N_POSITIVE_PAIRS}. This is not {DATASET_VERSION}."
        )
    if EXCLUDED_DRUG in set(drugs["drugbank_id"]):
        raise ValueError(
            f"{EXCLUDED_DRUG} is present, but it was excluded from "
            f"{DATASET_VERSION} because RDKit cannot parse its SMILES."
        )

    # `name` mirrors `drugbank_id`: the Phase A-2 split files, negative sampler
    # and prediction files all key on `name`, and renaming here would mean
    # translating at every boundary instead of once.
    drugs = drugs.assign(name=drugs["drugbank_id"])

    pairs = labels.rename(
        columns={"drug_a_id": "drug_a", "drug_b_id": "drug_b"}
    )[["drug_a", "drug_b", "label"]].copy()
    pairs["pair_key"] = list(zip(pairs["drug_a"], pairs["drug_b"]))

    known = set(drugs["name"])
    stray = {d for d in set(pairs["drug_a"]) | set(pairs["drug_b"]) if d not in known}
    if stray:
        raise ValueError(
            f"{len(stray)} drugs appear in the label file but not in drugs.parquet, "
            f"first: {sorted(stray)[:3]}"
        )

    manifest_path = root / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest_hash = _hash_file(manifest_path) if manifest_path.exists() else ""

    return V2Universe(drugs=drugs, pairs=pairs, manifest=manifest,
                      manifest_hash=manifest_hash)


def load_frozen_split(
    universe: V2Universe,
    scheme: str = "drug",
    seed: int = 0,
    root: Path | str = MECHANISM_V1,
) -> split_mod.DrugLevelSplit:
    """Rebuild the frozen split object from the recorded drug assignment.

    NOT a re-run of the splitting algorithm. The drug -> train/val/test map is
    read from ``split_assignments.csv``; only the pair routing is recomputed,
    and that is done by ``split.assemble_split``, the same function Phase A-2
    used. ``assert_no_leakage`` runs inside it.

    :param scheme: ``drug`` or ``scaffold``. ``random_pair`` is stored
        differently (per-pair, not per-drug) and is not needed for the
        drug-disjoint primary evaluation; it raises rather than silently
        returning something adjacent.
    """
    if scheme not in ("drug", "scaffold"):
        raise ValueError(
            f"scheme must be 'drug' or 'scaffold', got {scheme!r}. The "
            f"random_pair split is stored per-pair in "
            f"split_assignments_random_pair.csv.gz and needs a different loader."
        )
    assignments = pd.read_csv(Path(root) / "split_assignments.csv")
    rows = assignments[
        (assignments["scheme"] == scheme) & (assignments["seed"] == seed)
    ]
    if rows.empty:
        available = sorted(
            assignments[["scheme", "seed"]].drop_duplicates()
            .itertuples(index=False, name=None)
        )
        raise ValueError(f"No frozen split for {scheme!r} seed {seed}; have {available}")

    groups = {a: set(g["project_drug_id"]) for a, g in rows.groupby("assignment")}
    train_d = groups.get("train", set())
    val_d = groups.get("val", set())
    test_d = groups.get("test", set())

    covered = train_d | val_d | test_d
    known = set(universe.drug_names)
    if covered != known:
        raise ValueError(
            f"Frozen split covers {len(covered)} drugs, universe has {len(known)}; "
            f"missing {len(known - covered)}, extra {len(covered - known)}"
        )

    return split_mod.assemble_split(
        universe.pairs, train_d, val_d, test_d, group_by=scheme, seed=seed
    )


#: Column names that would be a DDI-graph feature if they ever reached a model
#: input. Checked by name because the check has to be cheap enough to run on
#: every frame, and a name is what a future contributor would add.
FORBIDDEN_FEATURE_COLUMNS: frozenset[str] = frozenset({
    "ddi_degree", "degree", "n_interactions", "n_ddi", "interacts_with",
    "neighbours", "neighbors", "adjacency", "y_types", "y_primary",
    "description", "mechanism", "faers_signal", "prr", "ror",
})


def assert_no_ddi_features(frame: pd.DataFrame, where: str = "frame") -> None:
    """Fail if a frame headed for the model carries DDI-derived columns.

    V2's claim is that biology transfers to unseen drugs where DDI topology
    cannot. A degree column reaching the feature path would make that claim
    untestable, and it would not show up as an error - only as a suspiciously
    good number, which is the failure mode this project keeps finding.
    """
    offenders = sorted(set(frame.columns) & FORBIDDEN_FEATURE_COLUMNS)
    if offenders:
        raise ValueError(
            f"{where} carries DDI-derived columns that must not reach the "
            f"model: {offenders}"
        )


def verify_matches_phase_a2(universe: V2Universe) -> dict:
    """Confirm the frozen universe equals the one Phase A-2 derived from TDC.

    Imported lazily and used only by tests and audits: making this a runtime
    dependency would reintroduce exactly the TDC-version coupling the freeze
    was meant to remove.
    """
    from . import tdc_drugbank as tdc

    drugs, pairs, _ = tdc.load_modelling_data()
    return {
        "drugs_match": set(drugs["name"]) == set(universe.drug_names),
        "pairs_match": set(zip(pairs["drug_a"], pairs["drug_b"]))
        == universe.positive_keys,
        "n_drugs_tdc": len(drugs),
        "n_pairs_tdc": len(pairs),
        "n_drugs_frozen": len(universe.drugs),
        "n_pairs_frozen": len(universe.pairs),
    }
