// Fixed top bar. Client-side view switching (the SPA has no router yet; views
// switch on state, matching the design prototype). MECHANISM routes to analyze,
// as documented in the handoff — the mechanism explorer lives inside analyze.
//
// The RU/EN switch changes UI language only; it never changes a number, an
// identifier or a data value.
import type { View } from "../App";
import { useI18n, type Lang } from "../i18n";

const ITEMS: { id: View; key: string }[] = [
  { id: "analyze", key: "nav.analyze" },
  { id: "model", key: "nav.model" },
  { id: "research", key: "nav.research" },
  { id: "data", key: "nav.data" },
  { id: "drugs", key: "nav.drugs" },
  { id: "limitations", key: "nav.limitations" },
];

export function Nav({ view, setView }: { view: View; setView: (v: View) => void }) {
  const { t, lang, setLang } = useI18n();
  return (
    <nav
      style={{
        position: "fixed", top: 0, left: 0, right: 0, zIndex: 60,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        gap: 12,
        padding: "16px clamp(20px, 5vw, 56px)",
        backdropFilter: "blur(14px)",
        background: "linear-gradient(to bottom, rgba(6,16,31,0.85), rgba(6,16,31,0))",
      }}
    >
      <button
        onClick={() => setView("home")}
        aria-label={t("nav.home")}
        style={{ display: "flex", alignItems: "center", gap: 10, background: "none", border: "none", cursor: "pointer", padding: 0 }}
      >
        <span style={{ width: 9, height: 9, borderRadius: "50%", background: "var(--cyan)", boxShadow: "0 0 12px var(--cyan)" }} />
        <span className="mono" style={{ color: "var(--text)", fontSize: 14, letterSpacing: "0.08em" }}>DDI-NET</span>
      </button>

      <div style={{ display: "flex", gap: 4, alignItems: "center", flexWrap: "wrap", justifyContent: "flex-end" }}>
        {ITEMS.map((it) => {
          const active = view === it.id;
          return (
            <button
              key={it.id}
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
              {t(it.key)}
            </button>
          );
        })}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div
          role="group"
          aria-label="Язык интерфейса / Interface language"
          style={{ display: "flex", border: "1px solid var(--border-strong)", borderRadius: 20, overflow: "hidden" }}
        >
          {(["ru", "en"] as Lang[]).map((l) => (
            <button
              key={l}
              onClick={() => setLang(l)}
              aria-pressed={lang === l}
              className="mono"
              style={{
                background: lang === l ? "rgba(111,227,245,0.12)" : "none",
                border: "none",
                color: lang === l ? "var(--cyan)" : "var(--text-3)",
                fontSize: 10.5, letterSpacing: "0.1em", padding: "6px 10px", cursor: "pointer",
              }}
            >
              {l.toUpperCase()}
            </button>
          ))}
        </div>

        <a
          href="https://github.com/mametaeverzat014-cell/DDI-Net"
          target="_blank" rel="noreferrer"
          className="mono"
          style={{ fontSize: 11, letterSpacing: "0.1em", color: "var(--text-2)", border: "1px solid var(--border-strong)", padding: "6px 14px", borderRadius: 20, whiteSpace: "nowrap" }}
        >
          {t("nav.repo")} ↗
        </a>
      </div>
    </nav>
  );
}
