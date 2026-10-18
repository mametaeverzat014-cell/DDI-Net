#!/usr/bin/env python3
"""Clinical Outcome Engine against independent reference data (DDI-Net 3.0).

Three measurements, each against data the engine's rules were not written from:

A. LABEL RULE ON REAL, INDEPENDENTLY ANNOTATED TEXT — DDI Corpus 2013
   (CC BY-NC 4.0; evaluation only, fetched at a pinned commit, not committed).
   In its DrugBank part every document is about one drug, as a label is. For
   each annotated pair whose one side is that drug, the engine's label rule
   (outcome term in the clause naming the partner, no "no effect" wording) is
   asked whether it would assign a documented outcome to the pair. Gold: the
   corpus' ddi=true/false annotation by its authors. Development = the official
   Train split, evaluation = the official Test split; no rule was changed after
   looking at Test.

B. DRUGBANK-DERIVED OUTCOMES vs. CRESCENDDI — positive controls (pair + adverse
   event documented in BNF, Micromedex and ANSM) and negative controls (pair +
   event judged unrelated). The engine is run with DrugBank only. Pairs are split
   by a hash of the pair key into development and evaluation halves; both are
   reported, the evaluation half is the estimate.

C. COVERAGE — how many pairs of the 1,705-drug universe have a documented,
   named clinical outcome before and after the reference set is added.

CRESCENDDI is RESTRICTED LOCAL DATA (docs/DATASET_AUDIT.md): parts B and C
run only where the index has been rebuilt locally (data/restricted/, git-ignored),
and the report carries aggregate counts only, never records or example pairs.
The public evidence artifact does not contain CRESCENDDI; C reports what adding
it would change, for research.

Not measured: whether CRESCENDDI itself is clinically correct (that would need
the compendia), and any label behaviour on real FDA labels (openFDA is not
reachable from the build container).

Output: reports/v3_reference_validation.{json,md}
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from ddinet.data import crescenddi as cr
from ddinet.data import ddi_corpus as dc
from ddinet.data.git_fetch import fetch
from serving.evidence.adapters.openfda import NO_EFFECT
from serving.evidence.engine import EvidenceEngine
from serving.evidence.outcomes import (
    LEXICON_VERSION,
    TYPE_MAP,
    label_terms,
)
from serving.evidence.reference_sets import (
    EFFECTS,
    MEDDRA_MAP_VERSION,
    effect_of,
)
from serving.evidence.store import EvidenceStore

OUT_JSON = ROOT / "reports" / "v3_reference_validation.json"
OUT_MD = ROOT / "reports" / "v3_reference_validation.md"
from serving.evidence.build import CRESCENDDI_INDEX as INDEX  # noqa: E402  (local, git-ignored)
C = "clinical_outcome"


def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)]


def prop(k: int, n: int) -> dict:
    return {"k": k, "n": n, "value": round(k / n, 3) if n else None, "wilson95": wilson(k, n)}


def split_of(a: str, b: str) -> str:
    """Deterministic 50/50 pair split (independent of drug order)."""
    h = hashlib.sha256("|".join(sorted((a, b))).encode()).digest()[0]
    return "development" if h < 128 else "evaluation"


# ------------------------------------------------------------ A: DDI Corpus ----
def rule_assigns(sentence: str, partner: str) -> bool:
    if NO_EFFECT.search(sentence):
        return False
    return bool(label_terms(sentence, partner))


def corpus_eval() -> dict:
    zdir = fetch(dc.SPEC)
    pairs = dc.read_pairs(zdir / dc.ZIP)
    # Unit = (sentence, document drug, partner NAME): the engine works per drug
    # name, while the corpus annotates per MENTION. A sentence naming a drug twice
    # has one interacting mention pair and other, non-interacting ones; the drug
    # pair interacts if any of its mention pairs does. Partners of type "drug"
    # only: the engine matches international names, not brands or classes.
    units: dict[tuple, dict] = {}
    mention_level = Counter()
    for p in pairs:
        if p.subcorpus != "DrugBank":
            continue
        owner = dc.document_drug(p.document)
        if p.e1.lower() == owner:
            partner, ptype = p.e2, p.e2_type
        elif p.e2.lower() == owner:
            partner, ptype = p.e1, p.e1_type
        else:
            continue
        if ptype != "drug" or partner.lower() == owner:
            continue
        mention_level[(p.split, p.ddi)] += 1
        key = (p.split, p.sentence_id, partner.lower())
        u = units.setdefault(key, {"split": p.split, "sentence": p.sentence, "partner": partner, "ddi": False,
                                   "types": set(), "sid": p.sentence_id})
        if p.ddi:
            u["ddi"] = True
            u["types"].add(p.ddi_type)
    # Sensitivity: the owner may be named by brand (FACTIVE for gemifloxacin),
    # which this script cannot map; count the partner as interacting if ANY of
    # its mention pairs in the sentence is annotated as interacting.
    any_ddi = {(p.split, p.sentence_id, x.lower()) for p in pairs if p.ddi for x in (p.e1, p.e2)}
    rows, sens = [], []
    for k, u in units.items():
        t = sorted(u["types"])[0] if u["types"] else None
        hit = rule_assigns(u["sentence"], u["partner"])
        rows.append((u["split"], u["ddi"], t, hit, u["sid"]))
        sens.append((u["split"], u["ddi"] or k in any_ddi, hit))
    out = {}
    for split in ("train", "test"):
        r = [x for x in rows if x[0] == split]
        pos = [x for x in r if x[1]]
        neg = [x for x in r if not x[1]]
        pred = [x for x in r if x[3]]
        by_type = {t: prop(sum(x[3] for x in pos if x[2] == t), sum(1 for x in pos if x[2] == t))
                   for t in ("effect", "mechanism", "advise", "int")}
        out["development" if split == "train" else "evaluation"] = {
            "corpus_split": split,
            "pairs": len(r), "interacting_pairs": len(pos), "non_interacting_pairs": len(neg),
            "mention_pairs_behind_them": {"interacting": mention_level[(split, True)],
                                          "non_interacting": mention_level[(split, False)]},
            "sentences": len({x[4] for x in r}),
            "assignment_precision": {**prop(sum(x[1] for x in pred), len(pred)),
                                     "definition": "pairs the rule gives an outcome that the corpus annotates as interacting"},
            "unsupported_assignment_rate": {**prop(sum(x[3] for x in neg), len(neg)),
                                            "definition": "non-interacting pairs (co-mentioned only) the rule gives an outcome"},
            "coverage_of_interacting_pairs": {**prop(sum(x[3] for x in pos), len(pos)),
                                              "definition": "interacting pairs for which the rule finds a named outcome or exposure change"},
            "coverage_by_ddi_type": by_type,
            "sensitivity_partner_interacts_with_anything_in_sentence": {
                "precision": prop(sum(x[1] for x in sens if x[0] == split and x[2]), sum(1 for x in sens if x[0] == split and x[2])),
                "unsupported_assignment_rate": prop(sum(x[2] for x in sens if x[0] == split and not x[1]),
                                                    sum(1 for x in sens if x[0] == split and not x[1]))},
        }
    return {"dataset": "DDI Corpus 2013, DrugBank part", "citation": dc.CITATION, "license": dc.LICENSE,
            "pinned_commit": dc.SPEC.commit, "zip_sha256": dc.SPEC.files[dc.ZIP],
            "rule": LEXICON_VERSION,
            "unit": "(sentence, document drug, partner drug name); interacting if any of its annotated mention pairs is",
            **out}


# --------------------------------------------------------- B: CRESCENDDI ----
def engine_effects(eng: EvidenceEngine, a: str, b: str) -> tuple[set[str], set[str], bool]:
    """(effect keys, categories) of documented non-research outcomes; and whether any DrugBank record exists."""
    r = eng.report(a, b, include_labels=False)
    shown = [o for o in r.outcomes.outcomes if not o.research_only]
    has_db = any(e.category.value == "database_interaction_record" for e in r.evidence)
    return ({o.effect for o in shown}, {o.category for o in shown if o.effect_level == C}, has_db,
            {o.category for o in shown if o.effect_level in (C, "pharmacodynamic_effect")})


def reference_eval(noref: EvidenceStore) -> dict:
    eng = EvidenceEngine(noref, model=None, external=False)
    idx = cr.load_index(INDEX)
    by_pair: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for x in idx["records"]:
        by_pair[(x["drug_a"], x["drug_b"])].append(x)
    cache: dict[tuple[str, str], tuple] = {}
    res = {s: Counter() for s in ("development", "evaluation")}
    neg_res = {s: Counter() for s in ("development", "evaluation")}
    for (a, b), recs in sorted(by_pair.items()):
        s = split_of(a, b)
        if (a, b) not in cache:
            cache[(a, b)] = engine_effects(eng, a, b)
        effects, cats, has_db, cats_pd = cache[(a, b)]
        pos = [x for x in recs if x["set"] == "positive"]
        if pos:
            res[s]["positive_pairs"] += 1
            res[s]["positive_pairs_with_drugbank_record"] += has_db
            pos_clin = {effect_of(x["event"])[1].category for x in pos if effect_of(x["event"])[1].level == C}
            if pos_clin:
                res[s]["pairs_with_clinical_event"] += 1
                res[s]["pairs_drugbank_names_any_clinical_outcome"] += bool(cats)
                res[s]["pairs_drugbank_names_same_category"] += bool(cats & pos_clin)
                res[s]["pairs_drugbank_same_category_incl_pd"] += bool(cats_pd & pos_clin)
            for x in pos:
                key, eff = effect_of(x["event"])
                res[s]["positive_events"] += 1
                res[s]["events_same_effect_in_drugbank"] += key in effects
                if eff.level == C:
                    res[s]["clinical_events"] += 1
                    res[s]["clinical_events_same_category_in_drugbank"] += eff.category in cats
        for x in recs:
            if x["set"] != "negative":
                continue
            key, eff = effect_of(x["event"])
            neg_res[s]["negative_controls"] += 1
            neg_res[s]["negative_pair_has_drugbank_record"] += has_db
            hit = eff.level == C and eff.category in cats
            neg_res[s]["drugbank_names_outcome_in_negative_category"] += hit

    def summary(c: Counter, n: Counter, s: str) -> dict:
        return {
            "positive_pairs": c["positive_pairs"],
            "drugbank_documents_the_pair": prop(c["positive_pairs_with_drugbank_record"], c["positive_pairs"]),
            "drugbank_names_any_clinical_outcome": prop(c["pairs_drugbank_names_any_clinical_outcome"], c["pairs_with_clinical_event"]),
            "drugbank_names_same_outcome_category": prop(c["pairs_drugbank_names_same_category"], c["pairs_with_clinical_event"]),
            "drugbank_same_category_incl_pharmacodynamic": {
                **prop(c["pairs_drugbank_same_category_incl_pd"], c["pairs_with_clinical_event"]),
                "reading": "DrugBank names a named outcome OR a pharmacodynamic effect (e.g. 'anticoagulant activities "
                           "increased') in the same category as a reference adverse event"},
            "event_level_same_effect": prop(c["events_same_effect_in_drugbank"], c["positive_events"]),
            "event_level_same_category_clinical": prop(c["clinical_events_same_category_in_drugbank"], c["clinical_events"]),
            "negative_controls": n["negative_controls"],
            "negative_controls_pair_documented_in_drugbank": prop(n["negative_pair_has_drugbank_record"], n["negative_controls"]),
            "drugbank_outcome_in_negative_control_category": {
                **prop(n["drugbank_names_outcome_in_negative_category"], n["negative_controls"]),
                "reading": "the engine (DrugBank only) names a clinical outcome in the same broad category as an event "
                           "the reference judged unrelated to the pair; category-level, so an upper bound on contradictions. "
                           "Example pairs are not published (restricted data)"},
        }
    return {"dataset": "CRESCENDDI (positive and negative controls), mapped to the 1,705-drug universe",
            "index_sha256": cr.SPEC.files, "split_rule": "sha256('drugA|drugB' sorted)[0] < 128 -> development",
            "engine": "DrugBank only (reference set removed), labels off",
            "event_grouping": MEDDRA_MAP_VERSION,
            **{s: summary(res[s], neg_res[s], s) for s in ("development", "evaluation")}}


# ------------------------------------------------------------ C: coverage ----
def coverage(store: EvidenceStore) -> dict:
    db_clin: dict[tuple[int, int], set[str]] = defaultdict(set)
    for (a, b), recs in store.records.items():
        for _, _, y in recs:
            row = TYPE_MAP.get(y)
            if row and row.level == C:
                db_clin[(a, b)].add(row.category)
    ref_clin: dict[tuple[int, int], set[str]] = defaultdict(set)
    ref_any = set()
    for (a, b), rows in store.reference.items():
        ref_any.add((a, b))
        for _, term, _ in rows:
            eff = EFFECTS[effect_of(term)[0]]
            if eff.level == C:
                ref_clin[(a, b)].add(eff.category)
    documented_db = set(store.records)
    union_clin = set(db_clin) | set(ref_clin)
    new_pairs = ref_any - documented_db
    pc_before = sum(len(v) for v in db_clin.values())
    pc_after = sum(len(db_clin.get(k, set()) | ref_clin.get(k, set())) for k in union_clin)
    cats_before = Counter(c for v in db_clin.values() for c in v)
    cats_after = Counter(c for k in union_clin for c in (db_clin.get(k, set()) | ref_clin.get(k, set())))
    return {
        "universe_drugs": len(store.ids),
        "documented_pairs_drugbank": len(documented_db),
        "pairs_with_named_clinical_outcome": {"drugbank_only": len(db_clin), "with_crescenddi": len(union_clin),
                                              "added": len(union_clin) - len(db_clin)},
        "pair_category_named_clinical_outcomes": {"drugbank_only": pc_before, "with_crescenddi": pc_after},
        "crescenddi_pairs": len(ref_any),
        "crescenddi_pairs_not_in_drugbank": len(new_pairs),
        "crescenddi_pairs_in_drugbank_without_named_outcome": len({k for k in ref_clin if k in documented_db and k not in db_clin}),
        "by_category": {c: {"drugbank_only": cats_before.get(c, 0), "with_crescenddi": cats_after[c]}
                        for c in sorted(cats_after)},
    }


# ------------------------------------------------------------------- report ----
def _f(x):
    return f"{x['value']} ({x['k']}/{x['n']}; 95% CI {x['wilson95']})" if x["n"] else "n/a"


def md(res: dict) -> str:
    a, b, c = res["ddi_corpus"], res["crescenddi"], res["coverage"]
    L = ["# DDI-Net 3.0 — outcome engine against independent reference data", "",
         "Generated by `scripts/67_v3_reference_validation.py`. Not a clinical validation.", "",
         "## A. Label rule on the DDI Corpus (independent annotation, real DrugBank text)", "",
         f"Unit: {a['unit']}; rule `{a['rule']}`.", "",
         "| Measure | Development (Train) | Evaluation (Test) |", "|---|---|---|"]
    for k, lab in [("pairs", "Pairs"), ("interacting_pairs", "Interacting pairs (gold)"),
                   ("non_interacting_pairs", "Co-mentioned, not interacting (gold)")]:
        L.append(f"| {lab} | {a['development'][k]} | {a['evaluation'][k]} |")
    for k, lab in [("assignment_precision", "Precision of an assigned outcome"),
                   ("unsupported_assignment_rate", "Outcome assigned to a non-interacting pair"),
                   ("coverage_of_interacting_pairs", "Interacting pairs with an extracted outcome")]:
        L.append(f"| {lab} | {_f(a['development'][k])} | {_f(a['evaluation'][k])} |")
    sd, se = (a[s]["sensitivity_partner_interacts_with_anything_in_sentence"] for s in ("development", "evaluation"))
    L.append(f"| Sensitivity: precision if the partner interacts with anything in the sentence | {_f(sd['precision'])} | {_f(se['precision'])} |")
    L.append(f"| Sensitivity: unsupported assignment, same reading | {_f(sd['unsupported_assignment_rate'])} | {_f(se['unsupported_assignment_rate'])} |")
    for t in ("effect", "mechanism", "advise", "int"):
        L.append(f"| … of type `{t}` | {_f(a['development']['coverage_by_ddi_type'][t])} | {_f(a['evaluation']['coverage_by_ddi_type'][t])} |")
    L += ["", "## B. DrugBank-derived outcomes vs. CRESCENDDI controls", "",
          f"Engine: {b['engine']}. Split: {b['split_rule']}.", "",
          "| Measure | Development | Evaluation |", "|---|---|---|",
          f"| Positive-control pairs | {b['development']['positive_pairs']} | {b['evaluation']['positive_pairs']} |"]
    for k, lab in [("drugbank_documents_the_pair", "DrugBank has a record for the pair"),
                   ("drugbank_names_any_clinical_outcome", "DrugBank names any clinical outcome"),
                   ("drugbank_names_same_outcome_category", "… in the same category as the reference event"),
                   ("drugbank_same_category_incl_pharmacodynamic", "DrugBank outcome or pharmacodynamic effect in that category"),
                   ("event_level_same_effect", "Reference events with the same effect from DrugBank"),
                   ("negative_controls_pair_documented_in_drugbank", "Negative-control pairs documented in DrugBank"),
                   ("drugbank_outcome_in_negative_control_category", "DrugBank outcome in a negative control's category")]:
        L.append(f"| {lab} | {_f(b['development'][k])} | {_f(b['evaluation'][k])} |")
    L += ["", "## C. Coverage of the 1,705-drug universe", "",
          "| | DrugBank only | + CRESCENDDI |", "|---|---:|---:|",
          f"| Pairs with a documented named clinical outcome | {c['pairs_with_named_clinical_outcome']['drugbank_only']} | {c['pairs_with_named_clinical_outcome']['with_crescenddi']} |",
          f"| Pair × outcome-category combinations | {c['pair_category_named_clinical_outcomes']['drugbank_only']} | {c['pair_category_named_clinical_outcomes']['with_crescenddi']} |",
          "", f"CRESCENDDI pairs in the universe: {c['crescenddi_pairs']}; not in DrugBank: {c['crescenddi_pairs_not_in_drugbank']}; "
          f"in DrugBank but without a named outcome there: {c['crescenddi_pairs_in_drugbank_without_named_outcome']}.", "",
          "| Category | DrugBank only | + CRESCENDDI |", "|---|---:|---:|",
          *[f"| {k} | {v['drugbank_only']} | {v['with_crescenddi']} |" for k, v in c["by_category"].items()], ""]
    return "\n".join(L)


def with_local_reference(store: EvidenceStore) -> EvidenceStore:
    """The public store plus the local CRESCENDDI positive controls (research measurement only)."""
    idx = cr.load_index(INDEX)
    store.reference.clear()
    for x in idx["records"]:
        if x["set"] == "positive" and x["drug_a"] in store.index and x["drug_b"] in store.index:
            a, b = sorted((store.index[x["drug_a"]], store.index[x["drug_b"]]))
            store.reference[(a, b)].append((x["meddra_code"], x["event"], "+".join(x["event_sources"])))
    return store


def main() -> None:
    noref = EvidenceStore.load()
    noref.reference.clear()
    noref.sources.pop("crescenddi", None)
    res = {"method": {"store_sha256": noref.sha256, "label_rule": LEXICON_VERSION, "event_map": MEDDRA_MAP_VERSION,
                      "crescenddi": "restricted local data; not in the public artifact; aggregate counts only"},
           "ddi_corpus": corpus_eval()}
    if not INDEX.exists():
        sys.exit("CRESCENDDI index not built locally (scripts/data/ingest_crescenddi.py); parts B and C need it")
    res["crescenddi"] = reference_eval(noref)
    res["coverage"] = coverage(with_local_reference(EvidenceStore.load()))
    OUT_JSON.write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
    OUT_MD.write_text(md(res))
    print(md(res))


if __name__ == "__main__":
    main()
