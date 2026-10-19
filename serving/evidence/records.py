"""Documented interaction records from the DrugBank export shipped with TDC.

THE STATEMENT IS THE SOURCE'S, NOT OURS. Each TDC row carries an interaction
type and DrugBank's sentence template for it ("The metabolism of #Drug2 can be
decreased when combined with #Drug1."). The API returns that template with the
two names filled in, marked ``source_template_filled``, and keeps the template
itself alongside. Nothing is paraphrased into a stronger or weaker claim.

DIRECTION IS KEPT. TDC rows are ordered; "#Drug1 may increase the anticoagulant
activities of #Drug2" names who affects whom. Collapsing the pair to unordered
form — which the model training rightly does — would misattribute that here.

NO SEVERITY. The export carries no severity grade, so none is reported. The
Russian sentences below are the project's translations of DrugBank's templates,
offered so a Russian reader can follow; the English original is always shown
with them.

TWO EXPLICIT TABLES, both readable against the template text:

* ``PK_DIRECTION`` — the 8 templates that state a pharmacokinetic direction
  (metabolism, serum concentration, excretion, active metabolite up or down).
  Used only to check whether documented drug-protein roles are *consistent*
  with a record; never to create a record.
* ``OPPOSING_TYPES`` — template pairs that assert opposite effects on the same
  quantity of the same drug. Two such records for one pair are a conflict and
  are reported as one, not averaged.
"""

from __future__ import annotations

import re

from .direction import orientation_status
from .schema import Bi, Conflict, EvidenceCategory, EvidenceRecord
from .store import EvidenceStore

#: Project translations of DrugBank's 86 templates. Placeholders are preserved;
#: the drug names are inserted with "препарат", which keeps them in the
#: nominative — a transliterated name cannot be declined reliably.
TEMPLATE_RU: dict[int, str] = {
    1: "#Drug1 может усиливать фотосенсибилизирующее действие препарата #Drug2.",
    2: "#Drug1 может усиливать антихолинергическое действие препарата #Drug2.",
    3: "Биодоступность препарата #Drug2 может снижаться при сочетании с препаратом #Drug1.",
    4: "Метаболизм препарата #Drug2 может ускоряться при сочетании с препаратом #Drug1.",
    5: "#Drug1 может ослаблять сосудосуживающее действие препарата #Drug2.",
    6: "#Drug1 может усиливать антикоагулянтное действие препарата #Drug2.",
    7: "#Drug1 может усиливать ототоксическое действие препарата #Drug2.",
    8: "Терапевтическая эффективность препарата #Drug2 может повышаться при сочетании с препаратом #Drug1.",
    9: "#Drug1 может усиливать гипогликемическое действие препарата #Drug2.",
    10: "#Drug1 может усиливать антигипертензивное действие препарата #Drug2.",
    11: "Концентрация активных метаболитов препарата #Drug2 в сыворотке может снижаться при сочетании с препаратом #Drug1, что ведёт к потере эффективности.",
    12: "#Drug1 может ослаблять антикоагулянтное действие препарата #Drug2.",
    13: "Всасывание препарата #Drug2 может снижаться при сочетании с препаратом #Drug1.",
    14: "#Drug1 может ослаблять бронхорасширяющее действие препарата #Drug2.",
    15: "#Drug1 может усиливать кардиотоксическое действие препарата #Drug2.",
    16: "#Drug1 может усиливать угнетающее действие препарата #Drug2 на центральную нервную систему.",
    17: "#Drug1 может ослаблять нервно-мышечное блокирующее действие препарата #Drug2.",
    18: "#Drug1 может усиливать всасывание препарата #Drug2, повышая его концентрацию в сыворотке и, возможно, усиливая нежелательные эффекты.",
    19: "#Drug1 может усиливать сосудосуживающее действие препарата #Drug2.",
    20: "#Drug1 может усиливать действие препарата #Drug2, удлиняющее интервал QTc.",
    21: "#Drug1 может усиливать нервно-мышечное блокирующее действие препарата #Drug2.",
    22: "#Drug1 может усиливать нежелательное нервно-мышечное действие препарата #Drug2.",
    23: "#Drug1 может усиливать стимулирующее действие препарата #Drug2.",
    24: "#Drug1 может усиливать гипокальциемическое действие препарата #Drug2.",
    25: "#Drug1 может усиливать действие препарата #Drug2, блокирующее атриовентрикулярную проводимость (АВ-блокада).",
    26: "#Drug1 может ослаблять антиагрегантное действие препарата #Drug2.",
    27: "#Drug1 может усиливать нейровозбуждающее действие препарата #Drug2.",
    28: "#Drug1 может усиливать нежелательное действие препарата #Drug2 на кожу.",
    29: "#Drug1 может ослаблять мочегонное действие препарата #Drug2.",
    30: "#Drug1 может усиливать ортостатическое гипотензивное действие препарата #Drug2.",
    31: "Риск или выраженность повышения давления могут увеличиваться при сочетании препарата #Drug2 с препаратом #Drug1.",
    32: "#Drug1 может усиливать седативное действие препарата #Drug2.",
    33: "Риск или выраженность удлинения интервала QTc могут увеличиваться при сочетании препарата #Drug1 с препаратом #Drug2.",
    34: "#Drug1 может усиливать иммуносупрессивное действие препарата #Drug2.",
    35: "#Drug1 может усиливать нейротоксическое действие препарата #Drug2.",
    36: "#Drug1 может усиливать антипсихотическое действие препарата #Drug2.",
    37: "#Drug1 может ослаблять антигипертензивное действие препарата #Drug2.",
    38: "#Drug1 может усиливать сосудорасширяющее действие препарата #Drug2.",
    39: "#Drug1 может усиливать способность препарата #Drug2 вызывать запор.",
    40: "#Drug1 может усиливать угнетающее действие препарата #Drug2 на дыхание.",
    41: "#Drug1 может усиливать гипотензивное действие препарата #Drug2 и его угнетающее действие на центральную нервную систему.",
    42: "Риск или выраженность гиперкалиемии могут увеличиваться при сочетании препарата #Drug1 с препаратом #Drug2.",
    43: "Связывание препарата #Drug2 с белками может снижаться при сочетании с препаратом #Drug1.",
    44: "#Drug1 может усиливать центральное нейротоксическое действие препарата #Drug2.",
    45: "#Drug1 может снижать эффективность препарата #Drug2 как диагностического средства.",
    46: "#Drug1 может усиливать бронхосуживающее действие препарата #Drug2.",
    47: "Метаболизм препарата #Drug2 может замедляться при сочетании с препаратом #Drug1.",
    48: "#Drug1 может усиливать способность препарата #Drug2 вызывать миопатию и рабдомиолиз.",
    49: "Риск или выраженность нежелательных эффектов могут увеличиваться при сочетании препарата #Drug1 с препаратом #Drug2.",
    50: "Риск или выраженность сердечной недостаточности могут увеличиваться при сочетании препарата #Drug2 с препаратом #Drug1.",
    51: "#Drug1 может усиливать гиперкальциемическое действие препарата #Drug2.",
    52: "#Drug1 может ослаблять обезболивающее действие препарата #Drug2.",
    53: "#Drug1 может усиливать антиагрегантное действие препарата #Drug2.",
    54: "#Drug1 может усиливать брадикардическое действие препарата #Drug2 (урежение пульса).",
    55: "#Drug1 может усиливать гипонатриемическое действие препарата #Drug2.",
    56: "Риск или выраженность снижения давления могут увеличиваться при сочетании препарата #Drug1 с препаратом #Drug2.",
    57: "#Drug1 может усиливать нефротоксическое действие препарата #Drug2.",
    58: "#Drug1 может ослаблять кардиотоксическое действие препарата #Drug2.",
    59: "#Drug1 может усиливать ульцерогенное действие препарата #Drug2 (способность вызывать язвы).",
    60: "#Drug1 может усиливать гипотензивное действие препарата #Drug2.",
    61: "#Drug1 может ослаблять стимулирующее действие препарата #Drug2.",
    62: "Биодоступность препарата #Drug2 может повышаться при сочетании с препаратом #Drug1.",
    63: "#Drug1 может усиливать миелосупрессивное действие препарата #Drug2 (угнетение кроветворения).",
    64: "#Drug1 может усиливать серотонинергическое действие препарата #Drug2.",
    65: "#Drug1 может ускорять выведение препарата #Drug2, что может снижать его уровень в сыворотке и, возможно, эффективность.",
    66: "Риск или выраженность кровотечения могут увеличиваться при сочетании препарата #Drug1 с препаратом #Drug2.",
    67: "#Drug1 может снижать всасывание препарата #Drug2, уменьшая его концентрацию в сыворотке и, возможно, эффективность.",
    68: "#Drug1 может усиливать гиперкалиемическое действие препарата #Drug2.",
    69: "#Drug1 может усиливать обезболивающее действие препарата #Drug2.",
    70: "Терапевтическая эффективность препарата #Drug2 может снижаться при сочетании с препаратом #Drug1.",
    71: "#Drug1 может усиливать гипертензивное действие препарата #Drug2.",
    72: "#Drug1 может замедлять выведение препарата #Drug2, что может повышать его уровень в сыворотке.",
    73: "Концентрация препарата #Drug2 в сыворотке может повышаться при сочетании с препаратом #Drug1.",
    74: "#Drug1 может усиливать действие препарата #Drug2, задерживающее жидкость в организме.",
    75: "Концентрация препарата #Drug2 в сыворотке может снижаться при сочетании с препаратом #Drug1.",
    76: "#Drug1 может ослаблять седативное действие препарата #Drug2.",
    77: "Концентрация активных метаболитов препарата #Drug2 в сыворотке может повышаться при сочетании с препаратом #Drug1.",
    78: "#Drug1 может усиливать гипергликемическое действие препарата #Drug2.",
    79: "#Drug1 может усиливать угнетающее действие препарата #Drug2 на центральную нервную систему и его гипертензивное действие.",
    80: "#Drug1 может усиливать гепатотоксическое действие препарата #Drug2.",
    81: "#Drug1 может усиливать тромбогенное действие препарата #Drug2.",
    82: "#Drug1 может усиливать аритмогенное действие препарата #Drug2.",
    83: "#Drug1 может усиливать гипокалиемическое действие препарата #Drug2.",
    84: "#Drug1 может усиливать вазопрессорное действие препарата #Drug2.",
    85: "#Drug1 может усиливать тахикардическое действие препарата #Drug2.",
    86: "Риск реакции гиперчувствительности к препарату #Drug2 повышается при сочетании с препаратом #Drug1.",
}

#: type -> (role Drug1 would need, relations where that role would be relevant).
#: "inhibitor": the template says Drug2 is processed more slowly / reaches a
#: higher level. "inducer": faster / lower. Read straight off the template text.
PK_DIRECTION: dict[int, tuple[str, frozenset[str]]] = {
    47: ("inhibitor", frozenset({"enzyme"})),                 # metabolism of Drug2 decreased
    11: ("inhibitor", frozenset({"enzyme"})),                 # active metabolites of Drug2 reduced
    73: ("inhibitor", frozenset({"enzyme", "transporter"})),  # serum concentration of Drug2 increased
    72: ("inhibitor", frozenset({"transporter"})),            # excretion rate of Drug2 decreased
    4: ("inducer", frozenset({"enzyme"})),                    # metabolism of Drug2 increased
    77: ("inducer", frozenset({"enzyme"})),                   # active metabolites of Drug2 increased
    75: ("inducer", frozenset({"enzyme", "transporter"})),    # serum concentration of Drug2 decreased
    65: ("inducer", frozenset({"transporter"})),              # excretion rate of Drug2 increased
}

#: Pairs of templates asserting opposite effects on the same quantity of #Drug2.
OPPOSING_TYPES: frozenset[frozenset[int]] = frozenset(frozenset(p) for p in [
    (73, 75), (4, 47), (11, 77), (65, 72), (3, 62), (13, 18), (67, 18),
    (8, 70), (6, 12), (26, 53), (10, 37), (32, 76), (23, 61), (5, 19),
    (17, 21), (15, 58),
])

QUALIFIERS = [
    "DrugBank's standard sentence for this interaction type, not a quotation from a study or a label.",
    "This export carries no severity grade. None is implied.",
    "The export does not state the basis of each record (clinical study, label text, or inference from pharmacological properties).",
]

_PLACEHOLDER = re.compile(r"#Drug[12]")


def _fill(template: str, d1: str, d2: str) -> str:
    return template.replace("#Drug1", d1).replace("#Drug2", d2)


def neutral_en(template: str) -> str:
    """Fill a template without saying which drug is which.

    The placeholder met first becomes "one of the two drugs", its repeats
    "that drug", the other placeholder "the other drug".
    """
    first: list[str] = []

    def sub(m: re.Match) -> str:
        ph = m.group(0)
        if not first:
            first.append(ph)
            return "one of the two drugs"
        return "that drug" if ph == first[0] else "the other drug"

    out = _PLACEHOLDER.sub(sub, template)
    return out[0].upper() + out[1:]


#: Russian needs the case of each slot, so the neutral forms are spelled out per
#: grammatical frame used in TEMPLATE_RU: (frame, first-mention, other-drug).
_RU_FRAMES = [
    ("с препаратом {}", "с одним из двух препаратов", "с другим препаратом"),
    ("препарату {}", "одному из двух препаратов", "другому препарату"),
    ("препарата {}", "одного из двух препаратов", "другого препарата"),
    ("{}", "один из двух препаратов", "другой препарат"),
]


def neutral_ru(template: str) -> str:
    seen: list[str] = []
    out = template
    for ph in sorted(set(_PLACEHOLDER.findall(template)), key=template.index):
        seen.append(ph)
    for ph in seen:
        is_first = ph == seen[0]
        for frame, first_form, other_form in _RU_FRAMES:
            pattern = frame.format(ph)
            while pattern in out:
                form = first_form if is_first else other_form
                if is_first and out.count(ph) < template.count(ph):
                    form = {"с одним из двух препаратов": "с этим препаратом",
                            "одному из двух препаратов": "этому препарату",
                            "одного из двух препаратов": "этого препарата",
                            "один из двух препаратов": "этот препарат"}[first_form]
                out = out.replace(pattern, form, 1)
    return out[0].upper() + out[1:]


def record_id(store: EvidenceStore, a: int, b: int, y: int) -> str:
    return f"drugbank-tdc:{store.ids[a]}>{store.ids[b]}:t{y}"


def _direction_qualifier(y: int, status: str, check: dict | None) -> str | None:
    if status == "symmetric":
        return None
    if status == "as_exported_verified":
        return (f"Drug order checked for this interaction type against documented DrugBank roles: "
                f"consistent in {check['n_consistent']:,} of {check['n_informative']:,} checkable records.")
    if check and check.get("n_informative"):
        return (f"Drug order for this interaction type matched documented DrugBank roles in only "
                f"{check['n_consistent']:,} of {check['n_informative']:,} checkable records, so the "
                "statement is shown without naming which drug is affected.")
    return ("The export's drug order for this interaction type cannot be checked, and for checkable "
            "types it proved unreliable (reversed in about 90% of records for types 47 and 73), so "
            "the statement is shown without naming which drug is affected.")


def database_evidence(store: EvidenceStore, a: int, b: int) -> tuple[list[EvidenceRecord], list[Conflict]]:
    src = store.sources["tdc_drugbank"]
    records: list[EvidenceRecord] = []
    raw = store.pair_records(a, b)
    for d1, d2, y in raw:
        e1, e2 = store.lexicon.entries[d1], store.lexicon.entries[d2]
        tpl = store.ddi_types[y]
        status = orientation_status(y, store.direction_audit)
        direction = {"symmetric": "symmetric", "consistent": "as_exported_verified"}.get(status, "not_verified")
        check = store.direction_audit.get(y)
        if direction == "not_verified":
            statement, origin = neutral_en(tpl), "source_template_direction_neutral"
            ru_tpl = TEMPLATE_RU.get(y)
            statement_ru = neutral_ru(ru_tpl) if ru_tpl else None
        else:
            statement, origin = _fill(tpl, e1.inn or e1.id, e2.inn or e2.id), "source_template_filled"
            statement_ru = russian_statement_for(store, y, e1.id, e2.id)
        qualifiers = list(QUALIFIERS)
        dq = _direction_qualifier(y, direction, check)
        if dq:
            qualifiers.append(dq)
        records.append(EvidenceRecord(
            id=record_id(store, d1, d2, y),
            category=EvidenceCategory.DATABASE_INTERACTION_RECORD,
            source_name=src["name"],
            source_version=src["loader"],
            source_record_id=f"{e1.id}|{e2.id}|Y={y}",
            source_url=src["url"],
            original_identifiers={"drugbank_id_drug1_as_exported": e1.id,
                                  "drugbank_id_drug2_as_exported": e2.id,
                                  "tdc_interaction_type": str(y)},
            statement=statement,
            statement_origin=origin,
            source_template=tpl,
            direction=direction,
            direction_check=check,
            statement_ru=statement_ru,
            drug1_id=e1.id if direction != "not_verified" else None,
            drug2_id=e2.id if direction != "not_verified" else None,
            retrieved_at=src["retrieved"],
            license=src["license"],
            qualifiers=qualifiers,
        ))

    conflicts: list[Conflict] = []
    for i, (x1, x2, xy) in enumerate(raw):
        for (z1, z2, zy) in raw[i + 1:]:
            if frozenset((xy, zy)) not in OPPOSING_TYPES:
                continue
            # Same affected slot as exported; with an unverified order this is
            # the most the export supports, and the description says so.
            if x2 != z2:
                continue
            conflicts.append(Conflict(
                record_ids=[record_id(store, x1, x2, xy), record_id(store, z1, z2, zy)],
                affected_drug_id=store.ids[x2],
                description=Bi(
                    ru="Две записи источника утверждают противоположное об одном и том же "
                       "эффекте. Обе показаны как есть; общий вывод из них не составлен.",
                    en="Two source records assert opposite effects on the same quantity. "
                       "Both are shown as they are; no combined conclusion is drawn.",
                ),
            ))
    return records, conflicts


def russian_statement_for(store: EvidenceStore, y: int, drug1_id: str, drug2_id: str) -> str | None:
    """Project translation of a DrugBank record, names in the Russian UI form."""
    tpl = TEMPLATE_RU.get(y)
    if tpl is None:
        return None
    e1, e2 = store.lexicon.by_id[drug1_id], store.lexicon.by_id[drug2_id]
    text = _fill(tpl, e1.display("ru"), e2.display("ru"))
    return text[0].upper() + text[1:]
