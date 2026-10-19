"""The vendored frozen bio_gine.py is the tag's module, byte for byte.

serving/frozen_model.py exists so research can change src/ddinet/models/bio_gine.py
without changing what inference runs. That only holds while the vendored copy is
exactly the frozen one; these tests pin it from two independent directions.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VENDORED = ROOT / "serving" / "frozen_artifacts" / "bio_gine.py"
TAG = "v2-final-github-safe-2026-09-03"


def test_vendored_hash_is_the_manifest_hash():
    manifest = json.loads((ROOT / "serving" / "frozen_manifest.json").read_text())
    expected = manifest["modules"]["serving/frozen_artifacts/bio_gine.py"]
    assert hashlib.sha256(VENDORED.read_bytes()).hexdigest() == expected
    assert manifest["vendored_modules"]["serving/frozen_artifacts/bio_gine.py"]["copied_from"] \
        == "src/ddinet/models/bio_gine.py"


def test_vendored_bytes_equal_the_tag():
    probe = subprocess.run(["git", "rev-parse", "-q", "--verify", f"refs/tags/{TAG}"],
                           cwd=ROOT, capture_output=True)
    if probe.returncode != 0:
        pytest.skip(f"tag {TAG} not fetched (git fetch origin tag {TAG})")
    at_tag = subprocess.run(["git", "show", f"{TAG}:src/ddinet/models/bio_gine.py"],
                            cwd=ROOT, capture_output=True, check=True).stdout
    assert VENDORED.read_bytes() == at_tag


def test_engine_builds_the_model_from_the_vendored_module():
    pytest.importorskip("torch")
    pytest.importorskip("torch_geometric")
    from serving import frozen_model

    mod = frozen_model.load()
    assert mod.__name__ == "ddinet.models.bio_gine_frozen"
    assert Path(mod.__file__).resolve() == VENDORED.resolve()
