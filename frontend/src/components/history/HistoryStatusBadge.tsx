import { memo } from "react";
import { historyStatusTone, statusLabel, type HistoryJobStatus } from "../../utils/historyDisplay";

export const HistoryStatusBadge = memo(function HistoryStatusBadge({ status }: { status: HistoryJobStatus }) {
  const tone = historyStatusTone(status);
  return (
    <span className={`history-status-badge history-status-badge--${tone}`}>
      <span className="history-status-badge__dot" aria-hidden />
      {statusLabel(status)}
    </span>
  );
});
