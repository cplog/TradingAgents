type Props = {
  summary: string | null | undefined;
};

export function ThemeSummary({ summary }: Props) {
  if (!summary?.trim()) {
    return <p className="topics-empty">No theme summary yet. Run a refresh.</p>;
  }
  return <div className="topics-theme-summary">{summary}</div>;
}
