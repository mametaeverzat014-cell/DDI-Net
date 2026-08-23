"""
A polite, cached client for the PubChem PUG-REST API.

WHY RESOLVE STRUCTURES BY InChIKey AND NOT BY NAME
--------------------------------------------------
Drug-name matching is the single most common silent-corruption bug in
cheminformatics pipelines.  "Aspirin", "acetylsalicylic acid", "ASA",
"Aspirin 81mg", and "aspirin sodium" all refer to overlapping but different
things, and a name lookup will happily return the wrong compound - or a
formulation, or a salt - with a 200 OK and no warning.

The InChIKey is computed *from the structure itself*, so it is exact.  Where an
InChIKey is available (the DrugBank vocabulary provides one for nearly every
entry) we use it, and fall back to name lookup only when it is not - flagging
those rows so you can report the fraction resolved by the less reliable route.

SALT AND MIXTURE HANDLING
-------------------------
PubChem records frequently contain counter-ions (``.[Na+]``, ``.Cl``) or are
multi-component.  A fingerprint of "atorvastatin calcium" is not a fingerprint
of atorvastatin.  ``strip_salts`` keeps the largest organic fragment, which is
the standard normalisation.  Do this consistently or your identical-drug rows
will disagree between sources.

RATE LIMITING IS NOT OPTIONAL
-----------------------------
PubChem's published limits are 5 requests/second and 400/minute per IP; exceed
them and you get throttled or blocked, which for a shared school network is
inconsiderate as well as inconvenient.  ``_RateLimiter`` enforces the limit,
and every response is cached on disk so a second run of the pipeline makes zero
network calls.
"""

from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path

import requests

from .download import RAW_DIR, USER_AGENT

PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
CACHE_DIR = RAW_DIR / "pubchem" / "cache"

#: PubChem renamed this property in 2025; older servers only know the old name.
#: We ask for both and take whichever comes back.
_SMILES_PROPERTIES = ("ConnectivitySMILES", "CanonicalSMILES", "IsomericSMILES")


class _RateLimiter:
    """Sliding-window limiter: at most ``n`` events per ``window`` seconds."""

    def __init__(self, n: int, window: float) -> None:
        self.n = n
        self.window = window
        self._events: deque[float] = deque()

    def wait(self) -> None:
        now = time.monotonic()
        while self._events and now - self._events[0] > self.window:
            self._events.popleft()
        if len(self._events) >= self.n:
            time.sleep(self.window - (now - self._events[0]) + 0.01)
        self._events.append(time.monotonic())


def strip_salts(smiles: str) -> str:
    """Keep the largest dot-separated fragment (the parent drug).

    Deliberately implemented by heavy-atom count rather than string length, so
    that a long counter-ion SMILES cannot beat a compact drug.
    """
    if "." not in smiles:
        return smiles
    try:
        from rdkit import Chem

        fragments = [f for f in smiles.split(".") if f]
        mols = [(f, Chem.MolFromSmiles(f)) for f in fragments]
        valid = [(f, m) for f, m in mols if m is not None]
        if not valid:
            return smiles
        return max(valid, key=lambda fm: fm[1].GetNumHeavyAtoms())[0]
    except ImportError:
        return max(smiles.split("."), key=len)


class PubChemClient:
    """Cached, rate-limited PUG-REST client.

    Every distinct query is stored as a JSON file under ``data/raw/pubchem/cache``.
    That makes the pipeline reproducible offline and means a failed run costs
    nothing to resume.
    """

    def __init__(self, cache_dir: Path | None = None, *, offline: bool = False) -> None:
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.offline = offline
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        # Stay clearly inside both published limits.
        self._per_second = _RateLimiter(4, 1.0)
        self._per_minute = _RateLimiter(350, 60.0)
        self.n_requests = 0
        self.n_cache_hits = 0

    # -- caching -----------------------------------------------------------
    def _cache_path(self, key: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)[:120]
        return self.cache_dir / f"{safe}.json"

    def _get_json(self, url: str, cache_key: str) -> dict | None:
        path = self._cache_path(cache_key)
        if path.exists():
            self.n_cache_hits += 1
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError:
                path.unlink()  # corrupt cache entry; refetch

        if self.offline:
            return None

        self._per_second.wait()
        self._per_minute.wait()
        self.n_requests += 1
        try:
            resp = self.session.get(url, timeout=30)
        except requests.RequestException:
            return None

        if resp.status_code == 404:
            # A genuine "no such compound". Cache the negative result so we do
            # not ask again on every re-run.
            path.write_text(json.dumps({"_not_found": True}))
            return {"_not_found": True}
        if resp.status_code != 200:
            return None

        try:
            data = resp.json()
        except ValueError:
            return None
        path.write_text(json.dumps(data))
        return data

    # -- lookups -----------------------------------------------------------
    def properties_by_inchikey(self, inchikey: str) -> dict | None:
        """Exact structural lookup. The preferred route."""
        props = ",".join(_SMILES_PROPERTIES + ("MolecularFormula", "MolecularWeight", "InChIKey"))
        url = f"{PUBCHEM_BASE}/compound/inchikey/{inchikey}/property/{props}/JSON"
        data = self._get_json(url, f"ik_{inchikey}")
        return self._first_property(data)

    def properties_by_name(self, name: str) -> dict | None:
        """Fallback lookup. Ambiguous - flag anything resolved this way."""
        props = ",".join(_SMILES_PROPERTIES + ("MolecularFormula", "MolecularWeight", "InChIKey"))
        url = f"{PUBCHEM_BASE}/compound/name/{requests.utils.quote(name)}/property/{props}/JSON"
        data = self._get_json(url, f"name_{name.lower()}")
        return self._first_property(data)

    @staticmethod
    def _first_property(data: dict | None) -> dict | None:
        if not data or data.get("_not_found"):
            return None
        try:
            rows = data["PropertyTable"]["Properties"]
        except (KeyError, TypeError):
            return None
        if not rows:
            return None
        row = rows[0]
        smiles = next((row[p] for p in _SMILES_PROPERTIES if row.get(p)), "")
        return {
            "cid": row.get("CID"),
            "smiles": strip_salts(smiles) if smiles else "",
            "formula": row.get("MolecularFormula", ""),
            "molecular_weight": row.get("MolecularWeight", ""),
            "inchikey": row.get("InChIKey", ""),
        }

    def resolve(self, *, inchikey: str = "", name: str = "") -> dict | None:
        """Try InChIKey first, then name. Records which route succeeded."""
        if inchikey:
            got = self.properties_by_inchikey(inchikey)
            if got:
                got["resolved_by"] = "inchikey"
                return got
        if name:
            got = self.properties_by_name(name)
            if got:
                got["resolved_by"] = "name"  # less reliable - report the count
                return got
        return None

    def stats(self) -> str:
        total = self.n_requests + self.n_cache_hits
        rate = (self.n_cache_hits / total * 100) if total else 0.0
        return (
            f"PubChem: {self.n_requests} network requests, "
            f"{self.n_cache_hits} cache hits ({rate:.0f}% cached)"
        )
