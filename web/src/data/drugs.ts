// Lazy loader for the compact drug dataset. The file lives in public/ and is
// fetched once on first Explorer visit, so it never enters the main bundle.
// import.meta.env.BASE_URL keeps the path correct under a subpath deployment.

export interface ProteinPreview {
  uniprot: string;
  gene: string;
  protein_name: string;
  relation: string;
  evidence: string;
  source: string;
}
export interface PathwayPreview { reactome_id: string; name: string; }

export interface Drug {
  id: string;
  formula: string | null;
  mol_weight: number | null;
  n_heavy_atoms: number | null;
  smiles: string | null;
  inchikey: string | null;
  groups: string | null;
  drug_type: string | null;
  n_targets: number; n_enzymes: number; n_transporters: number; n_carriers: number;
  n_proteins: number; n_pathways: number;
  has_reactome: boolean; has_chembl: boolean;
  proteins_preview: ProteinPreview[];
  pathways_preview: PathwayPreview[];
}

export interface DrugDataset {
  meta: { n_drugs: number; note: string; preview_caps: { proteins: number; pathways: number }; source: string };
  drugs: Drug[];
}

let cache: Promise<DrugDataset> | null = null;

export function loadDrugs(): Promise<DrugDataset> {
  if (!cache) {
    const url = `${import.meta.env.BASE_URL}data/drugs.json`;
    cache = fetch(url).then((r) => {
      if (!r.ok) throw new Error(`failed to load drug dataset (${r.status})`);
      return r.json() as Promise<DrugDataset>;
    });
  }
  return cache;
}
