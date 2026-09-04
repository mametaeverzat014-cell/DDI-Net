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
  /** Real INN from DrugCentral, matched on InChIKey. null when unmatched. */
  inn: string | null;
  /** Rule-based transliteration of the INN — a UI label, not sourced data. */
  inn_ru: string | null;
  name_source: string | null;
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
  meta: {
    n_drugs: number;
    note: string;
    preview_caps: { proteins: number; pathways: number };
    names: {
      n_with_inn: number; coverage_pct: number;
      en_source: string; ru_source: string;
      ru_is_transliteration: boolean; ru_warning: string;
    };
    source: string;
  };
  drugs: Drug[];
}

/** Search across ID, English INN, Russian transliteration and formula. */
export function matchesQuery(d: Drug, q: string): boolean {
  const s = q.trim().toLowerCase();
  if (!s) return false;
  return (
    d.id.toLowerCase().includes(s) ||
    (d.inn ?? "").toLowerCase().includes(s) ||
    (d.inn_ru ?? "").toLowerCase().includes(s) ||
    (d.formula ?? "").toLowerCase().includes(s)
  );
}

/** Display label for a drug in the given UI language; ID is always kept. */
export function drugLabel(d: Drug, lang: "ru" | "en"): string {
  const name = lang === "ru" ? d.inn_ru ?? d.inn : d.inn;
  return name ? `${name} · ${d.id}` : d.id;
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
