"""Integration: no unverified directional claim leaves the API.

THE RISK. The TDC DrugBank export's (ID1, ID2) order often contradicts the
sentence template's #Drug1/#Drug2 slots (reports/v3_tdc_direction_audit.md).
Filling the template in exported order would publish sentences like "The serum
concentration of fluconazole can be increased when it is combined with
warfarin" — the reverse of what DrugBank's own roles indicate.

WHAT IS PINNED HERE.
1. Every one of the 191,798 records: unverified types are rendered without a
   drug name or ID in either language and without drug1/drug2; verified and
   symmetric types are filled in exported order.
2. End to end through /api/v3 (report, graph, multi) for documented pairs with
   unverified records: neither orientation of the filled template — English
   or Russian — appears anywhere in the serialized JSON.
3. The mechanism graph's interaction edges are undirected unless verified.

Mechanism hypotheses DO name an actor and an affected drug; they come from
documented roles, are labelled "hypothesis", and are not what this file polices.
"""

from __future__ import annotations

import random
import re

import pytest
from fastapi.testclient import TestClient

from serving.evidence.direction import orientation_status
from serving.evidence.engine import EvidenceEngine
from serving.evidence.mechanism import mechanism_graph
from serving.evidence.records import TEMPLATE_RU, database_evidence

from test_v3_evidence import real, real_artifact  # noqa: F401  (session fixtures)


def _names(store, i: int) -> list[str]:
    e = store.lexicon.entries[i]
    return [n for n in (e.id, e.inn, e.inn_ru) if n]


def _contains(text: str, name: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text, re.IGNORECASE) is not None


def _filled(store, y: int, x: int, z: int) -> list[str]:
    """Both orientations of record type y for drugs x, z, in both languages."""
    ex, ez = store.lexicon.entries[x], store.lexicon.entries[z]
    out = []
    for d1, d2 in ((ex, ez), (ez, ex)):
        en = store.ddi_types[y].replace("#Drug1", d1.inn or d1.id).replace("#Drug2", d2.inn or d2.id)
        ru = TEMPLATE_RU[y].replace("#Drug1", d1.display("ru")).replace("#Drug2", d2.display("ru"))
        out += [en, ru, ru[0].upper() + ru[1:]]
    return out


def test_every_record_respects_its_direction_status(real):  # noqa: F811
    counts = {"not_verified": 0, "as_exported_verified": 0, "symmetric": 0}
    for (a, b) in real.records:
        for rec in database_evidence(real, a, b)[0]:
            counts[rec.direction] += 1
            d1 = real.index[rec.original_identifiers["drugbank_id_drug1_as_exported"]]
            d2 = real.index[rec.original_identifiers["drugbank_id_drug2_as_exported"]]
            if rec.direction == "not_verified":
                assert rec.drug1_id is None and rec.drug2_id is None, rec.id
                assert rec.statement_origin == "source_template_direction_neutral", rec.id
                for name in _names(real, d1) + _names(real, d2):
                    assert not _contains(rec.statement, name), (rec.id, name)
                    assert not _contains(rec.statement_ru or "", name), (rec.id, name)
            else:
                assert rec.drug1_id == real.ids[d1] and rec.drug2_id == real.ids[d2]
                assert rec.statement_origin == "source_template_filled"
    assert sum(counts.values()) == 191_798
    # Matches reports/v3_tdc_direction_audit.md.
    assert counts == {"not_verified": 115_920, "as_exported_verified": 14_481, "symmetric": 61_397}


def _sample_unverified_pairs(store, n: int, seed: int = 11) -> list[tuple[int, int]]:
    pairs = [p for p, recs in store.records.items()
             if any(orientation_status(y, store.direction_audit) == "unverified" for _, _, y in recs)]
    rng = random.Random(seed)
    must = [(store.index["DB00682"], store.index["DB00196"]),   # warfarin + fluconazole (type 73)
            (store.index["DB00641"], store.index["DB01211"])]   # simvastatin + clarithromycin
    return must + rng.sample(pairs, n)


def _forbidden_sentences(store, a: int, b: int) -> list[str]:
    out = []
    for _, _, y in store.pair_records(a, b):
        if orientation_status(y, store.direction_audit) == "unverified":
            out += _filled(store, y, a, b)
    return out


def test_engine_reports_never_contain_an_unverified_orientation(real):  # noqa: F811
    eng = EvidenceEngine(real, external=False)
    for a, b in _sample_unverified_pairs(real, 150):
        rep = eng.report(real.ids[a], real.ids[b], include_labels=False)
        text = rep.model_dump_json()
        for sentence in _forbidden_sentences(real, a, b):
            assert sentence not in text, (real.ids[a], real.ids[b], sentence)
        graph = mechanism_graph(real, a, b)
        for e in graph.edges:
            if e.kind == "documented_interaction" and e.detail["direction"] == "not_verified":
                assert e.directed is False
                assert (e.source, e.target) == (real.ids[a], real.ids[b]), "request order, not export order"
        gtext = graph.model_dump_json()
        for sentence in _forbidden_sentences(real, a, b):
            assert sentence not in gtext


def test_verified_types_keep_their_direction(real):  # noqa: F811
    verified = [(p, (d1, d2, y)) for p, recs in real.records.items() for d1, d2, y in recs
                if orientation_status(y, real.direction_audit) == "consistent"][:50]
    assert verified, "types 4 and 75 are verified"
    for (a, b), (d1, d2, y) in verified:
        g = mechanism_graph(real, a, b)
        edge = next(e for e in g.edges if e.kind == "documented_interaction" and e.id.endswith(f":t{y}"))
        assert edge.directed and (edge.source, edge.target) == (real.ids[d1], real.ids[d2])


@pytest.fixture()
def http(real_artifact, monkeypatch):  # noqa: F811
    import serving.api as api
    import serving.evidence.store as store_mod
    from serving.ratelimit import limiter

    monkeypatch.setattr(store_mod, "ARTIFACT", real_artifact)
    monkeypatch.setattr(api, "ALLOW_NO_MODEL", True)
    monkeypatch.setenv("DDINET_EXTERNAL_SOURCES", "off")
    limiter.reset()
    with TestClient(api.app) as c:
        yield c
    limiter.reset()


def test_http_responses_never_contain_an_unverified_orientation(http, real):  # noqa: F811
    pairs = _sample_unverified_pairs(real, 8)        # stays inside the per-minute limit
    for a, b in pairs:
        body = {"drug_a": real.ids[a], "drug_b": real.ids[b], "include_labels": False}
        report = http.post("/api/v3/report", json=body)
        graph = http.post("/api/v3/graph", json=body)
        assert report.status_code == graph.status_code == 200
        for sentence in _forbidden_sentences(real, a, b):
            assert sentence not in report.text and sentence not in graph.text, sentence
        # Explanation sentences built on an unverified record name neither drug.
        rep = report.json()
        unverified = {e["id"] for e in rep["evidence"] if e["direction"] == "not_verified"}
        for sec in rep["explanation"]["sections"]:
            for st in sec["statements"]:
                if st["kind"] == "documented" and st["refs"] and set(st["refs"]) <= unverified:
                    for name in _names(real, a) + _names(real, b):
                        assert not _contains(st["text"]["ru"], name) and not _contains(st["text"]["en"], name)
    ids = [real.ids[a] for a, _ in pairs[:4]] + [real.ids[b] for _, b in pairs[:4]]
    multi = http.post("/api/v3/multi", json={"drugs": ids, "include_labels": False})
    assert multi.status_code == 200
    for a, b in pairs[:4]:
        for sentence in _forbidden_sentences(real, a, b):
            assert sentence not in multi.text
