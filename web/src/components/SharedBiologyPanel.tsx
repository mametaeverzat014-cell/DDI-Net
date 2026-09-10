// What two drugs have in common in the body, written for someone who does not
// know what an enzyme is.
//
// Three layers, top to bottom: a heading with no jargon, an explanation in
// everyday words, then the gene symbols small underneath for a pharmacist. The
// diagram is two named boxes converging on one — no molecular structures,
// which look scientific and tell a lay reader nothing.
import { useI18n, pick } from "../i18n";
import { RELATION_ORDER, type AnalyzeResponse, type Relation } from "../data/analyze";
import {
  CAVEAT, EMPTY_BODY, EMPTY_TITLE, FACTS_NOT_PREDICTION, HEADING, RELATION_COPY,
} from "./sharedBiologyContent";

export function SharedBiologyPanel({ data, nameA, nameB }: {
  data: AnalyzeResponse; nameA: string; nameB: string;
}) {
  const { lang } = useI18n();
  const bio = data.shared_biology;
  // An API older than this block sends no shared_biology at all. Render
  // nothing rather than throwing: the score and the rest of the page still
  // work, and the block appears by itself once the backend catches up.
  if (!bio) return null;
  const present = RELATION_ORDER.filter((r) => bio[r]?.length);

  return (
    <section style={{ marginTop: 28 }}>
      <h2 style={{ fontSize: 22, marginBottom: 6 }}>{pick(HEADING, lang)}</h2>
      <p className="mono" style={{ fontSize: 11.5, color: "var(--text-3)", marginBottom: 18 }}>
        {pick(FACTS_NOT_PREDICTION, lang)}
      </p>

      {present.length === 0 ? (
        <Empty />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {present.map((r) => (
            <RelationCard key={r} relation={r} data={data} nameA={nameA} nameB={nameB} />
          ))}
          <p style={{ fontSize: 12.5, color: "var(--text-3)", lineHeight: 1.7, maxWidth: 700 }}>
            {pick(CAVEAT, lang)}
          </p>
        </div>
      )}
    </section>
  );
}

function RelationCard({ relation, data, nameA, nameB }: {
  relation: Relation; data: AnalyzeResponse; nameA: string; nameB: string;
}) {
  const { lang } = useI18n();
  const copy = RELATION_COPY[relation];
  const proteins = data.shared_biology?.[relation] ?? [];
  if (proteins.length === 0) return null;
  // No "headline" protein. Picking one would mean ranking them, and the data
  // carries no basis for that: sorting alphabetically once put CYP1A2 in front
  // of CYP2C9 for warfarin + phenytoin, presenting an incidental member as the
  // important one. When several are shared, the box states how many and the
  // full list sits below; a single shared protein is named directly.
  const single = proteins.length === 1 ? proteins[0] : null;

  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", background: "var(--surface)", padding: 22 }}>
      <h3 style={{ fontSize: 17, marginBottom: 8 }}>{pick(copy.title, lang)}</h3>
      <p style={{ fontSize: 14, color: "var(--text-2)", maxWidth: 620, lineHeight: 1.65 }}>
        {pick(copy.body, lang)}
      </p>

      {/* two drugs converging on one protein — no chemistry */}
      <div
        role="img"
        aria-label={`${nameA} + ${nameB} → ${proteins.map((p) => p.gene).join(", ")}`}
        style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 18, flexWrap: "wrap" }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <Box>{nameA}</Box>
          <Box>{nameB}</Box>
        </div>
        <span aria-hidden style={{ color: "var(--text-3)", fontSize: 20 }}>→</span>
        <div style={{ border: "1px solid var(--cyan)", background: "rgba(111,227,245,0.08)", borderRadius: 8, padding: "10px 16px" }}>
          {single ? (
            <div className="mono" style={{ fontSize: 15, color: "var(--cyan)" }}>{single.gene}</div>
          ) : (
            <div style={{ fontSize: 15, color: "var(--cyan)" }}>
              {proteins.length} {plural(proteins.length, copy.node, lang)}
            </div>
          )}
          <div style={{ fontSize: 11.5, color: "var(--text-3)", marginTop: 2 }}>
            {single ? pick(copy.node, lang) : pick(copy.title, lang).toLowerCase()}
          </div>
        </div>
      </div>

      {/* precise identifiers, for a specialist. Every shared protein is listed
          with its full name — none is promoted over the others. */}
      <div className="mono" style={{ fontSize: 10.5, color: "var(--text-3)", marginTop: 16, lineHeight: 1.8 }}>
        {proteins.map((p) => (
          <div key={p.uniprot}>{p.gene} · {p.name} · {p.uniprot}</div>
        ))}
        <div style={{ marginTop: 4 }}>{data.shared_biology?.source}</div>
      </div>
    </div>
  );
}

/** Russian needs three plural forms; English two. */
function plural(n: number, node: { ru: string; en: string }, lang: "ru" | "en"): string {
  if (lang === "en") return n === 1 ? node.en : `${node.en}s`;
  const forms: Record<string, [string, string, string]> = {
    "фермент печени": ["фермент печени", "фермента печени", "ферментов печени"],
    "белок-переносчик": ["белок-переносчик", "белка-переносчика", "белков-переносчиков"],
    "белок крови": ["белок крови", "белка крови", "белков крови"],
    "общая мишень": ["общая мишень", "общие мишени", "общих мишеней"],
  };
  const f = forms[node.ru];
  if (!f) return node.ru;
  const mod10 = n % 10, mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return f[0];
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return f[1];
  return f[2];
}

function Empty() {
  const { lang } = useI18n();
  return (
    <div style={{ border: "1px solid rgba(255,196,120,0.3)", background: "rgba(255,196,120,0.05)", borderRadius: "var(--radius-lg)", padding: 22 }}>
      <h3 style={{ fontSize: 17, marginBottom: 8, color: "var(--amber)" }}>{pick(EMPTY_TITLE, lang)}</h3>
      <p style={{ fontSize: 14, color: "var(--text-2)", maxWidth: 640, lineHeight: 1.65 }}>
        {pick(EMPTY_BODY, lang)}
      </p>
    </div>
  );
}

function Box({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ border: "1px solid var(--border-strong)", borderRadius: 8, padding: "8px 14px", fontSize: 13.5, color: "var(--text)", whiteSpace: "nowrap" }}>
      {children}
    </div>
  );
}
