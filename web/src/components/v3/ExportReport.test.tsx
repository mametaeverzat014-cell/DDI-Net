// The export controls: disabled until there is a result, both languages,
// a status that is announced, a helpful error, nothing downloaded on failure.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup, act } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { LanguageProvider } from "../../i18n";
import { ExportReport } from "./ExportReport";
import type { ExportInput } from "../../pdf/types";

const exportPdf = vi.fn();
const exportJson = vi.fn();
const download = vi.fn();
vi.mock("../../pdf/exportReport", () => ({ exportPdf: (...a: unknown[]) => exportPdf(...a), exportJson: (...a: unknown[]) => exportJson(...a), download: (...a: unknown[]) => download(...a) }));

const fixture = JSON.parse(readFileSync(join(__dirname, "..", "..", "pdf", "__fixtures__", "pair_warfarin_fluconazole.json"), "utf8"));
const input: ExportInput = { kind: "pair", origin: "analyzer", report: fixture.report };

function setup(lang: "ru" | "en", value: ExportInput | null) {
  localStorage.setItem("ddinet.lang", lang);
  return render(<LanguageProvider><ExportReport input={value} id="t" /></LanguageProvider>);
}

beforeEach(() => { exportPdf.mockReset(); exportJson.mockReset(); download.mockReset(); });
afterEach(() => { cleanup(); localStorage.clear(); });

describe("ExportReport", () => {
  it("is disabled, and says why, before results exist", () => {
    setup("en", null);
    expect((screen.getByRole("button", { name: /Export PDF/ }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: /^JSON/ }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("Available once results are shown.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Export PDF/ }));
    expect(exportPdf).not.toHaveBeenCalled();
  });

  it("speaks Russian by default", () => {
    setup("ru", null);
    expect(screen.getByRole("button", { name: /Экспорт PDF/ })).toBeTruthy();
    expect(screen.getByText("Станет доступно, когда появятся результаты.")).toBeTruthy();
  });

  it("exports the analysis it is given, in the page language, and reports the file", async () => {
    exportPdf.mockResolvedValue({ blob: new Blob(["%PDF-1.3"]), filename: "DDI-Net_Report_Warfarin_Fluconazole_2026-10-14.pdf", reportId: "DDI-X" });
    setup("en", input);
    const btn = screen.getByRole("button", { name: /Export PDF/ }) as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
    expect(btn.getAttribute("aria-describedby")).toBe("t-status");
    fireEvent.click(btn);
    await waitFor(() => expect(screen.getByText("File saved: DDI-Net_Report_Warfarin_Fluconazole_2026-10-14.pdf")).toBeTruthy());
    expect(exportPdf).toHaveBeenCalledWith(input, "en", "full");
    expect(download).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("status").textContent).toContain("File saved");
  });

  it("offers a quick report for a pair and exports it as the quick variant", async () => {
    exportPdf.mockResolvedValue({ blob: new Blob(["%PDF-1.3"]), filename: "DDI-Net_QuickReport_Warfarin_Fluconazole_2026-10-14.pdf", reportId: "DDI-X" });
    setup("en", input);
    fireEvent.click(screen.getByRole("button", { name: /Quick PDF/ }));
    await waitFor(() => expect(screen.getByText(/File saved: DDI-Net_QuickReport/)).toBeTruthy());
    expect(exportPdf).toHaveBeenCalledWith(input, "en", "quick");
  });

  it("shows a loading state and blocks a second export meanwhile", async () => {
    let finish: (v: unknown) => void = () => {};
    exportPdf.mockReturnValue(new Promise((r) => { finish = r; }));
    setup("en", input);
    fireEvent.click(screen.getByRole("button", { name: /Export PDF/ }));
    await waitFor(() => expect(screen.getByText("Generating PDF…")).toBeTruthy());
    expect((screen.getByRole("button", { name: /Export PDF/ }) as HTMLButtonElement).disabled).toBe(true);
    await act(async () => finish({ blob: new Blob(["x"]), filename: "a.pdf", reportId: "r" }));
    expect(exportPdf).toHaveBeenCalledTimes(1);
  });

  it("explains a failure, downloads nothing, and announces it as an alert", async () => {
    exportPdf.mockRejectedValue(new TypeError("Failed to fetch dynamically imported module: https://x/assets/exportReport.js"));
    setup("ru", input);
    fireEvent.click(screen.getByRole("button", { name: /Экспорт PDF/ }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Обновите страницу");
    expect(alert.textContent).toContain("Ничего не было скачано");
    expect(download).not.toHaveBeenCalled();
  });

  it("offers the companion JSON", async () => {
    exportJson.mockResolvedValue({ blob: new Blob(["{}"]), filename: "x.json", reportId: "r" });
    setup("en", input);
    fireEvent.click(screen.getByRole("button", { name: /^JSON/ }));
    await waitFor(() => expect(download).toHaveBeenCalledTimes(1));
    expect(exportJson).toHaveBeenCalledWith(input, "en");
  });

  it("clears the previous outcome when a new analysis arrives", async () => {
    exportPdf.mockRejectedValue(new Error("boom"));
    const { rerender } = setup("en", input);
    fireEvent.click(screen.getByRole("button", { name: /Export PDF/ }));
    await screen.findByRole("alert");
    rerender(<LanguageProvider><ExportReport input={{ ...input }} id="t" /></LanguageProvider>);
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });
});
