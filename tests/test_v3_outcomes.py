"""Clinical Outcome Engine: no outcome without a source statement for the pair.

Label text here is synthetic (tests/synthetic_labels.py and the constructed
labels below, every sentence marked "[synthetic]"); DrugBank records,
annotations and mechanism findings are the real local artifact.
"""

from __future__ import annotations

import json
import re

import pytest
from synthetic_labels import FakeLabelTransport, _label
from test_v3_evidence import real, real_artifact, real_noref  # noqa: F401  (session fixtures)

from serving.evidence.adapters.http import HttpClient
from serving.evidence.engine import EvidenceEngine
from serving.evidence.explain import _FORBIDDEN
from serving.evidence.outcomes import CATEGORIES, LEXICON, TYPE_MAP, label_terms


# ------------------------------------------------------------------ type map --
def test_every_drugbank_type_is_mapped_and_read_off_its_template(real):  # noqa: F811
    assert set(TYPE_MAP) == set(real.ddi_types)
    for y, row in TYPE_MAP.items():
        tpl = real.ddi_types[y].lower()
        assert row.key.lower() in tpl, (y, row.key, tpl)
        assert row.category in CATEGORIES
        if row.level == "clinical_outcome":
            # only templates that name an outcome as such ("risk or severity of …", "risk of …")
            assert "risk" in tpl, (y, tpl)
        if row.level == "pharmacodynamic_effect":
            assert "activities" in tpl or "efficacy" in tpl, (y, tpl)


def test_pharmacodynamic_records_never_become_clinical_outcomes():
    # "anticoagulant activities increased" is not "bleeding"
    assert TYPE_MAP[6].level == "pharmacodynamic_effect" and TYPE_MAP[6].effect != "bleeding"
    assert TYPE_MAP[66].level == "clinical_outcome" and TYPE_MAP[66].effect == "bleeding"
    assert TYPE_MAP[49].level == "unspecified_adverse"
    assert TYPE_MAP[73].level == "pharmacokinetic_change"


# ------------------------------------------------------------------- lexicon --
@pytest.mark.parametrize("sentence,expected", [
    ("[synthetic] Concomitant use with drugx is not recommended due to increased risk of bleeding.", {"bleeding"}),
    ("[synthetic] Coadministration with drugx did not result in bleeding events.", set()),
    ("[synthetic] No cases of serotonin syndrome were reported with drugx.", set()),
    ("[synthetic] Use caution in patients with hypokalemia receiving drugx.", set()),
    ("[synthetic] Drugx increased the prothrombin time, and bleeding has been reported.", {"bleeding", "coagulation_measure"}),
    ("[synthetic] Plasma concentrations of drugx were increased.", {"exposure_increase"}),
    ("[synthetic] Plasma concentrations of drugx were increased in some and reduced in others.", set()),
    ("[synthetic] Drugx may cause QT prolongation and torsades de pointes.", {"qt_arrhythmia"}),
    ("[synthetic] Drugx is a CYP3A4 inhibitor.", set()),
    ("[synthetic] The INR should be checked when drugx is started.", {"coagulation_measure"}),
    ("[synthetic] Patients at risk for hypoglycemia receiving drugx.", set()),
    # label_lexicon/v2: negation or unknown after the term, sentence-initial prothrombin time
    ("[synthetic] Bleeding risk was not increased with drugx.", set()),
    ("[synthetic] Hypotension was not observed with drugx.", set()),
    ("[synthetic] The risk of QT prolongation with drugx is unknown.", set()),
    ("[synthetic] Bleeding time was unchanged when given with drugx.", set()),
    ("Prothrombin time increased with drugx [synthetic].", {"coagulation_measure"}),
    ("[synthetic] Bleeding has been reported with drugx; the cause was not established.", {"bleeding"}),
])
def test_label_terms(sentence, expected):
    assert {t.name for t, _ in label_terms(sentence)} == expected


@pytest.mark.parametrize("sentence", [
    # label_lexicon/v3: no-effect wording found missed on DDI Corpus development text
    "[synthetic] Drugx had no effect on the pharmacodynamics of warfarin (prothrombin time).",
    "[synthetic] Co-administration did not result in clinically significant increases in drugx exposure.",
    "[synthetic] Drugx did not significantly interfere with the effect of warfarin on prothrombin time.",
    "[synthetic] No significant differences were observed in drugx AUC.",
])
def test_v3_no_effect_wording_is_recognised(sentence):
    from serving.evidence.adapters.openfda import NO_EFFECT
    assert NO_EFFECT.search(sentence)


def test_only_the_clause_naming_the_partner_is_read():
    s = "[synthetic] Drugx is an anticoagulant; this drug alone has caused hepatitis."
    assert {t.name for t, _ in label_terms(s)} == {"hepatotoxicity"}           # without a partner: whole sentence
    assert label_terms(s, "drugx") == []
    s2 = "[synthetic] Drugy was studied; bleeding occurred with drugx."
    assert {t.name for t, _ in label_terms(s2, "drugx")} == {"bleeding"}
    assert {t.name for t, _ in label_terms(s2, "drugz")} == {"bleeding"}       # partner named elsewhere: whole sentence


def test_lexicon_categories_exist():
    assert all(t.category in CATEGORIES for t in LEXICON)


# ------------------------------------------------------------- local pairs ----
@pytest.fixture()
def offline(real_noref):  # noqa: F811
    """DrugBank alone (no reference set): the type-map semantics under test here."""
    return EvidenceEngine(real_noref, model=None, external=False)


@pytest.fixture()
def with_ref(real):  # noqa: F811
    return EvidenceEngine(real, model=None, external=False)


def test_pk_record_with_unambiguous_roles_is_mechanistically_supported(offline):
    o = offline.report("warfarin", "fluconazole").outcomes
    assert o.interaction_status == "documented_outcome_unclear"     # exposure change only, no named outcome
    exp = next(x for x in o.outcomes if x.category == "exposure_increase")
    assert exp.evidence_status == "mechanistically_supported"
    assert exp.affected_drug_id == "DB00682"                        # warfarin, from the annotations
    assert "not from the DrugBank record" in exp.direction_note.en
    assert exp.seriousness == "documented_no_standard_severity"
    assert exp.seriousness_basis.en == "Severity not established from available evidence."
    assert exp.seriousness_basis.ru == "Степень серьёзности не установлена по доступным данным."
    sup = exp.supports[0]
    assert sup.source_type == "drugbank_tdc" and sup.excerpt.startswith("The serum concentration of #Drug2")
    assert sup.extraction_method == "drugbank_type_map/v1:type=73"
    assert not any(x.category == "bleeding_coagulation" for x in o.outcomes)   # no bleeding invented
    assert o.chains and all(c.links[0].provenance == "verified_annotation" for c in o.chains)


def test_ambiguous_roles_give_no_direction(offline):
    o = offline.report("simvastatin", "clarithromycin").outcomes
    exp = next(x for x in o.outcomes if x.category == "exposure_increase")
    assert exp.evidence_status == "documented" and exp.affected_drug_id is None
    for c in o.chains:   # "one of the two drugs" does not make it THIS drug
        assert c.links[2].provenance == "plausible_unconfirmed"


def test_pharmacodynamic_record_is_shown_as_such(offline):
    o = offline.report("warfarin", "aspirin").outcomes
    assert o.interaction_status == "documented_interaction"
    pd = next(x for x in o.outcomes if x.effect == "anticoagulant_increase")
    assert pd.effect_level == "pharmacodynamic_effect" and pd.evidence_status == "documented"
    assert "not that harm occurs" in " ".join(lim.en for lim in pd.limitations)
    assert not any(x.effect == "bleeding" for x in o.outcomes)
    hyps = [x for x in o.outcomes if x.evidence_status == "hypothesized"]
    assert all(h.research_only and h.seriousness == "not_applicable" for h in hyps)


def test_no_evidence_abstains_without_reassurance(offline):
    r = offline.report("metformin", "warfarin")
    o = r.outcomes
    assert o.interaction_status == "insufficient_evidence"
    assert not [x for x in o.outcomes if not x.research_only]
    assert "does not mean the combination is safe" in o.no_outcome_text.en
    assert o.seriousness == "not_applicable"


def test_model_score_does_not_change_outcomes(real):  # noqa: F811
    class Fake:
        has_protein = [True] * 5000
        index = {i: k for k, i in enumerate(real.ids)}
        def score(self, a, b):
            from types import SimpleNamespace
            return SimpleNamespace(raw_model_score=0.99999, calibrated_model_score=0.99)
    scored = EvidenceEngine(real, model=Fake(), external=False).report("metformin", "warfarin")
    assert scored.model.available and scored.model.calibrated_model_score == 0.99
    with_model = scored.outcomes
    without = EvidenceEngine(real, model=None, external=False).report("metformin", "warfarin").outcomes
    assert with_model.model_dump() == without.model_dump()


# ---------------------------------------------------------- label evidence ----
def _engine(store, routes=None):
    return EvidenceEngine(store, model=None, http=HttpClient(transport=FakeLabelTransport(routes), enabled=True))


def test_label_outcomes_from_synthetic_labels(real_noref):  # noqa: F811
    o = _engine(real_noref).report("warfarin", "fluconazole").outcomes
    bleed = next(x for x in o.outcomes if x.effect == "bleeding")
    assert bleed.evidence_status == "documented" and bleed.evidence_strength == "official_label_statement"
    assert all(s.source_type == "fda_label" and "warfarin" in s.excerpt for s in bleed.supports)
    assert bleed.n_source_documents == 1                      # one label, however many sentences
    coag = next(x for x in o.outcomes if x.effect == "coagulation_measure_change")
    assert coag.effect_level == "pharmacodynamic_effect"
    assert o.interaction_status == "documented_interaction"
    # every quoted excerpt is verbatim the evidence record's statement
    by_id = {e.id: e for e in _engine(real_noref).report("warfarin", "fluconazole").evidence}
    for x in o.outcomes:
        for s in x.supports:
            if s.source_type == "fda_label":
                assert s.excerpt == by_id[s.evidence_record_id].statement


def test_contraindication_and_serious_wording_are_source_stated(real_noref):  # noqa: F811
    lab = _label("00000000-0000-0000-0000-0000000000c1", "FLUCONAZOLE", "20250101",
                 contraindications="CONTRAINDICATIONS [synthetic] Coadministration with warfarin is contraindicated because of fatal bleeding in this fixture.")
    lab2 = _label("00000000-0000-0000-0000-0000000000c2", "WARFARIN SODIUM", "20250101",
                  warnings_and_cautions="5.1 [synthetic] Life-threatening hemorrhage occurred with fluconazole in this fixture.")
    o = _engine(real_noref, {'generic_name:"fluconazole"': lab, 'generic_name:"warfarin"': lab2}).report("warfarin", "fluconazole").outcomes
    bleed = next(x for x in o.outcomes if x.effect == "bleeding")
    assert bleed.seriousness == "documented_contraindication"
    assert "CONTRAINDICATIONS" in bleed.seriousness_basis.en
    assert o.seriousness == "documented_contraindication"
    # a section alone that is not Contraindications/Boxed never grades severity
    lab3 = _label("00000000-0000-0000-0000-0000000000c3", "FLUCONAZOLE", "20250101",
                  drug_interactions="7 [synthetic] Bleeding was reported with warfarin in this fixture.")
    o3 = _engine(real_noref, {'generic_name:"fluconazole"': lab3}).report("warfarin", "fluconazole").outcomes
    b3 = next(x for x in o3.outcomes if x.effect == "bleeding")
    assert b3.seriousness == "documented_no_standard_severity"


def test_unrelated_adverse_effect_in_same_label_is_not_assigned(real_noref):  # noqa: F811
    lab = _label("00000000-0000-0000-0000-0000000000d1", "FLUCONAZOLE", "20250101",
                 warnings="WARNINGS [synthetic] Hepatotoxicity has occurred in this fixture. "
                          "[synthetic] Warfarin is mentioned here without any effect term.")
    o = _engine(real_noref, {'generic_name:"fluconazole"': lab}).report("warfarin", "fluconazole").outcomes
    assert not any(x.category == "liver" for x in o.outcomes)


def test_two_drugs_in_separate_sentences_give_no_outcome(real_noref):  # noqa: F811
    lab = _label("00000000-0000-0000-0000-0000000000e1", "FLUCONAZOLE", "20250101",
                 drug_interactions="7 [synthetic] QT prolongation has been reported. [synthetic] Warfarin is listed in this fixture.")
    o = _engine(real_noref, {'generic_name:"fluconazole"': lab}).report("warfarin", "fluconazole").outcomes
    assert not any(x.category == "cardiac_rhythm" for x in o.outcomes)


def test_no_effect_sentence_gives_no_outcome(real_noref):  # noqa: F811
    lab = _label("00000000-0000-0000-0000-0000000000f9", "METFORMIN", "20250101",
                 drug_interactions="7 [synthetic] Warfarin did not significantly alter bleeding time in this fixture.")
    o = _engine(real_noref, {'generic_name:"metformin"': lab}).report("metformin", "warfarin").outcomes
    assert o.interaction_status in ("insufficient_evidence", "source_unavailable")
    assert not [x for x in o.outcomes if not x.research_only]


def test_unavailable_source_is_said(real):  # noqa: F811
    def down(url, timeout):
        raise OSError("simulated outage")
    eng = EvidenceEngine(real, model=None, http=HttpClient(transport=down, enabled=True))
    o = eng.report("metformin", "warfarin").outcomes
    assert o.interaction_status == "source_unavailable"
    assert any("unavailable" in c.en for c in o.coverage)


# ------------------------------------------------------------------- multi ----
def test_multi_reports_categories_per_pair_and_no_global_score(offline):
    m = offline.multi(["warfarin", "aspirin", "fluconazole", "metformin"])
    dump = json.dumps(m.model_dump())
    assert "overall" not in dump.lower() and "global" not in dump.lower()
    wa = next(p for p in m.pairs if {p.drug_a, p.drug_b} == {"DB00682", "DB00945"})
    assert "bleeding_coagulation" in wa.outcome_categories and wa.interaction_status == "documented_interaction"
    for cat, pairs in m.shared_outcome_categories.items():
        assert len(pairs) >= 2 and cat in m.outcome_categories


# -------------------------------------------------------------------- text ----
def test_texts_bilingual_and_free_of_advice(offline):
    for a, b in [("warfarin", "fluconazole"), ("warfarin", "aspirin"), ("metformin", "warfarin"), ("citalopram", "tramadol")]:
        o = offline.report(a, b).outcomes
        blob = o.model_dump()
        def walk(v):
            if isinstance(v, dict):
                if set(v) == {"ru", "en"}:
                    assert v["ru"].strip() and v["en"].strip()
                    assert re.search(r"[А-Яа-яЁё]", v["ru"]), v
                    for pat in _FORBIDDEN:
                        assert not pat.search(v["ru"]) and not pat.search(v["en"])
                for x in v.values():
                    walk(x)
            elif isinstance(v, list):
                for x in v:
                    walk(x)
        walk(blob)
        assert "safe to" not in json.dumps(blob).lower()


def test_contradicting_sources_are_both_kept(real_noref):  # noqa: F811
    lab = _label("00000000-0000-0000-0000-0000000000a9", "FLUCONAZOLE", "20250101",
                 drug_interactions="7 [synthetic] Fluconazole did not significantly alter warfarin exposure in this fixture.")
    o = _engine(real_noref, {'generic_name:"fluconazole"': lab}).report("warfarin", "fluconazole").outcomes
    exp = next(x for x in o.outcomes if x.category == "exposure_increase")    # DrugBank type 73 stays
    assert any("sources disagree" in lim.en for lim in exp.limitations)
