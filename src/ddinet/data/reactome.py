"""
Adapter for the two Reactome files: the protein-level network.

TWO FILES, DELIBERATELY BOTH
-----------------------------
They are not duplicates and neither replaces the other:

                          | homo_sapiens.interactions | FIsInGene (2025)
    key                   | UniProt                   | gene symbol
    edges                 | 124 865                   | 272 622
    nodes                 | 9 738                     | 13 733
    provenance            | curated only              | curated + 29.2% PREDICTED
    PubMed reference      | 100% of rows              | none
    sign / direction      | none                      | on 33.8% of edges

The first is conservative and traceable to literature for every single edge.
The second is wider and carries the sign of the interaction
(activate / inhibit), which is what a pharmacodynamic mechanism argument
actually needs. Use the first as the graph's backbone; take directed,
signed edges from the second - after dropping `predicted`.

WHY `predicted` MUST BE DROPPED BY DEFAULT
-------------------------------------------
79 564 of the FI network's edges (29.2%) are the output of Reactome's own
machine-learning predictor, not an observation. On this project's evidence
scale (EVIDENCE_MODEL.md) that is E5_INFERRED. Training on them without
separating them means training partly on another model's predictions, with a
circular-label risk that no downstream metric would reveal. They are therefore
excluded unless explicitly asked for, and running with and without them is a
required ablation rather than an option.

WHAT AN EDGE DOES AND DOES NOT MEAN
------------------------------------
`complex` and `input` together account for the large majority of edges. Both
are produced by CO-MEMBERSHIP: two proteins in the same complex, or two inputs
to the same reaction, get an edge whether or not they touch. For a mechanistic
claim such an edge means "these occur together", not "one acts on the other".
Collapsing all edge types into one unweighted graph would assert more than the
data contains, so the type is kept on every edge and the caller chooses.

SELECTION BIAS
--------------
Reactome is manually curated from literature. Edge density reflects how well
studied a pathway is, not how important it is - the same class of bias as node
degree in the DDI graph, and it will not be removed by anything downstream.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FI_DIR = PROJECT_ROOT / "data" / "raw" / "reactome_fi"
UNIPROT_DIR = PROJECT_ROOT / "data" / "raw" / "reactome"
FI_FILE = "FIsInGene_04142025_with_annotations.txt"
UNIPROT_FILE = "reactome.homo_sapiens.interactions.tab-delimited.txt"

#: Annotations that assert one protein acting ON another, with a sign. These
#: are the mechanistically meaningful subset; `complex` and `input` are not
#: here because co-membership is not action.
SIGNED_ANNOTATIONS = (
    "activate", "activated by", "inhibit", "inhibited by",
    "catalyze", "catalyzed by",
    "expression regulates", "expression regulated by",
)


def _require(path: Path, what: str) -> Path:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Reactome files are not in git (size, not licence "
            f"- they are CC0). Download {what} from https://reactome.org/download-data"
        )
    return path


@dataclass
class FINetwork:
    """The FI network plus the counts needed to report what was used."""

    edges: pd.DataFrame
    n_total: int
    n_predicted_dropped: int
    include_predicted: bool

    @property
    def genes(self) -> set[str]:
        return set(self.edges["gene_a"]) | set(self.edges["gene_b"])

    def report(self) -> str:
        return (
            f"Reactome FI (include_predicted={self.include_predicted})\n"
            f"  edges kept        : {len(self.edges)} of {self.n_total}\n"
            f"  predicted dropped : {self.n_predicted_dropped}\n"
            f"  distinct genes    : {len(self.genes)}\n"
            f"  signed edges      : {int(self.edges['is_signed'].sum())}"
        )


def load_fi_network(
    path: Path | None = None,
    *,
    include_predicted: bool = False,
    min_score: float = 0.0,
) -> FINetwork:
    """Gene-level functional interactions.

    :param include_predicted: keep edges annotated ``predicted``. Default
        False - see the module docstring. Setting True is a claim you must
        defend in the write-up.
    :param min_score: drop edges below this confidence. NOTE that ``Score`` is
        Reactome's internal confidence, **not** a probability that the
        interaction is real; using it as a weight is defensible, reading it as
        P(true) is not.
    """
    file = _require(path or (FI_DIR / FI_FILE), FI_FILE)
    raw = pd.read_csv(file, sep="\t", dtype={"Gene1": str, "Gene2": str,
                                             "Annotation": str, "Direction": str})
    n_total = len(raw)

    ann = raw["Annotation"].fillna("")
    is_predicted = ann.str.contains("predicted", case=False, regex=False)
    kept = raw if include_predicted else raw[~is_predicted]
    n_dropped = 0 if include_predicted else int(is_predicted.sum())

    if min_score > 0:
        kept = kept[kept["Score"].astype(float) >= min_score]

    out = pd.DataFrame({
        "gene_a": kept["Gene1"],
        "gene_b": kept["Gene2"],
        "annotation": kept["Annotation"].fillna(""),
        "direction": kept["Direction"].fillna("-"),
        "score": kept["Score"].astype(float),
    })
    out["is_predicted"] = out["annotation"].str.contains(
        "predicted", case=False, regex=False
    )
    # "Signed" means the annotation names an action with a direction, not
    # merely co-occurrence in a complex or a reaction's input list.
    pattern = "|".join(SIGNED_ANNOTATIONS)
    out["is_signed"] = out["annotation"].str.contains(pattern, case=False, regex=True)
    return FINetwork(
        edges=out.reset_index(drop=True),
        n_total=n_total,
        n_predicted_dropped=n_dropped,
        include_predicted=include_predicted,
    )


def load_uniprot_interactions(path: Path | None = None) -> pd.DataFrame:
    """The curated, PubMed-backed UniProt-keyed network.

    Self-interactions (6.3% of rows: homodimers) are KEPT and flagged rather
    than dropped. Dropping them silently would change the degree of 7 812 nodes,
    and node degree is a quantity this project measures rather than assumes.
    """
    file = _require(path or (UNIPROT_DIR / UNIPROT_FILE), UNIPROT_FILE)
    raw = pd.read_csv(file, sep="\t", dtype=str)
    cols = list(raw.columns)
    out = pd.DataFrame({
        "uniprot_a": raw[cols[0]].str.replace("uniprotkb:", "", regex=False),
        "uniprot_b": raw[cols[3]].str.replace("uniprotkb:", "", regex=False),
        "interaction_type": raw[cols[6]],
        "context": raw[cols[7]].str.replace("reactome:", "", regex=False),
        "pubmed": raw[cols[8]],
    })
    out["is_self"] = out["uniprot_a"] == out["uniprot_b"]
    return out.reset_index(drop=True)


def pathway_adjacency(net: FINetwork) -> dict[str, set[str]]:
    """Gene -> set of its FI neighbours. Undirected, self-loops removed.

    Self-loops are removed HERE and not at load time: a homodimer is a real
    biological fact worth keeping in the raw table, but it contributes nothing
    to "are these two drugs' targets connected", which is what this adjacency
    is for.
    """
    adj: dict[str, set[str]] = {}
    for a, b in zip(net.edges["gene_a"], net.edges["gene_b"]):
        if a == b:
            continue
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    return adj


def target_network_proximity(
    drug_targets: dict[str, set[str]],
    adjacency: dict[str, set[str]],
    pairs: pd.DataFrame,
) -> pd.DataFrame:
    """Are the two drugs' target sets adjacent in the pathway network?

    Deliberately limited to distance 1: "some target of A is a direct FI
    neighbour of some target of B". Longer paths are cheap to compute and easy
    to over-interpret - in a network this dense almost everything is within
    three hops, so a distance-3 feature would be close to constant and would
    look informative only because it is nearly always true.

    NOT a mechanism. Adjacency in a curated interaction network says the two
    proteins have been reported to interact by somebody, in some context, not
    that a drug pair acts through that link in a patient.
    """
    empty: set[str] = set()
    direct, shared_nb = [], []
    for a, b in zip(pairs["drug_a"], pairs["drug_b"]):
        ta, tb = drug_targets.get(a, empty), drug_targets.get(b, empty)
        if not ta or not tb:
            direct.append(0)
            shared_nb.append(0)
            continue
        nb_a: set[str] = set()
        for g in ta:
            nb_a |= adjacency.get(g, empty)
        direct.append(len(nb_a & tb))
        nb_b: set[str] = set()
        for g in tb:
            nb_b |= adjacency.get(g, empty)
        shared_nb.append(len(nb_a & nb_b))

    out = pairs[["drug_a", "drug_b"]].copy()
    out["n_target_adjacent"] = direct
    out["n_shared_neighbours"] = shared_nb
    return out
