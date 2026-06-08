import React from 'react';
import type { FactorScores } from '../../dimensions-types';

interface FactorDelta {
  factor: string;
  a: number | null;
  b: number | null;
  delta: number | null;
}

interface FactorDeltaBarsProps {
  factorScoresA: FactorScores;
  factorScoresB: FactorScores;
  labelA?: string;
  labelB?: string;
}

const FACTOR_ORDER: { key: keyof FactorScores; label: string }[] = [
  { key: 'value', label: 'Value' },
  { key: 'growth', label: 'Growth' },
  { key: 'quality', label: 'Quality' },
  { key: 'momentum', label: 'Momentum' },
  { key: 'low_risk', label: 'Low Risk' },
  { key: 'sentiment', label: 'Sentiment' },
];

function fmt(n: number | null): string {
  if (n == null || !Number.isFinite(n)) return '—';
  return `${Math.round(n)}`;
}

export function FactorDeltaBars({ factorScoresA, factorScoresB, labelA = 'A', labelB = 'B' }: FactorDeltaBarsProps) {
  const rows: FactorDelta[] = FACTOR_ORDER.map(({ key, label }) => {
    const a = factorScoresA[key].score ?? null;
    const b = factorScoresB[key].score ?? null;
    return {
      factor: label,
      a,
      b,
      delta: a != null && b != null ? b - a : null,
    };
  });

  const hasAny = rows.some(r => r.a != null || r.b != null);
  if (!hasAny) {
    return (
      <div style={{ padding: 'var(--spacing-16)', textAlign: 'center', color: 'var(--color-ash-gray)', fontSize: 'var(--text-caption)' }}>
        No factor scores available for comparison.
      </div>
    );
  }

  return (
    <div style={{ display: 'grid', gap: 'var(--spacing-12)' }}>
      {rows.map((row) => {
        const changed = row.delta != null && Math.abs(row.delta) >= 1;
        const improved = (row.delta ?? 0) > 0;
        return (
          <div key={row.factor} style={{ display: 'grid', gap: 'var(--spacing-4)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 'var(--text-caption)', fontWeight: 500 }}>
              <span style={{ color: 'var(--color-slate-text)' }}>{row.factor}</span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 'var(--spacing-8)', color: 'var(--color-steel-gray)' }}>
                <span className="mono">{fmt(row.a)}</span>
                <span style={{ color: 'var(--color-ash-gray)' }}>→</span>
                <span className="mono" style={changed ? { color: improved ? '#15803d' : '#b91c1c', fontWeight: 600 } : undefined}>
                  {fmt(row.b)}
                </span>
                {changed && (
                  <span className="mono" style={{ fontSize: 11, color: improved ? '#15803d' : '#b91c1c', fontWeight: 600 }}>
                    {improved ? '+' : ''}{fmt(row.delta)}
                  </span>
                )}
              </span>
            </div>
            <div style={{ position: 'relative', height: 6, background: 'var(--color-stone-border)', borderRadius: 3, overflow: 'hidden' }}>
              {row.a != null && (
                <div
                  style={{
                    position: 'absolute',
                    left: 0,
                    width: `${Math.min(Math.max(row.a, 0), 100)}%`,
                    height: '100%',
                    background: 'var(--color-phosphor)',
                    opacity: 0.35,
                    borderRadius: 3,
                  }}
                />
              )}
              {row.b != null && (
                <div
                  style={{
                    position: 'absolute',
                    left: 0,
                    width: `${Math.min(Math.max(row.b, 0), 100)}%`,
                    height: '100%',
                    background: row.delta != null && Math.abs(row.delta) >= 1 ? (improved ? '#15803d' : '#b91c1c') : '#8b5cf6',
                    opacity: 0.55,
                    borderRadius: 3,
                  }}
                />
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
