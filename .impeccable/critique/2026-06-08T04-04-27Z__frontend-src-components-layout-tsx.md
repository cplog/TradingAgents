---
target: research interface
total_score: 30
p0_count: 0
p1_count: 1
timestamp: 2026-06-08T04-04-27Z
slug: frontend-src-components-layout-tsx
---
# Critique: TradingAgents Research Interface

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Pipeline dots are abstract (4 static states: Queued/Pipeline/Report/Done) with no per-agent granularity. Real progress lives in the terminal log, which users must toggle. |
| 2 | Match Between System and Real World | 4 | Domain language is precise (ticker, debate rounds, analysts). "Paper brief" status line supports the metaphor. |
| 3 | User Control and Freedom | 4 | Breadcrumbs on every page, swap/clear on compare, cancelable jobs, re-run paths. Good escape hatches throughout. |
| 4 | Consistency and Standards | 2 | Three button naming conventions coexist (`ui-btn-primary`, `ui-btn--primary` BEM, `Pressable`). Form field patterns vary. `font-mono` is overapplied to every UI label, eroding hierarchy. |
| 5 | Error Prevention | 3 | Delete has `window.confirm`. Double-submit guarded. Ticker validation is absent on Dashboard — user types anything, gets API error downstream. |
| 6 | Recognition Rather Than Recall | 3 | Truncated run IDs are unmemorable. Compare dock requires remembering which run is A vs B. |
| 7 | Flexibility and Efficiency of Use | 4 | URL-synced filters, batch re-run, bulk delete, retry-all-failed, view mode toggle. Skip-to-content link present. |
| 8 | Aesthetic and Minimalist Design | 2 | HistoryPage toolbar has 7+ interactive controls on load. Dashboard setup shows 7+ fields before Advanced. Compare dock adds 4-5 more. Not minimalist. |
| 9 | Error Recovery | 3 | Inline error messages with `role="alert"`. "Checking API…" on Dashboard could stall indefinitely with no timeout feedback. |
| 10 | Help and Documentation | 2 | Column guide and complexityHint are good micro-help. No tooltip infrastructure, no empty-state guidance beyond "Start analysis," LLM picker has no inline explanation. |
| **Total** | | **30/40** | **Solid product — needs tightening** |

## Anti-Patterns Verdict

**LOW SLOP. This is clearly human-crafted.**

The strongest evidence is the genuine design personality: the SVG `feTurbulence` grain overlay, the slow ambient gradient drift, the rotating ring, the paper-tape visual language. These are committed aesthetic choices, not training-data defaults.

**LLM assessment**: No glassmorphism, no gradient text, no side-stripe borders, no hero-metric template, no modal-first thinking, no identical card grids. The brand register references (Fraunces display, warm-paper palette, apricot accent) are coherent and deliberate.

**Deterministic scan** (`npx impeccable detect --json frontend/src/`):
- **Em-dash overuse** (warning): `reportExport.ts` — 119 em-dashes in body text. These are in report generation output, not UI copy, so the impact is confined to exported reports, not the interface itself.
- **Numbered section markers** (advisory): `reportExport.test.ts` — `Sequence: 04, 05, 06` in test fixtures. Low severity.

The automated scan found no UI-specific anti-patterns in the interface components themselves. The findings are in utility/export code, not the visual surface.

**Design system drift**: The implemented CSS tokens (`cloud-white`, `stone-border`, `chartwell-blue` at `#3ba6f1`) diverge from the DESIGN.md spec (`paper-cream #faf6f0`, `ink-muted`, `apricot #e88c4d`). The blue `chartwell-blue` (#3ba6f1) is the most visible drift — a cool blue that sits uneasily against the warm-paper vision. This suggests the brand doc was written after some components were built, and the CSS variables haven't caught up.

## Overall Impression

This is an idiosyncratic, personality-rich research interface that feels genuinely crafted. The ambient texture layer (grain, drift, speckle, ring) is the best I've seen in a data app — it commits to the paper-craft metaphor without being distracting. The compare mode and progressive disclosure architecture show real UX maturity.

The main opportunity is **consolidation under the design vision**. The aesthetic is warm and handcrafted, but the implementation tokens are a mix of old (chartwell-blue, cloud-white) and new (apricot, paper-cream). The type hierarchy is flattened by mono-font overuse. The Dashboard and History pages carry too much upfront complexity for their default state. Tightening these would elevate a good product to a great one.

## What's Working

1. **Ambient texture layer** (Layout.tsx:178-186, index.css:54-62). The SVG `feTurbulence` noise, gradient drift, speckle crawl, and rotating ring are genuinely tasteful. They commit to the paper-craft metaphor without being distracting. The best ambient texture implementation in a data app.

2. **Compare mode UX.** The dock pattern (dropdowns, swap, clear, AnimatePresence transitions, dimensions radar charts per side) makes a complex comparison task feel playful and forgiving. The motion adds appropriate ceremony.

3. **Progressive disclosure architecture.** "Advanced" panel on Dashboard, "More filters" and "Column guide" details on HistoryPage — all use `<details>` to reveal complexity only when needed. The `complexityHint` function is exactly the kind of translation users need.

## Priority Issues

### [P1] Mono font overuse erodes typographic hierarchy

**What**: `font-mono` is applied to form labels, button text, filter headings, table headers, stat-card labels, status badges, pipeline labels, compare controls, sort controls, view toggles, and filter fields. Roughly 40+ CSS rules use `var(--font-mono)` in index.css.

**Why it matters**: When mono becomes the default for everything below heading level, the hierarchy collapses. Mono has more visual weight than Inter body text, so labels compete with data. The brand spec says JetBrains Mono is for code — using it for all UI labels breaks the mental model.

**Fix**: Restrict `font-mono` to data values, code blocks, and terminal output. Use Inter for form labels, navigation, and table headers. Add a `--font-ui: Inter` token and apply it across UI chrome.

### [P2] Dashboard setup panel is overwhelming

**What**: DashboardPage.tsx:202-317 — the Setup panel shows Ticker (input), Date (input), LLM Picker (3 controls), Output Language (input), 8 Analyst checkboxes, Report Format (select), plus Advanced section with Temperature + Debate + Risk. That's 7 primary controls + 8 checkboxes at the main decision point.

**Why it matters**: Analysis submission is the primary user task and the default landing page. New users face a wall of configuration before they can execute. This triggers pre-task anxiety and abandonment.

**Fix**: Move LLM Picker into Advanced. Make Language a hidden preference. Default analysts to "all" without exposing the full list. Primary form should show: Ticker, Date, [Submit]. The detector also flags this as an advisory — no specific anti-pattern, but the cognitive load assessment found it exceeds the 4-item rule of thumb at the primary decision point. Suggested command: `impeccable harden` or `impeccable distill`.

### [P3] Pipeline progress visualization is too abstract

**What**: DashboardPage.tsx:348-356 renders 4 static dots (Queued → Pipeline → Report → Done) that never change state during execution. The `pipelineDotClass()` function always returns `"pipeline-dot pipeline-dot--todo"` — completely decorative. Real progress lives in the terminal log, which is developer-oriented.

**Why it matters**: The execution phase is where users experience the greatest anxiety. Abstract dots provide no ETA and no sense of "which analyst is currently thinking." The terminal log is a raw dump.

**Fix**: Remove the 4-dot pipeline and show live status text ("Market analyst is reviewing AAPL fundamentals…") or surface the most recent terminal message as a cleaned-up status line. Suggested command: `impeccable animate`.

### [P4] HistoryPage filter bar is overwhelming

**What**: HistoryPage.tsx:717-788 — Ticker, From, To, Sort dropdown, view toggle (2 buttons), refresh, "More filters," "Column guide" — all in a flat flex-wrap layout. Plus toolbar with run count, badges, retry, bulk actions, and compare dock. ~15 interactive regions on a single browsing page.

**Why it matters**: Users come here to find past runs. The filter density means visually parsing 15+ elements before reaching data. Flat layout with no visual priority makes every control compete equally.

**Fix**: Merge date range into a single input pair. Move sort into the table header. Make compare dock a button that reveals the dock — not always visible. Suggested command: `impeccable distill`.

### [P5] Inconsistent button vocabulary

**What**: Three button patterns coexist: `ui-btn-primary` / `ui-btn-secondary` / `ui-btn-danger` / `ui-btn-ghost` (CSS), `ui-btn ui-btn--primary` / `ui-btn--ghost` / `ui-btn--danger` (BEM), and `Pressable` component (motion.button wrapper).

**Why it matters**: Developers will mix patterns, leading to visual drift. `Pressable` adds scale animation but only works with `motion.button` — it won't be used with `ui-btn-ghost` variants since those use a different class structure.

**Fix**: Consolidate on one pattern. Keep `Pressable` as the base with a `variant` prop. Remove standalone CSS button classes. Suggested command: `impeccable craft`.

## Minor Observations

- **HistoryStatsPage.tsx:126**: Inline `style={{ fontSize: "var(--text-title)" }}` — CSS variable in inline style works but is unusual. Prefer a CSS class.
- **TopicCard.tsx:33**: "Pinned" vs "Pin" — inconsistent capitalization on the label.
- **HistoryPage.tsx:130**: `mergeFilters` has `trigger: overnightOnly ? "overnight" : undefined` but the UI checkbox says "Overnight / scan triggers only" — the control label and filter name drift.
- **RunDetailPage.tsx:229**: Extra space before `content-entrance` in className.
- **Design token proliferation**: The tokens.json has 23 typography steps (xs through sm-18 through 5xl) — 15 of them are 12-14px Inter variants. This suggests auto-export without manual rationalization.
- **Em-dash overuse in report export** (`reportExport.ts`): 119 em-dashes in body copy. The detector flagged this — while it's in export output, it would affect reader perception if reports are shared externally.

## Questions to Consider

1. **What if the Dashboard showed nothing but a ticker input and a big "Analyze" button?** Every other setting would default and live behind "Customize." Would anyone miss the upfront configuration wall?

2. **What if the pipeline showed "Market analyst is reviewing AAPL fundamentals…" instead of 4 abstract dots?** Would real-time agent-name + status reduce execution anxiety more than any progress visualization could?

3. **How far can the paper metaphor be pushed?** The current implementation is "charming SaaS" but the brand aspiration ("die-cut paper, handmade, witty, sharp") is farther out. Printed-research-note aesthetics, handwritten annotations, paper-clipped sections — would finance users love it or reject it?
