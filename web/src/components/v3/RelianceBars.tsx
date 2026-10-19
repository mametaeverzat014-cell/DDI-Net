// Model reliance by modality: how far the frozen model's raw score moves when
// the molecular, protein or pathway branch is zeroed for both drugs.
//
// Shown with its validation (reproduces the frozen V2 analysis on all of its
// test pairs) and with its limit stated next to it: reliance is what the model
// leans on, not why two drugs interact.
import { useI18n, pick, type Bi } from "../../i18n";
import type { ModalityReliance } from "../../data/v3";

const T = {
  title: { ru: "На что опирается модель", en: "What the model leans on" },
  lead: { ru: "Изменение сырой оценки, если убрать один вид данных у обоих препаратов", en: "Change in the raw score when one kind of data is removed for both drugs" },
  molecular: { ru: "строение молекул", en: "molecular structure" },
  protein: { ru: "белки", en: "proteins" },
  pathway: { ru: "биологические пути", en: "pathways" },
  validated: { ru: "Воспроизводит замороженный анализ V2 на всех его тестовых парах", en: "Reproduces the frozen V2 analysis on all of its test pairs" },
  saturated: {
    ru: "Сырая оценка близка к краю шкалы (0 или 1). Там изменения сжимаются, и опора модели может выглядеть меньше, чем есть.",
    en: "The raw score is close to the edge of the scale (0 or 1). Changes are compressed there, and reliance can look smaller than it is.",
  },
} satisfies Record<string, Bi>;

export function RelianceBars({ r }: { r: ModalityReliance }) {
  const { lang } = useI18n();
  const rows = [
    { key: "protein" as const, d: r.delta_protein },
    { key: "molecular" as const, d: r.delta_molecular },
    { key: "pathway" as const, d: r.delta_pathway },
  ];
  return (
    <div>
      <span className="eyebrow">{pick(T.title, lang)}</span>
      <p style={{ fontSize: 12, marginTop: 6 }}>{pick(T.lead, lang)}</p>
      <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 10 }}>
        {rows.map(({ key, d }) => (
          <div key={key} style={{ display: "grid", gridTemplateColumns: "120px 1fr 64px", gap: 10, alignItems: "center", fontSize: 12.5 }}>
            <span style={{ color: "var(--text-2)" }}>{pick(T[key], lang)}</span>
            {/* Axis spans 0..1 in probability; the bar starts at the centre and
                grows toward the sign of the change, never truncated. */}
            <div style={{ position: "relative", height: 8, background: "rgba(255,255,255,0.05)", borderRadius: 4 }}>
              <div style={{ position: "absolute", left: "50%", top: -2, bottom: -2, width: 1, background: "var(--border-strong)" }} />
              <div style={{
                position: "absolute", top: 0, bottom: 0, borderRadius: 4, background: "var(--ev-model)",
                left: d >= 0 ? `${50 - Math.min(Math.abs(d), 1) * 50}%` : "50%",
                width: `${Math.min(Math.abs(d), 1) * 50}%`,
              }} />
            </div>
            <span className="mono" style={{ fontSize: 11.5, color: "var(--text)", textAlign: "right" }}>{Math.abs(d) < 0.0005 ? "0.000" : `${d > 0 ? "−" : "+"}${Math.abs(d).toFixed(3)}`}</span>
          </div>
        ))}
      </div>
      {(r.baseline_raw > 0.999 || r.baseline_raw < 0.001) && (
        <p style={{ fontSize: 12, color: "var(--ev-missing)", marginTop: 10 }}>{pick(T.saturated, lang)}</p>
      )}
      <p style={{ fontSize: 12, color: "var(--text-3)", marginTop: 10 }}>{pick(r.interpretation, lang)}</p>
      <p className="mono" style={{ fontSize: 10, color: "var(--text-3)", marginTop: 6 }}>
        {pick(T.validated, lang)}: n={r.validation.n_rows.toLocaleString(lang)}, max |Δ| {r.validation.max_abs_diff.toExponential(1)}
      </p>
    </div>
  );
}
