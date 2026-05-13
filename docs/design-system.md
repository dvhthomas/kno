# Kno design system

> **Scope:** visual design system for UI surfaces (web, app, embedded views).
>
> **Logo asset:** [`assets/knox-mark.svg`](../assets/knox-mark.svg)
> **Visual preview** (with swatches + rendered specimens): [`docs/design-system.html`](design-system.html)

## Color

### Source

Every color derives from a single hue. Change `--hue` to re-theme the entire system.

```css
:root {
  --hue: 290;                                          /* plum-violet — locked */

  /* primary scale */
  --p-50:  hsla(var(--hue), 32%, 96%, 1);
  --p-100: hsla(var(--hue), 34%, 88%, 1);
  --p-200: hsla(var(--hue), 38%, 78%, 1);
  --p-400: hsla(var(--hue), 42%, 58%, 1);
  --p-500: hsla(var(--hue), 46%, 48%, 1);
  --p-700: hsla(var(--hue), 52%, 30%, 1);
  --p-900: hsla(var(--hue), 58%, 14%, 1);

  /* secondary: hue + 60° → warm berry */
  --s-100: hsla(calc(var(--hue) + 60), 36%, 90%, 1);
  --s-500: hsla(calc(var(--hue) + 60), 44%, 56%, 1);
  --s-700: hsla(calc(var(--hue) + 60), 50%, 34%, 1);

  /* tertiary: hue - 60° → cool slate-blue */
  --t-100: hsla(calc(var(--hue) - 60), 30%, 90%, 1);
  --t-500: hsla(calc(var(--hue) - 60), 32%, 54%, 1);
  --t-700: hsla(calc(var(--hue) - 60), 38%, 32%, 1);

  /* neutrals & text — same hue, very low saturation */
  --bg:      hsla(var(--hue), 24%, 97%, 1);
  --surface: hsla(var(--hue), 16%, 94%, 1);
  --border:  hsla(var(--hue), 18%, 84%, 1);
  --fg:      hsla(var(--hue), 28%, 13%, 1);
  --muted:   hsla(var(--hue), 12%, 46%, 1);

  /* pure tones — tokenised so the values can be tweaked later */
  --white: #ffffff;
  --black: #111111;
}
```

### Usage rules

| Element                          | Token(s)                          | Notes                                                       |
| -------------------------------- | --------------------------------- | ----------------------------------------------------------- |
| Page background                  | `--bg`                            | Default body background.                                    |
| Card / elevated surface          | `--surface`                       | One step darker than `--bg`. No border needed.              |
| Border / divider                 | `--border`                        | 1px line on `--bg` or `--surface`.                          |
| Heading (h1, h3)                 | `--fg`                            | Always.                                                     |
| Section eyebrow (h2)             | `--muted`                         | UPPERCASE, letter-spacing 0.10em.                           |
| Body text                        | `--fg`                            | Always.                                                     |
| Muted / caption / helper         | `--muted`                         | Same hue, desaturated — feels related, not gray-from-nowhere. |
| Link (default)                   | `--p-500`                         | Always.                                                     |
| Link (hover)                     | `--p-700`                         | Always.                                                     |
| Primary button — background     | `--p-500` (hover `--p-700`)       |                                                             |
| Primary button — text           | `--p-50`                          |                                                             |
| Inline code — background        | `--surface`                       | 2px 6px padding, 4px radius.                                |
| Code block — background         | `--p-900`                         |                                                             |
| Code block — text               | `--p-100`                         |                                                             |
| Pill / badge — primary          | bg `--p-100`, text `--p-700`      |                                                             |
| Pill / badge — warm accent      | bg `--s-100`, text `--s-700`      | Success, "yes" states.                                      |
| Pill / badge — cool accent      | bg `--t-100`, text `--t-700`      | Info, tags.                                                 |
| Strong / inline emphasis         | `--p-700`                         | Color only; font weight stays inherited.                    |

### Why hue 290°

Plum-violet steers Knox away from the orange-fox cliché (GitLab, Firefox, Anthropic) and leans into a "knowledge / thoughtful" tone. The ±60° rotations on either side give a balanced triadic accent set without clashing.

## Typography

### Stacks

| Role      | Variable        | Stack                                                                                    |
| --------- | --------------- | ---------------------------------------------------------------------------------------- |
| Headings  | `--head-font`   | `"Rubik", sans-serif` — Google Fonts, weight 600                                         |
| Body      | `--body-font`   | `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`    |
| Monospace | `--mono-font`   | `ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace`                    |

Font loading (HTML `<head>`):

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Rubik:wght@400;600&display=swap" rel="stylesheet">
```

### Type scale

| Role                          | Font        | Size    | Line-height | Weight | Tracking  | Color     |
| ----------------------------- | ----------- | ------- | ----------- | ------ | --------- | --------- |
| H1 — page title              | Rubik       | 36px    | 1.15        | 600    | −0.02em   | `--fg`    |
| H2 — section eyebrow (UPPER) | Rubik       | 13px    | 1.4         | 600    | 0.10em    | `--muted` |
| H3 — subsection              | Rubik       | 17px    | 1.3         | 600    | −0.005em  | `--fg`    |
| Body                          | System sans | 16px    | 1.6         | 400    | 0         | `--fg`    |
| Lede / intro                  | System sans | 17px    | 1.55        | 400    | 0         | `--muted` |
| Caption / helper              | System sans | 14px    | 1.5         | 400    | 0         | `--muted` |
| Inline code                   | Monospace   | 13.5px  | inherit     | 400    | 0         | `--fg`    |
| Label / chip                  | Monospace   | 11px    | 1.4         | 400    | 0         | `--muted` |

## Logo — Knox the Fox

### Asset

- **Path:** [`assets/knox-mark.svg`](../assets/knox-mark.svg)
- **ViewBox:** `0 0 200 200` (1:1)
- **Vars** (set both as a pair per surface):
  - `--knox-fur` — silhouette fill
  - `--knox-ink` — outline, nose, eye features

### Color combos

Knox uses exactly two colors. Pick one of the named combos below — never mix custom values.

| Combo (CSS class)             | `--knox-fur`     | `--knox-ink`      | Allowed surfaces                                  |
| ----------------------------- | ---------------- | ----------------- | ------------------------------------------------- |
| `.knox-classic` *(primary)*  | `var(--white)`   | `var(--p-900)`    | `--p-50`, `--p-100`, `--p-200`, `--p-500`         |
| `.knox-inverse`               | `var(--p-50)`    | `var(--p-700)`    | `--p-900`                                         |
| `.knox-mono`                  | `var(--white)`   | `var(--black)`    | `var(--white)`, print, monochrome contexts        |
| `.knox-berry`                 | `var(--white)`   | `var(--s-700)`    | `--s-100` (warm-accent contexts)                  |
| `.knox-slate`                 | `var(--white)`   | `var(--t-700)`    | `--t-100` (cool-accent contexts)                  |

```css
.knox-classic { --knox-fur: var(--white); --knox-ink: var(--p-900); }
.knox-inverse { --knox-fur: var(--p-50);  --knox-ink: var(--p-700); }
.knox-mono    { --knox-fur: var(--white); --knox-ink: var(--black); }
.knox-berry   { --knox-fur: var(--white); --knox-ink: var(--s-700); }
.knox-slate   { --knox-fur: var(--white); --knox-ink: var(--t-700); }
```

### Eye states

Set `data-state` on the SVG root element to communicate the agent's state.

| State (`data-state`)  | Visual                                                  | Use when…                                                 |
| --------------------- | ------------------------------------------------------- | --------------------------------------------------------- |
| `alert` *(default)*   | Eyes open, attentive, pupils glancing up.               | Idle and ready for input.                                 |
| `waiting`             | Eyes closed in an upward content arch (∩ ∩).            | Peaceful pause inside a single user turn.                 |
| `sleep`               | Eyes closed in a downward crescent (∪ ∪).               | Long inactivity / low-power state. Agent paused.          |
| `think`               | Eyes squeezed shut, chevrons pointing inward (`> <`).   | Active processing. Knox is working on a response.         |
| `surprise`            | Wide hand-drawn eyes with small pupils.                 | Error, unexpected event, attention required.              |

If `data-state` is absent, the SVG renders as `alert`.

### Logo do / don't

| Do                                                                                | Don't                                                                                                 |
| --------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Pair `--knox-fur` and `--knox-ink` from the listed combos.                        | Mix colors from outside the primary / secondary / tertiary palette.                                   |
| Place Knox on a surface listed for the chosen combo.                              | Place `.knox-classic` on `--p-900` (ink and surface match — Knox's features disappear).               |
| Keep stroke widths as defined in the SVG.                                         | Add drop shadows, gradients, or extra colors.                                                         |
| Toggle `data-state` to communicate agent state.                                   | Animate or transition the fox itself — state changes are discrete.                                    |

## Conventions

- **One hue knob.** All color tokens derive from `--hue`. Edit one number, the rest follow.
- **HSLA over hex.** Pure tones (`--white`, `--black`) are the only hex values; everything else is HSLA with `calc()` on the hue.
- **Knox is always two-tone.** One fur, one ink, picked from a named combo. He is never colorful or gradient.
