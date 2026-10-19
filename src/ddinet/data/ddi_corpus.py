"""DDI Corpus 2013 (Herrero-Zazo et al.) — evaluation data, never committed.

Licence: Creative Commons Attribution-NonCommercial 4.0 (stated in the
corpus README). Used here only to MEASURE the label extraction rules on real,
independently annotated sentences; nothing from it is served by the app or
stored in the repository. The zip is fetched at a pinned commit of the
authors' repository (github.com/isegura/DDICorpus), checked by SHA-256 and
cached under data/raw/ddi_corpus/ (git-ignored).

Each sentence lists drug mentions and every mention pair, annotated
``ddi="true"`` with a type (mechanism / effect / advise / int) or
``ddi="false"`` (no interaction stated between that pair). The official split
is kept: Train = development, Test = evaluation.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .git_fetch import PinnedFiles

ZIP = "DDICorpus-2013.zip"
SPEC = PinnedFiles(
    key="ddi_corpus",
    repo_url="https://github.com/isegura/DDICorpus",
    commit="819b0fa538ed83ab2a8b4f5417bba3c03249b7f3",
    files={ZIP: "87fc63e32ebce20d9841c372e0c594ec72d60882ab5621550ca73c3eaf80ab60"},
)
LICENSE = "CC BY-NC 4.0 (corpus README); evaluation only, not redistributed"
CITATION = ("Herrero-Zazo M, Segura-Bedmar I, Martínez P, Declerck T. The DDI corpus: an annotated corpus with "
            "pharmacological substances and drug-drug interactions. J Biomed Inform 46(5):914-920 (2013).")


@dataclass(frozen=True)
class PairExample:
    split: str            #: "train" (development) or "test" (evaluation)
    subcorpus: str        #: "DrugBank" or "MedLine"
    document: str         #: file stem, e.g. "Hydroxyurea_ddi" (DrugBank: the drug the text is about)
    sentence_id: str
    sentence: str
    e1: str
    e1_type: str
    e2: str
    e2_type: str
    ddi: bool
    ddi_type: str | None


def _split_of(name: str) -> str | None:
    if "/Train/" in name:
        return "train"
    if "/Test/Test for DDI Extraction task/" in name:
        return "test"
    return None


def read_pairs(zip_path: Path) -> list[PairExample]:
    """Every annotated mention pair of the DDI-extraction part of the corpus."""
    out: list[PairExample] = []
    with zipfile.ZipFile(zip_path) as z:
        for name in sorted(z.namelist()):
            split = _split_of(name)
            if not split or not name.endswith(".xml"):
                continue
            sub = "DrugBank" if "/DrugBank/" in name else "MedLine"
            # The archive is pinned by SHA-256, so its content is the published corpus.
            root = ET.fromstring(z.read(name))
            stem = Path(name).stem
            for s in root.iter("sentence"):
                ents = {e.get("id"): (e.get("text") or "", e.get("type") or "") for e in s.iter("entity")}
                for p in s.iter("pair"):
                    (t1, ty1), (t2, ty2) = ents.get(p.get("e1"), ("", "")), ents.get(p.get("e2"), ("", ""))
                    ddi = (p.get("ddi") or "").lower() == "true"
                    out.append(PairExample(split, sub, stem, s.get("id") or "", s.get("text") or "",
                                           t1, ty1, t2, ty2, ddi, p.get("type") if ddi else None))
    return out


_WORD = re.compile(r"[^a-z0-9]+")


def document_drug(stem: str) -> str:
    """'Hydroxyurea_ddi' -> 'hydroxyurea' (DrugBank sub-corpus file names)."""
    return _WORD.sub(" ", stem.lower().removesuffix("_ddi")).strip()
