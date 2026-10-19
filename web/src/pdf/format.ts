// Pure helpers shared by the PDF document, the companion JSON and the tests:
// hashing input, timestamps with their time zone, file names, display names,
// safe text and URLs. No React, no PDF library.
import type { DrugOut } from "../data/v3";
import type { Lang } from "../i18n";
import { sha256Hex } from "./sha256";
import type { ExportContext, ExportInput, PreparedExport } from "./types";

// ------------------------------------------------------------------ hashing --

/** The API payload(s) an export is built from, exactly as received. */
export function payloadOf(input: ExportInput): Record<string, unknown> {
  return input.kind === "pair"
    ? { report: input.report.data, graph: input.graph?.data ?? null }
    : { multi: input.report.data };
}

/** JSON with object keys sorted at every level, so equal data hashes equally. */
export function canonicalJson(value: unknown): string {
  const norm = (v: unknown): unknown => {
    if (Array.isArray(v)) return v.map(norm);
    if (v && typeof v === "object") {
      return Object.fromEntries(Object.keys(v as object).sort().map((k) => [k, norm((v as Record<string, unknown>)[k])]));
    }
    return v;
  };
  return JSON.stringify(norm(value));
}

export async function prepareExport(input: ExportInput, ctx: ExportContext): Promise<PreparedExport> {
  const payloadSha256 = await sha256Hex(canonicalJson(payloadOf(input)));
  const iso = ctx.now.toISOString(); // UTC
  const reportId = `DDI-${iso.slice(0, 10).replace(/-/g, "")}-${iso.slice(11, 19).replace(/:/g, "")}-${payloadSha256.slice(0, 8).toUpperCase()}`;
  return { input, ctx, payloadSha256, reportId, fileBase: fileBase(input, ctx) };
}

// --------------------------------------------------------------------- time --

interface ZonedParts { year: string; month: string; day: string; hour: string; minute: string; second: string; offset: string }

/** Wall-clock parts and UTC offset ("+05:00") of an instant in a time zone. */
export function zonedParts(d: Date, timeZone: string): ZonedParts {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", timeZoneName: "longOffset",
  }).formatToParts(d);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  const tz = get("timeZoneName"); // "GMT+05:00" or "GMT"
  const offset = tz === "GMT" || tz === "UTC" ? "+00:00" : tz.replace(/^(GMT|UTC)/, "");
  return { year: get("year"), month: get("month"), day: get("day"), hour: get("hour"), minute: get("minute"), second: get("second"), offset };
}

/** ISO 8601 with the local offset, e.g. 2026-10-14T19:42:10+05:00. */
export function isoLocal(d: Date, timeZone: string): string {
  const p = zonedParts(d, timeZone);
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}${p.offset}`;
}

/** Human date and time in the report language, with zone name and offset. */
export function humanDateTime(d: Date, timeZone: string, lang: Lang): string {
  const date = new Intl.DateTimeFormat(lang === "ru" ? "ru-RU" : "en-GB", { timeZone, day: "numeric", month: "long", year: "numeric" }).format(d);
  const p = zonedParts(d, timeZone);
  return `${date}, ${p.hour}:${p.minute}:${p.second} (${timeZone}, UTC${p.offset})`;
}

export function localDate(d: Date, timeZone: string): string {
  const p = zonedParts(d, timeZone);
  return `${p.year}-${p.month}-${p.day}`;
}

export function browserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

// -------------------------------------------------------------------- names --

const cap = (s: string) => (s ? s.charAt(0).toLocaleUpperCase() + s.slice(1) : s);

/** Display name of a drug in the report language. Falls back to the DrugBank ID. */
export function drugName(d: Pick<DrugOut, "id" | "inn" | "name_ru">, lang: Lang): string {
  const n = lang === "ru" ? d.name_ru ?? d.inn : d.inn;
  return n ? cap(clean(n)) : d.id;
}

/** ASCII token for file names: the INN when known, else the DrugBank ID. */
function fileToken(d: Pick<DrugOut, "id" | "inn">): string {
  const raw = d.inn ? cap(d.inn) : d.id;
  const t = raw.normalize("NFKD").replace(/[^A-Za-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40);
  return t || d.id;
}

export function fileBase(input: ExportInput, ctx: ExportContext): string {
  const date = localDate(ctx.now, ctx.timeZone);
  const suffix = ctx.lang === "ru" ? "_RU" : "";
  if (input.kind === "pair") {
    const r = input.report.data;
    const kind = ctx.variant === "quick" ? "QuickReport" : "Report";
    return `DDI-Net_${kind}_${fileToken(r.drug_a)}_${fileToken(r.drug_b)}_${date}${suffix}`;
  }
  const drugs = input.report.data.drugs;
  const head = drugs.slice(0, 3).map(fileToken).join("_");
  const more = drugs.length > 3 ? `_and_${drugs.length - 3}_more` : "";
  return `DDI-Net_MultiDrug_Report_${head}${more}_${date}${suffix}`;
}

// ---------------------------------------------------------- text and links --

/** Text for a single run: control characters dropped, line breaks and tabs
 *  folded into spaces (a line break inside a run would fall back to a
 *  non-embedded font). Text is never interpreted as markup by the renderer. */
export function clean(s: string | null | undefined): string {
  return cleanLines(s).replace(/\s*\n\s*/g, " ").replace(/\t/g, " ");
}

/** Like clean(), but keeps line breaks — for text split into lines explicitly. */
export function cleanLines(s: string | null | undefined): string {
  if (s === null || s === undefined) return "";
  // eslint-disable-next-line no-control-regex
  return String(s).replace(/\r\n?/g, "\n").replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F\u200B-\u200F\u2028-\u202E\u2066-\u2069\uFEFF]/g, "");
}

/** The URL if it is an absolute http(s) URL, else null. Only these become links. */
export function safeUrl(u: string | null | undefined): string | null {
  if (!u) return null;
  try {
    const url = new URL(u);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}

/** Split a long unbroken string (URL, identifier, JSON line) into lines that fit
 *  `width` points in IBM Plex Mono at `size` (every glyph is 0.6 em wide),
 *  preferring breaks after URL punctuation. */
export function wrapMono(text: string, width: number, size: number): string[] {
  const max = Math.max(8, Math.floor(width / (0.6 * size)));
  const out: string[] = [];
  for (const line of cleanLines(text).split("\n")) {
    let rest = line;
    while (rest.length > max) {
      let cut = -1;
      for (let i = max; i > max * 0.6; i--) {
        if ("/?&=+,;:_-. ".includes(rest[i - 1])) { cut = i; break; }
      }
      if (cut < 0) cut = max;
      out.push(rest.slice(0, cut));
      rest = rest.slice(cut);
    }
    out.push(rest);
  }
  return out;
}

/** Long text cut into pieces of at most `max` characters at spaces, so that no
 *  single atomic block can be taller than a page. */
export function chunkText(text: string, max = 900): string[] {
  const out: string[] = [];
  let rest = text;
  while (rest.length > max) {
    let cut = rest.lastIndexOf(" ", max);
    if (cut < max / 2) cut = max;
    out.push(rest.slice(0, cut).trimEnd());
    rest = rest.slice(cut).trimStart();
  }
  out.push(rest);
  return out;
}

// ------------------------------------------------------------------ numbers --

export const fixed = (x: number | null | undefined, digits: number): string =>
  x === null || x === undefined || !Number.isFinite(x) ? "—" : x.toFixed(digits);

const WORDS = {
  drug: { en: ["drug", "drugs"], ru: ["препарат", "препарата", "препаратов"] },
  pair: { en: ["pair", "pairs"], ru: ["пара", "пары", "пар"] },
} as const;

/** "5 drugs", "1 pair", "2 препарата", "28 пар" — counts with the right noun form. */
export function countWords(n: number, word: keyof typeof WORDS, lang: Lang): string {
  if (lang === "en") return `${n} ${WORDS[word].en[n === 1 ? 0 : 1]}`;
  const [one, few, many] = WORDS[word].ru;
  const m10 = n % 10, m100 = n % 100;
  const form = m10 === 1 && m100 !== 11 ? one : m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? few : many;
  return `${n} ${form}`;
}

export const int = (n: number, lang: Lang): string => n.toLocaleString(lang === "ru" ? "ru-RU" : "en-US").replace(/\u00a0|\u202f/g, " ");

/** Signed change in the raw score, as the site shows it (positive = score drops). */
export function deltaText(d: number): string {
  if (Math.abs(d) < 0.0005) return "0.000";
  return `${d > 0 ? "−" : "+"}${Math.abs(d).toFixed(3)}`;
}

// --------------------------------------------------------------------- JSON --

export interface JsonLine { indent: number; text: string }

/** JSON pretty-printed to `prettyDepth` levels, deeper values kept compact on
 *  one line, then wrapped to `maxChars` columns only between tokens (never
 *  inside a string, unless a single string is longer than a line). Joining the
 *  lines with newlines gives valid JSON equal to `value`. */
export function jsonLines(value: unknown, maxChars: number, prettyDepth = 2): JsonLine[] {
  const raw: JsonLine[] = [];
  const emit = (v: unknown, indent: number, prefix: string, suffix: string) => {
    const pretty = indent < prettyDepth && v !== null && typeof v === "object" && (Array.isArray(v) ? v.length > 0 : Object.keys(v as object).length > 0);
    if (!pretty) {
      raw.push({ indent, text: `${prefix}${JSON.stringify(v)}${suffix}` });
      return;
    }
    const arr = Array.isArray(v);
    raw.push({ indent, text: `${prefix}${arr ? "[" : "{"}` });
    const entries: [string | null, unknown][] = arr ? (v as unknown[]).map((x) => [null, x]) : Object.entries(v as object);
    entries.forEach(([k, x], i) => emit(x, indent + 1, k === null ? "" : `${JSON.stringify(k)}: `, i < entries.length - 1 ? "," : ""));
    raw.push({ indent, text: `${arr ? "]" : "}"}${suffix}` });
  };
  emit(value, 0, "", "");

  const out: JsonLine[] = [];
  for (const line of raw) {
    const room = Math.max(16, maxChars - line.indent * 2);
    let rest = line.text;
    let first = true;
    while (rest.length > (first ? room : room - 2)) {
      const lim = first ? room : room - 2;
      let cut = -1, inStr = false;
      for (let i = 0; i < rest.length && i < lim; i++) {
        const c = rest[i];
        if (inStr) {
          if (c === "\\") i++;
          else if (c === '"') inStr = false;
        } else if (c === '"') inStr = true;
        else if (c === "," || c === ":" || c === "{" || c === "[") cut = i + 1;
      }
      const hard = cut <= 0;
      if (hard) cut = lim; // a single over-long token: break it
      out.push({ indent: line.indent + (first ? 0 : 1), text: rest.slice(0, cut) });
      // After a token boundary the separating space can go; inside a broken
      // string every character is data and stays.
      rest = hard ? rest.slice(cut) : rest.slice(cut).replace(/^ /, "");
      first = false;
    }
    out.push({ indent: line.indent + (first ? 0 : 1), text: rest });
  }
  return out;
}
