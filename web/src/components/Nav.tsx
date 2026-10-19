// Fixed top bar. Client-side view switching with the view mirrored in the URL
// hash (lib/route.ts). DDI-Net 3.0 information architecture: Overview,
// Analyzer, Mechanisms, Multi-drug, Research results, Model & methodology,
// Data & evidence, Limitations. The v2 score page and the drug explorer remain
// reachable from the Analyzer and the Data page.
//
// On narrow screens the eight items collapse into a menu button; a wrapped
// three-line bar would cover the content it is meant to navigate.
//
// The RU/EN switch changes UI language only; it never changes a number, an
// identifier or a data value.
import { useState } from "react";
import type { View } from "../App";
import { useI18n, type Lang } from "../i18n";

const ITEMS: { id: View; key: string }[] = [
  { id: "home", key: "nav.overview" },
  { id: "analyzer", key: "nav.analyzer" },
  { id: "mechanisms", key: "nav.mechanisms" },
  { id: "multi", key: "nav.multi" },
  { id: "research", key: "nav.research" },
  { id: "model", key: "nav.model" },
  { id: "data", key: "nav.data" },
  { id: "limitations", key: "nav.limitations" },
];

/** Views that live under a nav item without having their own. */
const PARENT: Partial<Record<View, View>> = { analyze: "analyzer", drugs: "data" };

export function Nav({ view, setView }: { view: View; setView: (v: View) => void }) {
  const { t, lang, setLang } = useI18n();
  const [open, setOpen] = useState(false);
  const activeId = PARENT[view] ?? view;
  const go = (v: View) => { setView(v); setOpen(false); };

  return (
    <nav
      className="ddi-nav"
      style={{
        position: "fixed", top: 0, left: 0, right: 0, zIndex: 60,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        gap: 12,
        padding: "14px clamp(16px, 4vw, 48px)",
        backdropFilter: "blur(14px)",
        background: "linear-gradient(to bottom, rgba(6,16,31,0.92), rgba(6,16,31,0.35))",
      }}
    >
      <button
        onClick={() => go("home")}
        aria-label={t("nav.home")}
        style={{ display: "flex", alignItems: "center", gap: 10, background: "none", border: "none", cursor: "pointer", padding: 0 }}
      >
        <span style={{ width: 9, height: 9, borderRadius: "50%", background: "var(--cyan)", boxShadow: "0 0 12px var(--cyan)" }} />
        <span className="mono" style={{ color: "var(--text)", fontSize: 14, letterSpacing: "0.08em", whiteSpace: "nowrap" }}>DDI-NET</span>
        <span className="mono" style={{ color: "var(--cyan)", fontSize: 10, letterSpacing: "0.1em", border: "1px solid rgba(111,227,245,0.35)", borderRadius: 4, padding: "1px 5px" }}>3.0</span>
      </button>

      <div className={`ddi-nav-items${open ? " open" : ""}`} id="ddi-nav-items">
        {ITEMS.map((it) => {
          const active = activeId === it.id;
          return (
            <button
              key={it.id}
              onClick={() => go(it.id)}
              aria-current={active ? "page" : undefined}
              className="mono"
              style={{
                background: active ? "rgba(111,227,245,0.08)" : "none",
                border: active ? "1px solid rgba(111,227,245,0.3)" : "1px solid transparent",
                color: active ? "var(--cyan)" : "var(--text-3)",
                fontSize: 10.5, letterSpacing: "0.12em", padding: "6px 10px",
                borderRadius: 20, cursor: "pointer", transition: "color 0.3s var(--ease)", whiteSpace: "nowrap",
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
          className="mono ddi-nav-repo"
          style={{ fontSize: 11, letterSpacing: "0.1em", color: "var(--text-2)", border: "1px solid var(--border-strong)", padding: "6px 14px", borderRadius: 20, whiteSpace: "nowrap" }}
        >
          {t("nav.repo")} ↗
        </a>

        <button
          className="mono ddi-nav-menu"
          aria-expanded={open}
          aria-controls="ddi-nav-items"
          onClick={() => setOpen(!open)}
          style={{ background: "none", border: "1px solid var(--border-strong)", color: "var(--text-2)", borderRadius: 20, padding: "6px 12px", fontSize: 11, letterSpacing: "0.1em", cursor: "pointer" }}
        >
          {open ? "×" : t("nav.menu")}
        </button>
      </div>
    </nav>
  );
}
