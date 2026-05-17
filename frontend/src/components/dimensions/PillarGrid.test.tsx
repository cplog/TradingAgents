import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PillarGrid } from './PillarGrid';
import type { PillarScores } from '../../dimensions-types';

const _ps = (s = 3, r = 'rationale text') => ({ score: s, rationale: r });

const pillars: PillarScores = {
  market: { trend: _ps(4, 'strong uptrend'), momentum: _ps(), volatility_risk: _ps(), setup_quality: _ps() },
  sentiment: { retail_sentiment: _ps(), social_buzz: _ps(), consensus_quality: _ps(), narrative_strength: _ps() },
  news: { catalyst_strength: _ps(), macro_alignment: _ps(), headline_quality: _ps(), surprise_risk: _ps() },
  fundamentals: { valuation: _ps(), growth: _ps(), profitability: _ps(), balance_sheet_strength: _ps() },
};

describe('PillarGrid', () => {
  it('shows all 16 sub-dimensions', () => {
    render(<PillarGrid pillars={pillars} />);
    expect(screen.getAllByRole('button').length).toBeGreaterThanOrEqual(16);
  });

  it('exposes rationale via tooltip role', () => {
    render(<PillarGrid pillars={pillars} />);
    const trendButtons = screen.getAllByRole("button", { name: /trend/i });
    expect(trendButtons.length).toBeGreaterThanOrEqual(1);
    expect(trendButtons[0]).toHaveAttribute("title", expect.stringContaining("strong uptrend"));
  });
});
