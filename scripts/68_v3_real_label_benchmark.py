#!/usr/bin/env python3
"""Score the label rules on the real-label benchmark (historical FDA labels).

Units: validation/clinical_outcomes/real_label_benchmark/{development,evaluation}_units.jsonl
(built by scripts/data/build_real_label_benchmark.py from the TAC 2017 labels).
Gold: annotations_{split}.jsonl, written by hand under ANNOTATION_RULES.md
before the rules were run on that split. Internally annotated; not an
independent or clinical validation.

The prediction for a unit is exactly what the engine does with the excerpts:
each excerpt with "no effect" wording becomes a no-effect mention (no outcome);
every other excerpt yields the outcome concepts of label_terms(excerpt, partner);
seriousness comes from the section and the excerpt's own wording.

    python scripts/68_v3_real_label_benchmark.py [development|evaluation|both]
Output: reports/v3_real_label_benchmark_{split}.json and .md
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serving.evidence.adapters.openfda import NO_EFFECT  # noqa: E402
from serving.evidence.outcomes import LEXICON_VERSION, SERIOUS_WORDS, _guarded, label_terms  # noqa: E402

B = ROOT / "validation" / "clinical_outcomes" / "real_label_benchmark"
FREEZE = B / "FREEZE.json"


def rules_fingerprint() -> str:
    """SHA-256 over every pattern and constant that decides label extraction."""
    import hashlib

    from serving.evidence.adapters import openfda as fda
    from serving.evidence import outcomes as oc
    parts = [oc.LEXICON_VERSION, *(f"{t.name}|{t.effect}|{t.pattern.pattern}|{t.pattern.flags}" for t in oc.LEXICON)]
    for name in ("NEGATION", "NEGATION_AFTER", "POPULATION", "CO_USE", "TRIAL_STATS", "CLAUSE_BREAK",
                 "PK_NOUN", "PK_UP", "PK_DOWN", "SERIOUS_WORDS"):
        parts.append(f"{name}:{getattr(oc, name).pattern}")
    for name in ("NO_EFFECT", "SENTENCE_SPLIT", "ABBREVIATION_END"):
        parts.append(f"{name}:{getattr(fda, name).pattern}")
    parts.append(f"{fda.MAX_EXCERPT}|{fda.MAX_PER_SECTION}|{fda.HEAD_CHARS}|{fda.BEFORE_HIT}|{fda.AFTER_HIT}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)]


def prop(k, n):
    return {"k": k, "n": n, "value": round(k / n, 3) if n else None, "wilson95": wilson(k, n)}


def f1(p, r):
    return round(2 * p * r / (p + r), 3) if p and r else 0.0


def predict(unit: dict) -> dict:
    concepts: dict[str, list[str]] = {}
    serious = "none"
    any_hit = False
    for x in unit["excerpts"]:
        text = x["text"]
        if NO_EFFECT.search(text):
            continue
        hits = label_terms(text, unit["partner"])
        for term, matched in hits:
            concepts.setdefault(term.name, []).append(matched)
        if hits:
            any_hit = True
            if x["section"] == "BOXED WARNING" or "BOXED WARNING" in x.get("also_in", []):
                serious = "boxed" if serious != "contraindication" else serious
            elif serious == "none" and any(_guarded(text, m.start()) is None for m in SERIOUS_WORDS.finditer(text)):
                serious = "serious_wording"
    return {"concepts": concepts, "seriousness": serious if any_hit else None}


def citation_ok(unit: dict, pred: dict) -> tuple[int, int]:
    """Every matched phrase must appear in the quoted excerpts (outcome words visible)."""
    blob = " ".join(x["text"] for x in unit["excerpts"]).lower()
    k = n = 0
    for phrases in pred["concepts"].values():
        for ph in phrases:
            n += 1
            k += all(part.strip().lower() in blob for part in ph.split("…"))
    return k, n


def score(split: str) -> dict:
    units = {u["unit"]: u for u in map(json.loads, (B / f"{split}_units.jsonl").read_text().splitlines())}
    gold = {g["unit"]: g for g in map(json.loads, (B / f"annotations_{split}.jsonl").read_text().splitlines())}
    assert set(units) == set(gold), "every unit must be annotated"
    rows = []
    for uid in sorted(units):
        g = gold[uid]
        if g["relation"] == "not_applicable":
            continue
        p = predict(units[uid])
        rows.append((uid, g, p, units[uid]))
    tp = fp = fn = 0
    per = Counter()
    unsupported = with_pred = 0
    pair_pred = pair_pred_inter = 0
    abst_n = abst_k = 0
    ser_n = ser_k = 0
    cit_k = cit_n = 0
    errors = []
    for uid, g, p, u in rows:
        gold_c, acc = set(g["outcomes"]), set(g["acceptable"])
        pred_c = set(p["concepts"])
        t, f_, n_ = gold_c & pred_c, pred_c - gold_c - acc, gold_c - pred_c
        tp, fp, fn = tp + len(t), fp + len(f_), fn + len(n_)
        for c in t:
            per[(c, "tp")] += 1
        for c in f_:
            per[(c, "fp")] += 1
        for c in n_:
            per[(c, "fn")] += 1
        if pred_c:
            with_pred += 1
            unsupported += bool(f_)
            pair_pred += 1
            pair_pred_inter += g["relation"] == "interaction"
            ser_n += 1
            ser_k += p["seriousness"] == g["seriousness"]
        if g["relation"] in ("no_interaction", "advice_only"):
            abst_n += 1
            abst_k += not pred_c
        k, n = citation_ok(u, p)
        cit_k, cit_n = cit_k + k, cit_n + n
        if f_ or n_ or (pred_c and p["seriousness"] != g["seriousness"]):
            errors.append({"unit": uid, "label": g["label"], "partner": g["partner"], "relation": g["relation"],
                           "gold": sorted(gold_c), "acceptable": sorted(acc), "pred": sorted(pred_c),
                           "pred_seriousness": p["seriousness"], "gold_seriousness": g["seriousness"],
                           "matched": p["concepts"]})
    concepts = sorted({c for c, _ in per})
    macro = []
    for c in concepts:
        ctp, cfp, cfn = per[(c, "tp")], per[(c, "fp")], per[(c, "fn")]
        pc = ctp / (ctp + cfp) if ctp + cfp else 0.0
        rc = ctp / (ctp + cfn) if ctp + cfn else 0.0
        macro.append((c, ctp, cfp, cfn, round(pc, 3), round(rc, 3), f1(pc, rc)))
    P = tp / (tp + fp) if tp + fp else 0.0
    R = tp / (tp + fn) if tp + fn else 0.0
    rel = Counter(g["relation"] for g in gold.values())
    return {
        "split": split, "rule": LEXICON_VERSION, "units_total": len(units), "relations": dict(rel),
        "scored_units": len(rows),
        "outcome_micro": {"tp": tp, "fp": fp, "fn": fn, "precision": prop(tp, tp + fp), "recall": prop(tp, tp + fn),
                          "f1": f1(P, R)},
        "outcome_macro_f1": round(sum(m[6] for m in macro) / len(macro), 3) if macro else None,
        "per_concept": [dict(zip(("concept", "tp", "fp", "fn", "precision", "recall", "f1"), m)) for m in macro],
        "pair_precision_interaction": prop(pair_pred_inter, pair_pred),
        "unsupported_claim_rate": prop(unsupported, with_pred),
        "abstention_on_no_or_advice_only": prop(abst_k, abst_n),
        "interaction_recall": prop(sum(1 for _, g, p, _ in rows if g["relation"] == "interaction" and p["concepts"]),
                                   sum(1 for _, g, _, _ in rows if g["relation"] == "interaction")),
        "seriousness_accuracy_on_predicted": prop(ser_k, ser_n),
        "citation_accuracy": prop(cit_k, cit_n),
        "errors": errors,
    }


def md(r: dict) -> str:
    def f(x):
        return f"{x['value']} ({x['k']}/{x['n']}; 95% CI {x['wilson95']})" if x["n"] else "n/a"
    L = [f"# Real-label benchmark — {r['split']} ({r['rule']})", "",
         "Historical FDA labels (TAC 2017), internally annotated. Not an independent or clinical validation.", "",
         f"Units: {r['units_total']} ({r['relations']}); scored (not `not_applicable`): {r['scored_units']}.", "",
         "| Measure | Value |", "|---|---|",
         f"| Outcome precision (micro) | {f(r['outcome_micro']['precision'])} |",
         f"| Outcome recall (micro) | {f(r['outcome_micro']['recall'])} |",
         f"| Outcome F1 micro / macro | {r['outcome_micro']['f1']} / {r['outcome_macro_f1']} |",
         f"| Units given an outcome that the label states as an interaction | {f(r['pair_precision_interaction'])} |",
         f"| Unsupported-claim rate (units with a concept neither gold nor acceptable) | {f(r['unsupported_claim_rate'])} |",
         f"| Interaction units with an extracted outcome (recall at pair level) | {f(r['interaction_recall'])} |",
         f"| Abstention on no-interaction / advice-only units | {f(r['abstention_on_no_or_advice_only'])} |",
         f"| Seriousness class correct (units given an outcome) | {f(r['seriousness_accuracy_on_predicted'])} |",
         f"| Citation accuracy (matched words present in the quote) | {f(r['citation_accuracy'])} |", "",
         "| Concept | TP | FP | FN | P | R | F1 |", "|---|---:|---:|---:|---:|---:|---:|",
         *[f"| {m['concept']} | {m['tp']} | {m['fp']} | {m['fn']} | {m['precision']} | {m['recall']} | {m['f1']} |" for m in r["per_concept"]],
         "", f"Errors: {len(r['errors'])} (listed in the JSON)."]
    return "\n".join(L) + "\n"


def main() -> None:
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    if which == "freeze":
        FREEZE.write_text(json.dumps({"rule": LEXICON_VERSION, "rules_sha256": rules_fingerprint(),
                                      "frozen": sys.argv[2] if len(sys.argv) > 2 else None,
                                      "note": "Frozen after development analysis, before the evaluation split was "
                                              "annotated or scored."}, indent=1) + "\n")
        print(FREEZE.read_text())
        return
    for split in (["development", "evaluation"] if which == "both" else [which]):
        if not (B / f"annotations_{split}.jsonl").exists():
            print(f"{split}: no annotations yet")
            continue
        if split == "evaluation":
            frozen = json.loads(FREEZE.read_text())
            if frozen["rules_sha256"] != rules_fingerprint():
                sys.exit("evaluation refused: the label rules changed after they were frozen "
                         f"({frozen['rule']}); re-freeze only for a new, unseen evaluation set")
        r = score(split)
        (ROOT / "reports" / f"v3_real_label_benchmark_{split}.json").write_text(json.dumps(r, indent=1) + "\n")
        (ROOT / "reports" / f"v3_real_label_benchmark_{split}.md").write_text(md(r))
        print(md(r))


if __name__ == "__main__":
    main()
