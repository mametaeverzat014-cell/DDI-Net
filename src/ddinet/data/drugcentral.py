"""
Adapter for DrugCentral: the missing `drug -> protein` link.

WHY THIS FILE EXISTS
--------------------
The corpus is keyed by DrugBank ID and InChIKey. Reactome is keyed by UniProt
accessions and gene symbols. Nothing connects them: a drug table with columns
``drugbank_id, smiles, inchikey, formula, mol_weight`` has no protein in it at
all. DrugCentral supplies exactly that missing layer, and this module is the
only place where the join is made.

THE JOIN, AND WHY IT IS DONE ON InChIKey
-----------------------------------------
``structures.smiles.tsv`` ships a precomputed ``InChIKey`` column, so no RDKit
recomputation is needed and no rounding or canonicalisation difference can
creep in. Joining on InChIKey rather than on drug NAME matters: the corpus does
not actually hold names (its ``name`` column is a copy of ``drugbank_id``), and
name matching across databases is a synonym problem that silently drops or
merges records.

MEASURED COVERAGE (2026-08-27, full numbers in DATA_PROVENANCE.md)
-------------------------------------------------------------------
    exact InChIKey                       1497 / 1705 = 87.8%
      + >=1 human target with a gene     1228 / 1705 = 72.0%
      + >=1 of those genes in Reactome   1214 / 1705 = 71.2%

FIRST-BLOCK MATCHING IS OPT-IN, NOT DEFAULT
--------------------------------------------
An InChIKey has three blocks: skeleton, stereo/isotope, protonation. Matching
on the first block alone recovers 40 more drugs (1537/1672 = 91.9%) by treating
a salt and its free base as one compound. That is often what a pharmacologist
means - but it IS a decision, not a fact, so it lives behind
``match="skeleton"`` and every result using it must say so. The default is
exact.

THE BIAS YOU MUST CARRY FORWARD
--------------------------------
Coverage is not random. Covered drugs have median DDI-graph degree 252;
uncovered drugs have 64 (Mann-Whitney p = 2.4e-56, Cohen d = 0.803). Biological
annotation exists preferentially for well-studied drugs - the same drugs where
the degree shortcut already works. Any "with biology vs without biology"
comparison must therefore run on the COVERED SUBSET ONLY, so both arms see the
same drugs; otherwise the difference measures selection, not biology. See
LIMITATIONS.md section 6d.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DIR = PROJECT_ROOT / "data" / "raw" / "drugcentral"
STRUCTURES = "structures.smiles.tsv"
INTERACTIONS = "drug.target.interaction.tsv.gz"

MatchMode = Literal["exact", "skeleton"]

#: Organism filter. Rat and mouse rows exist (2 087 and 574) and are dropped by
#: default: a target measured in rat is evidence about rat pharmacology, and
#: silently mixing species would put non-human proteins into a human pathway
#: graph.
HUMAN = "Homo sapiens"


def _require(path: Path) -> Path:
    """Fail with a message that says what to download, not just 'missing'."""
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. DrugCentral files are not in git (they are large "
            f"and CC BY-SA); download from https://drugcentral.org/download and "
            f"place them in {DEFAULT_DIR}. Required: {STRUCTURES}, {INTERACTIONS}."
        )
    return path


def load_structures(directory: Path | None = None) -> pd.DataFrame:
    """DrugCentral structures: ``struct_id, inchikey, inchikey_skeleton, inn``.

    ``inn`` is the International Nonproprietary Name - the closest thing to a
    real drug name available anywhere in this project's data.
    """
    path = _require((directory or DEFAULT_DIR) / STRUCTURES)
    raw = pd.read_csv(path, sep="\t", dtype=str)
    out = pd.DataFrame({
        "struct_id": raw["ID"],
        "inchikey": raw["InChIKey"],
        "inn": raw["INN"],
        "cas_rn": raw["CAS_RN"],
    }).dropna(subset=["struct_id", "inchikey"])
    out["inchikey_skeleton"] = out["inchikey"].str.split("-").str[0]
    return out.reset_index(drop=True)


def load_target_interactions(
    directory: Path | None = None, *, organism: str | None = HUMAN
) -> pd.DataFrame:
    """One row per (drug, target) assertion, exploded to one gene per row.

    The ``GENE`` column packs multiple gene symbols into one field separated by
    ``|`` (a protein complex, or a measurement that could not be resolved to a
    single subunit). Exploding rather than taking the first symbol keeps every
    named gene reachable; the cost is that one assertion becomes several rows,
    which is why ``assertion_id`` is carried through - it lets a caller collapse
    back to assertions when counting evidence rather than edges.
    """
    path = _require((directory or DEFAULT_DIR) / INTERACTIONS)
    raw = pd.read_csv(path, sep="\t", dtype=str)
    raw = raw.reset_index(names="assertion_id")
    if organism is not None:
        raw = raw[raw["ORGANISM"] == organism]

    raw = raw[raw["GENE"].notna() & (raw["GENE"] != "")]
    out = pd.DataFrame({
        "assertion_id": raw["assertion_id"],
        "struct_id": raw["STRUCT_ID"],
        "drug_name": raw["DRUG_NAME"],
        "gene": raw["GENE"].str.split("|"),
        "uniprot_id": raw["ACCESSION"],
        "target_name": raw["TARGET_NAME"],
        "target_class": raw["TARGET_CLASS"],
        "action_type": raw["ACTION_TYPE"],
        # MOA=1 marks a documented mechanism of action rather than a bare
        # measured activity. Only 16.8% of human rows carry it, so a caller
        # that needs "this is how the drug works" must filter, not assume.
        "is_moa": raw["MOA"].fillna("") == "1",
        "organism": raw["ORGANISM"],
    }).explode("gene")
    out["gene"] = out["gene"].str.strip()
    return out[out["gene"] != ""].reset_index(drop=True)


@dataclass
class DrugTargetTable:
    """The joined result, with the numbers needed to report it honestly."""

    #: drug_id, gene, uniprot_id, target_class, action_type, is_moa, ...
    edges: pd.DataFrame
    #: How the InChIKey match was made.
    match: MatchMode
    #: Drugs in the input that reached DrugCentral at all.
    n_matched: int
    #: Drugs that additionally have >=1 target.
    n_with_target: int
    #: Drugs in the input, total.
    n_input: int

    @property
    def covered(self) -> set[str]:
        return set(self.edges["drug_id"])

    def report(self) -> str:
        return (
            f"DrugCentral join (match={self.match})\n"
            f"  reached DrugCentral : {self.n_matched}/{self.n_input} "
            f"({self.n_matched / max(self.n_input, 1):.1%})\n"
            f"  with >=1 target     : {self.n_with_target}/{self.n_input} "
            f"({self.n_with_target / max(self.n_input, 1):.1%})\n"
            f"  target edges        : {len(self.edges)}\n"
            f"  distinct genes      : {self.edges['gene'].nunique()}"
        )


def build_drug_target_table(
    drugs: pd.DataFrame,
    directory: Path | None = None,
    *,
    match: MatchMode = "exact",
    organism: str | None = HUMAN,
) -> DrugTargetTable:
    """Join a drug table onto DrugCentral targets.

    :param drugs: must have ``drugbank_id`` and ``inchikey``.
    :param match: ``"exact"`` (default) compares the whole InChIKey;
        ``"skeleton"`` compares only the first block, merging salt forms and
        stereoisomers. Skeleton matching is a modelling decision - any result
        using it must state that it did.
    """
    if match not in ("exact", "skeleton"):
        raise ValueError(f"match must be 'exact' or 'skeleton', got {match!r}")
    for col in ("drugbank_id", "inchikey"):
        if col not in drugs.columns:
            raise ValueError(f"drugs table needs a {col!r} column")

    structures = load_structures(directory)
    targets = load_target_interactions(directory, organism=organism)

    left = drugs[["drugbank_id", "inchikey"]].dropna(subset=["inchikey"]).copy()
    if match == "exact":
        left["_key"] = left["inchikey"]
        right_key = "inchikey"
    else:
        left["_key"] = left["inchikey"].str.split("-").str[0]
        right_key = "inchikey_skeleton"

    # Rename before the merge. In "exact" mode both frames carry a column named
    # `inchikey`, so pandas would suffix them to inchikey_x/inchikey_y and the
    # `keep` filter below would silently drop both - leaving the output schema
    # DIFFERENT between the two match modes. A caller that read `inchikey` would
    # work on skeleton and fail on exact, which is the worse way round.
    left = left.rename(columns={"inchikey": "drug_inchikey"})

    matched = left.merge(
        structures[["struct_id", right_key, "inn"]],
        left_on="_key", right_on=right_key, how="inner",
    )

    edges = matched.merge(targets, on="struct_id", how="inner").rename(
        columns={"drugbank_id": "drug_id"}
    )
    keep = [
        "drug_id", "drug_inchikey", "struct_id", "inn", "assertion_id",
        "gene", "uniprot_id", "target_name", "target_class",
        "action_type", "is_moa", "organism",
    ]
    edges = edges[[c for c in keep if c in edges.columns]].drop_duplicates()

    return DrugTargetTable(
        edges=edges.reset_index(drop=True),
        match=match,
        n_matched=int(matched["drugbank_id"].nunique()),
        n_with_target=int(edges["drug_id"].nunique()),
        n_input=int(drugs["drugbank_id"].nunique()),
    )


def shared_target_counts(
    edges: pd.DataFrame, pairs: pd.DataFrame
) -> pd.DataFrame:
    """For each pair, how many target genes the two drugs have in common.

    The simplest biological feature the data supports, and the one most likely
    to matter: two drugs acting on the same protein is the textbook route to a
    pharmacodynamic interaction.

    NOT a claim of mechanism. A shared target says the two drugs were both
    measured against that protein - by whoever chose to measure it. Absence of
    a shared target is not evidence of independence; it is frequently evidence
    that nobody looked.
    """
    by_drug = edges.groupby("drug_id")["gene"].apply(set).to_dict()
    empty: set[str] = set()
    counts, union_sizes = [], []
    for a, b in zip(pairs["drug_a"], pairs["drug_b"]):
        ta, tb = by_drug.get(a, empty), by_drug.get(b, empty)
        counts.append(len(ta & tb))
        union_sizes.append(len(ta | tb))
    out = pairs[["drug_a", "drug_b"]].copy()
    out["n_shared_targets"] = counts
    out["n_union_targets"] = union_sizes
    # Jaccard, with 0/0 defined as 0: a pair where neither drug is annotated
    # has no measured overlap, and calling that 1.0 would make the least-known
    # pairs look the most similar.
    out["target_jaccard"] = [
        (c / u) if u else 0.0 for c, u in zip(counts, union_sizes)
    ]
    #: True when BOTH drugs are annotated. Every biological comparison must be
    #: restricted to these rows - see LIMITATIONS.md 6d.
    out["both_covered"] = [
        (a in by_drug) and (b in by_drug)
        for a, b in zip(pairs["drug_a"], pairs["drug_b"])
    ]
    return out
