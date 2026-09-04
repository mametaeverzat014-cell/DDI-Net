// Russian glosses for the descriptive label strings that come out of
// build_frozen_data.py (model names, hypothesis comparisons, evaluation views,
// conclusions, checkpoint note).
//
// WHY A LOOKUP AND NOT A TRANSLATION IN THE BUILD SCRIPT: frozen.json is
// regenerated from the immutable tag; keeping the glosses here means the frozen
// pipeline stays untouched. Every lookup FALLS BACK to the English string, so a
// label that changes upstream shows through in English rather than silently
// picking up a stale or wrong Russian one.
//
// Canonical tokens inside these labels — M0…M4, S2, S3, CONTROL A/C/F,
// BIO-GINE, BIO-RF, RF, GINE, H-V2-n — are NOT translated. They are the names
// the artifacts and the manuscript use.
import type { Lang } from "../i18n";

const RU: Record<string, string> = {
  // model / ladder labels
  "BIO-GINE M4": "BIO-GINE M4",
  "Aligned molecular GINE (M0)": "Молекулярный GINE, выровненный (M0)",
  "Aligned Dual (GINE + DDI network)": "Dual, выровненный (GINE + сеть DDI)",
  "BIO-RF": "BIO-RF",
  "Biological-degree-only RF (CONTROL A)": "RF только по биологическим степеням (CONTROL A)",
  "BIO-GINE M4, shuffled biology (CONTROL F)": "BIO-GINE M4, перемешанная биология (CONTROL F)",
  "M4 (primary)": "M4 (основная)",
  "M4 SUM (CONTROL C)": "M4 SUM (CONTROL C)",
  "M4 shuffled (CONTROL F)": "M4 перемешанная (CONTROL F)",

  // hypothesis comparisons
  "BIO-GINE M4 vs aligned molecular GINE": "BIO-GINE M4 против выровненного молекулярного GINE",
  "BIO-GINE M4 vs aligned Dual": "BIO-GINE M4 против выровненного Dual",
  "True biology vs degree-preserving shuffled biology": "Настоящая биология против перемешанной с сохранением степеней",
  "BIO-GINE M4 vs biological-degree-only RF": "BIO-GINE M4 против RF только по биологическим степеням",
  "Pathway-covered vs uncovered gain": "Прирост при покрытии путями против непокрытых",

  // evaluation views
  "pooled drug-holdout": "объединённый тест с отложенными препаратами",
  "S3 (both drugs held out)": "S3 (оба препарата отложены)",
  "subgroup contrast": "контраст подгрупп",

  // conclusions
  Supported: "Подтверждена",
  "Exploratory direction unsupported": "Поисковое направление не подтвердилось",

  // checkpoint
  "Frozen inference checkpoint not installed on this deployment.":
    "Замороженный файл весов модели на этом развёртывании не установлен.",
};

/** Gloss a frozen-artifact label. Falls back to the English string verbatim. */
export function gloss(s: string, lang: Lang): string {
  return lang === "ru" ? RU[s] ?? s : s;
}
