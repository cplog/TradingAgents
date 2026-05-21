import { useMemo } from "react";
import type { JobResultPayload } from "../api";
import { extractVisualEvidence } from "../utils/jobVisuals";

const PRICE_VIEWBOX_W = 640;
const PRICE_VIEWBOX_H = 240;
const PRICE_PADDING = 20;

function minMax(values: number[]): { min: number; max: number } {
  if (!values.length) return { min: 0, max: 1 };
  let min = values[0];
  let max = values[0];
  for (let i = 1; i < values.length; i += 1) {
    if (values[i] < min) min = values[i];
    if (values[i] > max) max = values[i];
  }
  if (min === max) return { min: min - 1, max: max + 1 };
  return { min, max };
}

function PriceCandles({ result }: { result: JobResultPayload | null | undefined }) {
  const data = useMemo(() => extractVisualEvidence(result).ohlcvSeries, [result]);
  if (!data.length) return null;
  const domain = minMax(data.flatMap((row) => [row.low, row.high]));
  const innerW = PRICE_VIEWBOX_W - PRICE_PADDING * 2;
  const innerH = PRICE_VIEWBOX_H - PRICE_PADDING * 2;
  const step = innerW / Math.max(1, data.length);
  const wickWidth = Math.max(1, Math.min(8, step * 0.16));
  const bodyWidth = Math.max(2, Math.min(14, step * 0.72));
  const yFor = (value: number) =>
    PRICE_PADDING + ((domain.max - value) / (domain.max - domain.min)) * innerH;
  const last = data[data.length - 1];
  return (
    <article className="evidence-placeholders__card">
      <h4 className="evidence-placeholders__title">Price chart (OHLCV)</h4>
      <div className="chart-panel" style={{ marginBottom: 0 }}>
        <svg viewBox={`0 0 ${PRICE_VIEWBOX_W} ${PRICE_VIEWBOX_H}`} width="100%" height={220} role="img">
          <title>Recent OHLCV candles</title>
          {data.map((row, i) => {
            const cx = PRICE_PADDING + step * i + step / 2;
            const yHigh = yFor(row.high);
            const yLow = yFor(row.low);
            const yOpen = yFor(row.open);
            const yClose = yFor(row.close);
            const rise = row.close >= row.open;
            const bodyTop = Math.min(yOpen, yClose);
            const bodyHeight = Math.max(1.2, Math.abs(yClose - yOpen));
            return (
              <g key={`${row.date}-${i}`}>
                <line
                  x1={cx}
                  x2={cx}
                  y1={yHigh}
                  y2={yLow}
                  stroke="var(--color-steel-gray)"
                  strokeWidth={wickWidth}
                  opacity={0.9}
                />
                <rect
                  x={cx - bodyWidth / 2}
                  y={bodyTop}
                  width={bodyWidth}
                  height={bodyHeight}
                  fill={rise ? "var(--color-phosphor)" : "var(--color-danger)"}
                  opacity={0.95}
                  rx={1}
                />
              </g>
            );
          })}
        </svg>
        <p className="evidence-placeholders__body" style={{ marginTop: "var(--spacing-8)" }}>
          {data.length} bars · latest close {last.close.toFixed(2)} ({last.date})
        </p>
      </div>
    </article>
  );
}

function KronosBand({ result }: { result: JobResultPayload | null | undefined }) {
  const forecast = useMemo(() => extractVisualEvidence(result).kronosForecast, [result]);
  if (!forecast.length) return null;
  const lows = forecast.map((f) => f.low);
  const highs = forecast.map((f) => f.high);
  const closes = forecast.map((f) => f.close);
  const domain = minMax([...lows, ...highs, ...closes]);
  const w = 640;
  const h = 220;
  const pad = 20;
  const innerW = w - pad * 2;
  const innerH = h - pad * 2;
  const step = innerW / Math.max(1, forecast.length - 1);
  const yFor = (value: number) => pad + ((domain.max - value) / (domain.max - domain.min)) * innerH;
  const xFor = (i: number) => pad + step * i;
  const bandPath =
    forecast
      .map((row, i) => `${i === 0 ? "M" : "L"} ${xFor(i).toFixed(2)} ${yFor(row.high).toFixed(2)}`)
      .join(" ") +
    " " +
    forecast
      .map((_, i) => {
        const r = forecast.length - 1 - i;
        return `L ${xFor(r).toFixed(2)} ${yFor(forecast[r].low).toFixed(2)}`;
      })
      .join(" ") +
    " Z";
  const closePath = forecast
    .map((row, i) => `${i === 0 ? "M" : "L"} ${xFor(i).toFixed(2)} ${yFor(row.close).toFixed(2)}`)
    .join(" ");
  const first = forecast[0];
  const last = forecast[forecast.length - 1];
  return (
    <article className="evidence-placeholders__card">
      <h4 className="evidence-placeholders__title">Kronos forecast band</h4>
      <div className="chart-panel" style={{ marginBottom: 0 }}>
        <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={210} role="img">
          <title>Kronos OHLC forecast envelope</title>
          <path d={bandPath} fill="var(--color-phosphor-glow)" />
          <path d={closePath} fill="none" stroke="var(--color-phosphor)" strokeWidth={2.5} />
        </svg>
        <p className="evidence-placeholders__body" style={{ marginTop: "var(--spacing-8)" }}>
          {forecast.length} steps · close {first.close.toFixed(2)} → {last.close.toFixed(2)}
        </p>
      </div>
    </article>
  );
}

function EvidenceChainCard({ result }: { result: JobResultPayload | null | undefined }) {
  const xml = useMemo(() => extractVisualEvidence(result).evidenceChainXml, [result]);
  if (!xml) {
    return (
      <article className="evidence-placeholders__card">
        <h4 className="evidence-placeholders__title">Evidence chain map</h4>
        <p className="evidence-placeholders__body">
          Interactive transmission diagram (Draw.io XML or rendered graph). Requires logic_visualizer
          artifact export.
        </p>
      </article>
    );
  }
  const nodeCount = (xml.match(/<mxCell\b/g) ?? []).length;
  return (
    <article className="evidence-placeholders__card">
      <h4 className="evidence-placeholders__title">Evidence chain map</h4>
      <p className="evidence-placeholders__body">
        Draw.io XML detected ({nodeCount.toLocaleString()} cells). Rendering can be added in a follow-up
        using this payload.
      </p>
    </article>
  );
}

export function EvidencePlaceholderCards({ result }: { result?: JobResultPayload | null }) {
  const evidence = useMemo(() => extractVisualEvidence(result), [result]);
  const hasLiveVisuals = evidence.ohlcvSeries.length > 0 || evidence.kronosForecast.length > 0;
  return (
    <section className="evidence-placeholders" aria-label="Visual evidence">
      <p className="ui-label" style={{ margin: "0 0 var(--spacing-8)" }}>
        {hasLiveVisuals ? "Visual evidence" : "Planned visuals (waiting for payloads)"}
      </p>
      <div className="evidence-placeholders__grid">
        <PriceCandles result={result} />
        <KronosBand result={result} />
        {!evidence.ohlcvSeries.length && (
          <article className="evidence-placeholders__card">
            <h4 className="evidence-placeholders__title">Price chart (OHLCV)</h4>
            <p className="evidence-placeholders__body">
              30-day candlestick panel with key levels. Requires structured OHLCV series in job results.
            </p>
          </article>
        )}
        {!evidence.kronosForecast.length && (
          <article className="evidence-placeholders__card">
            <h4 className="evidence-placeholders__title">Kronos forecast band</h4>
            <p className="evidence-placeholders__body">
              5-day forecast with confidence intervals. Requires kronos_forecast payload from the predictor
              pass.
            </p>
          </article>
        )}
        <EvidenceChainCard result={result} />
      </div>
    </section>
  );
}
