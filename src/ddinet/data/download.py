"""
A cache-first, integrity-checking downloader for the sources in ``sources.py``.

DESIGN NOTES YOU SHOULD BE ABLE TO DEFEND
-----------------------------------------
*Cache-first.*  Every file is stored under ``data/raw/<source_key>/`` and is
never re-fetched if it is already present and passes its integrity check.  This
matters for more than speed: SIDER and DDInter are small academic servers, and
hammering them during development is bad citizenship.  It also means your
results stay reproducible when you re-run the pipeline the night before the
fair on flaky hotel wifi.

*Integrity, not just status codes.*  A surprising failure mode on academic hosts
is a ``200 OK`` that serves an HTML "file moved" page instead of the data.  If
you only check ``response.status_code`` you get a 3 KB "CSV" full of ``<html>``
and a very confusing traceback three modules later.  ``_looks_like_html`` catches
this at the download boundary, where the error message can be useful.

*Retry only what is retryable.*  Connection resets and 5xx errors are transient
- retry with exponential backoff.  A 403/407 is a *policy* decision (your
network blocks the host, or the resource needs a licence); retrying it is futile
and, on a managed network, rude.  These raise immediately with an actionable
message.

*Hashes recorded, not enforced by default.*  On first download we record the
SHA-256 into ``data/raw/manifest.json``.  On later runs a mismatch is reported
loudly.  We do not hard-fail by default because upstream releases legitimately
change - but you want to KNOW, because "my numbers changed and I don't know why"
is the worst possible position to be in during judging.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import shutil
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import requests

from .sources import Source

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

#: Project root = three levels up from this file (src/ddinet/data/download.py).
PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
MANIFEST_PATH = RAW_DIR / "manifest.json"

#: Identify ourselves. Academic hosts appreciate a contactable UA string, and
#: some reject the default python-requests UA outright.
USER_AGENT = (
    "DDI-Net/0.1 (student research project; "
    "https://github.com/mametaeverzat014-cell/DDI-Net)"
)


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------

class DownloadError(RuntimeError):
    """Base class for every failure this module raises."""


class NetworkPolicyError(DownloadError):
    """The host was refused by a proxy or by the provider (HTTP 403/407).

    This is deliberately a distinct exception type. It means "you cannot get
    this file from *this machine*", which is a completely different problem
    from "the file is corrupt" - and it has a completely different fix
    (download elsewhere, or ask for the host to be allowed).
    """


class ManualDownloadRequired(DownloadError):
    """The source needs a human: an account, a signed licence, or a click."""


class IntegrityError(DownloadError):
    """The downloaded bytes are not what we expected."""


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def sha256_of(path: Path, chunk_size: int = 1 << 20) -> str:
    """Streaming SHA-256 so we never load a multi-GB file into memory."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def _looks_like_html(path: Path, probe_bytes: int = 2048) -> bool:
    """Heuristic: did we get an error page instead of the data file?

    We only probe the first couple of kB, and we bail out immediately for
    formats whose magic bytes we recognise (gzip ``1f 8b``, zip ``PK``), because
    a compressed file can legitimately contain the byte sequence ``<html``.
    """
    with path.open("rb") as fh:
        head = fh.read(probe_bytes)
    if head[:2] in (b"\x1f\x8b", b"PK"):
        return False
    lowered = head.lower()
    return b"<!doctype html" in lowered or b"<html" in lowered


def _is_policy_refusal(exc: Exception) -> bool:
    """Does this proxy error carry a 403/407, i.e. a policy denial?

    ``requests`` flattens the proxy's CONNECT response into the exception text
    ("Tunnel connection failed: 403 Forbidden"), so string inspection is the
    only handle we have. Narrow, and correct for every proxy we have seen.
    """
    text = str(exc)
    return bool(re.search(r"\b(403|407)\b", text)) and "tunnel" in text.lower()


def _load_manifest() -> dict[str, dict]:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {}


def _save_manifest(manifest: dict[str, dict]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True))


@dataclass
class DownloadResult:
    """What happened, so callers and logs can be precise about it."""

    source_key: str
    path: Path
    sha256: str
    n_bytes: int
    from_cache: bool

    def __str__(self) -> str:
        origin = "cached" if self.from_cache else "downloaded"
        return (
            f"{self.source_key}: {origin} {self.path.name} "
            f"({self.n_bytes / 1e6:.1f} MB, sha256={self.sha256[:12]}...)"
        )


# --------------------------------------------------------------------------
# The download primitive
# --------------------------------------------------------------------------

def fetch_url(
    url: str,
    dest: Path,
    *,
    max_retries: int = 4,
    timeout: int = 120,
    session: requests.Session | None = None,
) -> Path:
    """Download ``url`` to ``dest``, atomically, with sane retries.

    Atomicity matters: we stream into ``dest.with_suffix('.part')`` and only
    ``rename`` on success. A rename within one filesystem is atomic, so an
    interrupted download can never leave a half-file that the cache check would
    later accept as valid.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    sess = session or requests.Session()
    delay = 2.0
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            with sess.get(
                url,
                stream=True,
                timeout=timeout,
                headers={"User-Agent": USER_AGENT},
                allow_redirects=True,
            ) as resp:
                # --- Policy failures: do not retry, explain instead. --------
                if resp.status_code in (403, 407):
                    raise NetworkPolicyError(
                        f"HTTP {resp.status_code} for {url}\n"
                        f"  The host was refused by an egress proxy or by the "
                        f"provider.\n"
                        f"  This is a network-policy decision, not a transient "
                        f"error - retrying will not help.\n"
                        f"  Fix: run this download from an unrestricted network "
                        f"(your own laptop or school machine), then copy the file "
                        f"to {dest.parent}/ ."
                    )
                if resp.status_code == 404:
                    raise DownloadError(
                        f"HTTP 404 for {url}\n"
                        f"  Academic download URLs drift. Open the source's "
                        f"landing page (see sources.py) and update the URL."
                    )
                resp.raise_for_status()

                with tmp.open("wb") as fh:
                    for chunk in resp.iter_content(chunk_size=1 << 16):
                        if chunk:
                            fh.write(chunk)

            # --- Content sanity check ----------------------------------
            if tmp.stat().st_size == 0:
                raise IntegrityError(f"Empty file downloaded from {url}")
            if _looks_like_html(tmp):
                raise IntegrityError(
                    f"{url} returned an HTML page, not a data file.\n"
                    f"  This usually means the URL moved or a login wall was hit."
                )

            tmp.replace(dest)
            return dest

        except (NetworkPolicyError, ManualDownloadRequired):
            tmp.unlink(missing_ok=True)
            raise
        except requests.exceptions.ProxyError as exc:
            # A restricted network refuses the CONNECT tunnel *before* any HTTP
            # response exists, so the 403/407 never reaches the branch above -
            # it arrives wrapped in a ProxyError instead. Same policy meaning,
            # same "do not retry" conclusion, so translate and re-raise.
            tmp.unlink(missing_ok=True)
            if _is_policy_refusal(exc):
                raise NetworkPolicyError(
                    f"Proxy refused the tunnel to {url}\n"
                    f"  Underlying error: {exc}\n"
                    f"  Your network's egress policy does not allow this host. "
                    f"This is not transient - retrying will not help.\n"
                    f"  Fix: run `python scripts/01_download_data.py` from an "
                    f"unrestricted network, then copy data/raw/ across."
                ) from exc
            last_error = exc
            if attempt == max_retries:
                break
            time.sleep(delay)
            delay *= 2
        except (requests.RequestException, IntegrityError) as exc:
            last_error = exc
            tmp.unlink(missing_ok=True)
            if attempt == max_retries:
                break
            time.sleep(delay)
            delay *= 2  # 2s, 4s, 8s

    raise DownloadError(f"Failed to download {url} after {max_retries} attempts: {last_error}")


# --------------------------------------------------------------------------
# Source-aware entry point
# --------------------------------------------------------------------------

def ensure_source(
    src: Source,
    *,
    force: bool = False,
    session: requests.Session | None = None,
) -> DownloadResult:
    """Guarantee that ``src``'s file exists locally, downloading if needed.

    Raises ``ManualDownloadRequired`` (with instructions) for licence-gated
    sources rather than pretending they can be automated.
    """
    if src.filename is None or src.url is None:
        raise ManualDownloadRequired(
            f"'{src.key}' cannot be downloaded automatically.\n"
            f"  Access mode : {src.access}\n"
            f"  Licence     : {src.licence}\n"
            f"  Get it from : {src.landing_page}\n"
            f"  Then place the file at: data/raw/{src.key}/{src.filename or '<file>'}\n"
            f"  Notes       : {src.notes}"
        )

    dest = RAW_DIR / src.key / src.filename
    manifest = _load_manifest()

    if dest.exists() and not force:
        digest = sha256_of(dest)
        recorded = manifest.get(src.key, {}).get("sha256")
        if recorded and recorded != digest:
            print(
                f"  [warn] {src.key}: local file hash differs from the manifest.\n"
                f"         recorded={recorded[:12]}... actual={digest[:12]}...\n"
                f"         Either the upstream release changed or the file is "
                f"damaged. Re-run with force=True to refetch."
            )
        return DownloadResult(src.key, dest, digest, dest.stat().st_size, from_cache=True)

    fetch_url(src.url, dest, session=session)
    digest = sha256_of(dest)

    if src.sha256 and src.sha256 != digest:
        raise IntegrityError(
            f"{src.key}: expected sha256 {src.sha256}, got {digest}. "
            f"The upstream file changed - update sources.py deliberately."
        )

    manifest[src.key] = {
        "filename": src.filename,
        "sha256": digest,
        "n_bytes": dest.stat().st_size,
        "url": src.url,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "licence": src.licence,
    }
    _save_manifest(manifest)

    return DownloadResult(src.key, dest, digest, dest.stat().st_size, from_cache=False)


# --------------------------------------------------------------------------
# Decompression helpers - kept here so parsers stay format-agnostic
# --------------------------------------------------------------------------

def open_maybe_gzip(path: Path, encoding: str = "utf-8") -> io.TextIOBase:
    """Open a text file transparently, whether or not it is gzipped.

    Decided by magic bytes rather than by file extension, because more than one
    academic host serves ``.tsv`` files that are actually gzip.
    """
    with path.open("rb") as fh:
        magic = fh.read(2)
    if magic == b"\x1f\x8b":
        return gzip.open(path, "rt", encoding=encoding, errors="replace")
    return path.open("rt", encoding=encoding, errors="replace")


def extract_single_csv_from_zip(zip_path: Path, dest_dir: Path) -> Path:
    """Pull the one CSV out of a ZIP archive and return its path.

    Written defensively for the DrugBank vocabulary ZIP, whose inner file has
    historically been named ``drugbank vocabulary.csv`` - with a space, which
    is exactly the kind of thing that breaks a hard-coded path six months later.
    We glob instead.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        csvs = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if len(csvs) != 1:
            raise IntegrityError(
                f"Expected exactly one CSV inside {zip_path.name}, found {csvs}"
            )
        inner = csvs[0]
        out = dest_dir / Path(inner).name.replace(" ", "_")
        with zf.open(inner) as src_fh, out.open("wb") as dst_fh:
            shutil.copyfileobj(src_fh, dst_fh)
    return out
