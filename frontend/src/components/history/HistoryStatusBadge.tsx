import { historyStatusTone, statusLabel, type HistoryJobStatus } from "../../utils/historyDisplay";

export function HistoryStatusBadge({ status }: { status: HistoryJobStatus }) {
  const tone = historyStatusTone(status);
  return (
    <span className={`history-status-badge history-status-badge--${tone}`}>
      <span className="history-status-badge__dot" aria-hidden />
      {statusLabel(status)}
    </span>
  );
}
