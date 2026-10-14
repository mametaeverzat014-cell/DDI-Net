import { useCallback, useEffect, useState } from "react";
import { Nav } from "./components/Nav";
import { Footer } from "./components/Footer";
import { Home } from "./views/Home";
import { Research } from "./views/Research";
import { Analyze } from "./views/Analyze";
import { Analyzer } from "./views/Analyzer";
import { Mechanisms } from "./views/Mechanisms";
import { MultiDrug } from "./views/MultiDrug";
import { Model } from "./views/Model";
import { Data } from "./views/Data";
import { DrugExplorer } from "./views/DrugExplorer";
import { Limitations } from "./views/Limitations";
import { parseHash, toHash } from "./lib/route";

export type View =
  | "home" | "analyzer" | "mechanisms" | "multi" | "research" | "model" | "data" | "limitations"
  | "drugs" | "analyze";

const DEFAULT_PAIR: [string, string] = ["DB00682", "DB00196"]; // warfarin + fluconazole

export function App() {
  const initial = parseHash(typeof window === "undefined" ? "" : window.location.hash);
  const [view, setViewState] = useState<View>(initial.view ?? "home");
  const [pair, setPairState] = useState<[string, string]>(initial.pair ?? DEFAULT_PAIR);

  // The URL carries the view and the pair, so a result can be linked to.
  // replaceState, not pushState: switching drugs should not flood the history.
  useEffect(() => {
    const h = toHash(view, pair);
    if (window.location.hash !== h) window.history.replaceState(null, "", h);
  }, [view, pair]);

  useEffect(() => {
    const onHash = () => {
      const r = parseHash(window.location.hash);
      if (r.view) setViewState(r.view);
      if (r.pair) setPairState(r.pair);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const setView = useCallback((v: View) => setViewState(v), []);
  const setPair = useCallback((p: [string, string]) => setPairState(p), []);

  // reset scroll on view change, matching the prototype's behaviour
  useEffect(() => { window.scrollTo(0, 0); }, [view]);

  return (
    <>
      <Nav view={view} setView={setView} />
      <main>
        {view === "home" && <Home setView={setView} />}
        {view === "analyzer" && <Analyzer pair={pair} setPair={setPair} setView={setView} />}
        {view === "mechanisms" && <Mechanisms pair={pair} setPair={setPair} />}
        {view === "multi" && <MultiDrug setPair={setPair} setView={setView} />}
        {view === "analyze" && <Analyze />}
        {view === "model" && <Model />}
        {view === "research" && <Research />}
        {view === "data" && <Data setView={setView} />}
        {view === "drugs" && <DrugExplorer />}
        {view === "limitations" && <Limitations />}
      </main>
      <Footer setView={setView} />
    </>
  );
}
