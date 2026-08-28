"""
ChEMBL 36 -> canonical assertions, in two stages.

STAGE 1 (scripts/extract_chembl.py)   SQLite -> compact Parquet
STAGE 2 (this adapter)                Parquet -> KnowledgeStore

WHY TWO STAGES
--------------
The database is several GB. A pipeline that queried it during training would
pay that cost on every run, and would make every experiment depend on a file
that cannot be committed. Extraction happens once and writes small columnar
files; everything downstream reads those.

The adapter therefore reads Parquet, NOT SQLite. Pointing it at the database
would work and would be wrong.

HOW THE SCHEMA IS HANDLED WHEN THE DATABASE IS NOT HERE YET
--------------------------------------------------------------
docs/CHEMBL_TABLE_MAP.md was written from ChEMBL's published schema, which
could not be checked against the real file. So the required tables and columns
are declared here as data (``REQUIRED_SCHEMA``) and ``verify_schema`` checks
them against the actual database before a single row is read. A schema that
differs produces a precise error naming the missing table or column, instead of
an extraction that quietly returns fewer rows.

THE SCIENTIFIC CONSTRAINT THIS MODULE MUST NOT BREACH
-------------------------------------------------------
A ChEMBL target relationship is NOT a DDI mechanism. ChEMBL says "this compound
binds this protein at this concentration in this assay". It does not say two
drugs interact, nor by what route. Every relation emitted here is
DRUG_TARGETS_PROTEIN or one of the signed variants - never
DRUG_INTERACTS_WITH_DRUG, and never a mechanism category. Turning target
overlap into a mechanism claim is a modelling step that happens elsewhere,
under its own evidence rules.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterator

import pandas as pd

from ..integration.identifiers import (
    canonical_compound_id, canonical_protein_id, normalise,
)
from ..integration.schema import (
    Entity, EntityType, Evidence, EvidenceType, KnowledgeStore, Provenance,
    Relation, RelationType,
)
from . import BaseAdapter, SourceDescription

#: Tables and the columns this project reads. Checked against the real database
#: before extraction; see verify_schema.
REQUIRED_SCHEMA: dict[str, tuple[str, ...]] = {
    "molecule_dictionary": ("molregno", "chembl_id", "pref_name", "max_phase",
                            "molecule_type", "therapeutic_flag"),
    "compound_structures": ("molregno", "canonical_smiles", "standard_inchi_key"),
    "target_dictionary": ("tid", "chembl_id", "pref_name", "target_type",
                          "organism"),
    "target_components": ("tid", "component_id", "homologue"),
    "component_sequences": ("component_id", "accession", "component_type",
                            "organism"),
    "drug_mechanism": ("mec_id", "molregno", "tid", "mechanism_of_action",
                       "action_type", "direct_interaction", "molecular_mechanism"),
    "action_type": ("action_type", "description", "parent_type"),
    "assays": ("assay_id", "doc_id", "tid", "assay_type", "confidence_score",
               "assay_organism"),
    "activities": ("activity_id", "assay_id", "molregno", "standard_type",
                   "standard_relation", "standard_value", "standard_units",
                   "pchembl_value", "data_validity_comment", "potential_duplicate"),
    "docs": ("doc_id", "pubmed_id", "doi", "year"),
}

#: Only these activity endpoints. Others (percent inhibition, ratios) are not
#: comparable on one scale and would need their own handling.
ACTIVITY_TYPES = ("IC50", "Ki", "Kd", "EC50")

#: Assay confidence 8-9 = a single, directly assigned protein target. Below
#: that the target assignment is itself uncertain, and an edge built on it
#: would carry that uncertainty invisibly.
MIN_ASSAY_CONFIDENCE = 8

#: ChEMBL action_type -> our relation. Anything unmapped stays neutral: naming
#: a direction the source did not state is how a measurement becomes an
#: invented mechanism.
ACTION_RELATION = {
    "INHIBITOR": RelationType.DRUG_INHIBITS_PROTEIN,
    "ANTAGONIST": RelationType.DRUG_INHIBITS_PROTEIN,
    "BLOCKER": RelationType.DRUG_INHIBITS_PROTEIN,
    "NEGATIVE ALLOSTERIC MODULATOR": RelationType.DRUG_INHIBITS_PROTEIN,
    "NEGATIVE MODULATOR": RelationType.DRUG_INHIBITS_PROTEIN,
    "AGONIST": RelationType.DRUG_ACTIVATES_PROTEIN,
    "PARTIAL AGONIST": RelationType.DRUG_ACTIVATES_PROTEIN,
    "POSITIVE ALLOSTERIC MODULATOR": RelationType.DRUG_ACTIVATES_PROTEIN,
    "POSITIVE MODULATOR": RelationType.DRUG_ACTIVATES_PROTEIN,
    "ACTIVATOR": RelationType.DRUG_ACTIVATES_PROTEIN,
    "OPENER": RelationType.DRUG_ACTIVATES_PROTEIN,
    "SUBSTRATE": RelationType.DRUG_SUBSTRATE_OF_ENZYME,
}


class SchemaMismatch(RuntimeError):
    """The database does not have the tables or columns this code expects."""


def connect(db_path: Path) -> sqlite3.Connection:
    """Read-only connection. URI mode so the file cannot be modified by us."""
    if not db_path.exists():
        raise FileNotFoundError(
            f"{db_path} not found. Unpack chembl_36_sqlite.tar.gz into "
            f"{db_path.parent}/ - the archive is several GB and is not in git."
        )
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def verify_schema(conn: sqlite3.Connection,
                  required: dict[str, tuple[str, ...]] | None = None) -> dict:
    """Check every required table and column exists BEFORE reading rows.

    Returns a report of what was found. Raises :class:`SchemaMismatch` naming
    every problem at once - a schema check that stops at the first difference
    makes the second run reveal the second difference, and so on.
    """
    required = required or REQUIRED_SCHEMA
    # Positional access, not by name: verify_schema must work on any
    # connection, including one whose caller did not set a row_factory.
    present = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    missing_tables = sorted(set(required) - present)
    missing_columns: dict[str, list[str]] = {}
    found: dict[str, list[str]] = {}
    for table, columns in required.items():
        if table not in present:
            continue
        actual = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        found[table] = sorted(actual)
        gap = sorted(set(columns) - actual)
        if gap:
            missing_columns[table] = gap
    if missing_tables or missing_columns:
        raise SchemaMismatch(
            "ChEMBL schema differs from docs/CHEMBL_TABLE_MAP.md.\n"
            + (f"  missing tables: {missing_tables}\n" if missing_tables else "")
            + "".join(f"  {t}: missing columns {c}\n"
                      for t, c in missing_columns.items())
            + "Update the table map and REQUIRED_SCHEMA together - the document "
              "and the code must not drift apart."
        )
    return {"tables_checked": sorted(required), "columns_found": found}


# --------------------------------------------------------------------------
# Queries. Kept here rather than in the script so they are one testable object.
# --------------------------------------------------------------------------

COMPOUNDS_SQL = """
SELECT md.molregno, md.chembl_id, md.pref_name, md.max_phase,
       md.molecule_type, md.therapeutic_flag,
       cs.standard_inchi_key, cs.canonical_smiles
FROM molecule_dictionary md
JOIN compound_structures cs ON cs.molregno = md.molregno
WHERE cs.standard_inchi_key IS NOT NULL
"""

TARGETS_SQL = """
SELECT td.tid, td.chembl_id AS target_chembl_id, td.pref_name AS target_name,
       td.target_type, td.organism, cseq.accession, cseq.component_type
FROM target_dictionary td
JOIN target_components tc ON tc.tid = td.tid
JOIN component_sequences cseq ON cseq.component_id = tc.component_id
WHERE td.organism = ?
  AND td.target_type = 'SINGLE PROTEIN'
  AND cseq.accession IS NOT NULL
  AND tc.homologue = 0
"""

MECHANISMS_SQL = """
SELECT dm.mec_id, dm.molregno, dm.tid, dm.mechanism_of_action,
       dm.action_type, dm.direct_interaction, dm.molecular_mechanism,
       md.chembl_id, cs.standard_inchi_key,
       td.chembl_id AS target_chembl_id, td.organism
FROM drug_mechanism dm
JOIN molecule_dictionary md ON md.molregno = dm.molregno
JOIN compound_structures cs ON cs.molregno = dm.molregno
JOIN target_dictionary td ON td.tid = dm.tid
WHERE cs.standard_inchi_key IS NOT NULL
"""

#: The big one. Every filter is justified in docs/CHEMBL_TABLE_MAP.md §H.
ACTIVITIES_SQL = f"""
SELECT act.activity_id, act.molregno, a.tid, act.standard_type,
       act.standard_value, act.standard_units, act.pchembl_value,
       a.confidence_score, a.assay_type, d.pubmed_id, d.doi, d.year,
       cs.standard_inchi_key
FROM activities act
JOIN assays a ON a.assay_id = act.assay_id
JOIN compound_structures cs ON cs.molregno = act.molregno
LEFT JOIN docs d ON d.doc_id = a.doc_id
WHERE act.pchembl_value IS NOT NULL
  AND act.standard_relation = '='
  AND act.data_validity_comment IS NULL
  AND act.potential_duplicate = 0
  AND act.standard_type IN ({','.join('?' * len(ACTIVITY_TYPES))})
  AND a.confidence_score >= ?
  AND a.assay_organism = ?
"""


def stream_query(conn: sqlite3.Connection, sql: str, params: tuple = (),
                 chunk_size: int = 200_000) -> Iterator[pd.DataFrame]:
    """Yield the result in chunks.

    ``activities`` has tens of millions of rows before filtering. Reading it
    with ``pd.read_sql`` would materialise the whole result; this keeps peak
    memory at one chunk regardless of the table's size.
    """
    cursor = conn.execute(sql, params)
    columns = [c[0] for c in cursor.description]
    while True:
        rows = cursor.fetchmany(chunk_size)
        if not rows:
            return
        yield pd.DataFrame([tuple(r) for r in rows], columns=columns)


def load_uniprot_mapping_file(path: Path) -> pd.DataFrame:
    """The flat `chembl_NN_uniprot_mapping.txt`.

    Kept ALONGSIDE the table-derived mapping rather than instead of it: the two
    disagreeing is a signal worth having, and a single path would hide it.
    """
    if not path.exists():
        raise FileNotFoundError(f"{path} not found")
    frame = pd.read_csv(path, sep="\t", comment="#", header=None,
                        names=["accession", "target_chembl_id",
                               "target_name", "target_type"],
                        dtype=str)
    frame["accession"] = frame["accession"].map(lambda a: normalise("uniprot", a))
    return frame.dropna(subset=["accession"]).reset_index(drop=True)


# --------------------------------------------------------------------------
# Stage 2: Parquet -> KnowledgeStore
# --------------------------------------------------------------------------

@dataclass
class ChemblAdapter(BaseAdapter):
    """Reads the extracted Parquet files, never the database."""

    processed_dir: Path | None = None

    def describe(self) -> SourceDescription:
        return SourceDescription(
            name="chembl",
            version="36",
            licence="CC BY-SA 3.0",
            provides=("drug_targets_protein", "drug_inhibits_protein",
                      "drug_activates_protein", "drug_substrate_of_enzyme"),
            required_files=("chembl/chembl_36.db",),
            download_url="https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/latest/",
            notes=("Adapter consumes data/processed/chembl_*.parquet produced by "
                   "scripts/extract_chembl.py, not the database itself."),
        )

    def _processed(self) -> Path:
        from ..adapters import PROJECT_ROOT
        return self.processed_dir or (PROJECT_ROOT / "data" / "processed")

    def is_available(self) -> bool:
        """Available when the EXTRACTS exist - the database alone is not enough."""
        d = self._processed()
        return (d / "chembl_mechanisms.parquet").exists()

    def require(self) -> None:
        if not self.is_available():
            from . import SourceUnavailable
            raise SourceUnavailable(
                f"{self._processed()}/chembl_mechanisms.parquet not found. Run "
                "scripts/extract_chembl.py once against the SQLite database; "
                "this adapter never queries it directly."
            )

    def _extract(self, store: KnowledgeStore, *,
                 min_pchembl: float | None = None,
                 include_activities: bool = False) -> KnowledgeStore:
        """Load mechanisms, and optionally bioactivities.

        :param include_activities: mechanisms are curated statements of how a
            drug works; activities are measurements, far more numerous and far
            weaker as mechanism evidence. They are OFF by default so that a
            micromolar screening hit does not silently outnumber the curated
            mechanism it sits beside.
        :param min_pchembl: only with ``include_activities``. 6.0 is 1 uM.
        """
        desc = self.describe()
        d = self._processed()
        prov = lambda sid: Provenance(desc.name, desc.version,
                                      desc.retrieval_date, str(sid))

        targets = pd.read_parquet(d / "chembl_targets.parquet")
        tid_to_acc = {int(r.tid): normalise("uniprot", r.accession)
                      for r in targets.itertuples(index=False)}

        mechanisms = pd.read_parquet(d / "chembl_mechanisms.parquet")
        for row in mechanisms.itertuples(index=False):
            key = normalise("inchikey", row.standard_inchi_key)
            acc = tid_to_acc.get(int(row.tid))
            if key is None or acc is None:
                continue
            drug_id, protein_id = canonical_compound_id(key), canonical_protein_id(acc)
            store.add_entity(Entity(
                drug_id, EntityType.DRUG,
                name=str(getattr(row, "pref_name", "") or ""),
                synonyms=(str(row.chembl_id),),
                provenance=prov(row.chembl_id),
                metadata={"chembl_id": str(row.chembl_id)}))
            store.add_entity(Entity(
                protein_id, EntityType.PROTEIN, name=acc,
                provenance=prov(row.target_chembl_id)))
            action = str(row.action_type or "").upper()
            store.add_assertion(
                Relation(drug_id,
                         ACTION_RELATION.get(action, RelationType.DRUG_TARGETS_PROTEIN),
                         protein_id),
                Evidence(
                    # drug_mechanism is a curated statement of how the drug
                    # works - the ChEMBL analogue of DrugCentral's MOA=1.
                    EvidenceType.CURATED, prov(row.mec_id),
                    metadata={"action_type": action,
                              "mechanism_of_action": str(row.mechanism_of_action or ""),
                              "direct_interaction": int(row.direct_interaction or 0)},
                ))

        if not include_activities:
            return store

        path = d / "chembl_activities.parquet"
        if not path.exists():
            return store
        activities = pd.read_parquet(path)
        if min_pchembl is not None:
            activities = activities[activities["pchembl_value"] >= min_pchembl]
        for row in activities.itertuples(index=False):
            key = normalise("inchikey", row.standard_inchi_key)
            acc = tid_to_acc.get(int(row.tid))
            if key is None or acc is None:
                continue
            drug_id, protein_id = canonical_compound_id(key), canonical_protein_id(acc)
            store.add_entity(Entity(drug_id, EntityType.COMPOUND))
            store.add_entity(Entity(protein_id, EntityType.PROTEIN, name=acc))
            reference = (f"PMID:{int(row.pubmed_id)}"
                         if pd.notna(getattr(row, "pubmed_id", None)) else "")
            store.add_assertion(
                Relation(drug_id, RelationType.DRUG_TARGETS_PROTEIN, protein_id),
                Evidence(
                    EvidenceType.BIOACTIVITY, prov(row.activity_id),
                    reference=reference,
                    # pchembl and assay confidence are ChEMBL's own scales, not
                    # probabilities, so neither becomes `confidence`.
                    confidence=None,
                    metadata={"standard_type": str(row.standard_type),
                              "pchembl_value": float(row.pchembl_value),
                              "assay_confidence": int(row.confidence_score)},
                ))
        return store
