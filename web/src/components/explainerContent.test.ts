// The explainer is the site's highest-risk copy: it exists to make an
// interaction score understandable, and the obvious way to do that is the one
// forbidden reading — "higher means more dangerous". These tests pin the
// wording so a future simplification cannot quietly cross that line.
import { describe, it, expect } from "vitest";
import { CAVEATS, DRUG_NUMBERS, HOW_IT_WORKS, SCORE_NUMBERS } from "./explainerContent";
import type { Bi } from "../i18n";

const ALL: Bi[] = [
  HOW_IT_WORKS,
  ...DRUG_NUMBERS.flatMap((e) => [e.term, e.body]),
  ...SCORE_NUMBERS.flatMap((e) => [e.term, e.body]),
  ...CAVEATS,
];

describe("explainer copy is complete", () => {
  it("every string exists in both languages", () => {
    for (const b of ALL) {
      expect(b.ru.trim().length, `ru missing for: ${b.en}`).toBeGreaterThan(0);
      expect(b.en.trim().length, `en missing for: ${b.ru}`).toBeGreaterThan(0);
    }
  });

  it("covers every stat the Analyze page renders", () => {
    const terms = DRUG_NUMBERS.map((e) => e.term.en.toLowerCase());
    for (const stat of ["targets", "enzymes", "transporters", "proteins", "pathways"]) {
      expect(terms, `no explanation for the "${stat}" stat`).toContain(stat);
    }
  });

  it("explains every number the prediction panel shows", () => {
    const terms = SCORE_NUMBERS.map((e) => e.term.en.toLowerCase()).join(" | ");
    for (const needle of ["calibrated", "raw model score", "temperature", "dataset record", "provenance"]) {
      expect(terms).toContain(needle);
    }
  });
});

describe("explainer copy stays inside the safety wording", () => {
  const joined = (lang: "ru" | "en") => ALL.map((b) => b[lang]).join("\n").toLowerCase();

  it("never asserts a pair is safe or unsafe to take", () => {
    // Phrases that would be a claim about the combination itself. The word
    // "safe"/"опасно" alone is allowed — the caveats use it under negation,
    // which is the whole point of that section.
    const forbidden = [
      "safe to take", "unsafe to take", "do not combine", "should not be taken",
      "medical advice is", "clinical risk score", "patient risk",
      "можно принимать вместе", "нельзя принимать вместе", "не сочетать",
      "опасное сочетание", "степень опасности пары",
    ];
    for (const lang of ["ru", "en"] as const) {
      for (const phrase of forbidden) {
        expect(joined(lang), `"${phrase}" appears in ${lang} copy`).not.toContain(phrase);
      }
    }
  });

  it("says outright that the score is not a probability of harm", () => {
    expect(joined("ru")).toContain("не вероятность вреда");
    expect(joined("en")).toContain("not a probability of harm");
  });

  it("denies the danger reading explicitly, in both directions", () => {
    // Both halves matter: people misread a low score as reassurance just as
    // readily as a high score as alarm.
    expect(joined("ru")).toContain("не значит «опасно»");
    expect(joined("ru")).toContain("не значит «безопасно»");
    expect(joined("en")).toContain("does not mean");
    expect(joined("en")).toMatch(/high score does not mean .dangerous./);
  });

  it("states that an absent dataset record is not evidence of no interaction", () => {
    expect(joined("ru")).toContain("не значит, что взаимодействия нет");
    expect(joined("en")).toContain("does not mean there is no interaction");
  });

  it("states the model has no patient context", () => {
    expect(joined("ru")).toMatch(/ни возраста, ни дозы/);
    expect(joined("en")).toMatch(/not age, not dose/);
  });

  it("keeps the research-prototype disclaimer in the caveats", () => {
    const caveats = CAVEATS.map((c) => c.ru + c.en).join(" ").toLowerCase();
    expect(caveats).toContain("исследовательский прототип");
    expect(caveats).toContain("research prototype");
  });
});
