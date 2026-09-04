"""Integrity gate for frozen inference.

Nothing here is a formality. The V2 result is only reproducible if the weights,
the code that interprets them, and the data they were fitted against are all the
ones that were frozen. This module asserts that before a single number is
served, and refuses loudly rather than returning a plausible wrong score.

Three things are checked against serving/frozen_manifest.json, whose hashes were
read from the tag v2-final-github-safe-2026-09-03:

1. the checkpoint file's SHA-256,
2. the SHA-256 of every source module the inference path imports,
3. the SHA-256 of every mechanism_v1 data file the model is keyed on.

Point 2 matters more than it looks. The working branch is NOT a descendant of
the frozen commit: `git merge-base --is-ancestor 92c481e HEAD` is false, and the
working tree is missing ~5,650 lines that exist at the tag. The five modules the
inference path needs happen to be byte-identical today; this check is what keeps
that a fact rather than an assumption.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = Path(__file__).resolve().parent / "frozen_manifest.json"

#: Where the checkpoint is expected once fetched from the GitHub Release.
#: Gitignored — an 18 MB binary is distributed by Release, not by git history.
CHECKPOINT_PATH = ROOT / "runtime" / "model_assets" / "bd45f84e3c1b2c33.pt"


class IntegrityError(RuntimeError):
    """Raised when a frozen artifact does not match its recorded hash."""


@dataclass(frozen=True)
class IntegrityReport:
    checkpoint_sha256: str
    modules_checked: int
    data_files_checked: int
    frozen_tag: str
    frozen_commit: str


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text())


def verify_checkpoint(path: Path | None = None) -> str:
    """Return the checkpoint's SHA-256, raising if it is missing or wrong."""
    manifest = load_manifest()
    path = path or CHECKPOINT_PATH
    expected = manifest["checkpoint"]["sha256"]
    if not path.exists():
        raise IntegrityError(
            f"Frozen checkpoint not found at {path}.\n"
            f"Fetch it from the GitHub Release {manifest['checkpoint']['release_tag']}:\n"
            f"  curl -sSL -o {path} \\\n"
            f"    https://github.com/mametaeverzat014-cell/DDI-Net/releases/download/"
            f"{manifest['checkpoint']['release_tag']}/{manifest['checkpoint']['filename']}"
        )
    actual = sha256_file(path)
    if actual != expected:
        raise IntegrityError(
            "Checkpoint SHA-256 mismatch — refusing to run inference.\n"
            f"  expected {expected}\n  actual   {actual}\n"
            "The file is not the frozen seed-0 BIO-GINE M4 checkpoint."
        )
    return actual


def verify_sources() -> tuple[int, int]:
    """Check every module and data file the inference path depends on."""
    manifest = load_manifest()
    bad: list[str] = []
    for group in ("modules", "data"):
        for rel, expected in manifest[group].items():
            path = ROOT / rel
            if not path.exists():
                bad.append(f"{rel}: missing")
                continue
            actual = sha256_file(path)
            if actual != expected:
                bad.append(f"{rel}: expected {expected[:16]}…, got {actual[:16]}…")
    # Vendored copies of frozen artifacts: same rule, one indirection deeper.
    for rel, meta in manifest.get("vendored_artifacts", {}).items():
        path = ROOT / rel
        if not path.exists():
            bad.append(f"{rel}: missing")
            continue
        actual = sha256_file(path)
        if actual != meta["sha256"]:
            bad.append(
                f"{rel}: vendored copy differs from {meta['copied_from']} at the tag"
            )
    if bad:
        raise IntegrityError(
            "Working copy has drifted from the frozen tag "
            f"{manifest['frozen_tag']}; inference would not reproduce the "
            "published results:\n  " + "\n  ".join(bad)
        )
    return len(manifest["modules"]), len(manifest["data"]) + len(
        manifest.get("vendored_artifacts", {})
    )


def verify_all(checkpoint: Path | None = None) -> IntegrityReport:
    manifest = load_manifest()
    sha = verify_checkpoint(checkpoint)
    n_mod, n_data = verify_sources()
    return IntegrityReport(
        checkpoint_sha256=sha,
        modules_checked=n_mod,
        data_files_checked=n_data,
        frozen_tag=manifest["frozen_tag"],
        frozen_commit=manifest["frozen_commit"],
    )
