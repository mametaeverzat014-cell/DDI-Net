"""Label excerpts: one sentence is one excerpt, one label is one source.

An older-format label repeats its "Drug Interactions" subsection as a separate
openFDA field, so the same sentence was returned under PRECAUTIONS and again
under DRUG INTERACTIONS, and the report read as if six excerpts corroborated the
interaction. These tests pin the fix: repeated text within one label is merged
(keeping every section name), distinct sentences stay distinct, different labels
are never merged, and the explanation counts documents, not records.

Also pinned here: the pooled test metric is never presented as an S2-only one.

Label text is synthetic (tests/synthetic_labels.py).
"""

from __future__ import annotations

import pytest
from synthetic_labels import FLUCONAZOLE_OLD_FORMAT, WARFARIN_PLR, FakeLabelTransport
from test_v3_evidence import real, real_artifact  # noqa: F401  (session fixtures)

from serving.evidence.adapters.http import HttpClient
from serving.evidence.adapters.openfda import OpenFdaLabelAdapter, _parse, same_finding
from serving.evidence.engine import EvidenceEngine
from serving.evidence.schema import EvidenceCategory


def test_repeated_subsection_gives_one_excerpt_per_sentence():
    label = _parse(FLUCONAZOLE_OLD_FORMAT, "https://example.invalid")
    ex = OpenFdaLabelAdapter.find_mentions(label, ["warfarin"])
    assert len(ex) == 2                                   # was 4: two sentences, each in two fields
    assert {e.section for e in ex} == {"PRECAUTIONS"}     # first (more prominent) occurrence kept
    assert all(e.also_in == ["DRUG INTERACTIONS"] for e in ex)
    assert len({e.text for e in ex}) == 2


def test_distinct_sentences_in_one_label_stay_distinct():
    label = _parse(WARFARIN_PLR, "https://example.invalid")
    ex = OpenFdaLabelAdapter.find_mentions(label, ["fluconazole"])
    assert len(ex) == 2                                   # a table row and a separate sentence
    assert {e.section for e in ex} == {"WARNINGS AND PRECAUTIONS", "DRUG INTERACTIONS"}
    assert all(e.also_in == [] for e in ex)


@pytest.mark.parametrize("a,b,same", [
    ("Prothrombin time may be increased with fluconazole and warfarin.",
     "Prothrombin time may be increased with fluconazole and warfarin.", True),
    ("Prothrombin time may be increased with fluconazole and warfarin.",
     "7 DRUG INTERACTIONS Prothrombin time may be increased with fluconazole and warfarin.", True),   # heading glued on
    ("Prothrombin time may be increased with fluconazole and warfarin.",
     "prothrombin  time may be increased, with fluconazole and warfarin", True),                      # spacing, punctuation
    ("Prothrombin time may be increased with fluconazole and warfarin.",
     "Bleeding events have been reported with fluconazole and warfarin.", False),                     # same drugs, other finding
    ("Fluconazole increased warfarin exposure.", "Fluconazole decreased warfarin exposure.", False),  # short, opposite
    ("", "anything", False),
])
def test_same_finding(a, b, same):
    assert same_finding(a, b) is same


@pytest.fixture()
def eng(real):  # noqa: F811
    return EvidenceEngine(real, model=None, http=HttpClient(transport=FakeLabelTransport(), enabled=True))


def test_report_counts_documents_not_records(eng):
    rep = eng.report("warfarin", "fluconazole")
    labels = [e for e in rep.evidence if e.category != EvidenceCategory.DATABASE_INTERACTION_RECORD]
    assert len(labels) == 4                               # 2 per label, was 6
    assert len({e.source_record_id for e in labels}) == 2
    flu = [e for e in labels if e.source_record_id.endswith("f1")]
    assert all(e.also_in_sections == ["DRUG INTERACTIONS"] for e in flu)
    assert any("listed once" in q for e in flu for q in e.qualifiers)
    known = next(s for s in rep.explanation.sections if s.id == "known")
    label_statements = [s for s in known.statements if s.kind == "documented" and "label" in s.text.en]
    assert len(label_statements) == 2                     # one per document
    assert len({s.text.en for s in known.statements}) == len(known.statements)   # nothing repeated
    certainty = next(s for s in rep.explanation.sections if s.id == "certainty")
    counts = certainty.statements[0].text
    assert "2 FDA label(s) (4 distinct excerpt(s))" in counts.en and "1 DrugBank record(s)" in counts.en
    assert "not separate confirmations" in counts.en
    assert "2 инструкции FDA (4 фрагмента)" in counts.ru


def test_multi_reports_label_documents(eng):
    m = eng.multi(["warfarin", "fluconazole", "simvastatin"])
    pair = next(p for p in m.pairs if {p.drug_a, p.drug_b} == {"DB00682", "DB00196"})
    assert (pair.n_label_documents, pair.n_label_records) == (2, 4)


def test_explanation_counts_old_duplicated_records_once(real):  # noqa: F811
    """Records from an engine that did not merge (or a source that repeats text)
    still count each sentence once in the explanation."""
    from serving.evidence.explain import _distinct_excerpts
    eng = EvidenceEngine(real, model=None, http=HttpClient(transport=FakeLabelTransport(), enabled=True))
    rep = eng.report("warfarin", "fluconazole")
    flu = [e for e in rep.evidence if (e.source_record_id or "").endswith("f1")]
    dup = flu + [flu[0].model_copy(update={"id": flu[0].id + ":dup", "section": "DRUG INTERACTIONS", "also_in_sections": []})]
    assert _distinct_excerpts(dup) == 2


def test_pooled_metric_is_never_called_s2(real):  # noqa: F811
    """The frozen study reports S2 only pooled with S3. An S2 pair's explanation
    must say 'pooled', and must not present the figure as its own regime's."""
    from types import SimpleNamespace

    from serving.evidence import explain as ex
    from serving.evidence.model_context import model_block

    score = SimpleNamespace(raw_model_score=0.99, calibrated_model_score=0.8)
    for reg, (sa, sb) in {"S2": ("val", "train"), "S3": ("test", "test")}.items():
        mb = model_block(score=score, split_a=sa, split_b=sb, documented=True, has_protein_a=True, has_protein_b=True)
        stmts = ex._certainty([], SimpleNamespace(findings=[]), mb)
        text = next(s for s in stmts if s.kind == "model").text
        if reg == "S2":
            assert "pooled" in text.en and "no S2-only figure" in text.en and "(as here)" not in text.en
            assert "объединённом" in text.ru and "только для S2" in text.ru
            assert mb.measured_performance[0].view.startswith("pooled")
        else:
            assert "S3, as here" in text.en and "pooled" not in text.en
