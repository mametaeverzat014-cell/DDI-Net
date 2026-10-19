"""Fetch named files from a public git repository at a pinned commit.

Used for the evidence-layer reference sets (CRESCENDDI, the DDI Corpus), whose
canonical copies are files in public GitHub repositories. The build container
can reach GitHub over git but not the providers' other hosts, so this is the
only reproducible route here.

* **Pinned commit.** A moving branch would let the data change under the same
  name. The commit is part of the manifest, and `checkout` refuses any other.
* **Checksums enforced.** Every expected file has a SHA-256 in the caller's
  manifest. A mismatch raises; there is no "warn and continue" mode, because a
  silently different reference set changes every number measured on it.
* **Cache.** Files land in ``data/raw/<key>/<commit>/`` (git-ignored, never
  committed). An existing file that passes its checksum is not fetched again.
* **Untrusted content.** Nothing fetched is executed or imported; parsers read
  the files as data.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw"


class FetchError(RuntimeError):
    """The files could not be fetched, or they are not the files expected."""


@dataclass(frozen=True)
class PinnedFiles:
    key: str                    #: cache directory name under data/raw/
    repo_url: str               #: https URL of the public repository
    commit: str                 #: full 40-character commit SHA
    files: dict[str, str]       #: repository path -> expected SHA-256

    def cache_dir(self, root: Path = RAW) -> Path:
        return root / self.key / self.commit


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(spec: PinnedFiles, directory: Path) -> dict[str, str]:
    """Check every expected file under ``directory``; return path -> sha256."""
    out: dict[str, str] = {}
    problems: list[str] = []
    for rel, expected in spec.files.items():
        p = directory / rel
        if not p.is_file():
            problems.append(f"missing: {rel}")
            continue
        got = sha256_file(p)
        if got != expected:
            problems.append(f"checksum mismatch: {rel} (expected {expected}, got {got})")
        out[rel] = got
    if problems:
        raise FetchError(f"{spec.key} @ {spec.commit[:12]}: " + "; ".join(problems))
    return out


def _git(args: list[str], cwd: Path) -> None:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        raise FetchError(f"git {' '.join(args[:2])} failed: {r.stderr.strip()[:400]}")


def fetch(spec: PinnedFiles, root: Path = RAW) -> Path:
    """Return a directory holding the verified files, fetching them if needed."""
    dest = spec.cache_dir(root)
    try:
        verify(spec, dest)
        return dest
    except FetchError:
        pass
    if len(spec.commit) != 40:
        raise FetchError(f"{spec.key}: commit must be a full SHA, got {spec.commit!r}")
    with tempfile.TemporaryDirectory(prefix=f"{spec.key}-") as tmp:
        work = Path(tmp)
        _git(["init", "-q"], work)
        _git(["remote", "add", "origin", spec.repo_url], work)
        # Blob-less fetch of the one commit, then check out only the files named.
        _git(["fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", spec.commit], work)
        _git(["checkout", "-q", spec.commit, "--", *spec.files], work)
        verify(spec, work)
        for rel in spec.files:
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(work / rel, target)
    verify(spec, dest)
    return dest
