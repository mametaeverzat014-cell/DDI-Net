"""Mechanism hypotheses built from documented drug-protein roles.

WHAT THIS ADDS OVER "BOTH DRUGS USE THE SAME ENZYME". DrugBank records the
*role* each drug plays at a protein: substrate (the protein processes or moves
the drug), inhibitor (the drug slows the protein), inducer (the drug makes the
body produce more of it). Two drugs sharing an enzyme as substrates is weak;
one drug *inhibiting* the enzyme that *processes* the other is the classic
configuration behind pharmacokinetic interactions. The roles come with PubMed
IDs; this module only arranges them.

WHAT IT DOES NOT ESTABLISH. A configuration is a hypothesis, labelled as one:

* DrugBank does not grade inhibitor or inducer strength, nor how much of a
  drug's clearance a protein handles. A weak inhibitor of a minor route does
  nothing measurable.
* For a prodrug, slower processing can mean *less* active drug, not more. The
  sentences below therefore say "processed more slowly", never "levels rise".
* A shared protein or pathway does not imply an interaction. Most pairs that
  share a Reactome pathway never interact; pathways are context, not cause.
* Consistency with a DrugBank interaction record is not independent support:
  DrugBank may have derived the record from these very annotations.

ChEMBL bioactivity rows never enter here (see serving/shared_biology.py).
"""

from __future__ import annotations

from collections import defaultdict

from .schema import (
    AnnotationRef, Bi, GraphEdge, GraphNode, MechanismBlock, MechanismFinding,
    MechanismGraph, ProteinOut, SharedPathway,
)
from .direction import orientation_status
from .records import PK_DIRECTION, record_id
from .store import Annotation, EvidenceStore

PK_RELATIONS = ("enzyme", "transporter", "carrier")

#: Action words -> normalised role, for proteins that process or move a drug.
PK_ROLE = {
    "substrate": "substrate", "inhibitor": "inhibitor", "weak inhibitor": "inhibitor",
    "inducer": "inducer",
}
#: Action words at a target, grouped by the direction of their effect on it.
ACTIVATING = {
    "agonist", "partial agonist", "activator", "positive allosteric modulator",
    "positive modulator", "potentiator", "stimulator", "opener", "inducer",
    "upregulator",
}
INHIBITING = {
    "antagonist", "inhibitor", "blocker", "inverse agonist", "negative modulator",
    "inhibitory allosteric modulator", "partial antagonist", "downregulator",
    "suppressor", "weak inhibitor", "negative allosteric modulator",
}

SOURCE_LABEL = {
    "DrugBank_v5.1": ("DrugBank drug-protein annotation", "5.1 (export 2025-01-02)"),
    "ChEMBL_36_drug_mechanism": ("ChEMBL curated mechanism of action", "36"),
}


def roles_of(annotation: Annotation) -> list[str]:
    words = [w.strip() for w in annotation.action.split("|") if w.strip()]
    if annotation.relation in PK_RELATIONS:
        out = sorted({PK_ROLE[w] for w in words if w in PK_ROLE})
    else:
        out = sorted({"activating" if w in ACTIVATING else "inhibiting"
                      for w in words if w in ACTIVATING or w in INHIBITING})
    return out or ["unspecified"]


# ------------------------------------------------------- protein families ----
_FAMILIES: list[tuple[str, str, Bi]] = [
    ("CYP", "cytochrome_p450", Bi(
        ru="Фермент из семейства цитохромов P450. Такие ферменты работают в основном в печени и кишечнике и расщепляют многие лекарства, чтобы организм мог их вывести.",
        en="An enzyme of the cytochrome P450 family. These work mainly in the liver and gut and break down many medicines so the body can clear them.")),
    ("UGT", "ugt", Bi(
        ru="Фермент печени, который присоединяет к лекарству химическую «метку», облегчающую его выведение с мочой или желчью.",
        en="A liver enzyme that attaches a chemical tag to a drug so it can be flushed out in urine or bile.")),
    ("ABCB1", "p_glycoprotein", Bi(
        ru="P-гликопротеин — «насос» в стенках кишечника, печени, почек и сосудов мозга. Он выталкивает лекарства из клеток и этим ограничивает, сколько препарата попадает в кровь и в мозг.",
        en="P-glycoprotein — a pump in the walls of the gut, liver, kidney and brain blood vessels. It pushes drugs back out of cells, limiting how much reaches the blood and the brain.")),
    ("ABC", "abc_pump", Bi(
        ru="Белок-насос семейства ABC: выталкивает вещества, в том числе лекарства, из клеток.",
        en="An ABC-family pump: it pushes substances, including drugs, out of cells.")),
    ("SLCO", "oatp", Bi(
        ru="Белок-переносчик семейства OATP: затягивает лекарства внутрь клеток, особенно в клетки печени, где они перерабатываются.",
        en="An OATP-family transporter: it pulls drugs into cells, especially liver cells where they are processed.")),
    ("SLC22", "oat_oct", Bi(
        ru="Белок-переносчик органических ионов. Много работает в почках и печени и помогает выводить лекарства из организма.",
        en="An organic ion transporter. Highly active in the kidney and liver, it helps remove drugs from the body.")),
    ("SLC47", "mate", Bi(
        ru="Белок-переносчик MATE: выводит лекарства из клеток почек и печени в мочу или желчь.",
        en="A MATE transporter: it moves drugs out of kidney and liver cells into urine or bile.")),
    ("SLC", "slc", Bi(
        ru="Белок-переносчик семейства SLC: переносит вещества через клеточную мембрану.",
        en="An SLC-family transporter: it carries substances across the cell membrane.")),
    ("ALB", "albumin", Bi(
        ru="Альбумин — главный белок крови. Многие лекарства путешествуют по крови, прицепившись к нему.",
        en="Albumin — the main protein in blood. Many drugs travel through the bloodstream attached to it.")),
    ("ORM", "orosomucoid", Bi(
        ru="Альфа-1-кислый гликопротеин — белок крови, который связывает и переносит многие лекарства.",
        en="Alpha-1-acid glycoprotein — a blood protein that binds and carries many drugs.")),
    ("KCNH2", "herg", Bi(
        ru="Калиевый канал hERG в клетках сердца. Он участвует в восстановлении сердечной мышцы после каждого сокращения; его блокада связана с удлинением интервала QT на ЭКГ.",
        en="The hERG potassium channel in heart cells. It helps the heart muscle reset after each beat; blocking it is linked to QT prolongation on an ECG.")),
]

_RELATION_FALLBACK = {
    "enzyme": Bi(ru="Фермент: белок, который химически перерабатывает вещества, в том числе лекарства.",
                 en="An enzyme: a protein that chemically processes substances, including drugs."),
    "transporter": Bi(ru="Белок-переносчик: переносит вещества через стенки клеток.",
                      en="A transporter: a protein that moves substances across cell walls."),
    "carrier": Bi(ru="Белок-носитель: связывает лекарство и переносит его по крови.",
                  en="A carrier: a protein that binds a drug and carries it through the blood."),
    "target": Bi(ru="Мишень: белок, на который лекарство действует, чтобы оказать свой эффект.",
                 en="A target: a protein the drug acts on to produce its effect."),
}

_NON_HUMAN = Bi(
    ru="Это белок не человека, а микроорганизма (например, бактерии): лекарство действует на него, а не на клетки человека.",
    en="This is not a human protein but one from a microorganism (for example a bacterium): the drug acts on it, not on human cells.")


def protein_out(store: EvidenceStore, p: int, relation: str, organism: str = "") -> ProteinOut:
    meta = store.proteins[p]
    gene = meta["gene"]
    org = organism or meta.get("organism", "")
    non_human = bool(org) and org.lower() not in ("humans", "homo sapiens")
    family, plain = "other", _RELATION_FALLBACK[relation]
    if non_human:
        family, plain = "non_human", _NON_HUMAN
    else:
        for prefix, fam, text in _FAMILIES:
            if gene.upper().startswith(prefix):
                family, plain = fam, text
                break
    return ProteinOut(uniprot=meta["uniprot"], gene=gene, name=meta["name"],
                      organism=org, family=family, plain=plain)


def annotation_ref(store: EvidenceStore, an: Annotation) -> AnnotationRef:
    name, version = SOURCE_LABEL[an.source]
    retrieved = (store.sources["drugbank_annotations"]["retrieved"]
                 if an.source.startswith("DrugBank") else store.sources["chembl_moa"]["retrieved"])
    return AnnotationRef(
        id=annotation_id(store, an),
        drug_id=store.ids[an.drug],
        uniprot=store.proteins[an.protein]["uniprot"],
        relation=an.relation,
        roles=roles_of(an),
        raw_action=an.action,
        source_name=name,
        source_version=version,
        known_action=an.known_action or None,
        pmids=list(an.pmids),
        organism=an.organism,
        retrieved_at=retrieved,
    )


def annotation_id(store: EvidenceStore, an: Annotation) -> str:
    src = "drugbank" if an.source.startswith("DrugBank") else "chembl-moa"
    return f"annot:{src}:{store.ids[an.drug]}:{store.proteins[an.protein]['uniprot']}:{an.relation}"


# ----------------------------------------------------------- findings --------
def _group(store: EvidenceStore, drug: int) -> dict[tuple[int, str], list[Annotation]]:
    out: dict[tuple[int, str], list[Annotation]] = defaultdict(list)
    for an in store.annotations_of(drug):
        out[(an.protein, an.relation)].append(an)
    return out


def _roles(ans: list[Annotation]) -> list[str]:
    roles = sorted({r for an in ans for r in roles_of(an)} - {"unspecified"})
    return roles or ["unspecified"]


def findings(store: EvidenceStore, a: int, b: int) -> tuple[list[MechanismFinding], dict[str, AnnotationRef]]:
    ga, gb = _group(store, a), _group(store, b)
    shared = sorted(set(ga) & set(gb), key=lambda k: (k[1], store.proteins[k[0]]["gene"]))
    pk_records = [(d1, d2, y) for d1, d2, y in store.pair_records(a, b) if y in PK_DIRECTION]

    out: list[MechanismFinding] = []
    refs: dict[str, AnnotationRef] = {}
    for p, rel in shared:
        ans_a, ans_b = ga[(p, rel)], gb[(p, rel)]
        for an in ans_a + ans_b:
            refs[annotation_id(store, an)] = annotation_ref(store, an)
        ids = sorted({annotation_id(store, an) for an in ans_a + ans_b})
        ra, rb = _roles(ans_a), _roles(ans_b)
        organism = next((an.organism for an in ans_a + ans_b if an.organism), "")
        prot = protein_out(store, p, rel, organism)

        def make(pattern, actor=None, affected=None, consistent=()):
            return MechanismFinding(
                id=f"mech:{prot.uniprot}:{rel}:{pattern}" + (f":{store.ids[actor]}" if actor is not None else ""),
                protein=prot, relation=rel, pattern=pattern,
                actor_drug_id=store.ids[actor] if actor is not None else None,
                affected_drug_id=store.ids[affected] if affected is not None else None,
                roles_a=ra, roles_b=rb, annotation_ids=ids,
                consistent_with_records=list(consistent),
            )

        produced = False
        if rel in PK_RELATIONS:
            for actor, affected, r_act, r_aff in ((a, b, ra, rb), (b, a, rb, ra)):
                if "substrate" not in r_aff:
                    continue
                for role, pattern in (("inhibitor", "inhibitor_substrate"), ("inducer", "inducer_substrate")):
                    if role in r_act:
                        # The export's order is used only for types whose
                        # order was verified (direction.py); otherwise a
                        # record of the right kind counts in either order.
                        consistent = sorted(
                            record_id(store, d1, d2, y) for d1, d2, y in pk_records
                            if PK_DIRECTION[y][0] == role and rel in PK_DIRECTION[y][1]
                            and ((d1 == actor and d2 == affected)
                                 or orientation_status(y, store.direction_audit) != "consistent")
                        )
                        out.append(make(pattern, actor, affected, consistent))
                        produced = True
            if not produced and "substrate" in ra and "substrate" in rb:
                out.append(make("shared_substrate"))
                produced = True
        else:
            if {"activating"} == set(ra) and {"inhibiting"} == set(rb) or \
               {"inhibiting"} == set(ra) and {"activating"} == set(rb):
                out.append(make("opposing_target_action"))
                produced = True
            elif set(ra) == set(rb) and set(ra) <= {"activating", "inhibiting"} and len(ra) == 1:
                out.append(make("same_direction_target_action"))
                produced = True
        if not produced:
            out.append(make("shared_annotation"))

    order = {"inhibitor_substrate": 0, "inducer_substrate": 1, "opposing_target_action": 2,
             "same_direction_target_action": 3, "shared_substrate": 4, "shared_annotation": 5}
    out.sort(key=lambda f: (order[f.pattern], -len(f.consistent_with_records), f.protein.gene))
    return out, refs


# ----------------------------------------------------------- pathways --------
def _curated_proteins(store: EvidenceStore, drug: int) -> set[int]:
    return {an.protein for an in store.annotations_of(drug)}


def shared_pathways(store: EvidenceStore, a: int, b: int, limit: int = 12) -> tuple[list[SharedPathway], int]:
    """Reactome pathways reached by both drugs' curated proteins, most specific first.

    Specificity is the number of proteins the pathway holds in this dataset:
    "Biological oxidations" contains hundreds and says little; a pathway with
    eight members says more. That ordering is a presentation choice, not a
    measure of relevance to the interaction.
    """
    pa, pb = _curated_proteins(store, a), _curated_proteins(store, b)
    via_a: dict[int, set[int]] = defaultdict(set)
    via_b: dict[int, set[int]] = defaultdict(set)
    for p in pa:
        for w in store.pathways_of.get(p, {}):
            via_a[w].add(p)
    for p in pb:
        for w in store.pathways_of.get(p, {}):
            via_b[w].add(p)
    both = set(via_a) & set(via_b)
    # Pathways reached through a protein BOTH drugs act on come first; within
    # each group, smaller (more specific) pathways first.
    ranked = sorted(both, key=lambda w: (not (via_a[w] & via_b[w]),
                                         store.pathways[w]["n_proteins"], store.pathways[w]["name"]))
    gene = lambda p: store.proteins[p]["gene"]  # noqa: E731
    out = [
        SharedPathway(
            id=store.pathways[w]["id"], name=store.pathways[w]["name"],
            n_proteins_in_pathway=store.pathways[w]["n_proteins"],
            via_a=sorted(gene(p) for p in via_a[w]), via_b=sorted(gene(p) for p in via_b[w]),
        )
        for w in ranked[:limit]
    ]
    return out, len(both)


def coverage(store: EvidenceStore, drug: int) -> dict[str, int]:
    out = {"target": 0, "enzyme": 0, "transporter": 0, "carrier": 0}
    for p, rel in {(an.protein, an.relation) for an in store.annotations_of(drug)}:
        out[rel] += 1
    return out


MECHANISM_NOTE = Bi(
    ru="Ниже — задокументированные роли каждого препарата по отдельности (DrugBank, ChEMBL) и то, как они складываются. Это гипотезы о механизме, а не доказательство взаимодействия: базы не указывают силу действия и долю участия белка в переработке препарата.",
    en="Below are each drug's documented roles on their own (DrugBank, ChEMBL) and how they line up. These are mechanism hypotheses, not evidence of an interaction: the databases do not record strength of effect or how much of a drug's processing a protein handles.",
)


def mechanism_block(store: EvidenceStore, a: int, b: int) -> MechanismBlock:
    found, refs = findings(store, a, b)
    paths, n_paths = shared_pathways(store, a, b)
    return MechanismBlock(
        findings=found, shared_pathways=paths, n_shared_pathways_total=n_paths,
        annotations=refs,
        coverage={store.ids[a]: coverage(store, a), store.ids[b]: coverage(store, b)},
        note=MECHANISM_NOTE,
    )


# --------------------------------------------------------------- graph -------
GRAPH_LEGEND = {
    "annotation": Bi(ru="Задокументированная связь препарата с белком (DrugBank / ChEMBL)",
                     en="Documented drug-protein relation (DrugBank / ChEMBL)"),
    "pathway_membership": Bi(ru="Белок участвует в биологическом пути (Reactome)",
                             en="Protein belongs to a biological pathway (Reactome)"),
    "documented_interaction": Bi(ru="Задокументированное взаимодействие (запись DrugBank)",
                                 en="Documented interaction (DrugBank record)"),
    "shared": Bi(ru="Общий белок или путь — повод присмотреться, а не доказательство",
                 en="Shared protein or pathway — a reason to look closer, not proof"),
}


def mechanism_graph(store: EvidenceStore, a: int, b: int, per_drug: int = 10, n_pathways: int = 8) -> MechanismGraph:
    """Drug A, drug B, their curated proteins and the most specific shared pathways.

    Every shared protein is included. Non-shared proteins are capped per drug,
    pharmacokinetic relations first (where interactions most often arise), and
    the number left out is reported rather than hidden.
    """
    ida, idb = store.ids[a], store.ids[b]
    ga, gb = _group(store, a), _group(store, b)
    shared = set(ga) & set(gb)
    rel_rank = {"enzyme": 0, "transporter": 1, "carrier": 2, "target": 3}

    def own(g, other):
        keys = [k for k in g if k not in other]
        keys.sort(key=lambda k: (rel_rank[k[1]], store.proteins[k[0]]["gene"]))
        return keys[:per_drug], max(0, len(keys) - per_drug)

    own_a, cut_a = own(ga, gb)
    own_b, cut_b = own(gb, ga)

    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []

    def drug_node(i: int, side: str):
        e = store.lexicon.entries[i]
        nodes[e.id] = GraphNode(id=e.id, kind="drug", label=e.inn or e.id, side=side,
                                detail={"inn": e.inn, "name_ru": e.inn_ru})

    drug_node(a, "a")
    drug_node(b, "b")

    def protein_node(p: int, rel: str, side: str, organism: str):
        pid = f"P:{store.proteins[p]['uniprot']}"
        if pid not in nodes:
            prot = protein_out(store, p, rel, organism)
            nodes[pid] = GraphNode(id=pid, kind="protein", label=prot.gene, side=side,
                                   detail=prot.model_dump())
        return pid

    def add_edges(drug: int, keyset, g, side_for):
        for p, rel in keyset:
            ans = g[(p, rel)]
            pid = protein_node(p, rel, side_for(p, rel), ans[0].organism)
            for an in ans:
                ref = annotation_ref(store, an)
                edges.append(GraphEdge(
                    id=ref.id, source=store.ids[drug], target=pid, kind="annotation",
                    established=True,
                    detail={"relation": rel, "roles": ref.roles, "raw_action": an.action,
                            "source": ref.source_name, "source_version": ref.source_version,
                            "pmids": ref.pmids, "known_action": ref.known_action},
                ))

    side = lambda p, rel: "shared" if (p, rel) in shared else None  # noqa: E731
    add_edges(a, sorted(shared) + own_a, ga, lambda p, rel: side(p, rel) or "a")
    add_edges(b, sorted(shared) + own_b, gb, lambda p, rel: side(p, rel) or "b")

    paths, _ = shared_pathways(store, a, b, limit=n_pathways)
    shown = {nodes[n].detail["uniprot"]: n for n in nodes if nodes[n].kind == "protein"}
    for sp in paths:
        wid = f"W:{sp.id}"
        nodes[wid] = GraphNode(id=wid, kind="pathway", label=sp.name, side="pathway",
                               detail={"reactome_id": sp.id, "n_proteins_in_pathway": sp.n_proteins_in_pathway,
                                       "source": sp.source})
        w = store.pathway_index[sp.id]
        for p, codes in ((p, store.pathways_of[p][w]) for p in store.pathways_of if w in store.pathways_of[p]):
            uni = store.proteins[p]["uniprot"]
            if uni in shown:
                edges.append(GraphEdge(
                    id=f"pw:{uni}:{sp.id}", source=shown[uni], target=wid,
                    kind="pathway_membership", established=True,
                    detail={"reactome_evidence_codes": codes.split("|") if codes else []},
                ))

    for d1, d2, y in store.pair_records(a, b):
        edges.append(GraphEdge(
            id=record_id(store, d1, d2, y), source=store.ids[d1], target=store.ids[d2],
            kind="documented_interaction", established=True,
            detail={"template": store.ddi_types[y], "source": store.sources["tdc_drugbank"]["name"]},
        ))

    return MechanismGraph(
        drug_a=ida, drug_b=idb, nodes=list(nodes.values()), edges=edges,
        truncated={"proteins_a": cut_a, "proteins_b": cut_b},
        legend=GRAPH_LEGEND,
    )
