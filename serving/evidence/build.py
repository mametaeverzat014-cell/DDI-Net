"""Compile the evidence artifact from files committed to the repository.

    python -m serving.evidence.build            # writes runtime/evidence/

WHY AN ARTIFACT. The lean runtime image carries numpy and a web server, not
pandas or pyarrow, so it cannot read parquet. This script runs where pandas
exists (the Docker build stage, a developer machine, the test suite), reads the
frozen inputs, and writes one gzipped JSON document that the request path loads
with the standard library alone.

WHAT GOES IN, AND WHAT DELIBERATELY DOES NOT.

* Drug lexicon: DrugBank ID (canonical), the DrugCentral INN joined on InChIKey,
  and the rule-based Russian transliteration — carried with its flag, because
  it is a UI label and not data.
* DrugBank interaction records exactly as TDC shipped them: ordered
  (Drug1, Drug2, type) triples plus the type's sentence template. The order is
  kept: "#Drug1 may increase the anticoagulant activities of #Drug2" is not
  symmetric, and collapsing it would misattribute who affects whom.
* Curated drug-protein annotations: DrugBank v5.1 (with the drug's role —
  substrate, inhibitor, inducer, agonist ... — and PubMed IDs) and ChEMBL
  curated mechanism-of-action rows. ChEMBL *bioactivity* rows are excluded for
  the reason recorded in serving/shared_biology.py and
  reports/chembl_panel_artifact.md: shared assay panels make unrelated drugs
  look biologically related.
* Reactome pathway membership for the proteins above, with evidence codes.
* The seed-0 drug-level split, so the API can say whether the model saw a
  drug — and a pair's label — during training.

Nothing here is a model output, and the model never reads this artifact. Its
inputs are hashed into the metadata so a stale artifact is detectable.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "runtime" / "evidence"
ARTIFACT_NAME = "evidence_v1.json.gz"
SCHEMA_VERSION = 1

MECH = ROOT / "data" / "mechanism_v1"
INPUTS = {
    "drugs": MECH / "drugs.parquet",
    "drug_protein_edges": MECH / "drug_protein_edges.parquet",
    "proteins": MECH / "proteins.parquet",
    "pathways": MECH / "pathways.parquet",
    "protein_pathway_edges": MECH / "protein_pathway_edges.parquet",
    "split_assignments": MECH / "split_assignments.csv",
    "tdc_drugbank": ROOT / "data" / "raw" / "drugbank.tab.gz",
    "drug_names": ROOT / "web" / "public" / "data" / "drugs.json",
}

#: Evidence sources admitted to the annotation table. See the module docstring.
ANNOTATION_SOURCES = ("DrugBank_v5.1", "ChEMBL_36_drug_mechanism")

#: Facts about the TDC/DrugBank source, copied from DATA_PROVENANCE.md §1 so
#: the API can cite them without reading markdown at request time.
TDC_SOURCE = {
    "name": "DrugBank DDI records via Therapeutics Data Commons",
    "loader": "PyTDC 1.1.15, tdc.multi_pred.DDI(name='DrugBank')",
    "retrieved": "2026-08-24",
    "url": "https://tdcommons.ai/multi_pred_tasks/ddi/",
    "license": "TDC: CC BY 4.0; underlying DrugBank content: DrugBank non-commercial licence",
    "sha256": "cd2c99aa483a9917356047477ddbd1f8d792017be3d66fc8415af8b7dfeff883",
}

DRUGBANK_SOURCE = {
    "name": "DrugBank drug-protein annotations",
    "version": "5.1 (export 2025-01-02)",
    "retrieved": "2026-08-28",
}

CHEMBL_MOA_SOURCE = {
    "name": "ChEMBL curated mechanism of action",
    "version": "36",
    "retrieved": "2026-08-28",
}

REACTOME_SOURCE = {
    "name": "Reactome (UniProt2Reactome, all levels)",
    "retrieved": "2026-08-28",
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _str(x) -> str:
    """pandas NA / None / float NaN -> ""; everything else -> stripped str."""
    if x is None:
        return ""
    if isinstance(x, float) and x != x:
        return ""
    s = str(x).strip()
    return "" if s.lower() in ("nan", "none", "<na>") else s


def build_payload() -> dict:
    import pandas as pd

    missing = [str(p.relative_to(ROOT)) for p in INPUTS.values() if not p.exists()]
    if missing:
        raise FileNotFoundError(f"evidence build inputs missing: {missing}")

    # -- drugs: order is the frozen universe order --------------------------
    drugs = pd.read_parquet(INPUTS["drugs"])
    ids = [str(d) for d in drugs["drugbank_id"]]
    index = {d: i for i, d in enumerate(ids)}

    names = json.loads(INPUTS["drug_names"].read_text(encoding="utf-8"))
    by_id = {d["id"]: d for d in names["drugs"]}
    if set(by_id) != set(ids):
        raise ValueError("drugs.json and drugs.parquet disagree on the universe")

    split = pd.read_csv(INPUTS["split_assignments"])
    split = split[(split["scheme"] == "drug") & (split["seed"] == 0)]
    split_of = dict(zip(split["project_drug_id"], split["assignment"]))
    if set(split_of) != set(ids):
        raise ValueError("seed-0 drug split does not cover the universe exactly")

    # The model's has_protein condition: at least one drug-protein edge from any
    # source (1,638 drugs). Kept so coverage can be reported without the model.
    all_edges = pd.read_parquet(INPUTS["drug_protein_edges"], columns=["drugbank_id"])
    annotated = set(all_edges["drugbank_id"])

    drug_rows = []
    for d, groups, dtype in zip(ids, drugs["groups"], drugs["drug_type"]):
        n = by_id[d]
        drug_rows.append({
            "id": d,
            "inn": n.get("inn"),
            "inn_ru": n.get("inn_ru"),
            "inchikey": n.get("inchikey"),
            "groups": _str(groups),
            "drug_type": _str(dtype),
            "split_seed0": split_of[d],
            "has_protein_any": d in annotated,
        })

    # -- DrugBank interaction records (TDC), order preserved ----------------
    templates: dict[int, str] = {}
    records: set[tuple[int, int, int]] = set()
    with gzip.open(INPUTS["tdc_drugbank"], "rt", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            y = int(row["Y"])
            tpl = row["Map"]
            if templates.setdefault(y, tpl) != tpl:
                raise ValueError(f"type {y} carries two different templates")
            a, b = row["ID1"], row["ID2"]
            if a in index and b in index:
                records.add((index[a], index[b], y))
    ddi_records = sorted(records)

    # -- curated annotations -------------------------------------------------
    edges = pd.read_parquet(INPUTS["drug_protein_edges"])
    edges = edges[edges["evidence_source"].isin(ANNOTATION_SOURCES)]
    edges = edges[edges["drugbank_id"].isin(index)]

    proteins = pd.read_parquet(INPUTS["proteins"])
    pmeta = {
        _str(u): (_str(g), _str(n), _str(o))
        for u, g, n, o in zip(proteins["uniprot_accession"], proteins["gene_name"],
                              proteins["protein_name"], proteins["organism"])
    }
    used = sorted({_str(u) for u in edges["uniprot_id"] if _str(u)})
    pidx = {u: i for i, u in enumerate(used)}
    protein_rows = []
    for u in used:
        g, n, o = pmeta.get(u, ("", "", ""))
        # An absent symbol falls back to the accession; a blank chip could not
        # be looked up by anyone.
        protein_rows.append({"uniprot": u, "gene": g or u, "name": n or u, "organism": o})

    src_index = {s: i for i, s in enumerate(ANNOTATION_SOURCES)}
    seen: set[tuple] = set()
    annotation_rows = []
    for row in edges.itertuples(index=False):
        u = _str(row.uniprot_id)
        if not u:
            continue
        key = (index[row.drugbank_id], pidx[u], _str(row.relation_type),
               _str(row.action).lower(), src_index[row.evidence_source])
        if key in seen:
            continue
        seen.add(key)
        annotation_rows.append([
            *key,
            _str(row.known_action),
            _str(row.pmids),
            _str(row.organism),
        ])
    annotation_rows.sort(key=lambda r: (r[0], r[1], r[2], r[4], r[3]))

    # -- Reactome ------------------------------------------------------------
    ppe = pd.read_parquet(INPUTS["protein_pathway_edges"])
    size: dict[str, set] = defaultdict(set)
    for u, p in zip(ppe["uniprot_accession"], ppe["reactome_pathway_id"]):
        size[_str(p)].add(_str(u))
    pw = pd.read_parquet(INPUTS["pathways"])
    pw_name = dict(zip(pw["pathway_id"].map(_str), pw["pathway_name"].map(_str)))

    codes: dict[tuple[str, str], set] = defaultdict(set)
    for u, p, c in zip(ppe["uniprot_accession"], ppe["reactome_pathway_id"], ppe["evidence_code"]):
        u, p = _str(u), _str(p)
        if u in pidx:
            codes[(u, p)].add(_str(c))
    used_pw = sorted({p for _, p in codes})
    pwidx = {p: i for i, p in enumerate(used_pw)}
    pathway_rows = [
        {"id": p, "name": pw_name.get(p, p), "n_proteins": len(size[p])} for p in used_pw
    ]
    membership = sorted(
        [pidx[u], pwidx[p], "|".join(sorted(c for c in cs if c))]
        for (u, p), cs in codes.items()
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "universe": "DDI_MECH_1705_V1",
        "sources": {
            "tdc_drugbank": TDC_SOURCE,
            "drugbank_annotations": DRUGBANK_SOURCE,
            "chembl_moa": CHEMBL_MOA_SOURCE,
            "reactome": REACTOME_SOURCE,
            "names": {
                "en": names["meta"]["names"]["en_source"],
                "ru": names["meta"]["names"]["ru_source"],
                "ru_is_transliteration": True,
            },
        },
        "annotation_sources": list(ANNOTATION_SOURCES),
        "drugs": drug_rows,
        "ddi_types": {str(k): templates[k] for k in sorted(templates)},
        "ddi_records": [list(r) for r in ddi_records],
        "proteins": protein_rows,
        "annotations": annotation_rows,
        "pathways": pathway_rows,
        "pathway_membership": membership,
    }


def add_direction_audit(payload: dict) -> dict:
    """Measure, per interaction type, whether the export's drug order is usable.

    Computed here, once, from the same payload the API serves, so the table the
    API applies is exactly the one recorded in the build metadata. See
    serving/evidence/direction.py.
    """
    from .direction import audit
    from .store import EvidenceStore

    table = audit(EvidenceStore(payload))
    payload["direction_audit"] = {str(k): table[k] for k in sorted(table)}
    return payload


def write(payload: dict, out_dir: Path = OUT_DIR) -> dict:
    """Deterministic: same inputs give byte-identical output (gzip mtime=0)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9, mtime=0) as gz:
        gz.write(raw)
    path = out_dir / ARTIFACT_NAME
    path.write_bytes(buf.getvalue())

    meta = {
        "artifact": ARTIFACT_NAME,
        "schema_version": SCHEMA_VERSION,
        "sha256": hashlib.sha256(buf.getvalue()).hexdigest(),
        "size_bytes": len(buf.getvalue()),
        "n_drugs": len(payload["drugs"]),
        "n_ddi_records": len(payload["ddi_records"]),
        "n_ddi_types": len(payload["ddi_types"]),
        "n_annotations": len(payload["annotations"]),
        "n_proteins": len(payload["proteins"]),
        "n_pathways": len(payload["pathways"]),
        "direction_audit": payload.get("direction_audit"),
        "inputs": {
            k: {"path": str(p.relative_to(ROOT)), "sha256": _sha256(p)}
            for k, p in INPUTS.items()
        },
    }
    (out_dir / "evidence_v1.meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta


def main() -> None:
    print(json.dumps(write(add_direction_audit(build_payload())), indent=2))


if __name__ == "__main__":
    main()
