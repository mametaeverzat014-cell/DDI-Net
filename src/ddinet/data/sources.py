"""
Registry of every external data source DDI-Net can consume.

WHY A REGISTRY INSTEAD OF HARD-CODED URLs
-----------------------------------------
Three reasons, all of which you should be able to defend at ISEF:

1. **Provenance.** A judge's first question about any data-driven project is
   "where did the data come from, and are you allowed to use it?"  Every source
   here carries its licence, its citation, and whether it needs manual
   registration.  `scripts/00_data_report.py` prints this table straight into
   your write-up, so the answer is never hand-waved.

2. **Licence hygiene.** These sources are NOT uniformly redistributable.
   DrugBank's *full* release is free for academic use but requires a signed
   licence and may not be re-hosted; its *Open Data* vocabulary is CC0 and may.
   SIDER is CC BY-NC-SA (non-commercial).  Mixing them into one committed CSV
   would silently violate terms.  The registry keeps the distinction explicit
   and `.gitignore` keeps restricted files out of git.

3. **Reproducibility.** Every downloaded file is content-hashed (SHA-256).
   Databases are living resources - DrugBank ships a new release roughly
   quarterly - so "we used DrugBank" is not a reproducible statement, but
   "we used the release whose vocabulary file hashes to a1b2c3..." is.

HOW THE SOURCES FIT TOGETHER
----------------------------
    DrugBank vocabulary (CC0) ---> drug IDs, names, InChIKeys   [the spine]
                 |
                 +--> PubChem PUG-REST -----> SMILES            [structure]
                 +--> SIDER -----------------> side-effect vector [phenotype]
                 +--> DDInter / DrugBank XML -> interaction pairs [labels]
                 +--> openFDA FAERS ---------> real-world signal  [validation]

The vocabulary is the spine because its InChIKey column is a *structure-derived*
identifier: it lets us join chemistry (PubChem) to pharmacology (SIDER, DDInter)
without trusting drug-name string matching, which is notoriously lossy
("acetylsalicylic acid" vs "aspirin" vs "ASA").

A NOTE ON URL DRIFT
-------------------
Download URLs on academic sites change without notice.  Each entry stores a
`landing_page` alongside the direct `url`; if a download 404s, open the landing
page and update the entry.  The downloader validates *content*, not just status
codes, so a silently-changed URL that serves an HTML error page is caught.

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

from dataclasses import dataclass, field
from typing import Literal

Access = Literal["open", "registration", "licence", "api"]


@dataclass(frozen=True)
class Source:
    """One external data resource.

    Attributes
    ----------
    key:
        Short machine name; also the sub-directory under ``data/raw/``.
    name:
        Human-readable name for reports and figure captions.
    url:
        Direct download URL, or ``None`` when the resource is an API queried
        record-by-record (PubChem, openFDA) or needs a manual login (DrugBank
        full release).
    landing_page:
        Where a human goes to get the file or read the terms.  Always set.
    licence:
        Licence string exactly as the provider states it.
    access:
        ``open``          - anonymous direct download.
        ``registration``  - free account needed, then direct download.
        ``licence``       - signed licence needed; file must be placed manually.
        ``api``           - queried programmatically, no bulk file.
    provides:
        What DDI-Net actually takes from it.  Keeps the pipeline honest: if a
        source is not used for anything, it should not be in the registry.
    citation:
        The paper to cite.  ISEF write-ups need these.
    redistributable:
        Whether the raw file may be committed to a public repo.  Everything is
        gitignored regardless; this flag exists so the data report can say
        *why*.
    notes:
        Gotchas discovered while building the parser.
    """

    key: str
    name: str
    url: str | None
    landing_page: str
    licence: str
    access: Access
    provides: tuple[str, ...]
    citation: str
    redistributable: bool
    filename: str | None = None
    notes: str = ""
    # Expected SHA-256, filled in after your first successful download so that
    # later runs detect a silently-updated upstream file.  Left empty here
    # because the correct value depends on which release you fetched.
    sha256: str | None = None


# --------------------------------------------------------------------------
# The registry
# --------------------------------------------------------------------------

SOURCES: dict[str, Source] = {}


def _register(src: Source) -> Source:
    SOURCES[src.key] = src
    return src


DRUGBANK_VOCAB = _register(
    Source(
        key="drugbank_vocabulary",
        name="DrugBank Open Data - drug vocabulary",
        url="https://go.drugbank.com/releases/latest/downloads/all-drugbank-vocabulary",
        landing_page="https://go.drugbank.com/releases/latest#open-data",
        licence="CC0 1.0 Universal (public domain dedication)",
        access="open",
        provides=("drugbank_id", "common_name", "synonyms", "cas", "unii", "inchikey"),
        citation=(
            "Wishart DS, et al. DrugBank 5.0: a major update to the DrugBank "
            "database for 2018. Nucleic Acids Res. 2018;46(D1):D1074-D1082."
        ),
        redistributable=True,
        filename="drugbank_all_vocabulary.zip",
        notes=(
            "ZIP containing a single CSV, historically named 'drugbank vocabulary.csv' "
            "(note the space). The parser globs for '*.csv' rather than assuming the "
            "name. Contains NO structures and NO interactions - it is an identifier "
            "crosswalk only. That is precisely why it is CC0."
        ),
    )
)

DRUGBANK_FULL = _register(
    Source(
        key="drugbank_full",
        name="DrugBank full database release (XML)",
        url=None,  # cannot be fetched anonymously
        landing_page="https://go.drugbank.com/releases/latest",
        licence=(
            "DrugBank Academic (non-commercial) Licence - free for academic use, "
            "requires account approval; redistribution prohibited"
        ),
        access="licence",
        provides=("smiles", "ddi_pairs", "ddi_descriptions", "targets", "enzymes", "transporters"),
        citation=(
            "Knox C, et al. DrugBank 6.0: the DrugBank Knowledgebase for 2024. "
            "Nucleic Acids Res. 2024;52(D1):D1265-D1275."
        ),
        redistributable=False,
        filename="drugbank_full_database.xml",
        notes=(
            "THE richest source: ~1.4M interaction statements with free-text mechanism "
            "descriptions, plus CYP450 enzyme annotations per drug. Requires a free "
            "academic account and manual approval (typically a few days). Download "
            "'full database.xml' and place it at data/raw/drugbank_full/. "
            "The parser (drugbank.py) streams it with iterparse because the "
            "uncompressed XML is >1 GB and will not fit in memory."
        ),
    )
)

PUBCHEM = _register(
    Source(
        key="pubchem",
        name="PubChem PUG-REST",
        url=None,  # per-record API
        landing_page="https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest",
        licence="Public domain (US Government work)",
        access="api",
        provides=("smiles", "inchikey", "molecular_formula", "molecular_weight", "cid"),
        citation=(
            "Kim S, et al. PubChem 2023 update. Nucleic Acids Res. "
            "2023;51(D1):D1373-D1380."
        ),
        redistributable=True,
        notes=(
            "Rate limits: no more than 5 requests/second and 400 requests/minute per "
            "IP. The client in pubchem.py enforces this and caches every response to "
            "disk so a re-run costs zero requests. Resolve by InChIKey (exact, "
            "structure-derived) rather than by name wherever possible."
        ),
    )
)

SIDER = _register(
    Source(
        key="sider",
        name="SIDER 4.1 - Side Effect Resource",
        url="http://sideeffects.embl.de/media/download/meddra_all_se.tsv.gz",
        landing_page="http://sideeffects.embl.de/download/",
        licence="CC BY-NC-SA 4.0 (non-commercial, share-alike)",
        access="open",
        provides=("drug_side_effects", "meddra_terms"),
        citation=(
            "Kuhn M, Letunic I, Jensen LJ, Bork P. The SIDER database of drugs and "
            "side effects. Nucleic Acids Res. 2016;44(D1):D1075-D1079."
        ),
        redistributable=False,  # NC clause: do not re-host
        filename="meddra_all_se.tsv.gz",
        notes=(
            "Uses STITCH compound identifiers (CIDxxxxxxxxx). The 'flat' ID (CID1...) "
            "is the stereo-specific PubChem CID; the 'stereo' ID (CID0...) is the "
            "parent. Strip the prefix and leading zeros to recover a PubChem CID. "
            "SIDER is derived from drug LABELS, so it reflects what regulators "
            "documented, not what is biologically true - a real limitation to state."
        ),
    )
)

SIDER_NAMES = _register(
    Source(
        key="sider_drug_names",
        name="SIDER 4.1 - drug names",
        url="http://sideeffects.embl.de/media/download/drug_names.tsv",
        landing_page="http://sideeffects.embl.de/download/",
        licence="CC BY-NC-SA 4.0",
        access="open",
        provides=("stitch_id", "drug_name"),
        citation="Kuhn M, et al. Nucleic Acids Res. 2016;44(D1):D1075-D1079.",
        redistributable=False,
        filename="drug_names.tsv",
        notes="Two columns, no header: STITCH flat ID, name. Used to map SIDER -> DrugBank by name as a fallback when the CID join fails.",
    )
)

SIDER_ATC = _register(
    Source(
        key="sider_atc",
        name="SIDER 4.1 - ATC codes",
        url="http://sideeffects.embl.de/media/download/drug_atc.tsv",
        landing_page="http://sideeffects.embl.de/download/",
        licence="CC BY-NC-SA 4.0",
        access="open",
        provides=("stitch_id", "atc_code"),
        citation="Kuhn M, et al. Nucleic Acids Res. 2016;44(D1):D1075-D1079.",
        redistributable=False,
        filename="drug_atc.tsv",
        notes="ATC = WHO Anatomical Therapeutic Chemical class. Useful as a coarse pharmacological feature and for stratifying splits.",
    )
)

DDINTER = _register(
    Source(
        key="ddinter",
        name="DDInter 2.0",
        url=None,  # one CSV per ATC letter; see DDINTER_ATC_CODES
        landing_page="http://ddinter.scbdd.com/download/",
        licence="Free for academic research (see site terms)",
        access="open",
        provides=("ddi_pairs", "severity_level", "interaction_mechanism"),
        citation=(
            "Xiong G, et al. DDInter: an online drug-drug interaction database "
            "towards improving clinical practice and patient safety. "
            "Nucleic Acids Res. 2022;50(D1):D1200-D1207."
        ),
        redistributable=False,
        notes=(
            "THE key source for this project's framing. Unlike DrugBank, DDInter "
            "assigns each pair a clinical SEVERITY - Major / Moderate / Minor / "
            "Unknown - curated from clinical references. 'Dangerous' in our title "
            "maps to DDInter 'Major'. Downloads are split by ATC first letter: "
            "ddinter_downloads_code_{A,B,D,H,L,P,R,V}.csv"
        ),
    )
)

# DDInter serves its bulk data as one CSV per ATC top-level letter.
DDINTER_ATC_CODES: tuple[str, ...] = ("A", "B", "D", "H", "L", "P", "R", "V")
DDINTER_URL_TEMPLATE = (
    "http://ddinter.scbdd.com/static/media/download/ddinter_downloads_code_{code}.csv"
)

BIOSNAP_CHCH = _register(
    Source(
        key="biosnap_chch",
        name="BioSNAP ChCh-Miner - drug-drug interaction network",
        url="https://snap.stanford.edu/biodata/datasets/10001/files/ChCh-Miner_durgbank-chem-chem.tsv.gz",
        landing_page="https://snap.stanford.edu/biodata/datasets/10001/10001-ChCh-Miner.html",
        licence="Freely available for research (Stanford SNAP BioSNAP collection)",
        access="open",
        provides=("ddi_pairs",),
        citation=(
            "Zitnik M, Sosic R, Maheshwari S, Leskovec J. BioSNAP Datasets: "
            "Stanford Biomedical Network Dataset Collection. 2018."
        ),
        redistributable=False,
        filename="ChCh-Miner_durgbank-chem-chem.tsv.gz",
        notes=(
            "~48k unlabelled DDI edges over ~1.5k DrugBank IDs. Binary only - no "
            "severity, no mechanism. Its value is as a widely used BENCHMARK: many "
            "published DDI-GNN papers report on it, so it lets you compare against "
            "the literature. Note the typo 'durgbank' in the official filename."
        ),
    )
)

TWOSIDES = _register(
    Source(
        key="twosides",
        name="TWOSIDES (nSides) - FAERS-derived polypharmacy side effects",
        url="https://tatonettilab-resources.s3.amazonaws.com/nsides/TWOSIDES.csv.gz",
        landing_page="https://nsides.io/",
        licence="CC BY 4.0",
        access="open",
        provides=("ddi_pairs", "adverse_event_terms", "prr", "confidence_interval"),
        citation=(
            "Tatonetti NP, Ye PP, Daneshjou R, Altman RB. Data-driven prediction of "
            "drug effects and interactions. Sci Transl Med. 2012;4(125):125ra31."
        ),
        redistributable=False,
        notes=(
            "Pairs annotated with the specific adverse event and a proportional "
            "reporting ratio, mined from FAERS. Complements DrugBank: DrugBank is "
            "mechanism-driven (what pharmacologists expect), TWOSIDES is "
            "signal-driven (what patients actually reported). Disagreement between "
            "them is scientifically interesting, not an error."
        ),
    )
)

OPENFDA_FAERS = _register(
    Source(
        key="openfda_faers",
        name="openFDA - FAERS adverse event reports",
        url=None,  # query API
        landing_page="https://open.fda.gov/apis/drug/event/",
        licence="Public domain (US Government work); see openFDA disclaimer",
        access="api",
        provides=("adverse_event_reports", "co_reported_drug_pairs"),
        citation="U.S. Food and Drug Administration. openFDA drug/event endpoint.",
        redistributable=True,
        notes=(
            "Rate limits: 240 requests/min and 1,000/day without an API key; "
            "120,000/day with a free key (set DDINET_OPENFDA_KEY). "
            "CRITICAL CAVEAT for your write-up: FAERS is a SPONTANEOUS reporting "
            "system. Reports are unverified, duplicated, biased by media attention, "
            "and carry no denominator - so you can never compute a true incidence "
            "rate. It supports DISPROPORTIONALITY analysis (is this pair reported "
            "together with this event more than expected?), not causal proof."
        ),
    )
)


# --------------------------------------------------------------------------
# Convenience views
# --------------------------------------------------------------------------

def sources_by_access(access: Access) -> list[Source]:
    """All registered sources with a given access mode."""
    return [s for s in SOURCES.values() if s.access == access]


def directly_downloadable() -> list[Source]:
    """Sources the automated downloader can fetch without human intervention."""
    return [s for s in SOURCES.values() if s.url is not None and s.access == "open"]


def manual_sources() -> list[Source]:
    """Sources that require a human to register, sign, or click."""
    return [s for s in SOURCES.values() if s.access in ("registration", "licence")]


def citation_block() -> str:
    """Formatted citation list, ready to paste into the ISEF write-up."""
    lines = ["Data sources", "=" * 60]
    for src in sorted(SOURCES.values(), key=lambda s: s.name):
        lines.append(f"\n{src.name}")
        lines.append(f"  Licence : {src.licence}")
        lines.append(f"  Citation: {src.citation}")
        lines.append(f"  URL     : {src.landing_page}")
    return "\n".join(lines)
