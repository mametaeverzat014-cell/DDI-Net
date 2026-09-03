// A measured number with its provenance. The design's rule: every measured
// value carries its source file path in mono beneath it. This component makes
// that structural — you cannot render a Metric without giving it a source.
import type { ReactNode } from "react";

export function Metric({
  value,
  label,
  source,
  accent = "var(--text)",
  size = 34,
  sub,
}: {
  value: ReactNode;
  label?: ReactNode;
  source: string;
  accent?: string;
  size?: number;
  sub?: ReactNode;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {label && <span className="eyebrow">{label}</span>}
      <span
        className="mono"
        style={{ fontSize: size, fontWeight: 500, color: accent, letterSpacing: "-0.02em", lineHeight: 1.05 }}
      >
        {value}
      </span>
      {sub && <span style={{ fontSize: 13, color: "var(--text-2)" }}>{sub}</span>}
      <span className="mono" style={{ fontSize: 10.5, color: "var(--text-3)", wordBreak: "break-all" }}>
        {source}
      </span>
    </div>
  );
}
