#!/usr/bin/env python3
"""Clinical Outcome Engine: pilot validation (DDI-Net 3.0, Phase 8).

What this measures, and what it cannot:

1. Label outcome extraction (label_lexicon/v2) on the project's PILOT set —
   75 constructed sentences annotated by rules fixed before scoring
   (validation/clinical_outcomes/ANNOTATION_RULES.md). Same author as the rules:
   the numbers describe the rules on known and adversarial cases, not their
   accuracy on real FDA labels. Scored twice: on the rule function alone, and
   end to end through the engine with each sentence placed in a constructed
   label served by a mocked openFDA transport.
2. Pair-level checks on the local DrugBank export (real records, no labels —
   openFDA is not reachable from the build container): status consistency,
   citation accuracy, unsupported claims, direction claims, abstention,
   RU/EN structural consistency, model independence, unavailable sources.
3. Mechanism attribution: the annotation rule that names the affected drug of
   an exposure change, checked against the two exposure-decrease record types
   whose drug order WAS verified (types 4 and 75, direction.py). The rule is
   applied here without that order, so the order is a reference the rule did
   not see. Not independent of DrugBank: both come from the same database.
4. Adversarial cases with constructed labels.

No ground truth is fabricated: the pilot gold labels are rule annotations of
constructed sentences, and every pair-level check compares the engine with the
source record it cites. No clinical validation is claimed.

Output: reports/v3_outcome_validation.{json,md}
"""

from __future__ import annotations

import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from synthetic_labels import _label

from serving.evidence.adapters.http import HttpClient
from serving.evidence.adapters.openfda import NO_EFFECT
from serving.evidence.direction import orientation_status
from serving.evidence.engine import EvidenceEngine
from serving.evidence.mechanism import findings as mech_findings
from serving.evidence.outcomes import (
    LEXICON_VERSION,
    TYPE_MAP,
    label_terms,
)
from serving.evidence.reference_sets import EFFECTS as REF_EFFECTS  # noqa: E402
from serving.evidence.schema import Bi
from serving.evidence.store import EvidenceStore

PILOT = ROOT / "validation" / "clinical_outcomes" / "pilot_label_sentences.jsonl"
#: Written after label_lexicon/v2 was frozen and scored once, without tuning.
HOLDOUT = ROOT / "validation" / "clinical_outcomes" / "holdout_label_sentences.jsonl"
#: Development round 1 (label_lexicon/v1) on PILOT, kept as measured.
DEV_V1 = ROOT / "validation" / "clinical_outcomes" / "dev_round1_label_lexicon_v1.json"
OUT_JSON = ROOT / "reports" / "v3_outcome_validation.json"
OUT_MD = ROOT / "reports" / "v3_outcome_validation.md"
SEED = 20261015
BOOT = 2000
#: DrugBank interaction types sampled for the pair-level checks: every effect
#: level (clinical outcome, PD, PK, reduced effectiveness, unspecified).
PAIR_TYPES = [66, 33, 42, 56, 31, 50, 86, 6, 20, 16, 40, 64, 57, 80, 48, 73, 47, 75, 4, 72, 70, 37, 49]
PER_TYPE = 3
N_UNDOCUMENTED = 20
N_ATTRIBUTION = 1000
CYR = re.compile(r"[А-Яа-яЁё]")
LAT_WORD = re.compile(r"\b[a-z]{4,}\b")


# ------------------------------------------------------------------- stats ----
def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)]


def prop(k: int, n: int) -> dict:
    return {"k": k, "n": n, "value": round(k / n, 3) if n else None, "wilson95": wilson(k, n)}


def cluster_boot(rows: list[tuple[int, int, int]], rng: random.Random) -> dict:
    """Sentence-level bootstrap of precision and recall (units cluster in sentences)."""
    ps, rs = [], []
    for _ in range(BOOT):
        s = [rows[rng.randrange(len(rows))] for _ in rows]
        tp, fp, fn = (sum(x[i] for x in s) for i in range(3))
        if tp + fp:
            ps.append(tp / (tp + fp))
        if tp + fn:
            rs.append(tp / (tp + fn))

    def q(v):
        v = sorted(v)
        return [round(v[int(0.025 * len(v))], 3), round(v[int(0.975 * len(v)) - 1], 3)] if v else None
    return {"precision95": q(ps), "recall95": q(rs), "resamples": BOOT}


# ------------------------------------------------------------ pilot set ----
def predict_rule(sentence: str, partner: str) -> set[str]:
    """The rule path the engine applies to one label sentence."""
    if NO_EFFECT.search(sentence):
        return set()              # becomes "no effect reported", never an outcome
    return {t.name for t, _ in label_terms(sentence, partner)}


def score(items: list[dict], pred_key: str) -> dict:
    tp = fp = fn = 0
    rows = []
    by_case: dict[str, Counter] = defaultdict(Counter)
    by_concept: dict[str, Counter] = defaultdict(Counter)
    claim_sent = bad_claim_sent = 0
    empty = abstained = 0
    for it in items:
        gold, pred = set(it["gold"]), set(it[pred_key])
        t, f, n = len(gold & pred), len(pred - gold), len(gold - pred)
        tp, fp, fn = tp + t, fp + f, fn + n
        rows.append((t, f, n))
        c = by_case[it["case"]]
        c["sentences"] += 1
        c["tp"] += t
        c["fp"] += f
        c["fn"] += n
        for g in gold | pred:
            by_concept[g]["tp"] += g in gold and g in pred
            by_concept[g]["fp"] += g in pred and g not in gold
            by_concept[g]["fn"] += g in gold and g not in pred
        if pred:
            claim_sent += 1
            bad_claim_sent += bool(pred - gold)
        if not gold:
            empty += 1
            abstained += not pred
    return {
        "units": "(sentence, concept)",
        "sentences": len(items), "tp": tp, "fp": fp, "fn": fn,
        "precision": prop(tp, tp + fp), "recall": prop(tp, tp + fn),
        "unsupported_claim_rate": {**prop(bad_claim_sent, claim_sent),
                                   "definition": "sentences with at least one extracted concept the gold does not "
                                                 "contain / sentences with any extraction"},
        "abstention_on_no_outcome_sentences": {**prop(abstained, empty),
                                               "definition": "gold-empty sentences (negated, population, "
                                                             "single-drug, mechanism-only, mixed) with nothing "
                                                             "extracted"},
        "bootstrap": cluster_boot(rows, random.Random(SEED)),
        "by_case": {k: dict(v) for k, v in sorted(by_case.items())},
        "by_concept": {k: dict(v) for k, v in sorted(by_concept.items())},
        "errors": [{"id": it["id"], "case": it["case"], "gold": sorted(it["gold"]), "pred": sorted(it[pred_key]),
                    "sentence": it["sentence"]}
                   for it in items if set(it["gold"]) != set(it[pred_key])],
    }


class LabelRoutes:
    """openFDA transport mock: one constructed label per generic-name query."""

    def __init__(self, routes: dict[str, list[dict]]):
        self.routes = routes

    def __call__(self, url, timeout):
        import urllib.parse
        decoded = urllib.parse.unquote(url)
        for key, labels in self.routes.items():
            if key in decoded:
                return 200, json.dumps({"meta": {"results": {"total": len(labels)}}, "results": labels}).encode()
        return 404, json.dumps({"error": {"code": "NOT_FOUND", "message": "No matches found!"}}).encode()


def engine_with(store, routes) -> EvidenceEngine:
    return EvidenceEngine(store, model=None, http=HttpClient(transport=LabelRoutes(routes), enabled=True))


def label_concepts(report) -> set[str]:
    out = set()
    for o in report.outcomes.outcomes:
        if o.research_only:
            continue
        for s in o.supports:
            if s.source_type == "fda_label":
                out.add(s.extraction_method.split("term=")[1])
    return out


def pilot(store, path: Path = PILOT) -> dict:
    import hashlib
    items = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    offline = EvidenceEngine(store, model=None, external=False)
    for it in items:
        it["pred_rule"] = sorted(predict_rule(it["sentence"], it["partner"]))
    e2e, skipped = [], Counter()
    for k, it in enumerate(items):
        if offline.resolve(it["partner"]).status != "resolved":
            skipped[it["partner"]] += 1
            continue
        owner = "metformin" if it["partner"] in ("fluconazole", "metformin") else "fluconazole"
        if it["partner"] == "metformin":
            owner = "fluconazole"
        lab = _label(f"00000000-0000-0000-0000-{k:012d}", owner.upper(), "20250101",
                     drug_interactions=it["sentence"])
        rep = engine_with(store, {f'generic_name:"{owner}"': [lab]}).report(owner, it["partner"])
        found = any(e.category.value.startswith("label") for e in rep.evidence)
        e2e.append({**it, "pred_e2e": sorted(label_concepts(rep)), "partner_matched": found})
    agree = sum(set(x["pred_rule"]) == set(x["pred_e2e"]) for x in e2e)
    return {
        "set": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "n_sentences": len(items),
        "case_counts": dict(Counter(it["case"] for it in items)),
        "rule_level": score(items, "pred_rule"),
        "end_to_end": {
            "n_runnable": len(e2e),
            "skipped_partner_not_resolvable_offline": dict(skipped),
            "partner_found_by_label_matcher": prop(sum(x["partner_matched"] for x in e2e), len(e2e)),
            "rule_and_engine_agree": prop(agree, len(e2e)),
            **score(e2e, "pred_e2e"),
        },
    }


# ------------------------------------------------------------- pair level ----
def bis(obj):
    """Every Bi value in a pydantic object tree."""
    if isinstance(obj, Bi):
        yield obj
    elif hasattr(type(obj), "model_fields"):
        for k in type(obj).model_fields:
            yield from bis(getattr(obj, k))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from bis(v)
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from bis(v)


def bi_problems(b: Bi) -> list[str]:
    p = []
    if not b.ru.strip() or not b.en.strip():
        p.append("empty side")
    if not CYR.search(b.ru) and LAT_WORD.search(b.ru):
        p.append("ru without Cyrillic")
    if CYR.search(b.en):
        p.append("Cyrillic in en")
    if sorted(re.findall(r"\d+", b.ru)) != sorted(re.findall(r"\d+", b.en)):
        p.append("numbers differ")
    return p


class FixedModel:
    def __init__(self, store, value):
        self.has_protein = [True] * len(store.ids)
        self.index = {d: i for i, d in enumerate(store.ids)}
        self.value = value

    def score(self, a, b):
        return SimpleNamespace(raw_model_score=self.value, calibrated_model_score=self.value)


def sample_pairs(store, rng) -> tuple[list[tuple[str, str, int | None]], dict]:
    by_type: dict[int, list] = defaultdict(list)
    for key, recs in store.records.items():
        for _, _, y in recs:
            by_type[y].append(key)
    pairs, picked = [], {}
    for y in PAIR_TYPES:
        cand = sorted(set(by_type[y]))
        rng.shuffle(cand)
        chosen = [k for k in cand if store.lexicon.entries[k[0]].inn and store.lexicon.entries[k[1]].inn][:PER_TYPE]
        picked[y] = len(chosen)
        pairs += [(store.ids[a], store.ids[b], y) for a, b in chosen]
    n = len(store.ids)
    und = 0
    while und < N_UNDOCUMENTED:
        a, b = rng.randrange(n), rng.randrange(n)
        if a != b and not store.is_documented(a, b):
            pairs.append((store.ids[a], store.ids[b], None))
            und += 1
    return pairs, picked


def check_pair(store, rep, y) -> dict:
    o = rep.outcomes
    ev = {e.id: e for e in rep.evidence}
    issues: list[str] = []
    shown = [x for x in o.outcomes if not x.research_only]
    # status rule
    db_types = {int(e.original_identifiers["tdc_interaction_type"]) for e in rep.evidence
                if e.category.value == "database_interaction_record"}
    levels = {TYPE_MAP[t].level for t in db_types}
    # Reference-set (CRESCENDDI) records name their own outcomes (meddra_effect_map/v1).
    ref_keys = {e.original_identifiers["effect_key"] for e in rep.evidence if e.category.value == "reference_set_outcome"}
    levels |= {REF_EFFECTS[k].level for k in ref_keys}
    if db_types or ref_keys:
        want = "documented_interaction" if levels & {"clinical_outcome", "pharmacodynamic_effect",
                                                      "reduced_effectiveness"} else "documented_outcome_unclear"
    else:
        want = "research_prediction_only" if o.chains else "insufficient_evidence"
    if o.interaction_status != want:
        issues.append(f"status {o.interaction_status} != {want}")
    # every documented outcome maps from a record of this pair
    expected = {(TYPE_MAP[t].category, TYPE_MAP[t].effect) for t in db_types}
    expected |= {(REF_EFFECTS[k].category, k) for k in ref_keys}
    got = {(x.category, x.effect) for x in shown}
    if got != expected:
        issues.append(f"outcomes {sorted(got)} != records {sorted(expected)}")
    cites = cites_ok = 0
    direction_claims = direction_errors = 0
    for x in o.outcomes:
        if not x.supports:
            issues.append(f"{x.id}: no support")
        for s in x.supports:
            if s.source_type == "annotation":
                if not x.research_only or x.evidence_status != "hypothesized":
                    issues.append(f"{x.id}: annotation support outside research mode")
                continue
            cites += 1
            e = ev.get(s.evidence_record_id)
            ok = e is not None and s.excerpt in (e.source_template, e.statement)
            if ok and s.source_type == "drugbank_tdc":
                yt = int(e.original_identifiers["tdc_interaction_type"])
                ok = (TYPE_MAP[yt].category, TYPE_MAP[yt].effect) == (x.category, x.effect)
            cites_ok += ok
        if x.affected_drug_id and not x.research_only:
            direction_claims += 1
            verified = {s.affected_drug_id for s in x.supports if s.affected_drug_id}
            if verified:
                for s in x.supports:
                    if s.affected_drug_id:
                        e = ev[s.evidence_record_id]
                        yt = int(e.original_identifiers["tdc_interaction_type"])
                        if orientation_status(yt, store.direction_audit) != "consistent" or \
                           s.affected_drug_id != e.original_identifiers["drugbank_id_drug2_as_exported"]:
                            direction_errors += 1
                            issues.append(f"{x.id}: affected drug from an unverified or wrong order")
            elif x.evidence_status != "mechanistically_supported":
                direction_errors += 1
                issues.append(f"{x.id}: affected drug named without a verified order or annotations")
    # RU/EN
    bi_n = bi_bad = 0
    bad_examples = []
    for b in bis(o):
        bi_n += 1
        p = bi_problems(b)
        if p:
            bi_bad += 1
            bad_examples.append({"en": b.en[:120], "problems": p})
    return {"pair": f"{rep.drug_a.id}+{rep.drug_b.id}", "type": y, "status": o.interaction_status,
            "issues": issues, "cites": cites, "cites_ok": cites_ok,
            "direction_claims": direction_claims, "direction_errors": direction_errors,
            "n_shown": len(shown), "n_hypotheses": len(o.outcomes) - len(shown),
            "bi_n": bi_n, "bi_bad": bi_bad, "bi_bad_examples": bad_examples[:3]}


def pair_level(store) -> dict:
    rng = random.Random(SEED)
    pairs, picked = sample_pairs(store, rng)
    offline = EvidenceEngine(store, model=None, external=False)
    lo, hi = EvidenceEngine(store, model=FixedModel(store, 0.01), external=False), \
        EvidenceEngine(store, model=FixedModel(store, 0.99), external=False)

    def down(url, timeout):
        raise OSError("simulated outage")
    outage = EvidenceEngine(store, model=None, http=HttpClient(transport=down, enabled=True))

    rows, model_dependent, outage_rows = [], 0, []
    for a, b, y in pairs:
        rep = offline.report(a, b)
        rows.append(check_pair(store, rep, y))
        if lo.report(a, b).outcomes.model_dump() != hi.report(a, b).outcomes.model_dump():
            model_dependent += 1
        r2 = outage.report(a, b).outcomes
        shown_off = sorted(x.id for x in rep.outcomes.outcomes if not x.research_only)
        shown_out = sorted(x.id for x in r2.outcomes if not x.research_only)
        applicable = any(c.source == "openfda_label" and c.status == "unavailable" for c in
                         outage.report(a, b).sources_checked)
        said = any("unavailable" in c.en for c in r2.coverage) or not applicable
        # no international name: labels are not searched, so nothing can be "down"
        want = ("source_unavailable" if applicable else "insufficient_evidence") if y is None \
            else rep.outcomes.interaction_status
        outage_rows.append({"pair": f"{a}+{b}", "label_source_applicable": applicable,
                            "said_unavailable": said, "status": r2.interaction_status,
                            "ok": said and shown_off == shown_out and r2.interaction_status == want})
    doc = [r for r in rows if r["type"] is not None]
    und = [r for r in rows if r["type"] is None]
    return {
        "sample": {"seed": SEED, "per_type": PER_TYPE, "types": PAIR_TYPES, "picked_per_type": picked,
                   "documented_pairs": len(doc), "undocumented_pairs": len(und)},
        "status_and_outcome_consistency": prop(sum(not r["issues"] for r in rows), len(rows)),
        "citation_accuracy": {**prop(sum(r["cites_ok"] for r in rows), sum(r["cites"] for r in rows)),
                              "definition": "support excerpts equal to the cited record's template or statement, "
                                            "and mapped to the outcome its record type names"},
        "unsupported_documented_outcomes": {"k": sum(1 for r in rows for i in r["issues"] if "no support" in i
                                                     or "outcomes" in i),
                                            "n_outcomes": sum(r["n_shown"] for r in rows)},
        "direction": {"claims": sum(r["direction_claims"] for r in rows),
                      "errors": sum(r["direction_errors"] for r in rows),
                      "definition": "an affected drug named without a verified record order or an unambiguous "
                                    "inhibitor/inducer–substrate annotation"},
        "abstention_undocumented": {**prop(sum(r["n_shown"] == 0 for r in und), len(und)),
                                    "statuses": dict(Counter(r["status"] for r in und)),
                                    "with_research_hypotheses": sum(r["n_hypotheses"] > 0 for r in und)},
        "status_distribution_documented": dict(Counter(r["status"] for r in doc)),
        "ru_en_structural": {**prop(sum(r["bi_n"] - r["bi_bad"] for r in rows), sum(r["bi_n"] for r in rows)),
                             "checks": "both sides non-empty; Cyrillic in RU, none in EN; same numerals"},
        "model_independence": {"pairs": len(pairs), "outcomes_changed_between_scores_0.01_and_0.99": model_dependent},
        "unavailable_label_source": {**prop(sum(r["ok"] for r in outage_rows), len(outage_rows)),
                                     "pairs_where_labels_are_not_searched": sum(
                                         not r["label_source_applicable"] for r in outage_rows),
                                     "definition": "outage stated in coverage, DrugBank outcomes unchanged, "
                                                   "undocumented pairs reported as source_unavailable"},
        "failures": [r for r in rows if r["issues"] or r["bi_bad"]] + [r for r in outage_rows if not r["ok"]],
    }


# -------------------------------------------------- mechanism attribution ----
def attribution(store) -> dict:
    """Annotation-named affected drug vs. the verified drug order of types 4/75."""
    rng = random.Random(SEED + 1)
    keys = sorted({k for k, recs in store.records.items() for _, _, y in recs if y in (4, 75)})
    rng.shuffle(keys)
    keys = keys[:N_ATTRIBUTION]
    n = named = right = 0
    ambiguous = none = 0
    wrong_examples = []
    for a, b in keys:
        refs = [(d1, d2) for d1, d2, y in store.pair_records(a, b) if y in (4, 75)]
        affected_true = {store.ids[d2] for _, d2 in refs}
        if len(affected_true) != 1:
            continue                       # both orders recorded: no single reference
        n += 1
        fs, _ = mech_findings(store, a, b)
        cand = {f.affected_drug_id for f in fs if f.pattern == "inducer_substrate"}
        if len(cand) == 1:
            named += 1
            if cand == affected_true:
                right += 1
            elif len(wrong_examples) < 5:
                wrong_examples.append({"pair": f"{store.ids[a]}+{store.ids[b]}",
                                       "reference_affected": next(iter(affected_true)), "rule": next(iter(cand))})
        elif cand:
            ambiguous += 1
        else:
            none += 1
    return {
        "reference": "drug order of DrugBank types 4 and 75 (exposure decrease), verified in direction.py "
                     "(consistency 0.996 and 0.970)",
        "rule": "unique affected drug of inducer–substrate annotation findings, computed without the record order",
        "pairs_sampled": len(keys), "pairs_with_single_reference": n,
        "rule_names_a_drug": prop(named, n),
        "accuracy_when_named": prop(right, named),
        "abstained_ambiguous": ambiguous, "abstained_no_annotation": none,
        "wrong_examples": wrong_examples,
        "caveat": "Same database for rule and reference; DrugBank may have written these records from the "
                  "same annotations. Agreement is consistency, not independent confirmation.",
    }


# -------------------------------------------------------------- adversarial ----
def adversarial(store) -> list[dict]:
    out = []

    def case(name, ok, detail):
        out.append({"case": name, "pass": bool(ok), "detail": detail})

    w_f = lambda routes: engine_with(store, routes).report("warfarin", "fluconazole").outcomes
    lab = _label("00000000-0000-0000-0000-00000000ad01", "FLUCONAZOLE", "20250101",
                 warnings="WARNINGS [synthetic] Hepatotoxicity has occurred in this fixture. "
                          "[synthetic] Warfarin is named here without an effect term.")
    o = w_f({'generic_name:"fluconazole"': [lab]})
    case("unrelated adverse effect in the same label", not any(x.category == "liver" for x in o.outcomes),
         "hepatotoxicity sentence without the partner is not assigned to the pair")

    lab = _label("00000000-0000-0000-0000-00000000ad02", "FLUCONAZOLE", "20250101",
                 warnings="WARNINGS [synthetic] Bleeding has been reported in this fixture.",
                 drug_interactions="7 [synthetic] Warfarin is listed in this fixture.")
    o = w_f({'generic_name:"fluconazole"': [lab]})
    case("outcome and partner in separate sections", not any(x.effect == "bleeding" for x in o.outcomes),
         "bleeding (Warnings) + warfarin (Drug Interactions) give no bleeding outcome")

    offline = EvidenceEngine(store, model=None, external=False)
    rng = random.Random(SEED + 2)
    found = None
    for _ in range(20000):
        a, b = rng.randrange(len(store.ids)), rng.randrange(len(store.ids))
        if a == b or store.is_documented(a, b):
            continue
        fs, _ = mech_findings(store, a, b)
        if any(f.pattern in ("inhibitor_substrate", "inducer_substrate") for f in fs):
            found = (store.ids[a], store.ids[b])
            break
    if found:
        o = offline.report(*found).outcomes
        ok = (o.interaction_status == "research_prediction_only"
              and all(x.research_only and x.evidence_status == "hypothesized" for x in o.outcomes)
              and o.mechanism_without_outcome_text is not None)
        case("plausible but undocumented mechanism", ok,
             f"{found[0]}+{found[1]}: {len(o.outcomes)} hypothesis(es), all research-only; status {o.interaction_status}")

    old = _label("00000000-0000-0000-0000-00000000ad03", "FLUCONAZOLE", "20190101",
                 drug_interactions="7 [synthetic] Bleeding has been reported with warfarin in this older fixture.")
    new = _label("00000000-0000-0000-0000-00000000ad04", "FLUCONAZOLE", "20250101",
                 drug_interactions="7 [synthetic] Prothrombin time increased with warfarin in this newer fixture.")
    o = w_f({'generic_name:"fluconazole"': [old, new]})
    docs = {s.source_document_id for x in o.outcomes for s in x.supports if s.source_type == "fda_label"}
    case("outdated label next to a current one", docs == {new["set_id"]} and not any(x.effect == "bleeding" and any(
        s.source_type == "fda_label" for s in x.supports) for x in o.outcomes),
         f"only the most recent label is read (documents: {sorted(docs)})")

    lab = _label("00000000-0000-0000-0000-00000000ad05", "FLUCONAZOLE", "20250101",
                 warnings_and_cautions="5.1 [synthetic] Bleeding occurred with warfarin in this fixture.",
                 drug_interactions="7 [synthetic] Serious bleeding has been reported with warfarin in this fixture.")
    o = w_f({'generic_name:"fluconazole"': [lab]})
    bleed = next((x for x in o.outcomes if x.effect == "bleeding"), None)
    case("several excerpts from one document", bleed is not None and bleed.n_source_documents == 1
         and len([s for s in bleed.supports if s.source_type == "fda_label"]) == 2,
         "two sentences of one label: two excerpts, one source document")

    lab = _label("00000000-0000-0000-0000-00000000ad06", "FLUCONAZOLE", "20250101",
                 drug_interactions="7 [synthetic] Fluconazole did not significantly alter warfarin exposure in this fixture.")
    o = w_f({'generic_name:"fluconazole"': [lab]})
    exp = next((x for x in o.outcomes if x.category == "exposure_increase" and not x.research_only), None)
    case("contradictory sources", exp is not None and any("disagree" in lim.en.lower() or "no relevant" in lim.en.lower()
                                                           for lim in exp.limitations),
         "DrugBank exposure increase kept; label no-effect sentence shown as disagreement, neither wins")

    o = offline.report("simvastatin", "clarithromycin").outcomes
    exp = [x for x in o.outcomes if x.category.startswith("exposure") and not x.research_only]
    case("ambiguous DrugBank drug order", exp and all(x.affected_drug_id is None for x in exp),
         "both drugs inhibitor and substrate: no affected drug named")

    lab = _label("00000000-0000-0000-0000-00000000ad07", "FLUCONAZOLE", "20250101",
                 drug_interactions="7 [synthetic] Coadministration with warfarin and other drugs is described in this fixture.")
    o = w_f({'generic_name:"fluconazole"': [lab]})
    case("label names both drugs without asserting an outcome",
         not any(s.source_type == "fda_label" for x in o.outcomes for s in x.supports),
         "co-mention without an outcome term yields no label outcome")
    return out


# --------------------------------------------------------------------- main ----
def _f(x):
    return f"{x['value']} ({x['k']}/{x['n']}; Wilson 95% {x['wilson95']})" if x["n"] else "n/a"


def md_extraction(title: str, block: dict, note: str) -> list[str]:
    p, e2e = block["rule_level"], block["end_to_end"]
    return [
        f"## {title}",
        "",
        note,
        "",
        "| Measure | Rule level | End to end (engine, mocked openFDA) |",
        "|---|---|---|",
        f"| Sentences | {p['sentences']} | {e2e['sentences']} (partner resolvable offline) |",
        f"| Precision | {_f(p['precision'])} | {_f(e2e['precision'])} |",
        f"| Recall | {_f(p['recall'])} | {_f(e2e['recall'])} |",
        f"| Precision, sentence bootstrap 95% | {p['bootstrap']['precision95']} | {e2e['bootstrap']['precision95']} |",
        f"| Recall, sentence bootstrap 95% | {p['bootstrap']['recall95']} | {e2e['bootstrap']['recall95']} |",
        f"| Unsupported-claim rate | {_f(p['unsupported_claim_rate'])} | {_f(e2e['unsupported_claim_rate'])} |",
        f"| Abstention on no-outcome sentences | {_f(p['abstention_on_no_outcome_sentences'])} | "
        f"{_f(e2e['abstention_on_no_outcome_sentences'])} |",
        "",
        f"End to end: rule and engine agree on {_f(e2e['rule_and_engine_agree'])} sentences; "
        f"skipped (partner not resolvable offline): {e2e['skipped_partner_not_resolvable_offline'] or 'none'}.",
        "",
        "Errors (rule level):",
        "",
        "| id | case | gold | extracted | sentence |",
        "|---|---|---|---|---|",
        *[f"| {x['id']} | {x['case']} | {', '.join(x['gold']) or '—'} | {', '.join(x['pred']) or '—'} | {x['sentence']} |"
          for x in p["errors"]],
        "",
    ]


def md(res: dict) -> str:
    pl, at = res["pair_level"], res["attribution"]
    f = _f
    v1 = res.get("dev_round1_v1")
    lines = [
        "# DDI-Net 3.0 — clinical outcome engine: pilot validation",
        "",
        f"Generated by `scripts/66_v3_outcome_validation.py` (seed {SEED}, lexicon {res['method']['lexicon']}). "
        "Sentence sets by the rules' author; not an independent or clinical validation.",
        "",
    ]
    if v1:
        r1 = v1["pilot"]["rule_level"]
        lines += [
            "## 0. Development round 1 (label_lexicon/v1, kept as measured)",
            "",
            f"Development set, rule level: precision {f(r1['precision'])}, recall {f(r1['recall'])}, "
            f"unsupported-claim rate {f(r1['unsupported_claim_rate'])}. The v1 errors led to v2 (negation after "
            "the term, partner clause, case-insensitive prothrombin time). Measuring v2 on the same set is not "
            "held out; the hold-out set (section 1b) is.",
            "",
        ]
    lines += md_extraction("1a. Label extraction, development set (v2; NOT held out)", res["pilot"],
                           "75 constructed sentences; v2 was changed after seeing v1's errors on this set.")
    lines += md_extraction("1b. Label extraction, hold-out set (v2, scored once)", res["holdout"],
                           f"40 constructed sentences written after v2 was frozen (sha256 {res['holdout']['sha256'][:16]}…); "
                           "no rule was changed after scoring.")
    lines += [
        "## 2. Pair level, local DrugBank export",
        "",
        f"Sample: {pl['sample']['documented_pairs']} documented pairs ({PER_TYPE} per type × {len(PAIR_TYPES)} types) "
        f"and {pl['sample']['undocumented_pairs']} random undocumented pairs.",
        "",
        "| Check | Result |",
        "|---|---|",
        f"| Status and outcome set match the records | {f(pl['status_and_outcome_consistency'])} |",
        f"| Citation accuracy (support excerpts) | {f(pl['citation_accuracy'])} |",
        f"| Documented outcomes without a pair record | {pl['unsupported_documented_outcomes']['k']} of "
        f"{pl['unsupported_documented_outcomes']['n_outcomes']} |",
        f"| Direction errors | {pl['direction']['errors']} of {pl['direction']['claims']} affected-drug claims |",
        f"| Abstention, undocumented pairs | {f(pl['abstention_undocumented'])}; statuses {pl['abstention_undocumented']['statuses']} |",
        f"| RU/EN structural consistency (Bi texts) | {f(pl['ru_en_structural'])} |",
        f"| Outcomes changed by model score 0.01 vs 0.99 | {pl['model_independence']['outcomes_changed_between_scores_0.01_and_0.99']} of {pl['model_independence']['pairs']} pairs |",
        f"| Label source down: stated, outcomes kept | {f(pl['unavailable_label_source'])} |",
        "",
        "## 3. Mechanism attribution",
        "",
        f"{at['rule']}; reference: {at['reference']}.",
        "",
        f"* Pairs with a single reference: {at['pairs_with_single_reference']} (of {at['pairs_sampled']} sampled)",
        f"* Rule names an affected drug: {f(at['rule_names_a_drug'])}",
        f"* Accuracy when it does: {f(at['accuracy_when_named'])}",
        f"* Abstained: {at['abstained_ambiguous']} ambiguous, {at['abstained_no_annotation']} without annotations",
        f"* {at['caveat']}",
        "",
        "## 4. Adversarial cases",
        "",
        "| Case | Pass | Detail |",
        "|---|---|---|",
        *[f"| {c['case']} | {'yes' if c['pass'] else 'NO'} | {c['detail']} |" for c in res["adversarial"]],
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    store = EvidenceStore.load()
    noref = EvidenceStore.load()
    noref.reference.clear()
    noref.sources.pop("crescenddi", None)
    res = {
        "method": {"lexicon": LEXICON_VERSION, "seed": SEED, "store_sha256": store.sha256,
                   "note": "Pilot set by the rules' author; constructed sentences; not a clinical validation."},
        "pilot": pilot(store),
        "holdout": pilot(store, HOLDOUT),
        "pair_level": pair_level(store),
        "attribution": attribution(store),
        # label-rule cases: without the reference set, so a CRESCENDDI outcome for
        # the same pair cannot mask what the label rule did
        "adversarial": adversarial(noref),
        "dev_round1_v1": json.loads(DEV_V1.read_text()) if DEV_V1.exists() else None,
    }
    OUT_JSON.write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
    OUT_MD.write_text(md(res))
    print(md(res))


if __name__ == "__main__":
    main()
