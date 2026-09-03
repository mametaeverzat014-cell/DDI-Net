#!/usr/bin/env python3
"""
V2 post-hoc interpretability analysis.

Preregistered analyses:
1. Leave-one-protein-out attribution on top-20 seed-0 test pairs.
2. Leave-one-pathway-out attribution on the same pairs.
3. Modality contribution on all seed-0 test pairs.
4. CONTROL E: linear probe bio_emb -> training-DDI-degree.

IMPORTANT
---------
- Frozen BIO-GINE M4, seed 0 only.
- No training or model selection.
- No checkpoint modification.
- Test labels are never used to select explanations.
- Top-20 pairs are selected only by frozen model prediction confidence.
- Attribution is MODEL RELIANCE, not causal mechanism.
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from sklearn.linear_model import Ridge
from sklearn.metrics import r2_score
from scipy.stats import pearsonr, spearmanr
from torch_geometric.data import Batch

from ddinet.models.bio_gine import BiologicalSets


ROOT = Path(__file__).resolve().parents[1]

PREDICTIONS = ROOT / "reports/v2_final/v2_final_pair_predictions.csv"
OUTDIR = ROOT / "reports/v2_interpretability"

PROTEIN_OUT = OUTDIR / "seed0_leave_one_protein_out.csv"
PATHWAY_OUT = OUTDIR / "seed0_leave_one_pathway_out.csv"
MODALITY_OUT = OUTDIR / "seed0_modality_contribution.csv"
PROBE_DRUG_OUT = OUTDIR / "seed0_linear_probe_drugs.csv"
PROBE_SUMMARY_OUT = OUTDIR / "seed0_linear_probe_summary.json"
SUMMARY_OUT = OUTDIR / "interpretability_summary.json"

SEED = 0
TOP_K = 20


def git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:
        return "UNKNOWN"


def load_seed0_predictions() -> pd.DataFrame:
    if not PREDICTIONS.exists():
        raise FileNotFoundError(PREDICTIONS)

    df = pd.read_csv(PREDICTIONS)

    required = {
        "seed", "test_view", "drug_a", "drug_b",
        "label", "prediction"
    }
    missing = required - set(df.columns)
    if missing:
        raise RuntimeError(
            f"Prediction file missing columns: {sorted(missing)}"
        )

    df = df[(df["seed"] == SEED) & (df["test_view"] == "pooled")].copy()

    if len(df) == 0:
        raise RuntimeError("No seed-0 pooled predictions found.")

    if df[["drug_a", "drug_b"]].duplicated().any():
        raise RuntimeError("Duplicate seed-0 pooled test pairs.")

    return df.reset_index(drop=True)


def import_final_runner():
    """
    Import the already-frozen final runner rather than duplicating the
    experimental specification here.
    """
    import importlib.util

    path = ROOT / "scripts/35_v2_final_runner.py"
    if not path.exists():
        raise FileNotFoundError(path)

    spec = importlib.util.spec_from_file_location("v2_final_runner", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def find_seed0_spec(module):
    """Return the exact frozen seed-0 M4 spec from final runner."""
    if not hasattr(module, "load_specs"):
        raise RuntimeError(
            "scripts/35_v2_final_runner.py has no load_specs()."
        )

    specs = module.load_specs()
    hits = [spec for spec in specs if int(spec.seed) == SEED]

    if len(hits) != 1:
        raise RuntimeError(
            f"Expected exactly one frozen seed-0 spec, found {len(hits)}."
        )

    spec = hits[0]

    if str(spec.ablation) != "M4":
        raise RuntimeError(f"Expected M4, got {spec.ablation}")
    if str(spec.biology_source) != "true":
        raise RuntimeError(
            f"Expected true biology, got {spec.biology_source}"
        )
    if str(spec.aggregation) != "mean":
        raise RuntimeError(
            f"Expected mean aggregation, got {spec.aggregation}"
        )
    if str(spec.scheme) != "drug" or int(spec.split_seed) != 0:
        raise RuntimeError("Frozen drug-disjoint split-0 invariant failed.")
    if str(spec.negatives) != "degree_matched":
        raise RuntimeError("Expected degree_matched negatives.")
    if int(spec.eval_negative_seed) != 0:
        raise RuntimeError("Expected evaluation-negative seed 0.")

    return spec

def locate_checkpoint(module, spec) -> Path:
    """
    Resolve the frozen seed-0 checkpoint using the same run identity as the
    final runner.
    """
    run_id = None

    for attr in ("run_id", "id"):
        value = getattr(spec, attr, None)
        if isinstance(value, str) and value:
            run_id = value
            break

    if run_id is None:
        for name in ("run_id", "make_run_id", "spec_run_id"):
            fn = getattr(module, name, None)
            if callable(fn):
                try:
                    run_id = fn(spec)
                    break
                except Exception:
                    pass

    # Frozen seed-0 run ID recorded before final test access.
    if run_id is None:
        run_id = "bd45f84e3c1b2c33"

    candidates = [
        ROOT / "reports/v2_final_checkpoints" / f"{run_id}.pt",
        ROOT / "reports/v2_final/checkpoints" / f"{run_id}.pt",
    ]

    for p in candidates:
        if p.exists():
            return p

    hits = list((ROOT / "reports").rglob(f"{run_id}.pt"))
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise RuntimeError(
            f"Multiple checkpoints found for {run_id}: {hits}"
        )

    raise FileNotFoundError(
        f"Frozen seed-0 checkpoint {run_id}.pt not found."
    )


def build_trainer(module, spec):
    """
    Reconstruct the frozen seed-0 trainer through the exact same project-native
    path used by scripts/run_v2.py. No training is performed.
    """
    import importlib.util

    path = ROOT / "scripts/run_v2.py"
    rv_spec = importlib.util.spec_from_file_location(
        "run_v2_for_interpretability", path
    )
    rv = importlib.util.module_from_spec(rv_spec)
    assert rv_spec.loader is not None
    rv_spec.loader.exec_module(rv)

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA required for frozen V2 interpretability run.")

    universe = rv.load_universe()
    rv.assert_no_ddi_features(universe.drugs, "drugs.parquet")

    split = rv.load_frozen_split(
        universe, spec.scheme, spec.split_seed
    )

    bundle, _ = rv.resolve_biology(
        spec,
        list(universe.drugs["drugbank_id"]),
    )

    mol_graphs = rv.build_mol_graphs(
        list(universe.drugs["name"]),
        list(universe.drugs["smiles"]),
    )

    trainer = rv.V2Trainer(
        spec,
        universe,
        split,
        bundle,
        mol_graphs,
        mode=rv.EvaluationMode.WITH_TEST,
        dataset=None,
        device="cuda",
    )

    # Keep the exact resolved bundle accessible to the post-hoc perturbations.
    trainer.bundle = bundle

    return trainer

def load_frozen_checkpoint(trainer, checkpoint: Path):
    blob = torch.load(
        checkpoint,
        map_location=trainer.device,
        weights_only=False,
    )

    state = blob.get("model_state", blob.get("current_state"))
    if state is None:
        raise RuntimeError("Checkpoint has no model_state/current_state.")

    trainer.model.load_state_dict(state)
    trainer.model.eval()
    return blob


def canonical_top20(df: pd.DataFrame) -> pd.DataFrame:
    """
    Select top-20 by frozen raw model probability only.

    Stable secondary ordering by canonical pair makes ties deterministic.
    Labels are not used.
    """
    x = df.copy()

    x["pair_lo"] = x[["drug_a", "drug_b"]].min(axis=1)
    x["pair_hi"] = x[["drug_a", "drug_b"]].max(axis=1)

    x = x.sort_values(
        ["prediction", "pair_lo", "pair_hi"],
        ascending=[False, True, True],
        kind="mergesort",
    )

    return x.head(TOP_K).reset_index(drop=True)


@torch.no_grad()
def score_global_pairs(trainer, idx_a, idx_b):
    idx_a = torch.as_tensor(idx_a, dtype=torch.long)
    idx_b = torch.as_tensor(idx_b, dtype=torch.long)

    pred = trainer._batch_forward(idx_a, idx_b)
    return pred.interaction_prob().detach().cpu().numpy()


def drug_index_map(trainer):
    bundle = getattr(trainer, "bundle", None)
    if bundle is None:
        bundle = getattr(trainer, "biology_bundle", None)

    if bundle is None:
        raise RuntimeError(
            "Trainer does not expose BiologyBundle as bundle/biology_bundle."
        )

    ids = list(bundle.drug_ids)

    if len(ids) != len(set(ids)):
        raise RuntimeError("Duplicate drug IDs in BiologyBundle.")

    return bundle, {str(d): i for i, d in enumerate(ids)}


def clone_bundle_with_removed_entity(
    bundle,
    drug_idx: int,
    *,
    modality: str,
    entity_id: int,
):
    """
    Remove ALL entries for one protein/pathway entity from one drug.

    Protein removal intentionally removes every relation/evidence tuple for
    that protein: leave-one-PROTEIN-out is entity-level, not evidence-row-level.
    """
    b = copy.deepcopy(bundle)

    if modality == "protein":
        old = list(b.protein_items[drug_idx])
        new = [x for x in old if int(x[0]) != int(entity_id)]
        b.protein_items[drug_idx] = new

    elif modality == "pathway":
        old = list(b.pathway_items[drug_idx])

        def pathway_id(x):
            if isinstance(x, (tuple, list, np.ndarray)):
                return int(x[0])
            return int(x)

        new = [x for x in old if pathway_id(x) != int(entity_id)]
        b.pathway_items[drug_idx] = new

    else:
        raise ValueError(modality)

    return b


def entity_ids_for_drug(bundle, drug_idx: int, modality: str):
    if modality == "protein":
        return sorted({
            int(x[0]) for x in bundle.protein_items[drug_idx]
        })

    if modality == "pathway":
        out = set()
        for x in bundle.pathway_items[drug_idx]:
            if isinstance(x, (tuple, list, np.ndarray)):
                out.add(int(x[0]))
            else:
                out.add(int(x))
        return sorted(out)

    raise ValueError(modality)


def restore_biology(trainer, bundle):
    trainer.model.set_biology(BiologicalSets(bundle))


def leave_one_out(
    trainer,
    bundle,
    id_to_idx,
    top20,
    modality: str,
):
    rows = []

    for rank, row in top20.iterrows():
        da = str(row.drug_a)
        db = str(row.drug_b)

        if da not in id_to_idx or db not in id_to_idx:
            raise RuntimeError(f"Unknown pair IDs: {da}, {db}")

        ia = id_to_idx[da]
        ib = id_to_idx[db]

        baseline = float(
            score_global_pairs(trainer, [ia], [ib])[0]
        )

        # Frozen prediction integrity check.
        if not np.isclose(
            baseline, float(row.prediction), atol=2e-5, rtol=0
        ):
            raise RuntimeError(
                f"Frozen prediction mismatch for {da}/{db}: "
                f"checkpoint={baseline}, CSV={row.prediction}"
            )

        for side, drug_id, drug_idx in (
            ("A", da, ia),
            ("B", db, ib),
        ):
            entities = entity_ids_for_drug(
                bundle, drug_idx, modality
            )

            for entity_id in entities:
                altered = clone_bundle_with_removed_entity(
                    bundle,
                    drug_idx,
                    modality=modality,
                    entity_id=entity_id,
                )

                trainer.model.set_biology(BiologicalSets(altered))

                score = float(
                    score_global_pairs(trainer, [ia], [ib])[0]
                )

                rows.append({
                    "rank": rank + 1,
                    "drug_a": da,
                    "drug_b": db,
                    "label": int(row.label),
                    "baseline_prediction": baseline,
                    "drug_side": side,
                    "ablated_drug": drug_id,
                    "modality": modality,
                    "entity_id": entity_id,
                    "ablated_prediction": score,
                    "delta_probability": baseline - score,
                    "abs_delta_probability": abs(baseline - score),
                })

                restore_biology(trainer, bundle)

    return pd.DataFrame(rows)


def score_with_branch_zeroing(
    trainer,
    idx_a: torch.Tensor,
    idx_b: torch.Tensor,
    *,
    zero_molecular=False,
    zero_protein=False,
    zero_pathway=False,
):
    """
    Post-hoc branch ablation.

    This does NOT retrain the model. Branch representation is replaced by zero
    immediately before the frozen fusion layer. Missingness mask remains the
    original mask because this analysis asks how much the learned representation
    contributes, not how the model reacts to a genuinely missing annotation.
    """
    model = trainer.model
    model.eval()

    pair_nodes = torch.cat([idx_a, idx_b])
    node_idx, inverse = torch.unique(
        pair_nodes, return_inverse=True
    )

    local_a = inverse[:len(idx_a)].to(trainer.device)
    local_b = inverse[len(idx_a):].to(trainer.device)

    mol_batch = Batch.from_data_list(
        [trainer.mol_data[i] for i in node_idx.tolist()]
    ).to(trainer.device)

    prot, path, mask = model.encode_biology(
        node_idx.to(trainer.device)
    )

    parts = []

    if model.mol_encoder is not None:
        mol, _ = model.mol_encoder(
            mol_batch.x,
            mol_batch.edge_index,
            mol_batch.edge_attr,
            mol_batch.batch,
        )
        if zero_molecular:
            mol = torch.zeros_like(mol)
        parts.append(mol)

    if prot is not None:
        if zero_protein:
            prot = torch.zeros_like(prot)
        parts.append(prot)

    if path is not None:
        if zero_pathway:
            path = torch.zeros_like(path)
        parts.append(path)

    h = model.fusion_norm(
        model.fusion(torch.cat(parts, dim=-1))
    )

    pred = model.score_pairs(
        h,
        mask,
        local_a,
        local_b,
    )

    return pred.interaction_prob().detach().cpu().numpy()


@torch.no_grad()
def modality_contribution(trainer, predictions, id_to_idx, chunk=4096):
    rows = []

    for start in range(0, len(predictions), chunk):
        part = predictions.iloc[start:start + chunk]

        ia = torch.tensor(
            [id_to_idx[str(x)] for x in part.drug_a],
            dtype=torch.long,
        )
        ib = torch.tensor(
            [id_to_idx[str(x)] for x in part.drug_b],
            dtype=torch.long,
        )

        full = score_global_pairs(trainer, ia, ib)

        mol0 = score_with_branch_zeroing(
            trainer, ia, ib, zero_molecular=True
        )
        prot0 = score_with_branch_zeroing(
            trainer, ia, ib, zero_protein=True
        )
        path0 = score_with_branch_zeroing(
            trainer, ia, ib, zero_pathway=True
        )

        for j, (_, r) in enumerate(part.iterrows()):
            rows.append({
                "drug_a": str(r.drug_a),
                "drug_b": str(r.drug_b),
                "label": int(r.label),
                "baseline_prediction": float(full[j]),
                "without_molecular": float(mol0[j]),
                "without_protein": float(prot0[j]),
                "without_pathway": float(path0[j]),
                "molecular_delta": float(full[j] - mol0[j]),
                "protein_delta": float(full[j] - prot0[j]),
                "pathway_delta": float(full[j] - path0[j]),
                "abs_molecular_delta": float(abs(full[j] - mol0[j])),
                "abs_protein_delta": float(abs(full[j] - prot0[j])),
                "abs_pathway_delta": float(abs(full[j] - path0[j])),
            })

    out = pd.DataFrame(rows)

    if len(out) != len(predictions):
        raise RuntimeError("Modality output row count mismatch.")

    err = np.max(
        np.abs(
            out["baseline_prediction"].to_numpy()
            - predictions["prediction"].to_numpy()
        )
    )

    if err > 2e-5:
        raise RuntimeError(
            f"Frozen prediction integrity failed; max error={err}"
        )

    return out


@torch.no_grad()
def biological_embeddings(trainer):
    """
    Return concatenated learned protein/pathway representations for all drugs.

    This is the preregistered bio_emb used by CONTROL E. Molecular embeddings
    are deliberately excluded.
    """
    model = trainer.model
    prot, path, _ = model.encode_biology(None)

    parts = []
    if prot is not None:
        parts.append(prot)
    if path is not None:
        parts.append(path)

    if not parts:
        raise RuntimeError("Model exposes no biological embedding.")

    return torch.cat(parts, dim=-1).detach().cpu().numpy()


def training_ddi_degree(trainer, n_drugs: int):
    """
    Degree is calculated ONLY from positive training DDI edges.

    Test DDI edges are never used to construct the probe target.
    """
    train = trainer._train

    a = train["idx_a"].cpu().numpy()
    b = train["idx_b"].cpu().numpy()
    y = train["labels"].cpu().numpy()

    degree = np.zeros(n_drugs, dtype=np.float64)

    pos = y == 1
    np.add.at(degree, a[pos], 1)
    np.add.at(degree, b[pos], 1)

    return degree


def infer_train_test_drugs(trainer, bundle):
    """Return frozen drug-disjoint train/test drug indices.

    Membership comes directly from the preregistered DrugLevelSplit rather
    than being inferred from pooled pair buckets.
    """
    id_to_idx = {drug_id: i for i, drug_id in enumerate(bundle.drug_ids)}

    missing_train = sorted(set(trainer.split.train_drugs) - set(id_to_idx))
    missing_test = sorted(set(trainer.split.test_drugs) - set(id_to_idx))
    if missing_train or missing_test:
        raise RuntimeError(
            f"Frozen split contains drugs absent from BiologyBundle: "
            f"train={len(missing_train)}, test={len(missing_test)}"
        )

    train_drugs = np.asarray(
        sorted(id_to_idx[d] for d in trainer.split.train_drugs),
        dtype=np.int64,
    )
    test_drugs = np.asarray(
        sorted(id_to_idx[d] for d in trainer.split.test_drugs),
        dtype=np.int64,
    )

    overlap = np.intersect1d(train_drugs, test_drugs)
    if len(overlap):
        raise RuntimeError(
            f"Drug-disjoint integrity failure: "
            f"{len(overlap)} frozen train/test drugs overlap."
        )

    return train_drugs, test_drugs


def linear_probe(trainer, bundle):
    emb = biological_embeddings(trainer)
    n = len(bundle.drug_ids)

    if emb.shape[0] != n:
        raise RuntimeError("Biological embedding/drug count mismatch.")

    degree = training_ddi_degree(trainer, n)
    train_drugs, test_drugs = infer_train_test_drugs(
        trainer, bundle
    )

    # Standardize using training drugs ONLY.
    mu = emb[train_drugs].mean(axis=0)
    sd = emb[train_drugs].std(axis=0)
    sd[sd < 1e-12] = 1.0

    X = (emb - mu) / sd

    # Ridge is a linear probe with fixed regularization.
    # No test-set tuning.
    probe = Ridge(alpha=1.0)
    probe.fit(X[train_drugs], degree[train_drugs])

    pred_train = probe.predict(X[train_drugs])
    pred_test = probe.predict(X[test_drugs])

    r2_train = float(
        r2_score(degree[train_drugs], pred_train)
    )
    r2_test = float(
        r2_score(degree[test_drugs], pred_test)
    )

    pearson_test = float(
        pearsonr(degree[test_drugs], pred_test).statistic
    )
    spearman_test = float(
        spearmanr(degree[test_drugs], pred_test).statistic
    )

    split = np.full(n, "other", dtype=object)
    split[train_drugs] = "train"
    split[test_drugs] = "test"

    pred_all = probe.predict(X)

    drug_df = pd.DataFrame({
        "drug_id": list(bundle.drug_ids),
        "split": split,
        "training_ddi_degree": degree,
        "probe_prediction": pred_all,
    })

    summary = {
        "probe": "Ridge(alpha=1.0)",
        "target": "positive training-DDI degree only",
        "features": "frozen seed-0 BIO-GINE biological embedding",
        "n_train_drugs": int(len(train_drugs)),
        "n_test_drugs": int(len(test_drugs)),
        "r2_train": r2_train,
        "r2_test": r2_test,
        "pearson_test": pearson_test,
        "spearman_test": spearman_test,
        "elevated_concern_r2_gt_0_4": bool(r2_test > 0.4),
        "f4_probe_component_r2_gt_0_6": bool(r2_test > 0.6),
        "note": (
            "CONTROL E measures whether the learned biological "
            "embedding encodes training-DDI degree/popularity. "
            "It is not a causal interpretation."
        ),
    }

    return drug_df, summary


def dry_run():
    pred = load_seed0_predictions()
    top20 = canonical_top20(pred)

    print("V2 INTERPRETABILITY DRY RUN")
    print("--------------------------")
    print(f"git HEAD: {git_head()}")
    print(f"seed: {SEED}")
    print(f"pooled seed-0 test pairs: {len(pred):,}")
    print(f"top-K attribution pairs: {len(top20)}")
    print(
        f"prediction range top20: "
        f"{top20.prediction.min():.6f} .. "
        f"{top20.prediction.max():.6f}"
    )
    print("test labels were NOT used for top-20 selection")
    print("no checkpoint was opened")
    print("no model inference was performed")
    print("no output files were written")
    print()
    print("Planned:")
    print("  1. protein entity leave-one-out")
    print("  2. pathway entity leave-one-out")
    print("  3. molecular/protein/pathway branch contribution")
    print("  4. CONTROL E bio_emb -> training-DDI-degree")
    print()
    print("DRY RUN COMPLETE — INTERPRETABILITY WAS NOT EXECUTED")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        dry_run()
        return

    outputs = [
        PROTEIN_OUT,
        PATHWAY_OUT,
        MODALITY_OUT,
        PROBE_DRUG_OUT,
        PROBE_SUMMARY_OUT,
        SUMMARY_OUT,
    ]

    existing = [p for p in outputs if p.exists()]
    if existing:
        raise RuntimeError(
            "Refusing overwrite of frozen interpretability outputs: "
            + ", ".join(map(str, existing))
        )

    torch.manual_seed(SEED)
    np.random.seed(SEED)

    final_runner = import_final_runner()
    spec = find_seed0_spec(final_runner)
    checkpoint = locate_checkpoint(final_runner, spec)

    trainer = build_trainer(final_runner, spec)
    blob = load_frozen_checkpoint(trainer, checkpoint)

    test_data = trainer._pooled("test")
    if test_data is None or len(test_data["labels"]) == 0:
        raise RuntimeError(
            "Frozen pooled test dataset is empty."
        )

    predictions = load_seed0_predictions()
    top20 = canonical_top20(predictions)

    bundle, id_to_idx = drug_index_map(trainer)

    print(f"checkpoint: {checkpoint}")
    print(f"test pairs: {len(predictions):,}")
    print(f"top attribution pairs: {len(top20)}")

    # Baseline integrity before any perturbation.
    sample = top20.iloc[:5]
    ia = [id_to_idx[str(x)] for x in sample.drug_a]
    ib = [id_to_idx[str(x)] for x in sample.drug_b]
    check = score_global_pairs(trainer, ia, ib)

    if not np.allclose(
        check,
        sample.prediction.to_numpy(),
        atol=2e-5,
        rtol=0,
    ):
        raise RuntimeError(
            "Frozen seed-0 checkpoint does not reproduce "
            "stored final predictions."
        )

    print("Frozen prediction integrity: PASS")

    print("Running leave-one-protein-out...")
    protein = leave_one_out(
        trainer, bundle, id_to_idx, top20, "protein"
    )

    restore_biology(trainer, bundle)

    print("Running leave-one-pathway-out...")
    pathway = leave_one_out(
        trainer, bundle, id_to_idx, top20, "pathway"
    )

    restore_biology(trainer, bundle)

    print("Running all-test-pair modality contribution...")
    modality = modality_contribution(
        trainer,
        predictions,
        id_to_idx,
    )

    restore_biology(trainer, bundle)

    print("Running CONTROL E linear probe...")
    probe_drugs, probe_summary = linear_probe(
        trainer, bundle
    )

    OUTDIR.mkdir(parents=True, exist_ok=True)

    protein.to_csv(PROTEIN_OUT, index=False)
    pathway.to_csv(PATHWAY_OUT, index=False)
    modality.to_csv(MODALITY_OUT, index=False)
    probe_drugs.to_csv(PROBE_DRUG_OUT, index=False)

    PROBE_SUMMARY_OUT.write_text(
        json.dumps(probe_summary, indent=2),
        encoding="utf-8",
    )

    summary = {
        "analysis": "V2 post-hoc interpretability",
        "seed": SEED,
        "git_commit_at_execution": git_head(),
        "checkpoint": str(checkpoint.relative_to(ROOT)),
        "checkpoint_run_id": blob.get(
            "run_id", "bd45f84e3c1b2c33"
        ),
        "n_test_pairs": int(len(predictions)),
        "n_top_pairs": int(len(top20)),
        "n_protein_ablations": int(len(protein)),
        "n_pathway_ablations": int(len(pathway)),
        "n_modality_rows": int(len(modality)),
        "linear_probe": probe_summary,
        "interpretation_rule": (
            "Attribution values describe frozen-model reliance "
            "under post-hoc perturbation. They are not causal "
            "biological mechanisms or clinical recommendations."
        ),
    }

    SUMMARY_OUT.write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    print()
    print("INTERPRETABILITY COMPLETE")
    print(f"protein ablations: {len(protein):,}")
    print(f"pathway ablations: {len(pathway):,}")
    print(f"modality pairs: {len(modality):,}")
    print(
        "CONTROL E test R^2: "
        f"{probe_summary['r2_test']:.6f}"
    )
    print(
        "CONTROL E test Pearson: "
        f"{probe_summary['pearson_test']:.6f}"
    )
    print(
        "CONTROL E test Spearman: "
        f"{probe_summary['spearman_test']:.6f}"
    )
    print()
    print(
        "Interpretation: MODEL RELIANCE, "
        "not causal mechanism."
    )


if __name__ == "__main__":
    main()
