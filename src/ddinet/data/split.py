"""
Drug-level (inductive) splitting - the single most important methodological
decision in this project.

THE PROBLEM WITH THE OBVIOUS SPLIT
----------------------------------
The obvious thing to do with a list of interacting drug pairs is to shuffle the
*pairs* and take 80/10/10.  This is what a large fraction of published DDI
papers do, and it produces beautiful numbers - AUC 0.98, 0.99 - that mean
almost nothing.

Here is why.  Warfarin appears in ~30 interactions in our seed set.  Under a
pair-level shuffle, ~24 of them land in train and ~3 in test.  At test time the
model does not need to understand anything about warfarin's chemistry: it has
already learned an embedding that says "warfarin interacts with almost
everything", and it can score the test pairs from that alone.  The model has
memorised *node identity*, not *interaction mechanism*.

This is textbook information leakage.  It is not detectable from the loss curve
- train and validation loss both look great - and it is only exposed by
changing the split.

THE THREE SETTINGS (Pahikkala et al. 2015; standard in the DDI literature)
--------------------------------------------------------------------------
Let D_train be the drugs visible during training.

  S1  "warm start" / transductive
      Both drugs of a test pair are in D_train.
      Question answered: *"Given two drugs I have seen interact with others,
      do they interact with each other?"*
      Realistic use case: filling gaps in an existing database.

  S2  "one new drug" / semi-inductive
      Exactly one drug of a test pair is outside D_train.
      Question answered: *"A new drug is entering the market. Will it interact
      with the drugs already on my formulary?"*
      This is the clinically important question.

  S3  "both new" / fully inductive
      Neither drug is in D_train.
      Question answered: *"Can I reason about interaction purely from
      structure, with no prior interaction data for either compound?"*
      Hardest setting; the honest test of whether the chemistry is being used.

Expect a large drop from S1 to S2 to S3.  **That drop is a result, not a
failure.**  Reporting all three - and explaining why S1 is optimistic - is what
separates a serious project from one that just quotes 0.99.

HOW WE GUARANTEE NO LEAKAGE
---------------------------
We partition *drugs*, not pairs.  Then every pair is routed by the membership
of its two endpoints.  Critically, pairs that straddle the validation and test
drug groups are **discarded**, not assigned - otherwise a drug tuned on during
validation would reappear in the test set and quietly leak.

Discarding data feels wasteful.  It is the price of a clean measurement, and
``SplitReport`` records exactly how much was discarded so you can state it.

SCAFFOLD GROUPING (the harder, better split)
--------------------------------------------
Even a drug-level split can flatter you.  Simvastatin and lovastatin differ by
a single methyl group; if one is in train and the other in test, an "unseen"
test drug is effectively a seen one.  ``group_by="scaffold"`` uses the
Bemis-Murcko scaffold (the ring systems and linkers, with side chains
stripped) as the grouping unit, so close analogues are forced into the same
split.  This is standard practice in molecular property prediction and is
rarely applied to DDI - using it is a genuine methodological contribution you
can point at.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Literal, Sequence

import numpy as np
import pandas as pd
from rdkit import Chem
from rdkit.Chem.Scaffolds import MurckoScaffold

Setting = Literal["S1", "S2", "S3"]
GroupBy = Literal["drug", "scaffold"]


# --------------------------------------------------------------------------
# Grouping units
# --------------------------------------------------------------------------

def murcko_scaffold(smiles: str, generic: bool = False) -> str:
    """Bemis-Murcko scaffold of a molecule, as canonical SMILES.

    ``generic=True`` additionally erases atom types and bond orders, mapping
    every ring system to a carbon skeleton.  That is a *very* aggressive
    grouping - it puts a benzodiazepine and its aza-analogue together - and is
    the strictest generalisation test available.

    Returns the input SMILES unchanged for acyclic molecules (valproic acid,
    metformin), which have no scaffold; those become their own group.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return smiles
    try:
        scaffold = MurckoScaffold.GetScaffoldForMol(mol)
        if generic:
            scaffold = MurckoScaffold.MakeScaffoldGeneric(scaffold)
        smi = Chem.MolToSmiles(scaffold)
        return smi if smi else Chem.MolToSmiles(mol)
    except Exception:
        # MakeScaffoldGeneric raises on some exotic valences; fall back rather
        # than losing the molecule.
        return Chem.MolToSmiles(mol)


def assign_groups(
    drugs: pd.DataFrame,
    group_by: GroupBy = "drug",
    *,
    generic_scaffold: bool = False,
) -> dict[str, str]:
    """Map each drug name to its grouping unit.

    With ``group_by="drug"`` every drug is its own group (the standard
    drug-level split).  With ``"scaffold"`` structurally similar drugs share a
    group and therefore always land in the same split.
    """
    if group_by == "drug":
        return {name: name for name in drugs["name"]}
    if group_by == "scaffold":
        return {
            row["name"]: murcko_scaffold(row["smiles"], generic=generic_scaffold)
            for _, row in drugs.iterrows()
        }
    raise ValueError(f"Unknown group_by: {group_by!r}")


# --------------------------------------------------------------------------
# The split object
# --------------------------------------------------------------------------

@dataclass
class DrugLevelSplit:
    """A leakage-free partition of drugs, and the pair buckets implied by it."""

    train_drugs: set[str]
    val_drugs: set[str]
    test_drugs: set[str]
    #: bucket name -> DataFrame of positive pairs
    buckets: dict[str, pd.DataFrame] = field(default_factory=dict)
    discarded: pd.DataFrame | None = None
    group_by: GroupBy = "drug"
    seed: int = 0

    # -- membership helpers -------------------------------------------------
    def split_of(self, drug: str) -> str:
        if drug in self.train_drugs:
            return "train"
        if drug in self.val_drugs:
            return "val"
        if drug in self.test_drugs:
            return "test"
        return "unknown"

    def setting_of(self, drug_a: str, drug_b: str) -> Setting:
        """Which of S1/S2/S3 does this pair represent, given the train drugs?"""
        n_unseen = int(drug_a not in self.train_drugs) + int(drug_b not in self.train_drugs)
        return ("S1", "S2", "S3")[n_unseen]

    # -- integrity ----------------------------------------------------------
    def assert_no_leakage(self) -> None:
        """Fail loudly if the partition is not actually disjoint.

        Cheap to run, and it has caught real bugs during development. Call it
        before every training run - a silent leak invalidates every number you
        would otherwise report.
        """
        overlaps = {
            "train&val": self.train_drugs & self.val_drugs,
            "train&test": self.train_drugs & self.test_drugs,
            "val&test": self.val_drugs & self.test_drugs,
        }
        bad = {k: sorted(v) for k, v in overlaps.items() if v}
        if bad:
            raise AssertionError(f"Drug-level split is not disjoint: {bad}")

        train = self.buckets.get("train")
        if train is not None and len(train):
            stray = {
                d
                for d in set(train["drug_a"]) | set(train["drug_b"])
                if d not in self.train_drugs
            }
            if stray:
                raise AssertionError(
                    f"Training pairs reference non-training drugs: {sorted(stray)}"
                )

    # -- reporting ----------------------------------------------------------
    def report(self) -> str:
        lines = [
            f"Drug-level split (group_by={self.group_by}, seed={self.seed})",
            f"  drugs: train={len(self.train_drugs)} "
            f"val={len(self.val_drugs)} test={len(self.test_drugs)}",
            "  positive-pair buckets:",
        ]
        for name in sorted(self.buckets):
            df = self.buckets[name]
            n_major = int((df["severity"] == "major").sum()) if len(df) else 0
            lines.append(f"    {name:12s} n={len(df):5d}  major={n_major}")
        if self.discarded is not None:
            lines.append(
                f"  discarded (val/test drug straddle): {len(self.discarded)} pairs"
            )
        return "\n".join(lines)


# --------------------------------------------------------------------------
# Splitting
# --------------------------------------------------------------------------

def _stratify_key(degree: int) -> str:
    """Coarse degree stratum, so hubs and leaves are spread across splits.

    Without this, a random group split can put warfarin, aspirin and every
    other high-degree drug into train, leaving a test set of only peripheral
    compounds - which makes the test set both easy and unrepresentative.
    """
    if degree == 0:
        return "isolated"
    if degree <= 3:
        return "low"
    if degree <= 10:
        return "medium"
    return "hub"


def split_drugs(
    drugs: pd.DataFrame,
    pairs: pd.DataFrame,
    *,
    val_fraction: float = 0.15,
    test_fraction: float = 0.15,
    seed: int = 0,
    group_by: GroupBy = "drug",
    generic_scaffold: bool = False,
) -> tuple[set[str], set[str], set[str]]:
    """Partition drugs (or scaffold groups) into train / val / test.

    Groups are assigned whole - a scaffold group never spans two splits - and
    assignment is stratified by interaction degree so each split contains a
    comparable mix of hub and peripheral drugs.

    Determinism: we sort group names and drive a seeded ``numpy`` generator, so
    the same inputs always give the same split on any machine. Reproducibility
    is not optional in a science-fair project - a judge may well ask you to
    re-run it.
    """
    if not 0 < val_fraction + test_fraction < 1:
        raise ValueError("val_fraction + test_fraction must be strictly between 0 and 1")

    groups = assign_groups(drugs, group_by, generic_scaffold=generic_scaffold)

    degree: dict[str, int] = defaultdict(int)
    for a, b in zip(pairs["drug_a"], pairs["drug_b"]):
        degree[a] += 1
        degree[b] += 1

    # Aggregate to group level: a group's degree is the sum of its members'.
    group_members: dict[str, list[str]] = defaultdict(list)
    for drug, grp in groups.items():
        group_members[grp].append(drug)
    group_degree = {
        grp: sum(degree.get(d, 0) for d in members)
        for grp, members in group_members.items()
    }

    strata: dict[str, list[str]] = defaultdict(list)
    for grp, deg in group_degree.items():
        strata[_stratify_key(deg)].append(grp)

    rng = np.random.default_rng(seed)
    train_g: set[str] = set()
    val_g: set[str] = set()
    test_g: set[str] = set()

    for stratum in sorted(strata):                    # sorted -> deterministic
        members = sorted(strata[stratum])             # sorted -> deterministic
        rng.shuffle(members)
        n = len(members)
        n_val = int(round(n * val_fraction))
        n_test = int(round(n * test_fraction))
        # Guarantee at least one group per split when the stratum can afford it,
        # so a small stratum does not silently vanish from val/test.
        if n >= 3:
            n_val = max(1, n_val)
            n_test = max(1, n_test)
            n_val = min(n_val, n - 2)
            n_test = min(n_test, n - 1 - n_val)
        val_g.update(members[:n_val])
        test_g.update(members[n_val : n_val + n_test])
        train_g.update(members[n_val + n_test :])

    to_drugs = lambda gs: {d for g in gs for d in group_members[g]}
    return to_drugs(train_g), to_drugs(val_g), to_drugs(test_g)


def build_split(
    drugs: pd.DataFrame,
    pairs: pd.DataFrame,
    *,
    val_fraction: float = 0.15,
    test_fraction: float = 0.15,
    seed: int = 0,
    group_by: GroupBy = "drug",
    generic_scaffold: bool = False,
) -> DrugLevelSplit:
    """Produce a full :class:`DrugLevelSplit` with pairs routed into buckets.

    Bucket naming:
      ``train``    both drugs in train
      ``val_S2``   one drug in train, one in val
      ``val_S3``   both drugs in val
      ``test_S2``  one drug in train, one in test
      ``test_S3``  both drugs in test

    Pairs with one drug in val and the other in test are **discarded**: keeping
    them would let a test drug influence validation-time model selection.
    """
    train_d, val_d, test_d = split_drugs(
        drugs,
        pairs,
        val_fraction=val_fraction,
        test_fraction=test_fraction,
        seed=seed,
        group_by=group_by,
        generic_scaffold=generic_scaffold,
    )

    def route(a: str, b: str) -> str | None:
        sa = "train" if a in train_d else ("val" if a in val_d else "test")
        sb = "train" if b in train_d else ("val" if b in val_d else "test")
        combo = {sa, sb}
        if combo == {"train"}:
            return "train"
        if combo == {"train", "val"}:
            return "val_S2"
        if combo == {"val"}:
            return "val_S3"
        if combo == {"train", "test"}:
            return "test_S2"
        if combo == {"test"}:
            return "test_S3"
        return None  # val<->test straddle: discard

    routed = [route(a, b) for a, b in zip(pairs["drug_a"], pairs["drug_b"])]
    tagged = pairs.assign(_bucket=routed)

    buckets = {
        name: tagged.loc[tagged["_bucket"] == name].drop(columns="_bucket").reset_index(drop=True)
        for name in ("train", "val_S2", "val_S3", "test_S2", "test_S3")
    }
    discarded = tagged.loc[tagged["_bucket"].isna()].drop(columns="_bucket").reset_index(drop=True)

    split = DrugLevelSplit(
        train_drugs=train_d,
        val_drugs=val_d,
        test_drugs=test_d,
        buckets=buckets,
        discarded=discarded,
        group_by=group_by,
        seed=seed,
    )
    split.assert_no_leakage()
    return split


# --------------------------------------------------------------------------
# Cross-validation
# --------------------------------------------------------------------------

def drug_level_kfold(
    drugs: pd.DataFrame,
    pairs: pd.DataFrame,
    *,
    n_folds: int = 5,
    seed: int = 0,
    group_by: GroupBy = "drug",
    generic_scaffold: bool = False,
) -> list[DrugLevelSplit]:
    """K-fold CV where the *drugs* (or scaffold groups) are the folds.

    Each fold serves once as test; the fold after it (cyclically) serves as
    validation; the rest is train.  Because folds are disjoint sets of drugs,
    every fold is a genuine inductive evaluation, and averaging across folds
    gives you an honest variance estimate over *which drugs* you happened to
    hold out - which is the dominant source of variance in DDI prediction, far
    larger than the variance from random weight initialisation.

    Quoting mean +/- SD across drug folds is much more defensible than quoting
    a single split, and judges do ask "how do you know that isn't luck?".
    """
    groups = assign_groups(drugs, group_by, generic_scaffold=generic_scaffold)
    group_members: dict[str, list[str]] = defaultdict(list)
    for drug, grp in groups.items():
        group_members[grp].append(drug)

    degree: dict[str, int] = defaultdict(int)
    for a, b in zip(pairs["drug_a"], pairs["drug_b"]):
        degree[a] += 1
        degree[b] += 1
    group_degree = {
        g: sum(degree.get(d, 0) for d in m) for g, m in group_members.items()
    }

    # Greedy balanced assignment: walk groups from highest to lowest degree and
    # drop each into the currently lightest fold. This keeps total interaction
    # count roughly equal across folds, which random assignment does not - one
    # fold getting both warfarin and amiodarone would badly skew its results.
    order = sorted(group_degree, key=lambda g: (-group_degree[g], g))
    rng = np.random.default_rng(seed)
    # Break ties randomly but reproducibly so the split is not an artefact of
    # alphabetical order.
    order = sorted(order, key=lambda g: (-group_degree[g], rng.random()))

    fold_of: dict[str, int] = {}
    load = [0] * n_folds
    for grp in order:
        f = int(np.argmin(load))
        fold_of[grp] = f
        load[f] += group_degree[grp] + 1  # +1 so degree-0 groups still spread

    fold_drugs: list[set[str]] = [set() for _ in range(n_folds)]
    for grp, f in fold_of.items():
        fold_drugs[f].update(group_members[grp])

    splits: list[DrugLevelSplit] = []
    for k in range(n_folds):
        test_d = fold_drugs[k]
        val_d = fold_drugs[(k + 1) % n_folds]
        train_d = set().union(*(fold_drugs[j] for j in range(n_folds) if j not in (k, (k + 1) % n_folds)))

        def route(a: str, b: str) -> str | None:
            sa = "train" if a in train_d else ("val" if a in val_d else "test")
            sb = "train" if b in train_d else ("val" if b in val_d else "test")
            combo = {sa, sb}
            return {
                frozenset({"train"}): "train",
                frozenset({"train", "val"}): "val_S2",
                frozenset({"val"}): "val_S3",
                frozenset({"train", "test"}): "test_S2",
                frozenset({"test"}): "test_S3",
            }.get(frozenset(combo))

        routed = [route(a, b) for a, b in zip(pairs["drug_a"], pairs["drug_b"])]
        tagged = pairs.assign(_bucket=routed)
        buckets = {
            name: tagged.loc[tagged["_bucket"] == name].drop(columns="_bucket").reset_index(drop=True)
            for name in ("train", "val_S2", "val_S3", "test_S2", "test_S3")
        }
        s = DrugLevelSplit(
            train_drugs=train_d,
            val_drugs=val_d,
            test_drugs=test_d,
            buckets=buckets,
            discarded=tagged.loc[tagged["_bucket"].isna()].drop(columns="_bucket").reset_index(drop=True),
            group_by=group_by,
            seed=seed * 100 + k,
        )
        s.assert_no_leakage()
        splits.append(s)
    return splits
