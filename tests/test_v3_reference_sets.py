"""CRESCENDDI reference set: ingestion pipeline and its use as outcome evidence.

Ingestion tests use small in-memory rows shaped like the published spreadsheets
(column names as in Data Records 1 and 2); the integration tests use the real
committed index, built by scripts/data/ingest_crescenddi.py from the pinned,
checksummed data records.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest
from test_v3_evidence import (  # noqa: F401  (session fixtures)
    real,
    real_artifact,
    real_noref,
)

from ddinet.data import crescenddi as cr
from ddinet.data.git_fetch import FetchError, PinnedFiles, sha256_file, verify
from serving.evidence.engine import EvidenceEngine
from serving.evidence.outcomes import CATEGORIES
from serving.evidence.reference_sets import EFFECTS, EVENT_MAP, MEDDRA_MAP_VERSION
from serving.evidence.schema import EvidenceCategory

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "data" / "reference_sets" / "crescenddi" / "crescenddi_index_v1.json.gz"
MANIFEST = ROOT / "data" / "reference_sets" / "crescenddi" / "MANIFEST.json"

IDS = {"warfarin": "DB00682", "Aspirin": "DB00945", "aspirin": "DB00945", "fluconazole": "DB00196",
       "acetylsalicylic acid": "DB00945"}


def lookup(name):
    d = IDS.get(name)
    return (d, "inn") if d else (None, None)


def pos(n1, n2, ev="Haemorrhage", code=10055798, src="BNF+Micromedex", **extra):
    return {"DRUG_1_CONCEPT_NAME": n1, "DRUG_2_CONCEPT_NAME": n2, "EVENT_CONCEPT_NAME": ev, "MDR_CODE": code,
            "EVENT_SOURCE": src, "BNF_SEV_LEVEL": "Severe", "MICROMEDEX_SEV_LEVEL": "Major", **extra}


def neg(n1, n2, ev="Deafness", code=10011878):
    return {"DRUG_1_CONCEPT_NAME": n1, "DRUG_2_CONCEPT_NAME": n2, "EVENT_CONCEPT_NAME": ev, "MDR_CODE": code}


# --------------------------------------------------------------- ingestion ----
def test_schema_validation_rejects_bad_rows_and_missing_columns():
    p = cr.build_index([pos("warfarin", "aspirin"), pos("warfarin", None), pos("warfarin", "aspirin", code="x"),
                        pos("warfarin", "aspirin", src="Lexicomp")], [], lookup)
    reasons = sorted(r["reason"].split(":")[0] for r in p["rejected_rows"])
    assert reasons == ["MedDRA code not an integer", "missing drug or event name", "unknown EVENT_SOURCE"]
    assert p["stats"]["records"] == {"positive": 1}
    with pytest.raises(cr.SchemaError):
        cr.build_index([{"DRUG_1_CONCEPT_NAME": "warfarin"}], [], lookup)


def test_mapping_dedup_orientation_and_unmapped():
    p = cr.build_index([pos("warfarin", "aspirin"), pos("Aspirin", "warfarin"), pos("warfarin", "heparin")], [], lookup)
    recs = p["records"]
    assert len(recs) == 1 and recs[0]["drug_a"] < recs[0]["drug_b"]          # one unordered pair
    assert recs[0]["rows"] == [2, 3] and sorted(recs[0]["names"], key=str.lower) == ["aspirin", "Aspirin", "warfarin"]
    assert p["stats"]["unmapped_drug_names"] == ["heparin"]                   # reported, never guessed
    assert p["stats"]["dropped"] == {"positive_duplicate_collapsed": 1, "positive_unmapped_drug": 1}


def test_self_pairs_and_positive_negative_conflicts_are_removed():
    p = cr.build_index([pos("aspirin", "acetylsalicylic acid"), pos("warfarin", "fluconazole", "Deafness", 10011878)],
                       [neg("fluconazole", "warfarin")], lookup)
    assert p["records"] == []
    assert p["stats"]["dropped"] == {"positive_self_pair_after_mapping": 1}
    assert p["stats"]["positive_negative_conflicts_removed"] == 1


def test_severity_and_evidence_ratings_are_not_carried_over():
    p = cr.build_index([pos("warfarin", "aspirin")], [], lookup)
    blob = json.dumps(p)
    assert "Severe" not in blob and "Major" not in blob and "SEV" not in blob


def test_output_is_deterministic(tmp_path):
    p = cr.build_index([pos("warfarin", "aspirin")], [neg("warfarin", "fluconazole")], lookup)
    assert cr.dumps_gz(p) == cr.dumps_gz(json.loads(json.dumps(p)))
    m = cr.write(p, tmp_path, {"x": "0" * 64}, "2026-10-16")
    assert m["output"]["sha256"] == sha256_file(tmp_path / m["output"]["file"])
    assert cr.load_index(tmp_path / m["output"]["file"])["records"] == p["records"]


def test_checksums_are_enforced(tmp_path):
    (tmp_path / "a.txt").write_text("data")
    good = PinnedFiles("t", "https://example.invalid/r", "0" * 40, {"a.txt": sha256_file(tmp_path / "a.txt")})
    assert verify(good, tmp_path) == {"a.txt": good.files["a.txt"]}
    bad = PinnedFiles("t", "https://example.invalid/r", "0" * 40, {"a.txt": "f" * 64, "b.txt": "0" * 64})
    with pytest.raises(FetchError, match="checksum mismatch: a.txt.*missing: b.txt|missing: b.txt"):
        verify(bad, tmp_path)


# ----------------------------------------------------- committed artefact ----
def test_committed_index_matches_its_manifest_and_pin():
    m = json.loads(MANIFEST.read_text())
    assert m["output"]["sha256"] == sha256_file(INDEX)
    assert m["source"]["commit"] == cr.SPEC.commit
    assert {k: v["sha256"] for k, v in m["inputs"].items()} == cr.SPEC.files
    p = cr.load_index(INDEX)
    assert p["stats"] == m["stats"]
    for x in p["records"]:
        assert x["set"] in ("positive", "negative") and x["drug_a"] < x["drug_b"]
        assert 10_000_000 <= x["meddra_code"] <= 99_999_999
    keys = [(x["set"], x["drug_a"], x["drug_b"], x["meddra_code"]) for x in p["records"]]
    assert len(keys) == len(set(keys))                                         # no duplicates
    pos_keys = {k[1:] for k in keys if k[0] == "positive"}
    assert not pos_keys & {k[1:] for k in keys if k[0] == "negative"}          # no contradictions


def test_every_event_in_the_index_is_mapped_to_a_known_effect():
    with gzip.open(INDEX, "rt") as f:
        terms = {x["event"] for x in json.load(f)["records"]}
    assert terms <= set(EVENT_MAP), sorted(terms - set(EVENT_MAP))
    assert all(e.category in CATEGORIES for e in EFFECTS.values())
    assert set(EVENT_MAP.values()) <= set(EFFECTS)


# --------------------------------------------------------- engine usage ----
@pytest.fixture()
def eng(real):  # noqa: F811
    return EvidenceEngine(real, model=None, external=False)


def test_reference_outcome_is_pair_specific_and_cited(eng):
    r = eng.report("warfarin", "fluconazole")
    ref = [e for e in r.evidence if e.category == EvidenceCategory.REFERENCE_SET_OUTCOME]
    assert ref and all("CRESCENDDI" in e.source_name and e.source_url.endswith("CRESCENDDI") for e in ref)
    assert all(e.source_severity is None for e in ref)
    bleed = next(x for x in r.outcomes.outcomes if x.effect == "bleeding")
    assert bleed.evidence_status == "documented" and bleed.evidence_strength == "reference_set_statement"
    assert {s.source_type for s in bleed.supports} == {"reference_set"}
    assert all(s.extraction_method.startswith(f"{MEDDRA_MAP_VERSION}:meddra=") for s in bleed.supports)
    assert "Haemorrhage" in bleed.supports[0].matched_terms
    assert bleed.seriousness == "documented_no_standard_severity"
    assert "not reproduced" in bleed.seriousness_basis.en
    # CRESCENDDI states no mechanism: a chain may reach the outcome, but that last
    # link is never "documented" (no single source states exposure change AND bleeding)
    to_bleed = [lk for c in r.outcomes.chains for lk in c.links if lk.target == f"outcome:{bleed.id}" or bleed.id in lk.refs]
    assert to_bleed and all(lk.provenance == "plausible_unconfirmed" for lk in to_bleed)
    assert any(c.source == "crescenddi" and c.status == "ok" for c in r.sources_checked)
    assert any("CRESCENDDI" in st.text.en for sec in r.explanation.sections for st in sec.statements)


def test_drugbank_pd_record_still_never_becomes_bleeding(eng):
    o = eng.report("warfarin", "aspirin").outcomes
    bleed = next(x for x in o.outcomes if x.effect == "bleeding")
    assert {s.source_type for s in bleed.supports} == {"reference_set"}      # bleeding only where a source names it
    pd = next(x for x in o.outcomes if x.effect == "anticoagulant_increase")
    assert {s.source_type for s in pd.supports} == {"drugbank_tdc"}


def test_reference_only_pair_is_documented_and_absent_pair_is_not(eng, real):  # noqa: F811
    only = next(k for k in sorted(real.reference) if k not in real.records)
    a, b = (real.ids[i] for i in only)
    r = eng.report(a, b)
    assert r.evidence_status.value == "documented_no_severity"
    assert r.outcomes.interaction_status == "documented_interaction"
    assert all(e.category == EvidenceCategory.REFERENCE_SET_OUTCOME for e in r.evidence)
    none = eng.report("metformin", "warfarin")
    assert none.outcomes.interaction_status == "insufficient_evidence"
    assert any(c.source == "crescenddi" and c.status == "no_match" for c in none.sources_checked)
    assert not [x for x in none.outcomes.outcomes if not x.research_only]


def test_reference_set_adds_nothing_for_pairs_it_does_not_list(eng, real, real_noref):  # noqa: F811
    without = EvidenceEngine(real_noref, model=None, external=False)
    for a, b in [("metformin", "warfarin"), ("DB00641", "DB01211")]:
        ia, ib = (real.lexicon.lookup_name(x)[0] or real.lexicon.by_id[x] for x in (a, b))
        listed = bool(real.reference_outcomes(ia.index, ib.index))
        o1 = {x.id for x in eng.report(a, b).outcomes.outcomes if not x.research_only}
        o0 = {x.id for x in without.report(a, b).outcomes.outcomes if not x.research_only}
        assert (o1 == o0) is (not listed) or o0 <= o1


def test_multi_counts_reference_records_separately(eng):
    m = eng.multi(["warfarin", "fluconazole", "aspirin"])
    p = next(x for x in m.pairs if {x.drug_a, x.drug_b} == {"DB00682", "DB00196"})
    assert p.n_reference_records >= 1 and p.n_label_records == 0
    assert "bleeding_coagulation" in p.outcome_categories
