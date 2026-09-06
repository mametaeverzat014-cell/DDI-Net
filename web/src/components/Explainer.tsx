// "What am I looking at?" — a collapsible plain-language guide to every number
// on the Analyze page.
//
// WHY IT IS WRITTEN THE WAY IT IS. Simplifying an interaction score is exactly
// where a page slides into "the higher the number, the more dangerous" — which
// is both forbidden wording and false. The frozen dataset holds documented
// interactions and sampled UNLABELLED pairs, not clinical outcomes, so the
// score says how much a pair resembles the documented kind and nothing about
// harm. Every entry below is phrased to be understandable without becoming
// wrong, and the last section says outright what the page does not mean.
//
// <details>/<summary> rather than a state hook: it is keyboard-accessible and
// screen-reader-announced for free, and it survives with JavaScript disabled.
import { useI18n, pick } from "../i18n";
import { CAVEATS, DRUG_NUMBERS, HOW_IT_WORKS, SCORE_NUMBERS, type Entry } from "./explainerContent";

export function Explainer() {
  const { t, lang } = useI18n();
  return (
    <details style={{ marginTop: 26, border: "1px solid var(--border)", borderRadius: "var(--radius)", background: "var(--surface)" }}>
      <summary
        style={{
          cursor: "pointer", padding: "14px 18px", listStyle: "none",
          display: "flex", alignItems: "center", gap: 10,
          fontSize: 14, color: "var(--cyan)", userSelect: "none",
        }}
      >
        <span aria-hidden style={{ fontSize: 11 }}>▸</span>
        {t("ex.open")}
      </summary>

      <div style={{ padding: "0 18px 22px", borderTop: "1px solid var(--border-soft)" }}>
        <p style={{ marginTop: 16, maxWidth: 760, fontSize: 14 }}>{pick(HOW_IT_WORKS, lang)}</p>

        <Section title={t("ex.drug")} entries={DRUG_NUMBERS} lang={lang} />
        <Section title={t("ex.score")} entries={SCORE_NUMBERS} lang={lang} />

        <h4 style={{ marginTop: 26, marginBottom: 10, fontSize: 12, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--amber)" }}>
          {t("ex.caveats")}
        </h4>
        <ul style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 8, maxWidth: 760 }}>
          {CAVEATS.map((c) => (
            <li key={c.en} style={{ fontSize: 13.5, color: "var(--text-2)" }}>{pick(c, lang)}</li>
          ))}
        </ul>
      </div>
    </details>
  );
}

function Section({ title, entries, lang }: { title: string; entries: Entry[]; lang: "ru" | "en" }) {
  return (
    <>
      <h4 style={{ marginTop: 26, marginBottom: 10, fontSize: 12, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--text-3)" }}>
        {title}
      </h4>
      <dl style={{ margin: 0, display: "flex", flexDirection: "column", gap: 12, maxWidth: 760 }}>
        {entries.map((e) => (
          <div key={e.term.en}>
            <dt style={{ fontSize: 14, fontWeight: 600, color: "var(--text)" }}>{pick(e.term, lang)}</dt>
            <dd style={{ margin: "3px 0 0", fontSize: 13.5, color: "var(--text-2)", lineHeight: 1.65 }}>
              {pick(e.body, lang)}
            </dd>
          </div>
        ))}
      </dl>
    </>
  );
}
