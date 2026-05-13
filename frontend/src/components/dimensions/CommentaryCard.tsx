import React from 'react';
import type { DimensionsCommentary } from '../../dimensions-types';

const ALIGN_COLORS = {
  aligned: '#3a3', partial: '#ea3', misaligned: '#d23',
};

export function CommentaryCard({ commentary }: { commentary: DimensionsCommentary }) {
  return (
    <div style={{ border: '1px solid #ddd', borderRadius: 6, padding: 16,
                  background: '#fafafa' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{
          padding: '2px 8px', borderRadius: 4,
          background: ALIGN_COLORS[commentary.alignment], color: 'white',
          fontSize: 12, textTransform: 'uppercase',
        }}>{commentary.alignment}</span>
        <strong>Dimensions Commentary</strong>
      </div>
      <p style={{ margin: '12px 0' }}>{commentary.summary}</p>
      {commentary.supporting_dimensions.length > 0 && (
        <div><strong>Supporting:</strong> {commentary.supporting_dimensions.join(', ')}</div>
      )}
      {commentary.conflicting_dimensions.length > 0 && (
        <div><strong>Conflicting:</strong> {commentary.conflicting_dimensions.join(', ')}</div>
      )}
      {commentary.risk_flags.length > 0 && (
        <div><strong>Risk flags:</strong> {commentary.risk_flags.join(', ')}</div>
      )}
    </div>
  );
}
