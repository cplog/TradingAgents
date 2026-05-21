import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { HistoryRunRef } from "../../api";

function normalizeRating(r: string | null | undefined): string {
  if (!r || typeof r !== "string") return "Unknown";
  return r.trim() || "Unknown";
}

export function HistoryRatingChart({ runs }: { runs: HistoryRunRef[] }) {
  const counts = new Map<string, number>();
  for (const row of runs) {
    const label = normalizeRating(row.rating);
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }

  const data = [...counts.entries()]
    .map(([rating, count]) => ({ rating, count }))
    .sort((a, b) => b.count - a.count);

  if (!data.length) {
    return <p className="chart-empty">No rating data in this sample.</p>;
  }

  return (
    <div className="chart-panel" aria-label="Rating distribution">
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} layout="vertical" margin={{ top: 8, right: 12, left: 8, bottom: 0 }}>
          <CartesianGrid stroke="var(--color-stone-border)" strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" tick={{ fontSize: 10, fill: "var(--color-ash-gray)" }} allowDecimals={false} />
          <YAxis
            type="category"
            dataKey="rating"
            width={100}
            tick={{ fontSize: 10, fill: "var(--color-slate-text)" }}
          />
          <Tooltip
            contentStyle={{
              background: "var(--surface-elevated)",
              border: "1px solid var(--color-stone-border)",
              borderRadius: "var(--radius-md)",
            }}
          />
          <Bar dataKey="count" fill="var(--color-phosphor)" radius={[0, 2, 2, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
