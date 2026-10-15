// Inputs of the PDF export. An export is built only from responses the page
// already holds — the same objects the reader is looking at — plus the request
// provenance recorded when they arrived (data/v3.ts FetchMeta). Nothing here
// triggers a request.
import type { FetchMeta, MechanismGraph, MultiReport, PairReport } from "../data/v3";
import type { Lang } from "../i18n";

export interface Fetched<T> {
  data: T;
  /** Absent only if the response predates provenance recording. */
  meta?: FetchMeta | null;
}

export type ExportInput =
  | {
      kind: "pair";
      /** Page the export was started from; changes only the provenance note. */
      origin: "analyzer" | "mechanisms";
      report: Fetched<PairReport>;
      /** The /api/v3/graph response, when the page has one (Mechanisms page). */
      graph?: Fetched<MechanismGraph> | null;
    }
  | { kind: "multi"; report: Fetched<MultiReport> };

/** Everything about the moment and place of export. Injected so tests are deterministic. */
export interface ExportContext {
  lang: Lang;
  /** Generation instant. */
  now: Date;
  /** IANA time zone used for the local timestamp, e.g. "Europe/Moscow". */
  timeZone: string;
  /** Origin of the site that produced the PDF, e.g. https://….vercel.app. Null in tests. */
  siteOrigin: string | null;
  /** Git commit the site was built from, when the build exposed it. */
  siteCommit: string | null;
  /** "quick": 1–2 page summary of a pair report; "full" (default): the research report. */
  variant?: "full" | "quick";
}

/** An export after hashing: what the document and the companion JSON share. */
export interface PreparedExport {
  input: ExportInput;
  ctx: ExportContext;
  /** SHA-256 (hex) of the canonical JSON of the API payload(s) — see payloadOf(). */
  payloadSha256: string;
  reportId: string;
  /** File name without extension. */
  fileBase: string;
}
