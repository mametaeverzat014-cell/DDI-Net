# DDI-Net research site (`web/`)

Presentation layer for the frozen DDI-Net V2 scientific state. Built from the
Claude Design handoff (`design_handoff_ddinet/`) — its five-view structure, dark
navy identity, canvas engine and, above all, its scientific-integrity rules.

**This is a frontend only. It does not train, evaluate, or alter any model or
frozen artifact.**

## Scientific source of truth

No scientific number is hand-typed anywhere in this app. `tools/build_frozen_data.py`
reads the frozen artifacts **from the git tag** `v2-final-github-safe-2026-09-03`
(via `git show`, never the working tree) plus `data/mechanism_v1/*.json`, recomputes
every statistic from the per-seed rows, and writes `src/data/frozen.json`. The
frontend imports that file. It runs automatically before `dev` and `build`.

To regenerate manually:

```bash
python3 tools/build_frozen_data.py
```

## Develop / build

```bash
npm install
npm run dev        # regenerates frozen.json, then Vite dev server
npm run build      # typecheck + production build to dist/
npm run typecheck  # tsc --noEmit
npm run lint       # eslint
npm run test       # vitest (formatting + scientific-integrity assertions)
```

Stack: Vite + React + TypeScript. No Framer Motion / D3 / React Flow — the design's
motion is CSS keyframes + native `animation-timeline: view()` and one hand-written
2D canvas engine (`src/canvas/`), matching the handoff's zero-heavy-dependency ethos.

## Integrity rules enforced in code

- Every measured number renders through `<Metric>`, which requires a `source` path.
- Unmeasured values are amber-badged (`<Badge kind="demo|pending|specified">`); the
  0.82 analyze prediction is demo and stays badged.
- Uncertainty renders as `± not estimated` when no SD exists (`meanSd` in `lib/format`).
- AUPRC axes start at 0.5 and are never truncated (`AuprcBars`).
- The evidence ladder is rendered in M0→M4 order (not sorted), so its non-monotonic
  dip is visible; M2 and SUM are shown beating primary M4.
- No safe/unsafe/clinical language; the site-wide footer states it is not a clinical tool.
- `src/data/frozen.test.ts` fails loudly if any of these facts regress.

## Status (foundation pass)

Built: scaffold, design tokens, frozen-data layer, Home, Research, Nav/Footer,
canvas engine, integrity components, 20 passing tests.

Pending (next iterations): Analyze (with disabled live-inference state — checkpoint
`bd45f84e3c1b2c33.pt` is absent), Model, Data & provenance, Drug Explorer, read-only
API, remaining tests.
