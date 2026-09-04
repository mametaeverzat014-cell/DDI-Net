import { frozen } from "../data/frozen";
import { pct } from "../lib/format";
import { useI18n, pick, type Bi } from "../i18n";

// Limitations are prominent, not hidden — a dedicated view. Every item is a real
// constraint of the frozen study, phrased as the manuscript phrases it, in both
// languages. Nothing is softened in translation.
const ITEMS: { title: Bi; body: Bi }[] = [
  {
    title: { ru: "Выбранные негативы не являются подтверждёнными отсутствиями взаимодействия", en: "Sampled negatives are not confirmed non-interactions" },
    body: {
      ru: "В источнике есть только задокументированные положительные пары; ~86,8% пространства пар не размечено, а не отрицательно. Часть выбранных пар с согласованными степенями почти наверняка является незадокументированными настоящими взаимодействиями, что занижает измеренное качество на неизвестную величину.",
      en: "The source has only documented positives; ~86.8% of the pair space is unlabelled, not negative. Some sampled degree-matched pairs are almost certainly undocumented true interactions, which depresses measured performance by an unknown amount.",
    },
  },
  {
    title: { ru: "Одно замороженное разбиение по препаратам", en: "One frozen drug partition" },
    body: {
      ru: "Результаты получены на единственном разбиении с отложенными препаратами. Репликация по разбиениям не проводилась, поэтому числа не оценивают изменчивость по альтернативным вселенным препаратов.",
      en: "Results come from a single drug-holdout split. No cross-partition replication was performed, so the numbers do not estimate variability across alternative drug universes.",
    },
  },
  {
    title: { ru: "Пять сидов измеряют только шум обучения", en: "Five seeds quantify training noise only" },
    body: {
      ru: "Сиды варьируют инициализацию, порядок батчей и выбор негативов на одном фиксированном разбиении, а не вселенную препаратов. При n=5 предположение о нормальности в t-критерии проверить невозможно.",
      en: "Seeds vary initialisation, batch order and negative draws on one fixed partition — not the drug universe. With n=5 the t-test's normality assumption cannot be checked.",
    },
  },
  {
    title: { ru: "Немонотонная лестница абляций", en: "Non-monotonic ablation ladder" },
    body: {
      ru: "M2 и контроль SUM превосходят пререгистрированную основную M4 на тесте. M4 была зафиксирована на валидации до оценки на тесте; это пререгистрированная модель, а не лучшая на тесте.",
      en: "M2 and the SUM control both exceed the preregistered primary M4 on the test set. M4 was fixed on validation before test evaluation; it is the preregistered model, not the best test performer.",
    },
  },
  {
    title: { ru: "CONTROL E неидентифицируем", en: "CONTROL E is not identifiable" },
    body: {
      ru: "Запланированный зонд предсказывает обучающую степень DDI по эмбеддингу. Held-out R² не определён, потому что у каждого отложенного препарата степень равна нулю (дисперсия целевой переменной нулевая). Интерпретируем только R² на обучении, и только описательно.",
      en: "The planned probe predicts training-DDI degree from the embedding. Held-out R² is undefined because every held-out drug has degree zero (target variance is zero). Only the training-side R² is interpretable, and only descriptively.",
    },
  },
  {
    title: { ru: "Оценка на непересекающихся скаффолдах не проводилась", en: "Scaffold-disjoint not evaluated" },
    body: {
      ru: "Отложение препаратов не мешает тестовому препарату разделять скаффолд Бемиса–Мурко с обучающим. Оценка на непересекающихся скаффолдах в финальном V2 не проводилась, поэтому критерий фальсификации F5 разрешён лишь частично.",
      en: "Drug-holdout does not stop a test drug sharing a Bemis–Murcko scaffold with a training drug. Scaffold-disjoint evaluation was not performed in final V2, so falsification criterion F5 is only partly resolved.",
    },
  },
  {
    title: { ru: "Нет внешней и проспективной валидации", en: "No external or prospective validation" },
    body: {
      ru: "Все результаты получены на одном замороженном ретроспективном датасете. Ни независимый источник взаимодействий, ни проспективная проверка после среза данных не использовались.",
      en: "All results are from one frozen retrospective dataset. No independent interaction resource and no post-snapshot prospective test were used.",
    },
  },
  {
    title: { ru: "Нет клинической валидации", en: "No clinical validation" },
    body: {
      ru: "Система никогда не оценивалась по клиническим исходам. Ничто здесь не подтверждает клиническое утверждение, и ни один вывод не является медицинской рекомендацией.",
      en: "The system has never been evaluated against clinical outcomes. Nothing here supports a clinical claim, and no output is a medical recommendation.",
    },
  },
  {
    title: { ru: "Нет контекста пациента", en: "No patient-level context" },
    body: {
      ru: "Возраст, пол, доза, функция почек и печени, генотип не являются входами. У модели нет представления о пациенте, и она не может делать предсказания с учётом возраста или дозы.",
      en: "Age, sex, dose, renal or hepatic function and genotype are not inputs. The model has no representation of a patient and cannot make age- or dose-specific predictions.",
    },
  },
  {
    title: { ru: "Интерпретируемость — не причинность", en: "Interpretability is not causality" },
    body: {
      ru: "Пертурбационный анализ измеряет опору модели — насколько сдвигается предсказание при изъятии входа. Он не устанавливает, что белок опосредует взаимодействие.",
      en: "Perturbation analyses measure model reliance — how far the prediction moves when an input is withheld. They do not establish that a protein mediates an interaction.",
    },
  },
];

export function Limitations() {
  const { t, lang } = useI18n();
  return (
    <section className="section" style={{ paddingTop: "16vh" }}>
      <div className="wrap">
        <span className="eyebrow">{t("lm.eyebrow")}</span>
        <h1 style={{ marginTop: 18, maxInlineSize: "16ch" }}>{t("lm.title")}</h1>
        <p style={{ marginTop: 18, maxWidth: 640 }}>
          {t("lm.lede1")} {pct(100 - (frozen.coverage.protein_any_pct as number))} {t("lm.lede2")}
        </p>

        <div style={{ marginTop: 44, display: "flex", flexDirection: "column", gap: 2 }}>
          {ITEMS.map((it, i) => (
            <div key={it.title.en} style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: 20, padding: "22px 0", borderTop: "1px solid var(--border-soft)" }}>
              <span className="mono" style={{ fontSize: 12, color: "var(--text-3)" }}>{String(i + 1).padStart(2, "0")}</span>
              <div>
                <div style={{ fontSize: 16, fontWeight: 600, color: "var(--text)" }}>{pick(it.title, lang)}</div>
                <p style={{ marginTop: 8, maxWidth: 720 }}>{pick(it.body, lang)}</p>
              </div>
            </div>
          ))}
        </div>

        <div style={{ marginTop: 40, border: "1px solid var(--border-strong)", borderRadius: "var(--radius)", padding: 22, background: "var(--surface)" }}>
          <p style={{ fontSize: 14, color: "var(--text)" }}>{t("lm.disclaimer")}</p>
        </div>
      </div>
    </section>
  );
}
