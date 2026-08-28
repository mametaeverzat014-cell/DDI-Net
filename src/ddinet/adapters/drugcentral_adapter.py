"""
DrugCentral -> canonical assertions.

WRAPS, DOES NOT REPLACE, ``ddinet.data.drugcentral``. That module already
parses the two files, joins them onto the corpus by InChIKey and reports the
measured coverage (1 497 / 1 228 / 1 214 of 1 705). Re-parsing here would give
two code paths that could disagree.

WHAT DRUGCENTRAL SUPPLIES AND WHAT IT DOES NOT
------------------------------------------------
Supplies: the drug -> protein link the corpus lacks entirely, keyed by gene
symbol AND UniProt accession, for human targets.

Does not supply: substrate roles. ``ACTION_TYPE`` is filled on 24.3% of human
rows and every CYP row that has one says INHIBITOR. "Drug X is metabolised by
CYP3A4" - half of the commonest PK interaction mechanism - is not expressible
from this source. That is why the DrugBank full XML is still on the wanted list.

EVIDENCE TYPING
---------------
A row with ``MOA=1`` is a documented mechanism of action: CURATED.
A row without it is a measured activity: BIOACTIVITY.
The distinction is 2 409 rows against 11 892, and flattening it would let a
single micromolar screening hit look like a therapeutic mechanism.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from ..data import drugcentral as dc
from ..integration.identifiers import (
    canonical_compound_id, canonical_gene_id, canonical_protein_id, normalise,
)
from ..integration.schema import (
    Entity, EntityType, Evidence, EvidenceType, KnowledgeStore, Provenance,
    Relation, RelationType,
)
from . import BaseAdapter, SourceDescription

#: ACTION_TYPE -> the relation it licenses. Anything not listed falls back to
#: the neutral DRUG_TARGETS_PROTEIN: asserting a direction we were not told is
#: how a measurement becomes an invented mechanism.
_ACTION_RELATION = {
    "INHIBITOR": RelationType.DRUG_INHIBITS_PROTEIN,
    "BLOCKER": RelationType.DRUG_INHIBITS_PROTEIN,
    "ANTAGONIST": RelationType.DRUG_INHIBITS_PROTEIN,
    "AGONIST": RelationType.DRUG_ACTIVATES_PROTEIN,
    "ACTIVATOR": RelationType.DRUG_ACTIVATES_PROTEIN,
    "OPENER": RelationType.DRUG_ACTIVATES_PROTEIN,
    "POSITIVE ALLOSTERIC MODULATOR": RelationType.DRUG_ACTIVATES_PROTEIN,
}

#: Target classes that make a protein an enzyme or a transporter rather than a
#: plain target. Used for the node type only - the relation stays what the
#: source asserted.
_ENZYME_CLASSES = frozenset({"Enzyme", "Kinase"})
_TRANSPORTER_CLASSES = frozenset({"Transporter"})


def _text(row, field: str) -> str:
    """A column's value as a string, treating NaN as absent.

    Needed because most of these columns are sparse and pandas fills the gaps
    with float NaN - which is TRUTHY, so the usual ``value or ""`` idiom passes
    a float through and blows up on .strip() far from the cause.
    """
    value = getattr(row, field, None)
    if value is None or (isinstance(value, float) and value != value):
        return ""
    return str(value).strip()


@dataclass
class DrugCentralAdapter(BaseAdapter):
    """Emits drug -> protein assertions for drugs present in the corpus."""

    def describe(self) -> SourceDescription:
        return SourceDescription(
            name="drugcentral",
            version="2021_09_01",
            licence="CC BY-SA 4.0",
            provides=("drug_targets_protein", "drug_inhibits_protein",
                      "drug_activates_protein", "gene_encodes_protein"),
            required_files=("drugcentral/structures.smiles.tsv",
                            "drugcentral/drug.target.interaction.tsv.gz"),
            download_url="https://drugcentral.org/download",
            retrieval_date=date(2026, 8, 27),
            notes=("ACTION_TYPE present on 24.3% of human rows; MOA=1 on 16.8%. "
                   "No substrate roles at all."),
        )

    def _extract(self, store: KnowledgeStore, *, drugs: pd.DataFrame,
                 match: str = "exact") -> KnowledgeStore:
        """:param drugs: the corpus drug table (needs drugbank_id, inchikey)."""
        desc = self.describe()
        table = dc.build_drug_target_table(
            drugs, self.directory, match=match)

        # TARGET_CLASS is a property of the (drug, target) ASSERTION in
        # DrugCentral, not of the protein: PARP1 appears as "Enzyme" on one row
        # and unclassified on another. Typing the node per row would therefore
        # make its type depend on which row happened to be read first. Resolve
        # it once, over the whole frame, taking the most specific class seen.
        node_types: dict[str, EntityType] = {}
        seen_gene_links: set[tuple[str, str]] = set()
        for row in table.edges.itertuples(index=False):
            acc = normalise("uniprot", getattr(row, "uniprot_id", None))
            if acc is None:
                continue
            cls = _text(row, "target_class")
            candidate = (EntityType.ENZYME if cls in _ENZYME_CLASSES
                         else EntityType.TRANSPORTER if cls in _TRANSPORTER_CLASSES
                         else EntityType.PROTEIN)
            current = node_types.get(acc)
            # PROTEIN is the general case; a specific subtype wins over it, and
            # a clash between two specific subtypes keeps the general one rather
            # than picking arbitrarily.
            if current is None or current is EntityType.PROTEIN:
                node_types[acc] = candidate
            elif candidate is not EntityType.PROTEIN and candidate is not current:
                node_types[acc] = EntityType.PROTEIN

        # inchikey is carried through the join, so the canonical id comes from
        # the structure rather than from the DrugBank accession. Two DrugBank
        # ids on one structure therefore land on one node, which is correct and
        # is what IdentifierMap.collisions() surfaces.
        for row in table.edges.itertuples(index=False):
            key = normalise("inchikey", row.drug_inchikey)
            acc = normalise("uniprot", getattr(row, "uniprot_id", None))
            gene = normalise("gene", row.gene)
            if key is None or (acc is None and gene is None):
                continue

            drug_id = canonical_compound_id(key)
            store.add_entity(Entity(
                drug_id, EntityType.DRUG,
                name=_text(row, "inn"),
                synonyms=(row.drug_id,),
                provenance=Provenance(desc.name, desc.version,
                                      desc.retrieval_date, str(row.struct_id)),
                metadata={"drugbank_id": row.drug_id},
            ))

            target_class = _text(row, "target_class")
            node_type = node_types.get(acc, EntityType.PROTEIN)

            # Prefer the accession: it is a stable key, a gene symbol is not.
            if acc is not None:
                protein_id = canonical_protein_id(acc)
                store.add_entity(Entity(
                    protein_id, node_type,
                    name=_text(row, "target_name"),
                    synonyms=(gene,) if gene else (),
                    provenance=Provenance(desc.name, desc.version,
                                          desc.retrieval_date),
                    metadata={"gene": gene or "", "target_class": target_class},
                ))
                if gene is not None:
                    gene_id = canonical_gene_id(gene)
                    store.add_entity(Entity(gene_id, EntityType.GENE, name=gene))
                    # Once per (gene, protein), not once per drug-target row.
                    # A gene appearing in ten rows is one fact stated ten
                    # times, and repeating it would inflate this source's
                    # apparent support for it.
                    if (gene_id, protein_id) not in seen_gene_links:
                        seen_gene_links.add((gene_id, protein_id))
                        store.add_assertion(
                            Relation(gene_id, RelationType.GENE_ENCODES_PROTEIN,
                                     protein_id),
                            Evidence(EvidenceType.CURATED,
                                     Provenance(desc.name, desc.version,
                                                desc.retrieval_date,
                                                f"{gene}:{acc}")))
            else:
                protein_id = canonical_gene_id(gene)
                store.add_entity(Entity(protein_id, EntityType.GENE, name=gene))

            action = _text(row, "action_type").upper()
            relation = _ACTION_RELATION.get(action, RelationType.DRUG_TARGETS_PROTEIN)
            is_moa = bool(getattr(row, "is_moa", False))

            store.add_assertion(
                Relation(drug_id, relation, protein_id),
                Evidence(
                    # MOA=1 is a curated mechanism statement; everything else is
                    # a measured activity. See the module docstring.
                    EvidenceType.CURATED if is_moa else EvidenceType.BIOACTIVITY,
                    Provenance(desc.name, desc.version, desc.retrieval_date,
                               _text(row, "assertion_id")),
                    # DrugCentral reports no calibrated confidence, so none is
                    # invented. action_type and target_class go to metadata.
                    confidence=None,
                    metadata={"action_type": action,
                              "target_class": target_class,
                              "is_moa": is_moa},
                ))
        return store
