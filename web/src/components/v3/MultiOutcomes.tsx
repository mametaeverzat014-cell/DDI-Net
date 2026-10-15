// Multi-drug outcome explorer: per-pair documented outcome categories, a
// filterable pair matrix, and categories shared by several pairs. Pairwise only:
// nothing here adds effects up, infers three-way interactions or scores the set.
import { useMemo, useState } from "react";
import { useI18n, pick } from "../../i18n";
import type { InteractionStatus, MultiPair, MultiReport } from "../../data/v3";
import { OT } from "../../data/outcomeText";

const SHORT: Record<InteractionStatus, { code: string; color: string; ru: string; en: string }> = {
  documented_interaction: { code: "D", color: "var(--ev-label)", ru: "задокументировано", en: "documented" },
  documented_outcome_unclear: { code: "D?", color: "var(--ev-documented)", ru: "есть данные, последствие не ясно", en: "evidence, outcome unclear" },
  research_prediction_only: { code: "H", color: "var(--ev-hypothesis)", ru: "только гипотеза", en: "hypothesis only" },
  insufficient_evidence: { code: "–", color: "var(--ev-none)", ru: "недостаточно данных", en: "insufficient evidence" },
  source_unavailable: { code: "!", color: "var(--ev-missing)", ru: "источник недоступен", en: "source unavailable" },
};

export function MultiOutcomes({ report, label, onPick }: { report: MultiReport; label: (id: string) => string; onPick: (p: MultiPair) => void }) {
  const { lang } = useI18n();
  const [cat, setCat] = useState<string>("");
  const cats = report.outcome_categories ?? {};
  const has = report.pairs.some((p) => p.interaction_status);
  const pairOf = useMemo(() => {
    const m = new Map<string, MultiPair>();
    for (const p of report.pairs) { m.set(`${p.drug_a}|${p.drug_b}`, p); m.set(`${p.drug_b}|${p.drug_a}`, p); }
    return m;
  }, [report]);
  if (!has) return null;
  const ids = report.drugs.map((d) => d.id);
  const shared = Object.entries(report.shared_outcome_categories ?? {});
  return (
    <div className="v3-card">
      <h3 style={{ fontSize: 18 }}>{pick(OT.bTitle, lang)}</h3>
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginTop: 10 }}>
        <label htmlFor="outcome-filter" className="eyebrow">{pick(OT.filter, lang)}</label>
        <select id="outcome-filter" value={cat} onChange={(e) => setCat(e.target.value)}
          style={{ background: "rgba(0,0,0,0.25)", color: "var(--text)", border: "1px solid var(--border-strong)", borderRadius: 6, padding: "6px 8px", fontFamily: "var(--font-ui)", fontSize: 13 }}>
          <option value="">{pick(OT.all, lang)}</option>
          {Object.entries(cats).map(([k, v]) => <option key={k} value={k}>{pick(v, lang)}</option>)}
        </select>
      </div>
      <div className="v3-scroll" style={{ marginTop: 12 }}>
        <table className="v3-table" aria-label="pair outcome matrix">
          <thead><tr><th />{ids.map((id) => <th key={id} style={{ fontSize: 11 }}>{label(id)}</th>)}</tr></thead>
          <tbody>
            {ids.map((r, ri) => (
              <tr key={r}>
                <th style={{ fontSize: 11.5, textAlign: "left" }}>{label(r)}</th>
                {ids.map((c, ci) => {
                  if (ci <= ri) return <td key={c} />;
                  const p = pairOf.get(`${r}|${c}`);
                  if (!p || !p.interaction_status) return <td key={c}>—</td>;
                  const s = SHORT[p.interaction_status];
                  const hit = cat && (p.outcome_categories ?? []).includes(cat);
                  const dim = cat && !hit;
                  return (
                    <td key={c} style={{ opacity: dim ? 0.3 : 1, outline: hit ? `2px solid ${s.color}` : "none" }}>
                      <button onClick={() => onPick(p)} title={`${label(p.drug_a)} + ${label(p.drug_b)}: ${lang === "ru" ? s.ru : s.en}`}
                        aria-label={`${label(p.drug_a)} + ${label(p.drug_b)}: ${lang === "ru" ? s.ru : s.en}`}
                        style={{ background: "none", border: "none", color: s.color, cursor: "pointer", fontFamily: "var(--font-mono)", fontSize: 13 }}>
                        {s.code}{(p.outcome_categories ?? []).length ? ` · ${(p.outcome_categories ?? []).length}` : ""}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 14px", marginTop: 8, fontSize: 11.5, color: "var(--text-3)" }}>
        {Object.values(SHORT).map((s) => <span key={s.code}><span style={{ color: s.color, fontFamily: "var(--font-mono)" }}>{s.code}</span> {lang === "ru" ? s.ru : s.en}</span>)}
        <span>· N — {lang === "ru" ? "число задокументированных категорий" : "number of documented categories"}</span>
      </div>

      <ul style={{ listStyle: "none", padding: 0, margin: "14px 0 0", display: "flex", flexDirection: "column", gap: 6 }}>
        {report.pairs.filter((p) => !cat || (p.outcome_categories ?? []).includes(cat)).map((p) => (
          <li key={p.drug_a + p.drug_b} style={{ fontSize: 13 }}>
            <button onClick={() => onPick(p)} style={{ background: "none", border: "none", padding: 0, color: "var(--text)", cursor: "pointer", fontFamily: "var(--font-ui)", fontSize: 13 }}>
              {label(p.drug_a)} + {label(p.drug_b)} →
            </button>{" "}
            <span style={{ color: "var(--text-3)" }}>
              {(p.outcome_categories ?? []).length
                ? (p.outcome_categories ?? []).map((k) => (cats[k] ? pick(cats[k], lang) : k)).join(" · ")
                : pick(OT.noneDocumented, lang)}
            </span>
          </li>
        ))}
      </ul>

      {shared.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <span className="eyebrow">{pick(OT.sharedTitle, lang)}</span>
          <ul style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 13, color: "var(--text-2)" }}>
            {shared.map(([k, pairs]) => (
              <li key={k}>{cats[k] ? pick(cats[k], lang) : k}: {pairs.map(([x, y]) => `${label(x)} + ${label(y)}`).join("; ")}</li>
            ))}
          </ul>
          <p style={{ fontSize: 12.5, marginTop: 6, color: "var(--text-3)" }}>{pick(OT.sharedNote, lang)}</p>
        </div>
      )}
    </div>
  );
}
