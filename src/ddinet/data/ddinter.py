"""
Parser for DDInter 2.0 - the source of clinical SEVERITY.

WHY DDInter MATTERS FOR THIS PROJECT SPECIFICALLY
-------------------------------------------------
The project title says "dangerous" interactions.  That word has to mean
something measurable, or the whole framing collapses under a judge's first
question.  DrugBank tells you *that* two drugs interact and by what mechanism;
it does not grade how much you should care.  DDInter assigns each pair a
clinically curated level:

    Major     - avoid the combination; the risk outweighs the benefit
    Moderate  - usually avoid; use only under specific circumstances
    Minor     - minimal clinical significance
    Unknown   - insufficient evidence

So "dangerous" in DDI-Net = DDInter "Major".  That is a defensible operational
definition and it is not one we invented.

CLASS IMBALANCE IS THE POINT
----------------------------
Major interactions are a minority of all interactions, which are themselves a
minority of all drug pairs.  So the real task is a rare-event problem nested
inside another rare-event problem.  This is exactly why accuracy is a useless
metric here and why Step 4 reports AUPRC against the base rate.

'UNKNOWN' IS NOT 'NOT DANGEROUS'
--------------------------------
Rows graded Unknown must be dropped, not folded into the negative class.
Treating "we don't know" as "it's safe" would train the model toward exactly
the error that hurts patients.  ``load_ddinter`` drops them by default and
tells you how many it dropped.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .download import RAW_DIR, fetch_url
from .sources import DDINTER, DDINTER_ATC_CODES, DDINTER_URL_TEMPLATE

#: DDInter's own vocabulary, lower-cased.
SEVERITY_LEVELS = ("minor", "moderate", "major", "unknown")


def download_all(force: bool = False) -> list[Path]:
    """Fetch every per-ATC-letter CSV. Returns the local paths."""
    out = []
    for code in DDINTER_ATC_CODES:
        dest = RAW_DIR / DDINTER.key / f"ddinter_downloads_code_{code}.csv"
        if dest.exists() and not force:
            out.append(dest)
            continue
        fetch_url(DDINTER_URL_TEMPLATE.format(code=code), dest)
        out.append(dest)
    return out


def load_ddinter(
    directory: Path | None = None,
    *,
    drop_unknown: bool = True,
) -> pd.DataFrame:
    """Load and concatenate the DDInter CSVs into one deduplicated table.

    DDInter splits its export by ATC first letter, so a pair whose two drugs
    belong to different ATC classes appears in **two** files.  Deduplication on
    the unordered pair key is therefore mandatory, not defensive.

    Returned columns: ``drug_a``, ``drug_b`` (lower-cased, canonically
    ordered), ``severity``, ``is_dangerous``.
    """
    directory = directory or (RAW_DIR / DDINTER.key)
    files = sorted(directory.glob("ddinter_downloads_code_*.csv"))
    if not files:
        raise FileNotFoundError(
            f"No DDInter CSVs in {directory}. Run download_all(), or fetch them "
            f"manually from {DDINTER.landing_page}"
        )

    frames = []
    for path in files:
        df = pd.read_csv(path, dtype=str).fillna("")
        df.columns = [c.strip().lower() for c in df.columns]
        # Header names have varied across releases; resolve by fuzzy match so a
        # rename upstream does not silently produce an empty table.
        col_a = next((c for c in df.columns if c in ("drug_a", "drugA".lower(), "drug1")), None)
        col_b = next((c for c in df.columns if c in ("drug_b", "drugB".lower(), "drug2")), None)
        col_s = next((c for c in df.columns if "level" in c or "severity" in c), None)
        if not (col_a and col_b and col_s):
            raise ValueError(
                f"Unexpected DDInter columns in {path.name}: {list(df.columns)}"
            )
        frames.append(
            pd.DataFrame(
                {
                    "drug_a": df[col_a].str.strip().str.lower(),
                    "drug_b": df[col_b].str.strip().str.lower(),
                    "severity": df[col_s].str.strip().str.lower(),
                }
            )
        )

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.loc[
        (combined["drug_a"] != "") & (combined["drug_b"] != "") &
        (combined["drug_a"] != combined["drug_b"])
    ]

    keys = [tuple(sorted((a, b))) for a, b in zip(combined["drug_a"], combined["drug_b"])]
    combined["drug_a"] = [k[0] for k in keys]
    combined["drug_b"] = [k[1] for k in keys]

    # If the same pair appears with different grades in different files, keep
    # the most severe - the clinically conservative choice.
    rank = {s: i for i, s in enumerate(("unknown", "minor", "moderate", "major"))}
    combined["_rank"] = combined["severity"].map(rank).fillna(0)
    combined = (
        combined.sort_values("_rank", ascending=False)
        .drop_duplicates(subset=["drug_a", "drug_b"], keep="first")
        .drop(columns="_rank")
        .reset_index(drop=True)
    )

    n_unknown = int((combined["severity"] == "unknown").sum())
    if drop_unknown and n_unknown:
        combined = combined.loc[combined["severity"] != "unknown"].reset_index(drop=True)
        print(
            f"  [ddinter] dropped {n_unknown} 'unknown'-severity pairs "
            f"(they are unlabelled, NOT negative)"
        )

    combined["is_dangerous"] = (combined["severity"] == "major").astype(int)
    return combined
