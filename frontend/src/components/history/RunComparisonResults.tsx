import React, { useState } from 'react';
import { motion } from 'motion/react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { HistoryCompareResponse, HistoryCompareSide } from '../../api';
import type { StockDimensions, FactorScores } from '../../dimensions-types';
import { DualDimensionsRadar } from '../dimensions/DualDimensionsRadar';
import { FactorDeltaBars } from './FactorDeltaBars';
import { PlanLevelsCompare } from './PlanLevelsCompare';
import { prepareReportMarkdown } from '../../utils/reportMarkdown';
import type { Components } from 'react-markdown';

const REPORT_MD_COMPONENTS: Components = {
  table: ({ children, ...rest }) => (
    <div className="markdown-table-wrap">
      <table {...rest}>{children}</table>
    </div>
  ),
};

function pct(conf: number | null | undefined): string {
  if (conf == null || !Number.isFinite(conf)) return '—';
  return `${Math.round(conf * 100)}%`;
}

function ratingTone(rating: string | null | undefined): 'positive' | 'negative' | 'neutral' {
  const r = (rating || '').toLowerCase();
  if (r.includes('buy') || r.includes('overweight')) return 'positive';
  if (r.includes('sell') || r.includes('underweight')) return 'negative';
  return 'neutral';
}

function ratingClass(tone: 'positive' | 'negative' | 'neutral'): string {
  switch (tone) {
    case 'positive': return 'decision-brief__rating--positive';
    case 'negative': return 'decision-brief__rating--negative';
    default: return 'decision-brief__rating--neutral';
  }
}

function extractPlanLevels(side: HistoryCompareSide): { entry?: number; stop_loss?: number; price_target?: number } | null {
  const pl = side.plan_levels;
  if (pl && typeof pl === 'object') {
    const out: Record<string, number> = {};
    for (const k of ['entry', 'stop_loss', 'price_target']) {
      const v = (pl as Record<string, unknown>)[k];
      if (typeof v === 'number') out[k] = v;
    }
    return Object.keys(out).length ? out as { entry?: number; stop_loss?: number; price_target?: number } : null;
  }
  return null;
}

function extractPriceFromLiveContext(side: HistoryCompareSide): number | null {
  const ctx = side.live_context_at_run;
  if (!ctx || typeof ctx !== 'object') return null;
  const quote = (ctx as Record<string, unknown>).quote;
  if (quote && typeof quote === 'object') {
    const p = (quote as Record<string, unknown>).price;
    if (typeof p === 'number') return p;
  }
  return null;
}

function extractAnalysts(coverage: Record<string, { status?: string }> | null | undefined): string[] {
  if (!coverage) return [];
  return Object.entries(coverage)
    .filter(([, v]) => v.status === 'ok')
    .map(([k]) => k);
}

interface CompareSectionProps {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}

function CompareSection({ title, children, defaultOpen = true }: CompareSectionProps) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{ borderBottom: '1px solid var(--color-stone-border)', paddingBottom: 'var(--spacing-16)' }}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          width: '100%',
          background: 'none',
          border: 'none',
          padding: 'var(--spacing-12) 0',
          cursor: 'pointer',
          fontSize: 'var(--text-heading-sm)',
          fontWeight: 600,
          color: 'var(--color-slate-text)',
          fontFamily: 'inherit',
        }}
      >
        {title}
        <span style={{ fontSize: 14, color: 'var(--color-ash-gray)', transition: 'transform 200ms', transform: open ? 'rotate(180deg)' : 'rotate(0deg)' }}>▼</span>
      </button>
      {open && <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} transition={{ duration: 0.2 }}>{children}</motion.div>}
    </div>
  );
}

interface RunComparisonResultsProps {
  compare: HistoryCompareResponse;
  showFullPm: boolean;
  onToggleFullPm: () => void;
}

export function RunComparisonResults({ compare, showFullPm, onToggleFullPm }: RunComparisonResultsProps) {
  const { a, b } = compare;
  const sameTicker = (a.ticker || '').toUpperCase() === (b.ticker || '').toUpperCase() && !!a.ticker;
  const toneA = ratingTone(a.rating);
  const toneB = ratingTone(b.rating);
  const ratingChanged = (a.rating || '').toLowerCase() !== (b.rating || '').toLowerCase();
  const confA = a.confidence ?? null;
  const confB = b.confidence ?? null;
  const confDelta = confA != null && confB != null ? confB - confA : null;

  const priceA = extractPriceFromLiveContext(a);
  const priceB = extractPriceFromLiveContext(b);

  const dimsA = a.dimensions ?? null;
  const dimsB = b.dimensions ?? null;
  const hasDimsA = dimsA != null && dimsA.factor_scores != null;
  const hasDimsB = dimsB != null && dimsB.factor_scores != null;

  const planA = extractPlanLevels(a);
  const planB = extractPlanLevels(b);

  const analystsA = extractAnalysts(a.analyst_coverage);
  const analystsB = extractAnalysts(b.analyst_coverage);
  const allAnalysts = Array.from(new Set([...analystsA, ...analystsB]));

  // Build key differences list
  const diffs: string[] = [];
  if (ratingChanged) {
    diffs.push(`Rating changed from **${a.rating ?? '—'}** to **${b.rating ?? '—'}**`);
  } else if (a.rating) {
    diffs.push(`Rating unchanged at **${a.rating}**`);
  }
  if (confDelta != null && Math.abs(confDelta) >= 0.01) {
    const dir = confDelta > 0 ? 'increased' : 'decreased';
    diffs.push(`Conviction ${dir} from ${pct(confA)} to ${pct(confB)} (${confDelta > 0 ? '+' : ''}${pct(confDelta)})`);
  }
  if (sameTicker && priceA != null && priceB != null) {
    const priceDelta = priceB - priceA;
    const pricePct = priceA !== 0 ? (priceDelta / priceA) * 100 : 0;
    diffs.push(`Price moved from $${priceA.toFixed(2)} to $${priceB.toFixed(2)} (${pricePct >= 0 ? '+' : ''}${pricePct.toFixed(1)}%)`);
  }
  if (!sameTicker) {
    diffs.push(`Comparing two tickers: **${a.ticker}** vs **${b.ticker}**`);
  }

  const dateA = a.date ?? (a.completed_at ? a.completed_at.slice(0, 10) : null);
  const dateB = b.date ?? (b.completed_at ? b.completed_at.slice(0, 10) : null);

  return (
    <div className="history-page__compare-results" style={{ display: 'grid', gap: 'var(--spacing-24)' }}>
      {/* Decision Header */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 16rem), 1fr))',
          gap: 'var(--spacing-16)',
          alignItems: 'start',
        }}
      >
        {/* Side A */}
        <div
          className="compare-card"
          style={{
            borderLeft: '3px solid var(--color-phosphor)',
            display: 'grid',
            gap: 'var(--spacing-12)',
          }}
        >
          <div style={{ fontSize: 'var(--text-caption)', fontWeight: 600, color: 'var(--color-steel-gray)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Run A · {a.ticker ?? '—'} · {dateA ?? '—'}
          </div>
          <div className={`decision-brief__rating ${ratingClass(toneA)}`} style={{ display: 'inline-block', padding: 'var(--spacing-8) var(--spacing-16)', borderRadius: 'var(--radius-cards)', border: '1px solid transparent', width: 'fit-content' }}>
            {a.rating ?? '—'}
          </div>
          <div style={{ fontSize: 'var(--text-caption)', color: 'var(--color-steel-gray)' }}>
            Conviction <span className="mono" style={{ color: 'var(--color-slate-text)', fontWeight: 600 }}>{pct(confA)}</span>
            {priceA != null && (
              <span style={{ marginLeft: 'var(--spacing-12)' }}>Price <span className="mono" style={{ color: 'var(--color-slate-text)', fontWeight: 600 }}>${priceA.toFixed(2)}</span></span>
            )}
          </div>
          <div className="mono" style={{ fontSize: 11, color: 'var(--color-ash-gray)' }}>{a.run_id}</div>
        </div>

        {/* Delta Column (center, hidden on very narrow) */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 'var(--spacing-8)', minWidth: 0 }}>
          <div style={{ fontSize: 28, color: 'var(--color-ash-gray)' }}>→</div>
          {confDelta != null && (
            <div
              className="mono"
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: confDelta > 0 ? '#15803d' : confDelta < 0 ? '#b91c1c' : 'var(--color-ash-gray)',
                background: confDelta > 0 ? 'rgba(21,128,61,0.08)' : confDelta < 0 ? 'rgba(185,28,28,0.08)' : 'var(--surface-canvas-fog)',
                padding: '2px 8px',
                borderRadius: 999,
              }}
            >
              {confDelta > 0 ? '+' : ''}{pct(confDelta)}
            </div>
          )}
        </div>

        {/* Side B */}
        <div
          className="compare-card"
          style={{
            borderLeft: '3px solid #8b5cf6',
            display: 'grid',
            gap: 'var(--spacing-12)',
          }}
        >
          <div style={{ fontSize: 'var(--text-caption)', fontWeight: 600, color: 'var(--color-steel-gray)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Run B · {b.ticker ?? '—'} · {dateB ?? '—'}
          </div>
          <div className={`decision-brief__rating ${ratingClass(toneB)}`} style={{ display: 'inline-block', padding: 'var(--spacing-8) var(--spacing-16)', borderRadius: 'var(--radius-cards)', border: '1px solid transparent', width: 'fit-content' }}>
            {b.rating ?? '—'}
          </div>
          <div style={{ fontSize: 'var(--text-caption)', color: 'var(--color-steel-gray)' }}>
            Conviction <span className="mono" style={{ color: 'var(--color-slate-text)', fontWeight: 600 }}>{pct(confB)}</span>
            {priceB != null && (
              <span style={{ marginLeft: 'var(--spacing-12)' }}>Price <span className="mono" style={{ color: 'var(--color-slate-text)', fontWeight: 600 }}>${priceB.toFixed(2)}</span></span>
            )}
          </div>
          <div className="mono" style={{ fontSize: 11, color: 'var(--color-ash-gray)' }}>{b.run_id}</div>
        </div>
      </div>

      {/* Key Differences */}
      {diffs.length > 0 && (
        <div
          style={{
            background: 'var(--surface-cloud-white)',
            border: '1px solid var(--color-stone-border)',
            borderRadius: 'var(--radius-cards)',
            padding: 'var(--spacing-16) var(--spacing-20)',
            display: 'grid',
            gap: 'var(--spacing-8)',
          }}
        >
          <h4 style={{ margin: 0, fontSize: 'var(--text-heading-sm)', fontWeight: 600, color: 'var(--color-slate-text)' }}>
            Key changes
          </h4>
          <ul style={{ margin: 0, paddingLeft: 'var(--spacing-20)', fontSize: 'var(--text-caption)', color: 'var(--color-slate-text)', lineHeight: 1.6 }}>
            {diffs.map((d, i) => (
              <li key={i}>
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ p: ({ children }) => <span>{children}</span> }}>{d}</ReactMarkdown>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Analyst Coverage */}
      {allAnalysts.length > 0 && (
        <CompareSection title="Analyst coverage" defaultOpen={false}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--spacing-8)', paddingTop: 'var(--spacing-8)' }}>
            {allAnalysts.map((id) => {
              const inA = analystsA.includes(id);
              const inB = analystsB.includes(id);
              const changed = inA !== inB;
              return (
                <span
                  key={id}
                  style={{
                    fontSize: 11,
                    fontWeight: 500,
                    textTransform: 'capitalize',
                    padding: '4px 10px',
                    borderRadius: 999,
                    border: '1px solid var(--color-stone-border)',
                    background: inA && inB ? 'var(--surface-canvas-fog)' : inA ? 'rgba(244,184,136,0.08)' : 'rgba(139,92,246,0.08)',
                    color: changed ? (inA ? 'var(--color-phosphor)' : '#8b5cf6') : 'var(--color-steel-gray)',
                  }}
                  title={inA && inB ? 'Present in both runs' : inA ? 'Only in Run A' : 'Only in Run B'}
                >
                  {id.replace(/_/g, ' ')}
                  <span className="mono" style={{ marginLeft: 4, opacity: 0.7 }}>
                    {inA && inB ? 'A·B' : inA ? 'A' : 'B'}
                  </span>
                </span>
              );
            })}
          </div>
        </CompareSection>
      )}

      {/* Dimensions */}
      {(hasDimsA || hasDimsB) && (
        <CompareSection title="Dimensions" defaultOpen={true}>
          {sameTicker && hasDimsA && hasDimsB ? (
            <div style={{ paddingTop: 'var(--spacing-8)' }}>
              <FactorDeltaBars
                factorScoresA={dimsA!.factor_scores}
                factorScoresB={dimsB!.factor_scores}
                labelA="Run A"
                labelB="Run B"
              />
            </div>
          ) : (
            <div className="page-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 17rem), 1fr))', paddingTop: 'var(--spacing-8)' }}>
              {hasDimsA && hasDimsB ? (
                <div className="compare-radar-card">
                  <DualDimensionsRadar
                    factorScoresA={dimsA!.factor_scores}
                    factorScoresB={dimsB!.factor_scores}
                    labelA={`${a.ticker ?? 'A'} · ${dateA ?? ''}`}
                    labelB={`${b.ticker ?? 'B'} · ${dateB ?? ''}`}
                    height={260}
                  />
                </div>
              ) : (
                <>
                  {hasDimsA && (
                    <div className="compare-radar-card">
                      <div style={{ fontSize: 'var(--text-caption)', fontWeight: 600, color: 'var(--color-slate-text)', padding: 'var(--spacing-12)' }}>
                        Run A · Dimensions
                      </div>
                      {/* We could import DimensionsRadar here but it needs the right import; for now show placeholder */}
                      <div style={{ height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--color-ash-gray)', fontSize: 'var(--text-caption)' }}>
                        Radar available (import DimensionsRadar separately)
                      </div>
                    </div>
                  )}
                  {hasDimsB && (
                    <div className="compare-radar-card">
                      <div style={{ fontSize: 'var(--text-caption)', fontWeight: 600, color: 'var(--color-slate-text)', padding: 'var(--spacing-12)' }}>
                        Run B · Dimensions
                      </div>
                      <div style={{ height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--color-ash-gray)', fontSize: 'var(--text-caption)' }}>
                        Radar available (import DimensionsRadar separately)
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </CompareSection>
      )}

      {/* Plan Levels */}
      {(planA || planB) && (
        <CompareSection title="Plan levels" defaultOpen={true}>
          <div style={{ paddingTop: 'var(--spacing-8)' }}>
            <PlanLevelsCompare planA={planA} planB={planB} ticker={sameTicker ? a.ticker : undefined} />
          </div>
        </CompareSection>
      )}

      {/* Raw Reports */}
      <CompareSection title="Trader plan" defaultOpen={false}>
        <div className="compare-two-col" style={{ paddingTop: 'var(--spacing-8)' }}>
          {[a, b].map((side, idx) => (
            <pre
              key={idx}
              className="mono"
              style={{
                margin: 0,
                whiteSpace: 'pre-wrap',
                fontSize: 'var(--text-caption)',
                lineHeight: 1.55,
                background: 'var(--surface-canvas-fog)',
                border: '1px solid var(--color-stone-border)',
                padding: 'var(--spacing-16)',
                borderRadius: 'var(--radius-cards)',
                maxHeight: 280,
                overflow: 'auto',
              }}
            >
              {side.excerpt_trader_plan || '—'}
            </pre>
          ))}
        </div>
      </CompareSection>

      <CompareSection title="Portfolio decision" defaultOpen={false}>
        <div style={{ display: 'grid', gap: 'var(--spacing-12)', paddingTop: 'var(--spacing-8)' }}>
          <label className="history-page__compare-pm-toggle" style={{ justifySelf: 'start' }}>
            <input type="checkbox" checked={showFullPm} onChange={onToggleFullPm} />
            Full PM markdown
          </label>
          <div className="compare-two-col">
            {[a, b].map((side, idx) => (
              <div
                key={idx}
                className="markdown-body"
                style={{
                  fontSize: 'var(--text-caption)',
                  padding: 'var(--spacing-16)',
                  background: 'var(--surface-canvas-fog)',
                  border: '1px solid var(--color-stone-border)',
                  borderRadius: 'var(--radius-cards)',
                  maxHeight: 360,
                  overflow: 'auto',
                }}
              >
                {showFullPm && side.reports?.portfolio_decision?.trim() ? (
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={REPORT_MD_COMPONENTS}>
                    {prepareReportMarkdown('portfolio_decision', side.reports.portfolio_decision)}
                  </ReactMarkdown>
                ) : (
                  <pre className="mono" style={{ margin: 0, whiteSpace: 'pre-wrap', fontSize: 'var(--text-caption)', lineHeight: 1.55 }}>
                    {side.excerpt_portfolio_decision || '—'}
                  </pre>
                )}
              </div>
            ))}
          </div>
        </div>
      </CompareSection>
    </div>
  );
}
