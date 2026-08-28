"""Tests for the mechanism ontology.

Written around the three defects the audit found in the dormant draft
(MECHANISM_ONTOLOGY.md section 6.2). Each has a test that fails if the defect
returns, because each is the kind of bug that produces a plausible-looking
distribution rather than an error.
"""
import pandas as pd
import pytest

from ddinet.data.mechanism import Confidence, classify, coverage_report

DATA = __import__("pathlib").Path(__file__).resolve().parents[1] / "data" / "raw" / "drugbank.tab.gz"


# --------------------------------------------------------------------------
# Defect 1: the corpus's largest class must NOT be given a mechanism
# --------------------------------------------------------------------------

def test_generic_adverse_risk_is_ambiguous_not_synergy():
    """Y=49 is 31.7% of the corpus and names no mechanism. The draft labelled
    it `pd_synergy`, which ASSIGNS a mechanism the source never stated - the
    single most consequential defect in the ontology layer."""
    m = classify("The risk or severity of adverse effects can be increased "
                 "when X is combined with Y.")
    assert m.category == "UNSPEC_ADVERSE_RISK"
    assert m.confidence is Confidence.AMBIGUOUS
    assert not m.is_mechanistic
    assert m.carrier == "", "'adverse effects' is the absence of a carrier"


def test_a_NAMED_risk_is_still_a_mechanism_unlike_the_generic_one():
    """The generic rule must not swallow the specific ones. 'risk of bleeding'
    names a carrier; 'risk of adverse effects' does not."""
    m = classify("The risk or severity of bleeding can be increased when X is "
                 "combined with Y.")
    assert m.category == "PD_SYNERGY_TOXIC"
    assert m.carrier == "bleeding"
    assert m.is_mechanistic


# --------------------------------------------------------------------------
# Defect 2: exposure labels must not mix confidences
# --------------------------------------------------------------------------

def test_bare_serum_concentration_is_medium_confidence_and_unspecified():
    """Metabolism, transport and excretion would all produce this sentence.
    Calling it PK_METABOLISM would be a guess."""
    m = classify("The serum concentration of Y can be increased when it is "
                 "combined with X.")
    assert m.category == "PK_EXPOSURE_UNSPEC"
    assert m.confidence is Confidence.MEDIUM


def test_active_metabolites_names_metabolism_and_is_high_confidence():
    """This sentence DOES point at a carrier, so it must not land in the same
    bucket as the bare one."""
    m = classify("The serum concentration of the active metabolites of Y can "
                 "be increased when Y is used in combination with X.")
    assert m.category == "PK_METABOLISM"
    assert m.confidence is Confidence.HIGH


# --------------------------------------------------------------------------
# Defect 3: both sentence shapes for excretion
# --------------------------------------------------------------------------

@pytest.mark.parametrize("text,direction", [
    ("X may decrease the excretion rate of Y which could result in a higher "
     "serum level.", "increased_exposure"),
    ("X may increase the excretion rate of Y which could result in a lower "
     "serum level and potentially a reduction in efficacy.", "decreased_exposure"),
    ("The excretion of Y can be decreased when combined with X.",
     "increased_exposure"),
])
def test_excretion_is_matched_in_every_sentence_shape(text, direction):
    """The draft had an excretion rule that never fired on TDC's phrasing:
    1 825 of its 2 010 uncovered rows were this one miss."""
    m = classify(text)
    assert m.category == "PK_EXCRETION"
    assert m.direction == direction


# --------------------------------------------------------------------------
# The contract the ontology rests on
# --------------------------------------------------------------------------

def test_rule_order_is_load_bearing_specific_before_generic():
    """If the generic risk rule were tried first it would capture Y=49. This
    asserts the ordering property directly rather than trusting the list."""
    generic = classify("The risk or severity of adverse effects can be increased.")
    specific = classify("The risk or severity of QTc prolongation can be increased.")
    assert generic.category == "UNSPEC_ADVERSE_RISK"
    assert specific.category == "PD_SYNERGY_TOXIC"


def test_empty_and_unmatched_input_is_ambiguous_not_a_guess():
    assert classify("").category == "UNCLASSIFIED"
    assert classify("").confidence is Confidence.AMBIGUOUS
    weird = classify("Some sentence no template ever produced.")
    assert weird.category == "UNCLASSIFIED"
    assert not weird.is_mechanistic


def test_carrier_is_orthogonal_to_category():
    """QTc prolongation and CNS depression are one mechanism aimed at different
    systems, so the carrier is a field and not part of the category name."""
    a = classify("X may increase the QTc-prolonging activities of Y.")
    b = classify("X may increase the sedative activities of Y.")
    assert a.category == b.category == "PD_SYNERGY_TOXIC"
    assert a.carrier != b.carrier


def test_named_activity_is_low_confidence():
    """'increases the hypotensive activities' names a clinical effect, not a
    mechanism - it is equally consistent with a PK cause."""
    assert classify("X may increase the hypotensive activities of Y.").confidence \
        is Confidence.LOW


def test_coverage_report_rejects_mismatched_weights():
    with pytest.raises(ValueError, match="same length"):
        coverage_report(["a", "b"], [1])


def test_raw_label_survives_classification():
    """Every layer is kept; nothing overwrites its input. Re-labelling must not
    require re-reading the source."""
    text = "The metabolism of Y can be decreased when combined with X."
    assert classify(text).raw == text


# --------------------------------------------------------------------------
# Against the real corpus
# --------------------------------------------------------------------------

@pytest.mark.skipif(not DATA.exists(), reason="TDC DrugBank export not present")
def test_every_template_in_the_corpus_is_classified():
    """A rise in the unclassified rate means the source changed its templates.
    This is the project's detector for the two drifting apart."""
    df = pd.read_csv(DATA, sep="\t")
    templates = df.groupby("Y")["Map"].first()
    counts = df["Y"].value_counts()
    report = coverage_report(list(templates), [int(counts[y]) for y in templates.index])
    assert report["unclassified"] == 0, (
        f"{report['unclassified']} rows unclassified - templates may have changed"
    )


@pytest.mark.skipif(not DATA.exists(), reason="TDC DrugBank export not present")
def test_a_third_of_the_corpus_carries_no_mechanism():
    """The headline honest number. If a future change makes this fraction fall
    sharply, something started assigning mechanisms it cannot know."""
    df = pd.read_csv(DATA, sep="\t")
    templates = df.groupby("Y")["Map"].first()
    counts = df["Y"].value_counts()
    report = coverage_report(list(templates), [int(counts[y]) for y in templates.index])
    ambiguous = report["by_confidence"]["AMBIGUOUS"] / report["total"]
    assert 0.30 < ambiguous < 0.33, f"AMBIGUOUS fraction moved to {ambiguous:.3f}"
    assert report["mechanistic_fraction"] == pytest.approx(0.6833, abs=0.005)
