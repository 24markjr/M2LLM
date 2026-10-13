# The design system (Phase U2)

Code: `frontend/src/theme/` (tokens, theme, provider), `frontend/src/ui/` (icons, components,
`ui.css`), `frontend/src/components/SettingsMenu.tsx`.

## Themes (U2a)

**Light is the default.** Dark is chosen in **Settings** (the gear at the right of the header) and
remembered per browser under `localStorage["jarvis.theme"]`. When storage is refused (a private
window, blocked site data) the choice still applies for the visit and light returns next time.

The theme is a `data-theme` attribute on `<html>`. `index.html` sets it before anything paints, and
`main.tsx` again before React renders, so a dark choice never flashes light.

## Tokens

`theme/tokens.css` is the only place colours, type sizes, spacing, radii and shadows are defined.
Components use the semantic names:

| Group | Tokens |
|---|---|
| Surfaces | `--surface-page`, `--surface`, `--surface-raised`, `--surface-sunken`, `--surface-hover`, `--border`, `--border-strong` |
| Text | `--text`, `--text-muted`, `--text-faint`, `--text-on-accent` |
| Brand | `--accent`, `--accent-hover`, `--accent-soft`, `--focus-ring` |
| Meaning | `--verified`, `--inferred`, `--unsupported`, `--unknown`, `--sensitive`, each with a `-soft` background |
| Shape | `--radius-sm`, `--radius`, `--radius-lg`, `--shadow-sm`, `--shadow`, `--shadow-lg` |
| Type | `--sans`, `--mono`, `--text-xs` ... `--text-2xl` |
| Space | `--space-1` ... `--space-8` (4 px steps), `--gutter` (16 px, 12 px on phones) |

**Fonts are system fonts** (Segoe UI Variable on Windows, the platform UI font elsewhere, Cascadia
Mono for evidence lines). No web font is loaded: the console must work offline and air-gapped.

**Meaning never rests on colour alone**: every status shown in a meaning colour also carries a glyph
and a word, as the console always required.

**The names used before U2** (`--bg`, `--panel`, `--line`, `--text-dim`, `--ok`, `--warn`,
`--bad`...) are kept as aliases of the tokens, so every existing page follows the theme without being
rewritten; the pages are replaced one by one from U3. Hard-coded tints in `styles.css` became
`color-mix()` of the tokens, and the primary button now uses `--accent` with `--text-on-accent`
(it was white text on a pale background in light).

The 3D graph keeps its own dark canvas in both themes for now, like an image viewer; U6 themes it.

## Components (U2b)

`frontend/src/ui/components.tsx`, styled by `ui/components.css`; icons in `ui/icons.tsx` (inline SVG,
stroke in the text colour). Pure logic is separate and tested: `status.ts`, `toast.ts`, `tabs.ts`.

| Component | What it is for |
|---|---|
| `Button` | `primary`, `secondary`, `ghost`, `danger`; `sm`/`md`; `icon`; `busy` (spinner, disabled) |
| `TextInput`, `TextArea`, `Select` | Labelled fields with a hint or an error, wired with `aria-describedby` / `aria-invalid` |
| `Card` | Title, meta, actions and body; `flush` for a table edge to edge |
| `Badge`, `StatusBadge` | Neutral and meaning tones; a status badge always shows glyph and word |
| `StatusMark` | **The status underline**: verified (solid), inferred (dashed), not established (wavy), unknown (dotted), each in its colour, the word read to screen readers and shown on hover |
| `DataTable` | Columns with render functions; cells wrap so the page never scrolls sideways; below 720 px each row becomes a stacked, labelled card |
| `Tabs`, `TabPanel` | The WAI-ARIA tabs pattern: arrow keys, Home, End |
| `Dialog` | The native `<dialog>`: focus trapped, Escape closes |
| `ConfirmDialog` | Before anything that cannot be undone; `typeToConfirm` enables the button only once a word is typed (deleting everything) |
| `Notice` | Inline info, success, warning, error |
| `ToastProvider`, `useToast` | Short confirmations; at most four; an error stays until dismissed |

`statusOf` maps the API's `VerificationStatus` to a mark: SUPPORTED -> verified, PARTIALLY_SUPPORTED ->
inferred, UNSUPPORTED and CONTRADICTED -> not established, INCONCLUSIVE or none -> unknown.

**`#/design`** shows every token and component in the current theme, with a switch between themes.
It is linked from Settings, and is where a change to the system is reviewed.
