/**
 * Warm paper palette for standalone HTML export.
 * Values mirror frontend/variables.css so exports match the in-app theme.
 */
export const EXPORT_TOKENS = {
  ink: "#2a2018",
  muted: "#6b5e4f",
  rule: "rgba(42, 32, 24, 0.12)",
  accent: "#e88c4d",
  surface: "#fffbf3",
  soft: "#faf6f0",
  tissue: "#f4ece0",
  warn: "#b7833b",
  ok: "#7ba47f",
  fail: "#c47b5e",
  phosphorGlow: "rgba(232, 140, 77, 0.18)",
  phosphorBorder: "rgba(232, 140, 77, 0.35)",
  dangerSurface: "rgba(196, 123, 94, 0.14)",
  dangerBorder: "rgba(196, 123, 94, 0.45)",
  sageBorder: "rgba(123, 164, 127, 0.45)",
  warnBorder: "rgba(183, 131, 59, 0.45)",
  warnSurface: "rgba(232, 140, 77, 0.08)",
  tableStripe: "rgba(244, 236, 224, 0.55)",
} as const;

/** CSS custom properties block inlined into standalone report HTML. */
export function exportCssRoot(): string {
  const t = EXPORT_TOKENS;
  return `:root {
    color-scheme: light;
    --ink: ${t.ink};
    --muted: ${t.muted};
    --rule: ${t.rule};
    --accent: ${t.accent};
    --surface: ${t.surface};
    --soft: ${t.soft};
    --warn: ${t.warn};
    --ok: ${t.ok};
    --fail: ${t.fail};
    --page-pad: clamp(16px, 4vw, 40px);
    --content-max: 1180px;
  }`;
}
