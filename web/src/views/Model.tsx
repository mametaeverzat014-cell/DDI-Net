import { Badge } from "../components/Badge";
import { frozen } from "../data/frozen";
import { count } from "../lib/format";
import { useI18n, pick, type Bi } from "../i18n";

// Architecture blocks. Every block is Implemented in frozen V2 (the biological
// branch, marked "specified" in the original design, was completed). I/O
// signatures are the real code values verified against src/ddinet/models/bio_gine.py.
// The prose is bilingual; the numbers, dimensions and layer names are identical
// in both languages because they are the code, not the copy.
const BLOCKS: { name: Bi; io: Bi; body: Bi }[] = [
  {
    name: { ru: "Молекулярный энкодер GINE", en: "GINE molecular encoder" },
    io: { ru: "граф атомов (50 признаков) → структурный вектор 64-d", en: "atom graph (50 feat) → 64-d structural vector" },
    body: {
      ru: "Graph Isomorphism Network с признаками рёбер, 3 слоя, скрытая размерность 64, sum-пулинг. Переносится на любую структуру — вычислим для невиданного препарата.",
      en: "Graph Isomorphism Network with edge features, 3 layers, hidden 64, sum pooling. Transfers to any structure — computable for an unseen drug.",
    },
  },
  {
    name: { ru: "Белковый энкодер Deep Sets", en: "Deep Sets protein encoder" },
    io: { ru: "множество (белок, отношение, свидетельство) → вектор 128-d", en: "set of (protein, relation, evidence) → 128-d vector" },
    body: {
      ru: "Каждый элемент конкатенирует эмбеддинг белка (128), эмбеддинг типа отношения (16) и эмбеддинг типа свидетельства (16) = 160-d, отображается φ (160→256→128) и агрегируется по MEAN. Среднее, а не сумма, чтобы число аннотаций не было путём наименьшего сопротивления.",
      en: "Each element concatenates a protein embedding (128), a relation-type embedding (16) and an evidence-type embedding (16) = 160-d, mapped by φ (160→256→128), MEAN-aggregated. Mean, not sum, so annotation count is not the path of least resistance.",
    },
  },
  {
    name: { ru: "Энкодер путей Deep Sets", en: "Deep Sets pathway encoder" },
    io: { ru: "множество путей Reactome → вектор 128-d", en: "set of Reactome pathways → 128-d vector" },
    body: {
      ru: "Множество принадлежности путям, φ (128→256→128), агрегация MEAN. Только принадлежность — без топологии и направления реакций.",
      en: "Pathway-membership set, φ (128→256→128), MEAN-aggregated. Membership only — no reaction topology or direction.",
    },
  },
  {
    name: { ru: "Мультимодальное слияние", en: "Multimodal fusion" },
    io: { ru: "молекулярный ⊕ белковый ⊕ путевой → вектор препарата 128-d", en: "molecular ⊕ protein ⊕ pathway → 128-d drug vector" },
    body: {
      ru: "Конкатенация активных ветвей, затем Linear → LayerNorm. Пустая биология получает обучаемый токен MISSING, а не нулевой вектор.",
      en: "Concatenate the active branches, then Linear → LayerNorm. Empty biology gets a learned MISSING token, never a zero vector.",
    },
  },
  {
    name: { ru: "Симметричный парный декодер", en: "Symmetric pair decoder" },
    io: { ru: "(препарат A, препарат B) → логит взаимодействия", en: "(drug A, drug B) → interaction logit" },
    body: {
      ru: "Только коммутативные члены — сумма, |разность|, поэлементное произведение и min/max масок модальностей (388-d) — так что f(A,B) = f(B,A) точно, а не приближённо.",
      en: "Commutative terms only — sum, |difference|, elementwise product, and min/max of the modality masks (388-d) — so f(A,B) = f(B,A) exactly, not approximately.",
    },
  },
  {
    name: { ru: "Голова калиброванной вероятности", en: "Calibrated probability head" },
    io: { ru: "логит → вероятность после температурного шкалирования", en: "logit → temperature-scaled probability" },
    body: {
      ru: "Одна температура на сид, подобранная только на валидации. Монотонна, поэтому исправляет калибровку вероятностей, не меняя ранжирования.",
      en: "One temperature per seed, fitted on validation only. Monotonic, so it corrects probability calibration without changing ranking.",
    },
  },
];

export function Model() {
  const { t, lang } = useI18n();
  const c = frozen.config;
  return (
    <section className="section" style={{ paddingTop: "16vh" }}>
      <div className="wrap">
        <span className="eyebrow">{t("md.eyebrow")}</span>
        <h1 style={{ marginTop: 18, maxInlineSize: "16ch" }}>{t("md.title")}</h1>
        <p style={{ marginTop: 18, maxWidth: 640 }}>{t("md.lede")}</p>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 16, marginTop: 44 }}>
          {BLOCKS.map((b) => (
            <div key={b.name.en} style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", background: "var(--surface)", backdropFilter: "var(--blur)", padding: 22, transition: "transform 0.3s var(--ease)" }}
              onMouseEnter={(e) => (e.currentTarget.style.transform = "translateY(-3px)")}
              onMouseLeave={(e) => (e.currentTarget.style.transform = "none")}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: 16, fontWeight: 600, color: "var(--text)" }}>{pick(b.name, lang)}</span>
                <Badge kind="implemented">{t("md.implemented")}</Badge>
              </div>
              <div className="mono" style={{ fontSize: 11, color: "var(--cyan)", marginTop: 10 }}>{pick(b.io, lang)}</div>
              <p style={{ marginTop: 12, fontSize: 13.5 }}>{pick(b.body, lang)}</p>
            </div>
          ))}
        </div>

        {/* commutativity essay */}
        <div style={{ marginTop: 60, borderTop: "1px solid var(--border-soft)", paddingTop: 40, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 48 }} className="collapse">
          <div>
            <h3>{t("md.symtitle")}</h3>
            <p style={{ marginTop: 14 }}>
              {t("md.symbody1")} <span className="mono">[mask_A | mask_B]</span> {t("md.symbody2")}
            </p>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div className="mono" style={{ fontSize: 14, color: "var(--text-2)", padding: "16px 18px", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--radius)" }}>
              f(A, B) = f(B, A)
            </div>
            <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
              <FigStat n={count(c.total_parameters as number, lang)} label={t("md.params")} />
              <FigStat n={String(c.bio_dim)} label={t("md.biodim")} />
              <FigStat n={count(c.optimizer_steps as number, lang)} label={t("md.steps")} />
              <FigStat n={`${c.validation_configs}×${c.validation_seeds}`} label={t("md.grid")} />
            </div>
            <span className="mono" style={{ fontSize: 10, color: "var(--text-3)" }}>{c.source as string}</span>
          </div>
        </div>

        <p className="mono" style={{ marginTop: 40, fontSize: 12, color: "var(--text-3)", maxWidth: 680 }}>{t("md.honest")}</p>
      </div>
    </section>
  );
}

function FigStat({ n, label }: { n: string; label: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <span className="mono" style={{ fontSize: 22, color: "var(--text)" }}>{n}</span>
      <span className="eyebrow">{label}</span>
    </div>
  );
}
