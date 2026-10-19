"""Drug-name resolution against the frozen 1,705-drug universe.

WHAT IS RESOLVED LOCALLY, AND ON WHAT AUTHORITY.

* DrugBank IDs — the canonical identifier, matched exactly.
* English INNs — DrugCentral's INN column joined on InChIKey (real data).
* Russian names — a rule-based transliteration of the INN. It is accepted as a
  search key because a Russian-speaking user will type it, but it is never
  presented as a sourced name.
* Salt and hydrate forms ("warfarin sodium", "metformin hydrochloride") are
  reduced to the parent name only when the full string matched nothing, so a
  substance whose INN itself contains such a word ("magnesium sulfate") still
  matches as written.

WHAT IS NOT RESOLVED LOCALLY. Brand names and non-INN synonyms (USAN
"acetaminophen" for INN "paracetamol") have no verified mapping in this
repository. They go to RxNorm when that source is reachable (adapters/rxnorm.py)
and are otherwise reported as unresolved — never guessed.

A near miss produces *suggestions*, never a silent substitution: picking
"hydroxyzine" for a typed "hydralazine" would answer a question nobody asked.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field

#: Counter-ion and hydrate words removed when the full name finds nothing.
SALT_WORDS = frozenset({
    "sodium", "potassium", "calcium", "magnesium", "lithium", "zinc",
    "hydrochloride", "hcl", "dihydrochloride", "hydrobromide", "sulfate",
    "sulphate", "bisulfate", "phosphate", "maleate", "mesylate", "mesilate",
    "besylate", "besilate", "tartrate", "bitartrate", "citrate", "acetate",
    "succinate", "fumarate", "bromide", "chloride", "nitrate", "lactate",
    "gluconate", "tosylate", "malate", "oxalate", "propionate", "valerate",
    "dipropionate", "hyclate", "monohydrate", "dihydrate", "trihydrate",
    "hydrate", "anhydrous", "disodium", "trisodium", "dipotassium",
    # Russian counterparts of the most common forms.
    "натрия", "калия", "кальция", "магния", "гидрохлорид", "сульфат",
    "фосфат", "малеат", "мезилат", "безилат", "тартрат", "цитрат", "ацетат",
    "сукцинат", "фумарат", "бромид", "хлорид", "моногидрат", "дигидрат",
})

#: US (USAN) and other common names that differ from the INN used in this
#: dataset. PROJECT-CURATED, not sourced from a database: each pair is a
#: well-documented naming difference, every target is checked by a test to be an
#: INN present in the data, and a match through this list is reported as
#: ``curated_alias`` so the interface can say so. RxNorm, when reachable, covers
#: far more names than this list.
ALIASES: dict[str, str] = {
    "acetaminophen": "paracetamol",
    "aspirin": "acetylsalicylic acid",
    "albuterol": "salbutamol",
    "levalbuterol": "levosalbutamol",
    "glyburide": "glibenclamide",
    "meperidine": "pethidine",
    "adrenaline": "epinephrine",
    "noradrenaline": "norepinephrine",
    "lignocaine": "lidocaine",
    "frusemide": "furosemide",
    "cyclosporine": "ciclosporin",
    "cyclosporin": "ciclosporin",
    "cephalexin": "cefalexin",
    "isoproterenol": "isoprenaline",
    "dicyclomine": "dicycloverine",
    "mesalamine": "mesalazine",
    "methimazole": "thiamazole",
    "nitroglycerin": "glyceryl trinitrate",
    "meclizine": "meclozine",
    "propoxyphene": "dextropropoxyphene",
    "chlorpheniramine": "chlorphenamine",
    "aciclovir": "acyclovir",
    "valacyclovir": "valaciclovir",
    "clomiphene": "clomifene",
    "dextroamphetamine": "dexamfetamine",
    "amphetamine": "amfetamine",
    "metaproterenol": "orciprenaline",
    "hydroxyurea": "hydroxycarbamide",
    "ergonovine": "ergometrine",
    "penicillin g": "benzylpenicillin",
    "penicillin v": "phenoxymethylpenicillin",
    "glycopyrrolate": "glycopyrronium bromide",
    "bendrofluazide": "bendroflumethiazide",
    "amoxycillin": "amoxicillin",
    "6-mercaptopurine": "mercaptopurine",
    # Common Russian names that are not transliterations of the INN.
    "аспирин": "acetylsalicylic acid",
    "адреналин": "epinephrine",
    "норадреналин": "norepinephrine",
    "ацикловир": "acyclovir",
    "циклоспорин": "ciclosporin",
}

DRUGBANK_ID = re.compile(r"^DB\d{5}$", re.IGNORECASE)

#: Characters a drug name can legitimately contain. Anything else is refused at
#: the API boundary before it reaches a lookup or an external query.
ALLOWED_INPUT = re.compile(r"^[\w\s\-\.,'()/+]{1,100}$", re.UNICODE)


def normalize(text: str) -> str:
    """Case, accent, punctuation and whitespace-insensitive form of a name."""
    s = unicodedata.normalize("NFKD", text)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.casefold().replace("ё", "е")
    s = re.sub(r"[^\w]+", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def strip_salts(norm: str) -> str:
    kept = [w for w in norm.split(" ") if w not in SALT_WORDS]
    return " ".join(kept)


@dataclass(frozen=True)
class DrugEntry:
    index: int
    id: str
    inn: str | None
    inn_ru: str | None
    inchikey: str | None
    groups: str
    drug_type: str
    split_seed0: str
    has_protein_any: bool = False

    def display(self, lang: str = "ru") -> str:
        if lang == "ru" and self.inn_ru:
            return self.inn_ru
        return self.inn or self.id


@dataclass
class Resolution:
    query: str
    status: str                       # resolved | suggestions | not_found | invalid
    drug: DrugEntry | None = None
    matched_on: str | None = None     # drugbank_id | inn | inn_ru_transliteration | inn_without_salt | curated_alias | rxnorm_ingredient
    suggestions: list[DrugEntry] = field(default_factory=list)
    note: str | None = None
    rxnorm: dict | None = None        # filled by the RxNorm adapter when used


class DrugLexicon:
    def __init__(self, drugs: list[dict]) -> None:
        self.entries: list[DrugEntry] = [
            DrugEntry(
                index=i, id=d["id"], inn=d.get("inn"), inn_ru=d.get("inn_ru"),
                inchikey=d.get("inchikey"), groups=d.get("groups", ""),
                drug_type=d.get("drug_type", ""), split_seed0=d["split_seed0"],
                has_protein_any=bool(d.get("has_protein_any", False)),
            )
            for i, d in enumerate(drugs)
        ]
        self.by_id = {e.id: e for e in self.entries}
        self._by_inn: dict[str, DrugEntry] = {}
        self._by_ru: dict[str, DrugEntry] = {}
        for e in self.entries:
            if e.inn:
                self._by_inn.setdefault(normalize(e.inn), e)
            if e.inn_ru:
                self._by_ru.setdefault(normalize(e.inn_ru), e)
        self._names = sorted(set(self._by_inn) | set(self._by_ru))

    def __len__(self) -> int:
        return len(self.entries)

    def get(self, drug_id: str) -> DrugEntry | None:
        return self.by_id.get(drug_id.strip().upper())

    def lookup_name(self, name: str) -> tuple[DrugEntry | None, str | None]:
        """Exact (normalised) INN match, then transliteration, then salt-stripped."""
        n = normalize(name)
        if not n:
            return None, None
        if n in self._by_inn:
            return self._by_inn[n], "inn"
        if n in self._by_ru:
            return self._by_ru[n], "inn_ru_transliteration"
        bare = strip_salts(n)
        if bare and bare != n:
            if bare in self._by_inn:
                return self._by_inn[bare], "inn_without_salt"
            if bare in self._by_ru:
                return self._by_ru[bare], "inn_ru_transliteration"
        for key in (n, bare):
            target = ALIASES.get(key)
            if target and normalize(target) in self._by_inn:
                return self._by_inn[normalize(target)], "curated_alias"
        return None, None

    def suggest(self, name: str, limit: int = 5) -> list[DrugEntry]:
        n = strip_salts(normalize(name)) or normalize(name)
        if len(n) < 3:
            return []
        hits = difflib.get_close_matches(n, self._names, n=limit * 2, cutoff=0.75)
        # Prefix matches catch truncated input ("atorva") that edit distance misses.
        hits += [k for k in self._names if k.startswith(n)][:limit]
        out: list[DrugEntry] = []
        for k in hits:
            e = self._by_inn.get(k) or self._by_ru.get(k)
            if e and e not in out:
                out.append(e)
        return out[:limit]

    def resolve(self, query: str) -> Resolution:
        q = (query or "").strip()
        if not q or not ALLOWED_INPUT.match(q):
            return Resolution(query=q[:100], status="invalid",
                              note="Empty input or characters a drug name cannot contain.")
        if DRUGBANK_ID.match(q):
            e = self.get(q)
            if e:
                return Resolution(query=q, status="resolved", drug=e, matched_on="drugbank_id")
            return Resolution(
                query=q, status="not_found",
                note="Valid DrugBank ID format, but not one of the 1,705 drugs in the "
                     "frozen research universe.")
        e, how = self.lookup_name(q)
        if e:
            return Resolution(query=q, status="resolved", drug=e, matched_on=how)
        sug = self.suggest(q)
        if sug:
            return Resolution(query=q, status="suggestions", suggestions=sug,
                              note="No exact match. Similar names are listed; none was "
                                   "chosen automatically.")
        return Resolution(query=q, status="not_found",
                          note="No match among DrugBank IDs and INN names of the frozen "
                               "universe. Brand names need the RxNorm source.")
