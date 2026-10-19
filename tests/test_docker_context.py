"""The Docker build context contains exactly what the Dockerfiles need.

Render builds from a git clone with the repository root as context. These tests
apply .dockerignore to the tracked files the way Docker does, then check both
directions:

* every COPY source of serving/Dockerfile and serving/Dockerfile.lean (except
  ``COPY --from=``) is tracked by git and survives .dockerignore — a missing
  file would fail the deploy;
* nothing outside the intended set is sent — no reports, paper, checkpoints,
  web sources beyond the one data file, or caches.

The matcher follows Docker's rules (moby patternmatcher): patterns are
evaluated in order, the last match wins, a ``!`` pattern re-includes, a
pattern matching a parent directory matches everything under it, and ``**``
matches any number of path segments. It was cross-checked against docker-py's
``exclude_paths`` on every tracked file when it was written.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILES = [ROOT / "serving" / "Dockerfile", ROOT / "serving" / "Dockerfile.lean"]


def _pattern_regex(pattern: str) -> re.Pattern:
    out, i = "", 0
    while i < len(pattern):
        c = pattern[i]
        if c == "*":
            if pattern[i:i + 2] == "**":
                # "**/" matches zero or more directories; "**" at the end anything.
                if pattern[i + 2:i + 3] == "/":
                    out += "(?:.*/)?"
                    i += 3
                    continue
                out += ".*"
                i += 2
                continue
            out += "[^/]*"
        elif c == "?":
            out += "[^/]"
        else:
            out += re.escape(c)
        i += 1
    return re.compile(f"^{out}$")


def load_patterns() -> list[tuple[bool, re.Pattern]]:
    pats = []
    for line in (ROOT / ".dockerignore").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        negate = line.startswith("!")
        p = line[1:] if negate else line
        p = p.strip().strip("/")
        p = re.sub(r"/+", "/", p)
        pats.append((negate, _pattern_regex(p)))
    return pats


def excluded(path: str, patterns) -> bool:
    parts = path.split("/")
    prefixes = ["/".join(parts[:k]) for k in range(1, len(parts) + 1)]
    result = False
    for negate, rx in patterns:
        if any(rx.match(p) for p in prefixes):
            result = not negate
    return result


def tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return [p for p in out.decode().split("\0") if p]


def context_files() -> set[str]:
    pats = load_patterns()
    return {p for p in tracked() if not excluded(p, pats)}


def copy_sources(dockerfile: Path) -> list[str]:
    srcs = []
    text = re.sub(r"\\\n", " ", dockerfile.read_text())
    for line in text.splitlines():
        line = line.strip()
        if not line.upper().startswith(("COPY ", "ADD ")):
            continue
        args = line.split()[1:]
        if any(a.startswith("--from") for a in args):
            continue
        args = [a for a in args if not a.startswith("--")]
        srcs += args[:-1]
    return srcs


def test_every_copy_source_is_tracked_and_survives_dockerignore():
    ctx = context_files()
    for df in DOCKERFILES:
        for src in copy_sources(df):
            s = src.rstrip("/")
            if src.endswith("/"):
                inside = [p for p in ctx if p.startswith(s + "/")]
                assert inside, f"{df.name}: COPY {src} would copy nothing"
                in_git = [p for p in tracked() if p.startswith(s + "/") and "__pycache__" not in p]
                assert set(in_git) <= ctx, f"{df.name}: COPY {src} would miss {sorted(set(in_git) - ctx)[:5]}"
            else:
                assert s in ctx, f"{df.name}: COPY {src} is not in the build context"


def test_inference_inputs_are_in_the_context():
    """What the build stage reads at run time, beyond the COPY lines themselves."""
    import json

    ctx = context_files()
    manifest = json.loads((ROOT / "serving" / "frozen_manifest.json").read_text())
    for rel in [*manifest["modules"], *manifest["data"], *manifest["vendored_artifacts"]]:
        assert rel in ctx, f"integrity-checked file {rel} missing from the build context"
    for rel in ("data/raw/drugbank.tab.gz", "web/public/data/drugs.json",
                "data/mechanism_v1/split_assignments.csv", "serving/requirements.txt",
                "serving/requirements-lean.txt"):
        assert rel in ctx, rel


def test_nothing_else_is_sent():
    allowed_roots = ("serving/", "src/", "data/mechanism_v1/")
    allowed_files = {"data/raw/drugbank.tab.gz", "web/public/data/drugs.json"}
    stray = [p for p in context_files() if not p.startswith(allowed_roots) and p not in allowed_files]
    assert not stray, f"unexpected files in the build context: {stray[:10]}"
    pats = load_patterns()
    for p in ("runtime/model_assets/bd45f84e3c1b2c33.pt", "web/node_modules/x/index.js",
              "serving/__pycache__/api.cpython-311.pyc", "reports/v3_seed_disagreement.json",
              "paper/DDI_NET_ISEF_RESEARCH_PAPER.md", ".git/config", "web/src/App.tsx",
              "data/raw/sider/meddra_all_se.tsv.gz",
              # licence-restricted local research data never reaches an image
              "data/restricted/crescenddi/crescenddi_index_v1.json.gz",
              "data/reference_sets/crescenddi/MANIFEST.json"):
        assert excluded(p, pats), f"{p} would be sent to the builder"


def test_no_dockerfile_copies_restricted_data():
    for df in DOCKERFILES:
        for src in copy_sources(df):
            assert not src.startswith(("data/restricted", "data/reference_sets")), f"{df.name}: COPY {src}"


def test_context_is_small():
    size = sum((ROOT / p).stat().st_size for p in context_files())
    assert size < 25 * 1024 * 1024, f"build context is {size / 2**20:.1f} MiB"
