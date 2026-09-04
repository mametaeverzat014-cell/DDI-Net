"""Export a compact drug dataset for the Drug Explorer.

Reads the frozen mechanism_v1 parquet on this branch and writes
web/public/data/drugs.json — fetched lazily by the Explorer, so it never bloats
the main bundle. Only fields that genuinely exist are exported.

NAMES. The frozen dataset carries no human-readable name (its `name` column is a
copy of the DrugBank ID), so none is taken from there and none is invented.
Instead the real INN is joined in from DrugCentral's structures export on
InChIKey; drugs that do not match keep no name and are shown by DrugBank ID
alone. A Russian label is derived from the INN by rule-based transliteration
(drug_names.py) and is flagged in the payload as a UI label, not sourced data.
The DrugBank ID stays the canonical identifier and is never replaced.

Biology per drug is capped at a preview (top proteins / pathways) to bound the
file; the drug's true totals are shown alongside, so the preview never
masquerades as the full set.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from drug_names import transliterate_inn  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data" / "mechanism_v1"
DRUGCENTRAL = REPO / "data" / "raw" / "drugcentral" / "structures.smiles.tsv"
OUT = REPO / "web" / "public" / "data" / "drugs.json"

PREVIEW_PROTEINS = 12
PREVIEW_PATHWAYS = 12

drugs = pd.read_parquet(DATA / "drugs.parquet")
dp = pd.read_parquet(DATA / "drug_protein_edges.parquet")
proteins = pd.read_parquet(DATA / "proteins.parquet").set_index("uniprot_accession")
pp = pd.read_parquet(DATA / "protein_pathway_edges.parquet")

# distinct (drug, protein, relation, evidence) — collapse re-assertions
dp = dp.drop_duplicates(subset=["drugbank_id", "uniprot_id", "relation_type", "evidence_type"])

# protein -> pathways lookup (name kept, capped later per drug)
prot_paths: dict[str, list[tuple[str, str]]] = {}
for _, r in pp.drop_duplicates(subset=["uniprot_accession", "reactome_pathway_id"]).iterrows():
    prot_paths.setdefault(r.uniprot_accession, []).append((r.reactome_pathway_id, r.pathway_name))

by_drug = dp.groupby("drugbank_id")

# --------------------------------------------------------------- drug names
# English names are REAL: DrugCentral's INN column, joined on InChIKey. Drugs
# that do not match get no name and are shown by DrugBank ID alone — nothing is
# invented. Russian names are a rule-based transliteration of the INN and are a
# UI label only (flagged as such in the payload).
inn_by_inchikey: dict[str, str] = {}
if DRUGCENTRAL.exists():
    dc = pd.read_csv(DRUGCENTRAL, sep="\t", low_memory=False)
    for _, r in dc[["InChIKey", "INN"]].dropna().iterrows():
        inn_by_inchikey.setdefault(str(r.InChIKey), str(r.INN))

records = []
for _, d in drugs.iterrows():
    did = d.drugbank_id
    prot_rows = by_drug.get_group(did) if did in by_drug.groups else dp.iloc[0:0]

    prot_list = []
    seen_prot: set[str] = set()  # dedup by protein so preview count matches n_proteins
    seen_paths: dict[str, str] = {}
    for _, pr in prot_rows.iterrows():
        acc = pr.uniprot_id
        meta = proteins.loc[acc] if acc in proteins.index else None
        gene = (meta.gene_name if meta is not None and pd.notna(meta.gene_name) else "") if meta is not None else ""
        pname = (meta.protein_name if meta is not None and pd.notna(meta.protein_name) else "") if meta is not None else ""
        if acc not in seen_prot and len(prot_list) < PREVIEW_PROTEINS:
            seen_prot.add(acc)
            prot_list.append({
                "uniprot": acc, "gene": gene, "protein_name": pname,
                "relation": pr.relation_type, "evidence": pr.evidence_type,
                "source": pr.evidence_source,
            })
        for pid, pn in prot_paths.get(acc, []):
            if pid not in seen_paths:
                seen_paths[pid] = pn

    path_list = [{"reactome_id": k, "name": v} for k, v in list(seen_paths.items())[:PREVIEW_PATHWAYS]]

    # Counts are computed here from the edges the MODEL actually sees (keyed on
    # UniProt), not from drugs.parquet's n_proteins (which counts distinct
    # DrugBank protein_id and undercounts, because ChEMBL edges have null
    # protein_id). This keeps the displayed count consistent with the biological
    # representation and with the preview drawn from it.
    n_proteins_model = int(prot_rows.uniprot_id.nunique())
    n_pathways_model = len(seen_paths)

    inchikey = d.inchikey if pd.notna(d.inchikey) else None
    inn = inn_by_inchikey.get(inchikey) if inchikey else None
    inn_ru = transliterate_inn(inn) if inn else None

    records.append({
        "id": did,
        "inn": inn,
        "inn_ru": inn_ru,
        "name_source": "DrugCentral INN (matched on InChIKey)" if inn else None,
        "formula": d.formula if pd.notna(d.formula) else None,
        "mol_weight": round(float(d.mol_weight), 2) if pd.notna(d.mol_weight) else None,
        "n_heavy_atoms": int(d.n_heavy_atoms) if pd.notna(d.n_heavy_atoms) else None,
        "smiles": d.canonical_smiles if pd.notna(d.canonical_smiles) else None,
        "inchikey": d.inchikey if pd.notna(d.inchikey) else None,
        "groups": d.groups if pd.notna(d.groups) else None,
        "drug_type": d.drug_type if pd.notna(d.drug_type) else None,
        "n_targets": int(d.n_targets), "n_enzymes": int(d.n_enzymes),
        "n_transporters": int(d.n_transporters), "n_carriers": int(d.n_carriers),
        "n_proteins": n_proteins_model, "n_pathways": n_pathways_model,
        "has_reactome": bool(d.has_reactome), "has_chembl": bool(d.has_chembl),
        "proteins_preview": prot_list,
        "pathways_preview": path_list,
    })

OUT.parent.mkdir(parents=True, exist_ok=True)
n_named = sum(1 for r in records if r["inn"])
payload = {
    "meta": {
        "n_drugs": len(records),
        "note": "Compact export of the frozen mechanism_v1 universe. The DrugBank ID is the canonical identifier and is never replaced. Protein/pathway lists are previews capped per drug — the drug's true totals are given as n_proteins / n_pathways.",
        "preview_caps": {"proteins": PREVIEW_PROTEINS, "pathways": PREVIEW_PATHWAYS},
        "names": {
            "n_with_inn": n_named,
            "coverage_pct": round(100 * n_named / len(records), 2),
            "en_source": "DrugCentral structures export, INN column, joined on InChIKey. Real data.",
            "ru_source": "Rule-based transliteration of the INN, generated by web/tools/drug_names.py.",
            "ru_is_transliteration": True,
            "ru_warning": "Russian names are UI labels only. They are NOT sourced from DrugBank, DrugCentral or any database, and must not be presented as such.",
        },
        "source": "data/mechanism_v1/*.parquet; data/raw/drugcentral/structures.smiles.tsv",
    },
    "drugs": records,
}
OUT.write_text(json.dumps(payload, separators=(",", ":")))
size_kb = OUT.stat().st_size / 1024
print(f"wrote {OUT.relative_to(REPO)}  ({len(records)} drugs, {size_kb:.0f} KB)")
