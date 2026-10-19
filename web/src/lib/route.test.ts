import { describe, it, expect } from "vitest";
import { parseHash, toHash } from "./route";

describe("hash routing", () => {
  it("round-trips a pair view", () => {
    const h = toHash("analyzer", ["DB00682", "DB00196"]);
    expect(h).toBe("#/analyzer?a=DB00682&b=DB00196");
    expect(parseHash(h)).toEqual({ view: "analyzer", pair: ["DB00682", "DB00196"] });
  });

  it("ignores what it cannot parse instead of guessing", () => {
    expect(parseHash("")).toEqual({});
    expect(parseHash("#/nonsense")).toEqual({});
    expect(parseHash("#/analyzer?a=warfarin&b=DB00196")).toEqual({ view: "analyzer" });
    expect(parseHash("#/analyzer?a=DB00682&b=DB00682")).toEqual({ view: "analyzer" });
  });

  it("does not put a pair in URLs of views that have none", () => {
    expect(toHash("research", ["DB00682", "DB00196"])).toBe("#/research");
  });
});
