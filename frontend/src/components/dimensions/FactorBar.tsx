export type Tier = "red" | "orange" | "amber" | "lime" | "green";

export function colorTier(score: number): Tier {
  if (score < 20) return "red";
  if (score < 40) return "orange";
  if (score < 60) return "amber";
  if (score < 80) return "lime";
  return "green";
}

const TIER_COLORS: Record<Tier, string> = {
  red: "var(--color-danger)",
  orange: "var(--color-warning)",
  amber: "var(--color-amber-readout)",
  lime: "var(--color-phosphor-dim)",
  green: "var(--color-phosphor)",
};

const TIER_ICONS: Record<Tier, string> = {
  red: "▼▼",
  orange: "▼",
  amber: "◆",
  lime: "▲",
  green: "▲▲",
};

export interface FactorBarProps {
  label: string;
  score: number | null;
  width?: number;
}

import { memo } from "react";
import { motion } from "motion/react";

export const FactorBar = memo(function FactorBar({ label, score, width = 120 }: FactorBarProps) {
  if (score == null) {
    return (
      <div className="factor-bar">
        <span className="factor-bar__label">{label}</span>
        <span className="factor-bar__empty">—</span>
      </div>
    );
  }
  const tier = colorTier(score);
  const pct = Math.max(0, Math.min(100, score));
  return (
    <div className="factor-bar">
      <span className="factor-bar__label">{label}</span>
      <div className="factor-bar__track" style={{ width }}>
        <motion.div
          className="factor-bar__fill"
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.4, ease: [0.25, 1, 0.5, 1], delay: 0.08 }}
          style={{ background: TIER_COLORS[tier] }}
        />
      </div>
      <span className="factor-bar__value">{Math.round(score)}</span>
      <span
        className="factor-bar__tier"
        aria-label={`tier-${tier}`}
        title={tier}
        style={{ color: TIER_COLORS[tier] }}
      >
        {TIER_ICONS[tier]}
      </span>
    </div>
  );
});
