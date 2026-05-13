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
}

const FACTOR_KEYS = ['value', 'growth', 'quality', 'momentum', 'low_risk', 'sentiment'] as const;

export function DimensionsPanel({ dimensions, commentary, error }: DimensionsPanelProps) {
  if (error) {
    return (
      <div style={{ padding: 16, border: '1px solid #ea3', borderRadius: 6 }}>
        <strong>Dimensions unavailable for this run.</strong>
        <p style={{ margin: '8px 0 0', color: '#666' }}>{error}</p>
      </div>
    );
  }
  if (!dimensions) {
    return (
      <div style={{ padding: 16, border: '1px dashed #ccc', borderRadius: 6 }}>
        Dimensions not available — this run predates v1.0 of the dimensions layer.
      </div>
    );
  }
  return (
    <section style={{ display: 'grid', gap: 24 }}>
      <header>
        <h3 style={{ margin: 0 }}>Standardized Dimensions</h3>
        <small style={{ color: '#666' }}>
          version {dimensions.dimensions_version}
          {dimensions.peer_universe_id && ` · ${dimensions.peer_universe_id}`}
          {dimensions.source === 'facts_only' && ' · facts only (preview)'}
        </small>
      </header>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
        <DimensionsRadar factorScores={dimensions.factor_scores} />
        <div style={{ display: 'grid', gap: 8 }}>
          {FACTOR_KEYS.map(k => (
            <FactorBar
              key={k}
              label={k.replace('_', ' ')}
              score={dimensions.factor_scores[k].score}
            />
          ))}
        </div>
      </div>
      {commentary && <CommentaryCard commentary={commentary} />}
      <PillarGrid pillars={dimensions.pillar_scores} />
      <FactsTable facts={dimensions.facts} />
      {dimensions.data_quality_flags.length > 0 && (
        <div style={{ fontSize: 12, color: '#888' }}>
          Data quality flags: {dimensions.data_quality_flags.join(', ')}
        </div>
      )}
    </section>
  );
}
