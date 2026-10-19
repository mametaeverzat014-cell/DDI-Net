"""The DDI-Net 3.0 numbers on the site equal the reports, and the reports equal
a fresh recomputation. Same discipline as tests/test_site_numbers.py: a number
shown to a reader must be traceable to code that reproduces it.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from serving.evidence.direction import audit

from test_v3_evidence import real, real_artifact  # noqa: F401  (session fixtures)

ROOT = Path(__file__).resolve().parents[1]


def _tool():
    spec = importlib.util.spec_from_file_location("build_v3_facts", ROOT / "web" / "tools" / "build_v3_facts.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_site_facts_equal_a_fresh_regeneration():
    committed = json.loads((ROOT / "web" / "src" / "data" / "v3facts.json").read_text())
    assert committed == _tool().build(), "run: python3 web/tools/build_v3_facts.py"


def test_direction_report_equals_the_audit_the_api_applies(real):  # noqa: F811
    report = json.loads((ROOT / "reports" / "v3_tdc_direction_audit.json").read_text())
    fresh = audit(real)
    assert set(report["pk_types"]) == {str(y) for y in fresh}
    for y, row in fresh.items():
        r = report["pk_types"][str(y)]
        for k in ("n_informative", "n_consistent", "n_reversed", "consistency"):
            assert r[k] == row[k], (y, k)
    assert report["n_records"] == sum(len(v) for v in real.records.values())
    # The artifact the API serves carries the same table.
    assert {int(k): v for k, v in report["pk_types"].items()}.keys() == real.direction_audit.keys()
