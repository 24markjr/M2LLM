# ADR-011 — The knowledge graph explorer: vanilla 3d-force-graph, one wrapper, pure logic beside it

## Status

Accepted — 2026-10-04 (Phase 32)

## Context

Member 3 showed their knowledge graph in `dashboard.html`: a static page with a 2D vis.js network
over the whole graph. The owner asked for the knowledge graph to be **interactive and 3D**, with
**nodes that have sub-nodes**, **clicking a node highlighting all its related sub-nodes**, and
**hovering a node showing a pop-up** with its information (2026-10-03).

Phase 31 gave each mission a graph endpoint (`/missions/{id}/knowledge/graph`), node details
(`/nodes/{id}`) and a finding's evidence trail (`/findings/{id}/trail`). This decision is about
the browser side.

The frontend is React 19, Vite and strict TypeScript, with no chart or graph library and, until
this phase, no test runner.

## Decision

**`3d-force-graph` (three.js) for 3D and `force-graph` for 2D, used as vanilla libraries inside
one React component, with every decision about what to show kept in a pure module that is
unit-tested.**

| Piece | Role |
|---|---|
| `components/graph3d/model.ts` | Pure functions: what is visible (expand/collapse, filters), what is lit by a click at depth 1–3, which parents to unfold so lit claims can be seen, search, keyboard order, shape/colour/size/particles, `shortLabel`, 2D or 3D at start |
| `components/graph3d/KnowledgeGraph3D.tsx` | The only file that touches WebGL or canvas. Creates one library instance per mode, feeds it data, re-evaluates accessors when the highlight changes, flies the camera, frames the graph, disposes on unmount |
| `components/graph3d/KnowledgeExplorer.tsx` | State and side panels: loading, SSE refresh, selection, the hover tooltip, the node panel, the findings list, the keyboard list, controls, legend |
| `components/graph3d/AnalyzePage.tsx` | `#/knowledge`: Member 3's standalone "analyze these documents" use, no mission |

## Why these libraries

- **Force-directed layout in 3D is the request.** `3d-force-graph` is the maintained, widely used
  library for exactly that (d3-force-3d layout, three.js rendering, orbit controls, directional
  particles on links, node objects that can be any three.js mesh).
- **The same author's `force-graph` takes the same data and accessors in 2D.** The 2D fallback is
  therefore the same code path with a different constructor, not a second implementation.
- vis.js (Member 3's choice) is 2D only. Cytoscape is 2D only. Writing a three.js scene and a
  force layout by hand is weeks of work for the same result.

## Why the vanilla libraries rather than `react-force-graph-3d`

- The plan (2026-10-03) expected a React 19 peer conflict. Checked on 2026-10-04, there is none:
  `react-force-graph-3d` 1.29.2 accepts any React (`react: *`). Compatibility is therefore *not*
  the reason; the two below are.
- The wrapper re-renders the scene from props. Highlighting on click is then a React render of
  every node. With the vanilla instance, highlight is a matter of re-setting the accessors, which
  read the current state from a ref (`live`), and the library re-evaluates them in place.
- One component owns the WebGL context, its resize observer and its destructor. Switching 2D/3D
  destroys one instance and creates the other; nothing leaks between them.

## Why the logic is outside the component

What the owner asked for, *click a node and its related sub-nodes light up*, is a graph
computation (`highlightSet`: the node's family, then a breadth-first walk over every link kind to
the chosen depth). It is tested in Vitest without a browser (19 tests in `model.test.ts`), which
a canvas cannot be. The canvas is checked by the build and by screenshots in the development log.

## Accessibility (kept from Phase 21: nothing relies on colour alone)

| Rule | How |
|---|---|
| Node kind is not colour alone | Shape: sphere = entity, cube = claim, octahedron = document, tetrahedron = finding, in 3D meshes, in 2D canvas drawing, in the legend and in the keyboard list's glyphs |
| A conflict is not red alone | Its link is labelled "conflicts: …" and carries moving particles; the claim panel lists the conflict in words |
| Motion is optional | `prefers-reduced-motion` or no WebGL starts in 2D (`initialMode`); the toggle stays available |
| Keyboard | A listbox beside the canvas mirrors the visible graph: arrow keys move the selection (which lights the graph exactly as a click does), Enter unfolds an entity, Esc clears. The canvas itself is `aria-hidden` |
| Hover information without a mouse | The selected node's side panel carries the same details as the hover pop-up |

## Consequences

- **Bundle.** three.js is large. The explorer is lazy-loaded (`React.lazy`) on `#/mission/{id}/graph`
  and `#/knowledge`, so the main bundle stays at ~260 kB (81 kB gzipped) and the explorer chunk
  (~1.5 MB, 416 kB gzipped) loads only when opened. `chunkSizeWarningLimit` is raised to 1600 kB
  in `vite.config.ts` with that reason beside it.
- **Framing is ours.** The library's `zoomToFit` framed this view far too close in testing; the
  3D camera is placed from the node positions instead (`frameAll`: centroid, farthest node,
  narrower half of the field of view). 2D still uses `zoomToFit`, which frames correctly.
- **Layout constants are tuned for sparse graphs.** A run's graph is mostly loose entities; at
  the default repulsion they drift apart and labels become unreadable once framed, so the
  many-body strength is −12 rather than −30.
- **A click restyles; it does not rebuild.** Each node's 3D object (shape plus label sprite) is
  built once; a highlight change sets opacity, glow and label visibility on the existing objects
  (`styleNode`). The first version re-ran `nodeThreeObject` on every click, rebuilding every mesh
  and label texture, and the page stopped responding under software WebGL.
- **Labels.** Entities are always labelled (3D via `three-spritetext`), and every lit node is
  labelled once something is selected; long names are cut to 28 characters (`shortLabel`), the
  full text being in the pop-up and panel.
- The frontend now has a test runner (Vitest). CI runs it from Phase 34.
- Mission Control has only a dark theme; the canvas uses its background colour.
