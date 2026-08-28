"""
UniProt -> canonical assertions. INTERFACE ONLY - source not obtained.

WHAT IT WOULD BE FOR
--------------------
One job, and a narrow one: reconciling the two Reactome files. The curated
network is keyed by UniProt accession, the FI network by gene symbol, and
drug-target annotations arrive in both spaces. Without an accession <-> symbol
table those two networks cannot be merged into one protein graph.

WHAT IS **NOT** NEEDED
-----------------------
The full ``uniprot_sprot.xml`` release (896 MB). It carries sequences,
features, and cross-references this project has no use for, and parsing it
would cost hours for a mapping table. What is needed is a two-column export:
reviewed human entries, ``Entry`` and ``Gene Names`` - a few megabytes.

Until that file exists, this adapter raises SourceUnavailable with those
instructions rather than returning an empty store.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..integration.schema import KnowledgeStore
from . import BaseAdapter, SourceDescription


@dataclass
class UniProtAdapter(BaseAdapter):
    """Placeholder. ``extract`` raises until the mapping file is present."""

    def describe(self) -> SourceDescription:
        return SourceDescription(
            name="uniprot",
            version="",
            licence="CC BY 4.0",
            provides=("gene_encodes_protein",),
            required_files=("uniprot/human_reviewed_idmapping.tsv",),
            download_url=(
                "https://www.uniprot.org/uniprotkb?query=reviewed:true+AND+"
                "organism_id:9606&format=tsv&fields=accession,gene_names"
            ),
            notes=("Expected schema: TSV with columns `Entry` (UniProt "
                   "accession) and `Gene Names` (space-separated symbols). "
                   "The full XML release is NOT required and should not be "
                   "downloaded - it is 896 MB for a two-column need."),
            is_placeholder=True,
        )

    def _extract(self, store: KnowledgeStore, **kwargs) -> KnowledgeStore:
        raise NotImplementedError(
            "unreachable: BaseAdapter.require() raises first for a placeholder"
        )
