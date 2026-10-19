"""Is the drug order in the TDC DrugBank export the order the sentence means?

THE PROBLEM, MEASURED. Each TDC row is (ID1, ID2, type) with a template such as
"The metabolism of #Drug2 can be decreased when combined with #Drug1". Filling
#Drug1 with ID1 is the obvious reading — and for some types it is wrong most of
the time. Checked against DrugBank's own enzyme roles (the drug that slows
metabolism should be an inhibitor of an enzyme for which the other drug is a
substrate), type 47 puts the inhibitor in the ID2 slot in ~92% of the rows where
the roles decide it, while type 4 ("metabolism ... increased") puts the inducer
in the ID1 slot in >99% of them. The orientation is systematic per type and
differs between types.

The model is unaffected: BIO-GINE trains on unordered pairs. What is affected
is any sentence that says *which* drug is affected. This module decides, per
type, whether the export's order may be used:

* ``symmetric`` — the sentence means the same either way round ("The risk or
  severity of bleeding can be increased when #Drug1 is combined with #Drug2").
* ``consistent`` — the type can be checked against documented roles, and the
  export's order matches in at least ``VERIFIED_THRESHOLD`` of the informative
  rows (at least ``MIN_INFORMATIVE`` of them).
* ``unverified`` — everything else, including types measured as mostly
  reversed. These are rendered without naming which drug is affected; the
  documented roles, where they decide it for the pair at hand, are shown
  separately as a hypothesis.

No row is flipped. Reversing the 92% would make the other 8% wrong, and a
correction the source did not make is not the source's statement.
"""

from __future__ import annotations

from collections import defaultdict

#: Templates whose meaning does not depend on which drug fills which slot.
SYMMETRIC_TYPES = frozenset({31, 33, 42, 49, 50, 56, 66})

VERIFIED_THRESHOLD = 0.95
MIN_INFORMATIVE = 30


def audit(store) -> dict[int, dict]:
    """Per-type orientation check for the pharmacokinetic types.

    A row is *informative* when the documented roles support exactly one
    direction: one drug is an inhibitor (or inducer) of a protein of the right
    relation, for which the other drug is a substrate, and not vice versa.
    """
    from .mechanism import roles_of
    from .records import PK_DIRECTION

    role_sets: dict[tuple[str, str], dict[int, set]] = defaultdict(lambda: defaultdict(set))
    for an in store.annotations:
        for r in roles_of(an):
            role_sets[(an.relation, r)][an.drug].add(an.protein)

    def supports(actor: int, affected: int, role: str, relations) -> bool:
        return any(
            role_sets[(rel, role)].get(actor, set()) & role_sets[(rel, "substrate")].get(affected, set())
            for rel in relations
        )

    out: dict[int, dict] = {}
    counts = {y: [0, 0, 0] for y in PK_DIRECTION}       # consistent, reversed, ambiguous
    for recs in store.records.values():
        for d1, d2, y in recs:
            if y not in PK_DIRECTION:
                continue
            role, relations = PK_DIRECTION[y]
            fwd, rev = supports(d1, d2, role, relations), supports(d2, d1, role, relations)
            if fwd and not rev:
                counts[y][0] += 1
            elif rev and not fwd:
                counts[y][1] += 1
            else:
                counts[y][2] += 1
    for y, (c, r, amb) in counts.items():
        n = c + r
        out[y] = {
            "checkable": True,
            "n_rows": c + r + amb,
            "n_informative": n,
            "n_consistent": c,
            "n_reversed": r,
            "consistency": (c / n) if n else None,
        }
    return out


def orientation_status(y: int, table: dict[int, dict]) -> str:
    if y in SYMMETRIC_TYPES:
        return "symmetric"
    row = table.get(y)
    if row and row["n_informative"] >= MIN_INFORMATIVE and row["consistency"] is not None \
            and row["consistency"] >= VERIFIED_THRESHOLD:
        return "consistent"
    return "unverified"
