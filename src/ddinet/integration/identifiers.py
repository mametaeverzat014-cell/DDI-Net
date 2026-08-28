"""
Identifier normalisation: the layer that decides when two records are the
same thing, and how sure we are.

WHY THIS IS NOT A UTILITY MODULE
---------------------------------
Every biological claim in this project arrives keyed by an identifier the
corpus does not use. DrugCentral speaks struct_id, ChEMBL speaks CHEMBL id,
Reactome speaks UniProt and gene symbol, SIDER speaks STITCH CID. The corpus
speaks DrugBank id and InChIKey. Joining them is not plumbing - a wrong join
silently attributes one drug's biology to another, and nothing downstream would
flag it.

THE RANKING THAT MATTERS
-------------------------
Match quality is recorded on every mapping, and it is ordinal:

    EXACT_ID          the same identifier space, string-equal
    INCHIKEY_FULL     full 27-character InChIKey match
    CURATED_MAPPING   a cross-reference published by one of the databases
    INCHIKEY_SKELETON first block only - merges salt forms and stereoisomers
    FUZZY_NAME        name or synonym overlap. UNCERTAIN by construction.

The bottom two are decisions, not facts, and are marked as such:
``Mapping.is_uncertain`` is True for both. Any count computed over uncertain
mappings must be reported separately from the exact ones. Skeleton matching
gains this project 40 drugs (87.8% -> 91.9%) and is off by default for that
reason.

NAME MATCHING IS ALMOST ALWAYS WRONG HERE
------------------------------------------
Worth stating plainly because it is the tempting shortcut: the corpus has no
drug names at all. Its ``name`` column is a verbatim copy of ``drugbank_id``
(measured: ``(drugs.name == drugs.drugbank_id).all()`` is True). So a name join
against this corpus cannot succeed, and code that appears to do it is matching
accession numbers against words.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Iterable

from .schema import EntityType, Provenance


class MatchQuality(IntEnum):
    """Ordinal. Higher is a stronger basis for saying two records are one."""

    FUZZY_NAME = 1
    INCHIKEY_SKELETON = 2
    CURATED_MAPPING = 3
    INCHIKEY_FULL = 4
    EXACT_ID = 5

    @property
    def is_uncertain(self) -> bool:
        """True for bases that are a modelling decision rather than an identity."""
        return self <= MatchQuality.INCHIKEY_SKELETON


# --------------------------------------------------------------------------
# Syntactic validation
# --------------------------------------------------------------------------
# These check SHAPE, not existence. A well-formed accession that no database
# contains is a different problem from a malformed one, and conflating them
# would make the quality audit's "invalid identifier" count meaningless.

#: DrugBank accession: DB followed by five digits.
DRUGBANK_RE = re.compile(r"^DB\d{5}$")
#: ChEMBL identifier: CHEMBL followed by digits.
CHEMBL_RE = re.compile(r"^CHEMBL\d+$")
#: InChIKey: 14 letters, 10 letters, 1 letter - skeleton, stereo/isotope, proton.
INCHIKEY_RE = re.compile(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$")
#: UniProt accession, both the 6- and 10-character forms of the official regex.
UNIPROT_RE = re.compile(
    r"^[OPQ][0-9][A-Z0-9]{3}[0-9]$"
    r"|^[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}$"
)
#: HGNC-style gene symbol. Permissive on purpose: symbol conventions vary and
#: an over-strict rule would reject real genes as invalid.
GENE_RE = re.compile(r"^[A-Z][A-Z0-9\-]{0,14}$")
#: PubChem compound id: bare positive integer.
PUBCHEM_RE = re.compile(r"^[1-9]\d*$")

_VALIDATORS = {
    "drugbank": DRUGBANK_RE,
    "chembl": CHEMBL_RE,
    "inchikey": INCHIKEY_RE,
    "uniprot": UNIPROT_RE,
    "gene": GENE_RE,
    "pubchem": PUBCHEM_RE,
}


def is_valid(kind: str, value: str) -> bool:
    """Is ``value`` well formed for identifier space ``kind``?"""
    if kind not in _VALIDATORS:
        raise ValueError(f"unknown identifier kind {kind!r}; "
                         f"known: {sorted(_VALIDATORS)}")
    return bool(value) and bool(_VALIDATORS[kind].match(value.strip().upper()))


def normalise(kind: str, value: str | None) -> str | None:
    """Canonical surface form, or None when the value is absent or malformed.

    Returning None rather than raising: adapters read whole files, and a single
    malformed row must not abort an extraction. The quality audit counts them.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if kind == "uniprot":
        # Reactome writes "uniprotkb:P37840"; ChEMBL writes the bare accession.
        text = text.split(":")[-1]
        # Isoform suffixes (P12345-2) denote the same gene product for our
        # purposes; the suffix is dropped and recorded nowhere else, so this is
        # a deliberate, documented loss.
        text = text.split("-")[0]
    if kind == "pubchem":
        text = text.removeprefix("CID").lstrip("0") or "0"
    text = text.upper()
    return text if is_valid(kind, text) else None


def inchikey_skeleton(inchikey: str | None) -> str | None:
    """First block of an InChIKey: connectivity only, no stereo, no salt."""
    key = normalise("inchikey", inchikey)
    return key.split("-")[0] if key else None


# --------------------------------------------------------------------------
# Canonical ids
# --------------------------------------------------------------------------
# One prefixed string per entity, so that a canonical id is self-describing and
# two ids from different spaces can never collide.

def canonical_compound_id(inchikey: str) -> str:
    key = normalise("inchikey", inchikey)
    if key is None:
        raise ValueError(f"not a well-formed InChIKey: {inchikey!r}")
    return f"CMP:{key}"


def canonical_protein_id(uniprot: str) -> str:
    acc = normalise("uniprot", uniprot)
    if acc is None:
        raise ValueError(f"not a well-formed UniProt accession: {uniprot!r}")
    return f"PRO:{acc}"


def canonical_gene_id(symbol: str) -> str:
    sym = normalise("gene", symbol)
    if sym is None:
        raise ValueError(f"not a well-formed gene symbol: {symbol!r}")
    return f"GEN:{sym}"


def canonical_pathway_id(source: str, pathway_id: str) -> str:
    if not source or not pathway_id:
        raise ValueError("pathway needs both a source and an id")
    return f"PWY:{source.upper()}:{pathway_id.strip()}"


#: Which canonical prefix belongs to which entity type. Used by the quality
#: audit to catch an adapter that minted an id in the wrong space.
CANONICAL_PREFIX = {
    EntityType.DRUG: "CMP", EntityType.COMPOUND: "CMP",
    EntityType.METABOLITE: "CMP",
    EntityType.PROTEIN: "PRO", EntityType.ENZYME: "PRO",
    EntityType.TRANSPORTER: "PRO", EntityType.TARGET: "PRO",
    EntityType.GENE: "GEN", EntityType.PATHWAY: "PWY",
}


# --------------------------------------------------------------------------
# The mapping table
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Mapping:
    """One record's identity claim, with the basis for it kept."""

    source_space: str          # "drugbank"
    source_value: str          # "DB00945"
    canonical_id: str          # "CMP:BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
    quality: MatchQuality
    provenance: Provenance | None = None

    @property
    def is_uncertain(self) -> bool:
        return self.quality.is_uncertain


class IdentifierMap:
    """Many-to-one mappings onto canonical ids, with conflicts kept visible.

    A source value mapping to two canonical ids is a CONFLICT, not an error to
    resolve silently. It usually means the upstream data has a duplicate or the
    join key was too weak, and picking one arbitrarily would make the result
    depend on row order.
    """

    def __init__(self) -> None:
        self._by_source: dict[tuple[str, str], list[Mapping]] = {}
        self._reverse: dict[str, list[Mapping]] = {}

    def add(self, mapping: Mapping) -> None:
        key = (mapping.source_space, mapping.source_value)
        self._by_source.setdefault(key, []).append(mapping)
        self._reverse.setdefault(mapping.canonical_id, []).append(mapping)

    def resolve(self, source_space: str, source_value: str,
                *, allow_uncertain: bool = False) -> str | None:
        """Best canonical id for a source value, or None.

        "Best" = highest match quality. Uncertain bases are excluded unless
        explicitly allowed, so a caller cannot pick up a skeleton or name match
        without having asked for one.
        """
        candidates = self._by_source.get((source_space, source_value), [])
        if not allow_uncertain:
            candidates = [m for m in candidates if not m.is_uncertain]
        if not candidates:
            return None
        best = max(m.quality for m in candidates)
        top = {m.canonical_id for m in candidates if m.quality == best}
        # A tie between different canonical ids at the same quality is a
        # conflict; refuse rather than choose.
        return top.pop() if len(top) == 1 else None

    def conflicts(self) -> dict[tuple[str, str], set[str]]:
        """Source values that map to more than one canonical id at all."""
        return {
            key: {m.canonical_id for m in maps}
            for key, maps in self._by_source.items()
            if len({m.canonical_id for m in maps}) > 1
        }

    def collisions(self) -> dict[str, set[tuple[str, str]]]:
        """Canonical ids claimed by more than one value of the SAME space.

        Legitimate across spaces (one compound has a DrugBank id and a ChEMBL
        id). Suspicious within one space: two DrugBank ids on one InChIKey means
        the corpus holds the same structure twice.
        """
        out: dict[str, set[tuple[str, str]]] = {}
        for canonical, maps in self._reverse.items():
            by_space: dict[str, set[str]] = {}
            for m in maps:
                by_space.setdefault(m.source_space, set()).add(m.source_value)
            clashing = {(space, v) for space, vals in by_space.items()
                        if len(vals) > 1 for v in vals}
            if clashing:
                out[canonical] = clashing
        return out

    def of_quality(self, quality: MatchQuality) -> list[Mapping]:
        return [m for maps in self._by_source.values() for m in maps
                if m.quality == quality]

    def __len__(self) -> int:
        return sum(len(v) for v in self._by_source.values())

    def summary(self) -> dict:
        by_quality: dict[str, int] = {}
        by_space: dict[str, int] = {}
        for maps in self._by_source.values():
            for m in maps:
                by_quality[m.quality.name] = by_quality.get(m.quality.name, 0) + 1
                by_space[m.source_space] = by_space.get(m.source_space, 0) + 1
        uncertain = sum(n for q, n in by_quality.items()
                        if MatchQuality[q].is_uncertain)
        return {
            "n_mappings": len(self),
            "n_source_values": len(self._by_source),
            "n_canonical_ids": len(self._reverse),
            "n_uncertain": uncertain,
            "by_quality": by_quality,
            "by_source_space": by_space,
            "n_conflicts": len(self.conflicts()),
            "n_within_space_collisions": len(self.collisions()),
        }


def build_compound_map(
    records: Iterable[tuple[str, str, str]],
    *,
    provenance: Provenance | None = None,
    allow_skeleton: bool = False,
) -> IdentifierMap:
    """Map (space, value, inchikey) triples onto canonical compound ids.

    :param allow_skeleton: additionally emit INCHIKEY_SKELETON mappings, which
        merge salt forms and stereoisomers. Off by default; a result computed
        with it on must say so.
    """
    imap = IdentifierMap()
    for space, value, inchikey in records:
        key = normalise("inchikey", inchikey)
        if key is None:
            continue
        imap.add(Mapping(space, value, canonical_compound_id(key),
                         MatchQuality.INCHIKEY_FULL, provenance))
        if allow_skeleton:
            imap.add(Mapping(space, value, f"CMP:{inchikey_skeleton(key)}",
                             MatchQuality.INCHIKEY_SKELETON, provenance))
    return imap
