"""
Parser for SIDER 4.1 - side-effect profiles as a phenotypic drug feature.

WHY ADD SIDE EFFECTS TO A STRUCTURE-BASED MODEL
-----------------------------------------------
Two drugs that share a side-effect profile often share a biological target or
a metabolic route, even when their structures look nothing alike.  Structure
tells you what a molecule *is*; the side-effect profile tells you what it
*does* in a human body.  These are complementary views, and the second one
captures effects (idiosyncratic toxicity, off-target activity) that no
fingerprint can encode.

This is the same intuition behind Zitnik et al.'s Decagon: side effects are a
usable proxy for shared pharmacology.

WHAT IT COSTS YOU - BE HONEST ABOUT THIS
----------------------------------------
1. **Coverage.**  SIDER covers roughly 1,400 drugs.  Anything newer, or never
   marketed in a region with public labelling, has no profile.  Missing rows
   must be an explicit zero vector plus a "has_sider" indicator flag - never
   silently imputed, or the model learns "no data" as a feature.

2. **Circularity risk.**  SIDER is derived from drug *labels*, and labels list
   adverse effects that sometimes arose from known interactions.  There is a
   real possibility of label leakage.  Mitigation: report performance with and
   without SIDER features (Step 4 does this as an ablation).  If SIDER helps
   enormously in S1 but not at all in S3, that is a leak, not a signal.

3. **It kills the S3 setting.**  A genuinely new drug has no side-effect
   profile, so SIDER features are unavailable exactly when you need the model
   most.  This is the strongest argument for keeping structure as the primary
   representation and SIDER as an optional auxiliary.

STITCH IDENTIFIERS
------------------
SIDER labels compounds with STITCH ids like ``CID100002244``.  The scheme is
``CID`` + one flag digit + a zero-padded PubChem CID.  Flag ``1`` = the
stereo-specific compound, ``0`` = the flat/parent compound.  Stripping the
prefix and leading zeros recovers the PubChem CID, which is how we join to
structures.

.. NOTE:: UNUSED AS OF 2026-08-24.

   This module is not part of the Phase A pipeline. Data now comes from the TDC
   DrugBank export via ``ddinet.data.tdc_drugbank``.

   It is retained rather than deleted because two things the Phase A/B plan
   needs are absent from the TDC export: CYP450 substrate/inhibitor/inducer
   annotations (required for Phase B) and clinical severity grades. If those
   turn out to be needed, these parsers are already written and tested. The
   decision to delete is deferred until that is settled - see
   DATA_PROVENANCE.md section 3.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from .download import RAW_DIR, open_maybe_gzip
from .sources import SIDER, SIDER_ATC, SIDER_NAMES

_STITCH_RE = re.compile(r"^CID([01])(\d+)$")


def stitch_to_pubchem_cid(stitch_id: str) -> int | None:
    """``'CID100002244'`` -> ``2244``. Returns ``None`` if unparseable."""
    m = _STITCH_RE.match((stitch_id or "").strip())
    if not m:
        return None
    return int(m.group(2))


def load_side_effects(path: Path | None = None) -> pd.DataFrame:
    """Load ``meddra_all_se.tsv(.gz)``.

    The file has no header. Columns are:
      0 STITCH flat id, 1 STITCH stereo id, 2 UMLS concept id (label),
      3 MedDRA concept type, 4 UMLS concept id (MedDRA), 5 side-effect name

    We keep only ``PT`` (Preferred Term) rows.  MedDRA is hierarchical: ``LLT``
    (Lowest Level Term) rows are near-duplicates of their PT parent, so keeping
    both would double-count the same side effect and distort the feature vector.
    """
    path = path or (RAW_DIR / SIDER.key / SIDER.filename)
    if not path.exists():
        raise FileNotFoundError(f"SIDER file not found at {path}")

    rows = []
    with open_maybe_gzip(path) as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 6:
                continue
            if parts[3].strip().upper() != "PT":
                continue
            rows.append((parts[0].strip(), parts[4].strip(), parts[5].strip().lower()))

    df = pd.DataFrame(rows, columns=["stitch_id", "umls_id", "side_effect"])
    df["pubchem_cid"] = df["stitch_id"].map(stitch_to_pubchem_cid)
    return df.drop_duplicates().reset_index(drop=True)


def load_drug_names(path: Path | None = None) -> pd.DataFrame:
    """Two-column, header-less ``drug_names.tsv``: STITCH id, name."""
    path = path or (RAW_DIR / SIDER_NAMES.key / SIDER_NAMES.filename)
    df = pd.read_csv(path, sep="\t", header=None, names=["stitch_id", "name"], dtype=str)
    df["name"] = df["name"].str.strip().str.lower()
    df["pubchem_cid"] = df["stitch_id"].map(stitch_to_pubchem_cid)
    return df


def load_atc(path: Path | None = None) -> pd.DataFrame:
    """Header-less ``drug_atc.tsv``: STITCH id, ATC code."""
    path = path or (RAW_DIR / SIDER_ATC.key / SIDER_ATC.filename)
    df = pd.read_csv(path, sep="\t", header=None, names=["stitch_id", "atc_code"], dtype=str)
    df["pubchem_cid"] = df["stitch_id"].map(stitch_to_pubchem_cid)
    return df


def build_side_effect_matrix(
    side_effects: pd.DataFrame,
    drug_keys: list[str],
    key_to_cid: dict[str, int],
    *,
    min_frequency: int = 5,
) -> tuple[np.ndarray, list[str], np.ndarray]:
    """Build a binary drug x side-effect matrix.

    Returns ``(matrix, side_effect_vocabulary, has_profile_mask)``.

    ``min_frequency`` drops side effects seen in fewer than N drugs.  Rare
    terms are mostly transcription noise from individual labels; keeping them
    inflates dimensionality (SIDER has ~5,800 PT terms) without adding signal,
    and in a small-sample regime that is a direct route to overfitting.

    ``has_profile_mask`` is returned separately and MUST be used as an explicit
    feature.  Without it, "all zeros because no SIDER record" is indistinguishable
    from "all zeros because this drug has no reported side effects", and those
    mean opposite things.
    """
    cid_to_effects: dict[int, set[str]] = {}
    for cid, effect in zip(side_effects["pubchem_cid"], side_effects["side_effect"]):
        if cid is None or (isinstance(cid, float) and np.isnan(cid)):
            continue
        cid_to_effects.setdefault(int(cid), set()).add(effect)

    counts: dict[str, int] = {}
    for key in drug_keys:
        cid = key_to_cid.get(key)
        if cid is None:
            continue
        for effect in cid_to_effects.get(int(cid), ()):
            counts[effect] = counts.get(effect, 0) + 1

    vocab = sorted(e for e, c in counts.items() if c >= min_frequency)
    index = {e: i for i, e in enumerate(vocab)}

    matrix = np.zeros((len(drug_keys), len(vocab)), dtype=np.float32)
    has_profile = np.zeros(len(drug_keys), dtype=np.float32)
    for row, key in enumerate(drug_keys):
        cid = key_to_cid.get(key)
        if cid is None:
            continue
        effects = cid_to_effects.get(int(cid))
        if not effects:
            continue
        has_profile[row] = 1.0
        for effect in effects:
            j = index.get(effect)
            if j is not None:
                matrix[row, j] = 1.0

    return matrix, vocab, has_profile
