import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DimensionsRadar } from './DimensionsRadar';

describe('DimensionsRadar', () => {
  it('renders with full factor scores', () => {
    const { container } = render(
      <DimensionsRadar
        factorScores={{
          value: { score: 70, inputs: {} },
          growth: { score: 60, inputs: {} },
          quality: { score: 80, inputs: {} },
          momentum: { score: 55, inputs: {} },
          low_risk: { score: 40, inputs: {} },
          sentiment: { score: 50, inputs: {} },
        }}
      />,
    );
    expect(container.querySelector('svg')).toBeTruthy();
  });

  it('renders empty state with null scores', () => {
    const { getByText } = render(
      <DimensionsRadar
        factorScores={{
          value: { score: null, inputs: {} },
          growth: { score: null, inputs: {} },
          quality: { score: null, inputs: {} },
          momentum: { score: null, inputs: {} },
          low_risk: { score: null, inputs: {} },
          sentiment: { score: null, inputs: {} },
        }}
      />,
    );
    expect(getByText(/insufficient data/i)).toBeInTheDocument();
  });
});
