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
});
