// Footer on every view. The disclaimer is not optional — it appears site-wide,
// exactly as the design specifies.
import { frozen } from "../data/frozen";

export function Footer() {
  return (
    <footer style={{ borderTop: "1px solid var(--border-soft)", padding: "40px 0 60px", position: "relative", zIndex: 1 }}>
      <div className="wrap" style={{ display: "flex", flexWrap: "wrap", gap: 24, justifyContent: "space-between", alignItems: "baseline" }}>
        <div style={{ maxWidth: 640 }}>
          <p style={{ fontSize: 13, color: "var(--text-2)" }}>
            Regeneron ISEF · Computational Biology &amp; Bioinformatics. This system is a
            computational research prototype and is <strong style={{ color: "var(--text)" }}>not
            validated for clinical decision-making</strong>. It is not a medical device and not a
            clinical decision support system.
          </p>
        </div>
        <div className="mono" style={{ fontSize: 10.5, color: "var(--text-3)", textAlign: "right", lineHeight: 1.7 }}>
          <div>frozen tag: {frozen.meta.frozen_tag}</div>
          <div>commit: {frozen.meta.frozen_commit.slice(0, 12)}</div>
        </div>
      </div>
    </footer>
  );
}
