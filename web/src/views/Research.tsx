import { useState } from "react";
import { AuprcBars } from "../components/AuprcBars";
import { Badge } from "../components/Badge";
import { frozen, hypothesis, model } from "../data/frozen";
import { auprc, delta, meanSd, pValue } from "../lib/format";
import { useI18n, fill } from "../i18n";
import { gloss } from "../data/labels";

export function Research() {
  const { t, lang } = useI18n();
  const [regime, setRegime] = useState<"pooled" | "s3">("pooled");
  const main = frozen.models;
  const ladder = frozen.ladder;

  return (
    <section className="section" style={{ paddingTop: "18vh" }}>
      <div className="wrap">
        <span className="eyebrow">{t("rs.eyebrow")}</span>
        <h1 style={{ marginTop: 18, maxInlineSize: "16ch" }}>{t("rs.title")}</h1>
        <p style={{ marginTop: 20, maxWidth: 640 }}>
          {t("rs.lede1")}{" "}
          <span className="mono" style={{ color: "var(--text-2)" }}>{frozen.meta.frozen_tag}</span>{t("rs.lede2")}
        </p>

        {/* regime toggle */}
        <div style={{ display: "flex", gap: 8, marginTop: 40 }}>
          {(["pooled", "s3"] as const).map((r) => (
            <button
              key={r}
              onClick={() => setRegime(r)}
              className="mono"
              style={{
                background: regime === r ? "rgba(111,227,245,0.1)" : "none",
                border: `1px solid ${regime === r ? "rgba(111,227,245,0.35)" : "var(--border-strong)"}`,
                color: regime === r ? "var(--cyan)" : "var(--text-3)",
                borderRadius: 20, padding: "7px 16px", fontSize: 11, letterSpacing: "0.12em", cursor: "pointer",
              }}
            >
              {r === "pooled" ? t("rs.pooled") : t("rs.s3")}
            </button>
          ))}
        </div>

        {/* MAIN COMPARISON */}
        <div style={{ marginTop: 28, border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", background: "var(--surface)", backdropFilter: "var(--blur)", padding: "28px 26px" }}>
          <AuprcBars rows={regime === "s3" ? main.filter((m) => m.s3_mean !== null) : main} metric={regime} title={regime === "pooled" ? t("rs.cmp.pooled") : t("rs.cmp.s3")} />
          <p className="mono" style={{ marginTop: 18, fontSize: 11, color: "var(--text-3)" }}>
            {regime === "s3" ? t("rs.note.s3") : t("rs.note.pooled")}
          </p>
        </div>

        {/* HYPOTHESES */}
        <h2 style={{ marginTop: 90 }}>{t("rs.hyp")}</h2>
        <p style={{ marginTop: 16, maxWidth: 620 }}>{t("rs.hyplede")}</p>
        <div style={{ marginTop: 28, display: "flex", flexDirection: "column", gap: 12 }}>
          {frozen.hypotheses.map((h) => (
            <div key={h.id} style={{ display: "grid", gridTemplateColumns: "auto 1fr auto", gap: 18, alignItems: "center", border: "1px solid var(--border-soft)", borderRadius: "var(--radius)", padding: "16px 20px", background: "var(--surface)" }} className="collapse">
              <div style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 120 }}>
                <span className="mono" style={{ fontSize: 13, color: "var(--text)" }}>{h.id}</span>
                <Badge kind={h.status === "confirmatory" ? "measured" : "exploratory"}>{h.status === "confirmatory" ? t("rs.confirmatory") : t("rs.exploratory")}</Badge>
              </div>
              <div>
                <div style={{ fontSize: 14, color: "var(--text-2)" }} title={h.comparison}>{gloss(h.comparison, lang)}</div>
                <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 4 }} title={h.view}>{gloss(h.view, lang)}</div>
              </div>
              <div style={{ textAlign: "right", display: "flex", flexDirection: "column", gap: 3 }}>
                <span className="mono" style={{ fontSize: 15, color: h.status === "confirmatory" ? "var(--cyan)" : "var(--amber)" }}>Δ {delta(h.delta)}</span>
                <span className="mono" style={{ fontSize: 11, color: "var(--text-3)" }}>
                  95% CI [{delta(h.ci_low)}, {delta(h.ci_high)}]
                </span>
                <span className="mono" style={{ fontSize: 11, color: "var(--text-3)" }}>Holm p = {pValue(h.holm_p)} · dz {h.dz.toFixed(2)}</span>
                <span style={{ fontSize: 11, color: h.status === "confirmatory" ? "var(--text-2)" : "var(--amber)" }} title={h.conclusion}>{gloss(h.conclusion, lang)}</span>
              </div>
            </div>
          ))}
        </div>
        <p className="mono" style={{ marginTop: 14, fontSize: 10.5, color: "var(--text-3)" }}>reports/v2_statistics/final_h1_h5_holm.csv</p>

        {/* EVIDENCE LADDER (non-monotonic) */}
        <h2 style={{ marginTop: 90 }}>{t("rs.ladder")}</h2>
        <p style={{ marginTop: 16, maxWidth: 640 }}>{t("rs.ladderlede")}</p>
        <div style={{ marginTop: 28, border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", background: "var(--surface)", backdropFilter: "var(--blur)", padding: "28px 26px" }}>
          <AuprcBars rows={regime === "s3" ? ladder.filter((m) => m.s3_mean !== null) : ladder} metric={regime} />
        </div>

        {/* CONTROLS SUMMARY */}
        <h2 style={{ marginTop: 90 }}>{t("rs.controls")}</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 20, marginTop: 28 }}>
          <ControlCard
            title={t("rs.cf.title")}
            body={fill(t("rs.cf.body"), {
              a: auprc(model("BIO-GINE M4").pooled_mean),
              b: auprc(model("BIO-GINE M4, shuffled biology (CONTROL F)").pooled_mean),
              c: Math.round(frozen.control_f.changed_fraction * 100),
              d: (frozen.control_f.retained_fraction * 100).toFixed(2),
            })}
            source={frozen.control_f.source}
          />
          <ControlCard
            title={t("rs.ca.title")}
            body={fill(t("rs.ca.body"), { a: auprc(model("Biological-degree-only RF (CONTROL A)").pooled_mean) })}
            source={model("Biological-degree-only RF (CONTROL A)").source}
          />
          <ControlCard
            title={t("rs.ce.title")}
            body={fill(t("rs.ce.body"), { a: frozen.control_e.r2_train.toFixed(3) })}
            source={frozen.control_e.source}
            amber
          />
        </div>

        {/* CALIBRATION */}
        <h2 style={{ marginTop: 90 }}>{t("rs.calib")}</h2>
        <p style={{ marginTop: 16, maxWidth: 640 }}>{t("rs.caliblede")}</p>
        <div style={{ marginTop: 24, overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 520 }}>
            <thead>
              <tr>
                {["rs.col.seed", "rs.col.temp", "rs.col.ece", "rs.col.brier"].map((h) => (
                  <th key={h} className="mono" style={{ textAlign: "left", fontSize: 11, color: "var(--text-3)", fontWeight: 400, padding: "8px 12px", borderBottom: "1px solid var(--border)" }}>{t(h)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {frozen.calibration.map((c) => (
                <tr key={c.seed}>
                  <td className="mono" style={td}>{c.seed}</td>
                  <td className="mono" style={td}>{c.temperature.toFixed(3)}</td>
                  <td className="mono" style={td}>{c.ece_raw.toFixed(3)} → <span style={{ color: "var(--cyan)" }}>{c.ece_scaled.toFixed(3)}</span></td>
                  <td className="mono" style={td}>{c.brier_raw.toFixed(3)} → <span style={{ color: "var(--cyan)" }}>{c.brier_scaled.toFixed(3)}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mono" style={{ marginTop: 12, fontSize: 10.5, color: "var(--text-3)" }}>reports/v2_calibration/m4_temperature_scaling.csv</p>

        {/* headline reproduction */}
        <div style={{ marginTop: 70, borderTop: "1px solid var(--border-soft)", paddingTop: 30, display: "flex", flexWrap: "wrap", gap: 40 }}>
          <div style={{ maxWidth: 480 }}>
            <span className="eyebrow">{t("rs.headline")}</span>
            <p style={{ marginTop: 12 }}>{fill(t("rs.headlinep"), { n: frozen.dataset.n_drugs })}</p>
          </div>
          <div className="mono" style={{ fontSize: 12, color: "var(--text-2)", lineHeight: 1.9 }}>
            <div>M4 pooled &nbsp;{meanSd(model("BIO-GINE M4").pooled_mean, model("BIO-GINE M4").pooled_std)}</div>
            <div>M4 S3 &nbsp;&nbsp;&nbsp;&nbsp;{meanSd(model("BIO-GINE M4").s3_mean!, model("BIO-GINE M4").s3_std!)}</div>
            <div>H-V2-1 Holm p = {pValue(hypothesis("H-V2-1").holm_p)}</div>
          </div>
        </div>
      </div>
    </section>
  );
}

const td: React.CSSProperties = { fontSize: 12.5, color: "var(--text-2)", padding: "9px 12px", borderBottom: "1px solid var(--border-soft)" };

function ControlCard({ title, body, source, amber }: { title: string; body: string; source: string; amber?: boolean }) {
  return (
    <div style={{ border: `1px solid ${amber ? "rgba(255,196,120,0.25)" : "var(--border)"}`, background: amber ? "rgba(255,196,120,0.04)" : "var(--surface)", borderRadius: "var(--radius)", padding: 22 }}>
      <div className="mono" style={{ fontSize: 12, color: amber ? "var(--amber)" : "var(--cyan)", letterSpacing: "0.06em" }}>{title}</div>
      <p style={{ marginTop: 12, fontSize: 13.5 }}>{body}</p>
      <div className="mono" style={{ marginTop: 14, fontSize: 10, color: "var(--text-3)", wordBreak: "break-all" }}>{source}</div>
    </div>
  );
}
