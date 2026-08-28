"""
Degree-preserving stratified double-edge swap for bipartite biological graphs.

WHAT THIS CONTROL IS FOR
-------------------------
A model given biological annotations may improve for two very different
reasons. It may be using WHICH proteins a drug acts on - real pharmacology. Or
it may be using HOW MANY annotations a drug has, which is a measure of how well
studied the drug is, and which correlates with the DDI degree shortcut this
project has already measured.

A shuffled control separates them. If the model performs the same on a graph
where every nuisance statistic is preserved but the drug-protein assignments
are randomised, then it was never using the identities.

THE CONTROL IS ONLY AS GOOD AS WHAT IT PRESERVES
--------------------------------------------------
A weak shuffle is worse than none: if the control differs from the true graph
in some statistic the model can see, a performance gap proves nothing about
identity. So this implementation preserves, exactly:

  * per-drug distinct protein degree - exactly, via a GLOBAL duplicate set
    shared across strata rather than a per-stratum one
  * per-protein distinct drug degree - likewise
  * per-drug assertion row count (annotation density)
  * the stratum of every edge - relation_type x evidence_type - so a
    DrugBank TARGET edge never becomes a ChEMBL BIOACTIVITY edge

and deliberately does NOT preserve:

  * per-protein assertion row count. Multiplicity (a drug-target pair with 40
    ChEMBL assays behind it) travels with the DRUG's edge slot, because the
    model aggregates over each drug's proteins and it is the drug side that
    must be indistinguishable. Stated rather than hidden.
  * per-drug pathway count. Pathways follow from the shuffled proteins by
    design - see the pathway section of the calling script.

WHY DOUBLE-EDGE SWAP AND NOT RESAMPLING
-----------------------------------------
Drawing |P(d)| proteins uniformly for each drug preserves drug degree but
destroys PROTEIN degree: a popular target loses its popularity, and the
resulting graph is distinguishable from the true one by protein-side
statistics alone. The swap preserves both sides by construction, which makes
it the stricter control.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class SwapReport:
    """Everything needed to judge whether the randomisation is adequate."""

    n_edges: int
    attempted: int
    successful: int
    retained: int
    #: Per-stratum counts, so a stratum too small to randomise is visible
    #: rather than averaged away.
    by_stratum: dict[str, dict] = field(default_factory=dict)

    @property
    def acceptance_rate(self) -> float:
        return self.successful / self.attempted if self.attempted else 0.0

    @property
    def retained_fraction(self) -> float:
        return self.retained / self.n_edges if self.n_edges else 0.0

    def summary(self) -> dict:
        return {
            "n_edges": self.n_edges,
            "attempted_swaps": self.attempted,
            "successful_swaps": self.successful,
            "acceptance_rate": round(self.acceptance_rate, 4),
            "edges_retained": self.retained,
            "retained_fraction": round(self.retained_fraction, 6),
            "changed_fraction": round(1.0 - self.retained_fraction, 6),
            "by_stratum": self.by_stratum,
        }


def swap_within_stratum(
    left: np.ndarray,
    right: np.ndarray,
    rng: np.random.Generator,
    *,
    swaps_per_edge: int = 20,
    present: set[tuple[int, int]] | None = None,
) -> tuple[np.ndarray, int, int]:
    """Double-edge swap on one bipartite stratum. Returns (new_right, attempted, ok).

    ``left`` and ``right`` are parallel arrays of integer node ids: edge i is
    ``left[i] -- right[i]``. Only ``right`` is rewritten, so every edge keeps
    its left endpoint and its position - which is what lets assertion rows and
    their multiplicity travel with the drug's edge slot.

    A proposal picks edges i and j and exchanges their right endpoints. It is
    accepted only when all four conditions hold:

      * ``left[i] != left[j]``   - swapping within one drug changes nothing
      * ``right[i] != right[j]`` - likewise
      * ``(left[i], right[j])`` is not already an edge
      * ``(left[j], right[i])`` is not already an edge

    The last two are what keep the graph simple. Rejecting rather than
    repairing keeps the degree sequence exactly intact: every accepted swap is
    degree-neutral on both sides by construction.
    """
    n = len(left)
    if n < 2:
        return right.copy(), 0, 0

    right = right.copy()
    # The duplicate check uses a GLOBAL set spanning every stratum, not a
    # per-stratum one. Strata are shuffled independently, so a drug with edges
    # in two strata could otherwise be handed the same protein in both, and its
    # distinct-protein count would silently DROP. A per-stratum set gets the
    # within-stratum invariant right and the drug-level one wrong.
    if present is None:
        present = {(int(a), int(b)) for a, b in zip(left, right)}
    attempted = int(swaps_per_edge * n)
    successful = 0

    # Draw all proposals at once: an RNG call per proposal would dominate the
    # runtime at ~1.8M proposals.
    idx = rng.integers(0, n, size=(attempted, 2))
    for i, j in idx:
        if i == j:
            continue
        a_i, a_j = int(left[i]), int(left[j])
        b_i, b_j = int(right[i]), int(right[j])
        if a_i == a_j or b_i == b_j:
            continue
        if (a_i, b_j) in present or (a_j, b_i) in present:
            continue
        present.discard((a_i, b_i))
        present.discard((a_j, b_j))
        present.add((a_i, b_j))
        present.add((a_j, b_i))
        right[i], right[j] = b_j, b_i
        successful += 1

    return right, attempted, successful


def shuffle_bipartite(
    left_ids: np.ndarray,
    right_ids: np.ndarray,
    strata: np.ndarray,
    *,
    seed: int,
    swaps_per_edge: int = 20,
) -> tuple[np.ndarray, SwapReport]:
    """Shuffle right endpoints within each stratum independently.

    Independence between strata is the point: it is what guarantees a
    DrugBank TARGET edge stays a DrugBank TARGET edge. The cost is that a
    stratum with very few edges cannot be randomised much, which the per-
    stratum report makes visible instead of burying in an average.

    Determinism: one seeded generator, and strata are processed in sorted
    order, so the result depends only on (inputs, seed).
    """
    rng = np.random.default_rng(seed)
    out = right_ids.copy()
    # One set for the whole graph - see swap_within_stratum.
    present = {(int(a), int(b)) for a, b in zip(left_ids, right_ids)}
    report = SwapReport(n_edges=len(left_ids), attempted=0, successful=0, retained=0)

    for stratum in sorted(set(strata.tolist())):
        mask = strata == stratum
        sub_left, sub_right = left_ids[mask], right_ids[mask]
        new_right, attempted, ok = swap_within_stratum(
            sub_left, sub_right, rng, swaps_per_edge=swaps_per_edge,
            present=present)
        out[mask] = new_right
        retained = int((new_right == sub_right).sum())
        report.attempted += attempted
        report.successful += ok
        report.retained += retained
        report.by_stratum[str(stratum)] = {
            "n_edges": int(mask.sum()),
            "n_distinct_left": int(len(set(sub_left.tolist()))),
            "n_distinct_right": int(len(set(sub_right.tolist()))),
            "attempted_swaps": attempted,
            "successful_swaps": ok,
            "acceptance_rate": round(ok / attempted, 4) if attempted else 0.0,
            "edges_retained": retained,
            "retained_fraction": round(retained / int(mask.sum()), 6),
        }
    return out, report


def degree_table(left_ids: np.ndarray, right_ids: np.ndarray) -> dict[int, int]:
    """Distinct-neighbour degree per left node. Used for validation only."""
    out: dict[int, set] = {}
    for a, b in zip(left_ids, right_ids):
        out.setdefault(int(a), set()).add(int(b))
    return {k: len(v) for k, v in out.items()}
