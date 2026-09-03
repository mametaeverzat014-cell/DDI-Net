import { useEffect, useState } from "react";
import { Nav } from "./components/Nav";
import { Footer } from "./components/Footer";
import { Home } from "./views/Home";
import { Research } from "./views/Research";
import { Placeholder } from "./views/Placeholder";

export type View = "home" | "analyze" | "model" | "research" | "data";

export function App() {
  const [view, setView] = useState<View>("home");

  // reset scroll on view change, matching the prototype's behaviour
  useEffect(() => { window.scrollTo(0, 0); }, [view]);

  return (
    <>
      <Nav view={view} setView={setView} />
      <main>
        {view === "home" && <Home setView={setView} />}
        {view === "research" && <Research />}
        {view === "analyze" && <Placeholder title="Analyze a drug pair" phase="Foundation build — Analyze arrives in the next iteration." />}
        {view === "model" && <Placeholder title="How BIO-GINE works" phase="Foundation build — the architecture view arrives in the next iteration." />}
        {view === "data" && <Placeholder title="Data & provenance" phase="Foundation build — the data explorer arrives in the next iteration." />}
      </main>
      <Footer />
    </>
  );
}
