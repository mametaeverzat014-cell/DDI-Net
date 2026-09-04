"""Drug names: real English INN + a rule-based Russian transliteration.

PROVENANCE — read this before trusting a name.

English names are REAL DATA: the INN (International Nonproprietary Name) column
of DrugCentral's structures export, joined to our universe on InChIKey. Nothing
is invented. Drugs that do not match keep no name at all and are shown by their
DrugBank ID alone.

Russian names are NOT data. They are produced here by a rule-based
transliteration of the INN, following the conventions the Russian pharmacopoeia
uses for INN (ph->ф, th->т, c+e/i/y->ц, x->кс, ...). They exist ONLY as UI
labels so a Russian-speaking reader can find a drug. They are explicitly flagged
`ru_is_transliteration: true` and must never be presented as data from DrugBank,
DrugCentral, or any other source.
"""

from __future__ import annotations

import re

# Multi-character sequences first; order matters (longest match wins).
_SEQ: list[tuple[str, str]] = [
    ("sch", "ш"), ("sh", "ш"), ("ch", "х"), ("ph", "ф"), ("th", "т"),
    ("qu", "кв"), ("ck", "к"), ("kh", "х"), ("zh", "ж"),
    ("oo", "у"), ("ee", "и"), ("ou", "у"), ("ae", "е"), ("oe", "е"),
    ("ia", "иа"), ("io", "ио"), ("ie", "ие"), ("iu", "иу"),
    ("ya", "я"), ("yu", "ю"), ("ye", "е"), ("yo", "ё"),
]

_SINGLE: dict[str, str] = {
    "a": "а", "b": "б", "c": "к", "d": "д", "e": "е", "f": "ф", "g": "г",
    "h": "г", "i": "и", "j": "й", "k": "к", "l": "л", "m": "м", "n": "н",
    "o": "о", "p": "п", "q": "к", "r": "р", "s": "с", "t": "т", "u": "у",
    "v": "в", "w": "в", "x": "кс", "y": "и", "z": "з",
}

#: Words that are translated rather than transliterated. These are ordinary
#: chemical-nomenclature words, not drug identities.
_WORD: dict[str, str] = {
    "acid": "кислота",
    "sodium": "натрия",
    "potassium": "калия",
    "calcium": "кальция",
    "magnesium": "магния",
    "chloride": "хлорид",
    "sulfate": "сульфат",
    "sulphate": "сульфат",
    "phosphate": "фосфат",
    "hydrochloride": "гидрохлорид",
    "oxide": "оксид",
    "citrate": "цитрат",
    "acetate": "ацетат",
    "carbonate": "карбонат",
    "nitrate": "нитрат",
    "bromide": "бромид",
    "iodide": "йодид",
    "water": "вода",
    "alcohol": "спирт",
    "oil": "масло",
}

#: Adjective endings that become Russian feminine forms before "кислота".
_ACID_ADJ = [("ic", "овая"), ("ous", "истая")]

#: Acids whose established Russian adjective is not the default "-овая".
#: Small and explicit — a guess here would be visibly wrong to a pharmacologist.
_ACID_EXCEPTIONS: dict[str, str] = {
    "ascorbic": "аскорбиновая",
    "folic": "фолиевая",
    "folinic": "фолиниевая",
    "nicotinic": "никотиновая",
    "valproic": "вальпроевая",
    "retinoic": "ретиноевая",
    "tranexamic": "транексамовая",
    "aminocaproic": "аминокапроновая",
    "ursodeoxycholic": "урсодезоксихолевая",
    "acetylsalicylic": "ацетилсалициловая",
    "salicylic": "салициловая",
    "citric": "лимонная",
    "acetic": "уксусная",
    "lactic": "молочная",
    "boric": "борная",
    "benzoic": "бензойная",
    "fusidic": "фузидиевая",
    "mycophenolic": "микофеноловая",
    "zoledronic": "золедроновая",
    "alendronic": "алендроновая",
    "pamidronic": "памидроновая",
    "ibandronic": "ибандроновая",
    "clavulanic": "клавулановая",
    "hyaluronic": "гиалуроновая",
}


def _translit_word(w: str) -> str:
    """Transliterate one Latin token into Cyrillic by INN conventions."""
    s = w.lower()
    # a trailing silent -e is dropped: 'chloride' -> handled by _WORD, but e.g.
    # 'dopamine' -> 'допамин' rather than 'допамине'.
    if len(s) > 3 and s.endswith("e") and s[-2] not in "aeiou":
        s = s[:-1]

    out: list[str] = []
    i = 0
    while i < len(s):
        # soft c/g before front vowels: c->ц (g stays г, as Russian INN does)
        if s[i] == "c" and i + 1 < len(s) and s[i + 1] in "eiy":
            out.append("ц")
            i += 1
            continue
        matched = False
        for src, dst in _SEQ:
            if s.startswith(src, i):
                out.append(dst)
                i += len(src)
                matched = True
                break
        if matched:
            continue
        out.append(_SINGLE.get(s[i], s[i]))
        i += 1
    return "".join(out)


def transliterate_inn(inn: str) -> str:
    """INN -> Russian UI label. Rule-based, not a sourced translation."""
    if not inn:
        return ""
    tokens = re.split(r"([\s\-])", inn.strip())
    words = [t for t in tokens if t.strip() and t not in ("-", " ")]

    # "<adj> acid" -> "<adj-овая> кислота"
    if len(words) == 2 and words[-1].lower() == "acid":
        stem = words[0].lower()
        if stem in _ACID_EXCEPTIONS:
            return f"{_ACID_EXCEPTIONS[stem]} кислота"
        for suf, ru_suf in _ACID_ADJ:
            if stem.endswith(suf):
                return f"{_translit_word(stem[: -len(suf)])}{ru_suf} кислота"
        return f"{_translit_word(stem)}овая кислота"

    out: list[str] = []
    for t in tokens:
        if not t.strip() or t in ("-", " "):
            out.append(t)
            continue
        low = t.lower()
        out.append(_WORD[low] if low in _WORD else _translit_word(t))
    return "".join(out).strip()


if __name__ == "__main__":
    # Spot-check against names whose Russian spelling is well established.
    checks = [
        "metformin", "warfarin", "ibuprofen", "paracetamol", "ciclosporin",
        "gentamicin", "ascorbic acid", "bivalirudin", "desmopressin",
        "daptomycin", "phenylalanine", "choline", "amoxicillin", "digoxin",
        "simvastatin", "omeprazole", "ceftriaxone", "hydrochlorothiazide",
    ]
    for c in checks:
        print(f"  {c:<24} -> {transliterate_inn(c)}")
