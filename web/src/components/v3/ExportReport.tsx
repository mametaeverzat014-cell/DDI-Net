// "Export PDF" / "JSON" for the analysis on screen.
//
// The export is built from the exact response the page shows (passed in as
// `input`) — nothing is requested again. The PDF code is loaded only when a
// button is pressed, so the library never weighs on the page itself. Buttons
// are native <button>s (keyboard and screen-reader behaviour for free); the
// status line is a polite live region so progress and errors are announced.
import { useEffect, useState } from "react";
import { useI18n, pick, fill, type Bi } from "../../i18n";
import type { ExportInput } from "../../pdf/types";

const T = {
  pdf: { ru: "Экспорт PDF", en: "Export PDF" },
  quick: { ru: "Краткий PDF", en: "Quick PDF" },
  quickTitle: { ru: "Краткий отчёт на 1–2 страницы: статус, последствия по источникам, механизм, неопределённость", en: "1–2 page quick report: status, source-stated outcomes, mechanism, uncertainty" },
  json: { ru: "JSON", en: "JSON" },
  jsonTitle: { ru: "Скачать полные данные ответа в JSON (тот же SHA-256, что указан в PDF)", en: "Download the full response data as JSON (same SHA-256 as stated in the PDF)" },
  group: { ru: "Экспорт отчёта", en: "Report export" },
  disabled: { ru: "Станет доступно, когда появятся результаты.", en: "Available once results are shown." },
  workingPdf: { ru: "Собираем PDF…", en: "Generating PDF…" },
  workingJson: { ru: "Собираем JSON…", en: "Preparing JSON…" },
  done: { ru: "Файл сохранён: {f}", en: "File saved: {f}" },
  failed: { ru: "Не удалось создать файл. {m} Ничего не было скачано.", en: "The file could not be created. {m} Nothing was downloaded." },
  chunk: { ru: "Не загрузился модуль экспорта — возможно, сайт обновился. Обновите страницу и попробуйте снова.", en: "The export module did not load — the site may have been updated. Reload the page and try again." },
  fonts: { ru: "Не загрузились шрифты отчёта; проверьте подключение к сети.", en: "The report fonts did not load; check the network connection." },
  other: { ru: "Техническая причина: {m}.", en: "Technical reason: {m}." },
  note: { ru: "PDF собирается в браузере из показанного ответа; данные никуда не отправляются.", en: "The PDF is built in your browser from the response shown; no data is sent anywhere." },
} satisfies Record<string, Bi>;

type State =
  | { kind: "idle" }
  | { kind: "working"; what: "pdf" | "quick" | "json" }
  | { kind: "done"; file: string }
  | { kind: "error"; message: string };

function explain(e: unknown, lang: "ru" | "en"): string {
  const msg = e instanceof Error ? e.message : String(e);
  if (/dynamically imported module|Importing a module script failed|ChunkLoadError|Loading chunk/i.test(msg)) return pick(T.chunk, lang);
  if (/font|woff|Unknown font format|fetch/i.test(msg)) return pick(T.fonts, lang);
  return fill(pick(T.other, lang), { m: msg.slice(0, 160) });
}

export function ExportReport({ input, id }: { input: ExportInput | null; id: string }) {
  const { lang } = useI18n();
  const [state, setState] = useState<State>({ kind: "idle" });

  // A new analysis replaces the previous outcome message.
  useEffect(() => { setState({ kind: "idle" }); }, [input]);

  const busy = state.kind === "working";
  const run = async (what: "pdf" | "quick" | "json") => {
    if (!input || busy) return;
    setState({ kind: "working", what });
    try {
      const mod = await import("../../pdf/exportReport");
      const file = what === "json" ? await mod.exportJson(input, lang) : await mod.exportPdf(input, lang, what === "quick" ? "quick" : "full");
      mod.download(file);
      setState({ kind: "done", file: file.filename });
    } catch (e) {
      setState({ kind: "error", message: fill(pick(T.failed, lang), { m: explain(e, lang) }) });
    }
  };

  const statusId = `${id}-status`;
  const status =
    !input ? pick(T.disabled, lang)
      : state.kind === "working" ? pick(state.what === "json" ? T.workingJson : T.workingPdf, lang)
        : state.kind === "done" ? fill(pick(T.done, lang), { f: state.file })
          : state.kind === "error" ? state.message
            : pick(T.note, lang);

  return (
    <div className="v3-export" role="group" aria-label={pick(T.group, lang)}>
      <button type="button" className="v3-export-primary" onClick={() => run("pdf")} disabled={!input || busy}
        aria-describedby={statusId} aria-busy={busy && state.kind === "working" && state.what === "pdf"}>
        {busy && state.kind === "working" && state.what === "pdf" ? <span className="v3-spinner" aria-hidden="true" /> : <PdfIcon />}
        {pick(T.pdf, lang)}
      </button>
      {input?.kind === "pair" && (
        <button type="button" className="v3-export-secondary" onClick={() => run("quick")} disabled={!input || busy}
          aria-describedby={statusId} title={pick(T.quickTitle, lang)} aria-label={`${pick(T.quick, lang)} — ${pick(T.quickTitle, lang)}`}>
          {busy && state.kind === "working" && state.what === "quick" ? <span className="v3-spinner" aria-hidden="true" /> : null}
          {pick(T.quick, lang)}
        </button>
      )}
      <button type="button" className="v3-export-secondary" onClick={() => run("json")} disabled={!input || busy}
        aria-describedby={statusId} title={pick(T.jsonTitle, lang)} aria-label={`${pick(T.json, lang)} — ${pick(T.jsonTitle, lang)}`}>
        {busy && state.kind === "working" && state.what === "json" ? <span className="v3-spinner" aria-hidden="true" /> : null}
        {pick(T.json, lang)}
      </button>
      <p id={statusId} className={`v3-export-status${state.kind === "error" ? " is-error" : ""}`} role={state.kind === "error" ? "alert" : "status"} aria-live="polite">
        {status}
      </p>
    </div>
  );
}

function PdfIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <path d="M4 1.5h5.2L13 5.3V14a.5.5 0 0 1-.5.5h-8.5A.5.5 0 0 1 3.5 14V2a.5.5 0 0 1 .5-.5Z" fill="none" stroke="currentColor" strokeWidth="1.3" />
      <path d="M9 1.7V5.5h3.8M8 7.5v4.5m-2-2 2 2 2-2" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
