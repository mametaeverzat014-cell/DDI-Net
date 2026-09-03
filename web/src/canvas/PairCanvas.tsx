// Two generated molecules side by side — the "pair" scene. Synthetic geometry,
// used only to make the pair legible; it is not the real conformer of either drug.
import { useEffect, useRef } from "react";
import { buildMolecule, drawMolecule } from "./engine";

export function PairCanvas({ seedA, seedB }: { seedA: number; seedB: number }) {
  const ref = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const molA = buildMolecule(seedA + 1, 3);
    const molB = buildMolecule(seedB + 1, 2);

    let dpr = Math.min(window.devicePixelRatio || 1, 2);
    let W = 0, H = 0;
    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      W = canvas!.clientWidth; H = 240;
      canvas!.width = Math.round(W * dpr); canvas!.height = Math.round(H * dpr);
      canvas!.style.height = H + "px";
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    let raf = 0;
    const start = performance.now();
    function frame(now: number) {
      const t = (now - start) / 1000;
      ctx!.clearRect(0, 0, W, H);
      // connecting hairline
      ctx!.strokeStyle = "rgba(111,227,245,0.18)";
      ctx!.setLineDash([3, 6]);
      ctx!.beginPath(); ctx!.moveTo(W * 0.34, H / 2); ctx!.lineTo(W * 0.66, H / 2); ctx!.stroke();
      ctx!.setLineDash([]);
      drawMolecule(ctx!, molA, W * 0.27, H / 2, 22, t * 0.16, 0.95);
      drawMolecule(ctx!, molB, W * 0.73, H / 2, 20, -t * 0.14, 0.95);
      if (!reduce) raf = requestAnimationFrame(frame);
    }
    raf = requestAnimationFrame(frame);
    return () => { cancelAnimationFrame(raf); ro.disconnect(); };
  }, [seedA, seedB]);

  return <canvas ref={ref} aria-hidden="true" style={{ width: "100%", height: 240 }} />;
}
