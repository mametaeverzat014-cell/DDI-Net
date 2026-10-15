# DDI-Net 3.0 — PDF report export

An **Export PDF** button on the Analyzer, the Mechanisms page and the Multi-Drug
Explorer turns the analysis on screen into an A4 research report, generated in
the browser. A **JSON** button next to it saves the same analysis as
machine-readable data. Nothing is sent anywhere and nothing is requested again
for the export.

Samples generated in a real browser: `docs/samples/pdf-export/` (see the README
there for their provenance).

---

## 1. Using it

| Page | Enabled when | Report contains |
|---|---|---|
| Analyzer | the pair report has loaded | pair report; mechanism diagram drawn from the report's own mechanism block |
| Mechanisms | the pair report has loaded and the graph request has finished | pair report; mechanism diagram drawn from the `/api/v3/graph` response (falls back to the report's block if the graph failed) |
| Multi-Drug Explorer | "Check pairs" has returned | all drugs, all pairs, network, pair matrix |

* Before results exist both buttons are disabled and the status line says
  why. While a file is being generated the button shows a spinner and both
  buttons are disabled; the status line (an ARIA live region) announces
  "Generating PDF…", then "File saved: <name>", or a specific error (module
  not loaded after a site update, fonts not loaded, or the technical reason).
  On failure nothing is downloaded.
* Native buttons: Tab to reach, Enter or Space to activate.
* Language: the report follows the site language (RU default, EN).
* File names: `DDI-Net_Report_<DrugA>_<DrugB>_<YYYY-MM-DD>.pdf`,
  `DDI-Net_MultiDrug_Report_<first three>_and_<n>_more_<date>.pdf`; `_RU` is
  appended for Russian reports. INNs in ASCII, the DrugBank ID when a drug has
  no INN, the date in the browser's time zone.
* The first export loads the PDF module (≈490 KB gzipped) and the fonts
  (≈0.9 MB); later exports reuse them. Measured in Chromium: about 6 s for the
  first two-drug report, including those downloads, against a local API.

### Quick Report and the outcome sections (Clinical Outcome Engine)

A **Quick PDF** button (pair reports only) produces a 1–2 page report built
from the same API response as the site and the full report:

* **A — Is there a documented interaction?** The interaction status.
* **B — What could happen?** Each documented outcome with the source's own
  words and its extraction method.
* **C — Why could it happen?** The verified chain summaries.
* **D — How certain is the information?** Seriousness as the source states
  it, the source documents, coverage and key uncertainties.
* **E — What does BIO-GINE add?**
* **F — Important limitation.**

File name: `DDI-Net_QuickReport_<A>_<B>_<date>.pdf`.

The **full report** adds three things:
* the outcome summary in section 1;
* in section 3, an outcome table plus provenance for every outcome, with
  every excerpt verbatim;
* in section 4, a chain figure in which solid, dashed and dotted lines show
  the provenance class.

For multi-drug reports it adds the pairwise interaction status and the
outcome categories shared by two or more pairs, with no combined score.

The JSON machine summary (`machine_summary.outcomes`) carries the same
records.

## 2. What the report contains

Pair report:

* **Cover:** drugs, report ID, generation time with time zone and UTC offset,
  model and checkpoint, API report version, service time stamps, contents,
  research-only notice.
* **1 Executive summary:**
  * status card and an "In brief" line;
  * the four kinds of information;
  * five parts (`docs/DDINET_V3_REPORT_QUALITY_PASS.md` §2): what the official
    sources document, what their quoted words directly say, what is only a
    hypothesis, what BIO-GINE adds, what remains uncertain.
* **2 Drug information.**
* **3 Documented interactions, grouped by source document:**
  * counts line, table of source documents;
  * one card per document with its distinct excerpts: the source's own words,
    every section an excerpt was found in, the project translation for
    DrugBank sentences, direction status with the measured order check;
  * the document's provenance and qualifiers;
  * conflicts and sources checked.
* **4 Biological mechanisms:** vector diagram, legend, hypotheses table with
  roles and PubMed IDs, pathway membership matrix, Reactome table, protein
  family notes.
* **5 BIO-GINE research analysis:**
  * scores at the precision they have, regime, splits, reliability;
  * what the two numbers mean;
  * measured test-set quality, labelled pooled or S3, with the test-set notes;
  * uncertainty, modality reliance chart, service notes.
* **6 The service's structured explanation** with its reference labels.
* **7 Sources and reproducibility:** source documents, annotation records,
  provenance and parameters, SHA-256.
* **8 Limitations.**
* **9 Glossary.**
* **Supplement S1:** every evidence record as received.
* **Appendix A:** machine-readable summary (JSON).

Multi-drug report:

* cover;
* summary with counts per kind of documentation, no overall score;
* drug overview;
* pairwise network and pair matrix;
* all pairs, with FDA label documents and, in brackets, their distinct
  excerpts;
* coverage and uncertainty;
* sources and reproducibility;
* limitations;
* glossary;
* Appendix A.

### Rules the report follows

* **Only the payload.** Every value is read from the API response(s) the page
  holds; the export never calls the API. Where a field is absent the report says
  "not recorded", "none" or "model unavailable", never a substitute value. A
  test checks every number with 2 to 6 decimals in the text against the payload.
* **Four kinds kept apart:** documented evidence, mechanism hypotheses, the
  machine-learning prediction, and missing or unavailable evidence, each with its
  own colour. No colour is green and none encodes danger.
* **No direction the data does not support.** For DrugBank records whose drug
  order is not verified the report prints the direction-neutral statement and
  says so; the diagram's link between the drugs never has an arrowhead. A test
  checks that no orientation-filled template appears.
* **One source, one count.** Records are grouped into source documents and
  distinct excerpts with the server's rule (`web/src/data/evidenceGroups.ts`).
  * Several excerpts of one label are one source, and the report says so.
  * A sentence that one label repeats in two sections is shown once, with both
    section names.
  * Every raw record stays in Supplement S1 and in the companion JSON.
  * The site prints the same counts sentence.
* **Numbers at the precision they have.** The calibrated score is shown to 2
  decimals. The raw score is shown to 4, or as a bound ("> 0.9999") at the
  ends of the scale. Exact values are in Appendix A. Published metrics keep
  their published 3 decimals.
* **Pooled is called pooled.** M4's frozen test metrics exist only for the
  pooled S2+S3 test and for S3. An S2 pair's report says that no S2-only
  estimate exists, and a service sentence that quotes a metric without
  "pooled" gets a visible note.
* **No uncertainty that was not measured.** The API serves one checkpoint (seed
  0) and gives no per-pair interval or ensemble; the report says this and shows
  the regime-level performance across seeds instead.
* **The score is not a risk.** Stated on the cover, in the summary, next to the
  score and in the limitations.
* **No overall multi-drug score**, stated explicitly.

### Provenance

Each successful API response is recorded with its endpoint, the exact request
body and the browser time it arrived (`data/v3.ts`, `FetchMeta`). The report
prints these, the service's own `generated_at`, the frozen research tag and
commit, the site origin and build commit (`VERCEL_GIT_COMMIT_SHA` at build time,
"not recorded" elsewhere) and the generation time.

The **report ID** is `DDI-<UTC date>-<UTC time>-<first 8 hex of the payload
hash>`. The **payload SHA-256** is the hash of `JSON.stringify` of the response
payload(s) with object keys sorted at every level. The companion JSON carries
the payload verbatim and the same hash, so a reader can check that the PDF and
the data belong together:

```js
const norm = (v) => Array.isArray(v) ? v.map(norm) : v && typeof v === "object"
  ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, norm(v[k])])) : v;
crypto.createHash("sha256").update(JSON.stringify(norm(json.payload))).digest("hex") === json.payload_sha256;
```

## 3. Implementation

| File | Role |
|---|---|
| `web/src/components/v3/ExportReport.tsx` | buttons, states, messages; loads the PDF code on demand |
| `web/src/pdf/exportReport.tsx` | entry point: prepare, render, download |
| `web/src/pdf/format.ts` | hashing, report ID, file names, time zones, safe text and URLs, wrapping, JSON lines |
| `web/src/pdf/content.ts` | summary sentences, counts, machine summary, companion JSON — all from the payload |
| `web/src/pdf/diagram.ts` | geometry of the mechanism schematic and the network (pure, tested) |
| `web/src/pdf/Diagrams.tsx`, `components.tsx`, `ReportDocument.tsx` | the document |
| `web/src/pdf/strings.ts`, `theme.ts`, `styles.ts`, `fonts.ts` | wording (RU/EN), palette, type, fonts |
| `web/tools/render_sample_reports.tsx` | renders the fixtures to PDF from the command line |

Library: `@react-pdf/renderer` 4.9.0 (pinned), client-side, real text and
vector graphics, not a screenshot. No server, no paid service, no API key.

Fonts: IBM Plex Sans, Serif and Mono (SIL Open Font License 1.1), the
unmodified WOFF files of the official `@ibm/plex-*` packages, in
`web/public/fonts/pdf/` with the licence. The renderer embeds the subset each
report uses, so the PDF reads the same offline on any machine. Latin and
Cyrillic in all three; Plex Mono has no Greek, so a wrapped monospace line
(URL, identifier, JSON) containing Greek is set in Plex Sans instead.

Safety: text reaches the PDF as plain text (react-pdf interprets no markup);
control and bidirectional-override characters are removed; only absolute
`http(s)` URLs become links. File names are ASCII-only.

### Renderer problems found and handled

1. **Line height compounding.** react-pdf 4.9.0 re-resolves a page's unitless
   `lineHeight` on every page it splits into, multiplying it by the font size
   each time. Anything inheriting it — the running header and footer — grew
   ×9.2 per page: their rules were drawn millions of points off the page, and
   in a long report the numbers overflowed and rendering failed. The page style
   now has no line height; every text style sets its own. Test: no drawing
   coordinate above 10,000 pt on any page.
2. **Font objects shared between documents.** Generating several reports in one
   session let glyph state leak between them, and a glyph could extract as the
   wrong character (the "C" of "Clarithromycin" became U+0016 in the text layer
   while still looking right). Each export now loads fresh font objects
   (`freshPdfFonts`); `Font.reset()` cannot be used because in this version it
   breaks the built-in fonts. Test: ten reports rendered in one process, every
   extracted character checked against the font files.
3. **Long unbroken words.** The renderer breaks only at spaces and at points
   given by the hyphenation callback. Words over 24 characters get break points
   after punctuation, else every 12 characters; dictionary hyphenation is off
   (its patterns are English). Letter-spacing is not used, because it makes
   text extract as "D D I".
4. **Split boxes squeeze their content.** A View that splits across pages gets
   a fixed height for its first part, and on the second layout pass (page
   numbers) its children are shrunk to fit. An evidence card's last rows were
   drawn over the footer. Now:
   * only page-level children split;
   * nested Views are atomic;
   * long cards, lists, the JSON appendix and the glossary are emitted as
     atomic page-level segments.

   Details are in the comment "PAGE BREAKS" in `components.tsx`. Tests: the
   geometry checks in `layout.test.ts`.
5. **Titles split instead of moved.** A title that did not fit was split, and
   `minPresenceAhead` is checked only when a node does not split, so titles
   ended pages. Titles are now atomic.
6. **Hyphens inserted at forced breaks.** textkit draws "-" wherever it breaks
   a word, including inside identifiers, and it treats a two-space gap as such
   a point. References follow a single space, and code-like text in narrow
   cells is wrapped explicitly in mono (`SafeText`).

## 4. Tests

The test files are:

* `web/src/pdf/units.test.ts` (22)
* `web/src/pdf/render.test.ts` (20)
* `web/src/pdf/layout.test.ts` (16)
* `web/src/components/v3/ExportReport.test.tsx` (7)

`render.test.ts` generates twelve PDFs and reads them back with `pdfjs-dist`.

* **Real responses:** two-drug EN/RU, Mechanisms EN/RU, no-evidence pair,
  8-drug EN/RU.
* **Synthetic variants:**
  * label evidence without a model;
  * 8 drugs with very long names;
  * hostile input;
  * the duplicated-label report in EN and RU.

What the checks cover:

* **File and fonts:** validity, A4, fonts embedded and only IBM Plex, every
  character drawn with a real glyph.
* **Layout:** no text outside the margins, no blank pages.
* **Content:**
  * sections and values present;
  * every source URL, API record ID, section, retrieval date and PMID cited;
  * no number absent from the payload (rounded payload values and the
    "> 0.9999" bound allowed).
* **Scientific rules:**
  * counts of documents and excerpts equal to the site's sentence;
  * a repeated label sentence shown once in section 3;
  * the pooled metric never presented as S2;
  * no unverified direction;
  * no advice wording.
* **Multi-drug:** every drug and pair covered, no overall score.
* **Safety:** markup printed literally, no `javascript:` links.

`layout.test.ts` checks the geometry of 16 reports and of a sweep of excerpt
lengths: margins, header and footer bands, overlapping lines, page numbers,
blank and mostly empty pages (`docs/DDINET_V3_REPORT_QUALITY_PASS.md` §3).

Outside the unit tests: the exported files were also checked with poppler
(`pdfinfo`, `pdffonts`, `pdftotext`) and `pypdf` in strict mode, and inspected
page by page at 40, 60, 110 and 220 dpi.

## 5. Limitations

* The report reflects the evidence service as it answered. The samples in this
  repository come from a local API whose network policy blocked openFDA, so
  their label source reads "unavailable"; the Render API reaches openFDA.
* Very long tables and appendices simply continue on further pages; the JSON
  appendix of an 8-drug report is about one page.
* A figure that does not fit moves whole to the next page and can leave up to
  about half a page empty before it.
* Drug names longer than the figure space are shortened with "…" in the network
  and matrix labels, and on the cover of a report with more than four drugs;
  the tables always carry the full name.
* The PDF is not tagged for screen readers (react-pdf does not produce tagged
  PDF); its text layer is complete and in reading order.
