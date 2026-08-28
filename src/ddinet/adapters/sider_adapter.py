"""
SIDER -> canonical assertions. Files present, join BLOCKED.

WHY THIS ADAPTER REFUSES TO RUN WITHOUT AN EXTRA ARGUMENT
-----------------------------------------------------------
SIDER 4.1 is on disk and intact (1 430 drugs, 6 123 MedDRA terms, verified in
DATA_PROVENANCE.md). It is keyed by STITCH CID. The corpus is keyed by
DrugBank id and InChIKey. There is no shared identifier, and a name join is
impossible because the corpus holds no names - its `name` column is a copy of
`drugbank_id`.

So ``extract`` requires a ``cid_to_inchikey`` mapping supplied by the caller.
Without it the adapter raises. It does NOT fall back to matching on anything
weaker, and it does not return an empty store pretending to have run: an
adapter that silently yields nothing is indistinguishable from a source with no
data, and that is precisely the confusion this project cannot afford.

The bridge will come from PubChem (STITCH CID is a PubChem CID with a known
transform, already implemented in ``ddinet.data.sider.stitch_to_pubchem_cid``)
plus a CID -> InChIKey table. PubChem's REST API is unreachable from this
container (403 through the proxy), so the table must be supplied.

THE CIRCULARITY WARNING THAT TRAVELS WITH THIS SOURCE
-------------------------------------------------------
SIDER records MONOTHERAPY side effects extracted from drug labels. The corpus's
largest interaction class, Y=49 "risk or severity of adverse effects can be
increased" (31.67% of all rows), also comes from label text. A feature built
from SIDER and that label share an origin. This is not split leakage - it is a
circular label, and it is documented in docs/BIOLOGICAL_GRAPH_LEAKAGE.md §4.
Results for the UNSPEC_ADVERSE_RISK category must be reported separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Mapping

from ..data import sider
from ..integration.identifiers import canonical_compound_id, normalise
from ..integration.schema import (
    Entity, EntityType, Evidence, EvidenceType, KnowledgeStore, Provenance,
    Relation, RelationType,
)
from . import BaseAdapter, SourceDescription


class JoinUnavailable(RuntimeError):
    """The source is present but cannot be connected to the corpus."""


@dataclass
class SiderAdapter(BaseAdapter):
    """Drug -> side effect, once a CID bridge is supplied."""

    def describe(self) -> SourceDescription:
        return SourceDescription(
            name="sider",
            version="4.1",
            licence="CC BY-NC-SA 4.0",
            provides=("drug_causes_effect",),
            required_files=("sider/meddra_all_se.tsv.gz", "sider/drug_names.tsv"),
            download_url="http://sideeffects.embl.de/download/",
            retrieval_date=date(2026, 8, 27),
            notes=("Keyed by STITCH CID; needs a CID -> InChIKey bridge. "
                   "Monotherapy side effects - see the circularity warning."),
        )

    def _extract(self, store: KnowledgeStore, *,
                 cid_to_inchikey: Mapping[int, str] | None = None,
                 ) -> KnowledgeStore:
        if not cid_to_inchikey:
            raise JoinUnavailable(
                "SIDER is keyed by STITCH CID and the corpus by InChIKey. Pass "
                "cid_to_inchikey={pubchem_cid: inchikey} to join them. No "
                "weaker fallback exists: the corpus has no drug names (its "
                "`name` column is a copy of `drugbank_id`), so a name join "
                "cannot work. See DATA_PROVENANCE.md, SIDER section."
            )
        desc = self.describe()
        table = sider.load_side_effects()

        for row in table.itertuples(index=False):
            cid = sider.stitch_to_pubchem_cid(str(row.stitch_id))
            key = normalise("inchikey", cid_to_inchikey.get(cid)) if cid else None
            if key is None:
                continue
            drug_id = canonical_compound_id(key)
            store.add_entity(Entity(drug_id, EntityType.DRUG))
            effect_id = f"MDR:{row.umls_id}"
            store.add_entity(Entity(effect_id, EntityType.MECHANISM,
                                    name=str(row.side_effect_name)))
            store.add_assertion(
                Relation(drug_id, RelationType.DRUG_CAUSES_EFFECT, effect_id),
                Evidence(
                    # Extracted from a regulatory label, not measured here.
                    EvidenceType.CURATED,
                    Provenance(desc.name, desc.version, desc.retrieval_date,
                               str(row.stitch_id)),
                    metadata={"umls_id": row.umls_id},
                ))
        return store
