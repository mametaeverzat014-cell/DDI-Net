"""External-source adapters against recorded response SHAPES — no network.

The responses below follow the documented structure of the openFDA drug label
endpoint and the RxNav REST API. Their CONTENT is synthetic: set IDs are all
zeros, manufacturer fields say SYNTHETIC TEST FIXTURE, and the label sentences
are written for these tests. None of it is, or may be presented as, a real
label statement.
"""

from __future__ import annotations

import json
import urllib.parse

import pytest

from serving.evidence.adapters.http import HttpClient, SourceUnavailable
from serving.evidence.adapters.openfda import OpenFdaLabelAdapter
from serving.evidence.adapters.rxnorm import RxNormAdapter
from serving.evidence.engine import EvidenceEngine
from serving.evidence.schema import EvidenceCategory, EvidenceStatus

from test_v3_evidence import real, real_artifact  # noqa: F401  (session fixtures)

ZERO_SET = "00000000-0000-0000-0000-000000000001"


def _label(set_id: str, generic: str, substance: list[str], effective: str, **sections) -> dict:
    return {
        "set_id": set_id, "id": "00000000-0000-0000-0000-00000000aaaa", "version": "3",
        "effective_time": effective,
        **{k: [v] for k, v in sections.items()},
        "openfda": {"generic_name": [generic], "brand_name": ["SYNTHETIC"], "substance_name": substance,
                    "product_type": ["HUMAN PRESCRIPTION DRUG"], "manufacturer_name": ["SYNTHETIC TEST FIXTURE"]},
    }


FLUCONAZOLE_LABEL = _label(
    ZERO_SET, "FLUCONAZOLE", ["FLUCONAZOLE"], "20250101",
    drug_interactions="7 DRUG INTERACTIONS [synthetic test text] Coadministration with warfarin was "
                      "associated with increased prothrombin time in a fixture study. Monitor as described. "
                      "Fluconazole did not significantly alter the exposure of fixturamide.",
    contraindications="[synthetic test text] Coadministration with terfenadine is contraindicated.",
)
OLDER_COMBO = _label("00000000-0000-0000-0000-000000000002", "FLUCONAZOLE AND OTHER",
                     ["FLUCONAZOLE", "OTHER"], "20260101",
                     drug_interactions="[synthetic] warfarin is mentioned in a combination product.")
WARFARIN_LABEL = _label(
    "00000000-0000-0000-0000-000000000003", "WARFARIN SODIUM", ["WARFARIN SODIUM"], "20240101",
    boxed_warning="WARNING: BLEEDING RISK [synthetic test text] Drugs such as fluconazole may "
                  "increase bleeding risk in this fixture.",
)


class FakeTransport:
    """Routes by URL substring; records every URL it was asked for."""

    def __init__(self, routes: dict[str, tuple[int, object]] | None = None, fail: bool = False):
        self.routes = routes or {}
        self.fail = fail
        self.calls: list[str] = []

    def __call__(self, url: str, timeout: float):
        self.calls.append(url)
        if self.fail:
            raise OSError("simulated network failure")
        decoded = urllib.parse.unquote(url)
        for key, (status, body) in self.routes.items():
            if key in decoded:
                return status, json.dumps(body).encode()
        return 404, json.dumps({"error": {"code": "NOT_FOUND", "message": "No matches found!"}}).encode()


def fda_routes() -> dict:
    return {
        'generic_name:"fluconazole"': (200, {"meta": {"results": {"total": 2}}, "results": [OLDER_COMBO, FLUCONAZOLE_LABEL]}),
        'generic_name:"warfarin"': (200, {"meta": {"results": {"total": 1}}, "results": [WARFARIN_LABEL]}),
    }


# ------------------------------------------------------------------- http -----
def test_network_failure_is_unavailable_not_empty():
    t = FakeTransport(fail=True)
    http = HttpClient(transport=t, enabled=True)
    with pytest.raises(SourceUnavailable):
        http.get_json("openfda_label", "https://api.fda.gov/drug/label.json?search=x")
    # cooldown: the second call does not hit the network again
    with pytest.raises(SourceUnavailable, match="cooldown"):
        http.get_json("openfda_label", "https://api.fda.gov/drug/label.json?search=y")
    assert len(t.calls) == 1


@pytest.mark.parametrize("status", [403, 429, 500, 503])
def test_http_errors_are_unavailable(status):
    http = HttpClient(transport=lambda u, t: (status, b"{}"), enabled=True)
    with pytest.raises(SourceUnavailable):
        http.get_json("s", "https://x.invalid")


def test_disabled_client_never_calls_transport():
    t = FakeTransport()
    with pytest.raises(SourceUnavailable, match="disabled"):
        HttpClient(transport=t, enabled=False).get_json("s", "https://x.invalid")
    assert t.calls == []


def test_responses_are_cached():
    t = FakeTransport(fda_routes())
    http = HttpClient(transport=t, enabled=True)
    url = 'https://api.fda.gov/drug/label.json?search=openfda.generic_name:"warfarin"'
    http.get_json("openfda_label", url)
    http.get_json("openfda_label", url)
    assert len(t.calls) == 1


# ---------------------------------------------------------------- openFDA -----
def test_label_choice_prefers_single_ingredient_over_newer_combination():
    a = OpenFdaLabelAdapter(HttpClient(transport=FakeTransport(fda_routes()), enabled=True))
    label, n = a.current_label("fluconazole")
    assert n == 2 and label.set_id == ZERO_SET
    assert label.dailymed_url.endswith(ZERO_SET)


def test_mentions_carry_section_and_no_effect_flag():
    a = OpenFdaLabelAdapter(HttpClient(transport=FakeTransport(fda_routes()), enabled=True))
    label, _ = a.current_label("fluconazole")
    ex = a.find_mentions(label, ["warfarin", "fixturamide", "terfenadine"])
    by_term = {e.matched_term: e for e in ex}
    assert by_term["warfarin"].section == "DRUG INTERACTIONS" and not by_term["warfarin"].no_effect_wording
    assert by_term["fixturamide"].no_effect_wording
    assert by_term["terfenadine"].category == "label_contraindication"
    # whole words only
    assert not a.find_mentions(label, ["warf"])


def test_api_key_never_leaves_in_urls():
    t = FakeTransport(fda_routes())
    a = OpenFdaLabelAdapter(HttpClient(transport=t, enabled=True), api_key="SECRET123")
    label, _ = a.current_label("warfarin")
    assert "SECRET123" in t.calls[0]
    assert "SECRET123" not in label.retrieval_url


# ----------------------------------------------------------------- RxNorm -----
RX_ROUTES = {
    "rxcui.json?name=Fixtrabrand": (200, {"idGroup": {"name": "Fixtrabrand", "rxnormId": ["900001"]}}),
    "rxcui/900001/properties.json": (200, {"properties": {"rxcui": "900001", "name": "Fixtrabrand", "tty": "BN"}}),
    "rxcui/900001/related.json": (200, {"relatedGroup": {"conceptGroup": [
        {"tty": "IN", "conceptProperties": [{"rxcui": "11289", "name": "warfarin", "tty": "IN"}]}]}}),
    "rxcui.json?name=Comboxa": (200, {"idGroup": {"rxnormId": ["900002"]}}),
    "rxcui/900002/properties.json": (200, {"properties": {"rxcui": "900002", "name": "Comboxa", "tty": "BN"}}),
    "rxcui/900002/related.json": (200, {"relatedGroup": {"conceptGroup": [
        {"tty": "IN", "conceptProperties": [{"rxcui": "1", "name": "warfarin", "tty": "IN"},
                                            {"rxcui": "2", "name": "fluconazole", "tty": "IN"}]}]}}),
    "rxcui.json?name=Outsidamab": (200, {"idGroup": {"rxnormId": ["900003"]}}),
    "rxcui/900003/properties.json": (200, {"properties": {"rxcui": "900003", "name": "outsidamab", "tty": "IN"}}),
    "rxcui.json?name=Nothing": (200, {"idGroup": {"name": "Nothing"}}),
}


def test_rxnorm_brand_to_ingredient():
    rx = RxNormAdapter(HttpClient(transport=FakeTransport(RX_ROUTES), enabled=True))
    r = rx.resolve("Fixtrabrand")
    assert [c.name for c in r.ingredients] == ["warfarin"]
    assert rx.resolve("Nothing") is None


@pytest.fixture()
def wired(real):  # noqa: F811
    t = FakeTransport({**RX_ROUTES, **fda_routes()})
    return EvidenceEngine(real, http=HttpClient(transport=t, enabled=True)), t


def test_engine_resolves_brand_through_rxnorm(wired):
    eng, _ = wired
    r = eng.resolve("Fixtrabrand")
    assert r.status == "resolved" and r.drug.id == "DB00682" and r.drug.matched_on == "rxnorm_ingredient"
    assert r.rxnorm["ingredients"][0]["rxcui"] == "11289"
    assert eng.resolve("Comboxa").status == "multiple_ingredients"
    assert eng.resolve("Outsidamab").status == "not_in_universe"


def test_engine_report_with_labels(wired):
    eng, _ = wired
    rep = eng.report("warfarin", "fluconazole")
    cats = [e.category for e in rep.evidence]
    assert EvidenceCategory.LABEL_WARNING_OR_INTERACTION in cats      # fluconazole label -> warfarin
    assert EvidenceCategory.LABEL_BOXED_WARNING in cats               # warfarin label -> fluconazole
    assert rep.evidence_status == EvidenceStatus.WARNING_IN_LABEL
    lab = next(e for e in rep.evidence if e.category == EvidenceCategory.LABEL_BOXED_WARNING)
    assert lab.statement_origin == "verbatim_excerpt" and "synthetic" in lab.statement
    assert lab.source_url.startswith("https://dailymed.nlm.nih.gov/")
    assert lab.source_severity is None
    assert {c.source: c.status for c in rep.sources_checked}["openfda_label"] == "ok"


def test_engine_report_when_labels_unreachable(real):  # noqa: F811
    eng = EvidenceEngine(real, http=HttpClient(transport=FakeTransport(fail=True), enabled=True))
    rep = eng.report("warfarin", "fluconazole")
    status = {c.source: c.status for c in rep.sources_checked}
    assert status["openfda_label"] == "unavailable"
    assert rep.evidence_status == EvidenceStatus.DOCUMENTED_NO_SEVERITY   # local records still count
    missing = next(s for s in rep.explanation.sections if s.id == "missing")
    assert any("не удалось проверить" in st.text.ru for st in missing.statements)
