// The v3 client's contract: every response maps to a distinct state, and none
// of the failure states can be mistaken for an empty ("nothing found") report.
import { describe, it, expect, vi, afterEach } from "vitest";
import { interpret, fetchReport } from "./v3";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

afterEach(() => vi.unstubAllGlobals());

describe("v3 client", () => {
  it("is unconfigured in the default build and never calls the network", async () => {
    const spy = vi.fn();
    vi.stubGlobal("fetch", spy);
    expect(await fetchReport("DB00682", "DB00196")).toEqual({ kind: "unconfigured" });
    expect(spy).not.toHaveBeenCalled();
  });

  it("maps 200 to ok", async () => {
    const r = await interpret(json(200, { report_version: "3.0" }));
    expect(r).toEqual({ kind: "ok", data: { report_version: "3.0" } });
  });

  it("maps 503 to unavailable, with the server's reason", async () => {
    const r = await interpret(json(503, { detail: "evidence layer unavailable: artifact missing" }));
    expect(r).toEqual({ kind: "unavailable", message: "evidence layer unavailable: artifact missing" });
  });

  it("maps 404 (an older API without /api/v3) to unavailable, not to an empty report", async () => {
    const r = await interpret(json(404, { detail: "Not Found" }));
    expect(r.kind).toBe("unavailable");
  });

  it("maps an unresolved drug to unresolved, keeping the candidates", async () => {
    const r = await interpret(json(422, { detail: { message: "x", resolutions: [{ query: "warfarn", status: "suggestions", candidates: [{ id: "DB00682", inn: "warfarin", name_ru: "варфарин" }], drug: null, note: null, rxnorm: null }] } }));
    expect(r.kind).toBe("unresolved");
    if (r.kind === "unresolved") expect(r.resolutions[0].candidates[0].id).toBe("DB00682");
  });

  it("maps a validation 422 to error with the message", async () => {
    const r = await interpret(json(422, { detail: [{ msg: "field required" }] }));
    expect(r).toEqual({ kind: "error", message: "field required" });
  });
});
