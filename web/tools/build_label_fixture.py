"""Write web/src/pdf/__fixtures__/pair_synthetic_duplicated_labels.json.

SYNTHETIC TEST FIXTURE. The FDA label text comes from tests/synthetic_labels.py
(all-zero set IDs, "[synthetic]" in every sentence). Everything else is real
output of the local engine: DrugBank record, mechanism block, BIO-GINE model
block (lean engine, frozen checkpoint). The endpoint is "synthetic://", which
makes the PDF print a SYNTHETIC TEST DATA banner.

The file reproduces how the API answered before label excerpts were merged
across sections (one record per section, duplicates included), because that is
what an older deployment returns and the site must handle it. Run with
--merged for the current engine's answer.

    python web/tools/build_label_fixture.py [--merged]
"""
import datetime
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from synthetic_labels import FakeLabelTransport

from serving.evidence.adapters.http import HttpClient
from serving.evidence.engine import EvidenceEngine
from serving.evidence.store import EvidenceStore
from serving.lean import LeanEngine

merged = "--merged" in sys.argv
store = EvidenceStore.load(ROOT / "runtime/evidence/evidence_v1.json.gz")
engine = EvidenceEngine(store, model=LeanEngine(), http=HttpClient(transport=FakeLabelTransport(), enabled=True))
graph = engine.graph("DB00682", "DB00196").model_dump(mode="json")
report = engine.report("DB00682", "DB00196").model_dump(mode="json")
now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
meta = lambda path, body: {"endpoint": f"synthetic://local-engine-with-synthetic-labels{path}", "request": body, "receivedAt": now}
out = {
    "_comment": "SYNTHETIC TEST FIXTURE: FDA label sentences are synthetic (tests/synthetic_labels.py); DrugBank, mechanism and model blocks are real local-engine output. "
                + ("Excerpts merged across sections (current engine)." if merged else "One record per label section, duplicates included (engine before the merge)."),
    "report": {"meta": meta("/api/v3/report", {"drug_a": "DB00682", "drug_b": "DB00196", "include_labels": True}), "data": report},
    "graph": {"meta": meta("/api/v3/graph", {"drug_a": "DB00682", "drug_b": "DB00196"}), "data": graph},
}
name = "pair_synthetic_merged_labels.json" if merged else "pair_synthetic_duplicated_labels.json"
path = ROOT / "web/src/pdf/__fixtures__" / name
path.write_text(json.dumps(out, ensure_ascii=False, indent=1))
print(path, len(report["evidence"]), "evidence records,", report["evidence_status"])
