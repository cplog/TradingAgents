import type { JobResultPayload } from "../api";

type Dict = Record<string, unknown>;

export type OhlcvRow = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
};

export type KronosForecastRow = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
};

export type VisualEvidence = {
  ohlcvSeries: OhlcvRow[];
  kronosForecast: KronosForecastRow[];
  evidenceChainXml: string | null;
};

function asDict(v: unknown): Dict | null {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Dict) : null;
}

function toFiniteNumber(v: unknown): number | null {
  const n = typeof v === "number" ? v : typeof v === "string" ? Number(v) : NaN;
  return Number.isFinite(n) ? n : null;
}

function toDateString(v: unknown): string | null {
  if (typeof v !== "string") return null;
  const t = v.trim();
  return t ? t : null;
}

function toOhlcvRow(v: unknown): OhlcvRow | null {
  const d = asDict(v);
  if (!d) return null;
  const date = toDateString(d.date);
  const open = toFiniteNumber(d.open);
  const high = toFiniteNumber(d.high);
  const low = toFiniteNumber(d.low);
  const close = toFiniteNumber(d.close);
  if (!date || open == null || high == null || low == null || close == null) return null;
  const volume = toFiniteNumber(d.volume);
  return volume == null
    ? { date, open, high, low, close }
    : { date, open, high, low, close, volume };
}

function pickRows(v: unknown): OhlcvRow[] {
  if (!Array.isArray(v)) return [];
  const rows: OhlcvRow[] = [];
  for (const item of v) {
    const row = toOhlcvRow(item);
    if (row) rows.push(row);
  }
  return rows;
}

function toForecastRow(v: unknown): KronosForecastRow | null {
  const d = asDict(v);
  if (!d) return null;
  const date = toDateString(d.date);
  const point = toFiniteNumber(d.point);
  const close = toFiniteNumber(d.close ?? point);
  const high = toFiniteNumber(d.high ?? d.upper ?? close);
  const low = toFiniteNumber(d.low ?? d.lower ?? close);
  const open = toFiniteNumber(d.open ?? close);
  if (!date || open == null || high == null || low == null || close == null) return null;
  const volume = toFiniteNumber(d.volume);
  return volume == null
    ? { date, open, high, low, close }
    : { date, open, high, low, close, volume };
}

function pickForecast(v: unknown): KronosForecastRow[] {
  if (!Array.isArray(v)) return [];
  const rows: KronosForecastRow[] = [];
  for (const item of v) {
    const row = toForecastRow(item);
    if (row) rows.push(row);
  }
  return rows;
}

function pickString(v: unknown): string | null {
  if (typeof v !== "string") return null;
  const t = v.trim();
  return t || null;
}

function hasDrawIoXml(v: string | null): boolean {
  return Boolean(v && (v.includes("<mxfile") || v.includes("<mxGraphModel")));
}

function takeRecent<T>(rows: T[], maxPoints: number): T[] {
  if (rows.length <= maxPoints) return rows;
  return rows.slice(rows.length - maxPoints);
}

function firstNonEmpty<T>(...candidates: T[][]): T[] {
  for (const rows of candidates) {
    if (rows.length) return rows;
  }
  return [];
}

export function extractVisualEvidence(result: JobResultPayload | null | undefined): VisualEvidence {
  if (!result) return { ohlcvSeries: [], kronosForecast: [], evidenceChainXml: null };
  const root = result as unknown as Dict;
  const visual = asDict(root.visual_artifacts);
  const structured = asDict(root.structured);
  const kronosTop = asDict(root.kronos_forecast);
  const kronosNested = asDict(structured?.kronos_forecast) ?? asDict(structured?.kronos);
  const kronos = kronosTop ?? kronosNested;

  const ohlcvSeries = takeRecent(
    firstNonEmpty(
      pickRows(visual?.ohlcv_series),
      pickRows(kronos?.history_tail),
      pickRows(structured?.ohlcv_series),
    ),
    60,
  );

  const kronosForecast = takeRecent(
    firstNonEmpty(
      pickForecast(visual?.kronos_forecast),
      pickForecast(kronos?.forecast),
      pickForecast(structured?.kronos_forecast),
    ),
    30,
  );

  const xmlCandidate =
    pickString(visual?.evidence_chain_xml) ??
    pickString(root.logic_visualizer_xml) ??
    pickString(root.evidence_chain_xml) ??
    pickString(structured?.logic_visualizer_xml);
  const evidenceChainXml = hasDrawIoXml(xmlCandidate) ? xmlCandidate : null;

  return { ohlcvSeries, kronosForecast, evidenceChainXml };
}
