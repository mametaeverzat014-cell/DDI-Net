"""
Molecules as graphs: atoms are nodes, bonds are edges.

WHY A GRAPH AND NOT A FINGERPRINT (for the *learned* branch)
------------------------------------------------------------
A fingerprint is a fixed, hand-designed hash of substructures chosen before
seeing any data. A molecular graph is the raw object; a GNN over it *learns*
which substructures matter for this task. Concretely:

* A fingerprint bit fires for a substructure whether or not that substructure
  is relevant to CYP3A4 binding. The GNN can learn to weight it.
* Fingerprints hash colliding substructures together irreversibly. Message
  passing keeps atoms distinct throughout.
* Fingerprint radius is fixed at featurisation time. A GNN's effective receptive
  field grows with depth and is a trained hyperparameter.

We use both: fingerprints for the interpretable, provenance-carrying branch and
a learned graph encoder for capacity. Step 4 ablates them separately so you can
say what each contributes rather than asserting it.

THE REPRESENTATION IS A DELIBERATE CHOICE, NOT A DEFAULT
---------------------------------------------------------
Every atom feature below is one you can justify to a chemist:

  atomic number      - element identity; the single most important property
  degree             - substitution pattern; steric bulk
  formal charge      - ionisation state, drives membrane permeability
  total H count      - hydrogen-bond donor capacity
  hybridisation      - geometry (planar sp2 vs tetrahedral sp3)
  aromaticity        - aromatic rings dominate CYP450 active-site binding
  ring membership    - conformational rigidity
  ring size          - strain and reactivity (epoxides, beta-lactams)
  chirality          - stereochemistry changes metabolism (esomeprazole)

We deliberately do NOT include 3-D coordinates. Drugs are flexible; a single
conformer is arbitrary, and generating conformer ensembles is expensive and
adds a large source of variance. 2-D topology is what fingerprints use too,
so this keeps the two branches comparable.

ONE-HOT WITH AN EXPLICIT 'OTHER' BUCKET
----------------------------------------
Every categorical uses a fixed vocabulary plus a trailing "other" slot. Without
the "other" slot an unseen element at inference time produces an all-zero
one-hot block, which is silently indistinguishable from a legitimate zero. With
it, "unusual atom" is an explicit, learnable signal. This matters for the S3
setting, where test drugs are by definition unseen.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch
from rdkit import Chem
from torch_geometric.data import Data

#: Elements that actually occur in small-molecule drugs. Anything else lands in
#: the "other" bucket rather than silently vanishing.
ATOM_VOCABULARY: tuple[int, ...] = (
    6, 7, 8, 9, 15, 16, 17, 35, 53, 5, 14, 34,  # C N O F P S Cl Br I B Si Se
)
DEGREES: tuple[int, ...] = (0, 1, 2, 3, 4, 5)
FORMAL_CHARGES: tuple[int, ...] = (-2, -1, 0, 1, 2)
NUM_HS: tuple[int, ...] = (0, 1, 2, 3, 4)
HYBRIDIZATIONS: tuple[Chem.HybridizationType, ...] = (
    Chem.HybridizationType.SP,
    Chem.HybridizationType.SP2,
    Chem.HybridizationType.SP3,
    Chem.HybridizationType.SP3D,
    Chem.HybridizationType.SP3D2,
)
CHIRAL_TAGS: tuple[Chem.ChiralType, ...] = (
    Chem.ChiralType.CHI_UNSPECIFIED,
    Chem.ChiralType.CHI_TETRAHEDRAL_CW,
    Chem.ChiralType.CHI_TETRAHEDRAL_CCW,
)
RING_SIZES: tuple[int, ...] = (3, 4, 5, 6, 7)

BOND_TYPES: tuple[Chem.BondType, ...] = (
    Chem.BondType.SINGLE,
    Chem.BondType.DOUBLE,
    Chem.BondType.TRIPLE,
    Chem.BondType.AROMATIC,
)
BOND_STEREO: tuple[Chem.BondStereo, ...] = (
    Chem.BondStereo.STEREONONE,
    Chem.BondStereo.STEREOZ,
    Chem.BondStereo.STEREOE,
)


def _one_hot(value, vocabulary: tuple, *, allow_other: bool = True) -> list[float]:
    """One-hot with a trailing 'other' slot. See module docstring for why."""
    vec = [0.0] * (len(vocabulary) + (1 if allow_other else 0))
    try:
        vec[vocabulary.index(value)] = 1.0
    except ValueError:
        if allow_other:
            vec[-1] = 1.0
    return vec


def atom_feature_names() -> list[str]:
    """Human-readable name per atom-feature dimension.

    Needed for Step 5: an attention weight on dimension 37 is meaningless
    without a name attached to it.
    """
    names: list[str] = []
    names += [f"element_{z}" for z in ATOM_VOCABULARY] + ["element_other"]
    names += [f"degree_{d}" for d in DEGREES] + ["degree_other"]
    names += [f"charge_{c}" for c in FORMAL_CHARGES] + ["charge_other"]
    names += [f"numH_{h}" for h in NUM_HS] + ["numH_other"]
    names += [f"hyb_{h.name}" for h in HYBRIDIZATIONS] + ["hyb_other"]
    names += [f"chiral_{c.name}" for c in CHIRAL_TAGS] + ["chiral_other"]
    names += ["is_aromatic", "is_in_ring"]
    names += [f"in_ring_{n}" for n in RING_SIZES]
    names += ["atomic_mass_scaled"]
    return names


ATOM_FEATURE_DIM = len(atom_feature_names())


def atom_features(atom: Chem.Atom) -> np.ndarray:
    """Feature vector for one atom."""
    ring_info = atom.GetOwningMol().GetRingInfo()
    feats: list[float] = []
    feats += _one_hot(atom.GetAtomicNum(), ATOM_VOCABULARY)
    feats += _one_hot(atom.GetTotalDegree(), DEGREES)
    feats += _one_hot(atom.GetFormalCharge(), FORMAL_CHARGES)
    feats += _one_hot(atom.GetTotalNumHs(), NUM_HS)
    feats += _one_hot(atom.GetHybridization(), HYBRIDIZATIONS)
    feats += _one_hot(atom.GetChiralTag(), CHIRAL_TAGS)
    feats += [float(atom.GetIsAromatic()), float(atom.IsInRing())]
    feats += [float(ring_info.IsAtomInRingOfSize(atom.GetIdx(), n)) for n in RING_SIZES]
    # Scaled so it sits in roughly the same range as the one-hot bits; an
    # unscaled mass of 127 (iodine) would dominate every other feature and
    # destabilise the first layer.
    feats += [atom.GetMass() / 100.0]
    return np.asarray(feats, dtype=np.float32)


def bond_feature_names() -> list[str]:
    names = [f"bond_{b.name}" for b in BOND_TYPES] + ["bond_other"]
    names += [f"stereo_{s.name}" for s in BOND_STEREO] + ["stereo_other"]
    names += ["is_conjugated", "is_in_ring"]
    return names


BOND_FEATURE_DIM = len(bond_feature_names())


def bond_features(bond: Chem.Bond) -> np.ndarray:
    feats: list[float] = []
    feats += _one_hot(bond.GetBondType(), BOND_TYPES)
    feats += _one_hot(bond.GetStereo(), BOND_STEREO)
    feats += [float(bond.GetIsConjugated()), float(bond.IsInRing())]
    return np.asarray(feats, dtype=np.float32)


@dataclass
class MolGraph:
    """A molecule in PyG form, plus what we need to draw explanations on it."""

    data: Data
    smiles: str
    n_atoms: int

    def __repr__(self) -> str:
        return f"MolGraph({self.smiles!r}, atoms={self.n_atoms})"


def mol_to_graph(mol: Chem.Mol, smiles: str = "") -> MolGraph:
    """Convert an RDKit molecule to a PyG ``Data`` object.

    Edges are stored in **both directions**. PyG's message passing is
    directional: a single (i, j) entry sends messages only from i to j, so a
    chemical bond needs both (i, j) and (j, i) to behave like an undirected
    bond. Omitting the reverse direction is a classic and near-silent bug -
    the model still trains, just on half a molecule.

    A single-atom molecule (or a parse failure) produces a graph with a valid
    node set and an empty edge set rather than raising. Downstream pooling
    handles zero edges correctly, and crashing on one odd molecule in a batch
    of thousands is worse than representing it faithfully.
    """
    if mol is None:
        return MolGraph(
            Data(
                x=torch.zeros((1, ATOM_FEATURE_DIM), dtype=torch.float),
                edge_index=torch.zeros((2, 0), dtype=torch.long),
                edge_attr=torch.zeros((0, BOND_FEATURE_DIM), dtype=torch.float),
            ),
            smiles=smiles,
            n_atoms=0,
        )

    x = torch.tensor(
        np.vstack([atom_features(a) for a in mol.GetAtoms()]), dtype=torch.float
    )

    src, dst, attrs = [], [], []
    for bond in mol.GetBonds():
        i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        feat = bond_features(bond)
        src += [i, j]          # both directions - see docstring
        dst += [j, i]
        attrs += [feat, feat]

    if src:
        edge_index = torch.tensor([src, dst], dtype=torch.long)
        edge_attr = torch.tensor(np.vstack(attrs), dtype=torch.float)
    else:
        edge_index = torch.zeros((2, 0), dtype=torch.long)
        edge_attr = torch.zeros((0, BOND_FEATURE_DIM), dtype=torch.float)

    data = Data(x=x, edge_index=edge_index, edge_attr=edge_attr)
    data.smiles = smiles
    return MolGraph(data, smiles=smiles, n_atoms=mol.GetNumAtoms())


def smiles_to_graph(smiles: str) -> MolGraph:
    return mol_to_graph(Chem.MolFromSmiles(smiles), smiles=smiles)


def build_mol_graphs(names: list[str], smiles_list: list[str]) -> dict[str, MolGraph]:
    """Build and index molecular graphs by drug name."""
    return {n: smiles_to_graph(s) for n, s in zip(names, smiles_list)}
