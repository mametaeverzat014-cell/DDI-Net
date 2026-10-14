// DDI-Net 3.0 measurements, shown where the study's results are shown.
//
// Three findings from existing artifacts, none requiring a new model:
// the DrugBank export's drug order is unreliable for several interaction
// types; seed disagreement does not add uncertainty information beyond the
// score itself; and missing protein annotations measurably lower accuracy.
// Every number comes from v3facts.json (generated from reports/v3_*.json).
import { useI18n, pick, type Bi } from "../../i18n";
import { v3facts } from "../../data/v3facts";

const T = {
  eyebrow: { ru: "DDI-Net 3.0 · Новые измерения", en: "DDI-Net 3.0 · New measurements" },
  title: { ru: "Что мы проверили, прежде чем показывать объяснения", en: "What we checked before showing explanations" },
  dirTitle: { ru: "Порядок препаратов в выгрузке DrugBank (TDC) ненадёжен", en: "The drug order in the DrugBank (TDC) export is unreliable" },
  dirBody: {
    ru: "В записи «метаболизм #Drug2 замедляется при сочетании с #Drug1» на месте #Drug1 должен стоять ингибитор фермента, который перерабатывает #Drug2. Мы проверили это по собственным аннотациям DrugBank. Для одних типов записей порядок совпадает почти всегда, для других — почти всегда перевёрнут. Поэтому сайт не говорит, какой препарат на какой влияет, если порядок не подтверждён.",
    en: "In a record 'the metabolism of #Drug2 is decreased when combined with #Drug1', the #Drug1 slot should hold an inhibitor of an enzyme that processes #Drug2. We checked this against DrugBank's own annotations. For some record types the order almost always matches; for others it is almost always reversed. So the site does not say which drug affects which unless the order is verified.",
  },
  colType: { ru: "тип", en: "type" },
  colInf: { ru: "проверяемых записей", en: "checkable records" },
  colCons: { ru: "порядок совпадает", en: "order matches" },
  seedTitle: { ru: "Разброс между запусками модели не даёт новой информации о неопределённости", en: "Disagreement between model runs adds no uncertainty information" },
  seedBody: {
    ru: "На отложенных парах разброс пяти запусков находит ошибки ансамбля не лучше, чем простая близость оценки к 0.5. Поэтому отдельный «индикатор неопределённости» на его основе не показывается.",
    en: "On held-out pairs, the spread of five runs finds the ensemble's errors no better than the score's simple closeness to 0.5. So no separate 'uncertainty indicator' is built from it.",
  },
  sd: { ru: "разброс запусков", en: "seed spread" },
  margin: { ru: "близость к 0.5", en: "closeness to 0.5" },
  covTitle: { ru: "Без данных о белках модель заметно хуже", en: "Without protein data the model is noticeably worse" },
  covBody: {
    ru: "Если хотя бы у одного препарата нет записей о белках, точность на отложенных парах ниже. Анализатор сообщает об этом для каждой такой пары.",
    en: "When at least one drug has no protein records, accuracy on held-out pairs is lower. The Analyzer says so for every such pair.",
  },
  both: { ru: "оба с белками", en: "both annotated" },
  one: { ru: "хотя бы один без белков", en: "at least one unannotated" },
} satisfies Record<string, Bi>;

const f3 = (x: number) => x.toFixed(3);

export function V3Findings() {
  const { lang } = useI18n();
  const d = v3facts.direction_audit;
  const s = v3facts.seed_disagreement.views;
  const c = v3facts.coverage_reliability.views;
  const types = Object.entries(d.pk_types).filter(([, r]) => r.n_informative >= 30);

  return (
    <div style={{ marginTop: 80 }}>
      <span className="eyebrow">{pick(T.eyebrow, lang)}</span>
      <h2 style={{ marginTop: 16, maxWidth: "20ch" }}>{pick(T.title, lang)}</h2>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 18, marginTop: 28 }}>
        <article className="v3-card">
          <h3 style={{ fontSize: 18 }}>{pick(T.dirTitle, lang)}</h3>
          <p style={{ fontSize: 13.5, marginTop: 10 }}>{pick(T.dirBody, lang)}</p>
          <table className="v3-table" style={{ marginTop: 12 }}>
            <thead><tr><th>{pick(T.colType, lang)}</th><th>{pick(T.colInf, lang)}</th><th>{pick(T.colCons, lang)}</th></tr></thead>
            <tbody>
              {types.map(([y, r]) => (
                <tr key={y} title={r.template}>
                  <td className="mono">{y}</td>
                  <td className="mono">{r.n_informative.toLocaleString(lang)}</td>
                  <td className="mono" style={{ color: r.status === "consistent" ? "var(--cyan)" : "var(--ev-missing)" }}>
                    {r.consistency === null ? "—" : `${(r.consistency * 100).toFixed(1)}%`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <span className="mono" style={{ display: "block", marginTop: 8, fontSize: 10, color: "var(--text-3)" }}>{d.source}</span>
        </article>

        <article className="v3-card">
          <h3 style={{ fontSize: 18 }}>{pick(T.seedTitle, lang)}</h3>
          <p style={{ fontSize: 13.5, marginTop: 10 }}>{pick(T.seedBody, lang)}</p>
          <table className="v3-table" style={{ marginTop: 12 }}>
            <thead><tr><th /><th>AUROC · {pick(T.sd, lang)}</th><th>AUROC · {pick(T.margin, lang)}</th></tr></thead>
            <tbody>
              {(["pooled", "S3"] as const).map((v) => (
                <tr key={v}>
                  <td className="mono">{v}</td>
                  <td className="mono">{f3(s[v].auroc_sd_detects_error)} <span style={{ color: "var(--text-3)" }}>[{f3(s[v].auroc_sd_detects_error_ci95[0])}–{f3(s[v].auroc_sd_detects_error_ci95[1])}]</span></td>
                  <td className="mono">{f3(s[v].auroc_margin_detects_error)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <span className="mono" style={{ display: "block", marginTop: 8, fontSize: 10, color: "var(--text-3)" }}>{v3facts.seed_disagreement.source}</span>
        </article>

        <article className="v3-card">
          <h3 style={{ fontSize: 18 }}>{pick(T.covTitle, lang)}</h3>
          <p style={{ fontSize: 13.5, marginTop: 10 }}>{pick(T.covBody, lang)}</p>
          <table className="v3-table" style={{ marginTop: 12 }}>
            <thead><tr><th /><th>AUROC · {pick(T.both, lang)}</th><th>AUROC · {pick(T.one, lang)}</th></tr></thead>
            <tbody>
              {(["pooled", "S3"] as const).map((v) => (
                <tr key={v}>
                  <td className="mono">{v}</td>
                  <td className="mono">{f3(c[v].both_annotated.auroc_mean)} ± {f3(c[v].both_annotated.auroc_sd)}</td>
                  <td className="mono">{f3(c[v].at_least_one_unannotated.auroc_mean)} ± {f3(c[v].at_least_one_unannotated.auroc_sd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <span className="mono" style={{ display: "block", marginTop: 8, fontSize: 10, color: "var(--text-3)" }}>{v3facts.coverage_reliability.source}</span>
        </article>
      </div>
    </div>
  );
}
