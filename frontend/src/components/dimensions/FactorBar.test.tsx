import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { FactorBar, colorTier } from './FactorBar';

describe('colorTier', () => {
  it.each([
    [0, 'red'], [19, 'red'], [20, 'orange'], [39, 'orange'],
    [40, 'amber'], [59, 'amber'], [60, 'lime'], [79, 'lime'],
    [80, 'green'], [100, 'green'],
  ])('maps %d to %s', (score, expected) => {
    expect(colorTier(score as number)).toBe(expected);
  });
});

describe('FactorBar', () => {
  it('renders the score label', () => {
    const { container } = render(<FactorBar label="Value" score={72.5} />);
    expect(container.textContent).toMatch(/73/);
    expect(screen.getByText('Value')).toBeInTheDocument();
  });

  it('renders empty state when score is null', () => {
    render(<FactorBar label="Value" score={null} />);
    expect(screen.getByText(/—/)).toBeInTheDocument();
  });
});
