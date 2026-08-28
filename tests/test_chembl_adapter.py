"""Tests for the ChEMBL adapter.

THE DATABASE IS NOT PRESENT, SO THE SQL IS TESTED AGAINST A MINIATURE ONE.
The fixture below builds a SQLite database with the schema
docs/CHEMBL_TABLE_MAP.md declares and a handful of rows chosen to exercise each
filter. It is a test double for the QUERIES - it is never a substitute for
ChEMBL data, and nothing it produces reaches a result.

Without it the SQL would be unverified until the 5 GB download lands, and a
join-path error would surface only then.
"""
import sqlite3
from datetime import date

import pandas as pd
import pytest

from ddinet.adapters import SourceUnavailable
from ddinet.adapters.chembl_adapter import (
    ACTIVITIES_SQL, ACTIVITY_TYPES, ACTION_RELATION, COMPOUNDS_SQL,
    MECHANISMS_SQL, MIN_ASSAY_CONFIDENCE, REQUIRED_SCHEMA, SchemaMismatch,
    TARGETS_SQL, ChemblAdapter, load_uniprot_mapping_file, stream_query,
    verify_schema,
)
from ddinet.integration.schema import EntityType, KnowledgeStore, RelationType

ASPIRIN = "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
IBUPROFEN = "HEFNNWSXXWATRW-UHFFFAOYSA-N"
HUMAN = "Homo sapiens"


@pytest.fixture
def mini_chembl():
    """A ChEMBL-shaped database with rows chosen to exercise every filter."""
    conn = sqlite3.connect(":memory:")
    # Column types matter. Declaring everything TEXT made the filter tests
    # below compare an int against a string, so `activity_id not in rows` was
    # true whatever the SQL did - seven tests passing vacuously. The real
    # ChEMBL schema types these as INTEGER, so the fixture does too.
    integer_columns = {
        "molregno", "tid", "component_id", "homologue", "mec_id", "assay_id",
        "activity_id", "doc_id", "confidence_score", "max_phase",
        "therapeutic_flag", "direct_interaction", "molecular_mechanism",
        "potential_duplicate", "pubmed_id", "year", "standard_value",
        "pchembl_value",
    }
    for table, columns in REQUIRED_SCHEMA.items():
        spec = ", ".join(
            f"{c} {'INTEGER' if c in integer_columns else 'TEXT'}"
            for c in columns)
        conn.execute(f"CREATE TABLE {table} ({spec})")

    conn.executemany(
        "INSERT INTO molecule_dictionary "
        "(molregno, chembl_id, pref_name, max_phase, molecule_type, therapeutic_flag)"
        " VALUES (?,?,?,?,?,?)",
        [(1, "CHEMBL25", "ASPIRIN", 4, "Small molecule", 1),
         (2, "CHEMBL521", "IBUPROFEN", 4, "Small molecule", 1),
         (3, "CHEMBL999", "NOSTRUCT", 0, "Small molecule", 0)])
    conn.executemany(
        "INSERT INTO compound_structures "
        "(molregno, canonical_smiles, standard_inchi_key) VALUES (?,?,?)",
        [(1, "CC(=O)Oc1ccccc1C(=O)O", ASPIRIN),
         (2, "CC(C)Cc1ccc(cc1)C(C)C(=O)O", IBUPROFEN)])
    conn.executemany(
        "INSERT INTO target_dictionary "
        "(tid, chembl_id, pref_name, target_type, organism) VALUES (?,?,?,?,?)",
        [(10, "CHEMBL221", "COX-1", "SINGLE PROTEIN", HUMAN),
         (11, "CHEMBL230", "COX-2", "SINGLE PROTEIN", HUMAN),
         (12, "CHEMBL777", "Rat COX", "SINGLE PROTEIN", "Rattus norvegicus"),
         (13, "CHEMBL888", "A complex", "PROTEIN COMPLEX", HUMAN)])
    conn.executemany(
        "INSERT INTO target_components (tid, component_id, homologue) VALUES (?,?,?)",
        [(10, 100, 0), (11, 101, 0), (12, 102, 0), (13, 103, 0),
         (10, 104, 1)])                     # homologue: must be filtered out
    conn.executemany(
        "INSERT INTO component_sequences "
        "(component_id, accession, component_type, organism) VALUES (?,?,?,?)",
        [(100, "P23219", "PROTEIN", HUMAN), (101, "P35354", "PROTEIN", HUMAN),
         (102, "P00000", "PROTEIN", "Rattus norvegicus"),
         (103, "Q00000", "PROTEIN", HUMAN), (104, "P99999", "PROTEIN", HUMAN)])
    conn.executemany(
        "INSERT INTO drug_mechanism (mec_id, molregno, tid, mechanism_of_action,"
        " action_type, direct_interaction, molecular_mechanism) VALUES (?,?,?,?,?,?,?)",
        [(1, 1, 10, "Cyclooxygenase inhibitor", "INHIBITOR", 1, 1),
         (2, 2, 11, "Cyclooxygenase inhibitor", "INHIBITOR", 1, 1),
         (3, 1, 11, "Unclear", "MODULATOR", 0, 0)])
    conn.executemany(
        "INSERT INTO action_type (action_type, description, parent_type) VALUES (?,?,?)",
        [("INHIBITOR", "inhibits", "NEGATIVE MODULATOR"),
         ("MODULATOR", "modulates", "MODULATOR")])
    conn.executemany(
        "INSERT INTO docs (doc_id, pubmed_id, doi, year) VALUES (?,?,?,?)",
        [(1000, 12345, "10.1/x", 2001)])
    conn.executemany(
        "INSERT INTO assays (assay_id, doc_id, tid, assay_type, confidence_score,"
        " assay_organism) VALUES (?,?,?,?,?,?)",
        [(500, 1000, 10, "B", 9, HUMAN),
         (501, 1000, 11, "B", 5, HUMAN),          # low confidence
         (502, 1000, 10, "B", 9, "Rattus norvegicus")])  # wrong organism
    conn.executemany(
        "INSERT INTO activities (activity_id, assay_id, molregno, standard_type,"
        " standard_relation, standard_value, standard_units, pchembl_value,"
        " data_validity_comment, potential_duplicate) VALUES (?,?,?,?,?,?,?,?,?,?)",
        [(1, 500, 1, "IC50", "=", 100, "nM", 7.0, None, 0),      # keep
         (2, 500, 2, "IC50", ">", 100, "nM", 7.0, None, 0),      # relation
         (3, 500, 1, "IC50", "=", 100, "nM", 7.0, "Outside range", 0),  # invalid
         (4, 500, 1, "IC50", "=", 100, "nM", 7.0, None, 1),      # duplicate
         (5, 500, 1, "Percent", "=", 50, "%", 7.0, None, 0),     # wrong type
         (6, 501, 1, "IC50", "=", 100, "nM", 7.0, None, 0),      # low confidence
         (7, 502, 1, "IC50", "=", 100, "nM", 7.0, None, 0),      # wrong organism
         (8, 500, 1, "IC50", "=", 100, "nM", None, None, 0)])    # no pchembl
    conn.commit()
    yield conn
    conn.close()


# --------------------------------------------------------------------------
# Schema verification runs before any row is read
# --------------------------------------------------------------------------

def test_a_complete_schema_is_accepted(mini_chembl):
    report = verify_schema(mini_chembl)
    assert set(report["tables_checked"]) == set(REQUIRED_SCHEMA)


def test_a_missing_table_is_named_in_the_error():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE docs (doc_id TEXT)")
    with pytest.raises(SchemaMismatch) as exc:
        verify_schema(conn)
    assert "missing tables" in str(exc.value)
    assert "activities" in str(exc.value)


def test_a_missing_column_is_named_too(mini_chembl):
    mini_chembl.execute("DROP TABLE activities")
    mini_chembl.execute("CREATE TABLE activities (activity_id TEXT)")
    with pytest.raises(SchemaMismatch, match="missing columns"):
        verify_schema(mini_chembl)


def test_every_problem_is_reported_at_once_not_just_the_first():
    """A check that stops at the first difference makes the second run reveal
    the second difference, and so on."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE docs (doc_id TEXT)")
    conn.execute("CREATE TABLE activities (activity_id TEXT)")
    with pytest.raises(SchemaMismatch) as exc:
        verify_schema(conn)
    text = str(exc.value)
    assert "docs" in text and "activities" in text


def test_verify_schema_does_not_need_a_row_factory():
    """It must work on any connection, including one the caller made plainly."""
    conn = sqlite3.connect(":memory:")
    with pytest.raises(SchemaMismatch):
        verify_schema(conn)


# --------------------------------------------------------------------------
# The queries
# --------------------------------------------------------------------------

def test_compounds_query_skips_molecules_without_a_structure(mini_chembl):
    rows = pd.concat(list(stream_query(mini_chembl, COMPOUNDS_SQL)))
    assert len(rows) == 2
    assert "CHEMBL999" not in set(rows["chembl_id"])


def test_targets_query_filters_organism_type_and_homologues(mini_chembl):
    rows = pd.read_sql(TARGETS_SQL, mini_chembl, params=(HUMAN,))
    accessions = set(rows["accession"])
    assert accessions == {"P23219", "P35354"}, (
        "rat target, protein complex and homologue component must all be gone")


def test_mechanisms_query_keeps_only_rows_with_a_structure(mini_chembl):
    rows = pd.read_sql(MECHANISMS_SQL, mini_chembl)
    assert len(rows) == 3
    assert set(rows["standard_inchi_key"]) == {ASPIRIN, IBUPROFEN}


@pytest.mark.parametrize("activity_id,reason", [
    (2, "standard_relation is > not ="),
    (3, "data_validity_comment is set"),
    (4, "potential_duplicate is 1"),
    (5, "standard_type is not a binding endpoint"),
    (6, "assay confidence below the threshold"),
    (7, "assay organism is not human"),
    (8, "pchembl_value is null"),
])
def test_each_activity_filter_removes_its_own_row(mini_chembl, activity_id, reason):
    """One test per filter, so a change to the SQL says WHICH guarantee broke."""
    params = (*ACTIVITY_TYPES, MIN_ASSAY_CONFIDENCE, HUMAN)
    rows = pd.concat(list(stream_query(mini_chembl, ACTIVITIES_SQL, params)))
    assert activity_id not in set(rows["activity_id"]), f"not filtered: {reason}"


def test_the_one_clean_activity_survives(mini_chembl):
    params = (*ACTIVITY_TYPES, MIN_ASSAY_CONFIDENCE, HUMAN)
    rows = pd.concat(list(stream_query(mini_chembl, ACTIVITIES_SQL, params)))
    assert set(rows["activity_id"]) == {1}
    assert rows.iloc[0]["standard_inchi_key"] == ASPIRIN


def test_streaming_yields_chunks_rather_than_one_frame(mini_chembl):
    """`activities` has tens of millions of rows before filtering; peak memory
    must be one chunk regardless of the table's size."""
    chunks = list(stream_query(mini_chembl, COMPOUNDS_SQL, chunk_size=1))
    assert len(chunks) == 2
    assert all(len(c) == 1 for c in chunks)


# --------------------------------------------------------------------------
# Stage 2: Parquet -> store
# --------------------------------------------------------------------------

def test_adapter_reads_parquet_and_refuses_without_it(tmp_path):
    adapter = ChemblAdapter(processed_dir=tmp_path)
    assert not adapter.is_available()
    with pytest.raises(SourceUnavailable, match="extract_chembl"):
        adapter.extract(KnowledgeStore())


def test_adapter_emits_signed_relations_and_never_a_ddi_edge(tmp_path):
    """The scientific constraint: a ChEMBL target relationship is NOT a DDI
    mechanism. Nothing this adapter emits may be DRUG_INTERACTS_WITH_DRUG."""
    pd.DataFrame({"tid": [10, 11], "accession": ["P23219", "P35354"],
                  "target_chembl_id": ["CHEMBL221", "CHEMBL230"]}
                 ).to_parquet(tmp_path / "chembl_targets.parquet")
    pd.DataFrame({
        "mec_id": [1, 2], "molregno": [1, 2], "tid": [10, 11],
        "mechanism_of_action": ["COX inhibitor", "COX agonist"],
        "action_type": ["INHIBITOR", "AGONIST"], "direct_interaction": [1, 1],
        "chembl_id": ["CHEMBL25", "CHEMBL521"],
        "standard_inchi_key": [ASPIRIN, IBUPROFEN],
        "target_chembl_id": ["CHEMBL221", "CHEMBL230"],
        "pref_name": ["ASPIRIN", "IBUPROFEN"],
    }).to_parquet(tmp_path / "chembl_mechanisms.parquet")

    store = ChemblAdapter(processed_dir=tmp_path).extract(KnowledgeStore())
    predicates = {a.relation.predicate for a in store.assertions}
    assert RelationType.DRUG_INHIBITS_PROTEIN in predicates
    assert RelationType.DRUG_ACTIVATES_PROTEIN in predicates
    assert RelationType.DRUG_INTERACTS_WITH_DRUG not in predicates
    assert len(store.entities_of(EntityType.DRUG)) == 2


def test_an_unmapped_action_type_stays_neutral():
    """Naming a direction the source did not state is how a measurement
    becomes an invented mechanism."""
    assert "MODULATOR" not in ACTION_RELATION
    assert ACTION_RELATION["INHIBITOR"] is RelationType.DRUG_INHIBITS_PROTEIN


def test_activities_are_off_by_default(tmp_path):
    """A micromolar screening hit must not silently outnumber the curated
    mechanism it sits beside."""
    pd.DataFrame({"tid": [10], "accession": ["P23219"],
                  "target_chembl_id": ["CHEMBL221"]}
                 ).to_parquet(tmp_path / "chembl_targets.parquet")
    pd.DataFrame({
        "mec_id": [1], "molregno": [1], "tid": [10],
        "mechanism_of_action": ["x"], "action_type": ["INHIBITOR"],
        "direct_interaction": [1], "chembl_id": ["CHEMBL25"],
        "standard_inchi_key": [ASPIRIN], "target_chembl_id": ["CHEMBL221"],
        "pref_name": ["ASPIRIN"],
    }).to_parquet(tmp_path / "chembl_mechanisms.parquet")
    pd.DataFrame({
        "activity_id": [1, 2], "molregno": [1, 1], "tid": [10, 10],
        "standard_type": ["IC50", "IC50"], "pchembl_value": [7.0, 4.0],
        "confidence_score": [9, 9], "pubmed_id": [12345, None],
        "standard_inchi_key": [ASPIRIN, ASPIRIN],
    }).to_parquet(tmp_path / "chembl_activities.parquet")

    adapter = ChemblAdapter(processed_dir=tmp_path)
    assert len(adapter.extract(KnowledgeStore())) == 1
    assert len(adapter.extract(KnowledgeStore(), include_activities=True)) == 3
    assert len(adapter.extract(KnowledgeStore(), include_activities=True,
                               min_pchembl=6.0)) == 2


def test_uniprot_mapping_file_normalises_and_drops_bad_rows(tmp_path):
    path = tmp_path / "map.txt"
    path.write_text("# comment\nP23219\tCHEMBL221\tCOX-1\tSINGLE PROTEIN\n"
                    "garbage\tCHEMBL999\tX\tSINGLE PROTEIN\n")
    frame = load_uniprot_mapping_file(path)
    assert list(frame["accession"]) == ["P23219"]


def test_missing_uniprot_mapping_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_uniprot_mapping_file(tmp_path / "absent.txt")
