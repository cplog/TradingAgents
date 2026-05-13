import React from 'react';
import type { FactSnapshot } from '../../dimensions-types';

const GROUPS: Array<[string, (keyof FactSnapshot)[]]> = [
  ['Price & Return', ['price', 'price_52w_high', 'pct_off_52w_high',
                      'return_1m', 'return_3m', 'return_6m', 'return_12m', 'beta']],
  ['Volatility & Liquidity', ['realized_vol_30d', 'rsi_14',
                              'avg_daily_dollar_volume_30d']],
  ['Valuation', ['pe_ttm', 'forward_pe', 'peg', 'ev_ebitda', 'ps_ttm', 'pb',
                 'fcf_yield']],
  ['Growth', ['revenue_growth_yoy', 'eps_growth_yoy', 'revenue_cagr_3y', 'eps_cagr_3y']],
  ['Quality', ['roe', 'roic', 'gross_margin', 'operating_margin', 'net_margin',
               'debt_to_equity', 'interest_coverage', 'current_ratio']],
  ['Income', ['dividend_yield', 'payout_ratio']],
  ['Sell-side', ['analyst_count', 'analyst_target_mean', 'analyst_recommendation_mean']],
];

function fmt(v: any): string {
  if (v == null) return '—';
  if (typeof v === 'number') return Math.abs(v) < 1 ? v.toFixed(3) : v.toLocaleString();
  return String(v);
}

export function FactsTable({ facts }: { facts: FactSnapshot }) {
  return (
    <div style={{ display: 'grid', gap: 16 }}>
      {GROUPS.map(([title, keys]) => (
        <div key={title}>
          <h4 style={{ margin: '4px 0' }}>{title}</h4>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <tbody>
              {keys.map(k => (
                <tr key={k as string}>
                  <td style={{ padding: '4px 8px', color: '#555' }}>
                    {(k as string).replace(/_/g, ' ')}
                  </td>
                  <td style={{ padding: '4px 8px', textAlign: 'right' }}>
                    {fmt((facts as any)[k])}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
