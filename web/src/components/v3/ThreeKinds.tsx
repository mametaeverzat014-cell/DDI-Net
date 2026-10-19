// Overview section: the one idea DDI-Net 3.0 is built around — three kinds of
// statement that are never mixed — and the entry points to the new tools.
import type { View } from "../../App";
import { useI18n, pick, type Bi } from "../../i18n";

const T = {
  eyebrow: { ru: "DDI-Net 3.0 · Объяснимая аналитика взаимодействий", en: "DDI-Net 3.0 · Explainable interaction intelligence" },
  title: { ru: "Три вида утверждений, которые нельзя смешивать.", en: "Three kinds of statement that must never be mixed." },
  lede: {
    ru: "Модель, которая выдаёт одно число, не говорит, что известно, почему и насколько это надёжно. DDI-Net 3.0 разделяет ответ на три слоя и подписывает каждое предложение.",
    en: "A model that outputs one number does not say what is known, why, or how reliable it is. DDI-Net 3.0 splits the answer into three layers and labels every sentence.",
  },
  cta1: { ru: "Анализатор пары", en: "Pair analyzer" },
  cta2: { ru: "Граф механизмов", en: "Mechanism graph" },
  cta3: { ru: "Несколько препаратов", en: "Multiple drugs" },
} satisfies Record<string, Bi>;

const KINDS: { color: string; title: Bi; body: Bi; example: Bi }[] = [
  {
    color: "var(--ev-documented)",
    title: { ru: "Задокументировано", en: "Documented" },
    body: {
      ru: "Что записано в источниках: базе DrugBank и официальных инструкциях FDA. С датой получения, ссылкой и словами самого источника.",
      en: "What the sources record: DrugBank and official FDA labels. With retrieval date, link and the source's own words.",
    },
    example: { ru: "«Концентрация одного из двух препаратов может повышаться…» — DrugBank", en: "“The serum concentration of one of the two drugs can be increased…” — DrugBank" },
  },
  {
    color: "var(--ev-hypothesis)",
    title: { ru: "Гипотеза о механизме", en: "Mechanism hypothesis" },
    body: {
      ru: "Почему это может происходить: например, один препарат подавляет фермент, который перерабатывает другой. Собрано из задокументированных ролей с PubMed-ссылками, но для пары не проверено.",
      en: "Why it might happen: for instance, one drug inhibits an enzyme that processes the other. Assembled from documented roles with PubMed links, but not tested for the pair.",
    },
    example: { ru: "флуконазол подавляет CYP2C9, варфарин — его субстрат", en: "fluconazole inhibits CYP2C9; warfarin is its substrate" },
  },
  {
    color: "var(--ev-model)",
    title: { ru: "Сигнал модели", en: "Model signal" },
    body: {
      ru: "Насколько пара похожа на уже описанные взаимодействия, по оценке BIO-GINE — с указанием, видела ли модель эти препараты при обучении и насколько она точна в таком режиме.",
      en: "How much the pair resembles recorded interactions, according to BIO-GINE — with whether the model saw these drugs in training and how accurate it is in that regime.",
    },
    example: { ru: "сходство, а не риск; не вероятность вреда", en: "resemblance, not risk; not a probability of harm" },
  },
];

export function ThreeKinds({ setView }: { setView: (v: View) => void }) {
  const { lang } = useI18n();
  return (
    <section className="section">
      <div className="wrap">
        <span className="eyebrow">{pick(T.eyebrow, lang)}</span>
        <h2 className="reveal" style={{ marginTop: 18, maxWidth: "18ch" }}>{pick(T.title, lang)}</h2>
        <p style={{ marginTop: 22, maxWidth: 680 }}>{pick(T.lede, lang)}</p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 18, marginTop: 36 }}>
          {KINDS.map((k) => (
            <article key={k.title.en} className="v3-card reveal" style={{ borderTop: `3px solid ${k.color}` }}>
              <span className="v3-chip" style={{ color: k.color }}>{pick(k.title, lang)}</span>
              <p style={{ marginTop: 14, fontSize: 14.5 }}>{pick(k.body, lang)}</p>
              <p className="mono" style={{ marginTop: 14, fontSize: 11.5, color: "var(--text-3)" }}>{pick(k.example, lang)}</p>
            </article>
          ))}
        </div>
        <div style={{ marginTop: 32, display: "flex", gap: 12, flexWrap: "wrap" }}>
          {([["analyzer", T.cta1], ["mechanisms", T.cta2], ["multi", T.cta3]] as const).map(([v, label]) => (
            <button key={v} onClick={() => setView(v)}
              style={{ background: "none", color: "var(--text)", border: "1px solid var(--border-strong)", borderRadius: 24, padding: "11px 20px", fontSize: 14, cursor: "pointer", fontFamily: "var(--font-ui)" }}>
              {pick(label, lang)} →
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
