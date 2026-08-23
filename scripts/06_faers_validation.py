#!/usr/bin/env python3
"""
Validate model predictions against openFDA FAERS adverse-event reports.

    python scripts/06_faers_validation.py --top 50
    DDINET_OPENFDA_KEY=... python scripts/06_faers_validation.py --top 200

THE EXPERIMENT
--------------
Not "does FAERS agree about warfarin + fluconazole?" - it will, and that proves
nothing, because famous interactions are heavily reported precisely because they
are famous (notoriety bias).

The experiment is a RATE COMPARISON:

    Do pairs the model flags carry a FAERS disproportionality signal more often
    than control pairs it does not flag?

Both groups are drawn from the same undocumented-pair pool, so the only
systematic difference between them is the model's opinion.

The most interesting subgroup is the model's high-confidence "false positives":
pairs absent from the database that the model insists are dangerous. Under the
positive-unlabelled framing (Step 1), a raised signal there is evidence the
model is finding genuine undocumented interactions rather than making mistakes.

Every result here is CORROBORATING EVIDENCE, NOT PROOF. FAERS has no denominator
and is subject to notoriety and indication bias. See ddinet/eval/faers.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd
import torch

from ddinet.data import assemble, synthetic_fixture, split as split_mod
from ddinet.eval.faers import FAERSClient, signal_enrichment, validate_predictions
from ddinet.features.build import FeatureConfig, build_feature_bundle
from ddinet.features.molgraph import ATOM_FEATURE_DIM, BOND_FEATURE_DIM
from ddinet.models.ddinet import DDINet, DDINetConfig
from ddinet.models.train import Trainer, TrainConfig

REPORTS = Path(__file__).resolve().parents[1] / "reports"


def _fixture_warning() -> None:
    """Print the prohibition banner when running against the synthetic fixture.

    Without this the code contradicts the documentation: LIMITATIONS.md and
    reports/ANNULLED.md say metrics from the fixture are void, while the script
    would happily print a results table that looks authoritative. Anything that
    prints a metric has to say what it was computed on.
    """
    print("\n" + "!" * 78)
    print("!! SYNTHETIC FIXTURE - EVERY NUMBER BELOW IS VOID")
    print("!! Source: tests/fixtures/synthetic_ddi/ (LLM-generated, no citable source)")
    print("!! These outputs exercise code paths only. Reporting them is prohibited.")
    print("!! See LIMITATIONS.md and reports/ANNULLED.md")
    print("!" * 78 + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top", type=int, default=50, help="pairs per group to query")
    ap.add_argument("--epochs", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--offline", action="store_true",
                    help="serve from cache only; never touch the network")
    args = ap.parse_args()

    _fixture_warning()

    client = FAERSClient(offline=args.offline)
    if not args.offline:
        probe = client.count_reports('patient.drug.medicinalproduct:"warfarin"')
        if probe is None:
            print("openFDA is not reachable from this machine (network policy).")
            print("Run this script from an unrestricted network, or use --offline")
            print("once data/raw/openfda_faers/cache/ has been populated elsewhere.")
            return 1
        print(f"openFDA reachable: {probe:,} reports mention warfarin.\n")

    # ---- Train a model and score every undocumented pair -----------------
    drugs, pairs = synthetic_fixture.load_drugs(), synthetic_fixture.load_pairs()
    known = set(pairs["pair_key"])
    sp = split_mod.build_split(drugs, pairs, seed=args.seed)
    bundle = build_feature_bundle(drugs, sp, FeatureConfig())
    dataset = assemble.build_supervised_dataset(
        sp, known, assemble.AssemblyConfig(neg_ratio=3.0, seed=args.seed)
    )

    print("Training the model used for scoring...")
    model = DDINet(DDINetConfig(
        atom_dim=ATOM_FEATURE_DIM, bond_dim=BOND_FEATURE_DIM,
        node_feature_dim=bundle.node_features.shape[1],
    ))
    trainer = Trainer(model, bundle, dataset,
                      TrainConfig(epochs=args.epochs, patience=50,
                                  seed=args.seed, verbose=False))
    history = trainer.fit()
    print(f"  {history.summary()}\n")

    names = list(drugs["name"])
    idx = bundle.name_to_idx
    candidates = [
        (a, b) for i, a in enumerate(names) for b in names[i + 1:]
        if ((a, b) if a < b else (b, a)) not in known
    ]
    print(f"Scoring {len(candidates):,} undocumented pairs...")

    model.eval()
    with torch.no_grad():
        enc = trainer._encode()
        ia = torch.tensor([idx[a] for a, _ in candidates], dtype=torch.long)
        ib = torch.tensor([idx[b] for _, b in candidates], dtype=torch.long)
        scores = trainer.model.score_pairs(enc, ia, ib).interaction_prob().cpu().numpy()

    scored = pd.DataFrame({
        "drug_a": [a for a, _ in candidates],
        "drug_b": [b for _, b in candidates],
        "score": scores,
    }).sort_values("score", ascending=False).reset_index(drop=True)

    flagged = scored.head(args.top).copy()
    control = scored.tail(args.top).copy()

    print(f"\nTop {min(10, args.top)} undocumented pairs by predicted risk:")
    for r in flagged.head(10).itertuples():
        print(f"  {r.score:.3f}  {r.drug_a} + {r.drug_b}")

    # ---- Query FAERS -----------------------------------------------------
    print(f"\nQuerying openFDA for {args.top} flagged and {args.top} control pairs")
    print("(4 requests per pair; cached, so re-runs are free)...")
    flagged_results = validate_predictions(flagged, client)
    control_results = validate_predictions(control, client)
    print("  " + client.stats())

    enrichment = signal_enrichment(flagged_results, control_results)

    print("\n" + "=" * 78)
    print("FAERS SIGNAL ENRICHMENT")
    print("=" * 78)
    print(f"  model-flagged : {enrichment['flagged_signals']}/{enrichment['flagged_n']} "
          f"= {enrichment['flagged_rate']:.3f}")
    print(f"  control       : {enrichment['control_signals']}/{enrichment['control_n']} "
          f"= {enrichment['control_rate']:.3f}")
    print(f"  rate ratio    : {enrichment['rate_ratio']:.2f}")
    print(f"\n  {enrichment['interpretation']}")

    REPORTS.mkdir(parents=True, exist_ok=True)
    flagged_results.to_csv(REPORTS / "faers_flagged.csv", index=False)
    control_results.to_csv(REPORTS / "faers_control.csv", index=False)
    (REPORTS / "faers_enrichment.json").write_text(
        json.dumps(enrichment, indent=2, default=float))
    scored.head(200).to_csv(REPORTS / "top_undocumented_predictions.csv", index=False)
    print(f"\nWrote FAERS results and top predictions to {REPORTS}/")
    _fixture_warning()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
