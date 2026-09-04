"""The lean request path must run with numpy and nothing else.

WHY THIS FILE EXISTS. The deployed lean image returned HTTP 500 on every
/api/analyze while /api/health cheerfully reported the model loaded. The handler
imported its tolerance constant from serving/parity.py, which imports pandas —
absent from the slim image. Every other test passed, because they all ran in an
environment where pandas, torch, rdkit and torch_geometric were installed. A
missing dependency in the deployment image was invisible to the whole suite.

So this test does not import the app the ordinary way. It runs it in a
subprocess with those modules BLOCKED at import, which is what the slim image
actually looks like, and drives a real request through the handler.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "runtime" / "model_assets" / "lean_decoder_v1.npz"

pytestmark = pytest.mark.skipif(
    not ARTIFACT.exists(),
    reason="lean artifact not built; run `python -m serving.precompute`",
)

# Runs inside the subprocess. Installs a meta-path hook that makes the heavy
# modules unimportable, then exercises the full request path.
PROBE = r'''
import sys, importlib.abc, importlib.machinery, json

BLOCKED = {"torch", "torch_geometric", "rdkit", "pandas", "sklearn", "scipy"}

class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        root = fullname.split(".")[0]
        if root in BLOCKED:
            raise ImportError(f"BLOCKED: {fullname} is not in the lean image")
        return None

sys.meta_path.insert(0, Blocker())
for name in list(sys.modules):
    if name.split(".")[0] in BLOCKED:
        del sys.modules[name]

import serving.api as api

api._startup()                      # loads the lean engine
health = api.health()
assert health["engine"] == "lean", health
assert health["model_available"] is True, health

resp = api.analyze(api.AnalyzeRequest(drug_a="DB00331", drug_b="DB00682"))

# Both refusals must be reached, not crash on the way.
from fastapi import HTTPException
codes = {}
for a, b, key in [("DB00331", "DB00331", "identical"), ("DB99999", "DB00682", "unknown")]:
    try:
        api.analyze(api.AnalyzeRequest(drug_a=a, drug_b=b))
        codes[key] = 200
    except HTTPException as exc:
        codes[key] = exc.status_code

loaded = sorted(m for m in sys.modules if m.split(".")[0] in BLOCKED)
print(json.dumps({
    "raw": resp.raw_model_score,
    "calibrated": resp.calibrated_model_score,
    "documented": resp.dataset_record.documented_in_frozen_dataset,
    "tag": resp.provenance.frozen_tag,
    "commit": resp.provenance.frozen_commit,
    "sha": resp.provenance.checkpoint_sha256,
    "codes": codes,
    "blocked_modules_loaded": loaded,
}))
'''


@pytest.fixture(scope="module")
def probe() -> dict:
    import json

    proc = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=ROOT, capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT), "DDINET_ENGINE": "lean",
             "HOME": str(Path.home())},
    )
    if proc.returncode != 0:
        pytest.fail(
            "lean request path failed with the heavy modules blocked — this is "
            f"exactly the production 500.\n\nSTDERR:\n{proc.stderr}"
        )
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_request_path_needs_no_heavy_dependency(probe):
    assert probe["blocked_modules_loaded"] == [], (
        "the request path imported a module the lean image does not have: "
        f"{probe['blocked_modules_loaded']}"
    )


def test_scores_match_the_reference_values(probe):
    assert probe["raw"] == pytest.approx(0.165018881, abs=1e-9)
    assert probe["calibrated"] == pytest.approx(0.443942295, abs=1e-9)
    assert probe["documented"] is False


def test_provenance_survives_without_pandas(probe):
    assert probe["tag"] == "v2-final-github-safe-2026-09-03"
    assert probe["commit"] == "92c481eeaba8faff991ced850e1c4de418ea31b0"
    assert probe["sha"].startswith("b828a471")


def test_refusals_are_reached_not_crashed(probe):
    assert probe["codes"]["identical"] == 422
    assert probe["codes"]["unknown"] == 404
