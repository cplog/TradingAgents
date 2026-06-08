import React from 'react';

export interface PlanLevelRecord {
  entry?: number | null;
  stop_loss?: number | null;
  price_target?: number | null;
}

interface PlanLevelsCompareProps {
  planA: PlanLevelRecord | null | undefined;
  planB: PlanLevelRecord | null | undefined;
  labelA?: string;
  labelB?: string;
  ticker?: string | null;
}

function fmtPrice(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return '—';
  return n.toFixed(2);
}

export function PlanLevelsCompare({ planA, planB, labelA = 'Run A', labelB = 'Run B', ticker }: PlanLevelsCompareProps) {
  const a = planA || {};
  const b = planB || {};
  const hasAny = [a.entry, a.stop_loss, a.price_target, b.entry, b.stop_loss, b.price_target].some(v => v != null);
  if (!hasAny) return null;

  const rows = [
    { key: 'entry', label: 'Entry' },
    { key: 'stop_loss', label: 'Stop Loss' },
    { key: 'price_target', label: 'Price Target' },
  ] as const;

  return (
    <div style={{ display: 'grid', gap: 'var(--spacing-12)' }}>
      <h4 style={{ margin: 0, fontSize: 'var(--text-heading-sm)', fontWeight: 600, color: 'var(--color-slate-text)' }}>
        Plan levels{ticker ? ` · ${ticker}` : ''}
      </h4>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr 1fr',
          gap: 'var(--spacing-8)',
          background: 'var(--surface-canvas-fog)',
          border: '1px solid var(--color-stone-border)',
          borderRadius: 'var(--radius-cards)',
          overflow: 'hidden',
          fontSize: 'var(--text-caption)',
        }}
      >
        <div style={{ padding: 'var(--spacing-12)', fontWeight: 600, color: 'var(--color-steel-gray)', borderBottom: '1px solid var(--color-stone-border)' }} />
        <div style={{ padding: 'var(--spacing-12)', fontWeight: 600, color: 'var(--color-phosphor)', borderBottom: '1px solid var(--color-stone-border)', background: 'rgba(244,184,136,0.06)' }}>
          {labelA}
        </div>
        <div style={{ padding: 'var(--spacing-12)', fontWeight: 600, color: '#8b5cf6', borderBottom: '1px solid var(--color-stone-border)', background: 'rgba(139,92,246,0.04)' }}>
          {labelB}
        </div>
        {rows.map((row) => {
          const av = (a as Record<string, unknown>)[row.key];
          const bv = (b as Record<string, unknown>)[row.key];
          const aNum = typeof av === 'number' ? av : null;
          const bNum = typeof bv === 'number' ? bv : null;
          const changed = aNum != null && bNum != null && Math.abs(aNum - bNum) > 0.01;
          return (
            <React.Fragment key={row.key}>
              <div style={{ padding: 'var(--spacing-12)', fontWeight: 500, color: 'var(--color-steel-gray)', borderBottom: '1px solid var(--color-stone-border)' }}>
                {row.label}
              </div>
              <div className="mono" style={{ padding: 'var(--spacing-12)', color: 'var(--color-slate-text)', borderBottom: '1px solid var(--color-stone-border)', background: 'rgba(244,184,136,0.03)' }}>
                {fmtPrice(aNum)}
              </div>
              <div className="mono" style={{ padding: 'var(--spacing-12)', color: changed ? '#8b5cf6' : 'var(--color-slate-text)', fontWeight: changed ? 600 : 400, borderBottom: '1px solid var(--color-stone-border)', background: 'rgba(139,92,246,0.02)' }}>
                {fmtPrice(bNum)}
              </div>
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
}
