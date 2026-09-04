import type { View } from "../App";
import { HomeCanvas } from "../canvas/HomeCanvas";
import { Badge } from "../components/Badge";
import { Metric } from "../components/Metric";
import { frozen, model } from "../data/frozen";
import { auprc, count, delta, meanSd, pct } from "../lib/format";
import { useI18n } from "../i18n";

export function Home({ setView }: { setView: (v: View) => void }) {
  const { t, lang } = useI18n();
  const m4 = model("BIO-GINE M4");
  const m0 = model("Aligned molecular GINE (M0)");
  const shuffled = model("BIO-GINE M4, shuffled biology (CONTROL F)");
  const d = frozen.dataset;
  const leak = frozen.leakage.both_endpoints_seen;

  return (
    <>
      <HomeCanvas />

      {/* HERO */}
      <section style={{ minHeight: "100vh", display: "flex", flexDirection: "column", justifyContent: "center", position: "relative", zIndex: 1 }}>
        <div className="wrap" style={{ pointerEvents: "none" }}>
          <span className="eyebrow">{t("home.eyebrow")}</span>
          <h1 style={{ marginTop: 22, maxInlineSize: "16ch" }}>
            {t("home.title1")}<br />{t("home.title2")}
          </h1>
          <p style={{ marginTop: 26, maxWidth: 560 }}>
            {t("home.lede")}
          </p>
          <div style={{ marginTop: 34, display: "flex", gap: 14, flexWrap: "wrap", pointerEvents: "auto" }}>
            <button onClick={() => setView("analyze")} style={btnFilled}>{t("home.cta.pair")}</button>
            <button onClick={() => setView("model")} style={btnOutline}>{t("home.cta.model")}</button>
          </div>
        </div>
        <div className="wrap" style={{ position: "absolute", bottom: 34, left: 0, right: 0, display: "flex", justifyContent: "space-between", alignItems: "baseline", pointerEvents: "none" }}>
          <span className="mono" style={{ fontSize: 11, color: "var(--text-3)" }}>
            TDC DrugBank · {count(d.n_drugs, lang)} {lang === "ru" ? "препаратов" : "drugs"} · {count(d.n_pairs, lang)} {lang === "ru" ? "пар" : "pairs"}
          </span>
          <span className="mono" style={{ fontSize: 11, color: "var(--text-3)" }}>{t("home.rail.research")}</span>
        </div>
      </section>

      {/* 01 THE PROBLEM */}
      <section className="section">
        <div className="wrap">
          <span className="eyebrow">{t("home.s1.eyebrow")}</span>
          <h2 className="reveal" style={{ marginTop: 18, maxWidth: "14ch" }}>{t("home.s1.title")}</h2>
          <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 48, marginTop: 40, alignItems: "start" }} className="collapse">
            <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
              <p>{t("home.s1.p1")}</p>
              <p>{t("home.s1.p2")}</p>
              <span className="hand" style={{ fontSize: 24, color: "var(--amber)", opacity: 0.9 }}>
                {t("home.s1.hand")}
              </span>
            </div>
            <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius)", background: "var(--surface)", backdropFilter: "var(--blur)", padding: 22 }}>
              <span className="eyebrow" style={{ display: "block", marginBottom: 14 }}>{t("home.s1.tablehead")}</span>
              {([["random_pair", "home.s1.random"], ["drug", "home.s1.drug"], ["scaffold", "home.s1.scaffold"]] as const).map(([k, labelKey]) => (
                <div key={k} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 0", borderTop: "1px solid var(--border-soft)" }}>
                  <span style={{ fontSize: 14, color: "var(--text-2)" }}>{t(labelKey)}</span>
                  <span className="mono" style={{ fontSize: 16, color: k === "random_pair" ? "var(--amber)" : "var(--cyan)" }}>
                    {pct(leak[k] * 100, 2)}
                  </span>
                </div>
              ))}
              <span className="mono" style={{ display: "block", marginTop: 14, fontSize: 10, color: "var(--text-3)" }}>{frozen.leakage.source}</span>
            </div>
          </div>
        </div>
      </section>

      {/* 02 RESEARCH QUESTION + PRIMARY RESULT */}
      <section className="section">
        <div className="wrap">
          <span className="eyebrow">{t("home.s2.eyebrow")}</span>
          <h2 className="reveal" style={{ marginTop: 18, maxWidth: "18ch" }}>{t("home.s2.title")}</h2>
          <p style={{ marginTop: 22, maxWidth: 620 }}>{t("home.s2.p")}</p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: 28, marginTop: 40 }}>
            <Metric label={t("home.s2.m4")} value={meanSd(m4.pooled_mean, m4.pooled_std)} accent="var(--cyan)" source={m4.source} />
            <Metric label={t("home.s2.m0")} value={meanSd(m0.pooled_mean, m0.pooled_std)} accent="var(--blue)" source={m0.source} />
            <Metric label={t("home.s2.delta")} value={delta(m4.pooled_mean - m0.pooled_mean)} sub={t("home.s2.deltasub")} accent="var(--text)" source="reports/v2_statistics/final_h1_h5_holm.csv" />
          </div>
          <p className="mono" style={{ marginTop: 26, fontSize: 12, color: "var(--text-3)", maxWidth: 640 }}>
            {t("home.s2.note")}
          </p>
        </div>
      </section>

      {/* 03 WHY CONTROL F MATTERS */}
      <section className="section">
        <div className="wrap">
          <span className="eyebrow">{t("home.s3.eyebrow")}</span>
          <h2 className="reveal" style={{ marginTop: 18, maxWidth: "16ch" }}>{t("home.s3.title")}</h2>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 48, marginTop: 40, alignItems: "center" }} className="collapse">
            <p>{t("home.s3.p")}</p>
            <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
              <Metric label={t("home.s3.true")} value={auprc(m4.pooled_mean)} accent="var(--cyan)" source={m4.source} size={40} />
              <Metric label={t("home.s3.shuf")} value={auprc(shuffled.pooled_mean)} accent="var(--violet)" source={shuffled.source} size={40} />
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span className="mono" style={{ fontSize: 20, color: "var(--text)" }}>{delta(m4.pooled_mean - shuffled.pooled_mean)}</span>
                <span style={{ fontSize: 13, color: "var(--text-2)" }}>{t("home.s3.lost")}</span>
              </div>
              <p style={{ fontSize: 13, color: "var(--text-3)" }}>{t("home.s3.caveat")}</p>
            </div>
          </div>
        </div>
      </section>

      {/* HONEST FINDINGS STRIP */}
      <section className="section" style={{ paddingTop: 0 }}>
        <div className="wrap">
          <div style={{ border: "1px solid rgba(255,196,120,0.25)", background: "rgba(255,196,120,0.05)", borderRadius: "var(--radius)", padding: 24 }}>
            <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 14 }}>
              <Badge kind="exploratory">{t("home.honest.badge")}</Badge>
              <span style={{ fontSize: 13, color: "var(--text-2)" }}>{t("home.honest.lede")}</span>
            </div>
            <ul style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 8 }}>
              <li style={{ fontSize: 14, color: "var(--text-2)" }}>
                {t("home.honest.1a")} <strong>{t("home.honest.1b")}</strong>: M2 ({auprc(model("M2").pooled_mean)}) {t("home.honest.1c")} SUM ({auprc(model("M4 SUM (CONTROL C)").pooled_mean)}) {t("home.honest.1d")} ({auprc(m4.pooled_mean)}).
              </li>
              <li style={{ fontSize: 14, color: "var(--text-2)" }}>{t("home.honest.2")}</li>
              <li style={{ fontSize: 14, color: "var(--text-2)" }}>{t("home.honest.3")}</li>
              <li style={{ fontSize: 14, color: "var(--text-2)" }}>{t("home.honest.4")}</li>
            </ul>
          </div>
          <div style={{ marginTop: 46, display: "flex", gap: 14, flexWrap: "wrap" }}>
            <button onClick={() => setView("research")} style={btnFilled}>{t("home.cta.results")}</button>
            <button onClick={() => setView("model")} style={btnOutline}>{t("home.cta.model")}</button>
          </div>
        </div>
      </section>
    </>
  );
}

const btnFilled: React.CSSProperties = {
  background: "var(--cyan)", color: "#06101f", border: "none", borderRadius: 24,
  padding: "12px 22px", fontSize: 14, fontWeight: 600, cursor: "pointer", fontFamily: "var(--font-ui)",
};
const btnOutline: React.CSSProperties = {
  background: "none", color: "var(--text)", border: "1px solid var(--border-strong)", borderRadius: 24,
  padding: "12px 22px", fontSize: 14, fontWeight: 500, cursor: "pointer", fontFamily: "var(--font-ui)",
};
