# JARVIS Mission Control

An operations console for the investigation engine. The landing view is a list of missions and
a "New mission" button — **not** a chat transcript. The unit of work here is a run with a plan,
a trace and a report, not a turn in a conversation.

## Running it

The engine must be up first; the UI is a client and holds no state of its own.

```bash
# terminal 1 — the engine
cd backend
uvicorn app.api.app:create_app --factory --reload

# terminal 2 — the console
cd frontend
npm install
npm run dev          # http://localhost:5173
```

Vite proxies `/api` and `/health` to port 8000, so the browser stays on one origin and an SSE
reconnect behaves in development the way it will in production.

```bash
npm run build       # tsc -b && vite build
npm run typecheck   # tsc --noEmit
```

## What it shows

| View | Purpose |
|---|---|
| Mission list | Every run, newest first, with finding and gap counts |
| New mission | Objective plus documents. Aurora fixtures are prefilled |
| Mission detail | Phase tracker, task graph, findings, gaps, report, execution trace |

The detail page subscribes to `GET /missions/{id}/stream` with `EventSource`, so the phase
tracker and the trace move while the run is happening. When the stream closes the page refetches
the settled state: the stream says what *happened*, the REST endpoints say what is *true now*,
and a UI built only on the stream would have to reconstruct state it may have joined too late
to see.

## The rule that is not cosmetic

**Uncertainty is shown, not smoothed.**

Every finding renders its claim, classification, computed confidence, verification state, and
expandable evidence with the source locator each citation resolved to. An unsupported claim is
not hidden and is not quietly styled like a supported one.

Confidence and verification never rely on colour alone. Each state carries a label, a glyph and
a border style as well as a hue — a dashed border for unsupported, dotted for unverified, a
filled bar plus a printed number plus a band word for confidence. Someone who cannot
distinguish the hues must still be able to tell a verified finding from a rejected one, and
"it looked fine to me" is not a test.

Two further things made deliberately visible:

- **Tasks inserted mid-run** are drawn with a dashed border and labelled `INSERTED BY REPLAN`.
  Adaptive replanning is the behaviour the project exists to demonstrate; a task the loop added
  must not look identical to one the planner wrote.
- **A degraded verification** says so on the badge. A check that silently fell back to the
  baseline verifier is weaker than it looks, and a badge that hides that is a lie of omission.

Model deliberation is never rendered. The trace shows operational events only.

## Notes on the build

**Dependencies are React and nothing else.** The implementation plan named Tailwind, React
Query, Zustand, Recharts and Framer Motion. None of them are here: hand-written CSS, `fetch`,
`useState` and `EventSource` cover what this console does, and each library omitted is a
toolchain that cannot break during a demo. Should the UI grow — a findings table that needs
sorting and virtualising, real charts on the evaluation page — React Query and Recharts are the
two worth adding first.

**Types are hand-written** in `src/api/types.ts`, narrower than the schema, covering only the
fields the UI reads. `docs/openapi.json` remains the contract; regenerate it with
`python scripts/export_openapi.py` and reconcile here if a response shape changes. Generating
them is the better long-term answer and needs a codegen step in CI to be worth it.

**Hash routing**, so the app works as static files next to the API without a server that
rewrites unknown paths to `index.html`. Mission URLs stay shareable.

## Not built yet

The Evaluation page (Phase 20's reports rendered in the UI) and the animated graph transitions
of Phase 22. `.agent/evals/reports/*.md` is readable as-is in the meantime.
