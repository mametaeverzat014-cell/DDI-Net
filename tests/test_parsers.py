"""Tests for the external-source parsers, using synthetic fixtures.

These run without any network access: each test writes a small file in the
exact format of the real source, then parses it. That is what lets the parsers
be developed and regression-tested on a machine that cannot reach the hosts.
"""
import gzip

import pytest

from ddinet.data import biosnap, drugbank, sider
from ddinet.data.download import _looks_like_html, _is_policy_refusal


# -- DrugBank ---------------------------------------------------------------

DRUGBANK_XML = """<?xml version="1.0" encoding="UTF-8"?>
<drugbank xmlns="http://www.drugbank.ca">
  <drug type="small molecule">
    <drugbank-id primary="true">DB00001</drugbank-id>
    <drugbank-id>DBOLD1</drugbank-id>
    <name>Testazole</name>
    <groups><group>approved</group></groups>
    <atc-codes><atc-code code="J02AB02"/></atc-codes>
    <calculated-properties>
      <property><kind>SMILES</kind><value>CCO</value></property>
      <property><kind>InChIKey</kind><value>InChIKey=LFQSCWFLJHTTHZ-UHFFFAOYSA-N</value></property>
    </calculated-properties>
    <enzymes>
      <enzyme><name>Cytochrome P450 3A4</name>
        <actions><action>inhibitor</action></actions></enzyme>
    </enzymes>
    <drug-interactions>
      <drug-interaction>
        <drugbank-id>DB00002</drugbank-id><name>Testastatin</name>
        <description>The metabolism of Testastatin can be decreased when combined with Testazole.</description>
      </drug-interaction>
    </drug-interactions>
    <pathways>
      <pathway><name>Fake pathway</name>
        <drugs><drug><drugbank-id>DB99999</drugbank-id><name>Decoy</name></drug></drugs>
      </pathway>
    </pathways>
  </drug>
  <drug type="small molecule">
    <drugbank-id primary="true">DB00002</drugbank-id>
    <name>Testastatin</name>
    <groups><group>approved</group></groups>
    <calculated-properties>
      <property><kind>SMILES</kind><value>CCC</value></property>
    </calculated-properties>
    <enzymes>
      <enzyme><name>Cytochrome P450 3A4</name>
        <actions><action>substrate</action></actions></enzyme>
    </enzymes>
    <drug-interactions>
      <drug-interaction>
        <drugbank-id>DB00001</drugbank-id><name>Testazole</name>
        <description>The metabolism of Testastatin can be decreased when combined with Testazole.</description>
      </drug-interaction>
    </drug-interactions>
  </drug>
  <drug type="biotech">
    <drugbank-id primary="true">DB00003</drugbank-id>
    <name>Testomab</name>
    <groups><group>approved</group></groups>
  </drug>
</drugbank>
"""


@pytest.fixture
def drugbank_xml(tmp_path):
    path = tmp_path / "db.xml"
    path.write_text(DRUGBANK_XML)
    return path


def test_nested_pathway_drugs_are_not_parsed_as_records(drugbank_xml):
    """The classic DrugBank parsing bug: <drug> nested inside <pathway>."""
    ids = [d.drugbank_id for d in drugbank.iter_drugs(drugbank_xml)]
    assert ids == ["DB00001", "DB00002", "DB00003"]
    assert "DB99999" not in ids


def test_primary_id_is_selected_over_secondary(drugbank_xml):
    first = next(iter(drugbank.iter_drugs(drugbank_xml)))
    assert first.drugbank_id == "DB00001"


def test_inchikey_prefix_is_stripped(drugbank_xml):
    first = next(iter(drugbank.iter_drugs(drugbank_xml)))
    assert first.inchikey == "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"


def test_cyp_roles_normalise_to_short_names(drugbank_xml):
    first = next(iter(drugbank.iter_drugs(drugbank_xml)))
    assert first.cyp_roles() == {"CYP3A4": {"inhibitor"}}


def test_biotech_drugs_are_filtered_out(drugbank_xml):
    drugs, _ = drugbank.build_tables(drugbank_xml)
    assert "DB00003" not in set(drugs["drugbank_id"])


def test_reciprocal_interactions_are_emitted_once(drugbank_xml):
    """DrugBank lists A->B and B->A; double counting would split one fact."""
    _, inter = drugbank.build_tables(drugbank_xml)
    assert len(inter) == 1
    assert inter.iloc[0]["mechanism"] == "pk_metabolism"


@pytest.mark.parametrize(
    "text,mechanism",
    [
        ("The metabolism of X can be decreased when combined with Y.", "pk_metabolism"),
        ("The risk or severity of bleeding can be increased when X is combined with Y.", "pd_synergy"),
        ("The serum concentration of X can be increased when it is combined with Y.", "pk_exposure"),
        ("The therapeutic efficacy of X can be decreased when used with Y.", "pd_antagonism"),
        ("Totally novel sentence with no template.", "unclassified"),
    ],
)
def test_description_classifier(text, mechanism):
    assert drugbank.classify_description(text).mechanism == mechanism


def test_adverse_effect_is_extracted():
    got = drugbank.classify_description(
        "The risk or severity of bleeding can be increased when A is combined with B."
    )
    assert got.adverse_effect == "bleeding"


# -- SIDER ------------------------------------------------------------------

@pytest.mark.parametrize(
    "stitch,cid",
    [("CID100002244", 2244), ("CID000002244", 2244), ("garbage", None)],
)
def test_stitch_id_parsing(stitch, cid):
    assert sider.stitch_to_pubchem_cid(stitch) == cid


def test_sider_keeps_only_preferred_terms(tmp_path):
    """LLT rows are near-duplicates of their PT parent and must be dropped."""
    path = tmp_path / "meddra_all_se.tsv"
    path.write_text(
        "CID100002244\tCID000002244\tC0000737\tPT\tC0000737\tAbdominal pain\n"
        "CID100002244\tCID000002244\tC0000737\tLLT\tC0000737\tTummy ache\n"
    )
    df = sider.load_side_effects(path)
    assert list(df["side_effect"]) == ["abdominal pain"]


def test_side_effect_matrix_flags_missing_profiles(tmp_path):
    """Missing SIDER data must be distinguishable from 'no side effects'."""
    path = tmp_path / "se.tsv"
    path.write_text(
        "CID100000001\tCID000000001\tC1\tPT\tC1\tnausea\n"
        "CID100000002\tCID000000002\tC1\tPT\tC1\tnausea\n"
    )
    se = sider.load_side_effects(path)
    matrix, vocab, has_profile = sider.build_side_effect_matrix(
        se, ["a", "b", "c"], {"a": 1, "b": 2}, min_frequency=1
    )
    assert vocab == ["nausea"]
    assert list(has_profile) == [1.0, 1.0, 0.0]   # 'c' has no SIDER record
    assert matrix.shape == (3, 1)


def test_sider_gzip_is_read_transparently(tmp_path):
    path = tmp_path / "se.tsv.gz"
    with gzip.open(path, "wt") as fh:
        fh.write("CID100002244\tCID000002244\tC1\tPT\tC1\tHeadache\n")
    assert list(sider.load_side_effects(path)["side_effect"]) == ["headache"]


# -- BioSNAP ----------------------------------------------------------------

def test_biosnap_deduplicates_and_canonicalises(tmp_path):
    path = tmp_path / "chch.tsv"
    path.write_text("# comment\nDB00002\tDB00001\nDB00001\tDB00002\nDB00003\tDB00003\n")
    df = biosnap.load_chch(path)
    assert len(df) == 1                                    # reciprocal + self-loop removed
    assert df.iloc[0].tolist() == ["DB00001", "DB00002"]   # canonically ordered


# -- Downloader guards ------------------------------------------------------

def test_html_error_page_is_detected(tmp_path):
    p = tmp_path / "x.csv"
    p.write_bytes(b"<!DOCTYPE html><html><body>404 not found</body></html>")
    assert _looks_like_html(p)


def test_gzip_magic_bytes_are_not_mistaken_for_html(tmp_path):
    p = tmp_path / "x.gz"
    with gzip.open(p, "wt") as fh:
        fh.write("<html>this is legitimately inside a gzip</html>")
    assert not _looks_like_html(p)


def test_proxy_policy_refusal_is_recognised():
    assert _is_policy_refusal(Exception("Tunnel connection failed: 403 Forbidden"))
    assert _is_policy_refusal(Exception("Tunnel connection failed: 407 Proxy Auth"))
    assert not _is_policy_refusal(Exception("Connection reset by peer"))
