// Status badges. The design uses colour as a semantic category: amber means
// "not measured" (demo / specified / pending), cyan means implemented/measured.
// A badge is never decorative — it tells the reader whether to trust a number.
import type { ReactNode } from "react";

type Kind = "demo" | "pending" | "specified" | "implemented" | "measured" | "quarantined" | "exploratory";

const STYLE: Record<Kind, { fg: string; bd: string; bg: string }> = {
  demo: { fg: "var(--amber)", bd: "rgba(255,196,120,0.4)", bg: "rgba(255,196,120,0.08)" },
  pending: { fg: "var(--amber)", bd: "rgba(255,196,120,0.4)", bg: "rgba(255,196,120,0.08)" },
  specified: { fg: "var(--amber)", bd: "rgba(255,196,120,0.4)", bg: "rgba(255,196,120,0.08)" },
  exploratory: { fg: "var(--amber)", bd: "rgba(255,196,120,0.4)", bg: "rgba(255,196,120,0.08)" },
  implemented: { fg: "var(--cyan)", bd: "rgba(111,227,245,0.4)", bg: "rgba(111,227,245,0.07)" },
  measured: { fg: "var(--cyan)", bd: "rgba(111,227,245,0.4)", bg: "rgba(111,227,245,0.07)" },
  quarantined: { fg: "var(--red)", bd: "rgba(255,158,158,0.45)", bg: "rgba(255,158,158,0.08)" },
};

export function Badge({ kind, children }: { kind: Kind; children?: ReactNode }) {
  const s = STYLE[kind];
  return (
    <span
      className="mono"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontSize: 10,
        textTransform: "uppercase",
        letterSpacing: "0.14em",
        color: s.fg,
        border: `1px solid ${s.bd}`,
        background: s.bg,
        borderRadius: 5,
        padding: "3px 8px",
        whiteSpace: "nowrap",
      }}
    >
      {children ?? kind}
    </span>
  );
}
