"""The frozen BIO-GINE module, loaded from a vendored byte-identical copy.

WHY. Research continues in ``src/ddinet/models/bio_gine.py``: Candidate A
(911bed9) and the fingerprint baseline (aa04493) added flags to it. Each was
built to reproduce V2 exactly at its defaults, but the integrity gate checks
bytes, not intentions, and correctly refused to serve once the file changed —
which also broke ``serving/Dockerfile.lean`` at its ``precompute`` step.

Inference must run the code that produced the frozen results, and research
must stay free to change ``src/``. So serving imports a vendored copy of the
module as it stood at the frozen tag. Its SHA-256 is the frozen one
(``serving/frozen_manifest.json``, ``modules``), checked by
``integrity.verify_sources()`` before the first score and again here before
the file is executed.

The copy uses relative imports (``from .encoders import ...``). It is loaded
under the name ``ddinet.models.bio_gine_frozen`` so those resolve inside the
``ddinet.models`` package — to ``encoders.py`` and ``data/biology.py``, which
are themselves hash-checked against the tag.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDORED = ROOT / "serving" / "frozen_artifacts" / "bio_gine.py"
MODULE_NAME = "ddinet.models.bio_gine_frozen"


def _expected_sha() -> str:
    manifest = json.loads((ROOT / "serving" / "frozen_manifest.json").read_text())
    return manifest["modules"]["serving/frozen_artifacts/bio_gine.py"]


def load():
    if MODULE_NAME in sys.modules:
        return sys.modules[MODULE_NAME]
    blob = VENDORED.read_bytes()
    actual = hashlib.sha256(blob).hexdigest()
    expected = _expected_sha()
    if actual != expected:
        raise RuntimeError(
            f"vendored frozen bio_gine.py differs from the frozen tag\n"
            f"  expected {expected}\n  actual   {actual}")
    if str(ROOT / "src") not in sys.path:
        sys.path.insert(0, str(ROOT / "src"))
    import ddinet.models  # noqa: F401  — parent package must exist first

    spec = importlib.util.spec_from_file_location(MODULE_NAME, VENDORED)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module
