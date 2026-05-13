import React from 'react';

export type Tier = 'red' | 'orange' | 'amber' | 'lime' | 'green';

export function colorTier(score: number): Tier {
  if (score < 20) return 'red';
  if (score < 40) return 'orange';
  if (score < 60) return 'amber';
  if (score < 80) return 'lime';
  return 'green';
}

const TIER_COLORS: Record<Tier, string> = {
  red: '#d23',
  orange: '#e57',
  amber: '#ea3',
  lime: '#9c3',
  green: '#3a3',
};

const TIER_ICONS: Record<Tier, string> = {
  red: '▼▼', orange: '▼', amber: '◆', lime: '▲', green: '▲▲',
};

export interface FactorBarProps {
  label: string;
  score: number | null;
  width?: number;
}

export function FactorBar({ label, score, width = 120 }: FactorBarProps) {
  if (score == null) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ minWidth: 80 }}>{label}</span>
        <span style={{ color: '#999' }}>—</span>
      </div>
    );
  }
  const tier = colorTier(score);
  const pct = Math.max(0, Math.min(100, score));
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{ minWidth: 80 }}>{label}</span>
      <div style={{ width, height: 10, background: '#eee', borderRadius: 4 }}>
        <div
          style={{
            width: `${pct}%`, height: '100%',
            background: TIER_COLORS[tier], borderRadius: 4,
          }}
        />
      </div>
      <span style={{ minWidth: 36, textAlign: 'right' }}>{Math.round(score)}</span>
      <span aria-label={`tier-${tier}`} title={tier} style={{ color: TIER_COLORS[tier] }}>
        {TIER_ICONS[tier]}
      </span>
    </div>
  );
}
