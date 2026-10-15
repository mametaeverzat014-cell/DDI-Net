// @vitest-environment node
// Pure parts of the PDF export: hashing, names, timestamps, wrapping, JSON
// lines, diagram geometry, colours and wording. No PDF is rendered here.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { webcrypto } from "node:crypto";
import { describe, expect, it } from "vitest";
import type { MechanismGraph, MultiReport, PairReport } from "../data/v3";
import { companionJson, machineSummary, pairBrief, STATUS_COLOR, t } from "./content";
import { diagramData, inside, labelBox, layoutMechanism, layoutNetwork, overlaps } from "./diagram";
import {
  canonicalJson, clean, countWords, drugName, fileBase, humanDateTime, isoLocal, jsonLines, payloadOf, prepareExport, safeUrl, wrapMono,
} from "./format";
import { sha256Fallback, sha256Hex } from "./sha256";
import { S } from "./strings";
import { needsPooledNote } from "../data/plainLanguage";
import { CONTENT_WIDTH, EV } from "./theme";
import type { ExportContext, ExportInput } from "./types";

const FX = join(__dirname, "__fixtures__");
const fx = (n: string) => JSON.parse(readFileSync(join(FX, n), "utf8"));
const wf = fx("pair_warfarin_fluconazole.json");
const sc = fx("pair_simvastatin_clarithromycin.json");
const mw = fx("pair_metformin_warfarin.json");
const m8 = fx("multi_8.json");

const ctx = (lang: "ru" | "en" = "en"): ExportContext => ({
  lang, now: new Date("2026-10-14T21:30:05.000Z"), timeZone: "Asia/Almaty", siteOrigin: "https://example.test", siteCommit: "abc123",
});
const pairInput = (f: { report: unknown; graph?: unknown }, withGraph = false): ExportInput => ({
  kind: "pair", origin: withGraph ? "mechanisms" : "analyzer",
  report: f.report as ExportInput extends never ? never : { data: PairReport },
  ...(withGraph ? { graph: f.graph as { data: MechanismGraph } } : {}),
} as ExportInput);

describe("sha256", () => {
  it("matches the standard vectors and WebCrypto", async () => {
    const enc = (s: string) => new TextEncoder().encode(s);
    expect(sha256Fallback(enc("abc"))).toBe("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    expect(sha256Fallback(enc(""))).toBe("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
    for (const s of ["", "abc", "x".repeat(55), "x".repeat(56), "x".repeat(64), "варфарин + флуконазол — Δ", canonicalJson(wf)]) {
      const web = Buffer.from(await webcrypto.subtle.digest("SHA-256", enc(s))).toString("hex");
      expect(sha256Fallback(enc(s))).toBe(web);
      expect(await sha256Hex(s)).toBe(web);
    }
  });

  it("hashes the payload independent of key order", async () => {
    expect(canonicalJson({ b: 1, a: { d: [1, { z: 1, y: 2 }], c: null } })).toBe('{"a":{"c":null,"d":[1,{"y":2,"z":1}]},"b":1}');
    const a = await prepareExport(pairInput(wf), ctx());
    const shuffled = { ...wf, report: { ...wf.report, data: Object.fromEntries(Object.entries(wf.report.data).reverse()) } };
    const b = await prepareExport(pairInput(shuffled), ctx());
    expect(a.payloadSha256).toBe(b.payloadSha256);
    expect(a.reportId).toBe(`DDI-20261014-213005-${a.payloadSha256.slice(0, 8).toUpperCase()}`);
  });
});

describe("names, files and time", () => {
  it("names files descriptively, in ASCII, with the local date", () => {
    expect(fileBase(pairInput(wf), ctx("en"))).toBe("DDI-Net_Report_Warfarin_Fluconazole_2026-10-15");
    expect(fileBase(pairInput(wf), ctx("ru"))).toBe("DDI-Net_Report_Warfarin_Fluconazole_2026-10-15_RU");
    expect(fileBase({ kind: "multi", report: m8 }, ctx())).toBe("DDI-Net_MultiDrug_Report_Warfarin_Fluconazole_Simvastatin_and_5_more_2026-10-15");
    const odd: ExportInput = { kind: "pair", origin: "analyzer", report: { data: { ...wf.report.data, drug_a: { ...wf.report.data.drug_a, inn: "co-trimoxazole/<b> (test)\u0000" }, drug_b: { ...wf.report.data.drug_b, inn: null } } } };
    const base = fileBase(odd, ctx());
    expect(base).toBe("DDI-Net_Report_Co-trimoxazole-b-test_DB00196_2026-10-15");
    expect(base).toMatch(/^[A-Za-z0-9_.-]+$/);
  });

  it("states time with zone and offset", () => {
    const d = new Date("2026-10-14T21:30:05.000Z");
    expect(isoLocal(d, "Asia/Almaty")).toBe("2026-10-15T02:30:05+05:00");
    expect(isoLocal(d, "UTC")).toBe("2026-10-14T21:30:05+00:00");
    expect(humanDateTime(d, "Europe/Moscow", "en")).toBe("15 October 2026, 00:30:05 (Europe/Moscow, UTC+03:00)");
    expect(humanDateTime(d, "Europe/Moscow", "ru")).toMatch(/^15 октября 2026 г\., 00:30:05 \(Europe\/Moscow, UTC\+03:00\)$/);
  });

  it("uses the right noun forms", () => {
    expect([1, 2, 5, 21, 28].map((n) => countWords(n, "pair", "ru"))).toEqual(["1 пара", "2 пары", "5 пар", "21 пара", "28 пар"]);
    expect([2, 4, 8].map((n) => countWords(n, "drug", "ru"))).toEqual(["2 препарата", "4 препарата", "8 препаратов"]);
    expect([1, 6].map((n) => countWords(n, "pair", "en"))).toEqual(["1 pair", "6 pairs"]);
  });

  it("falls back to the DrugBank ID when a drug has no name", () => {
    expect(drugName({ id: "DB01045", inn: null, name_ru: null }, "en")).toBe("DB01045");
    expect(drugName({ id: "DB00682", inn: "warfarin", name_ru: "варфарин" }, "ru")).toBe("Варфарин");
  });
});

describe("safe text", () => {
  it("drops control characters and folds line breaks; text is never markup", () => {
    // control characters and bidirectional overrides (text spoofing) are dropped
    expect(clean("a\u0000b\u0007c\u202e\u2066\r\nd\te")).toBe("abc d e");
    expect(clean("<script>alert(1)</script>")).toBe("<script>alert(1)</script>");
    expect(clean(null)).toBe("");
  });

  it("links only absolute http(s) URLs", () => {
    expect(safeUrl("https://tdcommons.ai/multi_pred_tasks/ddi/")).toBe("https://tdcommons.ai/multi_pred_tasks/ddi/");
    for (const bad of ["javascript:alert(1)", "data:text/html,x", "file:///etc/passwd", "//evil.test", "not a url", ""]) expect(safeUrl(bad)).toBeNull();
  });

  it("wraps long strings into lines that fit, keeping every character", () => {
    const url = "https://api.fda.gov/drug/label.json?search=openfda.generic_name:%22fluconazole%22+AND+openfda.product_type:%22HUMAN+PRESCRIPTION+DRUG%22&limit=25";
    const lines = wrapMono(url, 200, 6.6);
    const max = Math.floor(200 / (0.6 * 6.6));
    expect(lines.every((l) => l.length <= max)).toBe(true);
    expect(lines.join("")).toBe(url);
    expect(wrapMono("x".repeat(300), 100, 6).join("")).toBe("x".repeat(300));
  });

  it("prints JSON whose lines parse back to the same value, never splitting a string", () => {
    for (const lang of ["en", "ru"] as const) {
      for (const input of [pairInput(wf), pairInput(sc, true), { kind: "multi", report: m8 } as ExportInput]) {
        const prep = { input, ctx: ctx(lang), payloadSha256: "f".repeat(64), reportId: "DDI-X", fileBase: "x" };
        const value = machineSummary(prep);
        const expected = JSON.parse(JSON.stringify(value));
        // At the printed width (Appendix A: 131 columns) breaks fall only between
        // tokens, so the extracted lines parse as they are.
        const printed = jsonLines(value, Math.floor((CONTENT_WIDTH - 16) / (0.6 * 6)));
        expect(JSON.parse(printed.map((l) => l.text).join("\n"))).toEqual(expected);
        // At any width nothing is lost: the pieces concatenate back to valid JSON.
        const spaced = { s: "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu" };
        expect(JSON.parse(jsonLines(spaced, 20).map((l) => l.text).join(""))).toEqual(spaced);
        for (const width of [24, 40, 80]) {
          const lines = jsonLines(value, width);
          expect(lines.every((l) => l.text.length <= Math.max(16, width - l.indent * 2))).toBe(true);
          expect(JSON.parse(lines.map((l) => l.text).join(""))).toEqual(expected);
        }
      }
    }
  });
});

describe("content is read off the payload", () => {
  it("summary counts equal the payload", () => {
    const r = wf.report.data as PairReport;
    const s = pairBrief(r, "en");
    const all = (id: string) => s.parts.find((p) => p.id === id)!.items.map((i) => `${i.lead ?? ""} ${i.text ?? ""} ${i.quote ?? ""}`).join(" ");
    expect(s.headline).toContain("FDA label documents: 0 · distinct excerpts: 0 · DrugBank records: 1");
    expect(s.headline).toContain("BIO-GINE calibrated score: 0.81");
    expect(all("documents")).toContain("DrugBank (TDC export) holds 1 interaction record(s)");
    expect(all("quotes")).toContain(r.evidence[0].statement);
    expect(all("quotes")).toContain("does not say which drug affects which");
    expect(all("hypotheses")).toContain("Fluconazole → Warfarin");
    expect(all("model")).toContain("pooled held-out test (S2 and S3 pairs together; no S2-only estimate exists): AUPRC 0.812 ± 0.010");
    expect(all("model")).toContain("validation set");
    expect(all("uncertain")).toContain("FDA labels (openFDA)");
    expect(all("uncertain")).toContain("For 1 of 1 DrugBank records the drug order in the export is not verified");
    const none = pairBrief(mw.report.data as PairReport, "en");
    expect(none.parts[0].items.map((i) => i.text).join(" ")).toContain("does not mean the combination is safe");
    expect(none.parts[0].kind).toBe("missing");
  });

  it("summary of a report with label evidence counts documents, quotes verbatim, and keeps the direction rule", () => {
    const dup = fx("pair_synthetic_duplicated_labels.json").report.data as PairReport;
    const merged = fx("pair_synthetic_merged_labels.json").report.data as PairReport;
    for (const r of [dup, merged]) {
      const s = pairBrief(r, "en");
      expect(s.headline).toContain("FDA label documents: 2 · distinct excerpts: 4 · DrugBank records: 1");
      const docs = s.parts[0].items.map((i) => i.text).join(" ");
      expect(docs).toContain("The FDA label of Fluconazole names Warfarin in 2 distinct excerpt(s)");
      expect(docs).toContain("not separate confirmations");
      const quotes = s.parts[1].items.filter((i) => i.quote);
      // every quote is a verbatim prefix of a source sentence, never a paraphrase
      for (const q of quotes) expect(r.evidence.some((e) => e.statement.replace(/\s+/g, " ").startsWith(q.quote!.replace(/…$/, "")))).toBe(true);
      // the repeated sentence is quoted once
      expect(new Set(quotes.map((q) => q.quote)).size).toBe(quotes.length);
      expect(s.parts[1].items.map((i) => i.text ?? "").join(" ")).toContain("none is inferred from the mere fact that one drug's label names the other");
    }
    const ru = pairBrief(merged, "ru");
    expect(ru.headline).toContain("инструкций FDA: 2 · различных фрагментов: 4 · записей DrugBank: 1");
  });

  it("the machine summary and the companion JSON copy values, never invent them", async () => {
    const prep = await prepareExport(pairInput(wf), ctx());
    const m = machineSummary(prep) as Record<string, unknown> & { model: Record<string, unknown>; evidence: { url: string }[] };
    const r = wf.report.data as PairReport;
    expect(m.model.calibrated_score).toBe(r.model.calibrated_model_score);
    expect(m.model.raw_score).toBe(r.model.raw_model_score);
    expect(m.evidence[0].url).toBe(r.evidence[0].source_url);
    const c = companionJson(prep, payloadOf(prep.input)) as { payload: unknown; payload_sha256: string };
    expect(c.payload).toEqual({ report: r, graph: null });
    expect(await sha256Hex(canonicalJson(c.payload))).toBe(c.payload_sha256);
    const multi = machineSummary(await prepareExport({ kind: "multi", report: m8 }, ctx())) as { pairs: unknown[] };
    expect(multi.pairs).toHaveLength((m8.data as MultiReport).pairs.length);
  });
});

describe("diagram geometry", () => {
  const cases: [string, PairReport, MechanismGraph | null][] = [
    ["warfarin+fluconazole report", wf.report.data, null],
    ["warfarin+fluconazole graph", wf.report.data, wf.graph.data],
    ["simvastatin+clarithromycin graph", sc.report.data, sc.graph.data],
    ["metformin+warfarin graph", mw.report.data, mw.graph.data],
  ];
  for (const [name, r, g] of cases) {
    it(`${name}: every label inside the frame, none overlapping`, () => {
      for (const lang of ["en", "ru"] as const) {
        const d = diagramData(r, g, { a: drugName(r.drug_a, lang), b: drugName(r.drug_b, lang) });
        const lay = layoutMechanism(d, CONTENT_WIDTH, lang, { onlyA: "ONLY A", onlyB: "ONLY B", shared: "SHARED" });
        for (const b of lay.labels) expect(inside(b, lay.width, lay.height), `${b.text} outside`).toBe(true);
        for (let i = 0; i < lay.labels.length; i++) {
          for (let j = i + 1; j < lay.labels.length; j++) {
            expect(overlaps(lay.labels[i], lay.labels[j]), `${lay.labels[i].text} overlaps ${lay.labels[j].text}`).toBe(false);
          }
        }
        // a trunk never runs through a pill, so no line seems to end where it does not
        for (const p of lay.pills) for (const tr of lay.trunks) expect(tr.x > p.x && tr.x < p.x + p.w && tr.y2 > p.y && tr.y1 < p.y + p.h, `${p.label} crossed`).toBe(false);
        // documented link: present exactly when the payload has a record, never with a direction
        const hasRecord = g ? g.edges.some((e) => e.kind === "documented_interaction") : r.evidence.some((e) => e.category === "database_interaction_record");
        expect(lay.link !== null).toBe(hasRecord);
        if (hasRecord) expect(d.documented).toBe("undirected");
      }
    });
  }

  it("network labels stay inside the frame and apart, for 2 to 8 drugs", () => {
    for (let n = 2; n <= 8; n++) {
      const names = Array.from({ length: n }, (_, i) => `${i + 1} ${"Clarithromycin-long-name".slice(0, 10 + i)}`);
      const { nodes } = layoutNetwork(names.map((_, i) => `DB0${i}`), names, CONTENT_WIDTH, 212, 6.8);
      const boxes = nodes.map((nd) => labelBox(nd, 6.8));
      boxes.forEach((b) => expect(inside(b, CONTENT_WIDTH, 212)).toBe(true));
      for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) expect(overlaps(boxes[i], boxes[j])).toBe(false);
    }
  });
});

describe("pooled metric note for responses that predate the backend fix", () => {
  it("is added only to S2 sentences that quote a metric without saying pooled", () => {
    const old = { en: "Model quality on held-out pairs where the model did not see one of the drugs in training (as here): AUPRC 0.812 ± 0.010 over 5 runs.", ru: "" };
    const fixed = { en: "Model quality on the pooled held-out test (S2 and S3 pairs together, 91% S2; the frozen results hold no S2-only figure): AUPRC 0.812 ± 0.010.", ru: "" };
    const s3 = { en: "Model quality on held-out pairs where the model saw neither drug in training (S3, as here): AUPRC 0.737 ± 0.015.", ru: "" };
    expect(needsPooledNote(old, "S2")).toBe(true);
    expect(needsPooledNote(fixed, "S2")).toBe(false);
    expect(needsPooledNote(s3, "S3")).toBe(false);
    expect(needsPooledNote({ en: "No metric here.", ru: "" }, "S2")).toBe(false);
  });
});

describe("colour and wording rules", () => {
  const hue = (hex: string) => {
    const n = parseInt(hex.slice(1), 16);
    const r = ((n >> 16) & 255) / 255, g = ((n >> 8) & 255) / 255, b = (n & 255) / 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
    if (d === 0) return -1;
    const h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
    return (h * 60 + 360) % 360;
  };

  it("no evidence colour is green", () => {
    for (const c of [...Object.values(EV), ...Object.values(STATUS_COLOR)]) {
      const h = hue(c);
      expect(h < 75 || h > 165, `${c} hue ${h}`).toBe(true);
    }
  });

  it("no advice or safety claim anywhere in the report's own text", () => {
    const forbidden = [
      /\bsafe to (take|combine|use)\b/i, /\bsafe together\b/i, /\bSAFE TO TAKE\b/, /\byou should\b/i,
      /\bstop taking\b/i, /\bstart taking\b/i, /\b(increase|decrease|reduce|change|adjust) (the|your) dose\b/i,
      /можно (спокойно )?принимать/i, /безопасно (принимать|сочетать|применять)/i, /прекратите/i,
      /(измените|снизьте|увеличьте|уменьшите) дозу/i, /не принимайте/i, /рекомендуем/i,
      /\brisk of\b/i, /\bprobability of (an )?interaction\b/i,
    ];
    const files = [
      ...readdirSync(__dirname).filter((f) => /\.tsx?$/.test(f) && !f.includes(".test.")).map((f) => join(__dirname, f)),
      ...["plainLanguage.ts", "evidenceGroups.ts", "scoreFormat.ts", "outcomeText.ts"].map((f) => join(__dirname, "..", "data", f)),
    ];
    for (const f of files) {
      const text = readFileSync(f, "utf8");
      for (const p of forbidden) expect(p.test(text), `${p} in ${f}`).toBe(false);
    }
  });

  it("every string exists in both languages and keeps its placeholders", () => {
    for (const [k, v] of Object.entries(S)) {
      expect(v.ru && v.en, k).toBeTruthy();
      const ph = (s: string) => (s.match(/\{\w+\}/g) ?? []).sort().join();
      expect(ph(v.ru), k).toBe(ph(v.en));
    }
    expect(t("page", "ru", { n: 2, t: 9 })).toBe("Стр. 2 из 9");
  });
});
