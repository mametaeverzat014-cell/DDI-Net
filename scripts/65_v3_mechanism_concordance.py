#!/usr/bin/env python3
"""Mechanism configurations on the frozen test pairs: labels, and the model.

DDI-Net 3.0, Phase 6 (exploratory, descriptive). For each of the 84,690 seed-0
pooled test pairs, does DrugBank record a pharmacokinetic role configuration —
one drug an inhibitor or inducer of an enzyme/transporter for which the other is
a substrate (serving/evidence/mechanism.py, the code the API uses)?

Two questions, with their limits stated up front:

1. Label concordance. How much more common is the configuration among
   documented pairs than among the sampled unlabelled pairs? NOT independent
   validation: DrugBank may have derived interaction records from these very
   role annotations.
2. Model concordance. BIO-GINE never sees the role (action) field — its
   protein elements are (protein, relation type, evidence type). Within each
   label class separately, is the 5-seed mean score higher when the
   configuration is present? Within-class comparison removes the trivial path
   "configuration -> label -> score". It does not remove shared confounders
   (well-studied drugs have more annotations of every kind), so a difference is
   an association, not evidence that the model "learned the mechanism".

Unlabelled pairs scored high that carry a configuration are hypotheses for
undocumented interactions only; nothing here can confirm one.

No training, no selection. Output: reports/v3_mechanism_concordance.{json,md}
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serving.evidence import build as builder  # noqa: E402
from serving.evidence.mechanism import roles_of  # noqa: E402
from serving.evidence.store import EvidenceStore  # noqa: E402

TAG = "v2-final-github-safe-2026-09-03"
SRC = "reports/v2_final/v2_final_pair_predictions.csv"
OUT_JSON = ROOT / "reports" / "v3_mechanism_concordance.json"
OUT_MD = ROOT / "reports" / "v3_mechanism_concordance.md"
RNG_SEED = 20261014
BOOT = 1000


def pk_index(store: EvidenceStore):
    """drug -> {(relation, role): set(protein)} for PK relations."""
    from collections import defaultdict
    idx: dict[int, dict] = defaultdict(lambda: defaultdict(set))
    for an in store.annotations:
        if an.relation not in ("enzyme", "transporter"):
            continue
        for r in roles_of(an):
            idx[an.drug][(an.relation, r)].add(an.protein)
    return idx


def has_config(idx, a: int, b: int) -> bool:
    for actor, affected in ((a, b), (b, a)):
        for rel in ("enzyme", "transporter"):
            sub = idx[affected].get((rel, "substrate"), set())
            if not sub:
                continue
            if idx[actor].get((rel, "inhibitor"), set()) & sub or idx[actor].get((rel, "inducer"), set()) & sub:
                return True
    return False


def boot_diff(x: np.ndarray, y: np.ndarray, rng) -> list[float]:
    d = [rng.choice(x, len(x)).mean() - rng.choice(y, len(y)).mean() for _ in range(BOOT)]
    return [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]


def main() -> None:
    store = EvidenceStore(builder.build_payload())
    idx = pk_index(store)
    blob = subprocess.run(["git", "show", f"{TAG}:{SRC}"], cwd=ROOT, capture_output=True, check=True).stdout
    df = pd.read_csv(io.BytesIO(blob))
    df = df[df["test_view"] == "pooled"]
    wide = df.pivot_table(index=["drug_a", "drug_b"], columns="seed", values="prediction", aggfunc="first")
    label = df.groupby(["drug_a", "drug_b"])["label"].first().loc[wide.index]
    t = pd.DataFrame({"score": wide.mean(axis=1), "label": label.astype(int)}).reset_index()
    t["config"] = [has_config(idx, store.index[a], store.index[b]) for a, b in zip(t["drug_a"], t["drug_b"])]

    rng = np.random.default_rng(RNG_SEED)
    pos, neg = t[t.label == 1], t[t.label == 0]
    res = {
        "source": f"{SRC} @ {TAG}; roles from data/mechanism_v1 (DrugBank v5.1 / ChEMBL MOA)",
        "n_pairs": int(len(t)),
        "label_concordance": {
            "config_rate_documented": float(pos.config.mean()),
            "config_rate_unlabelled": float(neg.config.mean()),
            "n_documented": int(len(pos)), "n_unlabelled": int(len(neg)),
            "caveat": "not independent: DrugBank interaction records may be derived from the same role annotations",
        },
        "model_concordance": {},
    }
    for name, g in (("documented", pos), ("unlabelled", neg)):
        x, y = g[g.config].score.to_numpy(), g[~g.config].score.to_numpy()
        res["model_concordance"][name] = {
            "n_with_config": int(len(x)), "n_without_config": int(len(y)),
            "mean_score_with_config": float(x.mean()), "mean_score_without_config": float(y.mean()),
            "diff": float(x.mean() - y.mean()), "diff_ci95": boot_diff(x, y, rng),
            "auroc_score_separates_config": float(roc_auc_score(g.config.astype(int), g.score)),
        }
    # Confounder probe: well-studied drugs carry more PK annotations of every
    # kind, form configurations more easily, and may score higher for that
    # reason alone. Stratify unlabelled pairs by the pair's total number of
    # enzyme/transporter annotations and compare within strata.
    n_pk = {d: sum(len(v) for v in roles.values()) for d, roles in idx.items()}
    neg = neg.assign(pk_volume=[n_pk.get(store.index[a], 0) + n_pk.get(store.index[b], 0)
                                for a, b in zip(neg["drug_a"], neg["drug_b"])])
    neg = neg.assign(stratum=pd.qcut(neg["pk_volume"].rank(method="first"), 5, labels=False))
    strata = []
    for k, g in neg.groupby("stratum"):
        row = {"stratum": int(k), "pk_volume_range": [int(g.pk_volume.min()), int(g.pk_volume.max())],
               "n": int(len(g)), "config_rate": float(g.config.mean())}
        if g.config.nunique() == 2:
            row["diff"] = float(g[g.config].score.mean() - g[~g.config].score.mean())
            row["auroc"] = float(roc_auc_score(g.config.astype(int), g.score))
        strata.append(row)
    res["unlabelled_by_annotation_volume"] = strata

    # How many unlabelled pairs combine a configuration with a high score —
    # hypotheses only.
    res["unlabelled_high_score_with_config"] = int(((neg.score >= 0.5) & neg.config).sum())
    res["unlabelled_high_score"] = int((neg.score >= 0.5).sum())
    OUT_JSON.write_text(json.dumps(res, indent=2) + "\n")

    lc, mc = res["label_concordance"], res["model_concordance"]
    lines = [
        "# Pharmacokinetic role configurations on the frozen test pairs (DDI-Net 3.0, exploratory)",
        "",
        "Generated by `scripts/65_v3_mechanism_concordance.py`. Configuration = one drug an",
        "inhibitor or inducer of an enzyme/transporter for which the other is a substrate",
        "(DrugBank roles; the same rule the API's mechanism hypotheses use). Score = 5-seed",
        f"mean BIO-GINE M4 raw prediction on the {res['n_pairs']:,} pooled test pairs.",
        "",
        "## 1. Labels (not independent)",
        "",
        f"Configuration present in {lc['config_rate_documented']:.1%} of documented pairs and "
        f"{lc['config_rate_unlabelled']:.1%} of sampled unlabelled pairs. DrugBank may have derived",
        "interaction records from these annotations, so this is consistency, not validation.",
        "",
        "## 2. Model, within each label class",
        "",
        "| class | with config | without | mean score with | mean score without | difference (95% CI) | AUROC |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, r in mc.items():
        lo, hi = r["diff_ci95"]
        lines.append(f"| {name} | {r['n_with_config']:,} | {r['n_without_config']:,} | {r['mean_score_with_config']:.3f} | "
                     f"{r['mean_score_without_config']:.3f} | {r['diff']:+.3f} ({lo:+.3f}, {hi:+.3f}) | {r['auroc_score_separates_config']:.3f} |")
    lines += [
        "",
        "## 3. Unlabelled pairs, stratified by the pair's enzyme/transporter annotation volume",
        "",
        "| stratum | annotation volume | pairs | config rate | score difference | AUROC |",
        "|---|---|---|---|---|---|",
    ]
    for r in res["unlabelled_by_annotation_volume"]:
        lo, hi = r["pk_volume_range"]
        d = f"{r['diff']:+.3f}" if "diff" in r else "—"
        a = f"{r['auroc']:.3f}" if "auroc" in r else "—"
        lines.append(f"| {r['stratum']} | {lo}–{hi} | {r['n']:,} | {r['config_rate']:.1%} | {d} | {a} |")
    lines += [
        "",
        f"Unlabelled test pairs scored ≥ 0.5 with a configuration: {res['unlabelled_high_score_with_config']:,} of "
        f"{res['unlabelled_high_score']:,} scored ≥ 0.5. These are hypotheses for undocumented interactions,",
        "not findings: no independent source was available to check them.",
        "",
        "Reading. Among documented pairs the score barely differs with a configuration. Among",
        "unlabelled pairs it differs markedly, and section 3 shows whether that survives holding",
        "annotation volume roughly fixed. Two readings remain open and this design cannot separate",
        "them: unlabelled pairs with a configuration are more often undocumented true interactions",
        "(negatives here are unlabelled, not confirmed), or residual confounding by how well studied",
        "the drugs are. BIO-GINE never sees drug roles, but it does see the proteins, so neither",
        "reading shows that the model represents the mechanism.",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
