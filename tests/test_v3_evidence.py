"""DDI-Net 3.0 evidence layer: resolution, records, mechanism, model context,
explanations and the rules that keep the three kinds of statement apart.

Two kinds of fixture:

* ``real`` — the artifact built from the committed repository files, in a
  temporary directory. Tests on it check measured facts about the actual data.
* ``tiny`` — a hand-made payload of five fictional drugs, for logic that needs
  a precise configuration (a conflict, an inhibitor/substrate pair). Its names
  are plainly fictional so nothing here can be mistaken for real evidence.

No test touches the network.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

import pytest

from serving.evidence import build as builder
from serving.evidence.classify import classify
from serving.evidence.direction import SYMMETRIC_TYPES, orientation_status
from serving.evidence.engine import EvidenceEngine, ResolutionFailed
from serving.evidence.explain import FORBIDDEN, ExplanationError, validate
from serving.evidence.lexicon import ALIASES, normalize
from serving.evidence.mechanism import findings, mechanism_graph
from serving.evidence.model_context import (
    COVERAGE_AUROC, FROZEN_AUPRC, MODEL_SIGNAL_THRESHOLD, model_block, regime,
)
from serving.evidence.records import (
    PK_DIRECTION, TEMPLATE_RU, database_evidence, neutral_en, neutral_ru,
)
from serving.evidence.schema import (
    Bi, EvidenceCategory, EvidenceRecord, EvidenceStatus, Explanation, Section, Statement,
)
from serving.evidence.store import EvidenceStore

ROOT = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------ fixtures --
@pytest.fixture(scope="session")
def real_artifact(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("evidence")
    builder.write(builder.add_direction_audit(builder.build_payload()), out)
    return out / builder.ARTIFACT_NAME


@pytest.fixture(scope="session")
def real(real_artifact) -> EvidenceStore:
    return EvidenceStore.load(real_artifact)


@pytest.fixture(scope="session")
def real_noref(real_artifact) -> EvidenceStore:
    """The real store without the CRESCENDDI reference set: DrugBank and label semantics alone."""
    s = EvidenceStore.load(real_artifact)
    s.reference.clear()
    s.sources.pop("crescenddi", None)
    return s


@pytest.fixture(scope="session")
def engine(real) -> EvidenceEngine:
    return EvidenceEngine(real, model=None, external=False)


def tiny_payload() -> dict:
    """Five fictional drugs. Z1 inhibits enzyme P0, which processes Z2."""
    drugs = [
        {"id": f"DB9000{i}", "inn": f"zetamab{i}", "inn_ru": f"зетамаб{i}", "inchikey": None,
         "groups": "approved", "drug_type": "small molecule",
         "split_seed0": ["train", "train", "test", "val", "test"][i], "has_protein_any": i != 4}
        for i in range(5)
    ]
    return {
        "schema_version": 1,
        "sources": {
            "tdc_drugbank": {"name": "fixture", "loader": "fixture", "retrieved": "2026-01-01",
                             "url": "https://example.invalid", "license": "fixture"},
            "drugbank_annotations": {"retrieved": "2026-01-01"},
            "chembl_moa": {"retrieved": "2026-01-01"},
        },
        "annotation_sources": ["DrugBank_v5.1", "ChEMBL_36_drug_mechanism"],
        "drugs": drugs,
        # 73/75 contradict each other about the same #Drug2.
        "ddi_types": {"47": "The metabolism of #Drug2 can be decreased when combined with #Drug1.",
                      "73": "The serum concentration of #Drug2 can be increased when it is combined with #Drug1.",
                      "75": "The serum concentration of #Drug2 can be decreased when it is combined with #Drug1.",
                      "49": "The risk or severity of adverse effects can be increased when #Drug1 is combined with #Drug2."},
        "ddi_records": [[0, 1, 47], [2, 3, 73], [2, 3, 75], [0, 2, 49]],
        "proteins": [{"uniprot": "Q00000", "gene": "CYP9Z9", "name": "fictional enzyme", "organism": "Homo sapiens"},
                     {"uniprot": "Q00001", "gene": "TGT1", "name": "fictional target", "organism": "Homo sapiens"},
                     {"uniprot": "Q00002", "gene": "ABCB1", "name": "fictional pump", "organism": "Homo sapiens"}],
        "annotations": [
            [0, 0, "enzyme", "inhibitor", 0, "unknown", "1|2", "Humans"],
            [1, 0, "enzyme", "substrate", 0, "unknown", "3", "Humans"],
            [2, 1, "target", "agonist", 0, "yes", "", "Humans"],
            [3, 1, "target", "antagonist", 0, "yes", "", "Humans"],
            [2, 2, "transporter", "substrate", 0, "unknown", "", "Humans"],
            [3, 2, "transporter", "inducer", 0, "unknown", "", "Humans"],
        ],
        "pathways": [{"id": "R-HSA-0000001", "name": "fictional pathway", "n_proteins": 3}],
        "pathway_membership": [[0, 0, "TAS"], [1, 0, "IEA"]],
        "direction_audit": {"47": {"checkable": True, "n_rows": 1, "n_informative": 100,
                                   "n_consistent": 99, "n_reversed": 1, "consistency": 0.99}},
    }


@pytest.fixture()
def tiny() -> EvidenceStore:
    return EvidenceStore(tiny_payload())


# ----------------------------------------------------------- artifact build --
def test_artifact_is_deterministic(tmp_path, real_artifact):
    builder.write(builder.add_direction_audit(builder.build_payload()), tmp_path)
    assert (tmp_path / builder.ARTIFACT_NAME).read_bytes() == real_artifact.read_bytes()


def test_artifact_counts_match_the_frozen_data(real):
    assert len(real.lexicon) == 1705
    assert sum(len(v) for v in real.records.values()) == 191_798
    assert len(real.records) == 191_392, "every documented unordered pair, no more"
    assert len(real.ddi_types) == 86
    assert sum(e.has_protein_any for e in real.lexicon.entries) == 1638
    assert {e.split_seed0 for e in real.lexicon.entries} == {"train", "val", "test"}
    assert sum(e.split_seed0 == "train" for e in real.lexicon.entries) == 1195


def test_chembl_bioactivity_never_enters_annotations(real):
    assert {a.source for a in real.annotations} <= {"DrugBank_v5.1", "ChEMBL_36_drug_mechanism"}


# ---------------------------------------------------------------- lexicon ----
@pytest.mark.parametrize("query,expected,how", [
    ("DB00682", "DB00682", "drugbank_id"),
    ("db00682", "DB00682", "drugbank_id"),
    ("warfarin", "DB00682", "inn"),
    ("  WARFARIN ", "DB00682", "inn"),
    ("варфарин", "DB00682", "inn_ru_transliteration"),
    ("warfarin sodium", "DB00682", "inn_without_salt"),
    ("aspirin", "DB00945", "curated_alias"),
    ("acetaminophen", "DB00316", "curated_alias"),
])
def test_resolution(real, query, expected, how):
    r = real.lexicon.resolve(query)
    assert r.status == "resolved" and r.drug.id == expected and r.matched_on == how


def test_near_miss_gives_suggestions_and_never_a_silent_pick(real):
    r = real.lexicon.resolve("warfarn")
    assert r.status == "suggestions" and r.drug is None
    assert "DB00682" in [e.id for e in r.suggestions]


@pytest.mark.parametrize("bad", ["", "   ", "warfarin; DROP TABLE", "<script>", "x" * 101])
def test_invalid_input_is_refused(real, bad):
    assert real.lexicon.resolve(bad).status == "invalid"


def test_unknown_drugbank_id_is_not_in_universe(real):
    r = real.lexicon.resolve("DB99999")
    assert r.status == "not_found" and "1,705" in r.note


def test_every_alias_targets_an_inn_present_in_the_data(real):
    inns = {normalize(e.inn) for e in real.lexicon.entries if e.inn}
    assert all(normalize(v) in inns for v in ALIASES.values())
    # An alias must never shadow a real INN of a different drug.
    assert not [k for k in ALIASES if normalize(k) in inns]


# ---------------------------------------------------------------- records ----
def test_every_template_has_a_russian_translation_with_the_same_slots(real):
    assert set(TEMPLATE_RU) == set(real.ddi_types)
    for y, en in real.ddi_types.items():
        assert set(re.findall(r"#Drug[12]", en)) == set(re.findall(r"#Drug[12]", TEMPLATE_RU[y])), y


def test_neutral_rendering_names_no_slot_for_any_type(real):
    for y, en in real.ddi_types.items():
        assert "#Drug" not in neutral_en(en)
        assert "#Drug" not in neutral_ru(TEMPLATE_RU[y])


def test_direction_audit_reproduces_the_measured_orientation(real):
    """The finding that motivated direction.py, pinned so it cannot regress silently."""
    a = real.direction_audit
    assert a[4]["consistency"] > 0.99 and a[4]["n_informative"] > 3000
    assert a[75]["consistency"] > 0.95
    assert a[47]["consistency"] < 0.10 and a[47]["n_informative"] > 20000
    assert a[73]["consistency"] < 0.15
    assert orientation_status(4, a) == "consistent"
    assert orientation_status(47, a) == "unverified"
    assert orientation_status(6, a) == "unverified", "PD types cannot be checked"
    assert orientation_status(49, a) == "symmetric"
    assert set(PK_DIRECTION) == set(a)


def test_unverified_records_do_not_name_who_affects_whom(real):
    a, b = real.index["DB00682"], real.index["DB00196"]          # warfarin, fluconazole
    recs, _ = database_evidence(real, a, b)
    assert recs, "warfarin + fluconazole is documented"
    for r in recs:
        if r.direction == "not_verified":
            assert r.drug1_id is None and r.drug2_id is None
            assert "one of the two drugs" in r.statement
            assert "warfarin" not in r.statement and "fluconazole" not in r.statement
            assert r.statement_origin == "source_template_direction_neutral"
        assert r.source_severity is None
        assert r.category == EvidenceCategory.DATABASE_INTERACTION_RECORD


def test_opposing_records_become_a_conflict_not_a_consensus(tiny):
    recs, conflicts = database_evidence(tiny, 2, 3)
    assert len(recs) == 2 and len(conflicts) == 1
    assert set(conflicts[0].record_ids) == {r.id for r in recs}
    model = model_block(score=None, split_a="test", split_b="val", documented=True,
                        has_protein_a=True, has_protein_b=True)
    assert classify(recs, conflicts, model) == EvidenceStatus.CONFLICTING_EVIDENCE


def test_symmetric_record_keeps_names(tiny):
    recs, _ = database_evidence(tiny, 0, 2)
    assert recs[0].direction == "symmetric" and "zetamab0" in recs[0].statement


# -------------------------------------------------------------- mechanism ----
def test_inhibitor_substrate_is_found_with_direction(tiny):
    found, refs = findings(tiny, 0, 1)
    f = found[0]
    assert f.pattern == "inhibitor_substrate"
    assert (f.actor_drug_id, f.affected_drug_id) == ("DB90000", "DB90001")
    assert f.status == "hypothesis"
    assert all(i in refs for i in f.annotation_ids)
    # type 47 is 'consistent' in this fixture and the export order matches.
    assert f.consistent_with_records == ["drugbank-tdc:DB90000>DB90001:t47"]
    assert refs[f.annotation_ids[0]].pmids


def test_target_and_transporter_patterns(tiny):
    found, _ = findings(tiny, 2, 3)
    patterns = {f.pattern for f in found}
    assert "opposing_target_action" in patterns
    assert "inducer_substrate" in patterns
    assert any(f.protein.family == "p_glycoprotein" for f in found)


def test_real_pair_mechanism_and_graph(real):
    a, b = real.index["DB00682"], real.index["DB00196"]
    found, _ = findings(real, a, b)
    pk = [f for f in found if f.pattern == "inhibitor_substrate"]
    assert any(f.protein.gene == "CYP2C9" and f.actor_drug_id == "DB00196" and f.affected_drug_id == "DB00682"
               for f in pk), "fluconazole inhibits CYP2C9, which processes warfarin (DrugBank roles)"
    g = mechanism_graph(real, a, b)
    ids = {n.id for n in g.nodes}
    assert all(e.source in ids and e.target in ids for e in g.edges)
    assert any(e.kind == "documented_interaction" for e in g.edges)
    assert all(e.established for e in g.edges), "the graph holds no model-derived edge"


# -------------------------------------------------------- model context -----
def test_regimes():
    assert regime("train", "train") == "S1"
    assert regime("train", "test") == "S2"
    assert regime("val", "train") == "S2"
    assert regime("test", "val") == "S3"


class _Score:
    raw_model_score = 0.9
    calibrated_model_score = 0.8


def test_training_label_seen_abstains():
    m = model_block(score=_Score(), split_a="train", split_b="train", documented=True,
                    has_protein_a=True, has_protein_b=True)
    assert m.training_label_seen and m.abstain and m.reliability == "training_label_seen"
    assert m.measured_performance == []
    assert classify([], [], m) == EvidenceStatus.NO_DOCUMENTED_EVIDENCE_FOUND


def test_model_signal_only_requires_held_out_and_threshold():
    m = model_block(score=_Score(), split_a="test", split_b="test", documented=False,
                    has_protein_a=True, has_protein_b=False)
    assert m.regime == "S3" and not m.abstain
    assert classify([], [], m) == EvidenceStatus.MODEL_SIGNAL_ONLY
    assert m.measured_performance[0].mean == FROZEN_AUPRC["S3"]["mean"]
    assert m.measured_performance[1].mean == COVERAGE_AUROC[("S3", "at_least_one_unannotated")][0]
    low = type("S", (), {"raw_model_score": 0.1, "calibrated_model_score": MODEL_SIGNAL_THRESHOLD - 0.01})()
    m2 = model_block(score=low, split_a="test", split_b="test", documented=False,
                     has_protein_a=True, has_protein_b=True)
    assert classify([], [], m2) == EvidenceStatus.NO_DOCUMENTED_EVIDENCE_FOUND


def test_quoted_numbers_equal_their_source_files():
    facts = json.loads((ROOT / "paper" / "FACTS.json").read_text())["models"]
    assert FROZEN_AUPRC["pooled"]["mean"] == facts["M4_pooled"]["mean"]
    assert FROZEN_AUPRC["pooled"]["sd"] == facts["M4_pooled"]["std"]
    assert FROZEN_AUPRC["S3"]["mean"] == facts["M4_s3"]["mean"]
    assert FROZEN_AUPRC["S3"]["sd"] == facts["M4_s3"]["std"]
    cov = json.loads((ROOT / "reports" / "v3_coverage_reliability.json").read_text())["views"]
    for (view, group), (mean, sd) in COVERAGE_AUROC.items():
        assert mean == cov[view][group]["auroc_mean"] and sd == cov[view][group]["auroc_sd"]


# --------------------------------------------------------- classification ----
def _rec(cat: EvidenceCategory, i: int = 0) -> EvidenceRecord:
    return EvidenceRecord(id=f"x{i}", category=cat, source_name="fixture", statement="fixture",
                          statement_origin="verbatim_excerpt", retrieved_at="2026-01-01")


def test_status_precedence():
    m = model_block(score=_Score(), split_a="test", split_b="test", documented=False,
                    has_protein_a=True, has_protein_b=True)
    C = EvidenceCategory
    assert classify([_rec(C.DATABASE_INTERACTION_RECORD), _rec(C.LABEL_CONTRAINDICATION, 1)], [], m) \
        == EvidenceStatus.CONTRAINDICATION_IN_LABEL
    assert classify([_rec(C.DATABASE_INTERACTION_RECORD), _rec(C.LABEL_BOXED_WARNING, 1)], [], m) \
        == EvidenceStatus.WARNING_IN_LABEL
    assert classify([_rec(C.DATABASE_INTERACTION_RECORD)], [], m) == EvidenceStatus.DOCUMENTED_NO_SEVERITY
    # A label sentence reporting no effect never raises the status.
    assert classify([_rec(C.LABEL_MENTION_NO_EFFECT_REPORTED)], [], m) == EvidenceStatus.MODEL_SIGNAL_ONLY


# ------------------------------------------------------------ explanation ----
def _sample_pairs(real, n: int = 150, seed: int = 7):
    rng = random.Random(seed)
    documented = rng.sample(sorted(real.records), n // 2)
    ids = range(len(real.ids))
    random_pairs = [tuple(rng.sample(ids, 2)) for _ in range(n // 2)]
    return [(real.ids[a], real.ids[b]) for a, b in documented + random_pairs]


def test_every_explanation_validates_on_real_pairs(engine, real):
    for a, b in _sample_pairs(real):
        rep = engine.report(a, b, include_labels=False)
        validate(rep.explanation, rep.evidence, rep.mechanism, rep.model)   # raises on failure
        assert [s.id for s in rep.explanation.sections] == ["known", "why", "ai", "certainty", "missing"]
        if rep.evidence_status == EvidenceStatus.NO_DOCUMENTED_EVIDENCE_FOUND:
            first = rep.explanation.sections[0].statements[0]
            assert "не означает, что сочетание безопасно" in first.text.ru
            assert "does not mean the combination is safe" in first.text.en
        last = rep.explanation.sections[-1].statements[-1].text
        assert "врач или фармацевт" in last.ru and "doctor or pharmacist" in last.en


def test_validator_rejects_unreferenced_claims_and_advice(engine):
    rep = engine.report("warfarin", "fluconazole", include_labels=False)
    bad = Explanation(sections=[Section(id="known", title=Bi(ru="x", en="x"), statements=[
        Statement(kind="documented", text=Bi(ru="утверждение", en="claim"), refs=[])])])
    with pytest.raises(ExplanationError, match="no reference"):
        validate(bad, rep.evidence, rep.mechanism, rep.model)
    phantom = Explanation(sections=[Section(id="known", title=Bi(ru="x", en="x"), statements=[
        Statement(kind="documented", text=Bi(ru="утверждение", en="claim"), refs=["label:fake"])])])
    with pytest.raises(ExplanationError, match="not in the report"):
        validate(phantom, rep.evidence, rep.mechanism, rep.model)
    for advice in ("It is safe to take both.", "Вы можете спокойно принимать оба", "Снизьте дозу варфарина",
                   "You should stop taking it."):
        ex = Explanation(sections=[Section(id="missing", title=Bi(ru="x", en="x"), statements=[
            Statement(kind="caveat", text=Bi(ru=advice, en=advice))])])
        with pytest.raises(ExplanationError, match="forbidden"):
            validate(ex, rep.evidence, rep.mechanism, rep.model)


def test_forbidden_list_does_not_block_the_required_disclaimer():
    disclaimer = "Это не означает, что сочетание безопасно. This does not mean the combination is safe."
    assert not any(re.search(p, disclaimer, re.IGNORECASE) for p in FORBIDDEN)


def test_report_without_model_says_so(engine):
    rep = engine.report("warfarin", "fluconazole", include_labels=False)
    assert not rep.model.available and rep.model.calibrated_model_score is None
    ai = next(s for s in rep.explanation.sections if s.id == "ai")
    assert ai.statements[0].kind == "missing"
    assert {c.source: c.status for c in rep.sources_checked}["openfda_label"] == "disabled"


def test_same_drug_twice_is_refused(engine):
    with pytest.raises(ValueError):
        engine.report("warfarin", "DB00682")


def test_unresolved_drug_raises_with_candidates(engine):
    with pytest.raises(ResolutionFailed) as exc:
        engine.report("warfarn", "fluconazole")
    assert exc.value.results[0].status == "suggestions"


def test_multi_drug_is_pairwise_and_bounded(engine):
    rep = engine.multi(["warfarin", "fluconazole", "simvastatin", "clarithromycin"], include_labels=False)
    assert len(rep.pairs) == 6
    assert "три и более" in rep.scope_note.ru and "three or more" in rep.scope_note.en
    with pytest.raises(ValueError):
        engine.multi(["warfarin"] * 9, include_labels=False)
    with pytest.raises(ValueError):
        engine.multi(["warfarin", "DB00682"], include_labels=False)


def test_modality_parity_constant_equals_its_report():
    from serving.evidence.model_context import MODALITY_PARITY
    rep = json.loads((ROOT / "reports" / "v3_modality_parity.json").read_text())
    assert MODALITY_PARITY["n_rows"] == rep["n_rows"]
    assert MODALITY_PARITY["max_abs_diff"] == rep["max_abs_diff_overall"]
    assert rep["max_abs_diff_overall"] < 1e-5, "readout must reproduce the frozen analysis within the served tolerance"


def test_reliance_is_withheld_when_the_label_was_seen():
    r = {"baseline": 0.9, "without_molecular": 0.8, "without_protein": 0.2, "without_pathway": 0.85}
    seen = model_block(score=_Score(), split_a="train", split_b="train", documented=True,
                       has_protein_a=True, has_protein_b=True, reliance=r)
    assert seen.modality_reliance is None
    held = model_block(score=_Score(), split_a="test", split_b="train", documented=False,
                       has_protein_a=True, has_protein_b=True, reliance=r)
    assert abs(held.modality_reliance.delta_protein - 0.7) < 1e-12
