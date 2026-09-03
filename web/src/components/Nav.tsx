// Fixed top bar. Client-side view switching (the SPA has no router yet; views
// switch on state, matching the design prototype). MECHANISM routes to analyze,
// as documented in the handoff — the mechanism explorer lives inside analyze.
import type { View } from "../App";

const ITEMS: { id: View; label: string }[] = [
  { id: "analyze", label: "ANALYZE" },
  { id: "analyze", label: "MECHANISM" },
  { id: "model", label: "MODEL" },
  { id: "research", label: "RESEARCH" },
  { id: "data", label: "DATA" },
];

export function Nav({ view, setView }: { view: View; setView: (v: View) => void }) {
  return (
    <nav
      style={{
        position: "fixed", top: 0, left: 0, right: 0, zIndex: 60,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "16px clamp(20px, 5vw, 56px)",
        backdropFilter: "blur(14px)",
        background: "linear-gradient(to bottom, rgba(6,16,31,0.85), rgba(6,16,31,0))",
      }}
    >
      <button
        onClick={() => setView("home")}
        aria-label="DDI-Net home"
        style={{ display: "flex", alignItems: "center", gap: 10, background: "none", border: "none", cursor: "pointer", padding: 0 }}
      >
        <span style={{ width: 9, height: 9, borderRadius: "50%", background: "var(--cyan)", boxShadow: "0 0 12px var(--cyan)" }} />
        <span className="mono" style={{ color: "var(--text)", fontSize: 14, letterSpacing: "0.08em" }}>DDI-NET</span>
      </button>

      <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
        {ITEMS.map((it, i) => {
          const active = view === it.id && !(it.label === "MECHANISM");
          return (
            <button
              key={it.label + i}
              onClick={() => setView(it.id)}
              className="mono"
              style={{
                background: active ? "rgba(111,227,245,0.08)" : "none",
                border: active ? "1px solid rgba(111,227,245,0.3)" : "1px solid transparent",
                color: active ? "var(--cyan)" : "var(--text-3)",
                fontSize: 11, letterSpacing: "0.14em", padding: "6px 12px",
                borderRadius: 20, cursor: "pointer", transition: "color 0.3s var(--ease)",
              }}
            >
              {it.label}
            </button>
          );
        })}
      </div>

      <a
        href="https://github.com/mametaeverzat014-cell/DDI-Net"
        target="_blank" rel="noreferrer"
        className="mono"
        style={{ fontSize: 11, letterSpacing: "0.1em", color: "var(--text-2)", border: "1px solid var(--border-strong)", padding: "6px 14px", borderRadius: 20 }}
      >
        Repository ↗
      </a>
    </nav>
  );
}
