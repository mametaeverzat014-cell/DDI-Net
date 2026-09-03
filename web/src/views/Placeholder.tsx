// Honest placeholder for views not yet built in the foundation pass. It never
// shows a fake metric — it states plainly that the view is pending.
import { Badge } from "../components/Badge";

export function Placeholder({ title, phase }: { title: string; phase: string }) {
  return (
    <section className="section" style={{ minHeight: "70vh", display: "flex", alignItems: "center" }}>
      <div className="wrap">
        <Badge kind="pending">Not yet built</Badge>
        <h1 style={{ marginTop: 20, maxWidth: 720 }}>{title}</h1>
        <p style={{ marginTop: 18, maxWidth: 620 }}>{phase}</p>
      </div>
    </section>
  );
}
