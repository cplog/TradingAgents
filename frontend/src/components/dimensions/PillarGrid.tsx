import React from 'react';
import type { PillarScore, PillarScores } from '../../dimensions-types';

const SCORE_COLORS = ['#d23', '#e57', '#ea3', '#9c3', '#3a3'];

function Cell({ label, score }: { label: string; score: PillarScore }) {
  const color = SCORE_COLORS[score.score - 1];
  return (
    <button
      type="button"
      title={score.rationale}
      style={{
        padding: 8, border: '1px solid #ddd', borderRadius: 4,
        background: '#fafafa', textAlign: 'left', cursor: 'help',
      }}
    >
      <div style={{ fontSize: 12, color: '#666' }}>{label}</div>
      <div style={{ color, fontWeight: 600, fontSize: 18 }}>
        {score.score}/5
      </div>
    </button>
  );
}

export interface PillarGridProps { pillars: PillarScores }

const PILLAR_GROUPS: Array<[string, keyof PillarScores, string[]]> = [
  ['Market', 'market', ['trend', 'momentum', 'volatility_risk', 'setup_quality']],
  ['Sentiment', 'sentiment',
   ['retail_sentiment', 'social_buzz', 'consensus_quality', 'narrative_strength']],
  ['News', 'news',
   ['catalyst_strength', 'macro_alignment', 'headline_quality', 'surprise_risk']],
  ['Fundamentals', 'fundamentals',
   ['valuation', 'growth', 'profitability', 'balance_sheet_strength']],
];

export function PillarGrid({ pillars }: PillarGridProps) {
  return (
    <div style={{ display: 'grid', gap: 16 }}>
      {PILLAR_GROUPS.map(([title, key, dims]) => (
        <div key={key}>
          <h4 style={{ margin: '4px 0' }}>{title}</h4>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
            {dims.map(d => (
              <Cell key={d} label={d.replace(/_/g, ' ')}
                    score={(pillars[key] as any)[d]} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
