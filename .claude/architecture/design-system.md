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
