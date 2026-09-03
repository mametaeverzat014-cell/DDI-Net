import { useState } from "react";
import { AuprcBars } from "../components/AuprcBars";
import { Badge } from "../components/Badge";
import { frozen, hypothesis, model } from "../data/frozen";
import { auprc, delta, meanSd, pValue } from "../lib/format";

export function Research() {
  const [regime, setRegime] = useState<"pooled" | "s3">("pooled");
  const main = frozen.models;
  const ladder = frozen.ladder;

  return (
    <section className="section" style={{ paddingTop: "18vh" }}>
      <div className="wrap">
        <span className="eyebrow">Results — read from the frozen V2 state</span>
        <h1 style={{ marginTop: 18, maxInlineSize: "16ch" }}>The evidence, in full.</h1>
        <p style={{ marginTop: 20, maxWidth: 640 }}>
          Every number below is generated from the frozen artifacts at tag{" "}
          <span className="mono" style={{ color: "var(--text-2)" }}>{frozen.meta.frozen_tag}</span>. Confidence intervals,
          Holm-adjusted p-values and effect sizes are recomputed from the per-seed values, not
          retyped. The primary configuration was frozen before any test evaluation.
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
              {r === "pooled" ? "POOLED DRUG-HOLDOUT (S2+S3)" : "S3 · BOTH DRUGS HELD OUT"}
            </button>
          ))}
        </div>

        {/* MAIN COMPARISON */}
        <div style={{ marginTop: 28, border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", background: "var(--surface)", backdropFilter: "var(--blur)", padding: "28px 26px" }}>
          <AuprcBars rows={regime === "s3" ? main.filter((m) => m.s3_mean !== null) : main} metric={regime} title={regime === "pooled" ? "Model comparison — pooled drug-holdout AUPRC" : "Model comparison — S3 AUPRC (both drugs held out)"} />
          <p className="mono" style={{ marginTop: 18, fontSize: 11, color: "var(--text-3)" }}>
            {regime === "s3"
              ? "S3 is the hardest condition: neither drug has any interaction adjacency in the training graph. The Dual model, which relies on that adjacency, degrades most here."
              : "Colour: cyan = full model · blue = baselines · violet = shortcut controls. Axis begins at 0.5 and is never truncated."}
          </p>
        </div>

        {/* HYPOTHESES */}
        <h2 style={{ marginTop: 90 }}>Preregistered hypotheses</h2>
        <p style={{ marginTop: 16, maxWidth: 620 }}>
          Five hypotheses, fixed before any run. Holm–Bonferroni correction spans all five,
          including the exploratory H-V2-5 — which makes the correction stricter for the four
          confirmatory ones.
        </p>
        <div style={{ marginTop: 28, display: "flex", flexDirection: "column", gap: 12 }}>
          {frozen.hypotheses.map((h) => (
            <div key={h.id} style={{ display: "grid", gridTemplateColumns: "auto 1fr auto", gap: 18, alignItems: "center", border: "1px solid var(--border-soft)", borderRadius: "var(--radius)", padding: "16px 20px", background: "var(--surface)" }} className="collapse">
              <div style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 120 }}>
                <span className="mono" style={{ fontSize: 13, color: "var(--text)" }}>{h.id}</span>
                <Badge kind={h.status === "confirmatory" ? "measured" : "exploratory"}>{h.status}</Badge>
              </div>
              <div>
                <div style={{ fontSize: 14, color: "var(--text-2)" }}>{h.comparison}</div>
                <div className="mono" style={{ fontSize: 11, color: "var(--text-3)", marginTop: 4 }}>{h.view}</div>
              </div>
              <div style={{ textAlign: "right", display: "flex", flexDirection: "column", gap: 3 }}>
                <span className="mono" style={{ fontSize: 15, color: h.status === "confirmatory" ? "var(--cyan)" : "var(--amber)" }}>Δ {delta(h.delta)}</span>
                <span className="mono" style={{ fontSize: 11, color: "var(--text-3)" }}>
                  95% CI [{delta(h.ci_low)}, {delta(h.ci_high)}]
                </span>
                <span className="mono" style={{ fontSize: 11, color: "var(--text-3)" }}>Holm p = {pValue(h.holm_p)} · dz {h.dz.toFixed(2)}</span>
                <span style={{ fontSize: 11, color: h.status === "confirmatory" ? "var(--text-2)" : "var(--amber)" }}>{h.conclusion}</span>
              </div>
            </div>
          ))}
        </div>
        <p className="mono" style={{ marginTop: 14, fontSize: 10.5, color: "var(--text-3)" }}>reports/v2_statistics/final_h1_h5_holm.csv</p>

        {/* EVIDENCE LADDER (non-monotonic) */}
        <h2 style={{ marginTop: 90 }}>Evidence ladder — non-monotonic</h2>
        <p style={{ marginTop: 16, maxWidth: 640 }}>
          Adding biological evidence one source at a time. Every biological variant beats the
          no-biology baseline (M0), but the ladder <strong>does not rise monotonically</strong>:
          M2 is the strongest variant, and the SUM control beats the primary MEAN model. M4 was
          fixed as primary on validation before the test set was opened — it is the preregistered
          model, not the best test performer.
        </p>
        <div style={{ marginTop: 28, border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", background: "var(--surface)", backdropFilter: "var(--blur)", padding: "28px 26px" }}>
          <AuprcBars rows={regime === "s3" ? ladder.filter((m) => m.s3_mean !== null) : ladder} metric={regime} />
        </div>

        {/* CONTROLS SUMMARY */}
        <h2 style={{ marginTop: 90 }}>Shortcut controls</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 20, marginTop: 28 }}>
          <ControlCard
            title="CONTROL F — identity shuffle"
            body={`Rewiring which proteins each drug is annotated against, at fixed degree, drops AUPRC from ${auprc(model("BIO-GINE M4").pooled_mean)} to ${auprc(model("BIO-GINE M4, shuffled biology (CONTROL F)").pooled_mean)}. ${Math.round(frozen.control_f.changed_fraction * 100)}% of edges changed; ${(frozen.control_f.retained_fraction * 100).toFixed(2)}% retained.`}
            source={frozen.control_f.source}
          />
          <ControlCard
            title="CONTROL A — count-only baseline"
            body={`A random forest on annotation counts alone reaches ${auprc(model("Biological-degree-only RF (CONTROL A)").pooled_mean)} — above chance, so popularity is genuinely predictive, but far below the full model.`}
            source={model("Biological-degree-only RF (CONTROL A)").source}
          />
          <ControlCard
            title="CONTROL E — not identifiable"
            body={`The planned probe predicts training-DDI degree from the embedding. Held-out R² is undefined: every held-out drug has degree zero, so target variance is zero. Train R² = ${frozen.control_e.r2_train.toFixed(3)}, reported descriptively.`}
            source={frozen.control_e.source}
            amber
          />
        </div>

        {/* CALIBRATION */}
        <h2 style={{ marginTop: 90 }}>Calibration</h2>
        <p style={{ marginTop: 16, maxWidth: 640 }}>
          One temperature per seed, fitted only on validation predictions and applied to the
          frozen test predictions. Expected calibration error falls by roughly a factor of three;
          ranking is unchanged, because temperature scaling is monotonic.
        </p>
        <div style={{ marginTop: 24, overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 520 }}>
            <thead>
              <tr>
                {["seed", "temperature", "ECE raw → scaled", "Brier raw → scaled"].map((h) => (
                  <th key={h} className="mono" style={{ textAlign: "left", fontSize: 11, color: "var(--text-3)", fontWeight: 400, padding: "8px 12px", borderBottom: "1px solid var(--border)" }}>{h}</th>
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
            <span className="eyebrow">Headline</span>
            <p style={{ marginTop: 12 }}>
              Biological identity carried predictive information that transferred to unseen drugs
              and was not explained by annotation quantity — under one frozen drug partition, on a
              curated {frozen.dataset.n_drugs}-drug subset. Not clinically validated.
            </p>
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
