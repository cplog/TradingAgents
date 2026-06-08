/**
 * Shared export toolbar for completed agent reports (HTML, print/PDF, markdown).
 */

type ReportExportBarProps = {
  onExportHtml: () => void;
  onExportPng: () => void;
  onExportMarkdown: () => void;
  onPrint: () => void;
  disabled?: boolean;
  disabledHint?: string;
  /** Pins the bar under the app header while scrolling long reports. */
  sticky?: boolean;
  className?: string;
};

export function ReportExportBar({
  onExportHtml,
  onExportPng,
  onExportMarkdown,
  onPrint,
  disabled = false,
  disabledHint,
  sticky = false,
  className = "",
}: ReportExportBarProps) {
  const rootClass = [
    "report-export-bar",
    sticky ? "report-export-bar--sticky" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={rootClass} role="toolbar" aria-label="Export report">
      <div className="report-export-bar__lead">
        <span className="report-export-bar__title">Export report</span>
        <span className="report-export-bar__hint">
          {disabled && disabledHint
            ? disabledHint
            : "HTML archive · summary PNG · browser PDF · sanitized markdown"}
        </span>
      </div>
      <div className="report-export-bar__actions">
        <button
          type="button"
          className="ui-btn-secondary"
          onClick={onExportHtml}
          disabled={disabled}
          title="Download a self-contained HTML file (summary + full report)."
        >
          HTML
        </button>
        <button
          type="button"
          className="ui-btn-secondary"
          onClick={onExportPng}
          disabled={disabled}
          title="Download a high-DPI PNG of the decision summary card (not the full report)."
        >
          PNG (summary)
        </button>
        <button
          type="button"
          className="ui-btn-secondary"
          onClick={onPrint}
          disabled={disabled}
          title="Opens a print-ready report tab (no app sidebar). Choose Save as PDF in the dialog."
        >
          Print / PDF
        </button>
        <button
          type="button"
          className="ui-btn-secondary"
          onClick={onExportMarkdown}
          disabled={disabled}
          title="Download markdown matching the on-screen report (sanitized, section-ordered)."
        >
          Markdown
        </button>
      </div>
    </div>
  );
}
