import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { NewsItem } from "../../api";

function sentimentScore(s: NewsItem["sentiment"]): number {
  if (s === "bullish") return 1;
  if (s === "bearish") return -1;
  return 0;
}

function dayKey(pubDate: string | undefined, index: number): string {
  if (pubDate) {
    const d = pubDate.slice(0, 10);
    if (/^\d{4}-\d{2}-\d{2}$/.test(d)) return d;
  }
  return `item-${index}`;
}

export function SentimentTimelineChart({ items }: { items: NewsItem[] }) {
  const buckets = new Map<string, { sum: number; n: number }>();
  items.forEach((it, i) => {
    const key = dayKey(it.pub_date, i);
    const prev = buckets.get(key) ?? { sum: 0, n: 0 };
    prev.sum += sentimentScore(it.sentiment);
    prev.n += 1;
    buckets.set(key, prev);
  });

  const data = [...buckets.entries()]
    .map(([day, { sum, n }]) => ({
      day,
      score: n ? sum / n : 0,
      articles: n,
    }))
    .sort((a, b) => a.day.localeCompare(b.day));

  if (data.length < 2) {
    return (
      <p className="chart-empty">
        Need at least two time buckets to plot sentiment trend (load more articles or widen sources).
      </p>
    );
  }

  return (
    <div className="chart-panel" aria-label="Sentiment timeline">
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--color-stone-border)" strokeDasharray="3 3" />
          <XAxis dataKey="day" tick={{ fontSize: 10, fill: "var(--color-ash-gray)" }} />
          <YAxis
            domain={[-1, 1]}
            ticks={[-1, 0, 1]}
            tick={{ fontSize: 10, fill: "var(--color-ash-gray)" }}
          />
          <Tooltip
            contentStyle={{
              background: "var(--surface-elevated)",
              border: "1px solid var(--color-stone-border)",
              borderRadius: "var(--radius-md)",
              color: "var(--color-slate-text)",
            }}
            formatter={(value, _name, props) => [
              Number(value).toFixed(2),
              `avg · ${(props.payload as { articles: number }).articles} articles`,
            ]}
          />
          <Line
            type="monotone"
            dataKey="score"
            stroke="var(--color-phosphor)"
            strokeWidth={2}
            dot={{ r: 3, fill: "var(--color-phosphor)" }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
