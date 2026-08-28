"""
Data quality audit for the biomedical layer.

WHAT THIS IS FOR
----------------
Every check here catches a defect that would otherwise surface as a NUMBER, not
as an error. A duplicated assertion inflates a source's apparent support; an
orphan edge quietly drops a drug from a feature; a self-interaction adds a
degree that no biology justifies. None of those raise anything on their own.

WHAT A "PROBLEM" MEANS HERE
----------------------------
The audit reports counts and examples; it does not decide what is fatal. Some
findings are expected properties of the sources rather than bugs - Reactome
genuinely contains 7 812 homodimers, and a compound genuinely can have two
DrugBank accessions. The report exists so those are stated and counted rather
than discovered later inside a result.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterable

from .biograph import BioGraph, assert_relation_domains
from .identifiers import CANONICAL_PREFIX, IdentifierMap, is_valid, normalise
from .schema import COMPOUND_LIKE, EntityType, KnowledgeStore


def _example(items: Iterable, n: int = 5) -> list:
    out = []
    for item in items:
        out.append(str(item))
        if len(out) >= n:
            break
    return out


def audit_store(store: KnowledgeStore) -> dict:
    """Structural checks over entities and assertions."""
    findings: dict = {}

    # -- duplicate assertions ---------------------------------------------
    # The same source asserting the same relation with the same source_id twice.
    # NOT the same as two sources agreeing, which is the point of the store.
    seen: Counter = Counter()
    for a in store.assertions:
        seen[(a.relation, a.evidence.provenance.source,
              a.evidence.provenance.source_id)] += 1
    duplicates = {k: v for k, v in seen.items() if v > 1}
    findings["duplicate_assertions"] = {
        "count": sum(v - 1 for v in duplicates.values()),
        "examples": _example(f"{k[0].predicate.value} {k[0].subject}->"
                             f"{k[0].object} from {k[1]}#{k[2]} x{v}"
                             for k, v in duplicates.items()),
    }

    # -- self interactions -------------------------------------------------
    self_edges = [a for a in store.assertions
                  if a.relation.subject == a.relation.object]
    findings["self_interactions"] = {
        "count": len(self_edges),
        "examples": _example(f"{a.relation.predicate.value} {a.relation.subject}"
                             for a in self_edges),
    }

    # -- orphan edges: an endpoint with no registered entity ---------------
    orphans = [a for a in store.assertions
               if store.entity(a.relation.subject) is None
               or store.entity(a.relation.object) is None]
    findings["orphan_edges"] = {
        "count": len(orphans),
        "examples": _example(f"{a.relation.subject}->{a.relation.object}"
                             for a in orphans),
    }

    # -- orphan nodes: an entity nothing refers to -------------------------
    referenced = {a.relation.subject for a in store.assertions} | \
                 {a.relation.object for a in store.assertions}
    orphan_nodes = [e.canonical_id for e in store.entities
                    if e.canonical_id not in referenced]
    findings["orphan_nodes"] = {"count": len(orphan_nodes),
                                "examples": _example(orphan_nodes)}

    # -- impossible relation types -----------------------------------------
    domain_problems = assert_relation_domains(store)
    findings["impossible_relations"] = {"count": len(domain_problems),
                                        "examples": _example(domain_problems)}

    # -- identifiers in the wrong canonical space --------------------------
    wrong_space = []
    for e in store.entities:
        expected = CANONICAL_PREFIX.get(e.entity_type)
        if expected and not e.canonical_id.startswith(expected + ":"):
            wrong_space.append(f"{e.canonical_id} is {e.entity_type.value}, "
                               f"expected prefix {expected}:")
    findings["identifier_wrong_space"] = {"count": len(wrong_space),
                                          "examples": _example(wrong_space)}

    # -- malformed identifiers inside canonical ids ------------------------
    malformed = []
    for e in store.entities:
        prefix, _, value = e.canonical_id.partition(":")
        kind = {"CMP": "inchikey", "PRO": "uniprot", "GEN": "gene"}.get(prefix)
        if kind and not is_valid(kind, value):
            malformed.append(e.canonical_id)
    findings["malformed_identifiers"] = {"count": len(malformed),
                                         "examples": _example(malformed)}

    # -- assertions whose evidence names no source -------------------------
    unsourced = [a for a in store.assertions if not a.evidence.provenance.source]
    findings["assertions_without_source"] = {"count": len(unsourced)}

    # -- conflicting signs: one source says activate, another inhibit ------
    signs: dict[tuple[str, str], set[str]] = defaultdict(set)
    for a in store.assertions:
        p = a.relation.predicate.value
        if p.endswith("inhibits_protein") or p.endswith("activates_protein"):
            signs[(a.relation.subject, a.relation.object)].add(p)
    conflicting = {k: v for k, v in signs.items() if len(v) > 1}
    findings["conflicting_signs"] = {
        "count": len(conflicting),
        "examples": _example(f"{k[0]}->{k[1]}: {sorted(v)}"
                             for k, v in conflicting.items()),
    }

    findings["summary"] = store.summary()
    return findings


def audit_identifier_map(imap: IdentifierMap) -> dict:
    """Conflicts and collisions in the mapping table."""
    conflicts = imap.conflicts()
    collisions = imap.collisions()
    return {
        "conflicting_mappings": {
            "count": len(conflicts),
            "examples": _example(f"{space}:{value} -> {sorted(ids)}"
                                 for (space, value), ids in conflicts.items()),
        },
        "within_space_collisions": {
            "count": len(collisions),
            "examples": _example(f"{cid} <- {sorted(vals)}"
                                 for cid, vals in collisions.items()),
        },
        "summary": imap.summary(),
    }


def audit_compounds(records: Iterable[tuple[str, str, str]]) -> dict:
    """(id, smiles, inchikey) triples: duplicates and malformed structures.

    SMILES validity is checked with RDKit when it is importable. The corpus
    loader already flags invalid structures, so this is a second, independent
    look rather than the only one.
    """
    by_key: dict[str, set[str]] = defaultdict(set)
    missing_key, missing_smiles, bad_key = [], [], []
    rows = list(records)

    for ident, smiles, inchikey in rows:
        key = normalise("inchikey", inchikey)
        if not inchikey:
            missing_key.append(ident)
        elif key is None:
            bad_key.append(f"{ident}: {inchikey}")
        else:
            by_key[key].add(ident)
        if not smiles:
            missing_smiles.append(ident)

    duplicates = {k: v for k, v in by_key.items() if len(v) > 1}

    invalid_smiles: list[str] = []
    try:
        from rdkit import Chem, RDLogger
        RDLogger.DisableLog("rdApp.*")
        for ident, smiles, _ in rows:
            if smiles and Chem.MolFromSmiles(smiles) is None:
                invalid_smiles.append(ident)
        smiles_checked = True
    except ImportError:                          # pragma: no cover
        smiles_checked = False

    return {
        "n_records": len(rows),
        "duplicate_structures": {
            "count": len(duplicates),
            "examples": _example(f"{k} <- {sorted(v)}"
                                 for k, v in duplicates.items()),
        },
        "missing_inchikey": {"count": len(missing_key),
                             "examples": _example(missing_key)},
        "malformed_inchikey": {"count": len(bad_key),
                               "examples": _example(bad_key)},
        "missing_smiles": {"count": len(missing_smiles),
                           "examples": _example(missing_smiles)},
        "invalid_smiles": {"count": len(invalid_smiles),
                           "checked": smiles_checked,
                           "examples": _example(invalid_smiles)},
    }


def audit_graph(graph: BioGraph) -> dict:
    """Checks that only make sense once the split-aware graph is built."""
    edge_keys = Counter((e.source_id, e.relation, e.target_id,
                         e.provenance_source) for e in graph.edges)
    duplicate_edges = {k: v for k, v in edge_keys.items() if v > 1}

    isolated = [n for n in graph.nodes
                if not graph.neighbours(n)]
    drug_nodes = [n for n, node in graph.nodes.items()
                  if node.type in COMPOUND_LIKE]

    return {
        "n_nodes": len(graph.nodes),
        "n_edges": len(graph.edges),
        "duplicate_edges": {
            "count": sum(v - 1 for v in duplicate_edges.values()),
            "examples": _example(f"{k[0]}-{k[1].value}->{k[2]} ({k[3]}) x{v}"
                                 for k, v in duplicate_edges.items()),
        },
        "isolated_nodes": {"count": len(isolated),
                           "examples": _example(isolated)},
        "n_drug_nodes": len(drug_nodes),
        "n_fittable_nodes": len(graph.fittable_nodes),
        "excluded_during_build": graph.excluded,
        "policy": graph.policy,
    }
