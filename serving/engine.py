"""Frozen BIO-GINE M4 inference — the seed-0 checkpoint, reconstructed exactly.

WHAT THIS IS
------------
A read-only scorer for pairs of drugs from the frozen 1,705-drug universe. It
loads the frozen seed-0 checkpoint bd45f84e3c1b2c33.pt and reproduces the
research model's score. It trains nothing, fits nothing, and writes to no
scientific artifact.

HOW THE MODEL IS RECONSTRUCTED
------------------------------
Not from memory and not from website constants. Every architectural number comes
from ``checkpoint["spec"]`` — the run spec the trainer itself recorded — and the
two vocabulary sizes come from the BiologyBundle, exactly as
``V2Trainer._model_config()`` does at reports/v2_final time. The construction
mirrors scripts/36_v2_final_test.py, which is the script that produced the
frozen predictions:

    universe   = load_universe()
    drug_ids   = list(universe.drugs["drugbank_id"])
    bundle     = load_biology(policy="M4", drug_ids=drug_ids)
    mol_graphs = build_mol_graphs(universe.drugs["name"], universe.drugs["smiles"])
    model      = BioGine(config_from_spec).eval()
    model.set_biology(BiologicalSets(bundle))
    model.load_state_dict(checkpoint["model_state"])

``model_state`` and ``current_state`` in this checkpoint are bit-identical, so
there is no ambiguity about which weights the frozen predictions used.

WHY THE FULL ENCODING IS CACHED
-------------------------------
Every drug's representation depends only on its own molecular graph and its own
annotations. The molecular encoder normalises with LayerNorm, never BatchNorm —
a deliberate choice recorded in encoders.py — and dropout is inactive under
``eval()``, so no drug's vector depends on which other drugs share its batch.
The frozen model file itself documents the same property for the biological
branch (``test_subset_encoding_equals_full_encoding``). Encoding all 1,705 drugs
once at startup is therefore exact, not an approximation, and a request costs
one decoder pass instead of a full re-encode.

The parity test measures this claim rather than trusting it.

NO LABEL, NO ADJACENCY
----------------------
The DDI label graph is never read here. ``load_universe`` is followed by
``assert_no_ddi_features``, and the representation is built from structure and
annotation only. Whether a pair is documented in the frozen dataset is looked up
separately, for display, and is never an input to the model.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ddinet.data.biology import load_biology  # noqa: E402
from ddinet.data.v2_dataset import assert_no_ddi_features, load_universe  # noqa: E402
from ddinet.eval.calibration import _sigmoid, _to_logit  # noqa: E402
from ddinet.features.molgraph import (  # noqa: E402
    ATOM_FEATURE_DIM,
    BOND_FEATURE_DIM,
    build_mol_graphs,
)
from ddinet.models.bio_gine import BiologicalSets, BioGine, BioGineConfig  # noqa: E402

from .integrity import CHECKPOINT_PATH, IntegrityReport, verify_all  # noqa: E402

#: Seed-0 temperature, fitted on VALIDATION ONLY and frozen. Read from the
#: artifact rather than hard-coded — see load_frozen_temperature().
#: Byte-for-byte copy of reports/v2_calibration/m4_temperature_scaling.csv from
#: the frozen tag. Vendored because the deploy branch does not contain the
#: frozen commit; integrity.verify_sources() checks it against the tag hash.
CALIBRATION_CSV = Path(__file__).resolve().parent / "frozen_artifacts" / "m4_temperature_scaling.csv"
FROZEN_RUN_ID = "bd45f84e3c1b2c33"


class DrugNotInUniverse(KeyError):
    """The requested DrugBank ID is not one of the 1,705 frozen drugs."""


class IdenticalDrugs(ValueError):
    """A drug paired with itself is not a drug-drug interaction question."""


@dataclass(frozen=True)
class PairScore:
    """One pair's scores. Both are model outputs, neither is a risk estimate."""

    drug_a: str
    drug_b: str
    raw_logit: float
    raw_model_score: float
    calibrated_model_score: float
    biology_available_a: bool
    biology_available_b: bool


def load_frozen_temperature(run_id: str = FROZEN_RUN_ID) -> tuple[float, str]:
    """Seed-0 temperature from the frozen calibration artifact.

    Never refitted. The artifact also records the checkpoint SHA-256 the
    temperature was fitted for, which is asserted against the manifest so a
    temperature can never be paired with the wrong weights.
    """
    import pandas as pd

    from .integrity import load_manifest

    df = pd.read_csv(CALIBRATION_CSV)
    row = df[df["run_id"] == run_id]
    if len(row) != 1:
        raise RuntimeError(
            f"expected exactly one calibration row for run_id {run_id}, "
            f"found {len(row)} in {CALIBRATION_CSV}"
        )
    row = row.iloc[0]
    expected_sha = load_manifest()["checkpoint"]["sha256"]
    if str(row["checkpoint_sha256"]) != expected_sha:
        raise RuntimeError(
            "Calibration artifact was fitted for a different checkpoint:\n"
            f"  artifact {row['checkpoint_sha256']}\n  manifest {expected_sha}"
        )
    if not bool(row["temperature_converged"]):
        raise RuntimeError("frozen temperature fit did not converge; refusing to use it")
    return float(row["temperature"]), manifest_source()


def manifest_source() -> str:
    """Provenance string naming the ORIGINAL frozen path, not the vendored copy."""
    from .integrity import load_manifest

    vendored = load_manifest().get("vendored_artifacts", {})
    for meta in vendored.values():
        if meta["copied_from"].endswith("m4_temperature_scaling.csv"):
            return f"{meta['copied_from']} @ {load_manifest()['frozen_tag']}"
    return "unknown"


class FrozenBioGineEngine:
    """Loads once, scores many. Construct at process startup, never per request."""

    def __init__(self, device: str = "cpu", checkpoint: Path | None = None) -> None:
        t0 = time.perf_counter()
        self.integrity: IntegrityReport = verify_all(checkpoint)
        self.device = torch.device(device)

        blob = torch.load(
            checkpoint or CHECKPOINT_PATH, map_location="cpu", weights_only=False
        )
        if blob.get("run_id") != FROZEN_RUN_ID:
            raise RuntimeError(
                f"checkpoint run_id is {blob.get('run_id')!r}, expected {FROZEN_RUN_ID!r}"
            )
        self.spec: dict = dict(blob["spec"])
        if self.spec["ablation"] != "M4" or self.spec["biology_source"] != "true":
            raise RuntimeError(
                "checkpoint is not the M4 true-biology model: "
                f"ablation={self.spec['ablation']} biology={self.spec['biology_source']}"
            )

        # -- data, exactly as scripts/36_v2_final_test.py loads it ----------
        universe = load_universe()
        assert_no_ddi_features(universe.drugs, "drugs.parquet")
        self.drug_ids: list[str] = list(universe.drugs["drugbank_id"])
        bundle = load_biology(policy=self.spec["ablation"], drug_ids=self.drug_ids)
        mol_graphs = build_mol_graphs(
            list(universe.drugs["name"]), list(universe.drugs["smiles"])
        )

        # Drug order IS the model's index space; it comes from the bundle, which
        # is what the trainer indexed on. Never re-sorted.
        self.index: dict[str, int] = {d: i for i, d in enumerate(bundle.drug_ids)}
        self.ordered_ids: list[str] = list(bundle.drug_ids)
        mol_data = [mol_graphs[d].data for d in bundle.drug_ids]

        # -- model ----------------------------------------------------------
        config = BioGineConfig(
            n_protein_vocab=bundle.n_proteins,
            n_pathway_vocab=bundle.n_pathways,
            atom_dim=ATOM_FEATURE_DIM,
            bond_dim=BOND_FEATURE_DIM,
            mol_dim=self.spec["mol_dim"],
            mol_layers=self.spec["mol_layers"],
            mol_pooling=self.spec["mol_pooling"],
            dropout_mol=self.spec["dropout_mol"],
            bio_dim=self.spec["bio_dim"],
            dropout_bio=self.spec["dropout_bio"],
            aggregation=self.spec["aggregation"],
            hidden_dim=self.spec["hidden_dim"],
            dropout_pair=self.spec["dropout_pair"],
            use_molecular_branch=True,
            use_protein_level=True,   # M4
            use_pathway_level=True,   # M4
        )
        self.model = BioGine(config).to(self.device)
        self.model.set_biology(BiologicalSets(bundle))
        # strict=True: a renamed or absent buffer must fail here, not silently
        # leave a randomly initialised tensor in the forward pass.
        self.model.load_state_dict(blob["model_state"], strict=True)
        self.model.eval()
        self.n_parameters = self.model.n_parameters()

        # -- one full encode, reused by every request ------------------------
        from torch_geometric.data import Batch

        with torch.no_grad():
            mol_batch = Batch.from_data_list(mol_data).to(self.device)
            h, mask = self.model.encode(mol_batch, None)
        self._h, self._mask = h, mask

        # Per-drug set sizes, straight from the bundle the model was given, so
        # a displayed count can never disagree with what was encoded.
        #
        # TWO DIFFERENT COUNTS, deliberately kept apart. The DeepSets protein
        # branch encodes one element per (protein, relation, evidence) triple,
        # so a protein asserted as both a target and an enzyme contributes two
        # elements. Warfarin, for instance, has 112 distinct proteins but 119
        # annotation triples. The Drug Explorer shows distinct proteins; the
        # model encodes triples. Naming them the same thing would put two
        # different numbers for one drug on two pages of the same site.
        self.n_protein_annotations = [len(x) for x in bundle.protein_items]
        self.n_distinct_proteins = [
            len({int(r[0]) for r in x}) for x in bundle.protein_items
        ]
        self.n_pathways = [len(x) for x in bundle.pathway_items]
        self.has_protein = [n > 0 for n in self.n_protein_annotations]
        self.has_pathway = [n > 0 for n in self.n_pathways]

        self.temperature, self.temperature_source = load_frozen_temperature()
        self.startup_seconds = time.perf_counter() - t0

    # -- scoring -----------------------------------------------------------
    @torch.no_grad()
    def score_many(self, pairs: list[tuple[str, str]]) -> list[PairScore]:
        """Score pairs. Order in, order out. Raises on unknown or equal IDs."""
        for a, b in pairs:
            if a not in self.index:
                raise DrugNotInUniverse(a)
            if b not in self.index:
                raise DrugNotInUniverse(b)
            if a == b:
                raise IdenticalDrugs(a)

        idx_a = torch.tensor([self.index[a] for a, _ in pairs], dtype=torch.long)
        idx_b = torch.tensor([self.index[b] for _, b in pairs], dtype=torch.long)
        logits = self.model.score_pairs(
            self._h, self._mask, idx_a.to(self.device), idx_b.to(self.device)
        ).interaction_logit.cpu().numpy().astype(np.float64)

        raw = _sigmoid(logits)
        # The frozen pipeline stored PROBABILITIES and calibrated those, so the
        # calibrated score goes through the same probability round trip rather
        # than dividing the logit directly. Identical arithmetic, including the
        # 1e-12 clip that saturates the extremes.
        calibrated = _sigmoid(_to_logit(raw) / self.temperature)

        out = []
        for (a, b), lg, r, c in zip(pairs, logits, raw, calibrated):
            out.append(
                PairScore(
                    drug_a=a, drug_b=b,
                    raw_logit=float(lg),
                    raw_model_score=float(r),
                    calibrated_model_score=float(c),
                    biology_available_a=bool(self.has_protein[self.index[a]]),
                    biology_available_b=bool(self.has_protein[self.index[b]]),
                )
            )
        return out

    def score(self, drug_a: str, drug_b: str) -> PairScore:
        return self.score_many([(drug_a, drug_b)])[0]
