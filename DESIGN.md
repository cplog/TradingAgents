---
name: TradingAgents Command Center
description: Operational research interface for running, monitoring, and reviewing multi-agent trading analyses.
colors:
  signal-blue: "#3ba6f1"
  signal-blue-tint: "#c1e1f7"
  canvas-fog: "#fafaf9"
  cloud-white: "#ffffff"
  slate-text: "#0c0a09"
  ash-gray: "#78716c"
  steel-gray: "#a8a29e"
  stone-border: "#e5e7eb"
  ghost-ink: "#1c1917"
  platinum-outline: "#d6d3d1"
typography:
  display:
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "52px"
    fontWeight: 600
    lineHeight: 1
  headline:
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "32px"
    fontWeight: 600
    lineHeight: 1.12
  title:
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "20px"
    fontWeight: 600
    lineHeight: 1.2
  body:
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "12px"
    fontWeight: 500
    lineHeight: 1.5
    letterSpacing: "0.048px"
rounded:
  sm: "4px"
  md: "10px"
  lg: "16px"
  pill: "9999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  xxl: "32px"
  section: "48px"
components:
  button-primary:
    backgroundColor: "{colors.signal-blue}"
    textColor: "{colors.cloud-white}"
    typography: "{typography.body}"
    rounded: "{rounded.pill}"
    padding: "12px 16px"
  button-primary-hover:
    backgroundColor: "{colors.signal-blue-tint}"
    textColor: "{colors.slate-text}"
    typography: "{typography.body}"
    rounded: "{rounded.pill}"
    padding: "12px 16px"
  button-ghost:
    backgroundColor: "{colors.cloud-white}"
    textColor: "{colors.slate-text}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
  input-default:
    backgroundColor: "{colors.cloud-white}"
    textColor: "{colors.slate-text}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
  nav-item-active:
    backgroundColor: "{colors.signal-blue-tint}"
    textColor: "{colors.signal-blue}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
  card-surface:
    backgroundColor: "{colors.cloud-white}"
    textColor: "{colors.slate-text}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "24px"
---

# Design System: TradingAgents Command Center

## Overview

**Creative North Star: "The Research Mission Control"**

This system is an analyst companion, approachable and professional, built to keep users oriented through a dense decision workflow. The interface should always answer three questions quickly: what state the system is in, what evidence is available, and what action is next.

Visual language prioritizes stable structure over decorative novelty. Surfaces stay neutral and readable, accents are reserved for action and status, and interaction patterns repeat consistently across dashboard, history, screener, and system pages.

The system explicitly rejects Generic glossy SaaS marketing aesthetics, Neon trading-terminal visuals, Dense enterprise backoffice complexity, and Playful consumer-app styling.

**Key Characteristics:**
- Stable app shell with predictable navigation and page rhythm.
- Neutral-first surfaces with one signal accent for actions and active states.
- Dense but readable information layout, with progressive disclosure for advanced controls.
- Motion used for feedback and transitions, not choreography.

## Colors

The palette is hybrid by design, plain operational neutrals with one named domain accent.

### Primary
- **Signal Blue** (`#3ba6f1`): Primary action, active navigation state, and interactive links.

### Secondary
- **Signal Mist** (`#c1e1f7`): Selected backgrounds, active tab fills, and low-emphasis action context.

### Neutral
- **Canvas Fog** (`#fafaf9`): Application canvas and subtle content wells.
- **Cloud White** (`#ffffff`): Primary card and panel surfaces.
- **Slate Text** (`#0c0a09`): Primary text for headings and body content.
- **Ash Gray** (`#78716c`): Secondary text and explanatory copy.
- **Steel Gray** (`#a8a29e`): Tertiary labels and inactive metadata.
- **Stone Border** (`#e5e7eb`): Dividers, field outlines, and card borders.
- **Platinum Outline** (`#d6d3d1`): Disabled states and quiet separators.
- **Ghost Ink** (`#1c1917`): Inverse surfaces, dark badges, and console treatment.

**The Single Signal Rule.** Signal Blue is the only saturated accent in standard screens. If another saturated color appears, it must represent state semantics such as error or success, not decoration.

## Typography

**Display Font:** Inter (`Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`)
**Body Font:** Inter (`Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`)
**Label/Mono Font:** UI monospace (`ui-monospace, "Cascadia Code", monospace`) for IDs, timestamps, and logs.

**Character:** Clear and contemporary, tuned for rapid scanning and operational confidence rather than editorial flourish.

### Hierarchy
- **Display** (weight `600`, size `52px`, line-height `1`): Reserved for rare hero-scale callouts.
- **Headline** (weight `600`, size `32px`, line-height `1.12`): Page-level headings and major section titles.
- **Title** (weight `600`, size `20px`, line-height `1.2`): Card headers and high-value section labels.
- **Body** (weight `400`, size `16px`, line-height `1.5`): Default text and explanatory content.
- **Label** (weight `500`, size `12px`, line-height `1.5`, letter-spacing `0.048px`): Form labels, metadata, and helper text.

**The Scan-First Rule.** Typography must support scanning before reading. If body text and metadata compete for attention, reduce metadata contrast first.

## Elevation

Depth is tonal-first. Most hierarchy comes from surface color and borders, with shadows used as secondary reinforcement on cards and major containers.

### Shadow Vocabulary
- **Subtle Surface** (`0px 1px 2px 0px rgba(0, 0, 0, 0.05)`): Default card and panel lift.
- **Section Lift** (`0px 4px 16px 0px rgba(0, 0, 0, 0.05)`): Prominent report sections and high-importance containers.
- **Medium Utility** (`0px 4px 6px -1px rgba(0, 0, 0, 0.1), 0px 2px 4px -2px rgba(0, 0, 0, 0.1)`): Utility overlays and compact raised elements.

**The Tonal First Rule.** Choose background and border contrast before adding shadow. If depth still feels ambiguous after tonal correction, then add the lightest shadow that solves it.

## Components

Component language is approachable and professional, with familiar interaction patterns and low-friction defaults.

### Buttons
- **Shape:** Pill or compact rounded depending on role (`9999px` for primary actions, `4px` for utility actions).
- **Primary:** Signal Blue background (`#3ba6f1`) with white text, medium weight, generous touch target.
- **Hover / Focus:** Hover lightens toward Signal Mist context or increases contrast via border and text weight; focus uses visible blue outline.
- **Secondary / Ghost:** White or fog surfaces with border (`#e5e7eb`) and slate text for lower-priority actions.

### Cards / Containers
- **Corner Style:** Soft rounded corners (`10px` standard, `16px` for major feature sections).
- **Background:** Cloud White for primary content and Canvas Fog for nested contextual areas.
- **Shadow Strategy:** Subtle Surface by default, Section Lift on key report blocks.
- **Border:** Stone Border (`#e5e7eb`) is the default containment cue.
- **Internal Padding:** Uses `24px` card padding with `16px` internal spacing rhythm.

### Inputs / Fields
- **Style:** White background, thin neutral border (`#e5e7eb`), compact rounded corners (`4px`).
- **Focus:** Blue focus-visible outline with offset for keyboard clarity.
- **Error / Disabled:** Error uses explicit semantic color, disabled moves to Platinum Outline with reduced text contrast.

### Navigation
- **Style:** Left rail with neutral text and active state filled by Signal Mist.
- **Typography:** Body weight with stronger emphasis on active entries.
- **States:** Default neutral, hover subtle tonal shift, active uses blue text on tinted background.
- **Mobile treatment:** Sidebar collapses into top-first flow at narrow widths, preserving task order.

## Do's and Don'ts

### Do:
- **Do** keep primary pages in neutral surfaces (`#fafaf9`, `#ffffff`) with Signal Blue (`#3ba6f1`) reserved for action and state.
- **Do** maintain consistent control geometry (`4px`, `10px`, `16px`, `9999px`) instead of per-screen custom radii.
- **Do** use progressive disclosure for advanced controls, keep essentials visible first.
- **Do** keep run status, progress, and failure context visible near the active workflow.

### Don't:
- **Don't** use Generic glossy SaaS marketing aesthetics that prioritize decoration over utility.
- **Don't** use Neon trading-terminal visuals that increase urgency and fatigue.
- **Don't** use Dense enterprise backoffice complexity with overloaded controls and jargon-heavy labels.
- **Don't** use Playful consumer-app styling that weakens financial-research credibility.
- **Don't** use gradient text, heavy glassmorphism, or side-stripe accent borders as decorative shortcuts.
