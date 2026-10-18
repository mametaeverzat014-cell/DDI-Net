"""label_lexicon/v4 and the real-label benchmark.

The v4 rule changes were made on the DEVELOPMENT split of the real-label
benchmark (TAC 2017 train labels) and then frozen; these tests pin each change
with a sentence shaped like the development text that motivated it. The
evaluation split is checked only for integrity (annotated before scoring,
rules unchanged since the freeze), never for a particular score.

Sentences below are SYNTHETIC paraphrases written for these tests, not quotes.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path

import pytest

from serving.evidence.adapters.openfda import MAX_EXCERPT, Label, OpenFdaLabelAdapter, excerpt_of, split_sentences
from serving.evidence.outcomes import LEXICON_VERSION, NO_SPECIFIC_OUTCOME, comparator_arm, label_terms
from serving.evidence.reference_sets import EVENT_MAP, MEDDRA_MAP_VERSION, effect_of

ROOT = Path(__file__).resolve().parents[1]
B = ROOT / "validation" / "clinical_outcomes" / "real_label_benchmark"


def names(sentence, partner=None):
    return {t.name for t, _ in label_terms(sentence, partner)}


# ------------------------------------------------------------- sentences ----
def test_abbreviation_does_not_end_a_sentence():
    text = "Avoid St. John's Wort with drugx because it decreases drugx exposure. Next sentence."
    parts = split_sentences(text)
    assert parts[0].startswith("Avoid St. John's Wort") and parts[0].endswith("exposure.")
    assert len(parts) == 2


def test_long_sentence_excerpt_always_contains_the_partner():
    s = "Patients with a history of " + "condition, " * 80 + "should not receive drugx because of risk of bleeding."
    m = re.search(r"drugx", s)
    ex, truncated = excerpt_of(s, m)
    assert truncated and "drugx" in ex and len(ex) <= MAX_EXCERPT + 20


def test_find_mentions_quotes_the_partner():
    s = "Coadministration " + "of several agents " * 40 + "with drugx increased the risk of QT prolongation."
    lab = Label(set_id="SYNTH", spl_id="", version="", effective_time="", generic_names=[], brand_names=["SYNTH"],
                substance_names=[], product_type="HUMAN PRESCRIPTION DRUG",
                sections={"warnings_and_cautions": s}, retrieval_url="")
    ex = OpenFdaLabelAdapter.find_mentions(lab, ["drugx"])
    assert ex and all("drugx" in e.text.lower() for e in ex)


# ------------------------------------------------------------ v4 rules ----
def test_version():
    assert LEXICON_VERSION == "label_lexicon/v4"


def test_qt_effect_on_the_interval_phrasing():
    assert "qt_arrhythmia" in names("The effect of DRUGY on the QT interval was augmented by drugx.", "drugx")


def test_raised_transaminases_are_their_own_outcome():
    hits = label_terms("Increases in transaminases occurred when drugx was given with DRUGY.", "drugx")
    assert [(t.name, t.effect) for t, _ in hits] == [("hepatotoxicity", "liver_enzyme_increase")]


def test_condition_bullet_is_a_population_not_an_outcome():
    s = ("Use with caution in patients with risk factors * hypokalemia or hypomagnesemia * "
         "concomitant use of drugs that prolong QT such as drugx.")
    assert "hypokalemia" not in names(s, "drugx") and "hypomagnesemia" not in names(s, "drugx")


def test_comparator_arm_is_not_an_interaction():
    s = "Hypertension was reported in 40% (145/359) of patients receiving DRUGY and 29% of patients receiving drugx."
    assert comparator_arm(s, "drugx")
    assert names(s, "drugx") == set()


def test_co_use_wording_is_not_a_comparator_arm():
    s = "Concomitant use with drugx increased the incidence of hypertension (12% vs 5%)."
    assert not comparator_arm(s, "drugx")
    assert "hypertension" in names(s, "drugx")


# --------------------------------------------------------- no-outcome text ----
def test_no_specific_outcome_wording_is_exact():
    assert NO_SPECIFIC_OUTCOME.en.startswith("No specific clinical outcome established from available evidence.")
    assert NO_SPECIFIC_OUTCOME.ru.startswith("По доступным данным конкретное клиническое последствие не установлено.")
    assert "does not mean the combination is safe" in NO_SPECIFIC_OUTCOME.en
    assert "не означает, что сочетание безопасно" in NO_SPECIFIC_OUTCOME.ru


# ----------------------------------------------------------- MedDRA map v2 ----
@pytest.mark.parametrize("term,key", [
    ("Syncope", "syncope"), ("Blood creatinine increased", "creatinine_increase"),
    ("Hepatic enzyme increased", "liver_enzyme_increase"), ("Alanine aminotransferase increased", "liver_enzyme_increase"),
    ("Electrocardiogram abnormal", "ecg_change"), ("Cardiac output decreased", "haemodynamic_measure"),
    ("Hypotension", "hypotension"), ("Acute kidney injury", "kidney_injury"),
])
def test_meddra_map_v2_does_not_broaden_terms(term, key):
    assert MEDDRA_MAP_VERSION == "meddra_effect_map/v2"
    assert EVENT_MAP[term] == key and effect_of(term)[0] == key


def test_unknown_term_falls_back_without_guessing():
    assert effect_of("Some unlisted term")[0] == "other_symptom"


# -------------------------------------------------------- benchmark files ----
def _load(name):
    return [json.loads(x) for x in (B / name).read_text().splitlines()]


def test_benchmark_units_and_annotations_line_up():
    for split, n in (("development", 50), ("evaluation", 100)):
        units, gold = _load(f"{split}_units.jsonl"), _load(f"annotations_{split}.jsonl")
        assert len(units) == n and [u["unit"] for u in units] == [g["unit"] for g in gold]
        for u, g in zip(units, gold):
            assert (u["label"], u["partner"]) == (g["label"], g["partner"])
            assert g["relation"] in ("interaction", "advice_only", "no_interaction", "not_applicable")
            assert "not independently reviewed" in g["annotator"]
            assert all(u["partner"] in x["text"].lower() for x in u["excerpts"])     # citation contains the partner


def test_development_and_evaluation_labels_are_disjoint():
    dev = {u["label"].lower() for u in _load("development_units.jsonl")}
    ev = {u["label"].lower() for u in _load("evaluation_units.jsonl")}
    assert not dev & ev


def test_evaluation_annotations_were_checksummed_and_rules_are_frozen():
    freeze = json.loads((B / "FREEZE.json").read_text())
    blob = (B / "annotations_evaluation.jsonl").read_bytes()
    assert hashlib.sha256(blob).hexdigest() == freeze["evaluation_annotations_sha256"]
    spec = importlib.util.spec_from_file_location("bench", ROOT / "scripts" / "68_v3_real_label_benchmark.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.rules_fingerprint() == freeze["rules_sha256"], "label rules changed after the freeze"
