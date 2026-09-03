// Horizontal AUPRC bar chart with an HONEST axis. The domain starts at 0.5
// (a random ranker at prevalence 0.5), never at the minimum bar — truncating
// would visually exaggerate small differences, which the brief forbids.
// A 95% CI bracket is drawn on each bar when a std is available.
import type { ModelRow } from "../data/frozen";
import { auprc } from "../lib/format";

const CAT_COLOR: Record<string, string> = {
  primary: "var(--cyan)",
  "ladder-primary": "var(--cyan)",
  baseline: "var(--blue)",
  ladder: "var(--blue)",
  control: "var(--violet)",
  "ladder-control": "var(--violet)",
};

const DOMAIN_MIN = 0.5;
const DOMAIN_MAX = 0.85;

function x(v: number): number {
  return ((Math.min(v, DOMAIN_MAX) - DOMAIN_MIN) / (DOMAIN_MAX - DOMAIN_MIN)) * 100;
}

export function AuprcBars({
  rows,
  metric,
  title,
}: {
  rows: ModelRow[];
  metric: "pooled" | "s3";
  title?: string;
}) {
  return (
    <div>
      {title && <span className="eyebrow" style={{ display: "block", marginBottom: 14 }}>{title}</span>}
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {rows.map((r) => {
          const mean = metric === "pooled" ? r.pooled_mean : r.s3_mean;
          const sd = metric === "pooled" ? r.pooled_std : r.s3_std;
          if (mean === null) return null;
          const color = CAT_COLOR[r.category] ?? "var(--blue)";
          const ciLo = sd !== null ? x(mean - 1.96 * sd) : null;
          const ciHi = sd !== null ? x(mean + 1.96 * sd) : null;
          return (
            <div key={r.label + metric} style={{ display: "grid", gridTemplateColumns: "minmax(150px, 230px) 1fr auto", gap: 16, alignItems: "center" }}>
              <span style={{ fontSize: 13, color: "var(--text-2)" }}>{r.label}</span>
              <div
                role="img"
                aria-label={`${r.label}: ${auprc(mean)} AUPRC`}
                style={{ position: "relative", height: 22, background: "rgba(255,255,255,0.03)", borderRadius: 4, border: "1px solid var(--border-soft)" }}
              >
                <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${x(mean)}%`, background: `linear-gradient(90deg, ${color}22, ${color})`, borderRadius: 4 }} />
                {ciLo !== null && ciHi !== null && (
                  <div title="95% interval (mean ± 1.96·SD)" style={{ position: "absolute", left: `${ciLo}%`, width: `${ciHi - ciLo}%`, top: "50%", transform: "translateY(-50%)", height: 10, borderLeft: "1px solid var(--text-2)", borderRight: "1px solid var(--text-2)" }}>
                    <div style={{ position: "absolute", top: "50%", left: 0, right: 0, height: 1, background: "var(--text-2)", opacity: 0.5 }} />
                  </div>
                )}
              </div>
              <span className="mono" style={{ fontSize: 13, color: "var(--text)", minWidth: 52, textAlign: "right" }}>{auprc(mean)}</span>
            </div>
          );
        })}
      </div>
      <div className="mono" style={{ display: "flex", justifyContent: "space-between", marginTop: 10, fontSize: 10, color: "var(--text-3)" }}>
        <span>AUPRC {DOMAIN_MIN.toFixed(2)} (random at prevalence 0.5)</span>
        <span>{DOMAIN_MAX.toFixed(2)}</span>
      </div>
    </div>
  );
}
