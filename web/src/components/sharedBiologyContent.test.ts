// The copy that turns "CYP2C9" into something a patient can read. Same risk as
// the explainer: making it understandable is exactly what tempts it into
// "shared enzyme = dangerous", which is neither permitted nor true.
import { describe, it, expect } from "vitest";
import {
  CAVEAT, EMPTY_BODY, EMPTY_TITLE, FACTS_NOT_PREDICTION, HEADING, RELATION_COPY,
} from "./sharedBiologyContent";
import { scoreSentence, SCORE_NOT_RISK } from "./explainerContent";
import { RELATION_ORDER } from "../data/analyze";
import type { Bi } from "../i18n";

const ALL: Bi[] = [
  HEADING, EMPTY_TITLE, EMPTY_BODY, CAVEAT, FACTS_NOT_PREDICTION, SCORE_NOT_RISK,
  ...Object.values(RELATION_COPY).flatMap((c) => [c.title, c.body, c.node]),
  scoreSentence(0.9), scoreSentence(0.5), scoreSentence(0.1),
];

describe("shared-biology copy", () => {
  it("covers every relation the API can return", () => {
    for (const r of RELATION_ORDER) expect(RELATION_COPY[r]).toBeTruthy();
    expect(Object.keys(RELATION_COPY).sort()).toEqual([...RELATION_ORDER].sort());
  });

  it("exists in both languages", () => {
    for (const b of ALL) {
      expect(b.ru.trim().length, `ru missing: ${b.en}`).toBeGreaterThan(0);
      expect(b.en.trim().length, `en missing: ${b.ru}`).toBeGreaterThan(0);
    }
  });

  it("explains each relation without naming a gene", () => {
    // The body text must stand alone for a reader who never looks at the
    // symbols underneath.
    for (const [rel, copy] of Object.entries(RELATION_COPY)) {
      expect(copy.body.ru, `${rel} ru leaks a gene symbol`).not.toMatch(/CYP|SLCO|ABC[BC]/);
      expect(copy.body.en, `${rel} en leaks a gene symbol`).not.toMatch(/CYP|SLCO|ABC[BC]/);
      expect(copy.body.ru.length).toBeGreaterThan(80);
    }
  });
});

describe("shared-biology copy stays inside the safety wording", () => {
  const joined = (lang: "ru" | "en") => ALL.map((b) => b[lang]).join("\n").toLowerCase();

  it("never calls a shared protein dangerous", () => {
    for (const phrase of ["опасное сочетание", "нельзя принимать", "принимать вместе нельзя",
                          "dangerous combination", "do not take", "unsafe to"]) {
      expect(joined("ru") + joined("en")).not.toContain(phrase);
    }
  });

  it("says a shared enzyme is a reason to look, not a sign of danger", () => {
    expect(CAVEAT.ru).toContain("а не признак опасности");
    expect(CAVEAT.en).toContain("not a sign of danger");
  });

  it("refuses the empty state as reassurance", () => {
    // 71% of pairs land here; it is the single most misreadable screen.
    expect(EMPTY_BODY.ru).toContain("не заключение о безопасности");
    expect(EMPTY_BODY.en).toContain("not a safety verdict");
  });

  it("marks the block as facts rather than prediction", () => {
    expect(FACTS_NOT_PREDICTION.ru).toContain("не предсказание");
    expect(FACTS_NOT_PREDICTION.en).toContain("not a model prediction");
  });

  it("states the score is resemblance, not risk", () => {
    expect(SCORE_NOT_RISK.ru).toContain("сходство, а не риск");
    expect(SCORE_NOT_RISK.en).toContain("resemblance, not risk");
  });

  it("score sentences describe resemblance at every band, never danger", () => {
    for (const v of [0.05, 0.3, 0.5, 0.7, 0.95]) {
      const s = scoreSentence(v);
      expect(s.ru).toContain("похожа");
      expect(s.en.toLowerCase()).toMatch(/resembl/);
      expect(s.ru.toLowerCase()).not.toMatch(/опасн|безопасн|риск/);
    }
  });

  it("bands are ordered and cover the whole range", () => {
    expect(scoreSentence(0.9).ru).toContain("сильно");
    expect(scoreSentence(0.5).ru).toContain("умеренно");
    expect(scoreSentence(0.1).ru).toContain("мало");
  });
});
