// Typographic building blocks of the PDF report (react-pdf primitives).
//
// Layout rules: tables have a header that repeats on every page they span and
// rows that never split; a section title never sits alone at a page bottom;
// long unbroken strings (URLs, identifiers, JSON) are wrapped explicitly so
// nothing runs past the margin. Every string reaches the page as plain text —
// react-pdf does not interpret markup — and only http(s) URLs become links.
import type { ReactNode } from "react";
import { Link, Text, View, type Styles } from "@react-pdf/renderer";
import { clean, jsonLines, safeUrl, wrapMono } from "./format";
import { monoFont, st, tint, type Col } from "./styles";
import { C, CONTENT_WIDTH, FONT, PAGE, SIZE } from "./theme";

type Style = Styles[string];

export function Eyebrow({ children, color = C.teal }: { children: ReactNode; color?: string }) {
  return <Text style={[st.eyebrow, { color }]}>{children}</Text>;
}

export function SectionTitle({ n, title, lead, breakBefore }: { n: string; title: string; lead?: string; breakBefore?: boolean }) {
  return (
    <View break={breakBefore} minPresenceAhead={90} style={{ marginTop: breakBefore ? 0 : 20, marginBottom: 10 }}>
      <View style={{ flexDirection: "row", alignItems: "flex-end", borderBottomWidth: 0.8, borderBottomColor: C.navy, paddingBottom: 5 }}>
        <Text style={{ fontFamily: FONT.mono, fontSize: 9, color: C.teal, width: 26, paddingBottom: 2 }}>{n}</Text>
        <Text style={{ fontFamily: FONT.serif, fontWeight: 600, fontSize: SIZE.h2, color: C.navy, lineHeight: 1.15, flex: 1 }}>{title}</Text>
      </View>
      {lead ? <Text style={[st.small, { marginTop: 6 }]}>{lead}</Text> : null}
    </View>
  );
}

export function SubTitle({ children, color = C.navy, first }: { children: ReactNode; color?: string; first?: boolean }) {
  return (
    <View minPresenceAhead={50} style={{ marginTop: first ? 2 : 12, marginBottom: 5 }}>
      <Text style={[st.h3, { color, marginBottom: 0 }]}>{children}</Text>
    </View>
  );
}

export function P({ children, style }: { children: ReactNode; style?: Style }) {
  return <Text style={[st.p, style ?? {}]}>{children}</Text>;
}

export function Card({ children, accent, background = C.tint, wrap = false, style }: {
  children: ReactNode; accent?: string; background?: string; wrap?: boolean; style?: Style;
}) {
  return (
    <View wrap={wrap} style={[{
      backgroundColor: background, borderWidth: 0.6, borderColor: C.hair, borderRadius: 3,
      borderLeftWidth: accent ? 2.4 : 0.6, borderLeftColor: accent ?? C.hair, padding: 9, marginBottom: 7,
    }, style ?? {}]}>
      {children}
    </View>
  );
}

export function Chip({ color, children, filled }: { color: string; children: ReactNode; filled?: boolean }) {
  return (
    <View style={{
      borderWidth: 0.6, borderColor: color, borderRadius: 7, paddingHorizontal: 5, paddingVertical: 1.2,
      backgroundColor: filled ? tint(color, 0.12) : C.white, alignSelf: "flex-start", marginRight: 4,
    }}>
      <Text style={{ fontFamily: FONT.mono, fontSize: 6.2, color, lineHeight: 1.2 }}>{children}</Text>
    </View>
  );
}

export function Dot({ color, size = 5 }: { color: string; size?: number }) {
  return <View style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: color, marginTop: 3.2, marginRight: 6 }} />;
}

export function Bullets({ items, color = C.teal, size = SIZE.body }: { items: ReactNode[]; color?: string; size?: number }) {
  return (
    <View>
      {items.map((it, i) => (
        <View key={i} wrap={false} style={{ flexDirection: "row", marginBottom: 3.5 }}>
          <Text style={{ width: 10, color, fontSize: size }}>•</Text>
          <Text style={{ flex: 1, fontSize: size, color: C.slate, lineHeight: 1.45 }}>{it}</Text>
        </View>
      ))}
    </View>
  );
}

/** Two-column key / value list. */
export function KV({ rows, keyWidth = 150, size = SIZE.small }: { rows: [string, ReactNode][]; keyWidth?: number; size?: number }) {
  return (
    <View>
      {rows.map(([k, v], i) => (
        <View key={i} wrap={false} style={{ flexDirection: "row", paddingVertical: 2.6, borderBottomWidth: 0.5, borderBottomColor: C.hair }}>
          <Text style={{ width: keyWidth, fontSize: size, color: C.muted, paddingRight: 8 }}>{k}</Text>
          <View style={{ flex: 1 }}>{typeof v === "string" ? <Text style={{ fontSize: size, color: C.ink }}>{v}</Text> : v}</View>
        </View>
      ))}
    </View>
  );
}


/** Monospace text wrapped to a known width (URLs, identifiers). */
export function MonoLines({ text, width, size = SIZE.micro, color = C.slate2 }: { text: string; width: number; size?: number; color?: string }) {
  return (
    <View>
      {wrapMono(text, width, size).map((line, i) => (
        <Text key={i} style={{ fontFamily: monoFont(line), fontSize: size, color, lineHeight: 1.35 }}>{line || " "}</Text>
      ))}
    </View>
  );
}

/** JSON set in mono, indented with padding (leading spaces would be dropped)
 *  and wrapped only between tokens, so the extracted text parses as JSON. */
export function JsonBlock({ value, width, size = 6 }: { value: unknown; width: number; size?: number }) {
  const step = 2 * 0.6 * size;
  return (
    <View>
      {jsonLines(value, Math.floor(width / (0.6 * size))).map((l, i) => (
        <Text key={i} style={{ fontFamily: monoFont(l.text), fontSize: size, color: C.ink, lineHeight: 1.35, paddingLeft: l.indent * step }}>{l.text}</Text>
      ))}
    </View>
  );
}

/** A URL: clickable when it is http(s), always printed in full. */
export function Url({ url, width, size = SIZE.micro }: { url: string | null | undefined; width: number; size?: number }) {
  const safe = safeUrl(url);
  if (!url) return null;
  if (!safe) return <MonoLines text={clean(url)} width={width} size={size} />;
  return (
    <Link src={safe} style={{ textDecoration: "none" }}>
      <MonoLines text={safe} width={width} size={size} color={C.navy3} />
    </Link>
  );
}

/** Table whose header repeats on every page it spans; rows never split. */
export function Table({ cols, rows, size = 7.6, zebra = true }: { cols: Col[]; rows: ReactNode[][]; size?: number; zebra?: boolean }) {
  const total = cols.reduce((s, c) => s + c.width, 0);
  const w = (c: Col) => (c.width / total) * CONTENT_WIDTH;
  const cell = (c: Col, node: ReactNode, i: number, header: boolean) => (
    <View key={i} style={{ width: w(c), paddingHorizontal: 4, paddingVertical: header ? 3.5 : 3.2 }}>
      {typeof node === "string" || typeof node === "number"
        ? <Text style={{ fontSize: header ? 6.4 : size, color: header ? C.white : C.ink, textAlign: c.align ?? "left", fontFamily: header ? FONT.mono : FONT.sans, lineHeight: 1.35 }}>{String(node)}</Text>
        : node}
    </View>
  );
  return (
    <View style={{ marginBottom: 8, borderWidth: 0.5, borderColor: C.rule }}>
      <View fixed style={{ flexDirection: "row", backgroundColor: C.navy }}>
        {cols.map((c, i) => cell(c, c.title.toUpperCase(), i, true))}
      </View>
      {rows.map((r, ri) => (
        <View key={ri} wrap={false} style={{ flexDirection: "row", backgroundColor: zebra && ri % 2 ? C.tint : C.white, borderTopWidth: ri ? 0.5 : 0, borderTopColor: C.hair }}>
          {cols.map((c, i) => cell(c, r[i] ?? "", i, false))}
        </View>
      ))}
    </View>
  );
}

export function RunningHeader({ left, right }: { left: string; right: string }) {
  return (
    <View fixed style={{ position: "absolute", top: 26, left: PAGE.marginX, right: PAGE.marginX, flexDirection: "row", justifyContent: "space-between", alignItems: "flex-end", borderBottomWidth: 0.6, borderBottomColor: C.tealLine, paddingBottom: 4 }}>
      <Text style={[st.eyebrow, { color: C.navy }]}>{left}</Text>
      <Text style={{ fontSize: 7.2, color: C.slate2, maxWidth: 260, textAlign: "right" }}>{right}</Text>
    </View>
  );
}

export function RunningFooter({ left, center, pageText }: { left: string; center: string; pageText: (n: number, t: number) => string }) {
  return (
    <View fixed style={{ position: "absolute", bottom: 24, left: PAGE.marginX, right: PAGE.marginX, flexDirection: "row", justifyContent: "space-between", borderTopWidth: 0.5, borderTopColor: C.rule, paddingTop: 5 }}>
      <Text style={{ fontSize: 6.6, color: C.muted, width: 190 }}>{left}</Text>
      <Text style={{ fontFamily: FONT.mono, fontSize: 6.4, color: C.muted, textAlign: "center" }}>{center}</Text>
      <Text style={{ fontSize: 6.6, color: C.muted, width: 90, textAlign: "right" }} render={({ pageNumber, totalPages }) => pageText(pageNumber, totalPages)} />
    </View>
  );
}
