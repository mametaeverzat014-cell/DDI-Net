"""HTTP contract of /api/v3 and its coexistence with the frozen /api/analyze.

The lean-image probe at the end runs the v3 request path in a subprocess with
pandas, torch, rdkit, sklearn and scipy blocked at import — the shape of the
deployed image — because a dependency that is only present on a developer's
machine is exactly what broke /api/analyze once before (tests/test_lean_runtime.py).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from test_v3_evidence import real, real_artifact  # noqa: F401  (session fixtures)

ROOT = Path(__file__).resolve().parents[1]
LEAN = ROOT / "runtime" / "model_assets" / "lean_decoder_v1.npz"


@pytest.fixture()
def client(real_artifact, monkeypatch):  # noqa: F811
    import serving.api as api
    import serving.evidence.store as store_mod

    from serving.ratelimit import limiter

    monkeypatch.setattr(store_mod, "ARTIFACT", real_artifact)
    monkeypatch.setattr(api, "ALLOW_NO_MODEL", True)
    monkeypatch.setenv("DDINET_EXTERNAL_SOURCES", "off")
    limiter.reset()        # each test starts with empty rate-limit windows
    with TestClient(api.app) as c:
        yield c
    limiter.reset()


def test_health_reports_both_layers(client):
    h = client.get("/api/health").json()
    assert h["evidence_available"] is True
    assert "model_available" in h


def test_report_contract(client):
    r = client.post("/api/v3/report", json={"drug_a": "warfarin", "drug_b": "флуконазол"})
    assert r.status_code == 200
    body = r.json()
    assert body["report_version"] == "3.0"
    assert body["drug_a"]["id"] == "DB00682" and body["drug_b"]["id"] == "DB00196"
    assert body["evidence_status"] == "documented_no_severity"
    assert [s["id"] for s in body["explanation"]["sections"]] == ["known", "why", "ai", "certainty", "missing"]
    # The three kinds of statement live in different fields.
    assert {"evidence", "mechanism", "model"} <= set(body)
    assert all(e["category"].startswith(("label_", "database_", "reference_")) for e in body["evidence"])
    assert all(f["status"] == "hypothesis" for f in body["mechanism"]["findings"])


def test_unresolved_drug_is_422_with_candidates(client):
    r = client.post("/api/v3/report", json={"drug_a": "warfarn", "drug_b": "fluconazole"})
    assert r.status_code == 422
    res = r.json()["detail"]["resolutions"]
    assert res[0]["status"] == "suggestions" and res[0]["candidates"][0]["id"] == "DB00682"


@pytest.mark.parametrize("payload", [
    {"drug_a": "<script>", "drug_b": "warfarin"},
    {"drug_a": "x" * 101, "drug_b": "warfarin"},
    {"drug_a": "warfarin"},
])
def test_bad_input_is_422(client, payload):
    assert client.post("/api/v3/report", json=payload).status_code == 422


def test_same_drug_is_422(client):
    assert client.post("/api/v3/report", json={"drug_a": "warfarin", "drug_b": "DB00682"}).status_code == 422


def test_multi_limits(client):
    ok = client.post("/api/v3/multi", json={"drugs": ["warfarin", "fluconazole", "simvastatin"]})
    assert ok.status_code == 200 and len(ok.json()["pairs"]) == 3
    assert client.post("/api/v3/multi", json={"drugs": ["warfarin"]}).status_code == 422
    assert client.post("/api/v3/multi", json={"drugs": ["warfarin"] * 9}).status_code == 422


def test_graph_endpoint(client):
    g = client.post("/api/v3/graph", json={"drug_a": "warfarin", "drug_b": "fluconazole"}).json()
    kinds = {n["kind"] for n in g["nodes"]}
    assert {"drug", "protein"} <= kinds
    assert set(g["legend"]) >= {"annotation", "pathway_membership", "documented_interaction"}


def test_resolve_endpoint(client):
    r = client.get("/api/v3/resolve", params={"q": "aspirin"}).json()
    assert r["status"] == "resolved" and r["drug"]["matched_on"] == "curated_alias"


def test_sources_endpoint_exposes_the_direction_audit(client):
    s = client.get("/api/v3/sources").json()
    assert s["external_sources_enabled"] is False
    assert s["direction_audit"]["47"]["consistency"] < 0.1


@pytest.mark.skipif(not LEAN.exists(), reason="lean model artifact not built")
def test_frozen_analyze_endpoint_unchanged(client):
    r = client.post("/api/analyze", json={"drug_a": "DB00331", "drug_b": "DB00682"})
    assert r.status_code == 200
    assert r.json()["status"] == "research_prediction"


PROBE = r'''
import sys, importlib.abc, json
BLOCKED = {"torch", "torch_geometric", "rdkit", "pandas", "sklearn", "scipy", "pyarrow"}
class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in BLOCKED:
            raise ImportError(f"BLOCKED: {fullname}")
        return None
sys.meta_path.insert(0, Blocker())
import serving.api as api
api.ALLOW_NO_MODEL = True
api._startup()
from serving import api_v3
rep = api_v3.report(api_v3.PairRequest(drug_a="warfarin", drug_b="fluconazole", include_labels=True))
multi = api_v3.multi(api_v3.MultiRequest(drugs=["warfarin", "fluconazole", "aspirin"], include_labels=False))
loaded = sorted(m for m in sys.modules if m.split(".")[0] in BLOCKED)
print(json.dumps({"status": rep.evidence_status.value, "model": rep.model.available,
                  "pairs": len(multi.pairs), "blocked_loaded": loaded}))
'''


def test_v3_runs_in_the_lean_image_shape(real_artifact):  # noqa: F811
    env = {**os.environ, "PYTHONPATH": str(ROOT), "DDINET_EVIDENCE_ARTIFACT": str(real_artifact),
           "DDINET_EXTERNAL_SOURCES": "off"}
    out = subprocess.run([sys.executable, "-c", PROBE], cwd=ROOT, env=env,
                         capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    res = json.loads(out.stdout.strip().splitlines()[-1])
    assert res["status"] == "documented_no_severity"
    assert res["pairs"] == 3
    assert res["blocked_loaded"] == []


@pytest.mark.skipif(not LEAN.exists(), reason="lean model artifact not built")
def test_report_carries_validated_modality_reliance(client):
    body = client.post("/api/v3/report", json={"drug_a": "warfarin", "drug_b": "fluconazole"}).json()
    m = body["model"]
    if not m["available"]:
        pytest.skip("model not loaded in this environment")
    r = m["modality_reliance"]
    assert r is not None, "artifact predates branch-zeroed encodings; rerun serving.precompute"
    assert abs(r["delta_protein"] - (r["baseline_raw"] - r["without_protein_raw"])) < 1e-12
    assert r["validation"]["n_rows"] == 84690 and r["validation"]["max_abs_diff"] < 1e-5
    assert abs(r["baseline_raw"] - m["raw_model_score"]) < 1e-9
