import React from 'react';
import { DimensionsRadar } from './DimensionsRadar';
import { PillarGrid } from './PillarGrid';
import { FactsTable } from './FactsTable';
import { CommentaryCard } from './CommentaryCard';
import { FactorBar } from './FactorBar';
import type { StockDimensions, DimensionsCommentary } from '../../dimensions-types';

export interface DimensionsPanelProps {
  dimensions: StockDimensions | null;
  commentary?: DimensionsCommentary | null;
  error?: string | null;
  /** Shown when dimensions exist but PM-alignment commentary could not be generated. */
  commentaryError?: string | null;
}

const FACTOR_KEYS = ['value', 'growth', 'quality', 'momentum', 'low_risk', 'sentiment'] as const;

const jumpLink = { color: 'var(--color-chartwell-blue)', textDecoration: 'none' as const };

export function DimensionsPanel({ dimensions, commentary, error, commentaryError }: DimensionsPanelProps) {
  if (error && !dimensions) {
    return (
      <div className="panel panel--error">
        <strong>Dimensions unavailable for this run.</strong>
        <p style={{ margin: '8px 0 0', color: 'var(--color-ash-gray)' }}>{error}</p>
      </div>
    );
  }
  if (!dimensions) {
    return (
      <div className="panel dimensions-empty">
        Dimensions not available. This run predates v1.0 of the dimensions layer.
      </div>
    );
  }
  return (
    <section className="dimensions-panel">
      <header>
        <h3 style={{ margin: 0, color: 'var(--color-slate-text)' }}>Dimensional study</h3>
        <p
          style={{
            margin: '10px 0 0',
            fontSize: 'var(--text-caption)',
            color: 'var(--color-ash-gray)',
            maxWidth: '62ch',
            lineHeight: 1.55,
          }}
        >
          Standardized scores from the same analyst reports used in Agent reports, plus market data. This snapshot is
          also passed into the <strong>Trader</strong> and <strong>Portfolio Manager</strong> prompts during the run (when
          the graph build succeeds). Use this view to read factors and pillars side by side with the PM commentary
          below.
        </p>
        <small style={{ display: 'block', marginTop: 10, color: 'var(--color-ash-gray)' }}>
          version {dimensions.dimensions_version}
          {dimensions.peer_scope && <> · peer scope: {dimensions.peer_scope}</>}
          {dimensions.peer_universe_id && ` · ${dimensions.peer_universe_id}`}
          {dimensions.peer_universe_resolved_slug && (
            <> · slug {dimensions.peer_universe_resolved_slug}</>
          )}
          {dimensions.source === 'facts_only' && ' · facts only (preview)'}
        </small>
      </header>

      {commentaryError && (
        <div
          style={{
            padding: 12,
            border: '1px solid var(--color-warning)',
            borderRadius: 'var(--radius-cards)',
            background: 'var(--surface-cloud-white)',
            fontSize: 'var(--text-caption)',
            color: 'var(--color-ash-gray)',
          }}
        >
          <strong style={{ color: 'var(--color-slate-text)' }}>PM alignment commentary unavailable.</strong>
          <p style={{ margin: '8px 0 0' }}>{commentaryError}</p>
        </div>
      )}

      <nav
        aria-label="Jump to dimension sections"
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: '6px 10px',
          fontSize: 'var(--text-caption)',
          padding: '10px 12px',
          borderRadius: 'var(--radius-cards)',
          border: '1px solid var(--color-stone-border)',
          background: 'var(--color-ghost-ink)',
          color: 'var(--surface-cloud-white)',
        }}
      >
        <span style={{ opacity: 0.85 }}>Jump:</span>
        {commentary && (
          <>
            <a href="#ta-dim-alignment" style={jumpLink}>PM alignment</a>
            <span style={{ opacity: 0.45 }}>·</span>
          </>
        )}
        <a href="#ta-dim-factors" style={jumpLink}>Factors</a>
        <span style={{ opacity: 0.45 }}>·</span>
        <a href="#ta-dim-pillars" style={jumpLink}>Pillars</a>
        <span style={{ opacity: 0.45 }}>·</span>
        <a href="#ta-dim-facts" style={jumpLink}>Facts</a>
      </nav>

      {commentary && (
        <div id="ta-dim-alignment" style={{ scrollMarginTop: 24 }}>
          <CommentaryCard commentary={commentary} />
        </div>
      )}

      <div id="ta-dim-factors" style={{ scrollMarginTop: 24 }}>
        <h4 style={{ margin: '0 0 12px', fontSize: 'var(--text-heading-sm)', color: 'var(--color-slate-text)' }}>
          Factor scores
        </h4>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
            gap: 24,
          }}
        >
          <DimensionsRadar factorScores={dimensions.factor_scores} />
          <div style={{ display: 'grid', gap: 8 }}>
            {FACTOR_KEYS.map((k) => (
              <FactorBar
                key={k}
                label={k.replace('_', ' ')}
                score={dimensions.factor_scores[k].score}
              />
            ))}
          </div>
        </div>
      </div>

      <div id="ta-dim-pillars" style={{ scrollMarginTop: 24 }}>
        <h4 style={{ margin: '0 0 12px', fontSize: 'var(--text-heading-sm)', color: 'var(--color-slate-text)' }}>
          Pillar breakdown (16)
        </h4>
        <PillarGrid pillars={dimensions.pillar_scores} />
      </div>

      <details
        id="ta-dim-facts"
        style={{ scrollMarginTop: 24, border: '1px solid var(--color-stone-border)', borderRadius: 'var(--radius-cards)', padding: '12px 16px' }}
      >
        <summary
          style={{
            cursor: 'pointer',
            fontWeight: 600,
            color: 'var(--color-slate-text)',
          }}
        >
          Key facts tables (expand)
        </summary>
        <div style={{ marginTop: 16 }}>
          <FactsTable facts={dimensions.facts} />
        </div>
      </details>

      {dimensions.data_quality_flags.length > 0 && (
        <div style={{ fontSize: 12, color: 'var(--color-ash-gray)' }}>
          Data quality flags: {dimensions.data_quality_flags.join(', ')}
        </div>
      )}
    </section>
  );
}
