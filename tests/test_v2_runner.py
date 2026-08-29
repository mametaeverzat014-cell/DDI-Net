"""Tests the V2 runner must pass before any V2 model is trained.

The load-bearing ones are the seal tests. The whole V2 programme is a
preregistered comparison whose validity depends on the test set being unopened
during model development, and "we were careful" is not a mechanism. These check
that the mechanism exists: that test buckets are gone before negatives are
sampled, that the trainer refuses to produce test predictions, and that the
results schema has nowhere to put a test metric.
"""
import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch

from ddinet.data.biology import EVIDENCE_POLICIES, load_biology
from ddinet.data.negatives import NegativeSamplingConfig, build_dataset
from ddinet.data.v2_dataset import (
    DATASET_VERSION, EXCLUDED_DRUG, MECHANISM_V1, N_DRUGS, N_POSITIVE_PAIRS,
    assert_no_ddi_features, load_frozen_split, load_universe,
    verify_matches_phase_a2,
)
from ddinet.models.bio_gine import BiologicalSets, BioGine, BioGineConfig
from ddinet.training.v2_trainer import (
    CONTROL_F_EDGES, EvaluationMode, TestSetSealed, V2RunSpec, V2Trainer,
    build_v2_dataset, resolve_biology,
)

ROOT = Path(__file__).resolve().parents[1]

frozen_only = pytest.mark.skipif(
    not (MECHANISM_V1 / "drugs.parquet").exists(),
    reason="frozen DDI_MECH_1705_V1 snapshot not present in this checkout",
)


def _load_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runner():
    return _load_script("run_v2", ROOT / "scripts" / "run_v2.py")


@pytest.fixture(scope="module")
def grid():
    return _load_script("run_v2_grid", ROOT / "scripts" / "run_v2_grid.py")


@pytest.fixture(scope="module")
def universe():
    return load_universe()


@pytest.fixture(scope="module")
def split(universe):
    return load_frozen_split(universe, "drug", 0)


# 1 -- the authoritative universe -----------------------------------------
@frozen_only
def test_universe_is_the_authoritative_1705_drug_set(universe):
    assert len(universe.drugs) == N_DRUGS == 1705
    assert len(universe.pairs) == N_POSITIVE_PAIRS == 191392
    assert DATASET_VERSION == "DDI_MECH_1705_V1"


@frozen_only
def test_universe_matches_the_phase_a2_derivation(universe):
    """The freeze must be equal to what Phase A-2 derived, or the V2 numbers
    are not comparable to the Phase A-2 baselines they are tested against."""
    report = verify_matches_phase_a2(universe)
    assert report["drugs_match"] and report["pairs_match"], report


@frozen_only
def test_db11630_is_absent(universe):
    assert EXCLUDED_DRUG not in set(universe.drugs["drugbank_id"])
    assert EXCLUDED_DRUG not in set(universe.pairs["drug_a"])
    assert EXCLUDED_DRUG not in set(universe.pairs["drug_b"])


@frozen_only
def test_truncated_universe_is_rejected(tmp_path, universe):
    """A silently short Parquet must fail loudly, not train on 900 drugs."""
    root = tmp_path / "short"
    root.mkdir()
    pd.read_parquet(MECHANISM_V1 / "drugs.parquet").head(900).to_parquet(
        root / "drugs.parquet")
    pd.read_parquet(MECHANISM_V1 / "ddi_positive_labels.parquet").to_parquet(
        root / "ddi_positive_labels.parquet")
    with pytest.raises(ValueError, match="expected 1705"):
        load_universe(root)


# 2 -- exact split loading -------------------------------------------------
@frozen_only
def test_frozen_split_is_loaded_not_recomputed(universe, split):
    """The drug partition must equal the recorded assignment, drug for drug."""
    frozen = pd.read_csv(MECHANISM_V1 / "split_assignments.csv")
    rows = frozen[(frozen["scheme"] == "drug") & (frozen["seed"] == 0)]
    expected = {a: set(g["project_drug_id"]) for a, g in rows.groupby("assignment")}
    assert split.train_drugs == expected["train"]
    assert split.val_drugs == expected["val"]
    assert split.test_drugs == expected["test"]


@frozen_only
def test_frozen_split_reproduces_phase_a2_bucket_sizes(split):
    assert len(split.train_drugs) == 1195
    assert len(split.buckets["test_S2"]) == 38466
    assert len(split.buckets["test_S3"]) == 3879


@frozen_only
@pytest.mark.parametrize("scheme,seed", [("drug", s) for s in range(5)]
                                        + [("scaffold", s) for s in range(5)])
def test_every_frozen_split_loads_and_is_leak_free(universe, scheme, seed):
    sp = load_frozen_split(universe, scheme, seed)
    sp.assert_no_leakage()          # raises on overlap
    assert sp.train_drugs and sp.val_drugs and sp.test_drugs


def test_random_pair_scheme_is_refused_rather_than_approximated(universe):
    with pytest.raises(ValueError, match="random_pair"):
        load_frozen_split(universe, "random_pair", 0)


# 3 -- no DDI features -----------------------------------------------------
@frozen_only
def test_no_drug_drug_edges_in_the_biological_graph():
    """The preregistration's "zero INTERACTS_WITH edges" is a claim about
    DRUG-DRUG edges: the biological graph must not contain the DDI relation in
    any form, or the model would be handed the labels as features.

    The file DOES contain 15,087 ``PHYSICALLY_INTERACTS_WITH`` rows. Those are
    Reactome protein-protein interactions (source_type and target_type both
    PROTEIN) and are a different relation entirely. They are also unused: M4
    does not read protein_protein_edges, and the config marks it "not used in
    M4 (no GNN)". Pinned here so the distinction is explicit rather than
    rediscovered by a substring match.
    """
    edges = pd.read_parquet(MECHANISM_V1 / "biological_edges.parquet")
    pairs = set(zip(edges["source_type"].astype(str),
                    edges["target_type"].astype(str)))
    assert ("DRUG", "DRUG") not in pairs
    assert not edges["relation_type"].astype(str).str.upper().eq("INTERACTS_WITH").any()
    ppi = edges[edges["relation_type"].astype(str) == "PHYSICALLY_INTERACTS_WITH"]
    assert set(zip(ppi["source_type"], ppi["target_type"])) == {("PROTEIN", "PROTEIN")}


@frozen_only
def test_the_biology_loader_never_opens_the_ppi_or_label_files(universe):
    """M4 is DeepSets over sets, not a GNN: protein-protein edges are outside
    the preregistered architecture, and the DDI labels are never a feature."""
    source = (ROOT / "src" / "ddinet" / "data" / "biology.py").read_text()
    for forbidden in ("protein_protein_edges", "ddi_positive_labels",
                      "biological_edges"):
        reads = [line for line in source.splitlines()
                 if forbidden in line and ("read_parquet" in line or "read_csv" in line)]
        assert not reads, f"biology.py reads {forbidden}: {reads}"


def test_ddi_derived_columns_are_rejected():
    frame = pd.DataFrame({"name": ["A"], "ddi_degree": [7]})
    with pytest.raises(ValueError, match="ddi_degree"):
        assert_no_ddi_features(frame, "test frame")


@frozen_only
def test_bio_gine_receives_no_ddi_graph(universe, split):
    """Structural, not a flag: the model has no parameter to put one in."""
    import inspect
    sig = inspect.signature(BioGine.forward)
    assert list(sig.parameters) == ["self", "mol_batch", "idx_a", "idx_b"]
    assert not hasattr(BioGine, "graph_encoder")
    # Parse the module, do not grep it. The docstring names FeatureBundle
    # precisely to explain why it is NOT used, and a textual match fires on that
    # explanation - which is how this test first failed. An AST walk sees
    # imports, names and attributes, and nothing inside a string.
    import ast

    tree = ast.parse((ROOT / "src" / "ddinet" / "training"
                      / "v2_trainer.py").read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[-1] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported |= {a.name for a in node.names}
            if node.module:
                imported.add(node.module.split(".")[-1])
    forbidden_imports = {"FeatureBundle", "DDIGraph", "build_feature_bundle",
                         "ddi_graph", "build"}
    assert not (imported & forbidden_imports), (
        f"v2_trainer imports DDI-graph machinery: {sorted(imported & forbidden_imports)}"
    )

    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    used |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    forbidden_names = {"edge_index", "edge_type", "node_features",
                       "graph_encoder", "FeatureBundle", "DDIGraph"}
    assert not (used & forbidden_names), (
        f"v2_trainer references DDI-graph objects: {sorted(used & forbidden_names)}"
    )


# 4 -- the evidence ladder -------------------------------------------------
@frozen_only
@pytest.mark.parametrize("ablation", ["M0", "M1", "M2", "M3", "M4"])
def test_every_ablation_loads(universe, ablation):
    spec = V2RunSpec(ablation=ablation)
    bundle, provenance = resolve_biology(spec, list(universe.drugs["drugbank_id"]))
    assert bundle.n_drugs == N_DRUGS
    assert provenance["ablation"] == ablation
    assert bundle.policy.name == ablation


@frozen_only
def test_ablation_ladder_is_monotone_in_evidence(universe):
    sizes = []
    for ablation in ("M0", "M1", "M2", "M3"):
        bundle, _ = resolve_biology(V2RunSpec(ablation=ablation),
                                    list(universe.drugs["drugbank_id"]))
        sizes.append(sum(len(x) for x in bundle.protein_items))
    assert sizes == sorted(sizes)


def test_unknown_ablation_is_refused():
    with pytest.raises(ValueError, match="Unknown ablation"):
        resolve_biology(V2RunSpec(ablation="M9"), ["DB00006"])


# 5 -- true and shuffled biology ------------------------------------------
@frozen_only
def test_true_biology_loads_and_records_its_source(universe):
    bundle, prov = resolve_biology(V2RunSpec(biology_source="true"),
                                   list(universe.drugs["drugbank_id"]))
    assert prov["biology_source"] == "true"
    assert bundle.source == "true"
    assert "control_f_seed" not in prov


@pytest.mark.skipif(not CONTROL_F_EDGES.exists(), reason="CONTROL F not built")
def test_shuffled_biology_loads_the_frozen_artefact(universe):
    bundle, prov = resolve_biology(V2RunSpec(biology_source="shuffled"),
                                   list(universe.drugs["drugbank_id"]))
    assert bundle.source == "shuffled"
    assert prov["control_f_seed"] == 20260829
    assert len(prov["control_f_manifest_sha256"]) == 64
    assert len(prov["control_f_edges_sha256"]) == 64


@pytest.mark.skipif(not CONTROL_F_EDGES.exists(), reason="CONTROL F not built")
def test_shuffled_biology_preserves_protein_set_sizes(universe):
    drug_ids = list(universe.drugs["drugbank_id"])
    true, _ = resolve_biology(V2RunSpec(biology_source="true"), drug_ids)
    shuf, _ = resolve_biology(V2RunSpec(biology_source="shuffled"), drug_ids)
    assert [len(x) for x in true.protein_items] == [len(x) for x in shuf.protein_items]


def test_missing_control_f_raises_rather_than_falling_back(monkeypatch):
    """A shuffled run that quietly used true biology would report the exact
    opposite of what it measured."""
    import ddinet.training.v2_trainer as mod
    monkeypatch.setattr(mod, "CONTROL_F_EDGES", Path("/nonexistent/shuffled.parquet"))
    with pytest.raises(FileNotFoundError, match="CONTROL F"):
        resolve_biology(V2RunSpec(biology_source="shuffled"), ["DB00006"])


def test_unknown_biology_source_is_refused():
    with pytest.raises(ValueError, match="biology_source"):
        resolve_biology(V2RunSpec(biology_source="synthetic"), ["DB00006"])


# 6 -- missing biology -----------------------------------------------------
@frozen_only
def test_drugs_without_biology_are_present_not_dropped(universe):
    bundle, _ = resolve_biology(V2RunSpec(), list(universe.drugs["drugbank_id"]))
    assert bundle.n_drugs == N_DRUGS
    assert int((~bundle.has_protein()).sum()) == 67
    assert int((~bundle.has_pathway()).sum()) == 91


@frozen_only
def test_missing_biology_drugs_encode_finitely(universe):
    bundle, _ = resolve_biology(V2RunSpec(), list(universe.drugs["drugbank_id"]))
    model = BioGine(BioGineConfig(
        n_protein_vocab=bundle.n_proteins, n_pathway_vocab=bundle.n_pathways,
        use_molecular_branch=False, bio_dim=8, hidden_dim=16))
    model.set_biology(BiologicalSets(bundle))
    model.eval()
    no_prot = np.where(~bundle.has_protein())[0][:5]
    no_path = np.where(~bundle.has_pathway())[0][:5]
    idx = torch.tensor(sorted(set(no_prot.tolist()) | set(no_path.tolist())))
    with torch.no_grad():
        h, mask = model.encode(node_idx=idx)
    assert torch.isfinite(h).all()
    assert h.shape[0] == len(idx)


@frozen_only
def test_subset_encoding_equals_full_encoding(universe):
    """The minibatch path must be the same function, not an approximation."""
    bundle, _ = resolve_biology(V2RunSpec(), list(universe.drugs["drugbank_id"]))
    model = BioGine(BioGineConfig(
        n_protein_vocab=bundle.n_proteins, n_pathway_vocab=bundle.n_pathways,
        use_molecular_branch=False, bio_dim=8, hidden_dim=16))
    model.set_biology(BiologicalSets(bundle))
    model.eval()
    no_prot = np.where(~bundle.has_protein())[0][:2].tolist()
    no_path = np.where(~bundle.has_pathway())[0][:2].tolist()
    idx = torch.tensor(sorted(set(no_prot + no_path + [0, 7, 1704, 900])))
    with torch.no_grad():
        full, full_mask = model.encode()
        sub, sub_mask = model.encode(node_idx=idx)
    assert torch.allclose(full[idx], sub, atol=1e-6)
    assert torch.equal(full_mask[idx], sub_mask)


# 7 -- symmetry ------------------------------------------------------------
@frozen_only
def test_pair_prediction_is_symmetric_on_real_biology(universe):
    bundle, _ = resolve_biology(V2RunSpec(), list(universe.drugs["drugbank_id"]))
    model = BioGine(BioGineConfig(
        n_protein_vocab=bundle.n_proteins, n_pathway_vocab=bundle.n_pathways,
        use_molecular_branch=False, bio_dim=8, hidden_dim=16))
    model.set_biology(BiologicalSets(bundle))
    model.eval()
    with torch.no_grad():
        h, mask = model.encode()
        a = torch.tensor([0, 5, 103, 900, 1704])
        b = torch.tensor([1704, 900, 103, 5, 0])
        ab = model.score_pairs(h, mask, a, b).interaction_logit
        ba = model.score_pairs(h, mask, b, a).interaction_logit
    assert torch.equal(ab, ba)


# 8 -- negative sampling ---------------------------------------------------
@frozen_only
def test_validation_negatives_are_deterministic_across_train_seeds(universe, split):
    """Every grid configuration must be selected on the SAME validation pairs."""
    frames = []
    for seed in (0, 1, 2):
        ds = build_v2_dataset(replace(V2RunSpec(), seed=seed), universe, split,
                              EvaluationMode.VALIDATION_ONLY)
        val = ds[ds["bucket"].str.startswith("val")].reset_index(drop=True)
        frames.append(val[["drug_a", "drug_b", "label", "bucket"]])
    for f in frames[1:]:
        assert f.equals(frames[0])


@frozen_only
def test_training_negatives_still_vary_with_the_run_seed(universe, split):
    def train_negatives(seed):
        ds = build_v2_dataset(replace(V2RunSpec(), seed=seed), universe, split,
                              EvaluationMode.VALIDATION_ONLY)
        t = ds[(ds["bucket"] == "train") & (ds["label"] == 0)]
        return set(map(tuple, t[["drug_a", "drug_b"]].to_numpy()))
    assert train_negatives(0) != train_negatives(1)


@frozen_only
def test_no_sampled_negative_is_a_documented_interaction(universe, split):
    ds = build_v2_dataset(V2RunSpec(), universe, split,
                          EvaluationMode.VALIDATION_ONLY)
    negatives = ds[ds["label"] == 0]
    keys = universe.positive_keys
    offenders = [(a, b) for a, b in zip(negatives["drug_a"], negatives["drug_b"])
                 if ((a, b) if a < b else (b, a)) in keys]
    assert not offenders


@frozen_only
def test_v2_reuses_the_phase_a2_sampler_not_a_copy(universe, split):
    """Same call, same config object, same output - not a similar sampler."""
    spec = V2RunSpec(seed=0)
    ours = build_v2_dataset(spec, universe, split, EvaluationMode.VALIDATION_ONLY)
    kept = {n: f for n, f in split.buckets.items() if not n.startswith("test")}
    from ddinet.data.split import DrugLevelSplit
    trimmed = DrugLevelSplit(split.train_drugs, split.val_drugs, split.test_drugs,
                             kept, split.discarded, split.group_by, split.seed)
    theirs, _ = build_dataset(
        trimmed, universe.drug_names, universe.positive_keys,
        NegativeSamplingConfig(strategy="degree_matched", ratio=1.0, seed=0,
                               eval_seed=0))
    assert ours.equals(theirs)


# 9 -- train-only preprocessing -------------------------------------------
@frozen_only
def test_bio_rf_svd_is_fitted_on_training_drugs_only(universe, split):
    from ddinet.models.bio_baselines import BiologicalFeaturizer
    bundle, _ = resolve_biology(V2RunSpec(), list(universe.drugs["drugbank_id"]))
    train = sorted(split.train_drugs)
    f = BiologicalFeaturizer(bundle, protein_components=8, pathway_components=4)
    f.fit(train)
    assert f.features.fitted_on == len(train) == 1195
    assert set(f._svd) == {"protein", "pathway"}


@frozen_only
def test_bio_gine_has_no_fitted_preprocessing_at_all(universe):
    """Embeddings are learned by gradient descent inside the split; there is no
    transform fitted over the drug population that could straddle the boundary."""
    bundle, _ = resolve_biology(V2RunSpec(), list(universe.drugs["drugbank_id"]))
    model = BioGine(BioGineConfig(
        n_protein_vocab=bundle.n_proteins, n_pathway_vocab=bundle.n_pathways,
        use_molecular_branch=False, bio_dim=8, hidden_dim=16))
    for name in ("scaler", "svd", "pca", "normalizer"):
        assert not hasattr(model, name)


# 10 -- the seal -----------------------------------------------------------
@frozen_only
def test_validation_only_dataset_contains_no_test_bucket(universe, split):
    ds = build_v2_dataset(V2RunSpec(), universe, split,
                          EvaluationMode.VALIDATION_ONLY)
    assert not any(b.startswith("test") for b in ds["bucket"].unique())


@frozen_only
def test_validation_only_never_samples_a_test_negative(universe, split):
    """Not merely filtered afterwards: the test pairs never enter the sampler."""
    ds = build_v2_dataset(V2RunSpec(), universe, split,
                          EvaluationMode.VALIDATION_ONLY)
    seen = set(ds["drug_a"]) | set(ds["drug_b"])
    assert not (seen & split.test_drugs)


@frozen_only
def test_dropping_test_does_not_disturb_validation_negatives(universe, split):
    """The seal must be free: if removing test changed the validation sample,
    validation_only and with_test runs would not be comparable."""
    sealed = build_v2_dataset(V2RunSpec(), universe, split,
                              EvaluationMode.VALIDATION_ONLY)
    full = build_v2_dataset(V2RunSpec(), universe, split, EvaluationMode.WITH_TEST)
    cols = ["drug_a", "drug_b", "label", "bucket"]
    a = sealed[sealed["bucket"].str.startswith("val")].reset_index(drop=True)[cols]
    b = full[full["bucket"].str.startswith("val")].reset_index(drop=True)[cols]
    assert a.equals(b)


@frozen_only
def test_trainer_refuses_test_prediction_in_validation_only(universe, split):
    bundle, _ = resolve_biology(V2RunSpec(), list(universe.drugs["drugbank_id"]))
    spec = V2RunSpec(max_epochs=1)
    trainer = _tiny_trainer(spec, universe, split, bundle)
    with pytest.raises(TestSetSealed, match="validation_only"):
        trainer.predict_test()


@frozen_only
def test_trainer_holds_no_test_bucket(universe, split):
    bundle, _ = resolve_biology(V2RunSpec(), list(universe.drugs["drugbank_id"]))
    trainer = _tiny_trainer(V2RunSpec(), universe, split, bundle)
    assert not any(b.startswith("test") for b in trainer.buckets)
    assert trainer._pooled("test") is None


def _tiny_trainer(spec, universe, split, bundle):
    """A trainer over a deliberately small pair sample, for API-level tests."""
    dataset = build_v2_dataset(spec, universe, split, EvaluationMode.VALIDATION_ONLY)
    # BOTH classes from every bucket. head(200) alone takes the first 200 rows,
    # and the sampler emits positives before negatives, so it produced a
    # single-class validation set - AUPRC came back NaN, no epoch ever counted
    # as an improvement, and the run looked like it worked.
    small = pd.concat(
        [g.head(100) for _, g in dataset.groupby(["bucket", "label"], sort=True)],
        ignore_index=True,
    )
    from ddinet.features.molgraph import smiles_to_graph
    graphs = {n: smiles_to_graph(s) for n, s in
              zip(universe.drugs["name"], universe.drugs["smiles"])}
    return V2Trainer(spec, universe, split, bundle, graphs,
                     mode=EvaluationMode.VALIDATION_ONLY, dataset=small)


# 11 -- run identity and resume -------------------------------------------
def test_run_id_is_deterministic():
    assert V2RunSpec(seed=1).run_id() == V2RunSpec(seed=1).run_id()


def test_run_id_changes_with_every_identity_field():
    base = V2RunSpec()
    for field_name, value in [
        ("ablation", "M3"), ("biology_source", "shuffled"), ("aggregation", "sum"),
        ("scheme", "scaffold"), ("split_seed", 1), ("negatives", "uniform"),
        ("bio_dim", 128), ("dropout_bio", 0.3), ("dropout_pair", 0.2),
        ("lr", 3e-4), ("batch_size", 512), ("seed", 4),
        ("eval_negative_seed", 1), ("mol_dim", 128),
    ]:
        assert replace(base, **{field_name: value}).run_id() != base.run_id(), field_name


def test_run_id_ignores_evaluation_mode():
    """Whether test is scored later does not change what was trained, so a
    validation-only checkpoint must stay resumable for the final evaluation."""
    assert "evaluation_mode" not in V2RunSpec().identity()


def test_config_id_groups_seeds_of_one_configuration():
    a, b = V2RunSpec(seed=0), V2RunSpec(seed=2)
    assert a.config_id() == b.config_id()
    assert a.run_id() != b.run_id()
    assert V2RunSpec(bio_dim=128).config_id() != a.config_id()


def test_upsert_replaces_rather_than_duplicates(runner, tmp_path):
    path = tmp_path / "grid.csv"
    row = {c: None for c in runner.RESULT_COLUMNS}
    row.update({"run_id": "abc123", "val_auprc": 0.5, "status": "completed"})
    runner.upsert_row(path, row)
    row2 = dict(row, val_auprc=0.7)
    frame = runner.upsert_row(path, row2)
    assert len(frame) == 1
    assert float(frame.iloc[0]["val_auprc"]) == 0.7


def test_upsert_keeps_distinct_runs(runner, tmp_path):
    path = tmp_path / "grid.csv"
    for rid in ("a", "b", "c"):
        row = {c: None for c in runner.RESULT_COLUMNS}
        row.update({"run_id": rid, "status": "completed"})
        runner.upsert_row(path, row)
    assert len(pd.read_csv(path)) == 3


def test_checkpoint_from_another_run_is_refused(universe, split, tmp_path):
    pytest.importorskip("rdkit")
    bundle, _ = resolve_biology(V2RunSpec(), list(universe.drugs["drugbank_id"]))
    trainer = _tiny_trainer(V2RunSpec(seed=0), universe, split, bundle)
    path = tmp_path / "ckpt.pt"
    trainer.save_checkpoint(path)
    other = _tiny_trainer(V2RunSpec(seed=3), universe, split, bundle)
    with pytest.raises(ValueError, match="refusing to resume"):
        other.load_checkpoint(path)


# 12 -- the results schema -------------------------------------------------
def test_result_schema_has_no_test_columns(runner):
    offenders = [c for c in runner.RESULT_COLUMNS if c.startswith("test_")
                 or c.endswith("_test") or "test_auprc" in c]
    assert offenders == []


def test_result_schema_carries_the_identity_and_validation_metrics(runner):
    required = {"run_id", "config_id", "seed", "split", "model", "biology_source",
                "bio_dim", "dropout_bio", "dropout_pair", "lr", "batch_size",
                "best_epoch", "val_auprc", "val_auroc", "val_brier", "val_ece",
                "runtime_s", "status"}
    assert required <= set(runner.RESULT_COLUMNS)


# 13 -- the grid -----------------------------------------------------------
def test_grid_enumerates_exactly_the_preregistered_configurations(grid):
    spec_of = grid.load_grid()
    configs = grid.enumerate_configurations(spec_of)
    assert len(configs) == 32 == spec_of["declared_n_configurations"]
    assert spec_of["selection_seeds"] == [0, 1, 2]
    assert len(grid.build_specs(spec_of)) == 96


def test_grid_run_ids_are_unique(grid):
    specs = grid.build_specs(grid.load_grid())
    assert len({s.run_id() for s in specs}) == len(specs) == 96


def test_grid_axes_all_map_to_run_spec_fields(grid):
    spec_of = grid.load_grid()
    assert set(spec_of["grid"]) <= set(grid.AXIS_TO_FIELD)
    for field_name in grid.AXIS_TO_FIELD.values():
        assert hasattr(V2RunSpec(), field_name)


def test_grid_reads_the_config_rather_than_hard_coding(grid, tmp_path):
    """Editing the frozen config must change the enumeration - otherwise the
    printed count is decoration rather than a check."""
    import yaml
    cfg = yaml.safe_load((ROOT / "configs" / "v2_preregistered.yaml").read_text())
    cfg["hparam_search"]["grid"]["bio_dim"] = [64]
    cfg["hparam_search"]["n_configurations"] = 16
    path = tmp_path / "smaller.yaml"
    path.write_text(yaml.safe_dump(cfg))
    assert len(grid.enumerate_configurations(grid.load_grid(path))) == 16


def test_grid_skips_completed_runs(grid, tmp_path):
    specs = grid.build_specs(grid.load_grid())
    path = tmp_path / "results.csv"
    pd.DataFrame([
        {"run_id": specs[0].run_id(), "status": "completed"},
        {"run_id": specs[1].run_id(), "status": "failed"},
    ]).to_csv(path, index=False)
    done = grid.completed_run_ids(path)
    assert specs[0].run_id() in done
    assert specs[1].run_id() not in done      # a failed run is work remaining
    remaining = [s for s in specs if s.run_id() not in done]
    assert len(remaining) == 95


# 14 -- manifest -----------------------------------------------------------
@frozen_only
def test_manifest_records_everything_a_rerun_would_need(universe, split):
    bundle, provenance = resolve_biology(V2RunSpec(),
                                         list(universe.drugs["drugbank_id"]))
    trainer = _tiny_trainer(V2RunSpec(), universe, split, bundle)
    manifest = trainer.manifest(checkpoint_hash="deadbeef",
                                extra={"biology": provenance})
    for key in ("run_id", "config_id", "git_commit", "dataset_version",
                "dataset_manifest_sha256", "split_scheme", "split_seed",
                "negative_sampling", "model_variant", "ablation",
                "hyperparameters", "seed", "n_parameters", "best_epoch",
                "best_val_auprc", "checkpoint_sha256", "timestamp_utc",
                "evaluation_mode"):
        assert key in manifest, key
    assert manifest["dataset_version"] == DATASET_VERSION
    assert manifest["evaluation_mode"] == "validation_only"
    assert manifest["test_evaluated"] is False
    json.dumps(manifest, default=str)      # must be serialisable


@pytest.mark.skipif(not CONTROL_F_EDGES.exists(), reason="CONTROL F not built")
@frozen_only
def test_manifest_records_the_control_f_hashes(universe, split):
    spec = V2RunSpec(biology_source="shuffled")
    bundle, provenance = resolve_biology(spec, list(universe.drugs["drugbank_id"]))
    trainer = _tiny_trainer(spec, universe, split, bundle)
    manifest = trainer.manifest(extra={"biology": provenance})
    bio = manifest["biology"]
    assert bio["control_f_seed"] == 20260829
    assert bio["biology_source"] == "shuffled"
    assert len(bio["control_f_manifest_sha256"]) == 64


# 15 -- interruption and resume -------------------------------------------
@frozen_only
def test_periodic_checkpoint_survives_an_interrupted_run(universe, split, tmp_path):
    """A run killed mid-training must leave something to resume from.

    Without periodic checkpointing a checkpoint appeared only when a run
    finished, so a 400-epoch job dying at epoch 300 started over. This project
    has lost three long runs to container restarts already.
    """
    pytest.importorskip("rdkit")
    bundle, _ = resolve_biology(V2RunSpec(), list(universe.drugs["drugbank_id"]))
    spec = V2RunSpec(max_epochs=2)
    trainer = _tiny_trainer(spec, universe, split, bundle)
    path = tmp_path / "run.pt"
    trainer.fit(max_epochs=1, checkpoint_path=path, checkpoint_every=1)
    assert path.exists(), "no checkpoint written during training"

    blob = torch.load(path, map_location="cpu", weights_only=False)
    assert blob["epochs_run"] == 1
    assert "current_state" in blob and "model_state" in blob


@frozen_only
def test_resume_continues_from_where_training_stopped(universe, split, tmp_path):
    pytest.importorskip("rdkit")
    bundle, _ = resolve_biology(V2RunSpec(), list(universe.drugs["drugbank_id"]))
    spec = V2RunSpec(max_epochs=3)
    first = _tiny_trainer(spec, universe, split, bundle)
    path = tmp_path / "run.pt"
    first.fit(max_epochs=1, checkpoint_path=path, checkpoint_every=1)

    second = _tiny_trainer(spec, universe, split, bundle)
    second.load_checkpoint(path)
    assert second._start_epoch == 1
    assert second.spec.run_id() == first.spec.run_id()
    assert second.history.best_val_auprc == first.history.best_val_auprc


@frozen_only
def test_resume_restores_the_training_weights_not_the_best_weights(
        universe, split, tmp_path):
    """Resuming from the best epoch would rewind the optimiser on every
    restart, so a run interrupted repeatedly during a plateau could never
    leave it."""
    pytest.importorskip("rdkit")
    bundle, _ = resolve_biology(V2RunSpec(), list(universe.drugs["drugbank_id"]))
    trainer = _tiny_trainer(V2RunSpec(max_epochs=3), universe, split, bundle)
    path = tmp_path / "run.pt"
    trainer.fit(max_epochs=1, checkpoint_path=path, checkpoint_every=1)
    # Force current != best by taking one more step without improving the best.
    trainer.history.best_val_auprc = 1.0
    trainer.fit(max_epochs=2, checkpoint_path=path, checkpoint_every=1)
    blob = torch.load(path, map_location="cpu", weights_only=False)
    key = next(iter(blob["model_state"]))
    assert not torch.equal(blob["model_state"][key], blob["current_state"][key])

    resumed = _tiny_trainer(V2RunSpec(max_epochs=3), universe, split, bundle)
    resumed.load_checkpoint(path)
    live = resumed.model.state_dict()[key].detach().cpu()
    assert torch.equal(live, blob["current_state"][key])


@frozen_only
def test_patience_counter_survives_a_resume(universe, split, tmp_path):
    """Otherwise an interrupted run gets a fresh patience budget and trains
    past where early stopping would have ended it."""
    pytest.importorskip("rdkit")
    bundle, _ = resolve_biology(V2RunSpec(), list(universe.drugs["drugbank_id"]))
    trainer = _tiny_trainer(V2RunSpec(max_epochs=4), universe, split, bundle)
    path = tmp_path / "run.pt"
    # One real epoch first, so a best checkpoint exists; only then pin the best
    # score out of reach. Setting it before any epoch means nothing ever
    # improves, which now correctly raises rather than reporting best_epoch=0.
    trainer.fit(max_epochs=1, checkpoint_path=path, checkpoint_every=1)
    assert trainer.history.epochs_since_improvement == 0
    trainer.history.best_val_auprc = 1.0        # nothing can improve on this
    trainer.fit(max_epochs=3, checkpoint_path=path, checkpoint_every=1)
    assert trainer.history.epochs_run == 3
    assert trainer.history.epochs_since_improvement == 2

    resumed = _tiny_trainer(V2RunSpec(max_epochs=4), universe, split, bundle)
    resumed.load_checkpoint(path)
    assert resumed.history.epochs_since_improvement == 2
    assert resumed._start_epoch == 3


def test_max_epochs_is_part_of_the_run_identity():
    """It sets T_max of the cosine schedule, so a different cap is a different
    learning-rate trajectory - a different run, not a longer one. Measured:
    the same seed at cap 2 gave val AUPRC 0.7172/0.7360 for epochs 1-2 and at
    cap 4 gave 0.7115/0.7376."""
    assert V2RunSpec(max_epochs=2).run_id() != V2RunSpec(max_epochs=4).run_id()
    assert "max_epochs" in V2RunSpec().IDENTITY


def test_failed_resume_reports_the_nearest_sibling(runner, tmp_path):
    """--resume finding nothing must say so, and say why. Silence is how the
    first resume demonstration in this project quietly started from scratch."""
    spec_a = V2RunSpec(max_epochs=2)
    manifest = tmp_path / f"{spec_a.run_id()}.manifest.json"
    manifest.write_text(json.dumps({"hyperparameters": spec_a.to_dict()}))
    notes = runner.describe_sibling_checkpoints(V2RunSpec(max_epochs=4), tmp_path)
    assert len(notes) == 1
    assert "max_epochs" in notes[0] and "2" in notes[0] and "4" in notes[0]


def test_sibling_search_ignores_wholly_different_configurations(runner, tmp_path):
    far = V2RunSpec(max_epochs=4, bio_dim=128, lr=3e-4, batch_size=512,
                    dropout_bio=0.3)
    (tmp_path / f"{far.run_id()}.manifest.json").write_text(
        json.dumps({"hyperparameters": far.to_dict()}))
    assert runner.describe_sibling_checkpoints(V2RunSpec(), tmp_path) == []


@frozen_only
def test_a_run_that_never_selects_a_best_epoch_fails_loudly(universe, split):
    """A single-class validation bucket makes AUPRC NaN, no epoch improves on
    -inf, and the run would otherwise report best_epoch=0 as a success. That
    exact failure happened while this runner was being written."""
    pytest.importorskip("rdkit")
    bundle, _ = resolve_biology(V2RunSpec(), list(universe.drugs["drugbank_id"]))
    dataset = build_v2_dataset(V2RunSpec(), universe, split,
                               EvaluationMode.VALIDATION_ONLY)
    positives_only = dataset[
        (dataset["label"] == 1) | dataset["bucket"].str.startswith("train")
    ]
    single_class = pd.concat(
        [g.head(120) for _, g in positives_only.groupby("bucket", sort=True)],
        ignore_index=True,
    )
    from ddinet.features.molgraph import smiles_to_graph
    graphs = {n: smiles_to_graph(s) for n, s in
              zip(universe.drugs["name"], universe.drugs["smiles"])}
    trainer = V2Trainer(V2RunSpec(max_epochs=1), universe, split, bundle, graphs,
                        mode=EvaluationMode.VALIDATION_ONLY, dataset=single_class)
    assert len(np.unique(trainer._val["labels"].numpy())) == 1
    with pytest.raises(RuntimeError, match="without ever selecting a best epoch"):
        trainer.fit(max_epochs=1)


@frozen_only
def test_the_tiny_fixture_has_both_classes_in_validation(universe, split):
    """Pins the fixture defect itself, so it cannot come back silently."""
    pytest.importorskip("rdkit")
    bundle, _ = resolve_biology(V2RunSpec(), list(universe.drugs["drugbank_id"]))
    trainer = _tiny_trainer(V2RunSpec(), universe, split, bundle)
    assert len(np.unique(trainer._val["labels"].numpy())) == 2
    assert len(np.unique(trainer._train["labels"].numpy())) == 2


@frozen_only
def test_a_second_fit_continues_rather_than_replaying_epochs(universe, split):
    """history.epochs_run tracks the loop index, so a fit() that restarted at
    epoch 0 would report fewer epochs than it actually trained."""
    pytest.importorskip("rdkit")
    bundle, _ = resolve_biology(V2RunSpec(), list(universe.drugs["drugbank_id"]))
    trainer = _tiny_trainer(V2RunSpec(max_epochs=3), universe, split, bundle)
    trainer.fit(max_epochs=1)
    assert trainer.history.epochs_run == 1 == len(trainer.history.val_auprc)
    trainer.fit(max_epochs=3)
    assert trainer.history.epochs_run == 3 == len(trainer.history.val_auprc)
