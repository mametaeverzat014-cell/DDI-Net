#!/usr/bin/env python3
"""Real-label benchmark units: FDA label sentences that name a second drug.

Source text: the 200 structured product labels of the TAC 2017 Adverse Drug
Reaction track (Demner-Fushman D, Shooshan SE, Rodriguez L, et al. A dataset
of 200 structured product labels annotated for adverse drug reactions. Sci Data
5, 180001 (2018)), as redistributed with section text in the OnSIDES
repository (github.com/tatonetti-lab/onsides, data licence CC BY 4.0; the label
text itself is a U.S. Government work). Pinned commit, SHA-256 enforced.

These are HISTORICAL labels (about 2016-2017), not current labelling, and only
three sections are present: Boxed Warning, Warnings and Precautions, Adverse
Reactions. The engine reads the first two (it never reads Adverse Reactions),
so units are built from those two only.

A unit is one (label, partner drug) pair. Its excerpts are exactly what the
engine's label adapter would retrieve: OpenFdaLabelAdapter.find_mentions with
the partner's international name, at most 3 sentences per section.

Split: TAC's own train labels -> development, TAC's test labels -> evaluation
(different drugs' labels). A seeded random sample of pairs is drawn from each.
Gold annotations are written by hand in a separate file
(validation/clinical_outcomes/real_label_benchmark/annotations.jsonl) under the
rules in ANNOTATION_RULES.md of that directory.

    python scripts/data/build_real_label_benchmark.py
"""

from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from ddinet.data.git_fetch import PinnedFiles, fetch, verify  # noqa: E402
from serving.evidence.adapters.openfda import Label, OpenFdaLabelAdapter  # noqa: E402
from serving.evidence.store import EvidenceStore  # noqa: E402

SPEC = PinnedFiles(
    key="onsides_tac",
    repo_url="https://github.com/tatonetti-lab/onsides",
    commit="fe6a4a4e3415d93d02245692df9fd8277c6177e4",
    files={
        "database/annotations/demner-fushman-train-labels.json":
            "d7bc860201288b136a7931a199df29195a7dfec06a9957f7ece510b569ed7f9d",
        "database/annotations/demner-fushman-test-labels.json":
            "1c3614b1fcaffaddc78c8719ba77b42a5d22d31db27d8ba2d30edc27ee4dcf00",
    },
)
OUT = ROOT / "validation" / "clinical_outcomes" / "real_label_benchmark"
SEED = 20261018
N = {"development": 50, "evaluation": 100}
SECTION_FIELD = {"boxed warnings": "boxed_warning", "warnings and precautions": "warnings_and_cautions"}


def labels_of(path: Path) -> dict[str, Label]:
    out: dict[str, dict[str, str]] = {}
    for x in json.loads(path.read_text()):
        f = SECTION_FIELD.get(x["section_name"])
        if f:
            out.setdefault(x["label_id"], {})[f] = re.sub(r"\s+", " ", x["section_text"]).strip()
    return {lab: Label(set_id=f"TAC2017:{lab}", spl_id="", version="", effective_time="", generic_names=[],
                       brand_names=[lab], substance_names=[], product_type="HUMAN PRESCRIPTION DRUG",
                       sections=secs, retrieval_url="") for lab, secs in out.items()}


def main() -> None:
    src = fetch(SPEC)
    files = verify(SPEC, src)
    store = EvidenceStore.load()
    partners = sorted({e.inn.lower() for e in store.lexicon.entries if e.inn and len(e.inn) >= 4})
    rng = random.Random(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {"source": SPEC.repo_url, "commit": SPEC.commit, "files": files, "seed": SEED, "n": N,
            "citation": "Demner-Fushman D et al. Sci Data 5, 180001 (2018) (TAC 2017 ADR labels), via OnSIDES",
            "licence": "OnSIDES data CC BY 4.0; FDA label text is a U.S. Government work",
            "label_date": "historical labels used for TAC 2017 (about 2016-2017); not current labelling"}
    for split, fname in (("development", "train"), ("evaluation", "test")):
        labels = labels_of(src / f"database/annotations/demner-fushman-{fname}-labels.json")
        candidates = []
        for lab in sorted(labels):
            for p in partners:
                ex = OpenFdaLabelAdapter.find_mentions(labels[lab], [p])
                if ex:
                    candidates.append((lab, p, ex))
        rng.shuffle(candidates)
        units = []
        for k, (lab, p, ex) in enumerate(sorted(candidates[:N[split]], key=lambda c: (c[0], c[1]))):
            e, _ = store.lexicon.lookup_name(p)
            units.append({"unit": f"{split[:3]}-{k + 1:03d}", "split": split, "label": lab, "partner": p,
                          "partner_id": e.id if e else None,
                          "excerpts": [{"section": x.section, "text": x.text, "no_effect_wording": x.no_effect_wording,
                                        "also_in": x.also_in} for x in ex]})
        meta[f"{split}_candidates"] = len(candidates)
        (OUT / f"{split}_units.jsonl").write_text("".join(json.dumps(u, ensure_ascii=False) + "\n" for u in units))
        print(split, "candidate pairs", len(candidates), "sampled", len(units))
    (OUT / "UNITS_MANIFEST.json").write_text(json.dumps(meta, indent=1) + "\n")


if __name__ == "__main__":
    main()
