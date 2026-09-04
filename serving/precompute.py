"""Freeze the drug encodings and the pair decoder into one small artifact.

WHY. Serving the full pipeline costs ~1.15 GiB of RSS, almost all of it the
import weight of torch, torch_geometric and rdkit. None of those do any work at
request time: every drug's representation is fixed, so the encoders run once and
are then dead weight. What a request actually needs is the cached ``h``/``mask``
(0.89 MB) and the pair decoder (132,609 of the model's 1,122,804 parameters).

This script runs the FULL verified pipeline once — integrity gate, frozen
checkpoint, real encoders — and writes those two things to an .npz. serving
/lean.py then answers requests from the artifact alone, with numpy and nothing
else, which is what makes a 512 MB host viable.

WHAT THIS IS NOT. It is not a second model and it is not a re-derivation.
The encodings are the frozen model's own outputs, produced here by the same code
path the parity test validates; the decoder weights are copied out of the
checkpoint unchanged. tests/test_serving.py asserts the lean path agrees with
the torch path, so the two cannot drift apart silently.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import sys

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "runtime" / "model_assets" / "lean_decoder_v1.npz"


def build(out: Path = ARTIFACT) -> dict:
    from .engine import FrozenBioGineEngine

    engine = FrozenBioGineEngine()          # runs the integrity gate
    mlp = engine.model.pair_mlp

    # nn.Sequential: Linear, ReLU, Dropout, Linear, ReLU, Dropout, Linear.
    # Dropout is identity under eval(); the three Linears are all that remain.
    import torch.nn as nn

    linears = [m for m in mlp if isinstance(m, nn.Linear)]
    assert len(linears) == 3, f"pair decoder shape changed: {mlp}"

    # Documented pairs, as index pairs rather than IDs: 1,705 drugs fit in
    # int16, so the whole label table is ~766 KB and the lean server needs no
    # pandas or pyarrow. This is display metadata only — see serving/api.py on
    # why it is never an inference feature.
    from ddinet.data.v2_dataset import load_universe

    universe = load_universe()
    idx = engine.index
    documented = np.array(
        sorted({
            (min(idx[a], idx[b]), max(idx[a], idx[b]))
            for a, b in zip(universe.pairs["drug_a"], universe.pairs["drug_b"])
            if a in idx and b in idx
        }),
        dtype=np.int16,
    )

    payload = {
        "documented_pairs": documented,
        "h": engine._h.detach().cpu().numpy().astype(np.float32),
        "mask": engine._mask.detach().cpu().numpy().astype(np.float32),
        "drug_ids": np.array(engine.ordered_ids, dtype=object),
        "temperature": np.float64(engine.temperature),
        "n_protein_annotations": np.array(engine.n_protein_annotations, dtype=np.int32),
        "n_distinct_proteins": np.array(engine.n_distinct_proteins, dtype=np.int32),
        "n_pathways": np.array(engine.n_pathways, dtype=np.int32),
    }
    for i, lin in enumerate(linears):
        payload[f"w{i}"] = lin.weight.detach().cpu().numpy().astype(np.float32)
        payload[f"b{i}"] = lin.bias.detach().cpu().numpy().astype(np.float32)

    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, **payload)

    meta = {
        "artifact": str(out.relative_to(ROOT)),
        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "size_bytes": out.stat().st_size,
        "n_drugs": len(engine.ordered_ids),
        "hidden_dim": int(payload["h"].shape[1]),
        "source_checkpoint_sha256": engine.integrity.checkpoint_sha256,
        "frozen_tag": engine.integrity.frozen_tag,
        "temperature": float(engine.temperature),
        "n_documented_pairs": int(len(documented)),
    }
    (out.with_suffix(".json")).write_text(json.dumps(meta, indent=2) + "\n")
    return meta


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
