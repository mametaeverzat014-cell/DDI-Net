"""
Parser for BioSNAP ChCh-Miner - the standard public DDI benchmark graph.

WHY INCLUDE A DATASET THAT HAS NO SEVERITY AND NO MECHANISM
-----------------------------------------------------------
ChCh-Miner is ~48,000 unlabelled DrugBank-derived interaction edges over ~1,500
drugs.  On its own it cannot answer "is this dangerous?".  Its value is
**comparability**: a large share of the published DDI-GNN literature reports on
exactly this graph, so running on it lets you say "my model scores X where the
published method scores Y", instead of only reporting numbers on a dataset
nobody else has used.

For a science fair, that comparison is worth a great deal.  A model evaluated
only on your own dataset invites the question "compared to what?".
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .download import RAW_DIR, open_maybe_gzip
from .sources import BIOSNAP_CHCH


def load_chch(path: Path | None = None) -> pd.DataFrame:
    """Load the edge list as canonically-ordered, deduplicated pairs.

    The file is a two-column TSV of DrugBank IDs with no header. Some releases
    prepend a ``#`` comment line, which we skip.
    """
    path = path or (RAW_DIR / BIOSNAP_CHCH.key / BIOSNAP_CHCH.filename)
    if not path.exists():
        raise FileNotFoundError(f"ChCh-Miner file not found at {path}")

    edges: set[tuple[str, str]] = set()
    with open_maybe_gzip(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            a, b = parts[0].strip(), parts[1].strip()
            if a and b and a != b:
                edges.add((a, b) if a < b else (b, a))

    return pd.DataFrame(sorted(edges), columns=["drug_a_id", "drug_b_id"])
