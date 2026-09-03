// Fixed full-viewport canvas behind the home sections. Scroll progress over the
// whole page is normalised 0–1, smoothed, and fed to keyframe tracks so the two
// hero molecules travel, an "unseen" outside drug appears, and an embedding
// point cloud emerges — one continuous composition, as the design specifies.
// Respects prefers-reduced-motion by rendering a single static frame.
import { useEffect, useRef } from "react";
import { buildMolecule, drawMolecule, kf, type Molecule } from "./engine";

export function HomeCanvas() {
  const ref = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const molA: Molecule = buildMolecule(7, 3);
    const molB: Molecule = buildMolecule(23, 2);
    const cloud = Array.from({ length: 300 }, (_, i) => {
      const r = mulberryPoint(i);
      return { x: (r() - 0.5) * 2, y: (r() - 0.5) * 2, z: (r() - 0.5) * 2 };
    });

    let dpr = Math.min(window.devicePixelRatio || 1, 2);
    let W = 0, H = 0;
    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      W = canvas!.clientWidth; H = canvas!.clientHeight;
      canvas!.width = Math.round(W * dpr); canvas!.height = Math.round(H * dpr);
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    let smooth = 0;
    let raf = 0;
    const start = performance.now();

    function scrollProgress(): number {
      const max = document.documentElement.scrollHeight - window.innerHeight;
      return max > 0 ? Math.min(1, Math.max(0, window.scrollY / max)) : 0;
    }

    function frame(now: number) {
      const target = scrollProgress();
      smooth += (target - smooth) * 0.12;
      const p = smooth;
      const t = (now - start) / 1000;

      ctx!.clearRect(0, 0, W, H);

      // radial illumination centred mid-canvas
      const glow = ctx!.createRadialGradient(W * 0.5, H * 0.42, 0, W * 0.5, H * 0.42, Math.max(W, H) * 0.6);
      glow.addColorStop(0, "rgba(38,84,168,0.30)");
      glow.addColorStop(0.4, "rgba(20,48,104,0.14)");
      glow.addColorStop(1, "rgba(6,16,31,0)");
      ctx!.fillStyle = glow;
      ctx!.fillRect(0, 0, W, H);

      // molecule A travels left→centre and shrinks as the composition advances
      const ax = kf(p, [[0, 0.30], [0.35, 0.42], [0.7, 0.5], [1, 0.5]]) * W;
      const ay = kf(p, [[0, 0.44], [0.5, 0.5], [1, 0.42]]) * H;
      const aScale = kf(p, [[0, 46], [0.5, 34], [1, 24]]);
      const aOp = kf(p, [[0, 1], [0.75, 0.7], [1, 0.15]]);
      drawMolecule(ctx!, molA, ax, ay, aScale, t * 0.18, aOp);

      // molecule B mirrors from the right
      const bx = kf(p, [[0, 0.70], [0.35, 0.58], [0.7, 0.5], [1, 0.5]]) * W;
      const by = kf(p, [[0, 0.5], [0.5, 0.5], [1, 0.58]]) * H;
      const bScale = kf(p, [[0, 40], [0.5, 30], [1, 22]]);
      const bOp = kf(p, [[0, 0.9], [0.75, 0.6], [1, 0.12]]);
      drawMolecule(ctx!, molB, bx, by, bScale, -t * 0.15, bOp);

      // an "unseen" outside drug fades in during the middle (the leakage story)
      const uOp = kf(p, [[0.15, 0], [0.32, 0.8], [0.55, 0.5], [0.8, 0]]);
      if (uOp > 0.01) {
        ctx!.globalAlpha = uOp;
        ctx!.strokeStyle = "rgba(255,196,120,0.6)";
        ctx!.setLineDash([4, 5]);
        ctx!.beginPath();
        ctx!.arc(W * 0.82, H * 0.3, 34, 0, Math.PI * 2);
        ctx!.stroke();
        ctx!.setLineDash([]);
        ctx!.globalAlpha = 1;
      }

      // embedding point cloud emerges toward the end (perspective-projected)
      const cOp = kf(p, [[0.55, 0], [0.8, 0.7], [1, 0.5]]);
      if (cOp > 0.01) {
        const rot = t * 0.1;
        const cos = Math.cos(rot), sin = Math.sin(rot);
        for (const pt of cloud) {
          const rx = pt.x * cos - pt.z * sin;
          const rz = pt.x * sin + pt.z * cos;
          const persp = 1 / (1 + rz * 0.4);
          const sx = W * 0.5 + rx * 120 * persp;
          const sy = H * 0.5 + pt.y * 120 * persp;
          ctx!.globalAlpha = cOp * Math.max(0.1, persp - 0.3);
          ctx!.fillStyle = "#6fe3f5";
          ctx!.beginPath(); ctx!.arc(sx, sy, 1.4 * persp, 0, Math.PI * 2); ctx!.fill();
        }
        ctx!.globalAlpha = 1;
      }

      if (!reduce) raf = requestAnimationFrame(frame);
    }

    raf = requestAnimationFrame(frame);
    return () => { cancelAnimationFrame(raf); ro.disconnect(); };
  }, []);

  return (
    <canvas
      ref={ref}
      aria-hidden="true"
      style={{ position: "fixed", inset: 0, width: "100%", height: "100vh", zIndex: 0, pointerEvents: "none" }}
    />
  );
}

// tiny per-point deterministic sequence, independent of the engine PRNG
function mulberryPoint(i: number): () => number {
  let a = (i * 2654435761) >>> 0;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let x = Math.imul(a ^ (a >>> 15), 1 | a);
    x = (x + Math.imul(x ^ (x >>> 7), 61 | x)) ^ x;
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
}
