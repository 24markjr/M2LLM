# The application shell (Phase U3)

Code: `frontend/src/shell/` - `Shell.tsx` (layout, Ctrl+K, drawer), `Sidebar.tsx`, `TopBar.tsx`,
`CommandPalette.tsx`, `routes.ts` (routing, sections, trail, case groups), `palette.ts`,
`shell.css`. `App.tsx` now only chooses the page.

## Layout

```
+-------------+------------------------------------------------+
| JARVIS   [] | Cases > CASE-2026-00010        [Search Ctrl K] (moon) (gear)
| [+ New investigation]                                         |
|  Search  Ctrl K |                                             |
|  Pinned      |                 the page                       |
|  Today       |          (max 1200 px, centred)                |
|  Previous 7 days                                              |
|  Earlier     |                                                |
|  All cases   |                                                |
|-------------|                                                |
|  Library    |                                                |
|  Insights   |                                                |
|  Activity   |                                                |
|  * qwen3:4b |                                                |
+-------------+------------------------------------------------+
```

- **Sidebar** (272 px): New investigation; Search (Ctrl+K); cases grouped Pinned / Today / Previous
  7 days / Earlier, each with a menu: **Pin/Unpin**, **Rename** (dialog), **Delete** (confirmation
  that says what goes and what is kept, then `DELETE /cases/{id}`); a dot on a case with a running
  investigation; at the foot Library, Insights, Activity and the engine's state (model, a coloured
  dot: answering, not answering, unreachable). It can be collapsed to a 64 px rail of icons,
  remembered per browser (`jarvis.sidebar`).
- **Top bar** (56 px): the trail ("Library > Evidence > EV-000031"), whose earlier parts are links;
  search; a light/dark switch; Settings.
- **Below 1024 px** the sidebar is a drawer opened from the top bar's menu button and closed by
  choosing a page, Escape, or tapping outside it.
- When the engine cannot be reached, one banner under the top bar says how to start it.
- A "Skip to content" link is the first thing a keyboard reaches.

The sidebar reloads its cases when any page announces a change (`casesChanged()`, a window event):
opening a case, changing its status or severity, pinning, renaming, deleting.

## Pages that did the same thing are one place now

| Sidebar | Tabs | Old addresses (still work) |
|---|---|---|
| Cases | - | `#/`, `#/case/{id}`, `#/missions` (All investigations, linked from Cases) |
| New investigation | - | `#/new`, `#/knowledge` (quick analysis; becomes a mode of the composer in U4) |
| **Library** | Evidence, Documents | `#/evidence`, `#/evidence/{id}`, `#/documents`, `#/library` |
| **Insights** | Quality, Memory, Recordings | `#/evaluation`, `#/memory`, `#/replay`, `#/insights` |
| **Activity** | - | `#/audit`, `#/activity` |

Every old address opens inside its merged page, on the right tab, so the many links between pages
keep working without redirects. Each tab is an address, so the back button works.

## Search (Ctrl+K)

The places above, filtered by the words typed, then cases from `GET /cases?q=` (id, title,
description, or a question asked in the case), debounced. Arrow keys move, Enter opens.

## Verified

Unit tests for routing, sections, trail and grouping. Checked once in headless Chrome against the
built app and a temporary API on port 8010 (the user's 8000 and 5173 untouched): the cases page and
Insights at 1440 px, Library at 800 px (drawer). That check found `overflow-wrap: anywhere` (U2c)
breaking short words letter by letter in narrow columns; it is now `break-word`, and a table wider
than its card scrolls inside the card, never the page.
