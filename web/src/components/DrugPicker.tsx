// Drug selector over the frozen 1,705-drug universe (public/data/drugs.json).
// Search runs on DrugBank ID, English INN, the Russian transliteration and the
// formula, entirely in the browser — no request leaves the page while typing.
// Shared by the v2 Analyze page and the DDI-Net 3.0 views.
import { useMemo, useState } from "react";
import { matchesQuery, type Drug } from "../data/drugs";
import { useI18n, type Lang } from "../i18n";

/** Name in the active UI language, or null when the drug has no matched INN. */
// eslint-disable-next-line react-refresh/only-export-components
export function nameOf(d: Drug | undefined, lang: Lang): string | null {
  if (!d) return null;
  return (lang === "ru" ? d.inn_ru ?? d.inn : d.inn) ?? null;
}

export function DrugPicker({ label, value, onChange, dataset, accent }: {
  label: string; value: string; onChange: (v: string) => void; dataset: Drug[] | null; accent: string;
}) {
  const { t, lang } = useI18n();
  const [q, setQ] = useState("");
  const matches = useMemo(() => {
    if (!dataset || !q.trim()) return [];
    return dataset.filter((d) => matchesQuery(d, q)).slice(0, 8);
  }, [q, dataset]);

  const current = dataset?.find((d) => d.id === value);
  const currentName = nameOf(current, lang);

  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius)", background: "var(--surface)", padding: 16 }}>
      <span className="eyebrow" style={{ color: accent }}>{label}</span>
      <div style={{ fontSize: 20, color: "var(--text)", marginTop: 8, fontWeight: 600, minHeight: 26 }}>
        {currentName ?? <span className="mono">{value}</span>}
      </div>
      {currentName && <div className="mono" style={{ fontSize: 12, color: accent, marginTop: 2 }}>{value}</div>}
      <input
        aria-label={`${label} — ${t("an.search")}`}
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && matches.length > 0) { onChange(matches[0].id); setQ(""); }
        }}
        placeholder={dataset ? t("an.search") : t("an.loading")}
        disabled={!dataset}
        style={{ marginTop: 12, width: "100%", background: "rgba(0,0,0,0.25)", border: "1px solid var(--border-strong)", borderRadius: 6, color: "var(--text)", padding: "8px 10px", fontSize: 13, fontFamily: "var(--font-ui)" }}
      />
      {matches.length > 0 && (
        <div role="listbox" style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 2 }}>
          {matches.map((d) => {
            const n = nameOf(d, lang);
            return (
              <button key={d.id} role="option" aria-selected={d.id === value} onClick={() => { onChange(d.id); setQ(""); }}
                style={{ textAlign: "left", background: "none", border: "none", color: "var(--text-2)", padding: "5px 6px", fontSize: 12.5, cursor: "pointer", borderRadius: 4, fontFamily: "var(--font-ui)" }}>
                {n ? <span style={{ color: "var(--text)" }}>{n} </span> : null}
                <span className="mono" style={{ color: "var(--cyan)", fontSize: 11 }}>{d.id}</span>{" "}
                <span className="mono" style={{ color: "var(--text-3)", fontSize: 10.5 }}>{d.formula ?? "?"}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
