// The outcome view shows only what the API's outcome block supports, quotes its
// sources, keeps hypotheses out of "What could happen?", never shows the model
// as risk, and falls back plainly for API versions without the block.
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render, fireEvent } from "@testing-library/react";
import { LanguageProvider } from "../../i18n";
import { OutcomeOverview } from "./OutcomeParts";
import { MultiOutcomes } from "./MultiOutcomes";
import { buildRefIndex } from "./refs";
import type { MultiReport, PairReport } from "../../data/v3";

const FX = join(__dirname, "..", "..", "pdf", "__fixtures__");
const pair = (n: string) => JSON.parse(readFileSync(join(FX, n), "utf8")).report.data as PairReport;
const multi = (n: string) => JSON.parse(readFileSync(join(FX, n), "utf8")).data as MultiReport;

const view = (r: PairReport, research = false) => render(
  <LanguageProvider><OutcomeOverview report={r} refs={buildRefIndex(r)} research={research} /></LanguageProvider>,
);

describe("outcome overview", () => {
  it("label evidence: documented interaction, bleeding quoted verbatim, hypotheses kept out of B", () => {
    // SYNTHETIC label text (tests/synthetic_labels.py)
    const r = pair("pair_synthetic_merged_labels.json");
    const { container } = view(r);
    const text = container.textContent!;
    expect(text).toContain(r.outcomes!.interaction_status_label.ru);
    const bleed = r.outcomes!.outcomes.find((o) => o.effect === "bleeding")!;
    expect(text).toContain(bleed.label.ru);
    for (const s of bleed.supports) expect(text).toContain(s.excerpt);
    for (const h of r.outcomes!.outcomes.filter((o) => o.research_only)) expect(text).not.toContain(h.label.ru);
    expect(text).toContain("Степень серьёзности не установлена по доступным данным.");
  });

  it("no documentation, label source down: says it cannot assess, not that it is safe; no outcome card", () => {
    // captured from a local API whose network blocked openFDA
    const r = pair("pair_outcomes_metformin_warfarin.json");
    const { container } = view(r);
    expect(r.outcomes!.interaction_status).toBe("source_unavailable");
    expect(container.textContent).toContain("Оценить пару полностью нельзя");
    expect(container.textContent).toContain("не означает, что сочетание безопасно");
    expect(container.querySelectorAll("article")).toHaveLength(0);
  });

  it("model score is shown only as a research note", () => {
    const r = pair("pair_outcomes_warfarin_fluconazole.json");
    const { container } = view(r);
    const e = container.querySelector("#outcomes-e")!.textContent!;
    expect(e).toContain("0.81");
    expect(e).toContain("не является вероятностью вреда");
    expect(container.querySelector("[role=status]")!.textContent).not.toContain("0.81");
  });

  it("chain links show their provenance and reveal their basis when selected", () => {
    const r = pair("pair_outcomes_warfarin_fluconazole.json");
    const { container, getAllByRole } = view(r, true);
    expect(container.textContent).toContain("проверенная аннотация");
    fireEvent.click(getAllByRole("button", { name: /проверенная аннотация/ })[0]);
    const pressed = getAllByRole("button", { name: /проверенная аннотация/ })[0];
    expect(pressed.getAttribute("aria-pressed")).toBe("true");
    expect(container.textContent).toContain("отмечен как ингибитор");
  });

  it("older API responses fall back with a notice", () => {
    const r = pair("pair_warfarin_fluconazole.json");
    expect(r.outcomes).toBeUndefined();
    const { container } = view(r);
    expect(container.textContent).toContain("не содержит анализа последствий");
  });
});

describe("multi-drug outcomes", () => {
  it("lists categories per pair, filters, and computes no overall score", () => {
    const m = multi("multi_outcomes_6.json");
    const { container, getByLabelText } = render(<LanguageProvider><MultiOutcomes report={m} label={(id) => id} onPick={() => undefined} /></LanguageProvider>);
    expect(container.textContent).toContain("Кровотечения и свёртываемость крови");
    expect(container.textContent).toContain("не означает, что эффекты складываются");
    fireEvent.change(getByLabelText("Фильтр по категории"), { target: { value: "bleeding_coagulation" } });
    const items = Array.from(container.querySelectorAll("li")).filter((li) => li.textContent!.includes("→"));
    expect(items.length).toBe(m.pairs.filter((p) => (p.outcome_categories ?? []).includes("bleeding_coagulation")).length);
    expect(container.textContent!.toLowerCase()).not.toMatch(/overall|общий балл/);
  });
});
