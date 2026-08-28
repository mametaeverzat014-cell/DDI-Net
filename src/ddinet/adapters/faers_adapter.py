"""
FAERS / openFDA -> canonical assertions. INTERFACE ONLY - source not obtained.

WHAT IT WOULD ADD THAT NOTHING ELSE DOES
------------------------------------------
An evidence LEVEL, not just more rows. Every assertion this project currently
holds is EvidenceType.CURATED, extracted from labels. FAERS is spontaneous
adverse-event reporting: a statistical signal in what clinicians actually
reported. That is EvidenceType.CLINICAL, and it is the only route to the
experiment "does model quality depend on the strength of the evidence", which
is otherwise unrunnable because the evidence axis is currently a constant
(docs/EVIDENCE_MODEL.md §2).

WHY ITS BIAS IS DIFFERENT AND MUST NOT BE AVERAGED IN
--------------------------------------------------------
FAERS carries confounding by indication and reporting bias: widely prescribed
drugs generate more reports because they are prescribed more, not because they
are more reactive. That is a different failure mode from a curated label's
class-effect generalisation. Merging the two into one confidence number would
hide exactly the distinction the evidence model exists to preserve.

There is already an evaluation-side FAERS module (``ddinet.eval.faers``) for
validating predictions against pharmacovigilance signal. This adapter is the
ingestion side and does not duplicate it.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..integration.schema import KnowledgeStore
from . import BaseAdapter, SourceDescription


@dataclass
class FaersAdapter(BaseAdapter):
    """Placeholder. ``extract`` raises until extracted signal files exist."""

    def describe(self) -> SourceDescription:
        return SourceDescription(
            name="faers",
            version="",
            licence="public domain (US FDA)",
            provides=("drug_causes_effect", "drug_interacts_with_drug"),
            required_files=("openfda_faers/signal_pairs.parquet",),
            download_url="https://open.fda.gov/data/downloads/",
            notes=("Expected schema: drug_a, drug_b, event_term, n_reports, "
                   "prr or ror, ci_low, ci_high, quarter. NOTE: any drug-drug "
                   "row from this source is LABEL-BEARING and is restricted to "
                   "training drugs by build_biograph, same as any other DDI "
                   "edge - see docs/BIOLOGICAL_GRAPH_LEAKAGE.md rule 1."),
            is_placeholder=True,
        )

    def _extract(self, store: KnowledgeStore, **kwargs) -> KnowledgeStore:
        raise NotImplementedError(
            "unreachable: BaseAdapter.require() raises first for a placeholder"
        )
