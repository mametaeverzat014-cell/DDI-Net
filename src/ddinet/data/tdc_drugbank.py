"""
Loader for the TDC DrugBank DDI benchmark (``data/raw/drugbank.tab.gz``).

WHAT THIS FILE IS
-----------------
A Therapeutics Data Commons export of ``tdc.multi_pred.DDI(name='DrugBank')``.
Tab-separated, gzipped, six columns:

    ID1, ID2   DrugBank accession numbers of the two drugs
    Y          interaction TYPE, an integer in 1..86
    Map        the templated English description of that type
    X1, X2     SMILES of the two molecules

*** Y IS NOT A BINARY LABEL. ***

This is the single most important thing to understand about this file. ``Y=1``
does not mean "these drugs interact" and ``Y=0`` does not exist. Every one of
the 191,808 rows is a *documented interaction*; ``Y`` says which of 86
mechanisms it is. **The dataset contains no negative examples whatsoever.**

Consequently any binary interaction-prediction experiment on this data must
generate its own negatives, and the choice of how to do that is a first-class
methodological decision with consequences for every number that follows. See
LIMITATIONS.md (L1.3) and the negative-sampling options recorded there.

DIRECTIONALITY
--------------
``Map`` is directional: "The metabolism of #Drug2 can be decreased when
combined with #Drug1" assigns distinct roles to the two drugs, and ``#Drug1``
is ``ID1``. So the 86-class *typing* task is directional, while the binary
*does-it-interact* task is symmetric.

We store a canonically ordered ``(drug_a, drug_b)`` key for the symmetric task
and keep the original ``ID1``/``ID2`` orientation alongside it, so the
directional information is not destroyed by the ordering.

MULTI-LABEL PAIRS
-----------------
406 unordered pairs appear twice with *different* ``Y`` values - a drug pair
can have more than one documented mechanism at once. There are no exact
duplicates. For the binary task these collapse to one pair; for the typing task
they are genuinely multi-label. ``load_pairs`` collapses them and records every
type in ``y_types``, so neither view is lost.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from rdkit import Chem, RDLogger
from rdkit.Chem import Descriptors, inchi, rdMolDescriptors

RDLogger.DisableLog("rdApp.*")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PATH = PROJECT_ROOT / "data" / "raw" / "drugbank.tab.gz"

REQUIRED_COLUMNS = ("ID1", "ID2", "Y", "Map", "X1", "X2")


class TDCDataError(ValueError):
    """The export is not shaped the way the loader expects."""


def _read_raw(path: Path) -> pd.DataFrame:
    """Read the gzipped TSV.

    pandas infers gzip from the ``.gz`` suffix, but we pass ``compression``
    explicitly: the file is committed gzipped only because GitHub's web
    uploader caps at 25 MB, and being explicit means a future rename to ``.tab``
    fails loudly here instead of producing a one-column frame of binary junk.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"TDC DrugBank export not found at {path}.\n"
            f"  Download it with PyTDC on an unrestricted network:\n"
            f"      from tdc.multi_pred import DDI; DDI(name='DrugBank')\n"
            f"  and record version, date and SHA-256 in DATA_PROVENANCE.md."
        )
    df = pd.read_csv(path, sep="\t", compression="gzip")
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise TDCDataError(f"Missing columns {missing} in {path}; got {list(df.columns)}")
    return df


@lru_cache(maxsize=1)
def load_raw(path: str | None = None) -> pd.DataFrame:
    return _read_raw(Path(path) if path else DEFAULT_PATH)


# --------------------------------------------------------------------------
# Drugs
# --------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_drugs(path: str | None = None) -> pd.DataFrame:
    """One row per drug, with RDKit-derived structural columns.

    The SMILES for a given DrugBank ID is taken from whichever row mentions it;
    ``validate_smiles_consistency`` checks that every row agrees, so this is
    safe rather than merely convenient.

    Column ``name`` duplicates ``drugbank_id``. That is deliberate: the split
    and feature modules key on ``name``, and giving this frame the same contract
    means they need no changes to consume TDC data. The accession number is the
    identifier here - unlike the retired fixture, there are no human-readable
    drug names in this export.
    """
    raw = load_raw(path)

    smiles_by_id: dict[str, str] = {}
    for id_col, x_col in (("ID1", "X1"), ("ID2", "X2")):
        for drug_id, smi in zip(raw[id_col], raw[x_col]):
            smiles_by_id.setdefault(drug_id, smi)

    ids = sorted(smiles_by_id)
    rows = []
    for drug_id in ids:
        smi = smiles_by_id[drug_id]
        mol = Chem.MolFromSmiles(smi) if isinstance(smi, str) else None
        rows.append(
            {
                "drugbank_id": drug_id,
                "name": drug_id,          # split/feature modules key on `name`
                "smiles": smi if isinstance(smi, str) else "",
                "valid": mol is not None,
                "canonical_smiles": Chem.MolToSmiles(mol) if mol else "",
                "inchikey": inchi.MolToInchiKey(mol) if mol else "",
                "formula": rdMolDescriptors.CalcMolFormula(mol) if mol else "",
                "mol_weight": round(Descriptors.MolWt(mol), 2) if mol else float("nan"),
                "n_heavy_atoms": mol.GetNumHeavyAtoms() if mol else 0,
            }
        )
    return pd.DataFrame(rows)


def validate_smiles_consistency(path: str | None = None) -> list[str]:
    """DrugBank IDs whose SMILES differs between rows. Should be empty.

    If it is not, the same identifier denotes two structures somewhere in the
    export, and every downstream feature for that drug is ambiguous. Worth
    checking once rather than assuming.
    """
    raw = load_raw(path)
    seen: dict[str, str] = {}
    bad: set[str] = set()
    for id_col, x_col in (("ID1", "X1"), ("ID2", "X2")):
        for drug_id, smi in zip(raw[id_col], raw[x_col]):
            if drug_id in seen and seen[drug_id] != smi:
                bad.add(drug_id)
            seen.setdefault(drug_id, smi)
    return sorted(bad)


# --------------------------------------------------------------------------
# Pairs
# --------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_pairs(path: str | None = None) -> pd.DataFrame:
    """One row per *unordered* pair, collapsing multi-type duplicates.

    Columns:
      ``drug_a``, ``drug_b``  canonically ordered (drug_a < drug_b)
      ``pair_key``            the tuple, for set membership
      ``y_types``             sorted tuple of every documented type for the pair
      ``n_types``             how many mechanisms are documented
      ``y_primary``           the single most frequent type in the corpus among
                              this pair's types - a deterministic choice for
                              single-label experiments
      ``orientations``        tuple of (ID1, ID2, Y) as originally recorded,
                              preserving the direction that ``Map`` depends on
      ``label``               constant 1. Present so the frame has the same
                              contract as an assembled dataset. **It is not a
                              learnable target on its own** - see the module
                              docstring: this file has no negatives.
    """
    raw = load_raw(path)
    global_counts = raw["Y"].value_counts()

    by_key: dict[tuple[str, str], dict] = {}
    for r in raw.itertuples(index=False):
        key = (r.ID1, r.ID2) if r.ID1 < r.ID2 else (r.ID2, r.ID1)
        entry = by_key.setdefault(
            key, {"types": set(), "orientations": [], "maps": set()}
        )
        entry["types"].add(int(r.Y))
        entry["orientations"].append((r.ID1, r.ID2, int(r.Y)))
        entry["maps"].add(r.Map)

    rows = []
    for key, entry in by_key.items():
        types = tuple(sorted(entry["types"]))
        rows.append(
            {
                "drug_a": key[0],
                "drug_b": key[1],
                "pair_key": key,
                "y_types": types,
                "n_types": len(types),
                "y_primary": max(types, key=lambda t: (global_counts.get(t, 0), -t)),
                "orientations": tuple(entry["orientations"]),
                "label": 1,
            }
        )
    df = pd.DataFrame(rows).sort_values(["drug_a", "drug_b"]).reset_index(drop=True)
    return df


@lru_cache(maxsize=1)
def type_vocabulary(path: str | None = None) -> pd.DataFrame:
    """The 86 interaction types with their descriptions and corpus frequency."""
    raw = load_raw(path)
    counts = raw["Y"].value_counts()
    text = raw.drop_duplicates("Y").set_index("Y")["Map"].to_dict()
    return (
        pd.DataFrame(
            {"y": sorted(text), "description": [text[y] for y in sorted(text)],
             "n_rows": [int(counts.get(y, 0)) for y in sorted(text)]}
        )
        .sort_values("n_rows", ascending=False)
        .reset_index(drop=True)
    )


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

@dataclass
class DatasetReport:
    n_rows: int
    n_pairs: int
    n_drugs: int
    n_types: int
    n_multitype_pairs: int
    n_self_loops: int
    n_valid_smiles: int
    invalid_smiles_ids: list[str]
    inconsistent_smiles_ids: list[str]
    duplicate_structures: dict[str, list[str]]
    degree: pd.Series = field(default_factory=pd.Series)
    type_counts: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def smiles_valid_fraction(self) -> float:
        return self.n_valid_smiles / self.n_drugs if self.n_drugs else 0.0

    @property
    def density(self) -> float:
        possible = self.n_drugs * (self.n_drugs - 1) / 2
        return self.n_pairs / possible if possible else 0.0


def build_report(path: str | None = None) -> DatasetReport:
    raw = load_raw(path)
    drugs = load_drugs(path)
    pairs = load_pairs(path)

    degree: dict[str, int] = {d: 0 for d in drugs["drugbank_id"]}
    for a, b in zip(pairs["drug_a"], pairs["drug_b"]):
        degree[a] += 1
        degree[b] += 1

    by_structure: dict[str, list[str]] = {}
    for key, drug_id in zip(drugs["inchikey"], drugs["drugbank_id"]):
        if key:
            by_structure.setdefault(key, []).append(drug_id)

    return DatasetReport(
        n_rows=len(raw),
        n_pairs=len(pairs),
        n_drugs=len(drugs),
        n_types=int(raw["Y"].nunique()),
        n_multitype_pairs=int((pairs["n_types"] > 1).sum()),
        n_self_loops=int((raw["ID1"] == raw["ID2"]).sum()),
        n_valid_smiles=int(drugs["valid"].sum()),
        invalid_smiles_ids=drugs.loc[~drugs["valid"], "drugbank_id"].tolist(),
        inconsistent_smiles_ids=validate_smiles_consistency(path),
        duplicate_structures={k: v for k, v in by_structure.items() if len(v) > 1},
        degree=pd.Series(degree).sort_values(ascending=False),
        type_counts=type_vocabulary(path),
    )

# --------------------------------------------------------------------------
# Explicit exclusion of unparseable structures
# --------------------------------------------------------------------------

@dataclass
class DropReport:
    """What an exclusion step removed, and why. Printed into every run log."""

    dropped_drug_ids: list[str]
    n_dropped_drugs: int
    n_dropped_pairs: int
    n_drugs_before: int
    n_drugs_after: int
    n_pairs_before: int
    n_pairs_after: int
    reason: str

    def summary(self) -> str:
        pct_pairs = (
            100 * self.n_dropped_pairs / self.n_pairs_before
            if self.n_pairs_before else 0.0
        )
        return (
            f"Exclusion: {self.reason}\n"
            f"  drugs {self.n_drugs_before} -> {self.n_drugs_after} "
            f"(dropped {self.n_dropped_drugs}: {self.dropped_drug_ids})\n"
            f"  pairs {self.n_pairs_before} -> {self.n_pairs_after} "
            f"(dropped {self.n_dropped_pairs} = {pct_pairs:.4f}% of the corpus)"
        )


def drop_unparseable(
    drugs: pd.DataFrame, pairs: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, DropReport]:
    """Remove drugs whose SMILES RDKit cannot parse, and every pair touching them.

    *** THIS IS A DELIBERATE, VISIBLE EXCLUSION STEP, NOT A SILENT FILTER. ***

    Exactly one drug is affected: DB11630, a porphyrin macrocycle whose SMILES
    in the TDC export uses malformed ring-closure syntax (``C-1=``, ``\\-1N2``).
    That is an upstream defect, not a parsing bug on our side. It appears in 10
    of 191,402 pairs.

    Why drop rather than carry a zero feature vector:

      * 10 pairs is 0.005% of the corpus - far below the resolution of any
        confidence interval this project will report, so nothing is lost.
      * An all-zero ECFP4 vector is not a neutral encoding. It would be the
        *only* drug with an empty fingerprint, so every model could identify it
        exactly, and under the symmetric pair encoding ``|a-0| = a`` and
        ``a*0 = 0`` - the pair features would collapse to "drug A alone". The
        model would learn a rule for one specific molecule from 10 examples.
        That is a systematic distortion, not missing data.
      * A missingness indicator flag would work in principle, but it buys one
        drug's worth of coverage at the cost of an extra feature that only ever
        fires 10 times.

    The alternative was considered and rejected on those grounds; the decision
    is recorded in LIMITATIONS.md so it is auditable rather than folklore.

    Returns ``(drugs, pairs, report)``. Callers should print the report.
    """
    bad = set(drugs.loc[~drugs["valid"], "drugbank_id"])
    n_drugs_before, n_pairs_before = len(drugs), len(pairs)

    if not bad:
        return drugs, pairs, DropReport([], 0, 0, n_drugs_before, n_drugs_before,
                                        n_pairs_before, n_pairs_before,
                                        "no unparseable structures")

    kept_drugs = drugs.loc[drugs["valid"]].reset_index(drop=True)
    touches_bad = pairs["drug_a"].isin(bad) | pairs["drug_b"].isin(bad)
    kept_pairs = pairs.loc[~touches_bad].reset_index(drop=True)

    report = DropReport(
        dropped_drug_ids=sorted(bad),
        n_dropped_drugs=len(bad),
        n_dropped_pairs=int(touches_bad.sum()),
        n_drugs_before=n_drugs_before,
        n_drugs_after=len(kept_drugs),
        n_pairs_before=n_pairs_before,
        n_pairs_after=len(kept_pairs),
        reason="SMILES unparseable by RDKit (upstream defect in the TDC export)",
    )
    return kept_drugs, kept_pairs, report


def load_modelling_data(
    path: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, DropReport]:
    """The single entry point every experiment should use.

    Applies the exclusion step above so that no experiment can accidentally
    forget it, and returns the report so every run log records what was removed.
    """
    drugs, pairs = load_drugs(path), load_pairs(path)
    return drop_unparseable(drugs, pairs)
