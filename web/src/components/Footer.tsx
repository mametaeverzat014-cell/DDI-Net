// Footer on every view. The disclaimer is not optional — it appears site-wide,
// exactly as the design specifies, in whichever language the reader has chosen.
import type { View } from "../App";
import { frozen } from "../data/frozen";
import { useI18n } from "../i18n";

export function Footer({ setView }: { setView: (v: View) => void }) {
  const { t } = useI18n();
  return (
    <footer style={{ borderTop: "1px solid var(--border-soft)", padding: "40px 0 60px", position: "relative", zIndex: 1 }}>
      <div className="wrap" style={{ display: "flex", flexWrap: "wrap", gap: 24, justifyContent: "space-between", alignItems: "baseline" }}>
        <div style={{ maxWidth: 640 }}>
          <p style={{ fontSize: 13, color: "var(--text-2)" }}>
            {t("footer.disclaimer")}{" "}
            <strong style={{ color: "var(--text)" }}>{t("footer.notvalidated")}</strong>
            {t("footer.notdevice")}
          </p>
          <button onClick={() => setView("limitations")} className="mono" style={{ marginTop: 12, background: "none", border: "none", color: "var(--cyan)", cursor: "pointer", fontSize: 12, padding: 0 }}>
            {t("footer.readlimits")}
          </button>
        </div>
        <div className="mono" style={{ fontSize: 10.5, color: "var(--text-3)", textAlign: "right", lineHeight: 1.7 }}>
          <div>{t("footer.tag")}: {frozen.meta.frozen_tag}</div>
          <div>{t("footer.commit")}: {frozen.meta.frozen_commit.slice(0, 12)}</div>
        </div>
      </div>
    </footer>
  );
}
