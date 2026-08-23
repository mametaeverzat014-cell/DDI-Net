"""
Streaming parser for the DrugBank full XML release.

WHY ``iterparse`` AND NOT ``ElementTree.parse``
-----------------------------------------------
The uncompressed DrugBank XML is well over 1 GB.  ``ElementTree.parse`` builds
the entire DOM in memory first, which needs several GB of RAM and will simply
die on a laptop.  ``iterparse`` yields elements as they close, so we can pull
out what we need and immediately free the subtree.  The ``elem.clear()`` plus
previous-sibling deletion below is the standard idiom for keeping memory flat -
without it, ``iterparse`` still accumulates the whole tree.

THE NESTING TRAP
----------------
DrugBank nests ``<drug>`` elements inside ``<pathway><drugs>`` blocks.  A naive
``for event, elem in iterparse(...) if elem.tag == 'drug'`` therefore fires on
pathway members too, and you silently ingest thousands of stub records with no
structure and no interactions.  We track element depth and only process
``<drug>`` at the top level.

WHAT DRUGBANK GIVES AND WHAT IT DOES NOT
----------------------------------------
Gives:  SMILES, InChIKey, ATC codes, interaction partners with free-text
        mechanism descriptions, and - crucially for this project - explicit
        enzyme annotations ("Cytochrome P450 3A4", action "substrate" /
        "inhibitor" / "inducer") and transporter annotations.
Does not give (in the academic XML): a clinical severity grade.  That is why
        DDInter is in the pipeline - it supplies Major/Moderate/Minor.

INTERACTION TYPING FROM FREE TEXT
---------------------------------
DrugBank descriptions are generated from a small set of templates, e.g.
    "The metabolism of X can be decreased when combined with Y."
    "The risk or severity of bleeding can be increased when X is combined with Y."
    "The serum concentration of X can be increased when it is combined with Y."
This is the same observation that the DeepDDI paper exploited to define its 86
interaction types.  ``classify_description`` maps a description onto a coarse
mechanism family plus a direction, which becomes the multi-class target in
Step 3.  It is a rule-based classifier over machine-generated text, so it is
accurate - but you should say plainly that it is regex-based, not learned.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator
from xml.etree import ElementTree as ET

import pandas as pd

NS = "{http://www.drugbank.ca}"


@dataclass
class DrugRecord:
    """One top-level DrugBank drug, reduced to the fields DDI-Net uses."""

    drugbank_id: str
    name: str
    smiles: str = ""
    inchikey: str = ""
    atc_codes: list[str] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)
    drug_type: str = ""
    #: enzyme name -> set of actions, e.g. {"Cytochrome P450 3A4": {"substrate"}}
    enzymes: dict[str, set[str]] = field(default_factory=dict)
    transporters: dict[str, set[str]] = field(default_factory=dict)
    targets: dict[str, set[str]] = field(default_factory=dict)
    #: (partner_drugbank_id, partner_name, description)
    interactions: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def is_small_molecule(self) -> bool:
        return self.drug_type == "small molecule"

    @property
    def is_approved(self) -> bool:
        return "approved" in self.groups

    def cyp_roles(self) -> dict[str, set[str]]:
        """Extract CYP450 roles: ``{'CYP3A4': {'substrate', 'inhibitor'}}``.

        DrugBank spells enzymes out ("Cytochrome P450 3A4"); we normalise to the
        short form so it joins with the curated table and with DDInter.
        """
        out: dict[str, set[str]] = {}
        for enzyme_name, actions in self.enzymes.items():
            m = re.search(r"cytochrome\s+p450\s+([0-9]+[a-z]+[0-9]+)", enzyme_name, re.I)
            if not m:
                continue
            short = "CYP" + m.group(1).upper()
            out.setdefault(short, set()).update(a.lower() for a in actions)
        return out


# --------------------------------------------------------------------------
# XML streaming
# --------------------------------------------------------------------------

def _text(elem: ET.Element, path: str) -> str:
    node = elem.find(path)
    return (node.text or "").strip() if node is not None else ""


def _parse_drug(elem: ET.Element) -> DrugRecord:
    """Extract one drug from its (already fully-read) XML element."""
    primary = ""
    for node in elem.findall(f"{NS}drugbank-id"):
        if node.get("primary") == "true":
            primary = (node.text or "").strip()
            break

    rec = DrugRecord(
        drugbank_id=primary,
        name=_text(elem, f"{NS}name"),
        drug_type=(elem.get("type") or "").strip().lower(),
    )

    rec.groups = [
        (g.text or "").strip().lower() for g in elem.findall(f"{NS}groups/{NS}group")
    ]
    rec.atc_codes = [
        (a.get("code") or "") for a in elem.findall(f"{NS}atc-codes/{NS}atc-code")
    ]

    # Structures live in <calculated-properties>, keyed by <kind>.
    for prop in elem.findall(f"{NS}calculated-properties/{NS}property"):
        kind = _text(prop, f"{NS}kind").lower()
        value = _text(prop, f"{NS}value")
        if kind == "smiles":
            rec.smiles = value
        elif kind == "inchikey":
            # Sometimes stored as "InChIKey=XXXX-YYYY-Z"; strip the prefix.
            rec.inchikey = value.split("=", 1)[-1].strip()

    for section, target in (
        ("enzymes", rec.enzymes),
        ("transporters", rec.transporters),
        ("targets", rec.targets),
    ):
        singular = section[:-1]
        for node in elem.findall(f"{NS}{section}/{NS}{singular}"):
            pname = _text(node, f"{NS}name")
            if not pname:
                continue
            actions = {
                (a.text or "").strip().lower()
                for a in node.findall(f"{NS}actions/{NS}action")
                if (a.text or "").strip()
            }
            target.setdefault(pname, set()).update(actions)

    for node in elem.findall(f"{NS}drug-interactions/{NS}drug-interaction"):
        rec.interactions.append(
            (
                _text(node, f"{NS}drugbank-id"),
                _text(node, f"{NS}name"),
                _text(node, f"{NS}description"),
            )
        )

    return rec


def iter_drugs(xml_path: Path, limit: int | None = None) -> Iterator[DrugRecord]:
    """Yield every top-level drug record, with flat memory usage.

    ``limit`` is for development: parsing the full file takes minutes, and when
    you are debugging a downstream step you want the first 200 records now.
    """
    depth = 0
    n = 0
    context = ET.iterparse(str(xml_path), events=("start", "end"))
    root = None

    for event, elem in context:
        if root is None:
            root = elem
        if elem.tag == f"{NS}drug":
            if event == "start":
                depth += 1
                continue
            depth -= 1
            if depth != 0:
                # Nested <drug> inside <pathway><drugs> - not a real record.
                continue
            yield _parse_drug(elem)
            n += 1
            # Free the subtree: without this, iterparse still builds the whole
            # document in memory and we are back to needing many GB.
            elem.clear()
            if root is not None:
                # Also drop already-processed siblings held by the root.
                while len(root) > 1:
                    del root[0]
            if limit is not None and n >= limit:
                return


# --------------------------------------------------------------------------
# Free-text interaction typing
# --------------------------------------------------------------------------

#: Ordered rules: first match wins, so put the specific patterns first.
_DESCRIPTION_RULES: tuple[tuple[str, str, str], ...] = (
    # (regex, mechanism, direction)
    (r"metabolism of .+ can be (decreased|reduced)", "pk_metabolism", "increased_exposure"),
    (r"metabolism of .+ can be increased", "pk_metabolism", "decreased_exposure"),
    (r"serum concentration of .+ can be increased", "pk_exposure", "increased_exposure"),
    (r"serum concentration of .+ can be (decreased|reduced)", "pk_exposure", "decreased_exposure"),
    (r"(absorption|bioavailability) of .+ can be (decreased|reduced)", "pk_absorption", "decreased_exposure"),
    (r"(excretion|clearance) (rate )?of .+ can be (decreased|reduced)", "pk_excretion", "increased_exposure"),
    (r"(excretion|clearance) (rate )?of .+ can be increased", "pk_excretion", "decreased_exposure"),
    (r"protein binding of .+ can be (decreased|reduced)", "pk_protein_binding", "increased_exposure"),
    (r"therapeutic efficacy of .+ can be (decreased|reduced)", "pd_antagonism", "reduced_efficacy"),
    (r"therapeutic efficacy of .+ can be increased", "pd_synergy", "increased_effect"),
    (r"risk or severity of .+ can be increased", "pd_synergy", "increased_toxicity"),
    (r"(hypotensive|bradycardic|sedative|hypoglycemic|hyperkalemic|qtc?[- ]prolonging|"
     r"nephrotoxic|hepatotoxic|neurotoxic|myelosuppressive|serotonergic|anticoagulant)"
     r" activities of .+ can be increased", "pd_synergy", "increased_toxicity"),
    (r"can cause a decrease in the absorption", "pk_absorption", "decreased_exposure"),
    (r"may (decrease|reduce) the .+ activities", "pd_antagonism", "reduced_efficacy"),
    (r"may increase the .+ activities", "pd_synergy", "increased_toxicity"),
)

_ADVERSE_EFFECT_RE = re.compile(
    r"risk or severity of ([a-z ,\-/]+?) can be increased", re.I
)


@dataclass
class InteractionType:
    mechanism: str
    direction: str
    adverse_effect: str = ""


def classify_description(description: str) -> InteractionType:
    """Map a DrugBank interaction description onto a coarse mechanism type.

    Returns ``mechanism='unclassified'`` when no rule fires - and you should
    *report* that rate.  A high unclassified fraction would mean the template
    set changed between releases and the rules need revisiting.
    """
    text = (description or "").strip().lower()
    if not text:
        return InteractionType("unclassified", "unknown")

    effect = ""
    m = _ADVERSE_EFFECT_RE.search(text)
    if m:
        effect = m.group(1).strip()

    for pattern, mechanism, direction in _DESCRIPTION_RULES:
        if re.search(pattern, text):
            return InteractionType(mechanism, direction, effect)
    return InteractionType("unclassified", "unknown", effect)


# --------------------------------------------------------------------------
# Table builders
# --------------------------------------------------------------------------

def build_tables(
    xml_path: Path,
    *,
    small_molecules_only: bool = True,
    approved_only: bool = False,
    require_smiles: bool = True,
    limit: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Parse DrugBank into ``(drugs_df, interactions_df)``.

    Filtering rationale:
      ``small_molecules_only`` - biologics (antibodies, enzymes) have no usable
          SMILES, so a structure-based model cannot represent them at all.
          Including them would create rows whose features are all zero.
      ``require_smiles`` - same reason, applied per record.
      ``approved_only`` - optional. Restricting to approved drugs makes the
          task more clinically relevant but shrinks the graph substantially;
          report which setting you used.

    Interactions are emitted **once** per unordered pair.  DrugBank lists each
    interaction twice (A->B under drug A, B->A under drug B); keeping both would
    double-count and, worse, could place the two copies of one fact on opposite
    sides of a split.
    """
    drugs: list[dict] = []
    inter: dict[tuple[str, str], dict] = {}

    for rec in iter_drugs(xml_path, limit=limit):
        keep = True
        if small_molecules_only and not rec.is_small_molecule:
            keep = False
        if approved_only and not rec.is_approved:
            keep = False
        if require_smiles and not rec.smiles:
            keep = False

        if keep:
            cyp = rec.cyp_roles()
            drugs.append(
                {
                    "drugbank_id": rec.drugbank_id,
                    "name": rec.name,
                    "smiles": rec.smiles,
                    "inchikey": rec.inchikey,
                    "atc_code": rec.atc_codes[0] if rec.atc_codes else "",
                    "atc_codes": "|".join(rec.atc_codes),
                    "groups": "|".join(rec.groups),
                    "cyp_substrate": "|".join(sorted(k for k, v in cyp.items() if "substrate" in v)),
                    "cyp_inhibitor": "|".join(sorted(k for k, v in cyp.items() if "inhibitor" in v)),
                    "cyp_inducer": "|".join(sorted(k for k, v in cyp.items() if "inducer" in v)),
                    "n_targets": len(rec.targets),
                    "n_enzymes": len(rec.enzymes),
                    "n_transporters": len(rec.transporters),
                }
            )

        for partner_id, partner_name, desc in rec.interactions:
            if not partner_id:
                continue
            key = tuple(sorted((rec.drugbank_id, partner_id)))
            if key in inter:
                continue
            itype = classify_description(desc)
            inter[key] = {
                "drug_a_id": key[0],
                "drug_b_id": key[1],
                "description": desc,
                "mechanism": itype.mechanism,
                "direction": itype.direction,
                "adverse_effect": itype.adverse_effect,
            }

    drugs_df = pd.DataFrame(drugs)
    inter_df = pd.DataFrame(list(inter.values()))

    # Keep only interactions where BOTH drugs survived filtering - an edge to a
    # drug we cannot featurise is unusable.
    if len(drugs_df) and len(inter_df):
        valid = set(drugs_df["drugbank_id"])
        inter_df = inter_df.loc[
            inter_df["drug_a_id"].isin(valid) & inter_df["drug_b_id"].isin(valid)
        ].reset_index(drop=True)

    return drugs_df, inter_df


def parse_vocabulary(csv_path: Path) -> pd.DataFrame:
    """Parse the CC0 DrugBank Open Data vocabulary CSV.

    Column names in that file contain spaces and vary in case between releases,
    so we normalise rather than indexing by exact header text.
    """
    df = pd.read_csv(csv_path, dtype=str).fillna("")
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    rename = {
        "drugbank_id": "drugbank_id",
        "common_name": "name",
        "standard_inchi_key": "inchikey",
        "cas": "cas",
        "unii": "unii",
        "synonyms": "synonyms",
        "accession_numbers": "accession_numbers",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    return df
