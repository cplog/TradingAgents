import React from 'react';
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer,
} from 'recharts';
import type { FactorScores } from '../../dimensions-types';

export interface DimensionsRadarProps {
  factorScores: FactorScores;
  height?: number;
}

const FACTOR_ORDER: (keyof FactorScores)[] = [
  'value', 'growth', 'quality', 'momentum', 'low_risk', 'sentiment',
];

const FACTOR_LABEL: Record<keyof FactorScores, string> = {
  value: 'Value', growth: 'Growth', quality: 'Quality',
  momentum: 'Momentum', low_risk: 'Low Risk', sentiment: 'Sentiment',
};

export function DimensionsRadar({ factorScores, height = 280 }: DimensionsRadarProps) {
  const data = FACTOR_ORDER.map(k => ({
    factor: FACTOR_LABEL[k],
    score: factorScores[k].score ?? 0,
    available: factorScores[k].score != null,
  }));
  const anyData = data.some(d => d.available);
  if (!anyData) {
    return (
      <div className="chart-empty" style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        Insufficient data for radar chart
      </div>
    );
  }
  return (
    <ResponsiveContainer width="100%" height={height}>
      <RadarChart data={data}>
        <PolarGrid stroke="var(--color-stone-border)" />
        <PolarAngleAxis dataKey="factor" tick={{ fill: 'var(--color-ash-gray)', fontSize: 11 }} />
        <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fill: 'var(--color-steel-gray)', fontSize: 10 }} />
        <Radar
          name="Factor"
          dataKey="score"
          stroke="var(--color-phosphor)"
          fill="var(--color-phosphor)"
          fillOpacity={0.25}
        />
      </RadarChart>
    </ResponsiveContainer>
  );
}
