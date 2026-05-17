import React from 'react';
import type { DimensionsCommentary } from '../../dimensions-types';

const ALIGN_COLORS: Record<DimensionsCommentary['alignment'], string> = {
  aligned: '#16a34a',
  partial: '#ca8a04',
  misaligned: '#dc2626',
};

export function CommentaryCard({ commentary }: { commentary: DimensionsCommentary }) {
  const ac = ALIGN_COLORS[commentary.alignment];
  return (
    <div
      style={{
        border: '1px solid var(--color-stone-border)',
        borderRadius: 'var(--radius-cards)',
        padding: 'var(--spacing-16)',
        background: 'var(--color-sky-tint)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span
          style={{
            padding: '3px 10px',
            borderRadius: 'var(--radius-buttons)',
            background: ac,
            color: 'white',
            fontSize: 11,
            letterSpacing: '0.04em',
            fontWeight: 600,
          }}
        >
          {commentary.alignment}
        </span>
        <strong style={{ color: 'var(--color-slate-text)' }}>Dimensions vs PM decision</strong>
      </div>
      <p style={{ margin: '12px 0', color: 'var(--color-slate-text)', lineHeight: 1.55 }}>
        {commentary.summary}
      </p>
      {commentary.supporting_dimensions.length > 0 && (
        <div style={{ fontSize: 'var(--text-caption)', color: 'var(--color-slate-text)', marginBottom: 6 }}>
          <strong>Supporting factors:</strong> {commentary.supporting_dimensions.join(', ')}
        </div>
      )}
      {commentary.conflicting_dimensions.length > 0 && (
        <div style={{ fontSize: 'var(--text-caption)', color: 'var(--color-slate-text)', marginBottom: 6 }}>
          <strong>Conflicting factors:</strong> {commentary.conflicting_dimensions.join(', ')}
        </div>
      )}
      {commentary.risk_flags.length > 0 && (
        <div style={{ fontSize: 'var(--text-caption)', color: 'var(--color-slate-text)' }}>
          <strong>Risk flags:</strong> {commentary.risk_flags.join(', ')}
        </div>
      )}
    </div>
  );
}
