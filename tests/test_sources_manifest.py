"""The evidence-source manifest is complete, consistent and matches what is on disk."""

from __future__ import annotations

import json
from pathlib import Path

from ddinet.data.git_fetch import sha256_file

ROOT = Path(__file__).resolve().parents[1]
M = json.loads((ROOT / "data" / "sources_manifest.json").read_text())
STATUSES = {"integrated", "evaluation_only", "accepted_not_integrated", "requires_permission", "rejected", "already_present"}


def test_every_source_is_described():
    keys = [s["key"] for s in M["sources"]]
    assert len(keys) == len(set(keys))
    for s in M["sources"]:
        assert s["status"] in STATUSES, s["key"]
        assert s["licence_verified"] in ("direct", "search_excerpt", "not_verified"), s["key"]
        for f in ("name", "provider", "url", "licence", "content", "identifiers"):
            assert s.get(f), (s["key"], f)
        if s["status"] in ("accepted_not_integrated", "requires_permission", "rejected"):
            assert s.get("reason"), s["key"]


def test_integrated_sources_have_a_verified_licence_and_a_checked_manifest():
    for s in M["sources"]:
        if s["status"] != "integrated":
            continue
        assert s["licence_verified"] == "direct", s["key"]
        man = json.loads((ROOT / s["manifest"]).read_text())
        assert man["source"]["commit"] == s["pinned_commit"]
        out = ROOT / s["local"] / man["output"]["file"]
        assert sha256_file(out) == man["output"]["sha256"]


def test_evaluation_only_data_is_never_committed():
    import subprocess
    tracked = subprocess.run(["git", "ls-files", "data/raw"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    assert all(not p.startswith(("data/raw/ddi_corpus", "data/raw/crescenddi")) for p in tracked)
    assert "data/raw/drugbank.tab.gz" in tracked or not tracked
    s = next(x for x in M["sources"] if x["key"] == "tdc_drugbank")
    assert sha256_file(ROOT / s["local"]) == s["sha256"]
