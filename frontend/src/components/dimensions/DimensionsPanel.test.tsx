import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DimensionsPanel } from './DimensionsPanel';

describe('DimensionsPanel', () => {
  it('renders empty state when dimensions is null', () => {
    render(<DimensionsPanel dimensions={null} />);
    expect(screen.getByText(/predates v1.0/i)).toBeInTheDocument();
  });

  it('renders error state when error provided', () => {
    render(<DimensionsPanel dimensions={null} error="yfinance offline" />);
    expect(screen.getByText(/yfinance offline/)).toBeInTheDocument();
  });

  it('shows dimensions with commentary warning when commentaryError is set', () => {
    const ps = { score: 3, rationale: 'x' };
    render(
      <DimensionsPanel
        dimensions={{
          ticker: 'AAPL',
          as_of_date: '2026-05-13',
          dimensions_version: '1.0.0',
          facts: { as_of_date: '2026-05-13', currency: 'USD' },
          pillar_scores: {
            market: {
              trend: ps,
              momentum: ps,
              volatility_risk: ps,
              setup_quality: ps,
            },
            sentiment: {
              retail_sentiment: ps,
              social_buzz: ps,
              consensus_quality: ps,
              narrative_strength: ps,
            },
            news: {
              catalyst_strength: ps,
              macro_alignment: ps,
              headline_quality: ps,
              surprise_risk: ps,
            },
            fundamentals: {
              valuation: ps,
              growth: ps,
              profitability: ps,
              balance_sheet_strength: ps,
            },
          },
          factor_scores: {
            value: { score: 70 },
            growth: { score: 60 },
            quality: { score: 80 },
            momentum: { score: 55 },
            low_risk: { score: 40 },
            sentiment: { score: 50 },
          },
          data_quality_flags: [],
        }}
        commentaryError="Commentary failed: model timeout"
      />,
    );
    expect(screen.getByText(/Dimensional study/i)).toBeInTheDocument();
    expect(screen.getByText(/Commentary failed: model timeout/)).toBeInTheDocument();
  });
});
