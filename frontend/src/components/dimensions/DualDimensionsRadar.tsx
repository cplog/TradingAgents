import React from 'react';
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Legend,
} from 'recharts';
import type { FactorScores } from '../../dimensions-types';

export interface DualDimensionsRadarProps {
  factorScoresA: FactorScores;
  factorScoresB: FactorScores;
  labelA?: string;
  labelB?: string;
  height?: number;
}

const FACTOR_ORDER: (keyof FactorScores)[] = [
  'value', 'growth', 'quality', 'momentum', 'low_risk', 'sentiment',
];

const FACTOR_LABEL: Record<keyof FactorScores, string> = {
  value: 'Value', growth: 'Growth', quality: 'Quality',
  momentum: 'Momentum', low_risk: 'Low Risk', sentiment: 'Sentiment',
};

export function DualDimensionsRadar({
  factorScoresA,
  factorScoresB,
  labelA = 'Run A',
  labelB = 'Run B',
  height = 280,
}: DualDimensionsRadarProps) {
  const data = FACTOR_ORDER.map(k => ({
    factor: FACTOR_LABEL[k],
    scoreA: factorScoresA[k].score ?? 0,
    scoreB: factorScoresB[k].score ?? 0,
    availableA: factorScoresA[k].score != null,
    availableB: factorScoresB[k].score != null,
  }));
  const anyData = data.some(d => d.availableA || d.availableB);
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
          name={labelA}
          dataKey="scoreA"
          stroke="var(--color-phosphor)"
          fill="var(--color-phosphor)"
          fillOpacity={0.15}
          strokeWidth={2}
        />
        <Radar
          name={labelB}
          dataKey="scoreB"
          stroke="#8b5cf6"
          fill="#8b5cf6"
          fillOpacity={0.15}
          strokeWidth={2}
          strokeDasharray="4 3"
        />
        <Legend
          wrapperStyle={{ fontSize: 12, color: 'var(--color-steel-gray)' }}
          iconType="circle"
        />
      </RadarChart>
    </ResponsiveContainer>
  );
}
