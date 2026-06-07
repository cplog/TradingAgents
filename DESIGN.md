---
name: TradingAgents
description: Die-cut paper, visible grain, committed warm pastel. Handmade, witty, sharp.
colors:
  paper-cream: "#faf6f0"
  paper-card: "#fffbf3"
  paper-tissue: "#f4ece0"
  paper-newsprint: "#ede4d3"
  ink: "#2a2018"
  ink-muted: "#6b5e4f"
  ink-faint: "#a89a85"
  apricot: "#e88c4d"          # committed hue, 30-60% on brand surface
  apricot-soft: "#f4b888"
  sage: "#7ba47f"              # BUY (semantic, paper-toned)
  terracotta: "#c47b5e"        # SELL (semantic, paper-toned)
  taupe: "#a89b86"             # HOLD (semantic, paper-toned)
  hairline: "rgba(42, 32, 24, 0.12)"
  shadow-warm: "rgba(120, 80, 40, 0.08)"
typography:
  display: "Fraunces"          # variable, sharp or soft by axis
  body: "Inter"
  mono: "JetBrains Mono"
  weights:
    display-regular: 400
    display-bold: 600
    body-regular: 400
    body-medium: 500
    body-semibold: 600
  scale:
    hero: "clamp(56px, 9vw, 128px)"
    h1: "44px"
    h2: "32px"
    h3: "22px"
    body: "16px"
    label: "13px"
    micro: "11px"
  line-height:
    display: 1.05
    heading: 1.18
    body: 1.55
  letter-spacing:
    display: "-0.02em"
    body: "0"
    label: "0.04em"
rounded:
  card: "14px"
  button: "10px"
  pill: "999px"
  cutout: "18px"               # the hand-cut shape used for hero panels
spacing:
  section: "72px"
  band: "40px"
  card: "24px"
  element: "12px"
  micro: "6px"
shadows:
  paper-lift: "0 2px 8px rgba(120, 80, 40, 0.06), 0 1px 2px rgba(120, 80, 40, 0.04)"
  paper-tape: "0 4px 14px rgba(120, 80, 40, 0.10)"
  paper-floating: "0 12px 32px rgba(120, 80, 40, 0.10), 0 2px 4px rgba(120, 80, 40, 0.06)"
---

# Design System: TradingAgents

## Overview

**Creative North Star: "Handmade, witty, sharp."**

A die-cut paper aesthetic with visible grain, a committed warm pastel palette, and a display serif that carries the personality. The Mailchimp lane for craft and voice, the Revolut help-center lane for warmth-under-precision. Handcraft is visible on every surface; the analysis underneath it is serious.

**Paper is a material, not decoration.** A fixed paper grammar (3 weights, 1 cutout shape, committed palette, visible grain) makes the 30th illustration feel related to the 1st. Ad-hoc paper is forbidden; the system is the point.

**Two registers share one grammar.**
- **Brand surface** (hero, story, how-it-works, sample decisions, CTA): full paper expression. Layered depth, hand-cut edges, washi-tape accents, witty copy. Apricot carries 30-60%.
- **Research interface** (embedded demo, dashboard, run page, history, screener, settings): calmer, more legible. Same paper, less layered depth, more typographic precision, denser information. Restrained palette on UI surfaces.

The transition from brand surface to research interface is a single deliberate visual move (a fold, a paper-tape strip, a torn edge across the viewport), not a generic route change.

**Color strategy.**
- **Committed pastels** on the brand surface. Apricot (`#e88c4d`) is the committed hue and carries 30-60% of hero, CTA, and accent surfaces.
- **Restrained** on the research interface. Tinted neutrals (paper-cream, paper-card, ink) plus apricot as the action accent at ≤10%.
- **Semantic BUY/HOLD/SELL** stay in the paper world: sage, taupe, terracotta. Each is reinforced by *shape*, not just hue (filled chip / outlined / filled square).
- **No `#000` or `#fff`.** Ink and paper are always tinted toward warm.

**Theme.** Light by default. The research interface is used in normal daylight on a 14-inch laptop during market hours; the brand surface is the marketing front door. Dark is not the default; if a dark surface appears (e.g., a code block in a research report), it uses a warm near-black, not pure black.

## Colors

| Token | Value | Role |
|-------|-------|------|
| Paper Cream | `#faf6f0` | Brand surface canvas, app shell background |
| Paper Card | `#fffbf3` | Cards, panels, raised surfaces |
| Paper Tissue | `#f4ece0` | Soft overlays, dividers, washi-tape tints |
| Paper Newsprint | `#ede4d3` | Faded references, sample-data backgrounds |
| Ink | `#2a2018` | Primary copy |
| Ink Muted | `#6b5e4f` | Secondary copy |
| Ink Faint | `#a89a85` | Tertiary labels, captions |
| Apricot | `#e88c4d` | Committed hue, primary CTA, brand accent |
| Apricot Soft | `#f4b888` | Hover states, decorative tints |
| Sage | `#7ba47f` | BUY semantic |
| Terracotta | `#c47b5e` | SELL semantic |
| Taupe | `#a89b86` | HOLD semantic |
| Hairline | `rgba(42,32,24,0.12)` | Borders, dividers |
| Shadow Warm | `rgba(120,80,40,0.08)` | Card lift shadows |

The legacy CSS variables (`--color-chartwell-blue`, `--surface-cloud-white`, `--color-signal-blue`, etc.) are retired. Mapping is intentionally broken — the new system uses its own tokens, and existing components that referenced the old variables are flagged for rewrite, not legacy-mapped.

## Typography

The display face does most of the personality work. The body face stays out of the way.

- **Display (Fraunces).** Variable. Use the `opsz` axis for headlines (high optical size for display, lower for caption-size). The `SOFT` axis can dial warmth up for hero copy. Weights: 400 regular, 600 bold. Letter-spacing `-0.02em` for headings. Line-height 1.05 for hero, 1.18 for headings.
- **Body (Inter).** Weights: 400, 500, 600. Line-height 1.55. Used for paragraphs, UI labels, data readouts.
- **Mono (JetBrains Mono).** Tickers, IDs, timestamps, log readouts, code. The research interface uses it for run status, elapsed time, tool-call counts.

Hierarchy through scale + weight contrast (≥1.25 ratio between steps):

| Role | Size | Weight | Notes |
|------|------|--------|-------|
| Hero | clamp(56px, 9vw, 128px) | 600 | Fraunces, leading 1.05 |
| H1 | 44px | 600 | Fraunces |
| H2 | 32px | 600 | Fraunces |
| H3 | 22px | 600 | Inter or Fraunces |
| Body | 16px | 400 | Inter |
| Label | 13px | 500 | Inter, tracking 0.04em, optional uppercase |
| Micro | 11px | 500 | Inter or JetBrains Mono, tracking 0.04em |

**Cap body line length at 65-75ch.** Story sections, analyst reports, and the embedded demo's prose all sit inside this constraint.

**No gradient text.** Emphasis via weight, size, or color, never a clipped gradient.

## Paper Grammar

The system. Every paper element on every surface draws from this grammar.

**Three paper weights:**
1. **Card stock** (`paper-card` / `#fffbf3`) — primary surface. Hero panels, embedded demo shell, run-page cards.
2. **Tissue** (`paper-tissue` / `#f4ece0`) — soft overlays, washi-tape tints, dividers, section backgrounds when a quieter break is needed.
3. **Newsprint** (`paper-newsprint` / `#ede4d3`) — faded references, sample-data cards, "draft" states, archival feel.

**One cutout shape:** rounded rectangle with hand-cut imperfection. Default radius 14px (cards), 18px (hero cutouts), 10px (buttons). The hand-cut feel comes from a 1-2 degree rotation on hero elements, not from irregular paths.

**Edges:** subtle visible grain via an SVG noise overlay (`feTurbulence` filter, opacity 0.04-0.08). Applied via the `.paper-grain` utility class. Never on text. Reduced-texture mode removes it.

**Layered depth:** drop-shadow with warm tint, not gray. Three shadow tokens:
- `paper-lift` — most cards
- `paper-tape` — washi-tape "affixed" elements
- `paper-floating` — floating panels, modals (last resort)

**Tape:** washi-tape strips at 1-3 degree rotation, 24-40px wide, low opacity (0.6-0.8), in `apricot-soft` or `paper-tissue`. Used to "affix" a card to the surface or to bridge a transition. Never load-bearing for layout.

**Hand-drawn connecting lines** (1px, `ink-muted` 0.4 opacity) for the how-it-works explainer. Optional, used sparingly.

## Components

### Brand surface

**Hero.** Single Fraunces headline (hero scale), one-line subtitle in Inter, one apricot CTA pill. No metric bar, no second column. The headline is the artifact; the CTA is the only button.

**Story.** Long-form Inter copy in 65-75ch columns. Alternating left/right alignment per section to break monotony. No bullet walls.

**How-it-works.** Three die-cut paper diagrams (Configure → Run → Decide) in a horizontal row, connected by a hand-drawn line. Each diagram is a 200-280px square paper card with one cutout illustration and one label.

**Sample decisions.** Horizontal scroll of past analysis cards, each with a torn top edge, a ticker (JetBrains Mono), a rating chip (sage/taupe/terracotta + shape), and a one-line rationale. No identical card grid; vary the torn edge direction.

**CTA section.** A single Fraunces line, one apricot button, one secondary text link. Background is `paper-tissue`, not white.

**Footer.** Quiet paper-tape strip with three text links. No link wall.

### Research interface (embedded demo + standalone)

**App shell.** Paper-cream background. Top bar in `paper-card` with a hairline border, no drop shadow. Logo (Fraunces, 600) at left, primary nav (Inter, label scale) at right.

**Sidebar nav (if used).** Paper-card surface, 1px hairline right border. Active item: apricot text on `paper-tissue` background, no side-stripe accent (forbidden). Inset icon + label.

**Cards.** `paper-card` background, hairline border, `paper-lift` shadow, 24px padding, 14px radius. Used for analyst reports, charts, history items, screener rows.

**Buttons.**
- **Primary (apricot pill):** Apricot fill, ink text, 10px radius, 12-16px vertical padding. Hover darkens to a slightly warmer apricot. Active presses by 1px.
- **Secondary:** Paper-card fill, hairline border, ink text.
- **Ghost:** No fill, no border, ink-muted text. Underline on hover.
- **Destructive:** Terracotta text on `paper-card`, hairline border. Never filled terracotta as a primary action (too aggressive for the aesthetic).

**Rating badges.** Shape + color, not color alone.
- **BUY:** filled rounded chip, sage fill, ink text.
- **HOLD:** outlined chip, hairline border, taupe text.
- **SELL:** filled square chip (slightly different radius), terracotta fill, paper-card text.

**Charts.** Warm-toned grid lines (`ink-faint` at 0.2 opacity). Semantic colors as above. Hand-drawn gridline variant (1px, slightly wavy) available for hero/data-art surfaces; standard gridlines for analytical charts. No neon, no glow.

**Inputs.** Paper-card fill, hairline border, ink text, 10px radius. Focus state: apricot border, no glow. Placeholder: ink-faint.

**Status / progress.** JetBrains Mono for elapsed time, tool-call counts, node IDs. Pending nodes: paper-tissue circle. Active: apricot circle. Complete: sage check. Failed: terracotta X.

**Modals.** Avoid as a first thought. When needed, paper-floating shadow, paper-card fill, 18px radius, max-width 560px. No backdrop blur (glassmorphism forbidden).

**Ticker chips.** Paper-tissue fill, JetBrains Mono ticker, 6px radius, optional washi-tape effect (1-2 degree rotation) when used in marketing contexts.

**Embedded demo frame.** Paper-card with a slight rotation (-1 to 1 degree), washi-tape strip at the top edge, hairline border, paper-floating shadow. Reads as "a paper demo taped onto the page."

## Decorative motifs

Recurring visual elements that show up across both registers so the brand feels coherent:

- **Washi-tape strips.** 1-3 degree rotation, semi-transparent apricot-soft or paper-tissue. Used to "affix" cards, to bridge transitions, and to mark sections in long-form copy.
- **Torn edges.** Hero panels and sample-decision cards have a 2-4px torn top or bottom edge (a subtle SVG path with rough displacement) — never on every edge.
- **Hand-cut circles.** Used for rating chips, "new" badges, and step numbers in the how-it-works explainer.
- **Paper-clipped corners.** A 12-16px paper-clip graphic in `ink-muted` at the top-right of long-form documents.
- **Fold creases.** Optional 1px line with 0.1 opacity shadow indicating a paper fold, used in transitions from brand to research interface.

## Motion

- **Decorative motion only.** Parallax, layered entrance, paper-tape slide-ins, torn-edge reveals. Never on functional UI (buttons, inputs, status).
- **Easing: ease-out-quart or ease-out-expo.** No bounce, no elastic, no spring.
- **Reduced motion.** `prefers-reduced-motion: reduce` disables all decorative motion. Functional motion (status updates) is allowed but uses static fallbacks.
- **Reduced texture.** A separate mode (toggle in user settings) flattens grain, removes washi-tape, simplifies layered depth. The interface must remain fully functional in this mode.

## Anti-patterns (enforced)

These are forbidden across both registers. If you're about to write one, rewrite the element.

- **Side-stripe borders** on cards, list items, callouts, alerts. Never intentional.
- **Gradient text** (`background-clip: text` with a gradient). Decorative, never meaningful. Use a single solid color; emphasis via weight or size.
- **Glassmorphism** as a default. Backdrop blur only when there's a real depth reason.
- **Hero-metric template** (big number, small label, supporting stats, gradient accent). The hero is a headline + CTA. Metrics go in their own section with honest framing.
- **Identical card grids.** Same-sized cards with icon + heading + text, repeated. Vary the layout per section.
- **Modal as first thought.** Inline first; modal as a last resort.
- **No em dashes in copy.** Commas, colons, semicolons, periods, parentheses. Also not `--`.
- **Decorative paper without system discipline.** Ad-hoc cutouts, illustrations that don't share a grammar, paper grain as decoration rather than as a coherent material language. The paper grammar above is the system.

## Accessibility

- **Target: WCAG 2.1 AA.** All text/background pairings verified. Apricot-on-cream is verified for AA on body labels (≥4.5:1). Hero text uses ink-on-cream, not apricot-on-cream.
- **Semantic BUY/HOLD/SELL** carry shape, label, and color. Color is reinforcement, not the signal.
- **Texture as a known concern.** Reduced-texture mode is required. Reduced-motion mode is required. Both are user-toggleable in settings and respect system preferences.
- **Decorative paper elements** get `aria-hidden="true"` so they don't pollute the screen-reader tree.
- **Keyboard.** Full brand surface and research interface are keyboard-reachable. Washi-tape and torn-edge transitions are visual; they don't gate navigation.
- **Charts.** Provide a text/data-table alternative for every chart. Tooltips announce via `aria-label`.

## Implementation

**Token files:**
- `frontend/tokens.css` — color, typography, spacing, radius, shadow tokens (the values from the frontmatter, exposed as CSS custom properties)
- `frontend/paper-texture.css` — grain overlay utility (`.paper-grain`), tape utility (`.paper-tape`), torn-edge utility (`.torn-edge`)
- `frontend/motion.css` — easing tokens, reduced-motion media queries

**Primitives (`frontend/src/index.css`):**
- `.paper-card`, `.paper-tissue`, `.paper-newsprint` — surface classes
- `.ui-btn-primary`, `.ui-btn-secondary`, `.ui-btn-ghost`, `.ui-btn-destructive`
- `.ui-rating-buy`, `.ui-rating-hold`, `.ui-rating-sell`
- `.app-shell__*` — top bar, sidebar, content area
- `.ticker-chip`, `.status-dot`

**Fonts:** loaded in `frontend/index.html` from a self-hosted variable-font subset.
- Fraunces (variable, weights 400 + 600, opsz 9-144)
- Inter (variable, weights 400 + 500 + 600)
- JetBrains Mono (variable, weights 400 + 500)

**Migration note:** the old token names (`--color-chartwell-blue`, `--surface-cloud-white`, `--color-signal-blue`, etc.) and the old `ui-panel` / `ui-btn-primary` retro-dark classes are retired. Components that referenced them are flagged for rewrite, not legacy-mapped. The new system uses new token names; the visual language is incompatible.
