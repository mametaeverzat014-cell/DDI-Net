// Hash routing: "#/analyzer?a=DB00682&b=DB00196". Kept tiny on purpose — the
// site is a static SPA with no router dependency. Anything that does not parse
// is ignored rather than guessed: an unknown view or a malformed ID falls back
// to the defaults.
import type { View } from "../App";

const VIEWS: View[] = [
  "home", "analyzer", "mechanisms", "multi", "research", "model", "data", "limitations", "drugs", "analyze",
];
const DRUG_ID = /^DB\d{5}$/;

export function parseHash(hash: string): { view?: View; pair?: [string, string] } {
  const m = /^#\/([a-z]+)(?:\?(.*))?$/.exec(hash.trim());
  if (!m) return {};
  const out: { view?: View; pair?: [string, string] } = {};
  if ((VIEWS as string[]).includes(m[1])) out.view = m[1] as View;
  const q = new URLSearchParams(m[2] ?? "");
  const a = (q.get("a") ?? "").toUpperCase();
  const b = (q.get("b") ?? "").toUpperCase();
  if (DRUG_ID.test(a) && DRUG_ID.test(b) && a !== b) out.pair = [a, b];
  return out;
}

export function toHash(view: View, pair: [string, string]): string {
  return view === "analyzer" || view === "mechanisms"
    ? `#/${view}?a=${pair[0]}&b=${pair[1]}`
    : `#/${view}`;
}
