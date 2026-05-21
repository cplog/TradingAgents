---
name: TradingAgents Command Center
description: Retro digital command center for multi-agent trading research (Refero-inspired).
colors:
  deep-space: "#0a0a0a"
  shadow: "#161616"
  phosphor: "#78f0a8"
  phosphor-glow: "rgba(120, 240, 168, 0.14)"
  slate-text: "#ececec"
  ash-gray: "#9a9a9a"
  stone-border: "#2c2c2c"
typography:
  body: "IBM Plex Sans"
  display: "JetBrains Mono"
  brand: "Space Grotesk"
rounded:
  sm: "2px"
  md: "4px"
  lg: "6px"
spacing:
  section: "40px"
  card: "20px"
  element: "10px"
---

# Design System: TradingAgents Command Center

## Overview

**Creative North Star: "Retro Digital Mission Control"**

Inspired by [Refero Styles — retro digital](https://styles.refero.design/?q=retro+digital) references (especially [Analogue](https://styles.refero.design/style/f68dd3d8-e8fa-4d2c-8c59-28aba06c9d8a): dark command center, crisp type, phosphor accent). The UI should feel like a serious research terminal: high contrast, grid discipline, monospace readouts, minimal decoration.

**Key characteristics:**
- Dark canvas with elevated panels (`#0a0a0a` / `#161616`)
- Phosphor green accent (`#78f0a8`) for actions, links, active nav, and data readouts
- IBM Plex Sans body, JetBrains Mono for logs/IDs/tickers, Space Grotesk for section titles
- Sharp corners (2–4px), hairline borders, subtle grid + scanline atmosphere
- Motion for route transitions and press feedback only

**Rejected (still):** glossy SaaS marketing, rainbow gradients, glassmorphism defaults, playful consumer chrome.

## Colors

| Token | Value | Role |
|-------|-------|------|
| Deep Space | `#0a0a0a` | App canvas |
| Shadow | `#161616` | Cards, sidebar, inputs |
| Phosphor | `#78f0a8` | Primary accent, links, active states |
| Phosphor Glow | `rgba(120, 240, 168, 0.14)` | Selected nav, table headers, blockquotes |
| Slate Text | `#ececec` | Primary copy |
| Ash | `#9a9a9a` | Secondary copy |
| Stone Border | `#2c2c2c` | Dividers and outlines |

Legacy CSS variables (`--color-chartwell-blue`, `--surface-cloud-white`, etc.) map to these roles so existing screens inherit the theme without per-file rewrites.

## Typography

- **Body:** IBM Plex Sans, 16px / 1.5
- **Labels & metadata:** JetBrains Mono, 11px, uppercase tracking
- **Display readouts:** JetBrains Mono, large size, phosphor color
- **Section titles:** Space Grotesk, semibold, tight tracking

## Components

### Navigation
Left rail on elevated surface. Active item: phosphor text on glow background, no side-stripe accents.

### Buttons
Uppercase mono labels, 4px radius, phosphor border on dark fill. Hover adds soft glow.

### Cards
`ui-panel` class: shadow surface, 1px border, 20px padding, 4px radius.

### Markdown / reports
Tables use phosphor-tinted headers; code blocks use deep space background with phosphor text.

## Implementation

Tokens live in `frontend/variables.css` and `frontend/theme.css`. Global primitives in `frontend/src/index.css` (`.ui-panel`, `.ui-btn-primary`, `.app-shell__*`). Fonts loaded in `frontend/index.html`.
