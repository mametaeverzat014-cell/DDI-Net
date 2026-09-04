// The research model score, or an honest statement of why there isn't one.
//
// PHASE 8 WORDING. Never SAFE / UNSAFE / DO NOT COMBINE / patient risk / "%
// dangerous". The frozen dataset holds documented positive interactions and
// sampled UNLABELLED pairs — not verified clinical outcomes — so the score is a
// research model score and nothing stronger.
//
// The dataset record sits in its own block, visually separated, because it is
// retrospective metadata that the model never saw. Putting it beside the score
// without that separation would invite reading it as the model's evidence.
import { useI18n } from "../i18n";
import type { AnalyzeState } from "../data/analyze";
import { Badge } from "./Badge";

export function PredictionPanel({ state }: { state: AnalyzeState }) {
  const { t, lang } = useI18n();

  if (state.kind === "ok") return <Scored data={state.data} />;

  const message =
    state.kind === "unconfigured" ? t("an.state.unconfigured")
    : state.kind === "model_unavailable" ? t("an.state.unavailable")
    : state.kind === "error" ? `${t("an.state.error")} ${state.message}`
    : null;

  return (
    <div style={amberBox}>
      <span className="eyebrow" style={{ color: "var(--amber)" }}>{t("an.score.title")}</span>
      <div className="mono" style={{ fontSize: 40, color: "var(--amber)", marginTop: 12, letterSpacing: "-0.02em" }}>
        {state.kind === "loading" ? <span style={{ fontSize: 16 }}>{t("an.score.loading")}</span> : "—"}
      </div>
      {message && <p style={{ fontSize: 13, marginTop: 8, color: "var(--text-2)" }}>{message}</p>}
      <p style={{ fontSize: 12, color: "var(--text-3)", marginTop: 16 }}>
        {lang === "ru" ? t("an.disclaimer") : t("an.disclaimer")}
      </p>
    </div>
  );
}

function Scored({ data }: { data: NonNullable<Extract<AnalyzeState, { kind: "ok" }>>["data"] }) {
  const { t, lang } = useI18n();
  const cal = data.calibrated_model_score;
  const documented = data.dataset_record.documented_in_frozen_dataset;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {/* score */}
      <div style={{ border: "1px solid rgba(111,227,245,0.3)", background: "rgba(111,227,245,0.05)", borderRadius: "var(--radius-lg)", padding: 22 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
          <span className="eyebrow" style={{ color: "var(--cyan)" }}>{t("an.score.title")}</span>
          <Badge kind="measured">{data.status.replace(/_/g, " ")}</Badge>
        </div>
        <div className="mono" style={{ fontSize: 46, color: "var(--cyan)", marginTop: 10, letterSpacing: "-0.02em", lineHeight: 1 }}>
          {cal.toFixed(3)}
        </div>
        <div className="eyebrow" style={{ marginTop: 6 }}>{t("an.score.calibrated")}</div>

        <div className="mono" style={{ fontSize: 11.5, color: "var(--text-3)", marginTop: 14, lineHeight: 1.9 }}>
          <div>{t("an.score.raw")} &nbsp;{data.raw_model_score.toFixed(6)}</div>
          <div>model &nbsp;&nbsp;{data.model} · seed 0</div>
          <div>T &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{data.provenance.temperature.toFixed(6)}</div>
        </div>

        <p style={{ fontSize: 12.5, color: "var(--text-2)", marginTop: 14 }}>{t("an.score.what")}</p>
        <p style={{ fontSize: 11.5, color: "var(--text-3)", marginTop: 10 }}>{t("an.score.ceiling")}</p>
      </div>

      {/* dataset record — deliberately its own block, not part of the score */}
      <div style={{ border: "1px dashed var(--border-strong)", borderRadius: "var(--radius)", padding: 18, background: "rgba(255,255,255,0.015)" }}>
        <span className="eyebrow">{t("an.record.title")}</span>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10 }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: documented ? "var(--violet)" : "var(--text-3)" }} />
          <span style={{ fontSize: 13.5, color: "var(--text-2)" }}>
            {documented ? t("an.record.yes") : t("an.record.no")}
          </span>
        </div>
        <p style={{ fontSize: 11.5, color: "var(--text-3)", marginTop: 10, lineHeight: 1.7 }}>{t("an.record.note")}</p>
      </div>

      {/* provenance */}
      <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius)", padding: 18, background: "var(--surface)" }}>
        <span className="eyebrow">{t("an.provenance")}</span>
        <div className="mono" style={{ fontSize: 10.5, color: "var(--text-3)", marginTop: 10, lineHeight: 1.9, wordBreak: "break-all" }}>
          <div>tag &nbsp;&nbsp;&nbsp;&nbsp;{data.provenance.frozen_tag}</div>
          <div>commit &nbsp;{data.provenance.frozen_commit.slice(0, 12)}</div>
          <div>ckpt &nbsp;&nbsp;&nbsp;{data.checkpoint}</div>
          <div>sha256 &nbsp;{data.provenance.checkpoint_sha256.slice(0, 24)}…</div>
          <div>calib &nbsp;&nbsp;{data.provenance.calibration_source}</div>
          <div>{t("an.parity")} &nbsp;&lt; {data.provenance.parity_tolerance_prob.toExponential(0)}</div>
        </div>
      </div>

      <p style={{ fontSize: 12, color: "var(--amber)", lineHeight: 1.7 }}>
        {lang === "ru" ? data.disclaimer_ru : data.disclaimer_en}
      </p>
    </div>
  );
}

const amberBox: React.CSSProperties = {
  border: "1px solid rgba(255,196,120,0.3)",
  background: "rgba(255,196,120,0.05)",
  borderRadius: "var(--radius-lg)",
  padding: 22,
};
