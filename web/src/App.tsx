import { useEffect, useState } from "react";
import { Nav } from "./components/Nav";
import { Footer } from "./components/Footer";
import { Home } from "./views/Home";
import { Research } from "./views/Research";
import { Analyze } from "./views/Analyze";
import { Model } from "./views/Model";
import { Data } from "./views/Data";
import { DrugExplorer } from "./views/DrugExplorer";
import { Limitations } from "./views/Limitations";

export type View = "home" | "analyze" | "model" | "research" | "data" | "drugs" | "limitations";

export function App() {
  const [view, setView] = useState<View>("home");

  // reset scroll on view change, matching the prototype's behaviour
  useEffect(() => { window.scrollTo(0, 0); }, [view]);

  return (
    <>
      <Nav view={view} setView={setView} />
      <main>
        {view === "home" && <Home setView={setView} />}
        {view === "analyze" && <Analyze />}
        {view === "model" && <Model />}
        {view === "research" && <Research />}
        {view === "data" && <Data />}
        {view === "drugs" && <DrugExplorer />}
        {view === "limitations" && <Limitations />}
      </main>
      <Footer setView={setView} />
    </>
  );
}
