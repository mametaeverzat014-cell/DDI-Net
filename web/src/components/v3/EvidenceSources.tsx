// Data & Evidence page: which sources the DDI-Net 3.0 evidence layer consults,
// what each one can and cannot say, and how it is accessed. Assessed before
// integration (docs/DDINET_V3_ARCHITECTURE.md §4); written down here so a reader
// can judge a report without reading the code.
import type { View } from "../../App";
import { useI18n, pick, type Bi } from "../../i18n";
import { v3facts } from "../../data/v3facts";

const T = {
  title: { ru: "Источники доказательств DDI-Net 3.0", en: "DDI-Net 3.0 evidence sources" },
  lede: {
    ru: "Каждый источник отвечает на один узкий вопрос. Ни один не даёт полного покрытия, и ни один не даёт стандартизированной степени тяжести.",
    en: "Each source answers one narrow question. None gives complete coverage, and none gives a standardised severity grade.",
  },
  what: { ru: "Что говорит", en: "What it says" },
  not: { ru: "Чего не говорит", en: "What it does not say" },
  access: { ru: "Доступ", en: "Access" },
  explorer: { ru: "Обзор всех 1 705 препаратов →", en: "Browse all 1,705 drugs →" },
  wording: { ru: "Как сайт формулирует записи DrugBank", en: "How the site words DrugBank records" },
  sym: { ru: "смысл не зависит от порядка — названия подставлены", en: "meaning independent of order — names filled in" },
  cons: { ru: "порядок подтверждён — названия подставлены", en: "order verified — names filled in" },
  unv: { ru: "порядок не подтверждён — без указания, кто на кого влияет", en: "order not verified — no statement of who affects whom" },
} satisfies Record<string, Bi>;

const SOURCES: { name: string; what: Bi; not: Bi; access: Bi }[] = [
  {
    name: "DrugBank · TDC",
    what: { ru: "Есть ли запись о взаимодействии пары и стандартная фраза DrugBank для её типа (86 типов).", en: "Whether a pair has an interaction record, and DrugBank's standard sentence for its type (86 types)." },
    not: { ru: "Степень тяжести; на чём основана запись; надёжный порядок препаратов для многих типов.", en: "Severity; what the record is based on; a reliable drug order for many types." },
    access: { ru: "Локально, выгрузка TDC от 2026-08-24; некоммерческая лицензия DrugBank.", en: "Local, TDC export of 2026-08-24; DrugBank non-commercial licence." },
  },
  {
    name: "DrugBank · ChEMBL MOA",
    what: { ru: "Роль препарата на белке: субстрат, ингибитор, индуктор, агонист… со ссылками PubMed.", en: "A drug's role at a protein: substrate, inhibitor, inducer, agonist… with PubMed references." },
    not: { ru: "Силу действия и долю участия белка в переработке препарата.", en: "Strength of effect, and how much of a drug's handling a protein does." },
    access: { ru: "Локально, DrugBank 5.1 и ChEMBL 36. Биоактивность ChEMBL не используется: общие панели тестирования создают ложное сходство.", en: "Local, DrugBank 5.1 and ChEMBL 36. ChEMBL bioactivity is not used: shared screening panels create false similarity." },
  },
  {
    name: "FDA labels · openFDA",
    what: { ru: "Упомянут ли второй препарат в предупреждениях, противопоказаниях или разделе о взаимодействиях официальной инструкции, и какими словами.", en: "Whether an official label names the other drug in its warnings, contraindications or interactions section, and in what words." },
    not: { ru: "Утверждения о группах препаратов; рынки за пределами США; степень тяжести.", en: "Statements about drug classes; markets outside the US; a severity grade." },
    access: { ru: "По сети, общественное достояние (CC0); ссылка ведёт на DailyMed.", en: "Over the network, public domain (CC0); links go to DailyMed." },
  },
  {
    name: "RxNorm",
    what: { ru: "Какое действующее вещество скрывается за торговым названием или вариантом написания.", en: "Which ingredient a brand name or spelling variant refers to." },
    not: { ru: "Ничего о взаимодействиях: API взаимодействий NLM закрыт 2 января 2024 года.", en: "Nothing about interactions: NLM retired its interaction API on 2 January 2024." },
    access: { ru: "По сети, общественное достояние.", en: "Over the network, public domain." },
  },
  {
    name: "Reactome",
    what: { ru: "В каких биологических путях участвует белок.", en: "Which biological pathways a protein belongs to." },
    not: { ru: "Что общий путь вызывает взаимодействие.", en: "That a shared pathway causes an interaction." },
    access: { ru: "Локально, UniProt2Reactome.", en: "Local, UniProt2Reactome." },
  },
];

export function EvidenceSources({ setView }: { setView: (v: View) => void }) {
  const { lang } = useI18n();
  const d = v3facts.direction_audit;
  const total = d.n_records;
  const share = (n: number) => `${((n / total) * 100).toFixed(1)}%`;
  return (
    <div style={{ marginTop: 80 }}>
      <h2>{pick(T.title, lang)}</h2>
      <p style={{ marginTop: 14, maxWidth: 680 }}>{pick(T.lede, lang)}</p>
      <div className="v3-scroll" style={{ marginTop: 24 }}>
        <table className="v3-table" style={{ minWidth: 720 }}>
          <thead><tr><th /><th>{pick(T.what, lang)}</th><th>{pick(T.not, lang)}</th><th>{pick(T.access, lang)}</th></tr></thead>
          <tbody>
            {SOURCES.map((s) => (
              <tr key={s.name}>
                <td className="mono" style={{ color: "var(--cyan)", whiteSpace: "nowrap" }}>{s.name}</td>
                <td>{pick(s.what, lang)}</td>
                <td>{pick(s.not, lang)}</td>
                <td style={{ fontSize: 12 }}>{pick(s.access, lang)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="v3-card" style={{ marginTop: 22 }}>
        <span className="eyebrow">{pick(T.wording, lang)} · {total.toLocaleString(lang)}</span>
        <ul style={{ margin: "12px 0 0", paddingLeft: 18, fontSize: 13.5, color: "var(--text-2)", lineHeight: 1.8 }}>
          <li><span className="mono">{share(d.records_by_status.symmetric)}</span> — {pick(T.sym, lang)}</li>
          <li><span className="mono">{share(d.records_by_status.consistent)}</span> — {pick(T.cons, lang)}</li>
          <li><span className="mono">{share(d.records_by_status.unverified)}</span> — {pick(T.unv, lang)}</li>
        </ul>
        <span className="mono" style={{ display: "block", marginTop: 8, fontSize: 10, color: "var(--text-3)" }}>{d.source}</span>
      </div>

      <button onClick={() => setView("drugs")} className="mono"
        style={{ marginTop: 22, background: "none", border: "none", color: "var(--cyan)", cursor: "pointer", fontSize: 13, padding: 0 }}>
        {pick(T.explorer, lang)}
      </button>
    </div>
  );
}
