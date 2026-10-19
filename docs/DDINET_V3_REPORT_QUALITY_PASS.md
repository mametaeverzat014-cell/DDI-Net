# DDI-Net 3.0 — Report quality pass (PDF and site)

A real 14-page Russian PDF for warfarin + fluconazole, exported from the Vercel
Preview, showed five weaknesses. Each was traced to its cause before it was
changed. The frozen BIO-GINE model, checkpoint, predictions, metrics and
training artifacts are untouched; no language model or paid service was added.

---

## 1. Duplicated evidence

**Cause.** fluconazole has an older-format (non-PLR) FDA label. It keeps its
"Drug Interactions" subsection inside PRECAUTIONS, and openFDA *also* returns
that subsection as a separate `drug_interactions` field. Every sentence naming
warfarin was therefore matched twice, under two section names, and became two
records. Six label records were really four sentences in two labels. The
report numbered them [1]…[6], and the explanation counted them, as if they
were six sources.

Reproduced with synthetic labels of the same structure
(`tests/synthetic_labels.py`; set IDs are all zeros, every sentence carries
"[synthetic]"). openFDA cannot be reached from the development container.

**Fix, at the source (API).**

* `serving/evidence/adapters/openfda.py`: within one label, a sentence that is
  identical, contained in another (≥ 40 characters, e.g. with a heading glued
  on), or a near-verbatim copy (word sets ≥ 90 % alike and lengths within 10 %)
  becomes one excerpt. The other section names are kept in `also_in`.
  Normalisation is lower case with every non-`[0-9a-z]` run as a separator.
  * Different sentences stay separate even when they name the same two drugs.
  * Different labels are never merged.
  * DrugBank records are never merged.
* `EvidenceRecord.also_in_sections` (new field), plus a qualifier on the record:
  "listed once: repeated text in one label is not separate evidence".
* `MultiPair.n_label_documents` (new field) is reported next to
  `n_label_records`.
* The explanation (`serving/evidence/explain.py`) makes one statement per label
  document, not per record. Its certainty statement reads, for example:
  "2 FDA label(s) (4 distinct excerpt(s)) and 1 DrugBank record(s). Several
  excerpts of one label are one source, not separate confirmations, and a
  DrugBank record may itself rest on label text."

**Fix, on the site and in the PDF.**

* `web/src/data/evidenceGroups.ts` groups the records into **source
  documents** (one SPL set ID, or the DrugBank export) and **distinct
  excerpts**, with the same rule as the server. This keeps responses from the
  API version still deployed on Render correct.
* Labels: `[n]` is a document and `[n.k]` an excerpt of it. A reference to
  every excerpt of a document collapses to `[n]`.
* Counts line, word for word the same on the site and in the PDF: "FDA label
  documents: 2 · distinct excerpts: 4 · DrugBank records: 1".
* PDF section 3:
  * a table of source documents;
  * one card per document with its distinct excerpts, the sections each was
    found in, the document's provenance and qualifiers.
* **Supplement S1** lists every record of the response as received: section,
  identifiers, URLs and retrieval time. A merged repeat is marked "same text as
  [2.1]".
* The companion JSON still carries the response verbatim. Appendix A adds
  `evidence_counts` and `source_documents` (with the raw record IDs per excerpt).

## 2. Executive summary

The summary is built deterministically from the payload (`pairBrief` in
`web/src/pdf/content.ts`). The status card is followed by an "In brief" line
(the counts, the number of hypotheses, the calibrated score) and five parts:

| Part | What it contains |
|---|---|
| What the official sources document | one line per source document: whose label names whom, in how many distinct excerpts and which sections; what a DrugBank record is and is not |
| What the quoted evidence directly says | the sources' own sentences, quoted verbatim (up to two per label, shortened only at a word boundary and marked "…"); the report adds no interpretation |
| What is only a hypothesis | each actor → affected route with its proteins and H-labels; "not tested for this pair"; agreement with a DrugBank record is not independent confirmation |
| What BIO-GINE adds | the score, regime and band; for a documented pair, that it adds no new evidence of interaction; the pooled test figure; the validation-pair caveat; what the score cannot say |
| What remains uncertain | unavailable sources, unverified DrugBank order, name-matched label excerpts, labels and DrugBank not necessarily independent, unknown inhibition strength, no per-pair uncertainty, no severity, individual factors |

**Direction.** The DrugBank export's drug order is unverified for most
interaction types, so no direction is taken from DrugBank. Label sentences are
quoted as written: a direction they state is the label's own statement, shown
as such. No direction is inferred from the mere fact that one drug's label
names the other.

Nothing in the summary grades severity, recommends anything or calls a
combination safe. The wording tests cover the new text.

## 3. Page-6 overlap

**Cause.** In `@react-pdf/renderer` 4.9.0, a View that splits across pages
gets a fixed height for its first part. Because the footer prints page
numbers, the page is laid out a second time, and the children are shrunk to
that height: every node gets `flexShrink` 1, and 0 is not honoured. An
evidence card is a padded box around a key/value list. Its last rows were
squeezed into the bottom margin, over the running footer.

This was reproduced with the synthetic duplicated-label report and a sweep of
excerpt lengths that moves the page break through the card: the Russian
lengths 7–13 overlapped.

A second fault surfaced while checking: section titles left alone at the
bottom of a page. A title that did not fit was *split* instead of moved, and
react-pdf checks `minPresenceAhead` only when a node does not split.

**Fix** (`web/src/pdf/components.tsx`, comment "PAGE BREAKS"):

* Only children of the page itself may split. Every other View is atomic.
* Long blocks are emitted as sequences of atomic page-level blocks:
  * key/value lists and bullet lists;
  * evidence cards, drawn as stacked segments (`Seg`) that look like one box;
  * the JSON appendix;
  * the glossary.
* Long quotations are cut into pieces no taller than a page.
* Titles are atomic and keep `minPresenceAhead`.
* Tables keep a repeating header, carry no border or padding on the splitting
  container, and draw their sides per row.

Two related defects were fixed on the way:

* **Inserted hyphens.** textkit draws a "-" at every forced break inside a
  word, so `tdc.multi_pred.DDI(name='DrugBank')` printed as `DDI(-name=…`. A
  two-space gap counts as such a break point, which put a stray "-" before
  references. References now follow a single space. Code-like text in narrow
  cells is wrapped explicitly (`SafeText`, mono), which adds no characters.
* **Cover overflow.** A cover with eight very long drug names overflowed onto a
  second page with no margins. Names on the cover are now shortened; the full
  names are in section 2.

**Regression tests** (`web/src/pdf/layout.test.ts`, 16 tests) render real and
synthetic reports and read them back with pdfjs-dist:

* Reports: W+F RU/EN, a graph report, a pair without label evidence, the
  duplicated and merged synthetic-label reports, a long-name pair, 5-, 6- and
  8-drug reports, 8 drugs with very long names, and the excerpt-length sweep.
* Every page is checked for:
  * nothing drawn in the top or bottom margin;
  * only the running header and footer text and their hairline rules inside
    the header and footer bands;
  * no two text lines drawn over each other;
  * the footer's "Page n of N" matching the real page count;
  * no blank page;
  * no page except the last less than 40 % filled. This rule catches a block
    that was moved instead of split: the glossary of a six-drug report once
    left 70 % of a page empty.

## 4. Metric labelling

**Verified in the frozen artifacts.**

* M4's test metrics exist only for the **pooled** drug-disjoint test and for
  S3. The pooled test is exactly `test_S2` ∪ `test_S3`: buckets whose names
  start with "test", routed by `src/ddinet/data/split.py` at the frozen tag;
  validation–test pairs are discarded.
* It has 84,690 pairs: 7,758 S3 and 76,932 S2.
* There is **no S2-only M4 figure**. The S2 tables in `phase_a_summary.md`
  are for baselines.

**Change.**

* AUPRC 0.812 ± 0.010 is called pooled everywhere.
* For an S2 pair the report says that no S2-only estimate exists and gives the
  pooled test's composition.
* For an S3 pair the S3 figure is shown and called S3.

The API version still on Render wrote "Model quality on held-out pairs where
the model did not see one of the drugs in training (as here): AUPRC 0.812",
which reads as an S2 figure. The fixed backend says "pooled". For responses of
either version:

* the site and the PDF attach a visible "Note added by the report: … pooled
  … no S2-only estimate exists" to any S2 sentence that quotes AUPRC or AUROC
  without the word "pooled";
* they never rewrite the service's text.

Also stated:

* Test-set metrics describe thousands of pairs; ± is the spread between 5
  training runs. Neither is the reliability of one prediction, and the service
  gives no per-pair uncertainty.
* **Validation pairs.** Warfarin is a validation drug for seed 0, and
  validation pairs chose the configuration and fitted the calibration. The
  report says the test figures describe such a pair only approximately. The
  API's `reliability: held_out_like` is printed unchanged, next to this note.

**Precision.**

* The calibrated score is shown to 2 decimals.
* The raw score is shown to 4 decimals, or as a bound at the ends of the scale
  ("> 0.9999", "< 0.0001"). Temperature scaling is monotone, so the order of
  pairs is unchanged, and the network saturates near 0 and 1.
* The modality chart uses the same bounds.
* Exact values remain in Appendix A and the companion JSON.
* Published metrics keep their published 3 decimals.

## 5. Plain language

The text lives in `web/src/data/plainLanguage.ts` and is shared by the site and
the PDF, in RU and EN.

* **Score explainer** ("What the two numbers mean"):
  * what the raw and the calibrated score are, and why they differ;
  * why neither is a probability of harm;
  * what they can and cannot tell.
* **Test-set notes**: pooled vs S3 vs S1, "both annotated", and dataset-level
  quality vs one prediction.
* **Glossary**, 15 entries:
  * source evidence vs model prediction;
  * FDA label (SPL); document vs excerpt; DrugBank (TDC);
  * direction; CYP450; substrate, inhibitor and inducer;
  * mechanism hypothesis; Reactome pathway;
  * raw and calibrated score; regimes S1, S2 and S3; held-out test and
    "pooled";
  * AUROC; AUPRC; ±.

  Study counts in the glossary are read from the frozen data.
* Section 6 points to the glossary for the service's terms.

## 6. Scientific audit

| Finding | Where | Resolution |
|---|---|---|
| Repeated label text counted as separate evidence | labels, explanation, PDF, site | merged at source; documents and excerpts counted; provenance kept (§1) |
| Pooled metric implied to be S2-specific | explanation text of the deployed API | backend wording fixed; version-independent note on site and PDF (§4) |
| "Documented evidence: a source states that these two drugs interact" | PDF summary tile | a label may only *name* the other drug; now "A label or database record that names both drugs" |
| 6-decimal raw score, 3-decimal calibrated score | PDF, site | precision matched to what was measured (§4) |
| Hyphen inserted inside identifiers and versions | PDF | explicit wrapping, no inserted characters (§3) |
| Validation pair reported like a held-out test pair | PDF, site | stated: validation pairs chose the configuration and calibration (§4) |
| "BIO-GINE adds evidence" for an already documented pair | summary | stated: the score adds no new evidence of interaction; it shows whether the model would rank the pair with documented ones |
| FDA vs DrugBank | summary, section 3 | kept apart: per document, with what each kind of record does and does not state; a DrugBank record may rest on label text |
| Direction | summary, glossary | no direction from unverified DrugBank order; label sentences quoted as written; none inferred from a name mention |
| Missing evidence as safety | unchanged rule | re-checked: every "none found" says it is not "safe"; wording tests extended to the new text |
| Causal claims | mechanism text | hypotheses only, "not tested for this pair", the arrow is the hypothesis's direction |
| Web / PDF / JSON consistency | counts, labels | one grouping module and one counts sentence for site and PDF; JSON verbatim plus `evidence_counts` |

## 7. Files

Backend (needs a Render redeploy, §9):

* `serving/evidence/adapters/openfda.py`
* `serving/evidence/labels.py`
* `serving/evidence/schema.py`
* `serving/evidence/engine.py`
* `serving/evidence/explain.py`
* tests: `tests/synthetic_labels.py`, `tests/test_v3_label_dedup.py` (12 tests)

Site and PDF:

* new data modules:
  * `web/src/data/evidenceGroups.ts`
  * `web/src/data/scoreFormat.ts`
  * `web/src/data/plainLanguage.ts`
  * `web/src/data/studyCounts.ts`
* `web/src/data/v3.ts` (types)
* `web/src/components/v3/refs.ts`, `ReportParts.tsx`
* `web/src/views/Analyzer.tsx`, `MultiDrug.tsx`
* `web/src/pdf/components.tsx`, `ReportDocument.tsx`, `content.ts`,
  `strings.ts`, `format.ts`, `Diagrams.tsx`
* tests:
  * `web/src/pdf/testing/geometry.ts` (test helper)
  * `web/src/pdf/layout.test.ts`
  * updates to `render.test.ts`, `units.test.ts` and
    `components/v3/evidence.test.tsx`
* fixtures:
  * `pair_synthetic_duplicated_labels.json` and
    `pair_synthetic_merged_labels.json`, built by
    `web/tools/build_label_fixture.py`, SYNTHETIC;
  * `multi_6.json`, `pair_long_names.json`, captured from the local API.

## 8. Limitations that remain

* **openFDA was not reachable from the development container.** The label
  path was exercised with synthetic labels of the real structure. Real label
  excerpts will first appear through the deployed API, and the real W+F PDF
  should be exported again from the Preview once Render runs this backend.
* **The same-finding rule is lexical.** Paraphrases with different words are
  kept as separate excerpts of the same document. They are still counted as one
  source, never as separate confirmations.
* **No S2-only metric.** None can be shown without new evaluation of the frozen
  predictions. That would be a new analysis, not part of this pass.
* **The executive summary quotes, it does not summarise.** A deterministic
  system cannot say which part of a label sentence matters clinically, and
  this pass did not try.
* **The PDF is not tagged for screen readers**, a react-pdf limitation; its
  text layer is complete.

## 9. Deployment state

The frontend reaches Vercel through the push to `feature/ddinet-v3`. The
backend changes in `serving/evidence/` do **not** reach the Render test API on
their own: Auto-Deploy is off. Until it is redeployed, the deployed API keeps:

* sending repeated label sentences as separate records — the site and the PDF
  group them anyway;
* writing the old metric sentence — the site and the PDF annotate it;
* omitting `n_label_documents` — the multi-drug PDF then labels its column as
  excerpts.

To redeploy, follow `docs/DDINET_V3_DEPLOYMENT.md` §3.1.
