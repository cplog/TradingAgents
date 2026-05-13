export interface PillarScore { score: number; rationale: string }

export interface FactSnapshot {
  as_of_date: string; currency: string;
  exchange?: string | null; sector?: string | null; industry?: string | null;
  market_cap_usd?: number | null;
  price?: number | null; price_52w_high?: number | null;
  pct_off_52w_high?: number | null;
  return_1m?: number | null; return_3m?: number | null;
  return_6m?: number | null; return_12m?: number | null;
  beta?: number | null;
  realized_vol_30d?: number | null; rsi_14?: number | null;
  avg_daily_dollar_volume_30d?: number | null;
  pe_ttm?: number | null; forward_pe?: number | null; peg?: number | null;
  ev_ebitda?: number | null; ps_ttm?: number | null; pb?: number | null;
  fcf_yield?: number | null;
  revenue_growth_yoy?: number | null; eps_growth_yoy?: number | null;
  revenue_cagr_3y?: number | null; eps_cagr_3y?: number | null;
  roe?: number | null; roic?: number | null;
  gross_margin?: number | null; operating_margin?: number | null;
  net_margin?: number | null; debt_to_equity?: number | null;
  interest_coverage?: number | null; current_ratio?: number | null;
  dividend_yield?: number | null; payout_ratio?: number | null;
  analyst_count?: number | null;
  analyst_target_mean?: number | null; analyst_recommendation_mean?: number | null;
}

export interface PillarScores {
  market: { trend: PillarScore; momentum: PillarScore;
            volatility_risk: PillarScore; setup_quality: PillarScore };
  sentiment: { retail_sentiment: PillarScore; social_buzz: PillarScore;
               consensus_quality: PillarScore; narrative_strength: PillarScore };
  news: { catalyst_strength: PillarScore; macro_alignment: PillarScore;
          headline_quality: PillarScore; surprise_risk: PillarScore };
  fundamentals: { valuation: PillarScore; growth: PillarScore;
                  profitability: PillarScore; balance_sheet_strength: PillarScore };
}

export interface FactorScore { score: number | null; inputs: Record<string, number> }

export interface FactorScores {
  value: FactorScore; growth: FactorScore; quality: FactorScore;
  momentum: FactorScore; low_risk: FactorScore; sentiment: FactorScore;
}

export interface StockDimensions {
  ticker: string; as_of_date: string;
  facts: FactSnapshot; pillar_scores: PillarScores; factor_scores: FactorScores;
  dimensions_version: string;
  peer_universe_id?: string | null;
  data_quality_flags: string[];
  source: 'full_run' | 'facts_only';
}

export interface DimensionsCommentary {
  alignment: 'aligned' | 'partial' | 'misaligned';
  supporting_dimensions: string[]; conflicting_dimensions: string[];
  risk_flags: string[]; summary: string;
}
